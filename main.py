"""
Autonomous Sales Manager Bot — Discord Entry Point
===================================================
Main bot handler using discord.py.
Routes messages through the full processing pipeline:
  Message → Intent Parse → Validate → Price → Quote → Store → Respond

Commands:
  !quote <description>  — Generate a quotation
  !products             — List all products
  !history              — View recent conversation history
  !help                 — Show available commands

Also responds to natural chat messages (no prefix required).
"""
import asyncio
import logging
import time
import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone

from config import (
    DISCORD_TOKEN, DISCORD_ADMIN_CHANNEL_ID,
    BOT_PREFIX, RESPONSE_TIMEOUT,
)
from database import (
    save_conversation, log_audit, get_all_products,
    get_user_quotes,
)
from intent_parser import parse_intent
from product_validator import validate_product_request
from pricing_engine import calculate_price, format_price_display
from quote_generator import generate_quote, handle_product_inquiry
from memory_layer import (
    build_conversation_context, build_customer_context,
    update_customer_from_intent, get_user_region,
)
from follow_up_scheduler import (
    schedule_follow_up_if_needed, process_pending_follow_ups,
)
from llm_client import call_llm_with_history

# ── Logging Setup ────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-28s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("sales_bot.main")

# ── Bot Setup ────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)

# ── Track clarification attempts per user ────────────
_clarification_counts: dict = {}


# ══════════════════════════════════════════════════════
# BOT EVENTS
# ══════════════════════════════════════════════════════

@bot.event
async def on_ready():
    """Called when bot successfully connects to Discord."""
    logger.info(f"{'═' * 50}")
    logger.info(f"  Sales Manager Bot Online!")
    logger.info(f"  Logged in as: {bot.user.name} ({bot.user.id})")
    logger.info(f"  Guilds: {len(bot.guilds)}")
    logger.info(f"{'═' * 50}")

    log_audit(
        action_type="bot_started",
        input_data=f"bot_user={bot.user.name}",
        output_data=f"Connected to {len(bot.guilds)} guild(s)",
    )

    # Start background tasks
    if not follow_up_loop.is_running():
        follow_up_loop.start()

    # Set bot status
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="expansion joint inquiries | !help",
        )
    )


@bot.event
async def on_message(message: discord.Message):
    """Process every incoming message."""
    # Ignore bot's own messages
    if message.author == bot.user:
        return

    # Ignore DMs (only respond in guild channels)
    if not message.guild:
        return

    # Process commands first (!quote, !products, etc.)
    await bot.process_commands(message)

    # If message starts with prefix, it was handled by commands
    if message.content.startswith(BOT_PREFIX):
        return

    # ── Natural chat processing ──────────────────────
    # Only respond if bot is mentioned OR message is in a designated channel
    if bot.user.mentioned_in(message) or _is_sales_channel(message.channel):
        # Remove bot mention from message
        clean_content = message.content.replace(f"<@{bot.user.id}>", "").strip()
        if clean_content:
            await _process_message(message, clean_content)


# ══════════════════════════════════════════════════════
# BOT COMMANDS
# ══════════════════════════════════════════════════════

@bot.command(name="quote")
async def cmd_quote(ctx: commands.Context, *, description: str = None):
    """Generate a quotation. Usage: !quote WTZ-1700 for floor joints in Dubai, 10 units"""
    if not description:
        await ctx.send(
            "📝 **How to request a quote:**\n\n"
            "`!quote <product code> for <use-case> in <region>, <quantity> units`\n\n"
            "**Example:** `!quote WTZ-1700 for floor expansion joints in Dubai, 10 units`\n\n"
            "Or just describe what you need in plain English!"
        )
        return

    await _process_message(ctx.message, description, force_quote=True)


@bot.command(name="products")
async def cmd_products(ctx: commands.Context, category: str = None):
    """List available products. Usage: !products [floor|wall|roof]"""
    products = get_all_products()

    if category:
        products = [p for p in products if p.get("category") == category.lower()]

    if not products:
        await ctx.send("No products found for that category. Try: `!products floor`, `wall`, or `roof`.")
        return

    lines = ["📦 **Expansion Joint Covers — Product Catalog**\n"]
    current_category = None

    # Sort by category
    products.sort(key=lambda p: p.get("category", ""))

    for p in products:
        cat = p.get("category", "unknown").title()
        if cat != current_category:
            current_category = cat
            lines.append(f"\n**━━ {cat} Joints ━━**")

        code = p.get("product_code", "?")
        desc = p.get("description", "")[:70]
        price = float(p.get("base_price", 0))
        constraints = p.get("constraints", "none")

        lines.append(
            f"▸ **{code}** — {desc}\n"
            f"  Base: ${price:,.2f} │ Constraints: _{constraints}_"
        )

    lines.append("\n\n💡 Use `!quote <code> for <use-case> in <region>` to get a quote.")
    await ctx.send("\n".join(lines))


