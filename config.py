"""
Configuration loader for Vacation Planner Backend.
Loads environment variables securely from .env.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root or backend directory
env_path = Path(__file__).resolve().parent.parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent / ".env"

load_dotenv(dotenv_path=env_path)


class Settings:
    # Gemini API Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    GEMINI_EMBEDDING_MODEL: str = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001").strip()

    # ElevenLabs API Configuration
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "").strip()
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL").strip()  # "Sarah" voice default

    # Supabase Database Configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "").strip()
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    # n8n Webhook Configuration
    N8N_WEBHOOK_URL: str = os.getenv("N8N_WEBHOOK_URL", "").strip()

    # Server Settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8000))
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def has_gemini_key(self) -> bool:
        return bool(self.GEMINI_API_KEY and not self.GEMINI_API_KEY.startswith("your_"))

    @property
    def has_elevenlabs_key(self) -> bool:
        return bool(self.ELEVENLABS_API_KEY and not self.ELEVENLABS_API_KEY.startswith("your_"))

    @property
    def has_supabase(self) -> bool:
        return bool(self.SUPABASE_URL and self.SUPABASE_KEY and not self.SUPABASE_URL.startswith("https://your-"))


settings = Settings()
