"""
RAG (Retrieval-Augmented Generation) Service for Vacation Planner.
Uses Supabase pgvector for semantic vector similarity search and Gemini for context-aware responses.
Includes a resilient in-memory vector search engine for offline/local development.
"""
import math
import logging
from typing import List, Dict, Any, Optional
import httpx

from backend.config import settings
from backend.models import RagDocumentChunk, RagQueryResponse
from backend.services.gemini_service import gemini_service
from backend.database.seed_data import TRAVEL_GUIDE_CHUNKS

logger = logging.getLogger("vacation_planner.rag")
logger.setLevel(logging.INFO)

ADDITIONAL_KNOWLEDGE_BASE = [
    {
        "document_name": "Goa Packing & Monsoon Advisory",
        "category": "Packing & Safety",
        "destination": "Goa",
        "chunk_text": "During monsoon season (June to September), beaches have high tides and water sports are closed. Carry waterproof rain jackets, sturdy non-slip footwear, and mosquito repellent. In peak tourist season (Nov-Feb), carry lightweight sunscreen, polarized sunglasses, beach slippers, and light cotton shirts.",
        "metadata": {"tags": ["packing", "monsoon", "safety"]}
    },
    {
        "document_name": "Bangalore Dining & Craft Breweries",
        "category": "Dining & Nightlife",
        "destination": "Banglore",
        "chunk_text": "Bengaluru is celebrated for its microbreweries in Indiranagar, Koramangala, and Lavelle Road. Try South Indian filter coffee and masala dosas at Vidyarthi Bhavan or CTR Malleshwaram. Evening commutes can have heavy traffic, so traveling outside peak rush hours (8-10 AM, 6-8 PM) is recommended.",
        "metadata": {"tags": ["food", "breweries", "traffic"]}
    },
    {
        "document_name": "Cochin Cultural & Spice Guide",
        "category": "Culture & Shopping",
        "destination": "Cochin",
        "chunk_text": "In Fort Kochi, explore Jew Town for aromatic cardamom, cloves, and cinnamon. Attend an authentic evening Kathakali dance performance at the Kerala Kathakali Centre. Modest dressing is appreciated when visiting ancient temples and religious shrines.",
        "metadata": {"tags": ["culture", "spices", "shopping"]}
    },
    {
        "document_name": "Delhi Heritage & Metro Guide",
        "category": "Transit & Heritage",
        "destination": "Delhi",
        "chunk_text": "Delhi's top historical sites include the Red Fort, Qutub Minar, Humayun's Tomb, and India Gate. The Delhi Metro is world-class, air-conditioned, and connects all major tourist spots and the Indira Gandhi International Airport. In winter (Dec-Jan), temperatures drop to 5°C-10°C, requiring warm jackets and sweaters.",
        "metadata": {"tags": ["metro", "heritage", "winter"]}
    },
    {
        "document_name": "Mumbai Coastal Promenades & Local Guidance",
        "category": "Sightseeing & Safety",
        "destination": "Mumbai",
        "chunk_text": "Key sights in Mumbai include the Gateway of India, Marine Drive (Queen's Necklace), Bandra Bandstand, and Elephanta Caves ferry. Taxis and auto-rickshaws run strictly by electronic meter. Coastal evenings are breezy and pleasant year-round.",
        "metadata": {"tags": ["coastal", "transit", "sightseeing"]}
    }
]


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


