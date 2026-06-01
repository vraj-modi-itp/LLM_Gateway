🛡️ AI Proxy Gateway & ReAct Agent Framework
An enterprise-grade, localized AI Proxy and Observability Gateway built to handle multi-agent orchestration, semantic caching, real-time telemetry, and Data Loss Prevention (PII Redaction). It sits seamlessly between your application layer (such as the included framework-free ReAct Agent) and foundation model APIs.

🏗️ System Architecture
The project decouples your core agent logic from governance, security, and financial management by enforcing a strict middleware ingress pipeline:

Plaintext
 Upstream Client (ReAct Agent) 
               │
               ▼ [Standard OpenAI JSON Format]
 ┌───────────────────────────────────────────────────────────┐
 │               FASTAPI API GATEWAY / PROXY                 │
 │                                                           │
 │  1. Security Scan 🛡️ (Microsoft Presidio)                 │
 │     └── Scrubs/Redacts PII data out of incoming messages │
 │                                                           │
 │  2. Semantic Cache Check ⚡ (Qdrant Vector DB)            │
 │     └── Matches embedding arrays via Cosine Similarity    │
 │         - Cache Hit  --> Instant local return (~80ms, $0) │
 │         - Cache Miss --> Continues down pipeline         │
 │                                                           │
 │  3. Forwarding Switchboard 🔀                             │
 │     └── Attaches master API Keys and calls Groq / Gemini  │
 └─────────────────────────────┬─────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼ [Async Background Task]    ▼ [Outbound Internet Request]
 ┌──────────────────────────────┐       ┌──────────────────────────────┐
 │    TELEMETRY & ANALYTICS     │       │      FOUNDATION MODEL APIs   │
 │                              │       │                              │
 │  [PostgreSQL Database]       │       │  [Groq API] (Llama 3)        │
 │   └── Persists transactional │       │                              │
 │       token & cost logs      │       │  [Gemini API] (Flash 2.5)    │
 │                              │       └──────────────────────────────┘
 │  [Streamlit Dashboard] 📊    │
 │   └── Live monitoring UI     │
 └──────────────────────────────┘
🛠️ Tech Stack & Library Inventory
Core Frameworks
fastapi & uvicorn: High-performance, asynchronous ASGI web server framework serving the central proxy routing engine.

streamlit: Used to build the real-time governance, token tracking, and cost visualization dashboard.

Security & Sanitization (DLP)
presidio-analyzer & presidio-anonymizer: Microsoft's enterprise Data Loss Prevention package, running local regex and NLP models to catch names, emails, phones, and secrets in prompt vectors before they leave the gateway.

Vector Intelligence & Semantic Memory
qdrant-client: Client driver communicating with our Dockerized Qdrant Vector database.

sentence-transformers: Generates local, dense vector representation layouts using the all-MiniLM-L6-v2 model to evaluate prompt semantic similarity weights.

Database, Serializers & Network
psycopg2-binary: Synchronous adapter enabling the Streamlit UI dashboard to aggregate database query rows.

httpx: Asynchronous HTTP client providing thread-safe outbound payload forwarding to Groq and Gemini.

requests: Synchronous networking adapter utilized inside the ReAct agent framework for clean, custom-header injection.

orjson: Ultra-fast JSON rendering engine used to maximize gateway processing limits and reduce processing overhead.

pandas: Handles telemetry log data-frames dynamically for graph and metric layouts inside Streamlit.

🚀 Local Installation & Quickstart
1. Clone the Workspace & Establish Virtual Environment
Bash
git clone <your-repository-url>
cd llm-proxy-gateway

# Set up local environment context
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
2. Configure Environment Context
Create a .env file inside your proxy workspace root directory:

Code snippet
# Infrastructure Credentials
GROQ_API_KEY=your_groq_api_token_here
GEMINI_API_KEY=your_gemini_api_token_here

# Local Container Network Bindings
POSTGRES_USER=proxy_user
POSTGRES_PASSWORD=proxy_password
POSTGRES_DB=proxy_db
3. Initialize Docker Dependencies
Spin up your localized, background persistence layers (PostgreSQL and Qdrant) via Docker Compose:

Bash
docker-compose up -d
4. Boot Up the Network Infrastructure
Open three independent terminal sessions inside your active venv:

Terminal 1 (Proxy Engine Backend):

Bash
uvicorn app.main:app --port 8000
*   **Terminal 2 (Analytics Dashboard Interface):**
    ```bash
    streamlit run dashboard.py --server.port 8501
Terminal 3 (Client Workspace - ReAct Agent Frontend):
Run your main application execution script or interface to trigger reasoning loops.

🧠 Advanced Agentic Cache Handling
A primary highlight of this architecture is its handling of Agentic Cache Traps. Because ReAct loop iterations build cumulative thought strings, traditional cache matching thresholds (~0.92) cause matching collisions, generating repeating loops.

To manage this, the system incorporates explicit Cache Control Headers:

Bypass Engine Matrix: The agent sets "x-bypass-cache": "true" to enforce live out-of-band execution calculations throughout individual thinking cycles.

Dynamic Matching: To implement caching across identical separate agent executions, change "x-bypass-cache" to "false" and increase the similarity strictly to 0.95 or 0.99 in your proxy server check (app/api/router.py). This prevents mid-loop step collisions while preserving the performance gains of exact task repeats.