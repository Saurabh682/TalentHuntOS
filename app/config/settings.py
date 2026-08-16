"""Configuration management for TalentHunt OS."""

import os
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config.constants import DEFAULT_HOST, DEFAULT_PORT

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = Path(os.environ.get("TALENTHUNT_DATA_DIR", BASE_DIR / "data")).resolve()


class Settings(BaseSettings):
    """Application settings schema."""

    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "TalentHunt OS"
    app_version: str = "0.1.0"
    debug: bool = True
    # SQLAlchemy statement logging floods the console; keep off unless debugging DB issues
    sql_echo: bool = False
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT

    @field_validator("host")
    @classmethod
    def require_loopback_host(cls, value: str) -> str:
        host = (value or "").strip().lower()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "TalentHunt OS contains private recruiter data and must bind to a loopback host"
            )
        return host

    @field_validator("port")
    @classmethod
    def require_canonical_port(cls, value: int) -> int:
        if value != DEFAULT_PORT:
            raise ValueError(f"TalentHunt OS must run on port {DEFAULT_PORT}")
        return value

    # Database
    db_path: Path = DATA_DIR / "talenthunt.db"

    # AI Keys
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Voice Keys
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""

    # Free TTS: edge (Microsoft neural, free) | browser (Web Speech) | elevenlabs (paid)
    tts_provider: str = "kokoro"
    tts_edge_voice: str = "en-US-JennyNeural"
    tts_kokoro_voice: str = "af_heart"

    # Local AI Server
    llama_server_host: str = "127.0.0.1"
    llama_server_port: int = 1234
    embedded_ai_port: int = 18081
    local_model_path: Path = DATA_DIR / "models" / "granite-4.1-3b-Q4_K_M.gguf"
    local_ai_mode: str = "standard"
    local_ai_autostart: bool = True

    # Feature Flags
    enable_local_ai: bool = True
    enable_voice: bool = True
    enable_auto_pilot: bool = False


settings = Settings()
