# SPEC.md — Autonomous Sales Manager Bot
## Expansion Joint Covers Company — Discord Sales Agent

**Version:** 1.0.0
**Last Updated:** 2026-04-03
**Author:** AI Systems Engineering Team

---

## 1. Definition of "Correct"

### 1.1 Quotation Correctness Rules

A quotation is VALID if and only if ALL of the following conditions are met:

| # | Rule | Example |
|---|------|---------|
| R1 | **Product name + code must exist in DB** | `WTZ-1700`, `WE-50` — must match `products.product_code` |
| R2 | **Use-case must pass constraint validation** | If `constraints = "above-waterline only"` → reject submerged use-cases |
| R3 | **Region-specific pricing is DETERMINISTIC** | Pricing is rule-based, NEVER LLM-generated |
| R4 | **Currency matches region** | GCC → AED/SAR, India → INR, SEA → SGD/MYR |
| R5 | **No hallucinated product specs** | All specs pulled from DB, never fabricated by LLM |
| R6 | **Breakdown JSON is always present** | Every quote must include machine-parseable cost breakdown |

### 1.2 Region-Specific Pricing Logic (DETERMINISTIC)

```
GCC Pricing:
  final_price = (base_price × 2.0) + (shipping_cost × 1.5)
  currency = "AED"
  notes: Material markup ×2, Shipping markup ×1.5

India Pricing:
  final_price = base_price + installation_cost + pidilite_cost
  installation_cost = base_price × 0.25  (25% of base)
  pidilite_cost = base_price × 0.10      (10% of base, adhesive/sealant)
  currency = "INR"
  notes: Includes Pidilite adhesive + on-site installation

SEA Pricing:
  final_price = base_price × 2.5  (Ankara multiplier)
  currency = "SGD"
  notes: Ankara manufacturing + regional logistics ×2.5
```

### 1.3 Bot Behavioral Rules

| Rule | Description |
|------|-------------|
| B1 | Bot must NEVER quote invalid product-use combinations |
| B2 | Every interaction (user message + bot response) must be stored in `conversations` table |
| B3 | Conversation memory is maintained per Discord user ID |
| B4 | Memory context window = last 10 messages per user |
| B5 | All LLM calls must be logged in `bot_audit_log` |
| B6 | Bot must respond within 15 seconds or send "processing..." message |

---

## 2. Autonomy vs Escalation — 5 Rules

The bot operates autonomously UNLESS one of the following escalation triggers fires:

| # | Trigger | Condition | Action |
|---|---------|-----------|--------|
| E1 | **Unknown Product Code** | `product_code NOT IN products table` | Respond: "I don't recognize this product code. Let me connect you with our sales team." → Log `escalation_unknown_product` |
| E2 | **Conflicting Constraints** | Use-case violates `products.constraints` (e.g., submerged use with above-waterline-only product) | Reject quote, explain constraint, suggest alternatives if available → Log `guardrail_triggered` |
| E3 | **Large Order Value** | `final_price > $50,000 USD equivalent` OR `quantity > 500 units` | Respond: "This is a significant order. I'm flagging this for our senior sales manager for personalized pricing." → Log `escalation_large_order` |
| E4 | **Ambiguous Intent** | After 2 clarification attempts, user intent still unclear | Respond: "I want to make sure I get this right. Let me connect you with a specialist." → Log `escalation_ambiguous_intent` |
| E5 | **Custom Engineering Request** | User mentions: custom dimensions, non-standard materials, bespoke designs, engineering drawings | Respond: "Custom engineering requests require our technical team. I'll escalate this." → Log `escalation_custom_engineering` |

### Escalation Flow:
```
User Message → Intent Parse → Escalation Check
  ├── No trigger → Continue autonomous flow
  └── Trigger fired → Log escalation → Notify admin channel → Inform user
```

---

## 3. Failure Modes — 3 Critical Scenarios

### FM1: LLM Hallucinates Product Compatibility

