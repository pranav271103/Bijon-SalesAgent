# Autonomous Sales Manager Bot

> **Expansion Joint Covers Company** — Discord Sales Agent
> Production-grade prototype for automated product inquiries, quotations, and customer management across GCC, India, and SEA regions.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    DISCORD CLIENT                        │
│                   (discord.py v2.x)                      │
└──────────────────────────┬──────────────────────────────┘
                           │
               ┌───────────▼───────────┐
               │   main.py (Router)     │
               │  • Commands: !quote    │
               │  • Natural chat        │
               │  • Session mgmt        │
               └───────────┬───────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌────────────────┐ ┌─────────────┐ ┌─────────────────┐
│ intent_parser  │ │ memory_layer│ │ database.py      │
│ (LLM-powered)  │ │ (Context)   │ │ (Supabase/Local) │
└───────┬────────┘ └─────────────┘ └─────────────────┘
        │
        ▼
┌────────────────────┐     ┌──────────────────┐
│ product_validator  │───▶ │  pricing_engine  │
│ (RULE-BASED)       │     │ (DETERMINISTIC)  │
│  CRITICAL SAFETY   │     │ No LLM involved  │
└────────┬───────────┘     └────────┬─────────┘
         │                         │
         └────────────┬────────────┘
                      ▼
             ┌────────────────┐
             │quote_generator │
             │ (LLM + Rules)  │
             └────────────────┘
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Pricing is NEVER LLM-generated** | Deterministic math prevents hallucinated prices |
| **Product validation runs BEFORE quote generation** | Guardrail catches constraint violations early |
| **Every action is audit-logged** | Full traceability for compliance and debugging |
| **Local fallback when Supabase is offline** | Bot remains functional without cloud DB |
| **Customer cards store structured preferences** | Prevents context loss in long conversations |

---

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your credentials:
#   DISCORD_TOKEN=your_bot_token
#   NVIDIA_API_KEY=your_nvidia_key
#   SUPABASE_URL=your_supabase_url  (optional — works without it)
#   SUPABASE_KEY=your_supabase_key  (optional — works without it)
```

### 3. Set Up Database (Optional — bot works without Supabase)
Run `schema.sql` in your Supabase SQL editor to create all tables and seed product data.

### 4. Run the Bot
```bash
python main.py
```

---

## Project Structure

```
Discord/
├── main.py                 # Discord bot entry point + message routing
├── config.py               # Environment variables + constants
├── database.py             # Supabase client + all DB operations
├── llm_client.py           # NVIDIA LLM API wrapper with retry logic
├── intent_parser.py        # LLM-powered intent extraction
├── product_validator.py    # ⚠️ CRITICAL: Rule-based constraint checking
├── pricing_engine.py       # Deterministic regional pricing
├── quote_generator.py      # Full quote generation pipeline
├── memory_layer.py         # Conversation context + customer profiles
├── follow_up_scheduler.py  # Background follow-up reminders
├── schema.sql              # Supabase database schema + seed data
├── SPEC.md                 # Full system specification
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (NEVER commit)
└── .env.example            # Template for .env
```

---

## Discord Commands

| Command | Description | Example |
|---------|-------------|---------|
| `!quote <desc>` | Generate quotation | `!quote WTZ-1700 for floor joints in Dubai, 10 units` |
| `!products [cat]` | List products | `!products floor` |
| `!history` | View your recent quotes | `!history` |
| `!help` | Show commands | `!help` |
| `@bot <message>` | Natural chat | `@bot I need roof joints for Singapore` |

---

## Context Degradation in Long-Running Agents

### The Problem
LLMs have fixed context windows (typically 4K–128K tokens). As conversations grow longer, the agent faces:

1. **Token Overflow**: Conversation history exceeds context window → oldest messages are silently dropped
2. **Attention Dilution**: Even within the window, LLMs attend less to middle content ("lost in the middle" problem)
3. **Preference Drift**: User's region, product preferences stated early can be forgotten

### Our Mitigation Strategy

| Strategy | Implementation |
|----------|---------------|
| **Structured Customer Cards** | Region, preferences stored in DB — injected into every prompt regardless of history length |
| **Sliding Window** | Only last 10 messages sent to LLM (configurable via `MEMORY_WINDOW`) |
| **Retrieval over Summarization** | We retrieve raw messages rather than summarizing, preserving exact user intent |
| **Critical Fields in DB** | Region, product preferences stored structurally — not dependent on conversation text |

### Tradeoff: Retrieval vs Summarization

```
Retrieval (our approach):
  ✅ Exact user quotes preserved
  ✅ No information loss from summarization
  ❌ Limited to N most recent messages
  ❌ Older context lost

Summarization (alternative):
  ✅ Can compress entire conversation
  ✅ Covers all time periods
  ❌ LLM may lose critical details
  ❌ Costs extra tokens + latency for summarization call
  ❌ Summarization itself may hallucinate

Hybrid (future improvement):
  → Retrieve last 10 messages + summarize messages 11-50
  → Store structured "memory objects" for key decisions
```

---

## Task-Job Boundary — 5 Escalation Rules

The bot must know when to STOP being autonomous and escalate to a human.

| # | Rule | Trigger Condition | Bot Response |
|---|------|-------------------|-------------|
| 1 | **Unknown Product** | Product code not in database | "I don't recognize this product code." → Flag for sales team |
| 2 | **Constraint Conflict** | Use-case violates product constraints | "This product is not suitable for [use-case]." → Suggest alternatives |
| 3 | **Large Order** | Value > $50K or qty > 500 units | "This is a significant order." → Escalate for volume pricing |
| 4 | **Ambiguous Intent** | 2 failed clarification attempts | "Let me connect you with a specialist." → Hand off |
| 5 | **Custom Engineering** | Mentions custom dimensions, bespoke, engineering drawings | "Custom requests require our technical team." → Escalate |

### Why These 5?
- **Rules 1-2**: Safety — prevent hallucinated or dangerous recommendations
- **Rule 3**: Business logic — large orders need negotiation and logistics planning
- **Rule 4**: UX quality — don't frustrate users with endless bot loops
- **Rule 5**: Complexity boundary — custom engineering exceeds bot's knowledge

---

## Testing

### Run Guardrail Test
```
User: "Quote WTZ-1800 for a submerged swimming pool"
Expected: REJECTION — "This product is not suitable for submerged applications."
Check: bot_audit_log should have action_type = "guardrail_triggered"
```

### Verify Pricing
```
Product: WTZ-1700 (base: $450, shipping: $55)
GCC:   (450 × 2) + (55 × 1.5) = $982.50 AED per unit
India: 450 + (450 × 0.25) + (450 × 0.10) = $607.50 INR per unit
SEA:   450 × 2.5 = $1,125.00 SGD per unit
```

---

