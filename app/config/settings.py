"""Configuration management for TalentHunt OS."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"

class Settings(BaseSettings):
    """Application settings schema."""
    
    model_config = SettingsConfigDict(env_file=".env")

    app_name: str = "TalentHunt OS"
    app_version: str = "0.1.0"
    debug: bool = True
    # SQLAlchemy statement logging floods the console; keep off unless debugging DB issues
    sql_echo: bool = False
    host: str = "127.0.0.1"
    port: int = 8080
    
    # Database
    db_path: Path = DATA_DIR / "talenthunt.db"
    
    # AI Keys
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    
    # Voice Keys
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""
    
    # Local AI Server
    llama_server_host: str = "127.0.0.1"
    llama_server_port: int = 1234
    local_model_path: Path = MODELS_DIR / "gemma-2-2b-it.Q4_K_M.gguf"
    
    # Feature Flags
    enable_local_ai: bool = True
    enable_voice: bool = True
    enable_auto_pilot: bool = False

settings = Settings()
