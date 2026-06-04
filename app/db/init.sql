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