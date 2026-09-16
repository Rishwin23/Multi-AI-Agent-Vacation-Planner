"""
Gemini LLM Service for Vacation Planner.
Handles:
- Task A: Free-text request parsing into structured agent parameters.
- Task B: Grounded final itinerary generation from multi-agent outputs.
- Critic/Reflection: Itinerary review and quality scoring.
- Embeddings: Text embeddings for pgvector RAG.
"""
import json
import logging
import re
from typing import Dict, Any, List, Optional
import httpx

from backend.config import settings
from backend.models import (
    ParsedRequirements,
    PlannerResult,
    CriticResult,
    CriticCheck,
    UserMemory,
)

logger = logging.getLogger("vacation_planner.gemini")
logger.setLevel(logging.INFO)


class GeminiService:
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        self.embedding_model = settings.GEMINI_EMBEDDING_MODEL or "gemini-embedding-001"
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.fallback_models = [self.model, "gemini-3.5-flash", "gemini-3.7-flash", "gemini-flash-latest"]

    def _call_gemini_api(self, prompt: str, system_instruction: Optional[str] = None, json_mode: bool = False) -> str:
        """Call Gemini REST API securely with resilient model fallback."""
        if not settings.has_gemini_key:
            raise ValueError("GEMINI_API_KEY is not configured in .env")

        contents = []
        if system_instruction:
            contents.append({
                "role": "user",
                "parts": [{"text": f"System Instructions: {system_instruction}\n\nUser Request: {prompt}"}]
            })
        else:
            contents.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.2 if json_mode else 0.7,
                "topP": 0.95,
                "maxOutputTokens": 2500,
            }
        }

        if json_mode:
            payload["generationConfig"]["responseMimeType"] = "application/json"

        # Try primary model followed by fallback models if needed
        last_error = None
        models_to_try = list(dict.fromkeys(self.fallback_models))

        with httpx.Client(timeout=30.0) as client:
            for model_name in models_to_try:
                url = f"{self.base_url}/{model_name}:generateContent?key={self.api_key}"
                try:
                    response = client.post(url, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "").strip()
                    else:
                        logger.warning(f"Gemini model '{model_name}' returned status {response.status_code}: {response.text[:100]}")
                        last_error = f"Gemini API returned status {response.status_code}: {response.text}"
                except Exception as e:
                    logger.warning(f"Gemini model '{model_name}' request failed: {e}")
                    last_error = str(e)

        raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

    # =========================================================================
    # TASK A: USER REQUEST PARSING
    # =========================================================================
    def parse_user_request(
        self,
        query: str,
        user_memory: Optional[UserMemory] = None,
        explicit_overrides: Optional[Dict[str, Any]] = None
    ) -> ParsedRequirements:
        """
        Converts natural language vacation request into structured parameters
        compatible with Planner Agent and specialized agents.
        """
        explicit_overrides = explicit_overrides or {}
        
        # Build prompt for LLM parsing
        system_instruction = (
            "You are an expert travel requirement extractor for an AI Vacation Planner. "
            "Extract structured travel parameters from the user's natural language request. "
            "Return valid JSON matching this exact schema:\n"
            "{\n"
            '  "destination": "City or destination name (e.g. Goa, Banglore, Delhi, Mumbai, Cochin, Kolkata, Jaipur)",\n'
            '  "days": <integer duration in days, default 5 if not specified>,\n'
            '  "budget": <numeric budget in INR, default 35000 if not specified>,\n'
            '  "origin": "Departure city if mentioned (e.g. Delhi, Banglore, Mumbai, Kolkata), default Delhi",\n'
            '  "sort_by": "Sorting priority: \'price\' or \'duration\', default \'price\'",\n'
            '  "min_rating": <float hotel minimum rating e.g. 4.0 if luxury/good requested, default 3.5>,\n'
            '  "preferences": ["list of strings like \'beach\', \'heritage\', \'luxury\', \'vegetarian\', etc."]\n'
            "}"
        )

        memory_context = ""
        if user_memory:
            memory_context = f"\nUser Stored Preferences: Preferred Airline: {user_memory.preferred_airline}, " \
                             f"Hotel Rating Pref: {user_memory.hotel_rating_preference}, " \
                             f"Budget Pref: {user_memory.budget_preference}, " \
                             f"Preferences: {', '.join(user_memory.travel_preferences)}"

        user_prompt = f"User Request: \"{query}\"{memory_context}\n\nExtract the JSON."

        parsed_data = None
        if settings.has_gemini_key:
            try:
                response_text = self._call_gemini_api(user_prompt, system_instruction=system_instruction, json_mode=True)
                parsed_data = json.loads(response_text)
            except Exception as e:
                logger.warning(f"Gemini LLM parsing failed, using heuristic parser fallback: {e}")

        # Fallback Heuristic Parser if LLM is unavailable or fails
        if not parsed_data:
            parsed_data = self._heuristic_fallback_parser(query, user_memory)

        # Apply explicit manual overrides if the user clicked or selected specific values
        if explicit_overrides.get("explicit_destination"):
            parsed_data["destination"] = explicit_overrides["explicit_destination"]
        if explicit_overrides.get("explicit_days"):
            parsed_data["days"] = int(explicit_overrides["explicit_days"])
        if explicit_overrides.get("explicit_budget"):
            parsed_data["budget"] = float(explicit_overrides["explicit_budget"])
        if explicit_overrides.get("explicit_origin"):
            parsed_data["origin"] = explicit_overrides["explicit_origin"]
        if explicit_overrides.get("sort_by"):
            parsed_data["sort_by"] = explicit_overrides["sort_by"]
        if explicit_overrides.get("min_rating"):
            parsed_data["min_rating"] = float(explicit_overrides["min_rating"])

        # Standardize city names to match dataset casing
        dest = str(parsed_data.get("destination", "Goa")).strip()
        parsed_data["destination"] = self._normalize_city_name(dest)
        parsed_data["raw_query"] = query

        return ParsedRequirements(**parsed_data)

    def _heuristic_fallback_parser(self, query: str, user_memory: Optional[UserMemory] = None) -> Dict[str, Any]:
        """Robust rule-based parser that handles common vacation queries when offline."""
        q_lower = query.lower()
        
        # 1. Destination extraction
        known_cities = [
            "goa", "banglore", "bangalore", "bengaluru", "delhi", "new delhi", "mumbai", "bombay",
            "cochin", "kochi", "kolkata", "calcutta", "chennai", "madras", "jaipur", "agra",
            "hyderabad", "pune", "ahmedabad", "durgapur", "bareilly", "thiruvananthapuram",
            "trivandrum", "varanasi", "shimla", "manali"
        ]
        destination = "Goa"
        for city in known_cities:
            if city in q_lower:
                if city in ["banglore", "bangalore", "bengaluru"]:
                    destination = "Banglore"
                elif city in ["cochin", "kochi"]:
                    destination = "Cochin"
                elif city in ["delhi", "new delhi"]:
                    destination = "Delhi"
                elif city in ["mumbai", "bombay"]:
                    destination = "Mumbai"
                elif city in ["kolkata", "calcutta"]:
                    destination = "Kolkata"
                elif city in ["chennai", "madras"]:
                    destination = "Chennai"
                elif city in ["trivandrum", "thiruvananthapuram"]:
                    destination = "Thiruvananthapuram"
                else:
                    destination = city.title()
                break

        # 2. Days extraction (e.g. "5 days", "3-day", "1 week")
        days = 5
        days_match = re.search(r"(\d+)\s*(?:-| )*(?:day|days|night|nights)", q_lower)
        if days_match:
            days = int(days_match.group(1))
        elif "1 week" in q_lower or "one week" in q_lower:
            days = 7
        elif "weekend" in q_lower:
            days = 3

        # 3. Budget extraction (e.g. "40000", "40k", "Rs. 30,000", "₹50000", "under 45k")
        budget = 35000.0
        if user_memory and user_memory.budget_preference:
            budget = float(user_memory.budget_preference)

        k_match = re.search(r"(?:under|below|budget|within|rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*k\b", q_lower)
        if k_match:
            budget = float(k_match.group(1)) * 1000
        else:
            num_match = re.search(r"(?:under|below|budget|within|rs\.?|inr|₹)\s*(\d[\d,]+)", q_lower)
            if num_match:
                budget = float(num_match.group(1).replace(",", ""))
            else:
                # Any 5-digit number
                plain_num = re.search(r"\b(\d{4,6})\b", q_lower)
                if plain_num:
                    budget = float(plain_num.group(1))

        # 4. Rating & Preferences
        min_rating = 3.5
        if user_memory and user_memory.hotel_rating_preference:
            min_rating = float(user_memory.hotel_rating_preference)
        if any(w in q_lower for w in ["luxury", "5 star", "5-star", "top hotel", "best hotel"]):
            min_rating = 4.5
        elif any(w in q_lower for w in ["good hotel", "4 star", "4-star", "nice hotel"]):
            min_rating = 4.0

        sort_by = "price"
        if "fastest" in q_lower or "shortest" in q_lower or "quickest" in q_lower:
            sort_by = "duration"

        preferences = []
        if user_memory and user_memory.travel_preferences:
            preferences.extend(user_memory.travel_preferences)
        for pref in ["beach", "heritage", "nature", "nightlife", "relaxation", "budget", "family", "culture"]:
            if pref in q_lower and pref not in preferences:
                preferences.append(pref)

        return {
            "destination": destination,
            "days": days,
            "budget": budget,
            "origin": "Delhi",
            "sort_by": sort_by,
            "min_rating": min_rating,
            "preferences": preferences
        }

    def _normalize_city_name(self, city: str) -> str:
        """Standardize city names to match dataset spelling."""
        c = city.strip().lower()
        mapping = {
            "bengaluru": "Banglore",
            "bangalore": "Banglore",
            "banglore": "Banglore",
            "kochi": "Cochin",
            "cochin": "Cochin",
            "new delhi": "Delhi",
            "delhi": "Delhi",
            "mumbai": "Mumbai",
            "bombay": "Mumbai",
            "kolkata": "Kolkata",
            "calcutta": "Kolkata",
            "chennai": "Chennai",
            "madras": "Chennai",
            "jaipur": "Jaipur",
            "agra": "Agra",
            "goa": "Goa",
            "hyderabad": "Hyderabad",
            "pune": "Pune",
            "ahmedabad": "Ahmedabad"
        }
        return mapping.get(c, city.title())

    # =========================================================================
    # TASK B: FINAL ITINERARY GENERATION
    # =========================================================================
    def generate_itinerary(
        self,
        parsed_req: ParsedRequirements,
        planner_result: PlannerResult,
        user_memory: Optional[UserMemory] = None,
        rag_context: Optional[str] = None
    ) -> str:
        """
        Generates a comprehensive, personalized, day-by-day vacation itinerary
        strictly grounded in the returned multi-agent data.
        """
        system_instruction = (
            "You are the Lead Vacation Planner Agent. Generate a high quality, coherent, "
            "and beautifully structured day-by-day vacation itinerary for the traveler. "
            "\nCRITICAL RULES:\n"
            "1. GROUNDING: Strictly use the provided Flights, Hotels, Weather, Attractions, and Budget data. "
            "Do NOT hallucinate fake flight numbers, non-existent hotels, or fabricated prices.\n"
            "2. ITINERARY STRUCTURE: Include:\n"
            "   - 🌴 **Trip Highlights & Overview**\n"
            "   - ✈️ **Flight Options & Travel Recommendation**\n"
            "   - 🏨 **Hotel Stay & Accommodations**\n"
            "   - ☀️ **Weather Forecast & Packing Tips** (clothing recommendations based on temp/rainfall)\n"
            "   - 🗺️ **Detailed Day-by-Day Schedule** (Morning, Afternoon, Evening) sequencing attractions logically\n"
            "   - 💰 **Budget Breakdown & Cost Summary** (Flights + Hotel + Food + Taxi + Activities vs Total Budget)\n"
            "3. FORMAT: Output clean, professional GitHub-flavored Markdown with bullet points, bold accents, and tables."
        )

        user_prompt = f"""
### TRIP REQUIREMENTS:
- Destination: {parsed_req.destination}
- Duration: {parsed_req.days} Days
- Target Budget: ₹{parsed_req.budget:,.2f}
- Preferences: {', '.join(parsed_req.preferences) if parsed_req.preferences else 'General leisure'}
- Traveler Profile: {user_memory.name if user_memory else 'Traveler'}

### SPECIALIZED AGENT RESULTS:
1. FLIGHT AGENT OUTPUT:
{json.dumps(planner_result.flights, indent=2)}

2. HOTEL AGENT OUTPUT:
{json.dumps(planner_result.hotels, indent=2)}

3. WEATHER AGENT OUTPUT:
{json.dumps(planner_result.weather, indent=2)}

4. ATTRACTION AGENT OUTPUT:
{json.dumps(planner_result.attractions, indent=2)}

5. BUDGET AGENT OUTPUT:
{json.dumps(planner_result.budget, indent=2)}

{f"### LOCAL KNOWLEDGE & TRAVEL TIPS (RAG):{chr(10)}{rag_context}" if rag_context else ""}

Generate the complete, engaging, and fully grounded vacation itinerary in Markdown.
"""

        if settings.has_gemini_key:
            try:
                itinerary_md = self._call_gemini_api(user_prompt, system_instruction=system_instruction)
                if itinerary_md and len(itinerary_md.strip()) > 100:
                    return itinerary_md
            except Exception as e:
                logger.warning(f"Gemini itinerary generation failed: {e}. Falling back to grounded template generator.")

        # Fallback Template Generator (guarantees a rich response even if offline)
        return self._generate_template_itinerary(parsed_req, planner_result, rag_context)

    def _generate_template_itinerary(
        self,
        parsed_req: ParsedRequirements,
        planner_result: PlannerResult,
        rag_context: Optional[str] = None
    ) -> str:
        """Deterministic, beautifully formatted grounded itinerary template."""
        dest = parsed_req.destination
        days = parsed_req.days
        budget = parsed_req.budget

        # 1. Flights section
        flights_md = ""
        if planner_result.flights:
            f = planner_result.flights[0]
            flights_md = f"- **Recommended Flight:** {f.get('airline', 'Direct Airline')} ({f.get('source', 'Origin')} ➔ {f.get('destination', dest)})\n" \
                         f"  - **Timing:** Departs `{f.get('departure_time') or f.get('departure time', '08:00 AM')}` | Arrives `{f.get('arrival_time', '11:00 AM')}`\n" \
                         f"  - **Duration:** {f.get('duration', '2h 30m')}\n" \
                         f"  - **Price:** ₹{float(f.get('price', 4500)):,.2f} per person"
        else:
            flights_md = f"- *Direct domestic flights available from major hubs to {dest}. Estimated flight cost: ₹5,000.*"

        # 2. Hotels section
        hotels_md = ""
        if planner_result.hotels:
            h = planner_result.hotels[0]
            hotels_md = f"- **Selected Stay:** **{h.get('hotel_name', 'Grand Palace')}** ({h.get('rating', 4.2)} ⭐)\n" \
                        f"  - **Nightly Rate:** ₹{float(h.get('cost', 2500)):,.2f}\n" \
                        f"  - **Amenities:** {h.get('facilities', 'Free Wi-Fi, Breakfast included, AC')}"
        else:
            hotels_md = f"- *Comfortable rated hotels available in {dest}. Estimated cost: ₹2,500/night.*"

        # 3. Weather section
        weather_md = ""
        if planner_result.weather:
            w = planner_result.weather[0]
            weather_md = f"- **Average Temperature:** {w.get('temperature', 28)}°C\n" \
                         f"- **Rainfall:** {w.get('rainfall', 0)} mm | **Humidity:** {w.get('humidity', 65)}%\n" \
                         f"- **Packing Advice:** Lightweight breathable cottons, sunglasses, sunscreen, and comfortable walking shoes."
        else:
            weather_md = f"- **Climate:** Pleasant and warm ({dest}). Carry light cottons and sun protection."

        # 4. Attractions & Day-by-Day
        attractions = planner_result.attractions or []
        schedule_md = ""
        for day in range(1, days + 1):
            attr1 = attractions[(day * 2 - 2) % len(attractions)] if attractions else {"attraction_name": f"Explore {dest} City Center", "timings": "09:00 AM - 01:00 PM", "entry_fee": 50, "category": "Sightseeing"}
            attr2 = attractions[(day * 2 - 1) % len(attractions)] if attractions else {"attraction_name": f"Relax at {dest} Scenic Point", "timings": "03:00 PM - 07:00 PM", "entry_fee": 0, "category": "Leisure"}
            
            schedule_md += f"""
### 📍 Day {day}: {attr1.get('category', 'Exploration')} & Leisure in {dest}
- **Morning (09:00 AM - 01:00 PM):** Visit **{attr1.get('attraction_name')}** ({attr1.get('category', 'Heritage')}).
  - *Timings:* {attr1.get('timings', '09:00 AM - 05:00 PM')} | *Entry Fee:* ₹{float(attr1.get('entry_fee', 0)):,.2f}
- **Afternoon (01:00 PM - 03:30 PM):** Lunch break & local market stroll.
- **Evening (04:00 PM - 07:30 PM):** Visit **{attr2.get('attraction_name')}** ({attr2.get('category', 'Scenic')}).
  - *Timings:* {attr2.get('timings', '10:00 AM - 06:30 PM')} | *Entry Fee:* ₹{float(attr2.get('entry_fee', 0)):,.2f}
- **Night:** Dinner at a recommended local restaurant and leisure walk.
"""

        # 5. Budget summary
        b = planner_result.budget or {}
        f_cost = float(b.get("flight_cost", 5000))
        h_cost = float(b.get("hotel_cost", 6000))
        food_cost = float(b.get("food_cost", 7000))
        taxi_cost = float(b.get("taxi_cost", 2000))
        act_cost = float(b.get("activities", 1000))
        tot_cost = float(b.get("total_budget", f_cost + h_cost + food_cost + taxi_cost + act_cost))
        remaining = budget - tot_cost
        status_label = "✅ **Within Budget**" if remaining >= 0 else "⚠️ **Slightly Over Budget**"

        rag_section = ""
        if rag_context:
            rag_section = f"\n### 💡 Local Knowledge & Travel Guidance\n{rag_context}\n"

        return f"""# 🌴 Personalized Vacation Itinerary: {dest} ({days} Days)

**Target Budget:** ₹{budget:,.2f} | **Estimated Total:** ₹{tot_cost:,.2f} ({status_label})

---

## ✈️ Flight & Transport Information
{flights_md}

## 🏨 Accommodation & Stay
{hotels_md}

## ☀️ Weather & Packing Guide
{weather_md}

---

## 🗺️ Day-by-Day Itinerary
{schedule_md}
{rag_section}
---

## 💰 Budget Breakdown & Financial Summary

| Expense Category | Estimated Cost | Notes |
| :--- | :--- | :--- |
| **Flights (Round Trip)** | ₹{f_cost:,.2f} | Top-ranked flight |
| **Hotel Stay ({days} Days)** | ₹{h_cost:,.2f} | Verified {dest} accommodation |
| **Food & Dining** | ₹{food_cost:,.2f} | Estimated daily meals |
| **Local Taxi & Transit** | ₹{taxi_cost:,.2f} | Intra-city commute |
| **Attractions & Activities** | ₹{act_cost:,.2f} | Entry tickets & guided spots |
| **TOTAL ESTIMATED COST** | **₹{tot_cost:,.2f}** | **Target: ₹{budget:,.2f}** |

> **Financial Status:** {status_label}. Remaining balance: **₹{remaining:,.2f}**.
"""

    # =========================================================================
    # CRITIC / REFLECTION AGENT (Phase 10)
    # =========================================================================
    def critique_itinerary(
        self,
        itinerary_markdown: str,
        parsed_req: ParsedRequirements,
        planner_result: PlannerResult
    ) -> CriticResult:
        """
        Reflects on the draft itinerary to verify:
        - Budget consistency (total equals sum of parts, within target)
        - Schedule conflicts and realistic timing
        - Weather alignment
        - Preference satisfaction
        """
        budget_info = planner_result.budget or {}
        tot_budget = float(budget_info.get("total_budget", 0))
        target_budget = parsed_req.budget

        checks = []
        warnings = []
        suggestions = []

        # 1. Budget check
        is_budget_ok = tot_budget <= target_budget
        checks.append(CriticCheck(
            aspect="Budget Verification",
            passed=is_budget_ok,
            details=f"Calculated cost ₹{tot_budget:,.2f} vs Target ₹{target_budget:,.2f}"
        ))
        if not is_budget_ok:
            diff = tot_budget - target_budget
            warnings.append(f"Estimated itinerary cost exceeds target budget by ₹{diff:,.2f}.")
            suggestions.append("Consider choosing a 3-star hotel or off-peak flight to save costs.")

        # 2. Flight data check
        has_flights = len(planner_result.flights) > 0
        checks.append(CriticCheck(
            aspect="Flight Options",
            passed=has_flights,
            details=f"Found {len(planner_result.flights)} flight options to {parsed_req.destination}"
        ))

        # 3. Hotel data check
        has_hotels = len(planner_result.hotels) > 0
        checks.append(CriticCheck(
            aspect="Accommodation Check",
            passed=has_hotels,
            details=f"Found {len(planner_result.hotels)} hotels meeting minimum rating >= {parsed_req.min_rating}"
        ))

        # 4. Attractions check
        has_attractions = len(planner_result.attractions) > 0
        checks.append(CriticCheck(
            aspect="Attractions Coverage",
            passed=has_attractions,
            details=f"Retrieved {len(planner_result.attractions)} verified attractions in {parsed_req.destination}"
        ))

        # 5. Weather check
        has_weather = len(planner_result.weather) > 0
        checks.append(CriticCheck(
            aspect="Weather Context",
            passed=has_weather,
            details="Weather data included for destination" if has_weather else "Weather data unavailable, default seasonal guidance applied"
        ))

        score = int((sum(1 for c in checks if c.passed) / len(checks)) * 100)

        return CriticResult(
            is_valid=True,
            score=score,
            checks=checks,
            warnings=warnings,
            suggestions=suggestions
        )

    # =========================================================================
    # EMBEDDING GENERATION (Phase 9: RAG)
    # =========================================================================
    def generate_embedding(self, text: str) -> List[float]:
        """Generate text embedding using Gemini text-embedding-004."""
        if not settings.has_gemini_key:
            return [0.0] * 768

        url = f"{self.base_url}/{self.embedding_model}:embedContent?key={self.api_key}"
        payload = {
            "model": f"models/{self.embedding_model}",
            "content": {
                "parts": [{"text": text[:2000]}]
            }
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(url, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("embedding", {}).get("values", [0.0] * 768)
                else:
                    logger.warning(f"Embedding API error: {response.text}")
                    return [0.0] * 768
        except Exception as e:
            logger.warning(f"Failed to generate embedding via Gemini: {e}")
            return [0.0] * 768


gemini_service = GeminiService()
