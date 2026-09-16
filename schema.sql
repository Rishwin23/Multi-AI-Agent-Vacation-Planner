-- ==============================================================================
-- Multi-Agent AI Vacation Planner - Supabase Database Schema Migration
-- ==============================================================================
-- Run this script in your Supabase SQL Editor (Dashboard -> SQL Editor -> New query)

-- 1. Enable pgvector Extension for RAG Vector Search
CREATE EXTENSION IF NOT EXISTS vector;

-- ==============================================================================
-- 2. CORE TRAVEL DATASET TABLES
-- ==============================================================================

-- Flights Table
CREATE TABLE IF NOT EXISTS public."Flights" (
    flight_id BIGINT PRIMARY KEY,
    source TEXT NOT NULL,
    destination TEXT NOT NULL,
    airline TEXT NOT NULL,
    "departure time" TEXT,
    departure_time TEXT,
    arrival_time TEXT,
    price NUMERIC NOT NULL,
    duration TEXT,
    duration_minutes INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_flights_destination ON public."Flights" (destination);
CREATE INDEX IF NOT EXISTS idx_flights_price ON public."Flights" (price);

-- Hotels Table
CREATE TABLE IF NOT EXISTS public."Hotels" (
    hotel_id BIGINT PRIMARY KEY,
    hotel_name TEXT NOT NULL,
    city TEXT NOT NULL,
    rating NUMERIC NOT NULL,
    cost NUMERIC NOT NULL,
    facilities TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hotels_city ON public."Hotels" (city);
CREATE INDEX IF NOT EXISTS idx_hotels_rating_cost ON public."Hotels" (rating DESC, cost ASC);

-- Weather Table
CREATE TABLE IF NOT EXISTS public."Weather" (
    id BIGSERIAL PRIMARY KEY,
    destination TEXT NOT NULL,
    season TEXT,
    temperature NUMERIC,
    rainfall NUMERIC,
    humidity NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weather_destination ON public."Weather" (destination);

-- Attractions Table
CREATE TABLE IF NOT EXISTS public."Attractions" (
    id BIGSERIAL PRIMARY KEY,
    attraction_name TEXT NOT NULL,
    city TEXT NOT NULL,
    entry_fee NUMERIC DEFAULT 0,
    timings TEXT,
    category TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_attractions_city ON public."Attractions" (city);

-- ==============================================================================
-- 3. USER MEMORY & PREFERENCES TABLE (Phase 8)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public."Users" (
    user_id TEXT PRIMARY KEY,
    name TEXT DEFAULT 'Traveler',
    preferred_airline TEXT,
    hotel_rating_preference NUMERIC DEFAULT 4.0,
    budget_preference NUMERIC,
    preferred_destinations TEXT[] DEFAULT '{}',
    travel_preferences TEXT[] DEFAULT '{"leisure", "sightseeing"}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Seed default user
INSERT INTO public."Users" (user_id, name, preferred_airline, hotel_rating_preference, budget_preference, travel_preferences)
VALUES ('default_user', 'Traveler', 'IndiGo', 4.0, 40000, '{"beach", "relaxation", "heritage"}')
ON CONFLICT (user_id) DO NOTHING;

-- ==============================================================================
-- 4. CONVERSATION HISTORY TABLE (Phase 7)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public."Conversation_History" (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES public."Users"(user_id) ON DELETE CASCADE,
    session_id TEXT,
    question TEXT NOT NULL,
    response TEXT NOT NULL,
    parsed_intent JSONB,
    planner_data JSONB,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conv_history_user ON public."Conversation_History" (user_id, timestamp DESC);

-- Saved Trips Summary Table
CREATE TABLE IF NOT EXISTS public."Trips" (
    trip_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES public."Users"(user_id) ON DELETE CASCADE,
    destination TEXT NOT NULL,
    days INTEGER DEFAULT 5,
    budget NUMERIC,
    itinerary_text TEXT,
    flight_data JSONB,
    hotel_data JSONB,
    weather_data JSONB,
    attraction_data JSONB,
    budget_summary JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trips_user ON public."Trips" (user_id, created_at DESC);

-- ==============================================================================
-- 5. PGVECTOR RAG EMBEDDINGS TABLE & MATCH FUNCTION (Phase 9)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS public."Embeddings" (
    id BIGSERIAL PRIMARY KEY,
    document_name TEXT NOT NULL,
    category TEXT NOT NULL,
    destination TEXT,
    chunk_text TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(768),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_embeddings_destination ON public."Embeddings" (destination);

-- Cosine Similarity Search Function
CREATE OR REPLACE FUNCTION match_travel_documents (
  query_embedding vector(768),
  match_threshold float DEFAULT 0.3,
  match_count int DEFAULT 4,
  filter_destination text DEFAULT NULL
)
RETURNS TABLE (
  id bigint,
  document_name text,
  category text,
  destination text,
  chunk_text text,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.document_name,
    e.category,
    e.destination,
    e.chunk_text,
    e.metadata,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM public."Embeddings" e
  WHERE (filter_destination IS NULL OR e.destination ILIKE filter_destination)
    AND 1 - (e.embedding <=> query_embedding) > match_threshold
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