@bot.command(name="history")
async def cmd_history(ctx: commands.Context):
    """View your recent quotes. Usage: !history"""
    user_id = str(ctx.author.id)
    quotes = get_user_quotes(user_id, limit=5)

    if not quotes:
        await ctx.send("You don't have any quotes yet. Try `!quote` to create one!")
        return

    lines = ["📋 **Your Recent Quotes:**\n"]
    for q in quotes:
        code = q.get("product_code", "?")
        region = q.get("region", "?")
        price = float(q.get("final_price", 0))
        currency = q.get("currency", "USD")
        created = q.get("created_at", "?")[:10]
        lines.append(
            f"▸ **{code}** ({region}) — {format_price_display(price, currency)} │ {created}"
        )

    await ctx.send("\n".join(lines))


@bot.command(name="help")
async def cmd_help(ctx: commands.Context):
    """Show available commands."""
    help_text = (
        "🤖 **Expansion Joint Covers — Sales Assistant**\n\n"
        "**Commands:**\n"
        "▸ `!quote <description>` — Generate a quotation\n"
        "▸ `!products [category]` — List products (floor/wall/roof)\n"
        "▸ `!history` — View your recent quotes\n"
        "▸ `!help` — Show this message\n\n"
        "**Natural Chat:**\n"
        "You can also just @ mention me or chat naturally!\n"
        "Example: _\"I need expansion joints for a mall in Dubai\"_\n\n"
        "**Regions Served:**\n"
        "🌍 GCC (Middle East) │ 🇮🇳 India │ 🌏 SEA (Southeast Asia)"
    )
    await ctx.send(help_text)


# ══════════════════════════════════════════════════════
# CORE MESSAGE PROCESSING PIPELINE
# ══════════════════════════════════════════════════════

