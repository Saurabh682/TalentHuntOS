"""App-wide constants for TalentHunt OS."""

APP_NAME = "TalentHunt OS"
APP_VERSION = "0.1.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
APP_URL = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/"

# Keep sourcing progress and cancellation bounded while supporting larger pool fills.
MAX_SOURCING_TARGET = 100

# Local AI Defaults
LLAMA_SERVER_PORT = 8081
DEFAULT_LOCAL_MODEL = "gemma-2-2b-it.Q4_K_M.gguf"

# Theme Palette — Modern Ocean (design pack)
COLOR_BG = "#071019"
COLOR_SURFACE = "#08121d"
COLOR_SURFACE_ELEVATED = "#0e1b28"
COLOR_BORDER = "#1b3040"
COLOR_TEXT = "#edf5f7"
COLOR_MUTED = "#8195a5"
COLOR_NAVY = "#071019"
COLOR_TEAL = "#19d3c5"
COLOR_GOLD = "#d8941e"
COLOR_EMERALD = "#45d6a0"
COLOR_DARK_GREEN = "#12382f"
COLOR_DANGER = "#ff4d52"
COLOR_SUCCESS = "#45d6a0"
COLOR_PRIMARY = "#10a99f"

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
