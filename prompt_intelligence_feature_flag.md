Feature: Prompt Intelligence Dynamic Gateway Flag (Kill-Switch)
1. What We Implemented
We implemented a dynamic, zero-downtime feature flag system for the gateway's Prompt Intelligence (PI) SLM Engine.

Previously, the local SLM analyzed every inbound request, which added 200–800ms of latency per call. While necessary for human-agent traffic, this overhead is wasteful for trusted programmatic pipelines that already format prompts perfectly.

This upgrade introduces a live kill-switch that allows administrators to dynamically bypass the PI engine. It solves two core problems:

Cost & Latency Reduction: Trusted applications can skip the SLM, dropping routing latency from ~300ms down to ~70ms.

Incident Response: If the local SLM experiences an Out-Of-Memory (OOM) error or degrades, DevOps can disable it globally without restarting the FastAPI server or redeploying code.

2. How We Did It (Architecture)
The architecture was designed with a strict focus on zero-latency overhead. It consists of three primary components:

The Database Layer (PostgreSQL): We introduced a new gateway_feature_flags table to handle the global master switch, and appended a pi_enabled column to the existing app_budgets table to allow per-app granular overrides. Telemetry tables were also updated to log bypassed transactions under a new SKIPPED category.

The Brain (In-Memory TTL Cache): Reading from PostgreSQL on every LLM request would create a massive bottleneck. Instead, app/services/flag_resolver.py pulls the flag states and caches them in a local dictionary with a 30-second TTL (Time-To-Live). This guarantees sub-millisecond flag resolution while ensuring policy changes take effect within 30 seconds.

The Control Surface (Admin API): We exposed secure endpoints in app/api/admin_router.py. Protected by a static x-admin-key header, these endpoints allow administrators to toggle the database state via standard HTTP requests.

3. How to Run and Test Locally
Prerequisites
Before starting, ensure your .env file contains the new admin security key:

Code snippet
ADMIN_API_KEY=your_super_secret_admin_password
Step 1: Boot Infrastructure & Migrate Database
Start the Docker containers (Postgres/Qdrant) and run the migration scripts to generate the new tables.

Bash
docker-compose up -d
python setup_db.py
python migrateDb.py
Step 2: Start the Gateway
Launch the FastAPI application:

Bash
uvicorn app.main:app --reload --port 8000
Step 3: Run the Bypass Simulation
Open a second terminal to run the test suite.

A. Test Baseline (PI Engine Active)
Send a standard prompt. Notice the higher latency as it routes through the SLM.

Bash
curl -X POST "http://localhost:8000/v1/chat/completions" -H "Content-Type: application/json" -H "x-app-id: test-app-1" -H "x-bypass-cache: true" -d "{\"model\": \"gemini-1.5-flash\", \"messages\": [{\"role\": \"user\", \"content\": \"Explain quantum computing in one sentence.\"}]}"
B. Trigger the Global Kill-Switch
Act as an administrator to disable the PI Engine. Ensure you use the exact ADMIN_API_KEY defined in your .env.

Bash
curl -X POST "http://localhost:8000/admin/flags/prompt_intelligence_enabled" -H "Content-Type: application/json" -H "x-admin-key: your_super_secret_admin_password" -d "{\"is_enabled\": false, \"updated_by\": \"Local Dev\"}"
C. Wait 30 Seconds & Re-Test
Wait 30 seconds for the TTL cache to expire, then run the exact same chat request from Step A. You will see a massive drop in latency, and your database logs will show the transaction's PI Category as SKIPPED.