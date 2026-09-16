"""
Database Seeding Script for Vacation Planner.
Populates Supabase tables from CSV datasets and seeds travel knowledge for RAG.
Usage:
    python -m backend.database.seed_data
"""
import os
import sys
import logging
from pathlib import Path
import pandas as pd
import httpx

from backend.config import settings
from backend.services.gemini_service import gemini_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [%(levelname)s] - %(message)s")
logger = logging.getLogger("vacation_planner.seed")

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

TRAVEL_GUIDE_CHUNKS = [
    {
        "document_name": "Goa Travel & Beach Guide",
        "category": "Destination Guide",
        "destination": "Goa",
        "chunk_text": "Goa is renowned for its contrast between vibrant North Goa (Baga, Calangute, Anjuna) with water sports and nightlife, and tranquil South Goa (Palolem, Agonda) perfect for relaxation. The best time to visit is November to February when weather is pleasant (28°C - 32°C). Carry lightweight cottons, sunscreen, and beachwear. For local transit, renting a scooter or taxi is ideal.",
        "metadata": {"season": "Winter/Dry", "ideal_duration": "4-6 days"}
    },
    {
        "document_name": "Goa Culture & Heritage Guide",
        "category": "Heritage & Sightseeing",
        "destination": "Goa",
        "chunk_text": "Old Goa features UNESCO World Heritage Portuguese architecture including Basilica of Bom Jesus and Se Cathedral. Visit Aguada Fort for sunset coastal views and Chapora Fort for panoramic views of Vagator Beach. Entry fees to forts and churches are minimal (₹25 - ₹50).",
        "metadata": {"category": "Heritage"}
    },
    {
        "document_name": "Bangalore Travel & Tech Hub Guide",
        "category": "Destination Guide",
        "destination": "Banglore",
        "chunk_text": "Bengaluru (Bangalore) offers moderate pleasant climate year-round (20°C - 28°C). Known as the Garden City and Silicon Valley of India, must-visit spots include Lalbagh Botanical Garden, Cubbon Park, Bangalore Palace, and the vibrant dining/brewery scene in Indiranagar and Koramangala. The Namma Metro is efficient for commuting across the city.",
        "metadata": {"season": "All-Year", "ideal_duration": "2-4 days"}
    },
    {
        "document_name": "Cochin & Kerala Backwaters Guide",
        "category": "Destination Guide",
        "destination": "Cochin",
        "chunk_text": "Kochi (Cochin) is the cultural gateway to Kerala backwaters. Key highlights include the iconic Chinese Fishing Nets in Fort Kochi, Mattancherry Palace, and Jew Town with its antique spice markets. Moderate tropical climate with occasional rainfall; light breathable clothes and umbrellas are recommended. Sunset harbor cruises offer memorable views.",
        "metadata": {"season": "Winter/Post-monsoon", "ideal_duration": "3-5 days"}
    },
    {
        "document_name": "Jaipur Royal Heritage Guide",
        "category": "Destination Guide",
        "destination": "Jaipur",
        "chunk_text": "Jaipur, the Pink City of Rajasthan, is famed for magnificent forts and palaces: Amber Fort, Hawa Mahal, City Palace, and Jantar Mantar observatory. Best visited from October to March to avoid summer heat. Indulge in authentic Rajasthani thalis and shop for handicrafts in Johari and Bapu Bazaars.",
        "metadata": {"season": "Winter", "ideal_duration": "3-5 days"}
    }
]


def seed_supabase_database():
    """Uploads CSV records and RAG embeddings to Supabase."""
    if not settings.has_supabase:
        logger.warning("SUPABASE_URL and SUPABASE_KEY are not configured in .env. Skipping remote Supabase upload.")
        logger.info("Local CSV data engine is active and ready.")
        return

    headers = {
        "apikey": settings.SUPABASE_KEY or settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_KEY or settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }

    with httpx.Client(timeout=60.0) as client:
        # 1. Seed Users (Memory)
        logger.info("Seeding Users table...")
        user_payload = {
            "user_id": "default_user",
            "name": "Traveler",
            "preferred_airline": "IndiGo",
            "hotel_rating_preference": 4.0,
            "budget_preference": 40000,
            "travel_preferences": ["beach", "relaxation", "heritage"]
        }
        client.post(f"{settings.SUPABASE_URL}/rest/v1/Users", headers=headers, json=user_payload)

        # 2. Seed Flights (sample batch of 100)
        f_path = DATA_DIR / "flights.csv"
        if f_path.exists():
            logger.info("Seeding Flights table...")
            df = pd.read_csv(f_path).head(150)
            df = df.where(pd.notnull(df), None)
            records = df.to_dict(orient="records")
            client.post(f"{settings.SUPABASE_URL}/rest/v1/Flights", headers=headers, json=records)

        # 3. Seed Hotels
        h_path = DATA_DIR / "hotels.csv"
        if h_path.exists():
            logger.info("Seeding Hotels table...")
            df = pd.read_csv(h_path).head(150)
            df = df.where(pd.notnull(df), None)
            records = df.to_dict(orient="records")
            client.post(f"{settings.SUPABASE_URL}/rest/v1/Hotels", headers=headers, json=records)

        # 4. Seed Weather
        w_path = DATA_DIR / "weather.csv"
        if w_path.exists():
            logger.info("Seeding Weather table...")
            df = pd.read_csv(w_path).head(100)
            df = df.where(pd.notnull(df), None)
            records = df.to_dict(orient="records")
            client.post(f"{settings.SUPABASE_URL}/rest/v1/Weather", headers=headers, json=records)

        # 5. Seed Attractions
        a_path = DATA_DIR / "attractions.csv"
        if a_path.exists():
            logger.info("Seeding Attractions table...")
            df = pd.read_csv(a_path).head(100)
            df = df.where(pd.notnull(df), None)
            records = df.to_dict(orient="records")
            client.post(f"{settings.SUPABASE_URL}/rest/v1/Attractions", headers=headers, json=records)

        # 6. Seed RAG Embeddings
        logger.info("Seeding RAG Embeddings with vector representations...")
        for chunk in TRAVEL_GUIDE_CHUNKS:
            try:
                emb = gemini_service.generate_embedding(chunk["chunk_text"])
                chunk_record = {
                    "document_name": chunk["document_name"],
                    "category": chunk["category"],
                    "destination": chunk["destination"],
                    "chunk_text": chunk["chunk_text"],
                    "metadata": chunk["metadata"],
                    "embedding": emb
                }
                client.post(f"{settings.SUPABASE_URL}/rest/v1/Embeddings", headers=headers, json=chunk_record)
            except Exception as e:
                logger.warning(f"Failed to seed chunk '{chunk['document_name']}': {e}")

        logger.info("Supabase database seeding completed successfully!")


if __name__ == "__main__":
    seed_supabase_database()