async def _process_message(message: discord.Message, content: str,
                           force_quote: bool = False):
    """
    Main processing pipeline for all user messages.

    Flow:
    1. Log incoming message
    2. Parse intent (LLM)
    3. Route based on intent type
    4. Validate constraints (rule-based)
    5. Generate response
    6. Store conversation
    7. Schedule follow-up
    """
    user_id = str(message.author.id)
    username = message.author.display_name
    start_time = time.time()

    # Show "typing" indicator
    async with message.channel.typing():
        try:
            # ── Step 1: Log incoming ─────────────────
            log_audit(
                action_type="message_received",
                input_data=content[:500],
                user_id=user_id,
            )

            # ── Step 2: Parse intent ─────────────────
            intent = parse_intent(content, user_id=user_id)
            intent_type = intent.get("intent_type", "unknown")

            # ── Step 3: Update customer card ─────────
            update_customer_from_intent(user_id, intent, username)

            # ── Step 4: Route by intent type ─────────
            if force_quote or intent_type == "quote_request":
                response = generate_quote(user_id, intent, username)

            elif intent_type == "product_inquiry":
                response = handle_product_inquiry(user_id, intent)

            elif intent_type == "greeting":
                customer_ctx = build_customer_context(user_id)
                response = (
                    f"Hello {username}! 👋 Welcome to our Expansion Joint Covers sales assistant.\n\n"
                    f"I can help you with:\n"
                    f"• Product information and specifications\n"
                    f"• Quotations for GCC, India, and SEA regions\n"
                    f"• Product recommendations based on your project needs\n\n"
                    f"What can I help you with today?"
                )

            elif intent_type in ("general_question", "follow_up"):
                # Use LLM with conversation history for context-aware response
                history = build_conversation_context(user_id)
                customer_ctx = build_customer_context(user_id)

                system_prompt = (
                    "You are a professional sales assistant for an expansion joint covers company. "
                    "You help customers with product inquiries, quotations, and technical questions. "
                    "Be helpful, professional, and concise. If you're unsure about specific product "
                    "details, recommend they ask for specific product info or a quote.\n\n"
                    f"Customer Context:\n{customer_ctx}\n\n"
                    "IMPORTANT: Never make up product specifications. Only reference products "
                    "from the catalog. If unsure, say so."
                )

                response = call_llm_with_history(
                    system_prompt=system_prompt,
                    conversation_history=history,
                    user_message=content,
                    temperature=0.5,
                    user_id=user_id,
                    action_label="general_response",
                )

            elif intent_type == "unknown":
                # Ambiguity handling with escalation counter
                _clarification_counts[user_id] = _clarification_counts.get(user_id, 0) + 1
                if _clarification_counts[user_id] >= 2:
                    # Escalation rule E4: Ambiguous after 2 attempts
                    _clarification_counts[user_id] = 0
                    response = (
                        "I want to make sure I get this right. Let me connect you with a specialist "
                        "who can better assist you.\n\n"
                        "In the meantime, you can try:\n"
                        "• `!products` — Browse our catalog\n"
                        "• `!quote <product> for <use-case> in <region>` — Get a direct quote"
                    )
                    log_audit(
                        action_type="escalation_ambiguous_intent",
                        input_data=content[:500],
                        output_data="Escalated after 2 clarification attempts",
                        user_id=user_id,
                        warnings="User intent unclear after 2 attempts",
                    )
                else:
                    response = (
                        "I'd like to help! Could you clarify what you're looking for?\n\n"
                        "For example:\n"
                        "• _\"I need floor expansion joints for a mall in Dubai\"_\n"
                        "• _\"What's the price of WTZ-1700 for 10 units in India?\"_\n"
                        "• _\"Show me roof joint options\"_"
                    )
            else:
                response = (
                    "I'm here to help with expansion joint covers! Try:\n"
                    "• `!quote` — Get a quotation\n"
                    "• `!products` — Browse our catalog\n"
                    "• Or just describe what you need!"
                )

            # Reset clarification count on successful intent
            if intent_type not in ("unknown",):
                _clarification_counts[user_id] = 0

            # ── Step 5: Send response ────────────────
            # Discord has 2000 char limit — split if needed
            if len(response) > 1900:
                chunks = _split_message(response, 1900)
                for chunk in chunks:
                    await message.channel.send(chunk)
            else:
                await message.channel.send(response)

            # ── Step 6: Store conversation ───────────
            duration = int((time.time() - start_time) * 1000)
            save_conversation(
                user_id=user_id,
                username=username,
                message=content,
                response=response[:2000],
                intent_parsed=intent,
            )

            log_audit(
                action_type="response_sent",
                input_data=content[:200],
                output_data=response[:200],
                user_id=user_id,
                duration_ms=duration,
                metadata={"intent_type": intent_type},
            )

            # ── Step 7: Schedule follow-up ───────────
            if intent_type in ("quote_request", "product_inquiry"):
                schedule_follow_up_if_needed(
                    user_id=user_id,
                    channel_id=str(message.channel.id),
                )

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            log_audit(
                action_type="processing_error",
                input_data=content[:500],
                output_data=str(e),
                user_id=user_id,
                warnings=f"Unhandled error: {type(e).__name__}: {e}",
                success=False,
            )
            await message.channel.send(
                "I encountered an unexpected error processing your request. "
                "Please try again or use `!help` for available commands."
            )


# ══════════════════════════════════════════════════════
# BACKGROUND TASKS
# ══════════════════════════════════════════════════════

@tasks.loop(minutes=30)
async def follow_up_loop():
    """Background task: check and send pending follow-ups every 30 minutes."""
    try:
        count = await process_pending_follow_ups(bot)
        if count > 0:
            logger.info(f"Processed {count} follow-up(s)")
    except Exception as e:
        logger.error(f"Follow-up loop error: {e}")


@follow_up_loop.before_loop
async def before_follow_up_loop():
    """Wait for bot to be ready before starting follow-up loop."""
    await bot.wait_until_ready()


# ══════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════

def _is_sales_channel(channel) -> bool:
    """Check if the channel is designated for sales inquiries."""
    sales_keywords = ["sales", "quote", "inquiry", "support", "bot"]
    channel_name = getattr(channel, "name", "").lower()
    return any(kw in channel_name for kw in sales_keywords)


def _split_message(text: str, max_length: int = 1900) -> list:
    """Split a long message into chunks that fit Discord's limit."""
    if len(text) <= max_length:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break

        # Try to split at a newline
        split_at = text.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = max_length

        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks


# ══════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════

def main():
    """Start the Discord bot."""
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN":
        logger.error(
            "═══════════════════════════════════════════════\n"
            "  DISCORD_TOKEN not set!\n"
            "  Add your bot token to .env file:\n"
            "  DISCORD_TOKEN=your_token_here\n"
            "═══════════════════════════════════════════════"
        )
        return

    logger.info("Starting Autonomous Sales Manager Bot...")
    log_audit(action_type="bot_starting", input_data="Initialization")

    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
