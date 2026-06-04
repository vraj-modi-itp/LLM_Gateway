🛡️ AI Proxy Gateway (LLM Proxy)

An enterprise-style FastAPI proxy that mediates between local agents and foundation model providers. It enforces PII redaction (Presidio), provides a Qdrant-backed semantic cache (sentence-transformers), forwards requests to configured providers (Groq or Gemini), and logs telemetry to PostgreSQL with a Streamlit dashboard.

**Features**
- PII scanning and anonymization using Microsoft Presidio.
- Local semantic caching with Qdrant and `all-MiniLM-L6-v2` embeddings.
- Provider switchboard: forward to Groq or Gemini with API-key injection.
- Asynchronous telemetry logging to PostgreSQL and a Streamlit dashboard.

**Repository Structure (high level)**
- `app/main.py` — FastAPI application and startup lifecycle.
- `app/api/router.py` — Proxy endpoint (`POST /v1/chat/completions`).
- `app/services/dlp.py` — Presidio scanning and anonymizer.
- `app/services/cache.py` — Qdrant client and embedding-based cache.
- `app/services/telemetry.py` — Async telemetry writes to Postgres.
- `dashboard.py` — Streamlit analytics UI.
- `app/core/setup_model.py` — Script to download and cache the embedding model.
- `test_proxy.py` — Small test runner that exercises cache and DLP flows.
- `db/init.sql` — SQL to create the `llm_transactions` table (apply to Postgres).

## Requirements
- Python 3.9+
- Docker & Docker Compose (for Postgres and Qdrant)
- Recommended: create a virtual environment

## Quickstart (local)

1. Clone and create a venv

```bash
git clone <your-repository-url>
cd LLM_Gateway
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Create a `.env` file in the project root (example):

```
GROQ_API_KEY=
GEMINI_API_KEY=
POSTGRES_USER=proxy_user
POSTGRES_PASSWORD=proxy_password
POSTGRES_DB=proxy_db
POSTGRES_PORT=5433
PHOENIX_API_KEY=
PHOENIX_COLLECTOR_ENDPOINT=
# --- ALERTING & NOTIFICATIONS ---
# Create a free Slack Webhook (https://api.slack.com/messaging/webhooks)
SLACK_WEBHOOK_URL=
 
# Email Notification Settings (e.g., using Gmail App Passwords)
RESEND_API_KEY=
RESEND_FROM_EMAIL=
ALERT_RECIPIENT_EMAIL=
```

3. Start Docker infra (Postgres + Qdrant):

```bash
docker-compose up -d
```

4. Initialize the database schema (apply `db/init.sql`):

```bash
# using psql (make sure credentials match your .env/docker-compose)
psql -h localhost -U proxy_user -d proxy_db -f db/init.sql
```

5. (Optional) Download and cache the embedding model for faster startup:

```bash
python app/core/setup_model.py
```

6. Run the proxy and dashboard in separate terminals:

```bash
# Terminal 1: API proxy
uvicorn app.main:app --port 8000 --reload

# Terminal 2: Streamlit dashboard
streamlit run dashboard.py --server.port 8501
```

7. Exercise the proxy (example using the included test script):

```bash
python test_proxy.py
```

Or use curl / HTTP client:

```bash
curl -X POST "http://localhost:8000/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -H "x-app-id: test-client" \
    -H "x-target-provider: groq" \
    -d '{"model":"proxy-model","messages":[{"role":"user","content":"Say hello"}] }'
```

## How requests flow
1. DLP: incoming messages are scanned and redacted via Presidio.
2. Semantic cache: the user's most recent prompt is embedded and queried against Qdrant; close matches return a cached assistant response.
3. Forwarding: on cache miss (or when `x-bypass-cache: true`), the proxy forwards to the selected provider with the appropriate API key.
4. Telemetry: the request metrics are written asynchronously to Postgres and visualized in Streamlit.

## Important notes & troubleshooting
- The telemetry DB DSN in `app/services/telemetry.py` is set to `postgresql://proxy_user:proxy_password@localhost:5432/proxy_db`. Ensure your `.env` and `docker-compose` use the same credentials or update the code.
- Qdrant is expected at `localhost:6333` by default.
- Presidio uses spaCy `en_core_web_sm`; if you see errors, run:

```bash
python -m spacy download en_core_web_sm
```

