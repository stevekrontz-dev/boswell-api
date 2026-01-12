-- PHASE 3: AUDIT LOGGING
-- Comprehensive request logging for compliance and security monitoring
-- Run this AFTER Phase 2 (Encryption) is complete

-- PART 1: AUDIT_LOGS TABLE
CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  tenant_id UUID NOT NULL REFERENCES tenants(id),
  user_id UUID,                              -- Nullable until Phase 4 SSO
  api_key_id UUID,                           -- No FK constraint yet
  action VARCHAR(50) NOT NULL,
  resource_type VARCHAR(50) NOT NULL,
  resource_id VARCHAR(255),
  request_metadata JSONB DEFAULT '{}',
  response_status INTEGER NOT NULL,
  duration_ms INTEGER NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- PART 2: INDEXES FOR COMMON QUERY PATTERNS
-- Primary query: by tenant + time range
CREATE INDEX IF NOT EXISTS idx_audit_tenant_timestamp
  ON audit_logs(tenant_id, timestamp DESC);

-- Time-based queries across all tenants (admin)
CREATE INDEX IF NOT EXISTS idx_audit_timestamp
  ON audit_logs(timestamp DESC);

-- Filter by action type
CREATE INDEX IF NOT EXISTS idx_audit_action
  ON audit_logs(action);

-- Find all operations on a specific resource
CREATE INDEX IF NOT EXISTS idx_audit_resource
  ON audit_logs(resource_type, resource_id);

-- Tenant + action combination (common filter)
CREATE INDEX IF NOT EXISTS idx_audit_tenant_action
  ON audit_logs(tenant_id, action);

-- Partial index for errors only (status >= 400)
CREATE INDEX IF NOT EXISTS idx_audit_status_errors
  ON audit_logs(response_status)
  WHERE response_status >= 400;

-- PART 3: ROW LEVEL SECURITY
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_tenant_isolation ON audit_logs
  USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- PART 4: ACTION TYPES ENUM (for documentation/validation)
-- Valid actions:
-- COMMIT_CREATE, COMMIT_READ, BRANCH_CREATE, BRANCH_CHECKOUT,
-- BLOB_READ, SEARCH, LINK_CREATE, LINK_READ, REFLECT,
-- AUTH_SUCCESS, AUTH_FAILURE, API_KEY_CREATE, API_KEY_REVOKE,
-- AUDIT_QUERY, STARTUP, HEALTH_CHECK

-- PART 5: RETENTION POLICY SUPPORT
-- For future partitioning by month:
-- CREATE TABLE audit_logs_y2026m01 PARTITION OF audit_logs
--   FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

-- PART 6: VERIFICATION QUERIES
-- Check audit log count:
-- SELECT COUNT(*) FROM audit_logs;
--
-- Check logs by action:
-- SELECT action, COUNT(*) FROM audit_logs GROUP BY action ORDER BY COUNT(*) DESC;
--
-- Check error rate:
-- SELECT COUNT(*) FILTER (WHERE response_status >= 400) * 100.0 / COUNT(*) as error_rate FROM audit_logs;
