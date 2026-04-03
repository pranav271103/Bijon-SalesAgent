"""
Database layer — Supabase client + all DB operations.
Provides async-compatible wrapper around Supabase REST API.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger("sales_bot.database")


def get_supabase_client() -> Optional[Client]:
    """Create and return Supabase client. Returns None if not configured."""
    if not SUPABASE_URL or not SUPABASE_KEY or "YOUR_" in SUPABASE_URL:
        logger.warning("Supabase not configured — running in local-only mode")
        return None
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.error(f"Failed to create Supabase client: {e}")
        return None


# ── Global client (lazy init) ───────────────────────
_client: Optional[Client] = None


def _get_client() -> Optional[Client]:
    global _client
    if _client is None:
        _client = get_supabase_client()
    return _client


# ══════════════════════════════════════════════════════
# PRODUCT OPERATIONS
# ══════════════════════════════════════════════════════

def get_product(product_code: str) -> Optional[dict]:
    """Fetch a product by its code. Returns None if not found."""
    client = _get_client()
    if client is None:
        return _get_product_local(product_code)
    try:
        result = client.table("products").select("*").eq(
            "product_code", product_code.upper()
        ).eq("is_active", True).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"DB error fetching product {product_code}: {e}")
        return _get_product_local(product_code)


def get_all_products() -> list:
    """Fetch all active products."""
    client = _get_client()
    if client is None:
        return list(LOCAL_PRODUCTS.values())
    try:
        result = client.table("products").select("*").eq("is_active", True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"DB error fetching products: {e}")
        return list(LOCAL_PRODUCTS.values())


def search_products_by_category(category: str) -> list:
    """Search products by category (floor, wall, roof)."""
    client = _get_client()
    if client is None:
        return [p for p in LOCAL_PRODUCTS.values() if p["category"] == category.lower()]
    try:
        result = client.table("products").select("*").eq(
            "category", category.lower()
        ).eq("is_active", True).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"DB error searching products: {e}")
        return [p for p in LOCAL_PRODUCTS.values() if p["category"] == category.lower()]


# ══════════════════════════════════════════════════════
# CONVERSATION OPERATIONS
# ══════════════════════════════════════════════════════

def save_conversation(user_id: str, username: str, message: str,
                      response: str, intent_parsed: dict = None) -> bool:
    """Store a conversation turn in the database."""
    client = _get_client()
    record = {
        "user_id": str(user_id),
        "username": username,
        "message": message,
        "response": response,
        "intent_parsed": json.dumps(intent_parsed) if intent_parsed else None,
    }
    if client is None:
        _local_conversations.append({**record, "created_at": datetime.now(timezone.utc).isoformat()})
        logger.info(f"Conversation saved locally for user {user_id}")
        return True
    try:
        client.table("conversations").insert(record).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save conversation: {e}")
        _local_conversations.append({**record, "created_at": datetime.now(timezone.utc).isoformat()})
        return False


def get_recent_conversations(user_id: str, limit: int = 10) -> list:
    """Fetch the last N conversations for a user (most recent first)."""
    client = _get_client()
    if client is None:
        user_convos = [c for c in _local_conversations if c["user_id"] == str(user_id)]
        return user_convos[-limit:][::-1]
    try:
        result = client.table("conversations").select("*").eq(
            "user_id", str(user_id)
        ).order("created_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to fetch conversations: {e}")
        return []


# ══════════════════════════════════════════════════════
# CUSTOMER CARD OPERATIONS
# ══════════════════════════════════════════════════════

def get_customer_card(discord_user_id: str) -> Optional[dict]:
    """Get or create a customer card for a Discord user."""
    client = _get_client()
    if client is None:
        return _local_customer_cards.get(str(discord_user_id))
    try:
        result = client.table("customer_cards").select("*").eq(
            "discord_user_id", str(discord_user_id)
        ).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"Failed to fetch customer card: {e}")
        return None


def upsert_customer_card(discord_user_id: str, name: str = None,
                         region: str = None, notes: str = None,
                         company: str = None) -> bool:
    """Create or update a customer card."""
    client = _get_client()
    record = {"discord_user_id": str(discord_user_id)}
    if name:
        record["name"] = name
    if region:
        record["region"] = region
    if notes:
        record["notes"] = notes
    if company:
        record["company"] = company
    record["last_interaction"] = datetime.now(timezone.utc).isoformat()

    if client is None:
        existing = _local_customer_cards.get(str(discord_user_id), {})
        existing.update(record)
        _local_customer_cards[str(discord_user_id)] = existing
        return True
    try:
        client.table("customer_cards").upsert(
            record, on_conflict="discord_user_id"
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to upsert customer card: {e}")
        return False


# ══════════════════════════════════════════════════════
# QUOTE OPERATIONS
# ══════════════════════════════════════════════════════

def save_quote(user_id: str, product_code: str, product_name: str,
               region: str, quantity: int, base_price: float,
               final_price: float, currency: str, breakdown: dict) -> Optional[str]:
    """Save a generated quote. Returns quote ID or None on failure."""
    client = _get_client()
    record = {
        "user_id": str(user_id),
        "product_code": product_code,
        "product_name": product_name,
        "region": region,
        "quantity": quantity,
        "base_price": base_price,
        "final_price": final_price,
        "currency": currency,
        "breakdown_json": json.dumps(breakdown),
        "status": "sent",
    }
    if client is None:
        quote_id = f"LOCAL-{len(_local_quotes) + 1:04d}"
        _local_quotes.append({**record, "id": quote_id, "created_at": datetime.now(timezone.utc).isoformat()})
        return quote_id
    try:
        result = client.table("quotes").insert(record).execute()
        if result.data:
            return result.data[0].get("id")
        return None
    except Exception as e:
        logger.error(f"Failed to save quote: {e}")
        return None


def get_user_quotes(user_id: str, limit: int = 10) -> list:
    """Fetch recent quotes for a user."""
    client = _get_client()
    if client is None:
        return [q for q in _local_quotes if q["user_id"] == str(user_id)][-limit:]
    try:
        result = client.table("quotes").select("*").eq(
            "user_id", str(user_id)
        ).order("created_at", desc=True).limit(limit).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to fetch quotes: {e}")
        return []


# ══════════════════════════════════════════════════════
# AUDIT LOG OPERATIONS
# ══════════════════════════════════════════════════════

def log_audit(action_type: str, input_data: str = None,
              output_data: str = None, user_id: str = None,
              warnings: str = None, metadata: dict = None,
              duration_ms: int = None, success: bool = True) -> bool:
    """Log an action to the audit trail. NEVER skip this."""
    client = _get_client()
    record = {
        "action_type": action_type,
        "input": input_data,
        "output": output_data,
        "user_id": str(user_id) if user_id else None,
        "warnings": warnings,
        "metadata": json.dumps(metadata) if metadata else None,
        "duration_ms": duration_ms,
        "success": success,
    }
    if client is None:
        _local_audit_log.append({
            **record,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"AUDIT [{action_type}]: {input_data[:80] if input_data else 'N/A'}")
        return True
    try:
        client.table("bot_audit_log").insert(record).execute()
        return True
    except Exception as e:
        logger.error(f"CRITICAL: Failed to write audit log: {e}")
        # Fallback — at minimum, log to file
        _local_audit_log.append({
            **record,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        })
        return False


# ══════════════════════════════════════════════════════
# FOLLOW-UP OPERATIONS
# ══════════════════════════════════════════════════════

def create_follow_up(user_id: str, scheduled_time: datetime,
                     message: str, channel_id: str = None) -> bool:
    """Schedule a follow-up message."""
    client = _get_client()
    record = {
        "user_id": str(user_id),
        "discord_channel_id": channel_id,
        "scheduled_time": scheduled_time.isoformat(),
        "message": message,
        "status": "pending",
    }
    if client is None:
        _local_follow_ups.append(record)
        return True
    try:
        client.table("follow_ups").insert(record).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to create follow-up: {e}")
        return False


def get_pending_follow_ups() -> list:
    """Fetch all pending follow-ups that are due."""
    client = _get_client()
    now = datetime.now(timezone.utc).isoformat()
    if client is None:
        return [f for f in _local_follow_ups
                if f["status"] == "pending" and f["scheduled_time"] <= now]
    try:
        result = client.table("follow_ups").select("*").eq(
            "status", "pending"
        ).lte("scheduled_time", now).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to fetch follow-ups: {e}")
        return []


def mark_follow_up_sent(follow_up_id: str) -> bool:
    """Mark a follow-up as sent."""
    client = _get_client()
    if client is None:
        return True  # Local mode — no-op
    try:
        client.table("follow_ups").update({
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", follow_up_id).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to update follow-up: {e}")
        return False


# ══════════════════════════════════════════════════════
# LOCAL FALLBACK DATA (when Supabase is not configured)
# ══════════════════════════════════════════════════════

LOCAL_PRODUCTS = {
    "WTZ-1700": {
        "product_code": "WTZ-1700",
        "category": "floor",
        "constraints": "above-waterline only",
        "base_price": 450.00,
        "shipping_cost": 55.00,
        "description": "Floor expansion joint cover, aluminum profile, heavy traffic rated. Suitable for commercial buildings, malls, airports.",
    },
    "WTZ-1800": {
        "product_code": "WTZ-1800",
        "category": "floor",
        "constraints": "above-waterline only",
        "base_price": 520.00,
        "shipping_cost": 60.00,
        "description": "Premium floor expansion joint cover, stainless steel, seismic rated. Designed for high-movement zones.",
    },
    "WE-50": {
        "product_code": "WE-50",
        "category": "wall",
        "constraints": "interior only",
        "base_price": 280.00,
        "shipping_cost": 40.00,
        "description": "Wall expansion joint cover, standard aluminum profile. For interior partition walls and drywall joints.",
    },
    "WE-100": {
        "product_code": "WE-100",
        "category": "wall",
        "constraints": "none",
        "base_price": 350.00,
        "shipping_cost": 45.00,
        "description": "Wall expansion joint cover, fire-rated, all environments. Suitable for interior and exterior applications.",
    },
    "RE-200": {
        "product_code": "RE-200",
        "category": "roof",
        "constraints": "exterior only, UV resistant",
        "base_price": 420.00,
        "shipping_cost": 50.00,
        "description": "Roof expansion joint cover, weather-sealed with UV-resistant membrane. For flat and pitched roofs.",
    },
    "RE-300": {
        "product_code": "RE-300",
        "category": "roof",
        "constraints": "exterior only",
        "base_price": 380.00,
        "shipping_cost": 48.00,
        "description": "Roof expansion joint cover, lightweight aluminum construction. Budget-friendly exterior roof solution.",
    },
    "FE-75": {
        "product_code": "FE-75",
        "category": "floor",
        "constraints": "waterproof, submersible",
        "base_price": 680.00,
        "shipping_cost": 65.00,
        "description": "Submersible floor expansion joint, pool and fountain rated. Designed for continuous water exposure.",
    },
    "WTZ-2000": {
        "product_code": "WTZ-2000",
        "category": "floor",
        "constraints": "above-waterline only, heavy-duty",
        "base_price": 750.00,
        "shipping_cost": 70.00,
        "description": "Industrial floor expansion joint, warehouse and factory rated. Supports forklift and heavy machinery traffic.",
    },
}

# In-memory fallback storage
_local_conversations: list = []
_local_customer_cards: dict = {}
_local_quotes: list = []
_local_audit_log: list = []
_local_follow_ups: list = []


def _get_product_local(product_code: str) -> Optional[dict]:
    """Fallback: get product from local dictionary."""
    return LOCAL_PRODUCTS.get(product_code.upper())
