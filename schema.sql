-- ============================================================
-- AUTONOMOUS SALES MANAGER BOT — Supabase Schema
-- Expansion Joint Covers Company
-- Version: 1.0.0
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. PRODUCTS TABLE
-- Core product catalog with constraints for validation
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    product_code VARCHAR(20) NOT NULL UNIQUE,
    category VARCHAR(20) NOT NULL CHECK (category IN ('floor', 'wall', 'roof')),
    constraints TEXT DEFAULT 'none',
    base_price DECIMAL(10, 2) NOT NULL,
    shipping_cost DECIMAL(10, 2) DEFAULT 50.00,
    description TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast product lookups
CREATE INDEX IF NOT EXISTS idx_products_code ON products(product_code);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

-- ============================================================
-- 2. CUSTOMER CARDS TABLE
-- Persistent customer profiles with region preferences
-- ============================================================
CREATE TABLE IF NOT EXISTS customer_cards (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    discord_user_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100),
    region VARCHAR(10) CHECK (region IN ('GCC', 'India', 'SEA')),
    company VARCHAR(200),
    notes TEXT,
    preferred_products TEXT[],
    last_interaction TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customer_cards_discord ON customer_cards(discord_user_id);

-- ============================================================
-- 3. CONVERSATIONS TABLE
-- Full conversation history per user
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    username VARCHAR(100),
    message TEXT NOT NULL,
    response TEXT NOT NULL,
    intent_parsed JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_time ON conversations(created_at DESC);

-- ============================================================
-- 4. QUOTES TABLE
-- Generated quotations with full breakdown
-- ============================================================
CREATE TABLE IF NOT EXISTS quotes (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    product_code VARCHAR(20) NOT NULL,
    product_name VARCHAR(200),
    region VARCHAR(10) NOT NULL CHECK (region IN ('GCC', 'India', 'SEA')),
    quantity INTEGER DEFAULT 1,
    base_price DECIMAL(10, 2) NOT NULL,
    final_price DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(5) NOT NULL,
    breakdown_json JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'accepted', 'rejected', 'expired')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days')
);

CREATE INDEX IF NOT EXISTS idx_quotes_user ON quotes(user_id);
CREATE INDEX IF NOT EXISTS idx_quotes_product ON quotes(product_code);

-- ============================================================
-- 5. BOT AUDIT LOG TABLE (CRITICAL)
-- Every action the bot performs is logged here
-- ============================================================
CREATE TABLE IF NOT EXISTS bot_audit_log (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    user_id VARCHAR(50),
    action_type VARCHAR(50) NOT NULL,
    input TEXT,
    output TEXT,
    metadata JSONB,
    warnings TEXT,
    duration_ms INTEGER,
    success BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_audit_action ON bot_audit_log(action_type);
CREATE INDEX IF NOT EXISTS idx_audit_time ON bot_audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user ON bot_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_warnings ON bot_audit_log(warnings) WHERE warnings IS NOT NULL;

-- ============================================================
-- 6. FOLLOW-UPS TABLE
-- Scheduled follow-up reminders
-- ============================================================
CREATE TABLE IF NOT EXISTS follow_ups (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    discord_channel_id VARCHAR(50),
    scheduled_time TIMESTAMPTZ NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'cancelled', 'failed')),
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_followups_status ON follow_ups(status, scheduled_time);
CREATE INDEX IF NOT EXISTS idx_followups_user ON follow_ups(user_id);

-- ============================================================
-- SEED DATA: Product Catalog
-- ============================================================
INSERT INTO products (product_code, category, constraints, base_price, shipping_cost, description) VALUES
    ('WTZ-1700', 'floor', 'above-waterline only', 450.00, 55.00, 'Floor expansion joint cover, aluminum profile, heavy traffic rated. Suitable for commercial buildings, malls, airports.'),
    ('WTZ-1800', 'floor', 'above-waterline only', 520.00, 60.00, 'Premium floor expansion joint cover, stainless steel, seismic rated. Designed for high-movement zones.'),
    ('WE-50',    'wall',  'interior only', 280.00, 40.00, 'Wall expansion joint cover, standard aluminum profile. For interior partition walls and drywall joints.'),
    ('WE-100',   'wall',  'none', 350.00, 45.00, 'Wall expansion joint cover, fire-rated, all environments. Suitable for interior and exterior applications.'),
    ('RE-200',   'roof',  'exterior only, UV resistant', 420.00, 50.00, 'Roof expansion joint cover, weather-sealed with UV-resistant membrane. For flat and pitched roofs.'),
    ('RE-300',   'roof',  'exterior only', 380.00, 48.00, 'Roof expansion joint cover, lightweight aluminum construction. Budget-friendly exterior roof solution.'),
    ('FE-75',    'floor', 'waterproof, submersible', 680.00, 65.00, 'Submersible floor expansion joint, pool and fountain rated. Designed for continuous water exposure.'),
    ('WTZ-2000', 'floor', 'above-waterline only, heavy-duty', 750.00, 70.00, 'Industrial floor expansion joint, warehouse and factory rated. Supports forklift and heavy machinery traffic.')
ON CONFLICT (product_code) DO NOTHING;

-- ============================================================
-- Row Level Security (RLS) — Optional for production
-- ============================================================
-- ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE bot_audit_log ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Updated_at trigger function
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_products_updated
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trigger_customer_cards_updated
    BEFORE UPDATE ON customer_cards
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
