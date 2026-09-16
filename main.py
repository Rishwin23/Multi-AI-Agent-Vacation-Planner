"""
FastAPI Server Entry Point for Vacation Planner.
Exposes REST APIs for:
- Vacation Itinerary Planning (/api/plan)
- Natural Language Request Parsing (/api/parse)
- ElevenLabs Text-to-Speech (/api/voice/synthesize)
- Conversation History & User Memory (/api/history, /api/memory)
- RAG Destination Knowledge Search (/api/rag/query)
- Health Check (/api/health)
"""
import os
import time
import uuid
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.config import settings
from backend.models import (
    UserTravelRequest,
    ParsedRequirements,
    VacationPlanResponse,
    UserMemory,
    ConversationEntry,
    RagQueryRequest,
    RagQueryResponse
)
from backend.services.gemini_service import gemini_service
from backend.services.n8n_service import n8n_service
from backend.services.supabase_service import supabase_service
from backend.services.rag_service import rag_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s")
logger = logging.getLogger("vacation_planner.main")

app = FastAPI(
    title="Multi-Agent AI Vacation Planner API",
    description="Intelligent trip planning powered by coordinated multi-agents, Supabase, Gemini, and ElevenLabs.",
    version="1.0.0"
)

# Enable CORS for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# =============================================================================
# API ROUTES
# =============================================================================

@app.get("/api/health")
def health_check():
    """Returns the operational status of all platform integrations."""
    return {
        "status": "healthy",
        "gemini": "configured" if settings.has_gemini_key else "fallback_mode",
        "elevenlabs": "configured" if settings.has_elevenlabs_key else "fallback_mode",
        "supabase": "configured" if settings.has_supabase else "local_csv_mode",
        "n8n_webhook": "configured" if bool(settings.N8N_WEBHOOK_URL) else "local_orchestrator",
        "agents": ["Flight Agent", "Hotel Agent", "Weather Agent", "Attraction Agent", "Budget Agent", "Planner Agent"]
    }


@app.post("/api/parse", response_model=ParsedRequirements)
def parse_travel_query(request: UserTravelRequest):
    """Parses a free-text travel query into structured requirements (TASK A)."""
    user_mem = supabase_service.get_user_memory(request.user_id or "default_user")
    parsed = gemini_service.parse_user_request(
        query=request.query,
        user_memory=user_mem,
        explicit_overrides={
            "explicit_destination": request.explicit_destination,
            "explicit_days": request.explicit_days,
            "explicit_budget": request.explicit_budget,
            "explicit_origin": request.explicit_origin,
            "sort_by": request.sort_by,
            "min_rating": request.min_rating
        }
    )
    return parsed


@app.post("/api/plan", response_model=VacationPlanResponse)
def plan_vacation(request: UserTravelRequest, background_tasks: BackgroundTasks):
    """
    Complete end-to-end trip planning workflow:
    1. Parse natural language request (Gemini Task A).
    2. Invoke Planner Agent (which calls Flight, Hotel, Weather, Attraction, Budget agents).
    3. Generate personalized itinerary (Gemini Task B).
    4. Run Critic / Reflection quality review (Phase 10).
    5. Log conversation history (Supabase Phase 7).
    """
    start_time = time.time()
    session_id = request.session_id or str(uuid.uuid4())
    user_id = request.user_id or "default_user"

    try:
        # Step 1: User Memory retrieval
        user_mem = supabase_service.get_user_memory(user_id)

        # Step 2: Parse Request (Task A)
        parsed_req = gemini_service.parse_user_request(
            query=request.query,
            user_memory=user_mem,
            explicit_overrides={
                "explicit_destination": request.explicit_destination,
                "explicit_days": request.explicit_days,
                "explicit_budget": request.explicit_budget,
                "explicit_origin": request.explicit_origin,
                "sort_by": request.sort_by,
                "min_rating": request.min_rating
            }
        )

        # Step 3: Execute Planner Agent (calls the 5 specialized agents)
        planner_result = n8n_service.execute_planner(parsed_req)

        # Step 4: RAG Knowledge Retrieval (Phase 9)
        rag_context = rag_service.get_enriched_context(parsed_req.destination, parsed_req.raw_query)

        # Step 5: Generate Grounded Final Itinerary (Task B)
        itinerary_md = gemini_service.generate_itinerary(
            parsed_req=parsed_req,
            planner_result=planner_result,
            user_memory=user_mem,
            rag_context=rag_context
        )

        # Step 6: Reflection / Critic Check (Phase 10)
        critic_result = gemini_service.critique_itinerary(
            itinerary_markdown=itinerary_md,
            parsed_req=parsed_req,
            planner_result=planner_result
        )

        # Step 6: Log conversation history in background
        history_entry = ConversationEntry(
            user_id=user_id,
            session_id=session_id,
            question=request.query,
            response=itinerary_md,
            parsed_intent=parsed_req.model_dump(),
            planner_data=planner_result.model_dump()
        )
        background_tasks.add_task(supabase_service.log_conversation, history_entry)

        elapsed = round(time.time() - start_time, 2)

        return VacationPlanResponse(
            success=True,
            user_id=user_id,
            session_id=session_id,
            query=request.query,
            parsed_requirements=parsed_req,
            planner_result=planner_result,
            itinerary_markdown=itinerary_md,
            critic_result=critic_result,
            execution_time_seconds=elapsed
        )

    except Exception as e:
        logger.exception(f"Error executing trip planner: {e}")
        elapsed = round(time.time() - start_time, 2)
        raise HTTPException(status_code=500, detail=f"Vacation Planner encountered an error: {str(e)}")


from fastapi.responses import FileResponse, JSONResponse, Response
from backend.services.elevenlabs_service import elevenlabs_service

class VoiceSynthesisRequest(BaseModel):
    text: str
    voice_id: Optional[str] = None


@app.post("/api/voice/synthesize")
def synthesize_voice(req: VoiceSynthesisRequest):
    """
    Synthesizes itinerary text into speech audio using ElevenLabs.
    Returns audio/mpeg stream.
    """
    try:
        audio_bytes = elevenlabs_service.synthesize_speech(req.text, voice_id=req.voice_id)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Voice synthesis error: {e}")
        raise HTTPException(status_code=502, detail=f"ElevenLabs TTS service error: {str(e)}")


@app.get("/api/history")
def get_history(user_id: str = Query("default_user", description="User ID"), limit: int = 10):
    """Fetches recent conversation history."""
    return supabase_service.get_conversation_history(user_id=user_id, limit=limit)


@app.get("/api/memory", response_model=UserMemory)
def get_memory(user_id: str = Query("default_user", description="User ID")):
    """Fetches user memory and travel preferences."""
    return supabase_service.get_user_memory(user_id=user_id)


@app.post("/api/memory", response_model=UserMemory)
def update_memory(memory: UserMemory):
    """Updates user memory and travel preferences."""
    supabase_service.update_user_memory(memory)
    return memory


@app.post("/api/rag/query", response_model=RagQueryResponse)
def query_travel_knowledge(req: RagQueryRequest):
    """
    RAG Destination Knowledge Query endpoint.
    Retrieves vector chunks and generates context-aware travel guidance.
    """
    return rag_service.answer_travel_question(query=req.query, destination=req.destination)


# =============================================================================
# FRONTEND STATIC ASSETS & SINGLE PAGE APPLICATION SERVING
# =============================================================================
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_frontend_index():
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Frontend index.html not found."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=True)
