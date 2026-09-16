"""
Pydantic data models and schemas for the Vacation Planner.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class UserTravelRequest(BaseModel):
    """Incoming user travel prompt from frontend or voice."""
    query: str = Field(..., description="Natural language vacation request e.g. 'Plan a 5-day Goa trip under 40000'")
    user_id: Optional[str] = Field("default_user", description="Identifier for user personalization / memory")
    session_id: Optional[str] = Field(None, description="Conversation session ID")
    # Optional explicit overrides if user uses manual filters:
    explicit_destination: Optional[str] = None
    explicit_days: Optional[int] = None
    explicit_budget: Optional[float] = None
    explicit_origin: Optional[str] = None
    sort_by: Optional[str] = None
    min_rating: Optional[float] = None


class ParsedRequirements(BaseModel):
    """Structured requirements parsed by Gemini LLM (TASK A)."""
    destination: str = Field(..., description="Destination city/region (e.g. Goa, Banglore, Delhi)")
    days: int = Field(5, description="Duration of trip in days")
    budget: float = Field(..., description="Total target budget in INR")
    origin: Optional[str] = Field("Delhi", description="Departure city if mentioned, defaults to major hub")
    sort_by: str = Field("price", description="Sorting preference: 'price' or 'duration'")
    min_rating: float = Field(3.5, description="Minimum acceptable hotel rating (e.g. 3.0, 4.0)")
    preferences: List[str] = Field(default_factory=list, description="Extracted preferences e.g. 'beach', 'heritage'")
    travel_dates: Optional[str] = Field(None, description="Travel dates or season if mentioned")
    raw_query: Optional[str] = None


class FlightItem(BaseModel):
    flight_id: Optional[Any] = None
    source: Optional[str] = None
    destination: Optional[str] = None
    airline: Optional[str] = None
    departure_time: Optional[str] = Field(None, alias="departure time")
    arrival_time: Optional[str] = None
    price: Optional[float] = None
    duration: Optional[str] = None
    duration_minutes: Optional[int] = None

    model_config = ConfigDict(populate_by_name=True)


class HotelItem(BaseModel):
    hotel_id: Optional[Any] = None
    hotel_name: Optional[str] = None
    city: Optional[str] = None
    rating: Optional[float] = None
    cost: Optional[float] = None
    facilities: Optional[str] = None


class WeatherItem(BaseModel):
    destination: Optional[str] = None
    season: Optional[str] = None
    temperature: Optional[float] = None
    rainfall: Optional[float] = None
    humidity: Optional[float] = None
    suggested_clothing: Optional[str] = None


class AttractionItem(BaseModel):
    attraction_name: Optional[str] = None
    city: Optional[str] = None
    destination: Optional[str] = None
    entry_fee: Optional[float] = 0.0
    timings: Optional[str] = None
    category: Optional[str] = None


class BudgetSummary(BaseModel):
    flight_cost: float = 0.0
    hotel_cost: float = 0.0
    food_cost: float = 0.0
    taxi_cost: float = 0.0
    activities: float = 0.0
    total_budget: float = 0.0
    target_budget: Optional[float] = None
    is_within_budget: Optional[bool] = None
    remaining_balance: Optional[float] = None
    savings_suggestion: Optional[str] = None


class PlannerResult(BaseModel):
    """Aggregated output from all 5 specialized agents."""
    flights: List[Dict[str, Any]] = Field(default_factory=list)
    hotels: List[Dict[str, Any]] = Field(default_factory=list)
    weather: List[Dict[str, Any]] = Field(default_factory=list)
    attractions: List[Dict[str, Any]] = Field(default_factory=list)
    budget: Dict[str, Any] = Field(default_factory=dict)
    destination: Optional[str] = None
    days: Optional[int] = 5


class CriticCheck(BaseModel):
    aspect: str
    passed: bool
    details: str


class CriticResult(BaseModel):
    """Evaluation result from Reflection / Critic Agent (Phase 10)."""
    is_valid: bool = True
    score: int = Field(100, description="Quality score 0-100")
    checks: List[CriticCheck] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


class VacationPlanResponse(BaseModel):
    """Complete end-to-end itinerary response returned to frontend."""
    success: bool = True
    user_id: str
    session_id: str
    query: str
    parsed_requirements: ParsedRequirements
    planner_result: PlannerResult
    itinerary_markdown: str
    critic_result: Optional[CriticResult] = None
    audio_base64: Optional[str] = None
    audio_url: Optional[str] = None
    execution_time_seconds: Optional[float] = None
    error: Optional[str] = None


class UserMemory(BaseModel):
    """User profile and long-term travel memory (Phase 8)."""
    user_id: str
    name: Optional[str] = "Traveler"
    preferred_airline: Optional[str] = None
    hotel_rating_preference: Optional[float] = 4.0
    budget_preference: Optional[float] = None
    preferred_destinations: List[str] = Field(default_factory=list)
    travel_preferences: List[str] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConversationEntry(BaseModel):
    """Conversation history log record (Phase 7)."""
    id: Optional[Any] = None
    user_id: str
    session_id: Optional[str] = None
    question: str
    response: str
    parsed_intent: Optional[Dict[str, Any]] = None
    planner_data: Optional[Dict[str, Any]] = None
    timestamp: Optional[str] = None


class RagQueryRequest(BaseModel):
    query: str
    destination: Optional[str] = None
    top_k: int = 4


class RagDocumentChunk(BaseModel):
    id: Optional[Any] = None
    document_name: str
    category: str
    chunk_text: str
    similarity: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RagQueryResponse(BaseModel):
    query: str
    answer: str
    retrieved_chunks: List[RagDocumentChunk] = Field(default_factory=list)