| Aspect | Detail |
|--------|--------|
| **Scenario** | LLM generates a quote claiming WTZ-1700 is suitable for "underwater tunnels" when constraints say "above-waterline only" |
| **Root Cause** | LLM ignores constraint data in prompt context |
| **Mitigation** | Product Validator runs AFTER LLM intent parse but BEFORE quote generation. Validator is pure Python logic — no LLM involvement. Constraints are checked with keyword matching against a rejection word list. |
| **Detection** | Audit log shows `guardrail_triggered` entries. Weekly review of all `generate_quote` logs. |
| **Recovery** | Quote is blocked. User receives rejection message. Admin is notified. |

### FM2: Pricing Multiplier Applied Incorrectly

| Aspect | Detail |
|--------|--------|
| **Scenario** | India pricing formula applies GCC multiplier, resulting in 2× overcharge |
| **Root Cause** | Region detection error or code bug in pricing engine |
| **Mitigation** | Pricing engine is a deterministic function with unit tests. Region is validated against enum `["GCC", "India", "SEA"]`. If region is unknown, bot asks user to confirm. Every quote includes `breakdown_json` for manual verification. |
| **Detection** | Audit log captures `pricing_calculated` with full breakdown. Anomaly: price deviates >20% from historical average for same product+region. |
| **Recovery** | Requote with correct region. Notify affected customer. |

### FM3: Context Loss Across Long Conversations

| Aspect | Detail |
|--------|--------|
| **Scenario** | User has 50+ message conversation. Bot loses track of earlier requirements (e.g., forgets region was specified as India, switches to GCC pricing) |
| **Root Cause** | LLM context window overflow. Memory retrieval returns only recent messages. |
| **Mitigation** | (1) Store structured "customer card" with extracted preferences (region, preferred products). (2) Always inject customer card into LLM prompt. (3) Use summarization for conversations >10 messages. (4) Critical fields (region, product) are stored in structured form, not just in conversation text. |
| **Detection** | Monitor for region/product changes within same session. Flag if region switches without explicit user request. |
| **Recovery** | Re-confirm preferences with user. Rebuild customer card from conversation history. |

---

## 4. End-to-End Testing Plan

### Test Case Matrix

| # | Test Name | Input | Expected Output | Validates |
|---|-----------|-------|-----------------|-----------|
| T1 | **Valid GCC Quote** | "I need a quote for WTZ-1700 for floor expansion joints in Dubai, 10 units" | Quote generated: base×2 + shipping×1.5, currency=AED, product=WTZ-1700 | Pricing engine, region detection, quote generation |
| T2 | **Valid India Quote** | "Quote WE-50 for wall joints in Mumbai, 5 pieces" | Quote with base + installation(25%) + Pidilite(10%), currency=INR | India pricing formula |
| T3 | **Valid SEA Quote** | "Need WTZ-1700 for a project in Singapore, 20 units" | Quote with base×2.5, currency=SGD | SEA/Ankara multiplier |
| T4 | **🔴 GUARDRAIL: Submerged Rejection** | "Quote WTZ-1800 for a submerged swimming pool" | **REJECT**: "This product is not suitable for submerged applications. WTZ-1800 is rated for above-waterline use only." + `guardrail_triggered` log entry | Constraint validation, audit logging |
| T5 | **Unknown Product** | "Quote XYZ-9999 for Dubai" | Escalation: "I don't recognize product code XYZ-9999." + `escalation_unknown_product` log | Escalation rule E1 |
| T6 | **Large Order Escalation** | "Need 1000 units of WTZ-1700 for mega project in Dubai" | Escalation: "This is a significant order..." + `escalation_large_order` log | Escalation rule E3 |
| T7 | **Custom Engineering** | "I need custom-dimension expansion joints, 3m wide" | Escalation: "Custom engineering requests require..." + `escalation_custom_engineering` log | Escalation rule E5 |
| T8 | **Memory Persistence** | Message 1: "I'm based in Dubai" → Message 2: "Quote WTZ-1700" | Should remember region=GCC from message 1 and apply GCC pricing | Memory layer |
| T9 | **Conversation Storage** | Any user message | Entry created in `conversations` table with user_id, message, response, timestamp | Data persistence |
| T10 | **Audit Trail** | Any bot action | Corresponding entry in `bot_audit_log` with action_type, input, output | Audit completeness |

