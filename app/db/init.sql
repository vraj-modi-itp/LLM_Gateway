-- Table 1: The core telemetry log for every LLM request
CREATE TABLE IF NOT EXISTS llm_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id VARCHAR(100) NOT NULL,
    target_provider VARCHAR(50) NOT NULL,
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
    entity_types TEXT[], -- e.g., ['EMAIL_ADDRESS', 'CREDIT_CARD']
    action_taken VARCHAR(50), -- e.g., 'REDACTED', 'BLOCKED'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table 3: Metadata for tracking duplicate prompt clusters over time
CREATE TABLE IF NOT EXISTS prompt_clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_count INT DEFAULT 1,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);