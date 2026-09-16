"""
ElevenLabs Text-to-Speech Service.
Converts vacation itinerary markdown text into natural synthesized speech audio.
Secrets are strictly managed server-side and never exposed to the frontend.
"""
import re
import logging
from typing import Optional
import httpx

from backend.config import settings

logger = logging.getLogger("vacation_planner.elevenlabs")
logger.setLevel(logging.INFO)


class ElevenLabsService:
    def __init__(self):
        self.api_key = settings.ELEVENLABS_API_KEY
        self.voice_id = settings.ELEVENLABS_VOICE_ID or "EXAVITQu4vr4xnSDxMaL"  # Default: Sarah
        self.base_url = "https://api.elevenlabs.io/v1/text-to-speech"

    def clean_text_for_speech(self, markdown_text: str, max_chars: int = 1500) -> str:
        """
        Strips markdown formatting, symbols, tables, and emojis to produce
        clean, fluent spoken English for text-to-speech synthesis.
        """
        text = markdown_text

        # Remove entire lines that look like markdown tables
        lines = []
        for line in text.split("\n"):
            line_str = line.strip()
            if line_str.startswith("|") or line_str.endswith("|") or "---" in line_str:
                continue
            lines.append(line)
        text = "\n".join(lines)

        # Remove remaining pipes
        text = text.replace("|", "")
        # Remove headers hashes
        text = re.sub(r"#+\s*", "", text)
        # Remove bold, italics, code formatting
        text = re.sub(r"[*_`~]", "", text)
        # Remove markdown links [text](url) -> text
        text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
        # Remove emojis and non-ascii symbols
        text = re.sub(r"[^\x00-\x7F]+", " ", text)
        # Clean extra whitespace
        text = re.sub(r"\n\s*\n", "\n", text)
        text = re.sub(r"[ \t]+", " ", text).strip()

        if len(text) > max_chars:
            text = text[:max_chars].rsplit(".", 1)[0] + "."

        return text

    def synthesize_speech(self, text: str, voice_id: Optional[str] = None) -> bytes:
        """
        Calls ElevenLabs TTS API to synthesize text into MP3 audio bytes.
        """
        if not settings.has_elevenlabs_key:
            raise ValueError("ELEVENLABS_API_KEY is not configured in .env")

        target_voice = voice_id or self.voice_id
        url = f"{self.base_url}/{target_voice}"

        cleaned_text = self.clean_text_for_speech(text)
        if not cleaned_text:
            cleaned_text = "Here is your personalized vacation itinerary."

        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }

        payload = {
            "text": cleaned_text,
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        logger.info(f"Calling ElevenLabs TTS for {len(cleaned_text)} characters using voice {target_voice}...")

        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                logger.error(f"ElevenLabs API error {response.status_code}: {response.text}")
                raise RuntimeError(f"ElevenLabs API returned {response.status_code}: {response.text}")
            
            return response.content


elevenlabs_service = ElevenLabsService()
