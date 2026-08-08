"""App-wide constants for TalentHunt OS."""

APP_NAME = "TalentHunt OS"
APP_VERSION = "0.1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080

# Local AI Defaults
LLAMA_SERVER_PORT = 8081
DEFAULT_LOCAL_MODEL = "gemma-2-2b-it.Q4_K_M.gguf"

# Theme Palette (Vibrant Emerald & Lime Gradient System)
COLOR_BG = "#06120a"
COLOR_SURFACE = "#0b1c11"
COLOR_SURFACE_ELEVATED = "#12291b"
COLOR_BORDER = "rgba(123, 225, 40, 0.22)"
COLOR_TEXT = "#f0faf2"
COLOR_MUTED = "#81a889"
COLOR_NAVY = "#06120a"
COLOR_TEAL = "#7be128"
COLOR_GOLD = "#9ef04d"
COLOR_EMERALD = "#1fb138"
COLOR_DARK_GREEN = "#074f20"
COLOR_DANGER = "#ff4d52"
COLOR_SUCCESS = "#7be128"

# Pipeline Stages
DEFAULT_PIPELINE_STAGES = [
    "Sourced",
    "Contacted",
    "Screening",
    "Interview",
    "Offer",
    "Hired",
    "Rejected",
]