class RagService:
    def __init__(self):
        self.knowledge_base = TRAVEL_GUIDE_CHUNKS + ADDITIONAL_KNOWLEDGE_BASE
        self.cached_embeddings: Dict[str, List[float]] = {}
        self._init_local_embeddings()

    def _init_local_embeddings(self):
        """Precomputes vector embeddings for local knowledge chunks."""
        logger.info("Initializing RAG vector knowledge base...")
        for chunk in self.knowledge_base:
            key = chunk["document_name"]
            if key not in self.cached_embeddings:
                if settings.has_gemini_key:
                    try:
                        self.cached_embeddings[key] = gemini_service.generate_embedding(chunk["chunk_text"])
                    except Exception:
                        self.cached_embeddings[key] = [0.0] * 768
                else:
                    # Deterministic keyword vector for local testing
                    self.cached_embeddings[key] = [0.0] * 768

    def search_chunks(self, query: str, destination: Optional[str] = None, top_k: int = 4) -> List[RagDocumentChunk]:
        """
        Retrieves top-K most semantically relevant travel knowledge chunks.
        Queries Supabase pgvector RPC if available, or falls back to local vector search.
        """
        dest_clean = str(destination).strip().lower() if destination else None

        # 1. Supabase pgvector RPC Search
        if settings.has_supabase:
            try:
                query_vec = gemini_service.generate_embedding(query)
                headers = {
                    "apikey": settings.SUPABASE_KEY or settings.SUPABASE_SERVICE_ROLE_KEY,
                    "Authorization": f"Bearer {settings.SUPABASE_KEY or settings.SUPABASE_SERVICE_ROLE_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "query_embedding": query_vec,
                    "match_threshold": 0.25,
                    "match_count": top_k,
                    "filter_destination": destination
                }
                url = f"{settings.SUPABASE_URL}/rest/v1/rpc/match_travel_documents"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        rows = resp.json()
                        if rows:
                            return [RagDocumentChunk(**r) for r in rows]
            except Exception as e:
                logger.warning(f"Supabase pgvector RPC search error: {e}. Falling back to local vector search.")

        # 2. Local Vector / Keyword Search Engine
        query_vec = None
        if settings.has_gemini_key:
            try:
                query_vec = gemini_service.generate_embedding(query)
            except Exception:
                query_vec = None

        scored_chunks = []
        q_words = set(query.lower().split())

        for chunk in self.knowledge_base:
            chunk_dest = str(chunk.get("destination", "")).strip().lower()
            if dest_clean and chunk_dest and dest_clean not in chunk_dest and chunk_dest not in dest_clean:
                continue

            score = 0.0
            key = chunk["document_name"]
            
            # Vector similarity if embedding exists
            if query_vec and any(query_vec) and key in self.cached_embeddings:
                score = cosine_similarity(query_vec, self.cached_embeddings[key])
            
            # Keyword overlap boost
            chunk_words = set(chunk["chunk_text"].lower().split())
            overlap = len(q_words.intersection(chunk_words))
            score += (overlap * 0.15)

            if dest_clean and dest_clean in chunk["chunk_text"].lower():
                score += 0.3

            scored_chunks.append((score, chunk))

        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        results = []
        for s, c in scored_chunks[:top_k]:
            results.append(RagDocumentChunk(
                document_name=c["document_name"],
                category=c["category"],
                chunk_text=c["chunk_text"],
                similarity=round(float(s), 3),
                metadata=c.get("metadata", {})
            ))

        return results

    def answer_travel_question(self, query: str, destination: Optional[str] = None) -> RagQueryResponse:
        """Answers open-ended travel questions using RAG retrieval + Gemini synthesis."""
        chunks = self.search_chunks(query, destination=destination, top_k=3)

        context_text = "\n\n".join([f"[{c.document_name} - {c.category}]:\n{c.chunk_text}" for c in chunks])

        system_instruction = (
            "You are an expert travel advisor. Answer the user's travel question accurately "
            "based on the provided retrieved travel guide context. "
            "If the context provides specific tips, packing advice, seasons, or local customs, highlight them clearly."
        )

        user_prompt = f"### RETRIEVED TRAVEL KNOWLEDGE:\n{context_text}\n\n### USER QUESTION:\n{query}\n\nProvide a helpful, concise answer in markdown."

        answer = ""
        if settings.has_gemini_key:
            try:
                answer = gemini_service._call_gemini_api(user_prompt, system_instruction=system_instruction)
            except Exception as e:
                logger.warning(f"Gemini RAG answer generation error: {e}")

        if not answer:
            # Deterministic response built directly from retrieved knowledge
            if chunks:
                answer = f"**Here is guidance for your inquiry:**\n\n"
                for c in chunks:
                    answer += f"- **{c.document_name}:** {c.chunk_text}\n\n"
            else:
                answer = f"For travel to {destination or 'your destination'}, we recommend checking local weather, carrying appropriate footwear and clothing, and planning transport in advance."

        return RagQueryResponse(
            query=query,
            answer=answer,
            retrieved_chunks=chunks
        )

    def get_enriched_context(self, destination: str, query: Optional[str] = None) -> str:
        """Returns concise markdown string of destination tips for itinerary prompt enrichment."""
        chunks = self.search_chunks(query or f"Travel guide and advice for {destination}", destination=destination, top_k=2)
        if not chunks:
            return ""
        return "\n".join([f"- **{c.document_name}:** {c.chunk_text}" for c in chunks])


rag_service = RagService()
