-- Table 1: The core telemetry log for every LLM request
CREATE TABLE IF NOT EXISTS llm_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id VARCHAR(100) NOT NULL,
    target_provider VARCHAR(50) NOT NULL,
    routed_to VARCHAR(50), 
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    latency_ms FLOAT,
    cost_usd FLOAT DEFAULT 0.0,
    is_cached BOOLEAN DEFAULT FALSE,
    pi_was_run BOOLEAN DEFAULT TRUE,       -- ADDED
    pi_category VARCHAR(20) DEFAULT NULL,  -- ADDED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table 2: The security log for tracked PII violations
CREATE TABLE IF NOT EXISTS dlp_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID REFERENCES llm_transactions(id) ON DELETE CASCADE,
    entity_types TEXT[],
    action_taken VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table 3: Metadata for tracking duplicate prompt clusters over time
CREATE TABLE IF NOT EXISTS prompt_clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_count INT DEFAULT 1,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table 4: Tracks the intelligent routing logic and failovers
CREATE TABLE IF NOT EXISTS routing_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID REFERENCES llm_transactions(id) ON DELETE CASCADE,
    selected_provider VARCHAR(50),
    reason TEXT,
    fallback_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table 5: - Prompt Intelligence and Quality Metrics (Categories instead of Score)
CREATE TABLE IF NOT EXISTS prompt_quality_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID REFERENCES llm_transactions(id) ON DELETE CASCADE,
    original_prompt TEXT NOT NULL,
    enhanced_prompt TEXT,
    category VARCHAR(50) NOT NULL,
    is_enhanced BOOLEAN DEFAULT FALSE,
    detected_issues TEXT[],
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table 6: Budget Enforcement
CREATE TABLE IF NOT EXISTS app_budgets (
    app_id VARCHAR(100) PRIMARY KEY,
    monthly_token_limit INT DEFAULT 1000000,
    monthly_cost_limit_usd FLOAT DEFAULT 50.0,
    current_month_tokens INT DEFAULT 0,
    current_month_cost FLOAT DEFAULT 0.0,
    is_blocked BOOLEAN DEFAULT FALSE,
    pi_enabled BOOLEAN DEFAULT NULL,      -- ADDED
    last_reset_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table 7: Anomaly Alerts
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_type VARCHAR(50), -- 'COST_SPIKE', 'LATENCY_OUTLIER', 'DLP_SURGE'
    app_id VARCHAR(100),
    message TEXT,
    fired_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT FALSE
);

-- Table 8: Feature Flags for Prompt Intelligence
CREATE TABLE IF NOT EXISTS gateway_feature_flags (
    flag_name VARCHAR(100) PRIMARY KEY,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(100) DEFAULT 'system'
);

INSERT INTO gateway_feature_flags (flag_name, is_enabled, description)
VALUES ('prompt_intelligence_enabled', TRUE, 'Global master switch')
ON CONFLICT (flag_name) DO NOTHING;

-- Table 9: Dynamic Blacklist for Background Learning
CREATE TABLE IF NOT EXISTS dynamic_blacklist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_word VARCHAR(255) UNIQUE NOT NULL,
    mask_tag VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO dynamic_blacklist (original_word, mask_tag) 
VALUES ('Intuitive.AI', '[COMPANY_NAME]') 
ON CONFLICT DO NOTHING;

-- Audit table to capture stateless chat history across applications
CREATE TABLE IF NOT EXISTS audit_chat_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL,
    app_id VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    model_used VARCHAR(100) NOT NULL,
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    messages JSONB NOT NULL, -- Captures the entire history array sent by client
    response TEXT NOT NULL,  -- Captures the final answer returned by the gateway
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexing for fast retrieval during security audits and dashboard rendering
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_chat_history(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_app ON audit_chat_history(app_id);