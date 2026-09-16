"""
n8n Agent Orchestrator Service.
Coordinates the Planner Agent and the 5 specialized agents:
- Flight Agent
- Hotel Agent
- Weather Agent
- Attraction Agent
- Budget Agent

Supports:
1. Direct execution via n8n Webhook (if N8N_WEBHOOK_URL is configured).
2. Resilient local agent execution engine that faithfully executes the exact logic
   of the n8n workflows against Supabase / CSV datasets.
"""
import logging
from typing import Dict, Any, Optional
import httpx

from backend.config import settings
from backend.models import ParsedRequirements, PlannerResult
from backend.services.supabase_service import supabase_service

logger = logging.getLogger("vacation_planner.n8n")
logger.setLevel(logging.INFO)


class N8nPlannerService:
    def __init__(self):
        self.webhook_url = settings.N8N_WEBHOOK_URL

    def execute_planner(self, parsed_req: ParsedRequirements) -> PlannerResult:
        """
        Orchestrates specialized agents to build the complete travel context.
        Uses n8n webhook when N8N_WEBHOOK_URL is configured; falls back to local orchestrator.
        """
        if self.webhook_url and not self.webhook_url.startswith("http://placeholder"):
            logger.info(f"Orchestration path: n8n webhook (N8N_WEBHOOK_URL is set)")
            try:
                result = self._call_n8n_webhook(parsed_req)
                if result:
                    logger.info("Successfully executed Planner Agent via n8n webhook.")
                    return result
                logger.warning("n8n webhook returned no usable result. Falling back to local agent execution.")
            except Exception as e:
                logger.warning(f"n8n webhook execution failed: {e}. Falling back to local agent execution.")

        # Local Multi-Agent Execution Engine (fallback when N8N_WEBHOOK_URL is empty)
        logger.info("Orchestration path: local agent execution engine")
        return self._execute_local_planner(parsed_req)

    def _call_n8n_webhook(self, parsed_req: ParsedRequirements) -> Optional[PlannerResult]:
        """Dispatches travel requirements to n8n Planner Agent webhook."""
        payload = {
            "destination": parsed_req.destination,
            "budget": parsed_req.budget,
            "days": parsed_req.days,
            "sort_by": parsed_req.sort_by,
            "min_rating": parsed_req.min_rating,
            "origin": parsed_req.origin,
            "preferences": parsed_req.preferences
        }

        logger.info(f"Calling n8n Planner webhook for destination={parsed_req.destination}")

        with httpx.Client(timeout=120.0) as client:
            resp = client.post(self.webhook_url, json=payload)
            if resp.status_code == 200:
                data = resp.json()

                # n8n can return a list — take the first item
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]

                # Unwrap common n8n wrapper keys: json, output, result, data
                for wrapper_key in ("json", "output", "result", "data"):
                    if isinstance(data, dict) and wrapper_key in data and isinstance(data[wrapper_key], dict):
                        inner = data[wrapper_key]
                        # Only unwrap if the inner dict contains agent data keys
                        if any(k in inner for k in ("flights", "hotels", "weather", "attractions", "budget")):
                            data = inner
                            break

                logger.info(f"n8n webhook response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

                return PlannerResult(
                    destination=parsed_req.destination,
                    days=parsed_req.days,
                    flights=data.get("flights", []),
                    hotels=data.get("hotels", []),
                    weather=data.get("weather", []),
                    attractions=data.get("attractions", []),
                    budget=data.get("budget", {})
                )
            else:
                logger.error(f"n8n Webhook returned status {resp.status_code}: {resp.text[:200]}")
                return None

    def _execute_local_planner(self, parsed_req: ParsedRequirements) -> PlannerResult:
        """
        In-process orchestrator executing the exact 5 specialized agents.
        """
        dest = parsed_req.destination
        days = parsed_req.days
        target_budget = parsed_req.budget

        # -------------------------------------------------------------
        # Agent 1: Flight Agent (destination, sort_by -> Top 5)
        # -------------------------------------------------------------
        flights = supabase_service.get_flights(
            destination=dest,
            sort_by=parsed_req.sort_by,
            limit=5
        )

        # -------------------------------------------------------------
        # Agent 2: Hotel Agent (city, budget_per_night, min_rating -> Top 5)
        # -------------------------------------------------------------
        # Estimate max hotel cost per night: roughly 35-40% of budget / days
        max_hotel_per_night = max(1500.0, (target_budget * 0.40) / max(1, days))
        hotels = supabase_service.get_hotels(
            city=dest,
            budget=max_hotel_per_night,
            min_rating=parsed_req.min_rating,
            limit=5
        )

        # -------------------------------------------------------------
        # Agent 3: Weather Agent (destination -> Top 5)
        # -------------------------------------------------------------
        weather = supabase_service.get_weather(
            destination=dest,
            limit=5
        )

        # -------------------------------------------------------------
        # Agent 4: Attraction Agent (destination -> Top 5)
        # -------------------------------------------------------------
        attractions = supabase_service.get_attractions(
            destination=dest,
            limit=5
        )

        # -------------------------------------------------------------
        # Agent 5: Budget Agent (Aggregates Flight, Hotel, Food, Taxi, Activities)
        # -------------------------------------------------------------
        # 1. Flight cost (selected top flight * roundtrip/person)
        flight_unit_cost = float(flights[0].get("price", 4500)) if flights else 4500.0
        flight_cost = flight_unit_cost * 2  # roundtrip

        # 2. Hotel cost (selected top hotel * days)
        hotel_nightly_cost = float(hotels[0].get("cost", 2500)) if hotels else 2500.0
        hotel_cost = hotel_nightly_cost * max(1, days - 1)

        # 3. Food cost (estimated per-day food: ₹1,200 * days)
        food_cost = 1200.0 * days

        # 4. Local taxi / transit cost (estimated ₹600/day)
        taxi_cost = 600.0 * days

        # 5. Activities cost (sum of entry fees from selected attractions)
        activities_cost = sum(float(a.get("entry_fee", 0)) for a in attractions)
        if activities_cost == 0:
            activities_cost = 500.0

        budget_summary = supabase_service.calculate_budget(
            flight_cost=flight_cost,
            hotel_cost=hotel_cost,
            food_cost=food_cost,
            taxi_cost=taxi_cost,
            activities=activities_cost,
            target_budget=target_budget
        )

        logger.info(f"Local Planner Orchestration completed for {dest} ({days} days, Budget: ₹{target_budget:,.2f})")

        return PlannerResult(
            destination=dest,
            days=days,
            flights=flights,
            hotels=hotels,
            weather=weather,
            attractions=attractions,
            budget=budget_summary
        )


n8n_service = N8nPlannerService()
