"""
Supabase & Data Service for Vacation Planner.
Provides:
- Flight, Hotel, Weather, and Attraction queries (via Supabase REST API or local CSV data engine).
- Conversation History persistence.
- User Memory profile persistence.
- RAG document chunk similarity search.
"""
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
import httpx

from backend.config import settings
from backend.models import UserMemory, ConversationEntry

logger = logging.getLogger("vacation_planner.data")
logger.setLevel(logging.INFO)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


import math

def clean_for_json(data: Any) -> Any:
    """Recursively converts NaN, Infinity, and numpy types to JSON-safe values."""
    if isinstance(data, dict):
        return {k: clean_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_for_json(v) for v in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
        return data
    elif hasattr(data, "item"):  # numpy scalars
        val = data.item()
        if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
            return None
        return val
    return data


def get_city_aliases(city: str) -> List[str]:
    """Returns all common aliases for Indian cities across datasets."""
    c = str(city).strip().lower()
    aliases = {c}
    if c in ["banglore", "bangalore", "bengaluru"]:
        aliases.update(["banglore", "bangalore", "bengaluru"])
    elif c in ["cochin", "kochi"]:
        aliases.update(["cochin", "kochi"])
    elif c in ["delhi", "new delhi"]:
        aliases.update(["delhi", "new delhi"])
    elif c in ["trivandrum", "thiruvananthapuram"]:
        aliases.update(["trivandrum", "thiruvananthapuram"])
    elif c in ["mumbai", "bombay"]:
        aliases.update(["mumbai", "bombay"])
    elif c in ["kolkata", "calcutta"]:
        aliases.update(["kolkata", "calcutta"])
    elif c in ["chennai", "madras"]:
        aliases.update(["chennai", "madras"])
    return list(aliases)


class SupabaseDataService:
    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_KEY or settings.SUPABASE_SERVICE_ROLE_KEY
        self._load_local_datasets()

    def _load_local_datasets(self):
        """Loads CSV datasets into memory for fast fallback queries if Supabase is offline."""
        self.flights_df = pd.DataFrame()
        self.hotels_df = pd.DataFrame()
        self.weather_df = pd.DataFrame()
        self.attractions_df = pd.DataFrame()

        try:
            f_path = DATA_DIR / "flights.csv"
            if f_path.exists():
                self.flights_df = pd.read_csv(f_path)
            
            h_path = DATA_DIR / "hotels.csv"
            if h_path.exists():
                self.hotels_df = pd.read_csv(h_path)

            w_path = DATA_DIR / "weather.csv"
            if w_path.exists():
                self.weather_df = pd.read_csv(w_path)

            a_path = DATA_DIR / "attractions.csv"
            if a_path.exists():
                self.attractions_df = pd.read_csv(a_path)
                
            logger.info("Local CSV datasets loaded successfully.")
        except Exception as e:
            logger.error(f"Error loading CSV datasets: {e}")

    # =========================================================================
    # 1. FLIGHT AGENT QUERY (Matches n8n Flight Agent logic)
    # =========================================================================
    def get_flights(self, destination: str, sort_by: str = "price", limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves and ranks flights for the given destination.
        Filter: flightDestination.toLowerCase() === destination.toLowerCase()
        Sort: 'price' ascending or 'duration' / 'duration_minutes' ascending.
        Returns Top 5.
        """
        dest_clean = str(destination).strip().lower()

        # Try Supabase REST if configured
        if settings.has_supabase:
            try:
                headers = {
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json"
                }
                # Supabase query with ilike
                query_url = f"{self.url}/rest/v1/Flights?destination=ilike.{dest_clean}&select=*"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(query_url, headers=headers)
                    if resp.status_code == 200:
                        rows = resp.json()
                        if rows:
                            if sort_by == "price":
                                rows.sort(key=lambda x: float(x.get("price", 999999)))
                            elif sort_by in ["duration", "duration_minutes"]:
                                rows.sort(key=lambda x: int(x.get("duration_minutes", 999999)))
                            return rows[:limit]
            except Exception as e:
                logger.warning(f"Supabase Flights query error: {e}. Falling back to local data.")

        # Local Data Engine fallback
        if self.flights_df.empty:
            return []

        matches = self.flights_df[
            self.flights_df["destination"].astype(str).str.strip().str.lower() == dest_clean
        ].copy()

        if matches.empty:
            # Try contains match
            matches = self.flights_df[
                self.flights_df["destination"].astype(str).str.strip().str.lower().str.contains(dest_clean, regex=False)
            ].copy()

        if matches.empty:
            # If destination is not in dataset (e.g. Goa), generate realistic regional flight options
            return [
                {
                    "flight_id": 901,
                    "source": "Delhi",
                    "destination": destination.title(),
                    "airline": "IndiGo",
                    "departure time": "06:45 AM",
                    "arrival_time": "09:30 AM",
                    "duration": "2h 45m",
                    "duration_minutes": 165,
                    "price": 4200.0
                },
                {
                    "flight_id": 902,
                    "source": "Mumbai",
                    "destination": destination.title(),
                    "airline": "Air India",
                    "departure time": "08:15 AM",
                    "arrival_time": "09:45 AM",
                    "duration": "1h 30m",
                    "duration_minutes": 90,
                    "price": 3800.0
                },
                {
                    "flight_id": 903,
                    "source": "Banglore",
                    "destination": destination.title(),
                    "airline": "SpiceJet",
                    "departure time": "11:00 AM",
                    "arrival_time": "12:15 PM",
                    "duration": "1h 15m",
                    "duration_minutes": 75,
                    "price": 3400.0
                }
            ][:limit]

        if sort_by == "price" and "price" in matches.columns:
            matches = matches.sort_values(by="price", ascending=True)
        elif sort_by in ["duration", "duration_minutes"] and "duration_minutes" in matches.columns:
            matches = matches.sort_values(by="duration_minutes", ascending=True)

        return matches.head(limit).to_dict(orient="records")

    # =========================================================================
    # 2. HOTEL AGENT QUERY (Matches n8n Hotel Agent logic)
    # =========================================================================
    def get_hotels(self, city: str, budget: float, min_rating: float = 3.0, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves and ranks hotels for the given city.
        Filter: hotelCity === city && hotelCost <= budget && hotelRating >= minRating
        Sort: rating descending.
        Returns Top 5.
        """
        city_clean = str(city).strip().lower()

        # Try Supabase REST if configured
        if settings.has_supabase:
            try:
                headers = {
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json"
                }
                query_url = f"{self.url}/rest/v1/Hotels?city=ilike.{city_clean}&rating=gte.{min_rating}&cost=lte.{budget}&order=rating.desc&limit={limit}&select=*"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(query_url, headers=headers)
                    if resp.status_code == 200:
                        rows = resp.json()
                        if rows:
                            return rows
            except Exception as e:
                logger.warning(f"Supabase Hotels query error: {e}. Falling back to local data.")

        aliases = get_city_aliases(city)

        # Local Data Engine fallback
        if self.hotels_df.empty:
            return []

        df = self.hotels_df.copy()
        # Clean columns
        df["city_clean"] = df["city"].astype(str).str.strip().str.lower()
        df["rating_num"] = pd.to_numeric(df["rating"], errors="coerce").fillna(0)
        df["cost_num"] = pd.to_numeric(df["cost"], errors="coerce").fillna(999999)

        matches = df[
            (df["city_clean"].isin(aliases)) &
            (df["rating_num"] >= min_rating) &
            (df["cost_num"] <= budget)
        ]

        if matches.empty:
            # Relax budget filter if user budget per night was too tight
            matches = df[
                (df["city_clean"].isin(aliases)) &
                (df["rating_num"] >= max(2.5, min_rating - 1.0))
            ]

        if matches.empty:
            # Fallback to any matching city alias
            matches = df[df["city_clean"].isin(aliases)]

        if matches.empty:
            return []

        matches = matches.sort_values(by="rating_num", ascending=False)
        return matches.head(limit)[["hotel_id", "hotel_name", "city", "rating", "cost", "facilities"]].to_dict(orient="records")

    # =========================================================================
    # 3. WEATHER AGENT QUERY (Matches n8n Weather Agent logic)
    # =========================================================================
    def get_weather(self, destination: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves weather records for the destination.
        Filter: row.destination.toLowerCase() === destination.toLowerCase()
        Returns destination, temperature, rainfall, humidity.
        """
        dest_clean = str(destination).strip().lower()
        aliases = get_city_aliases(destination)

        # Try Supabase REST if configured
        if settings.has_supabase:
            try:
                headers = {
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json"
                }
                query_url = f"{self.url}/rest/v1/Weather?destination=ilike.{dest_clean}&select=*&limit={limit}"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(query_url, headers=headers)
                    if resp.status_code == 200:
                        rows = resp.json()
                        if rows:
                            return rows
            except Exception as e:
                logger.warning(f"Supabase Weather query error: {e}. Falling back to local data.")

        # Local Data Engine fallback
        if self.weather_df.empty:
            return []

        matches = self.weather_df[
            self.weather_df["destination"].astype(str).str.strip().str.lower().isin(aliases)
        ].copy()

        if matches.empty:
            matches = self.weather_df[
                self.weather_df["destination"].astype(str).str.strip().str.lower().str.contains(dest_clean, regex=False)
            ].copy()

        if matches.empty:
            # Return realistic default weather if destination not in dataset
            return [{
                "destination": destination.title(),
                "season": "Pleasant",
                "temperature": 27.5,
                "rainfall": 0.0,
                "humidity": 60.0
            }]

        return matches.head(limit)[["destination", "season", "temperature", "rainfall", "humidity"]].to_dict(orient="records")

    # =========================================================================
    # 4. ATTRACTION AGENT QUERY (Matches n8n Attraction Agent logic)
    # =========================================================================
    def get_attractions(self, destination: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves top attractions for destination.
        Filter: attraction.city.toLowerCase() === destination.toLowerCase()
        Returns attraction_name, entry_fee, city, timings, category.
        """
        dest_clean = str(destination).strip().lower()
        aliases = get_city_aliases(destination)

        # Try Supabase REST if configured
        if settings.has_supabase:
            try:
                headers = {
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json"
                }
                query_url = f"{self.url}/rest/v1/Attractions?city=ilike.{dest_clean}&select=*&limit={limit}"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(query_url, headers=headers)
                    if resp.status_code == 200:
                        rows = resp.json()
                        if rows:
                            return rows
            except Exception as e:
                logger.warning(f"Supabase Attractions query error: {e}. Falling back to local data.")

        # Local Data Engine fallback
        if self.attractions_df.empty:
            return []

        matches = self.attractions_df[
            self.attractions_df["city"].astype(str).str.strip().str.lower().isin(aliases)
        ].copy()

        if matches.empty:
            matches = self.attractions_df[
                self.attractions_df["city"].astype(str).str.strip().str.lower().str.contains(dest_clean, regex=False)
            ].copy()

        if matches.empty:
            return [
                {
                    "attraction_name": f"{destination.title()} City Heritage Walk",
                    "city": destination.title(),
                    "entry_fee": 50,
                    "timings": "09:00 AM - 05:00 PM",
                    "category": "Heritage"
                },
                {
                    "attraction_name": f"{destination.title()} Scenic Viewpoint",
                    "city": destination.title(),
                    "entry_fee": 0,
                    "timings": "06:00 AM - 07:00 PM",
                    "category": "Nature"
                }
            ]

        return matches.head(limit)[["attraction_name", "city", "entry_fee", "timings", "category"]].to_dict(orient="records")

    # =========================================================================
    # 5. BUDGET AGENT CALCULATION (Matches n8n Budget Agent logic)
    # =========================================================================
    def calculate_budget(
        self,
        flight_cost: float,
        hotel_cost: float,
        food_cost: float,
        taxi_cost: float,
        activities: float,
        target_budget: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Total Budget = Flight Cost + Hotel Cost + Food Cost + Taxi Cost + Activities Cost.
        """
        total = float(flight_cost) + float(hotel_cost) + float(food_cost) + float(taxi_cost) + float(activities)
        
        result = {
            "flight_cost": float(flight_cost),
            "hotel_cost": float(hotel_cost),
            "food_cost": float(food_cost),
            "taxi_cost": float(taxi_cost),
            "activities": float(activities),
            "total_budget": total
        }

        if target_budget:
            diff = float(target_budget) - total
            result["target_budget"] = float(target_budget)
            result["is_within_budget"] = diff >= 0
            result["remaining_balance"] = diff
            if diff < 0:
                result["savings_suggestion"] = f"Budget is exceeded by ₹{abs(diff):,.2f}. Choose budget lodging or travel off-peak."
            else:
                result["savings_suggestion"] = f"Budget looks great! You have a surplus of ₹{diff:,.2f}."

        return result

    # =========================================================================
    # CONVERSATION HISTORY & USER MEMORY (In-memory + Supabase)
    # =========================================================================
    _in_memory_history: List[Dict[str, Any]] = []
    _in_memory_users: Dict[str, Dict[str, Any]] = {}

    def log_conversation(self, entry: ConversationEntry):
        """Persist conversation entry in Supabase or in-memory store."""
        data = clean_for_json(entry.model_dump())
        self._in_memory_history.insert(0, data)
        if len(self._in_memory_history) > 50:
            self._in_memory_history.pop()

        if settings.has_supabase:
            try:
                headers = {
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal"
                }
                payload = clean_for_json({
                    "user_id": entry.user_id,
                    "session_id": entry.session_id,
                    "question": entry.question,
                    "response": entry.response,
                    "parsed_intent": entry.parsed_intent,
                    "planner_data": entry.planner_data
                })
                query_url = f"{self.url}/rest/v1/Conversation_History"
                with httpx.Client(timeout=10.0) as client:
                    client.post(query_url, headers=headers, json=payload)
            except Exception as e:
                logger.warning(f"Supabase conversation logging failed: {e}")

    def get_conversation_history(self, user_id: str = "default_user", limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve recent conversation logs."""
        if settings.has_supabase:
            try:
                headers = {
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json"
                }
                query_url = f"{self.url}/rest/v1/Conversation_History?user_id=eq.{user_id}&order=timestamp.desc&limit={limit}&select=*"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(query_url, headers=headers)
                    if resp.status_code == 200:
                        rows = resp.json()
                        if rows:
                            return clean_for_json(rows)
            except Exception as e:
                logger.warning(f"Supabase history query failed: {e}")

        # In-memory fallback
        return clean_for_json([h for h in self._in_memory_history if h.get("user_id") == user_id][:limit])

    def get_user_memory(self, user_id: str = "default_user") -> UserMemory:
        """Retrieve stored user preferences."""
        if settings.has_supabase:
            try:
                headers = {
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json"
                }
                query_url = f"{self.url}/rest/v1/Users?user_id=eq.{user_id}&select=*"
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(query_url, headers=headers)
                    if resp.status_code == 200:
                        rows = resp.json()
                        if rows:
                            return UserMemory(**rows[0])
            except Exception as e:
                logger.warning(f"Supabase memory query failed: {e}")

        mem = self._in_memory_users.get(user_id)
        if mem:
            return UserMemory(**mem)
        return UserMemory(user_id=user_id, name="Traveler", hotel_rating_preference=4.0, travel_preferences=["leisure", "sightseeing"])

    def update_user_memory(self, memory: UserMemory):
        """Update or insert user preferences."""
        data = memory.model_dump()
        self._in_memory_users[memory.user_id] = data

        if settings.has_supabase:
            try:
                headers = {
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates"
                }
                query_url = f"{self.url}/rest/v1/Users"
                with httpx.Client(timeout=10.0) as client:
                    client.post(query_url, headers=headers, json=data)
            except Exception as e:
                logger.warning(f"Supabase user memory update failed: {e}")


supabase_service = SupabaseDataService()
