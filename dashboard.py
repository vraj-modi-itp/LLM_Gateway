import streamlit as st
import pandas as pd
import psycopg2

st.set_page_config(page_title="LLM Proxy Dashboard", layout="wide")

# Connect to the local PostgreSQL Docker container
@st.cache_resource
def get_db_connection():
    return psycopg2.connect("postgresql://proxy_user:proxy_password@localhost:5432/proxy_db")

conn = get_db_connection()

st.title("🛡️ AI Proxy Governance & Analytics")
st.markdown("Live telemetry and security monitoring for internal LLM traffic.")
st.divider()

# --- FETCH DATA ---
@st.cache_data(ttl=5) # Refresh data every 5 seconds
def load_data():
    df_tx = pd.read_sql("SELECT * FROM llm_transactions ORDER BY created_at DESC", conn)
    # Ensure cost is a float to avoid display errors
    df_tx['cost_usd'] = df_tx['cost_usd'].astype(float) 
    return df_tx

df = load_data()

if df.empty:
    st.info("No LLM transactions logged yet. Run your test script to generate traffic!")
    st.stop()

# --- TOP LEVEL METRICS ---
col1, col2, col3, col4 = st.columns(4)

total_requests = len(df)
cache_hits = len(df[df['is_cached'] == True])
savings_pct = (cache_hits / total_requests) * 100 if total_requests > 0 else 0
total_tokens = df['prompt_tokens'].sum() + df['completion_tokens'].sum()
total_cost = df['cost_usd'].sum()

col1.metric("Total Network Requests", total_requests)
col2.metric("Cache Hit Rate", f"{savings_pct:.1f}%")
col3.metric("Total Tokens Consumed", f"{total_tokens:,}")
col4.metric("Total API Cost", f"${total_cost:.5f}")

st.divider()

# --- VISUALIZATIONS ---
colA, colB = st.columns(2)

with colA:
    st.subheader("Token Consumption by Application")
    # Group tokens by app_id
    app_tokens = df.groupby('app_id')[['prompt_tokens', 'completion_tokens']].sum()
    st.bar_chart(app_tokens)

with colB:
    st.subheader("Cache Efficiency (Network vs. Local)")
    # Count of cached vs non-cached requests
    cache_counts = df['is_cached'].value_counts().rename(index={True: 'Cached (Local)', False: 'Miss (Network)'})
    st.bar_chart(cache_counts, color="#ff4b4b")

# --- RAW TRANSACTION LOG ---
st.subheader("Recent Transactions Log")
# Format the dataframe for cleaner viewing
display_df = df[['created_at', 'app_id', 'target_provider', 'latency_ms', 'cost_usd', 'is_cached']].copy()
display_df.rename(columns={
    'created_at': 'Timestamp',
    'app_id': 'Application',
    'target_provider': 'Provider',
    'latency_ms': 'Latency (ms)',
    'cost_usd': 'Cost ($)',
    'is_cached': 'Cache Hit'
}, inplace=True)

st.dataframe(display_df, use_container_width=True, hide_index=True)