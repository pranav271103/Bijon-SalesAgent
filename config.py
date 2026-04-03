"""
Configuration module — loads environment variables and defines constants.
All secrets come from .env file, never hardcoded.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Discord ──────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_ADMIN_CHANNEL_ID = int(os.getenv("DISCORD_ADMIN_CHANNEL_ID", "0"))

# ── NVIDIA LLM API ──────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

# ── Supabase ─────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# ── Bot Settings ─────────────────────────────────────
BOT_PREFIX = "!"
MEMORY_WINDOW = 10          # Last N messages to include in LLM context
RESPONSE_TIMEOUT = 15       # Seconds before sending "thinking..." message
LARGE_ORDER_THRESHOLD = 50000  # USD equivalent — triggers escalation
LARGE_ORDER_QTY_THRESHOLD = 500  # Units — triggers escalation
FOLLOW_UP_HOURS = 48        # Hours of inactivity before follow-up
QUOTE_EXPIRY_DAYS = 30      # Quote validity period

# ── Region Configuration ─────────────────────────────
VALID_REGIONS = ["GCC", "India", "SEA"]

REGION_CURRENCIES = {
    "GCC": "AED",
    "India": "INR",
    "SEA": "SGD",
}

# ── Constraint Rejection Keywords ────────────────────
# If a use-case contains any of these words AND the product has
# an "above-waterline only" constraint, the quote is REJECTED.
SUBMERGED_KEYWORDS = [
    "submerged", "underwater", "submersible", "pool", "swimming pool",
    "fountain", "water tank", "below waterline", "immersed",
    "aquatic", "marine", "reservoir", "wet area",
]

INTERIOR_KEYWORDS = [
    "exterior", "outdoor", "outside", "rooftop", "facade",
    "terrace", "balcony", "weather-exposed",
]

EXTERIOR_KEYWORDS = [
    "interior", "indoor", "inside", "partition", "drywall",
    "ceiling", "false ceiling", "corridor",
]

# ── Custom Engineering Trigger Words ─────────────────
CUSTOM_ENGINEERING_KEYWORDS = [
    "custom", "bespoke", "non-standard", "special dimensions",
    "custom dimensions", "engineering drawing", "custom design",
    "tailor-made", "made to order", "special size",
]
