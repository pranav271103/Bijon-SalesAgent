"""
Follow-Up Scheduler — Monitors user inactivity and sends reminders.
Runs as a background task within the Discord bot.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from database import (
    create_follow_up, get_pending_follow_ups,
    mark_follow_up_sent, get_recent_conversations,
    get_customer_card, log_audit,
)
from config import FOLLOW_UP_HOURS

logger = logging.getLogger("sales_bot.follow_up")


def schedule_follow_up_if_needed(user_id: str, channel_id: str = None) -> bool:
    """
    Check if a follow-up should be scheduled for this user.
    Schedules one if the user has pending quotes or recent interactions
    but no existing pending follow-up.
    """
    # Check recent activity
    recent = get_recent_conversations(user_id, limit=3)
    if not recent:
        return False  # No conversations — no follow-up needed

    # Schedule a follow-up
    scheduled_time = datetime.now(timezone.utc) + timedelta(hours=FOLLOW_UP_HOURS)

    card = get_customer_card(user_id)
    name = card.get("name", "there") if card else "there"

    message = (
        f"Hi {name}! 👋 Just checking in on your recent inquiry about "
        f"expansion joint covers. Do you have any questions or need an updated quote? "
        f"I'm here to help!"
    )

    success = create_follow_up(
        user_id=user_id,
        scheduled_time=scheduled_time,
        message=message,
        channel_id=channel_id,
    )

    if success:
        log_audit(
            action_type="follow_up_scheduled",
            input_data=f"user={user_id}, hours={FOLLOW_UP_HOURS}",
            output_data=f"Scheduled for {scheduled_time.isoformat()}",
            user_id=user_id,
        )

    return success


async def process_pending_follow_ups(bot) -> int:
    """
    Process all pending follow-ups that are due.
    Called periodically by the Discord bot's background task.

    Args:
        bot: The Discord bot instance (for sending messages)

    Returns:
        Number of follow-ups processed
    """
    pending = get_pending_follow_ups()
    processed = 0

    for follow_up in pending:
        try:
            channel_id = follow_up.get("discord_channel_id")
            if channel_id:
                channel = bot.get_channel(int(channel_id))
                if channel:
                    await channel.send(follow_up.get("message", "Following up on your inquiry!"))
                    mark_follow_up_sent(follow_up.get("id", ""))
                    processed += 1

                    log_audit(
                        action_type="follow_up_sent",
                        input_data=f"follow_up_id={follow_up.get('id')}",
                        output_data=f"Sent to channel {channel_id}",
                        user_id=follow_up.get("user_id"),
                    )
        except Exception as e:
            logger.error(f"Failed to process follow-up: {e}")
            log_audit(
                action_type="follow_up_failed",
                input_data=f"follow_up_id={follow_up.get('id')}",
                output_data=str(e),
                user_id=follow_up.get("user_id"),
                success=False,
                warnings=str(e),
            )

    return processed
