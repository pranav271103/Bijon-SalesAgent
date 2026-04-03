"""
LLM Client — Wraps NVIDIA Build Platform API (OpenAI-compatible).
Handles all LLM calls with retry logic, error handling, and audit logging.
"""
import json
import time
import logging
from typing import Optional
from openai import OpenAI
from config import NVIDIA_API_KEY, NVIDIA_BASE_URL, NVIDIA_MODEL
from database import log_audit

logger = logging.getLogger("sales_bot.llm_client")

# ── Initialize NVIDIA client (OpenAI-compatible) ────
_llm_client: Optional[OpenAI] = None


def _get_llm_client() -> OpenAI:
    """Lazy-init the LLM client."""
    global _llm_client
    if _llm_client is None:
        if not NVIDIA_API_KEY:
            raise ValueError("NVIDIA_API_KEY not set in environment")
        _llm_client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=NVIDIA_API_KEY,
        )
    return _llm_client


def call_llm(system_prompt: str, user_message: str,
             temperature: float = 0.3, max_tokens: int = 1024,
             user_id: str = None, action_label: str = "llm_call") -> str:
    """
    Call the NVIDIA LLM API with retry logic.

    Args:
        system_prompt: The system-level instruction
        user_message: The user's input
        temperature: Creativity (low = deterministic for parsing)
        max_tokens: Max response length
        user_id: For audit logging
        action_label: Audit action type (e.g., parse_intent, generate_quote)

    Returns:
        LLM response text, or error message string
    """
    start_time = time.time()
    retries = 3

    for attempt in range(retries):
        try:
            client = _get_llm_client()
            response = client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = response.choices[0].message.content.strip()
            duration_ms = int((time.time() - start_time) * 1000)

            # Audit log every LLM call
            log_audit(
                action_type=action_label,
                input_data=user_message[:500],
                output_data=result[:500],
                user_id=user_id,
                duration_ms=duration_ms,
                success=True,
            )

            return result

        except Exception as e:
            logger.warning(f"LLM call attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
            else:
                duration_ms = int((time.time() - start_time) * 1000)
                log_audit(
                    action_type=action_label,
                    input_data=user_message[:500],
                    output_data=f"ERROR: {str(e)}",
                    user_id=user_id,
                    duration_ms=duration_ms,
                    success=False,
                    warnings=f"LLM call failed after {retries} retries: {e}",
                )
                return f"I'm experiencing a temporary issue. Please try again in a moment. (Error: {type(e).__name__})"


def call_llm_with_history(system_prompt: str, conversation_history: list,
                          user_message: str, temperature: float = 0.3,
                          max_tokens: int = 1024, user_id: str = None,
                          action_label: str = "llm_call") -> str:
    """
    Call LLM with full conversation history for context-aware responses.

    Args:
        system_prompt: System instruction
        conversation_history: List of {"role": "user"/"assistant", "content": "..."}
        user_message: Current user message
        temperature, max_tokens, user_id, action_label: Same as call_llm
    """
    start_time = time.time()
    retries = 3

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    for attempt in range(retries):
        try:
            client = _get_llm_client()
            response = client.chat.completions.create(
                model=NVIDIA_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            result = response.choices[0].message.content.strip()
            duration_ms = int((time.time() - start_time) * 1000)

            log_audit(
                action_type=action_label,
                input_data=user_message[:500],
                output_data=result[:500],
                user_id=user_id,
                duration_ms=duration_ms,
                success=True,
                metadata={"history_length": len(conversation_history)},
            )

            return result

        except Exception as e:
            logger.warning(f"LLM call attempt {attempt + 1}/{retries} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                duration_ms = int((time.time() - start_time) * 1000)
                log_audit(
                    action_type=action_label,
                    input_data=user_message[:500],
                    output_data=f"ERROR: {str(e)}",
                    user_id=user_id,
                    duration_ms=duration_ms,
                    success=False,
                    warnings=f"LLM call with history failed: {e}",
                )
                return f"I'm experiencing a temporary issue. Please try again in a moment. (Error: {type(e).__name__})"
