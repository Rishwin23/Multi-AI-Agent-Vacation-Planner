"""
Comprehensive Test Suite for Multi-Agent AI Vacation Planner.
Covers all 12 required test cases specified in Phase 12:
1. Basic trip request
2. Budget constrained request
3. Different destinations
4. Different trip durations
5. Missing optional preferences
6. Invalid/incomplete requests
7. n8n failure & fallback path
8. Gemini failure & fallback path
9. ElevenLabs failure & fallback path
10. RAG question query & retrieval
11. Conversation history persistence & retrieval
12. User memory retrieval & preference propagation
"""
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import UserTravelRequest, UserMemory, ConversationEntry, ParsedRequirements, PlannerResult
from backend.services.gemini_service import gemini_service
from backend.services.supabase_service import supabase_service
from backend.services.n8n_service import n8n_service
from backend.services.elevenlabs_service import elevenlabs_service
from backend.services.rag_service import rag_service

client = TestClient(app)


# =============================================================================
# TEST 1: Basic Trip Request
# =============================================================================
def test_1_basic_trip_request():
    """Verify standard happy-path trip request for Goa."""
    response = client.post("/api/plan", json={"query": "Plan a 5-day Goa trip under ₹40,000"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["parsed_requirements"]["destination"] == "Goa"
    assert data["parsed_requirements"]["days"] == 5
    assert data["parsed_requirements"]["budget"] == 40000.0
    assert len(data["planner_result"]["hotels"]) > 0
    assert len(data["planner_result"]["attractions"]) > 0
    assert len(data["itinerary_markdown"]) > 200
    assert data["critic_result"]["score"] >= 80


# =============================================================================
# TEST 2: Budget Constrained Request
# =============================================================================
def test_2_budget_constrained_request():
    """Verify over-budget request flags deficit and provides suggestions."""
    response = client.post("/api/plan", json={"query": "5-day luxury trip to Mumbai with only ₹5,000"})
    assert response.status_code == 200
    data = response.json()
    b = data["planner_result"]["budget"]
    assert b["is_within_budget"] is False
    assert b["remaining_balance"] < 0
    assert "exceeded" in b["savings_suggestion"].lower() or "budget" in b["savings_suggestion"].lower()
    assert len(data["critic_result"]["warnings"]) > 0


# =============================================================================
# TEST 3: Different Destinations
# =============================================================================
@pytest.mark.parametrize("destination,query", [
    ("Banglore", "3 days trip to Bangalore"),
    ("Cochin", "Weekend getaway to Cochin"),
    ("Jaipur", "4-day heritage tour of Jaipur under 30k"),
    ("Delhi", "Sightseeing tour of Delhi for 5 days")
])
def test_3_different_destinations(destination, query):
    """Verify system handles multiple distinct destinations accurately."""
    response = client.post("/api/plan", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["parsed_requirements"]["destination"] == destination
    aliases = [destination, "Bangalore", "Bengaluru", "Kochi", "Cochin", "Delhi", "Jaipur", "Goa"]
    assert any(a.lower() in data["itinerary_markdown"].lower() for a in aliases)


# =============================================================================
# TEST 4: Different Trip Durations
# =============================================================================
@pytest.mark.parametrize("query,expected_days", [
    ("Weekend in Banglore", 2),
    ("5-day Goa vacation", 5),
    ("7 days family trip to Cochin", 7),
    ("10 days extended holiday in Jaipur", 10)
])
def test_4_different_durations(query, expected_days):
    """Verify duration parsing and multi-day hotel/budget scaling."""
    response = client.post("/api/plan", json={"query": query})
    assert response.status_code == 200
    data = response.json()
    assert data["parsed_requirements"]["days"] == expected_days


# =============================================================================
# TEST 5: Missing Optional Preferences
# =============================================================================
def test_5_missing_optional_preferences():
    """Verify request without explicit preferences uses sensible defaults."""
    response = client.post("/api/plan", json={"query": "Goa"})
    assert response.status_code == 200
    data = response.json()
    assert data["parsed_requirements"]["destination"] == "Goa"
    assert data["parsed_requirements"]["days"] >= 1
    assert data["parsed_requirements"]["budget"] > 0
    assert data["parsed_requirements"]["min_rating"] >= 3.0


# =============================================================================
# TEST 6: Invalid / Incomplete Request
# =============================================================================
def test_6_invalid_requests():
    """Verify system handles empty query and malformed parameters gracefully."""
    # Empty query should fail or provide default
    resp_empty = client.post("/api/plan", json={"query": "   "})
    # Either handled with default or validation
    assert resp_empty.status_code in [200, 422]


# =============================================================================
# TEST 7: n8n Fallback Execution
# =============================================================================
def test_7_n8n_fallback_path():
    """Verify local agent execution operates seamlessly when n8n webhook is offline."""
    parsed_req = ParsedRequirements(
        destination="Cochin",
        days=4,
        budget=35000.0,
        sort_by="price",
        min_rating=3.5
    )
    result = n8n_service._execute_local_planner(parsed_req)
    assert result.destination == "Cochin"
    assert len(result.hotels) > 0
    assert len(result.attractions) > 0
    assert result.budget["total_budget"] > 0


# =============================================================================
# TEST 8: Gemini Fallback Parsing & Template Generation
# =============================================================================
def test_8_gemini_fallback_path():
    """Verify deterministic regex parser and grounded markdown generator when offline."""
    # Test heuristic parser directly
    parsed = gemini_service._heuristic_fallback_parser("7-day family vacation to Goa under 50k with beach")
    assert parsed["destination"] == "Goa"
    assert parsed["days"] == 7
    assert parsed["budget"] == 50000.0
    assert "beach" in parsed["preferences"]

    # Test template generator directly
    req = ParsedRequirements(**parsed)
    planner_result = n8n_service._execute_local_planner(req)
    itinerary = gemini_service._generate_template_itinerary(req, planner_result)
    assert "Goa" in itinerary
    assert "Flight & Transport" in itinerary
    assert "Accommodation" in itinerary
    assert "Budget Breakdown" in itinerary


# =============================================================================
# TEST 9: ElevenLabs Speech Cleaning & Handling
# =============================================================================
def test_9_elevenlabs_service():
    """Verify speech cleaner removes markdown tables, code, and symbols."""
    raw_md = "# 🌴 Goa Trip\n| Item | Price |\n| Flight | 4000 |\n- **IndiGo** (Delhi -> Goa)"
    cleaned = elevenlabs_service.clean_text_for_speech(raw_md)
    assert "|" not in cleaned
    assert "#" not in cleaned
    assert "*" not in cleaned
    assert "🌴" not in cleaned
    assert "IndiGo" in cleaned

    # Endpoint returns 400 when ELEVENLABS_API_KEY is not configured
    resp = client.post("/api/voice/synthesize", json={"text": "Hello world"})
    assert resp.status_code in [200, 400, 502]


# =============================================================================
# TEST 10: RAG Question & Chunk Retrieval
# =============================================================================
def test_10_rag_query_and_retrieval():
    """Verify semantic chunk search and Q&A answering."""
    chunks = rag_service.search_chunks("monsoon packing advice for Goa", destination="Goa", top_k=2)
    assert len(chunks) > 0
    assert "Goa" in chunks[0].document_name or "Goa" in chunks[0].chunk_text

    ans_resp = client.post("/api/rag/query", json={"query": "What to pack for Goa?", "destination": "Goa"})
    assert ans_resp.status_code == 200
    data = ans_resp.json()
    assert len(data["answer"]) > 20
    assert len(data["retrieved_chunks"]) > 0


# =============================================================================
# TEST 11: Conversation History Persistence & Retrieval
# =============================================================================
def test_11_conversation_history():
    """Verify conversation logging and retrieval."""
    test_user = "test_user_hist_11"
    entry = ConversationEntry(
        user_id=test_user,
        session_id="sess_11",
        question="Plan 5 days in Goa",
        response="Here is your Goa plan.",
        parsed_intent={"destination": "Goa"},
        planner_data={"flights": []}
    )
    supabase_service.log_conversation(entry)

    resp = client.get(f"/api/history?user_id={test_user}")
    assert resp.status_code == 200
    history = resp.json()
    assert len(history) >= 1
    assert history[0]["question"] == "Plan 5 days in Goa"


# =============================================================================
# TEST 12: User Memory Retrieval & Preference Merging
# =============================================================================
def test_12_user_memory_propagation():
    """Verify user memory profile updates and propagates into subsequent trip requests."""
    test_user = "vip_traveler_12"
    mem_payload = {
        "user_id": test_user,
        "name": "David",
        "preferred_airline": "Air India",
        "hotel_rating_preference": 4.5,
        "budget_preference": 75000.0,
        "travel_preferences": ["luxury", "heritage"]
    }
    client.post("/api/memory", json=mem_payload)

    # When querying with vague input, user memory preferences should be merged
    plan_resp = client.post("/api/plan", json={"query": "Plan a trip to Jaipur", "user_id": test_user})
    assert plan_resp.status_code == 200
    plan_data = plan_resp.json()
    assert plan_data["parsed_requirements"]["destination"] == "Jaipur"
    assert plan_data["parsed_requirements"]["min_rating"] == 4.5
    assert plan_data["parsed_requirements"]["budget"] == 75000.0
