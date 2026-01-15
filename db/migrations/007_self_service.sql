-- Migration 007: Self-service onboarding columns
-- Owner: CC
-- Task: Self-service wiring - zero-touch onboarding

-- Add columns to users table for self-service onboarding
ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending_payment';
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan VARCHAR(50) DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS api_key_encrypted TEXT;

-- Index for Stripe customer lookup (for subscription updates)
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users(stripe_customer_id);

-- Comments
COMMENT ON COLUMN users.status IS 'User status: pending_payment, active, suspended';
COMMENT ON COLUMN users.stripe_customer_id IS 'Stripe customer ID for billing';
COMMENT ON COLUMN users.stripe_subscription_id IS 'Active Stripe subscription ID';
COMMENT ON COLUMN users.plan IS 'Current plan: free, pro, team';
COMMENT ON COLUMN users.api_key_encrypted IS 'Encrypted API key for dashboard display (Fernet encrypted)';