### Guardrail Test (MANDATORY — T4 Detail)

```
INPUT:  "Quote WTZ-1800 for a submerged swimming pool"

PROCESSING:
  1. Intent Parser extracts: product_code=WTZ-1800, use_case="submerged swimming pool"
  2. Product Validator fetches WTZ-1800 from DB: constraints="above-waterline only"
  3. Validator checks: "submerged" ∈ rejection_keywords AND constraint="above-waterline only"
  4. RESULT: CONSTRAINT VIOLATION DETECTED

EXPECTED OUTPUT:
  Bot Response: "⚠️ This product is not suitable for submerged applications.
  WTZ-1800 is designed for above-waterline expansion joints only.
  For underwater/submerged applications, please contact our engineering
  team for suitable alternatives."

EXPECTED LOG:
  bot_audit_log entry:
    action_type = "guardrail_triggered"
    input = "Quote WTZ-1800 for a submerged swimming pool"
    output = "REJECTED: constraint violation — above-waterline only product requested for submerged use"
    warnings = "CONSTRAINT_VIOLATION: product=WTZ-1800, constraint=above-waterline only, use_case=submerged swimming pool"
```

---

## 5. System Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   DISCORD CLIENT                     │
│                  (discord.py)                         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│              BOT HANDLER (main.py)                    │
│  • Receives messages                                  │
│  • Routes to pipeline                                 │
│  • Manages sessions via Discord user ID               │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌─────────────┐ ┌───────────┐ ┌──────────┐
│ INTENT      │ │ MEMORY    │ │ AUDIT    │
│ PARSER      │ │ LAYER     │ │ LOGGER   │
│ (LLM)       │ │ (DB)      │ │ (DB)     │
└──────┬──────┘ └───────────┘ └──────────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│ PRODUCT      │────▶│ PRICING      │
│ VALIDATOR    │     │ ENGINE       │
│ (Rule-based) │     │ (Rule-based) │
└──────┬───────┘     └──────┬───────┘
       │                    │
       ▼                    ▼
┌──────────────────────────────────┐
│        QUOTE GENERATOR           │
│     (LLM + Structured Output)    │
└──────────────────────────────────┘
```

---

## 6. Product Catalog (Seed Data)

| Code | Category | Constraints | Base Price (USD) | Description |
|------|----------|-------------|-----------------|-------------|
| WTZ-1700 | Floor | above-waterline only | 450 | Floor expansion joint cover, aluminum profile, heavy traffic rated |
| WTZ-1800 | Floor | above-waterline only | 520 | Premium floor expansion joint, stainless steel, seismic rated |
| WE-50 | Wall | interior only | 280 | Wall expansion joint cover, standard profile |
| WE-100 | Wall | none | 350 | Wall expansion joint cover, fire-rated, all environments |
| RE-200 | Roof | exterior only, UV resistant | 420 | Roof expansion joint cover, weather-sealed |
| RE-300 | Roof | exterior only | 380 | Roof expansion joint, lightweight aluminum |
| FE-75 | Floor | waterproof, submersible | 680 | Submersible floor joint, pool/fountain rated |
| WTZ-2000 | Floor | above-waterline only, heavy-duty | 750 | Industrial floor joint, warehouse/factory rated |

---

## 7. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Response Latency | < 15 seconds (send "thinking..." if exceeding 5s) |
| Uptime | 99% (Discord bot process) |
| Data Retention | All conversations stored indefinitely |
| Audit Coverage | 100% of bot actions logged |
| Concurrent Users | Handle 50 simultaneous conversations |
| Error Recovery | Graceful degradation — if LLM fails, inform user and log |
