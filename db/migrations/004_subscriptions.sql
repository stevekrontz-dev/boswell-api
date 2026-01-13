-- 004_subscriptions.sql
-- Subscriptions table for Stripe billing
-- Owner: CC2
-- Workstream: W2P2
-- Note: Coordinated with CC1 (api_keys is 003)

-- Subscriptions table
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stripe_subscription_id VARCHAR(255) UNIQUE,
    stripe_customer_id VARCHAR(255),
    plan_id VARCHAR(50) NOT NULL DEFAULT 'free',
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    canceled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT subscriptions_tenant_unique UNIQUE (tenant_id)
);

-- Index for Stripe lookups
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_sub ON subscriptions(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_cust ON subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);

-- Add stripe_customer_id to tenants if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'tenants' AND column_name = 'stripe_customer_id'
    ) THEN
        ALTER TABLE tenants ADD COLUMN stripe_customer_id VARCHAR(255);
        CREATE INDEX idx_tenants_stripe_customer ON tenants(stripe_customer_id);
    END IF;
END $$;

-- Usage tracking table for enforcing limits
CREATE TABLE IF NOT EXISTS usage_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    metric VARCHAR(50) NOT NULL,  -- 'commits', 'storage_bytes', 'branches'
    value BIGINT NOT NULL DEFAULT 0,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT usage_tracking_unique UNIQUE (tenant_id, metric, period_start)
);

CREATE INDEX IF NOT EXISTS idx_usage_tracking_tenant ON usage_tracking(tenant_id);
CREATE INDEX IF NOT EXISTS idx_usage_tracking_period ON usage_tracking(period_start, period_end);

-- RLS policies for subscriptions
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY subscriptions_tenant_isolation ON subscriptions
    USING (tenant_id::text = current_setting('app.current_tenant', true));

-- RLS for usage_tracking
ALTER TABLE usage_tracking ENABLE ROW LEVEL SECURITY;

CREATE POLICY usage_tracking_tenant_isolation ON usage_tracking
    USING (tenant_id::text = current_setting('app.current_tenant', true));

-- Function to increment usage
CREATE OR REPLACE FUNCTION increment_usage(
    p_tenant_id UUID,
    p_metric VARCHAR(50),
    p_increment BIGINT DEFAULT 1
) RETURNS BIGINT AS $$
DECLARE
    v_period_start DATE;
    v_period_end DATE;
    v_new_value BIGINT;
BEGIN
    -- Get current billing period (first of month to last of month)
    v_period_start := DATE_TRUNC('month', CURRENT_DATE)::DATE;
    v_period_end := (DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month' - INTERVAL '1 day')::DATE;

    -- Upsert usage record
    INSERT INTO usage_tracking (tenant_id, metric, value, period_start, period_end)
    VALUES (p_tenant_id, p_metric, p_increment, v_period_start, v_period_end)
    ON CONFLICT (tenant_id, metric, period_start)
    DO UPDATE SET
        value = usage_tracking.value + p_increment,
        updated_at = NOW()
    RETURNING value INTO v_new_value;

    RETURN v_new_value;
END;
$$ LANGUAGE plpgsql;

-- Function to get current usage
CREATE OR REPLACE FUNCTION get_current_usage(
    p_tenant_id UUID,
    p_metric VARCHAR(50)
) RETURNS BIGINT AS $$
DECLARE
    v_period_start DATE;
    v_value BIGINT;
BEGIN
    v_period_start := DATE_TRUNC('month', CURRENT_DATE)::DATE;

    SELECT value INTO v_value
    FROM usage_tracking
    WHERE tenant_id = p_tenant_id
      AND metric = p_metric
      AND period_start = v_period_start;

    RETURN COALESCE(v_value, 0);
END;
$$ LANGUAGE plpgsql;