- If embeddings are slow on first startup, run `python app/core/setup_model.py` to cache the model locally under `./data/models`.
- On Windows PowerShell, if activation is blocked, run the PowerShell activation script or use `cmd` activation. Avoid running multiple blocking shell tasks in parallel.

## Files of interest
- `app/api/router.py` — main proxy logic and cache bypass header handling.
- `app/services/cache.py` — Qdrant client and cache logic.
- `app/services/dlp.py` — DLP scanning and anonymization.
- `dashboard.py` — Streamlit dashboard.
- `test_proxy.py` — basic integration tests for cache and DLP flows.

## Want help?
If you'd like, I can:
- Add a `Makefile` or Powershell `run.ps1` for convenience.
- Create a small test harness that runs on CI.
- Commit these README updates to a new branch and push it for you.

-----
## Expanded Features & Design

### Stack (open-source / recommended)
- Proxy: Python + FastAPI (async, mirrors OpenAI API contract)
- PII/DLP: Microsoft Presidio (detect & redact sensitive data)
- Embeddings: `sentence-transformers/all-MiniLM-L6-v2` (HuggingFace)
- Vector store: Qdrant (self-hosted) — optional `pgvector` alternative
- Cache: semantic cache implemented with Qdrant (Redis optional)
- Database: PostgreSQL for structured transaction logs
- Dashboard: Streamlit (current) — can swap to Grafana or React
- Infra: Docker Compose for Postgres and Qdrant

### Proxy pipeline (sequential; stages can short-circuit)
1. Context logger — extract `x-app-id`, `x-target-provider`, `x-request-type`, and `session_id` headers.
2. DLP scanner — run Presidio; on high-confidence PII either redact and continue or block and return 403; log to `dlp_incidents`.
3. Similarity check — embed the last user prompt and query Qdrant. If similarity > configured threshold: return cached response. Near-duplicates can be flagged for analytics.
4. LLM forward — call the selected provider (Groq/Gemini/Ollama) with proper API key or org/shared key.
5. Telemetry capture — async write: latency, tokens, estimated cost, cache flag, and store embedding + response in the vector store.

### Database schema (core tables)
- `llm_transactions(id, app_id, model, prompt_hash, prompt_tokens, completion_tokens, latency_ms, cost_usd, is_cached, created_at)`
- `dlp_incidents(id, transaction_id, entity_types, action, created_at)`
- `prompt_clusters(id, centroid_embedding, member_ids, label, first_seen, last_seen)`
- `routing_decisions(transaction_id, selected_provider, reason, fallback_used)`
- `alerts(id, alert_type, app_id, message, fired_at, acknowledged)`

### Analytics dashboard (suggested views)
1. Token consumption by application (bar chart, selectable interval)
2. Request volume & cache hit rate over time (line chart)
3. PII incident log and entity breakdown (table + pie)
4. Top duplicate/clustered prompts with cost-saving estimates
5. Cost projection and optimization recommendations

### Dynamic Threshold Engine (recommended enhancement)
- Add header `x-request-type` (e.g., `agent`) and `session_id` to requests.
- Use per-traffic-type thresholds: e.g., `AGENT_SIMILARITY_THRESHOLD=0.99` in `.env` for agent flows.
- When querying Qdrant during active sessions, filter out points where `session_id` == current session to avoid intra-run cache hits.
- Update `app/services/cache.py` to accept `threshold` and `payload_filter` parameters and use them in queries.

### Team tasks (high level)
- Vishnu — Prompt Intelligence & Optimization: build `prompt_analyzer.py` to score prompt quality and optionally rewrite weak prompts. Store scores in `prompt_quality_scores` and also stores enhanced prompt in 'enhanced_prompt' and surface in dashboard.
- Sumit — Intelligent Multi-Provider Router: implement `router.py` to select providers by cost/latency, and implement fallback retry logic. Add optional Ollama routing for low-risk prompts.
- Rahul — Observability & Alerting: build `anomaly_detector.py` scheduled job to detect cost/latency/DLP spikes, write `alerts`, and notify via Slack/email. Add `app_budgets` enforcement that can cause the proxy to return HTTP 429 when an app exceeds its budget.
- Vraj — Core Gateway Architecture & Semantic Memory: build the dual-ingress FastAPI pipeline supporting both OpenAI and Google ADK payloads, implement Qdrant vector caching with dynamic thresholds and agent session isolation, and streamlit network and cost telemetry section



-----
