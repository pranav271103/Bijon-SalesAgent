"""
Memory Layer — Manages conversation context and customer cards.
Provides the LLM with relevant history for context-aware responses.
"""
import logging
from typing import Optional
from database import (
    get_recent_conversations, get_customer_card,
    upsert_customer_card, log_audit,
)
from config import MEMORY_WINDOW

logger = logging.getLogger("sales_bot.memory")


def build_conversation_context(user_id: str) -> list:
    """
    Build conversation history for LLM context.

    Returns list of {"role": "user"/"assistant", "content": "..."}
    Limited to MEMORY_WINDOW messages.
    """
    conversations = get_recent_conversations(user_id, limit=MEMORY_WINDOW)

    # Conversations come in desc order — reverse for chronological
    conversations.reverse()

    history = []
    for conv in conversations:
        history.append({"role": "user", "content": conv.get("message", "")})
        history.append({"role": "assistant", "content": conv.get("response", "")})

    return history


def build_customer_context(user_id: str) -> str:
    """
    Build a customer profile summary for injecting into LLM prompt.
    This prevents context loss by keeping structured data separate.
    """
    card = get_customer_card(user_id)
    if card is None:
        return "New customer — no previous profile on record."

    parts = ["**Customer Profile:**"]
    if card.get("name"):
        parts.append(f"- Name: {card['name']}")
    if card.get("region"):
        parts.append(f"- Region: {card['region']}")
    if card.get("company"):
        parts.append(f"- Company: {card['company']}")
    if card.get("notes"):
        parts.append(f"- Notes: {card['notes']}")
    if card.get("preferred_products"):
        prods = ", ".join(card["preferred_products"])
        parts.append(f"- Previously inquired products: {prods}")
    if card.get("last_interaction"):
        parts.append(f"- Last interaction: {card['last_interaction']}")

    return "\n".join(parts)


def update_customer_from_intent(user_id: str, intent: dict,
                                username: str = None) -> None:
    """
    Update customer card with newly extracted information.
    Only updates fields that are newly provided (non-null).
    """
    updates = {}
    if username:
        updates["name"] = username
    if intent.get("region"):
        updates["region"] = intent["region"]

    # Only update if there's something new
    if updates:
        upsert_customer_card(user_id, **updates)
        log_audit(
            action_type="customer_card_updated",
            input_data=f"user={user_id}",
            output_data=f"Updated fields: {list(updates.keys())}",
            user_id=user_id,
        )


def get_user_region(user_id: str, intent: dict) -> Optional[str]:
    """
    Determine user's region. Priority:
    1. Current intent (explicitly mentioned in this message)
    2. Customer card (from previous interactions)
    3. None (needs to ask)
    """
    # Priority 1: Explicit in current message
    if intent.get("region"):
        return intent["region"]

    # Priority 2: Stored in customer profile
    card = get_customer_card(user_id)
    if card and card.get("region"):
        return card["region"]

    # Priority 3: Unknown
    return None
