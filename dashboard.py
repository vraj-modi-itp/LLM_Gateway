import streamlit as st
import pandas as pd
import psycopg2

st.set_page_config(page_title="LLM Proxy Dashboard", layout="wide")

@st.cache_resource
def get_db_connection():
    # Connects to our local PostgreSQL Docker container on port 5433
    return psycopg2.connect("postgresql://proxy_user:proxy_password@localhost:5433/proxy_db")

conn = get_db_connection()

st.title("🛡️ AI Proxy Governance & Analytics")
st.markdown("Live telemetry, cost enforcement, and security monitoring for internal LLM traffic.")
st.divider()

# --- FETCH DATA ---
# ttl=2 means Streamlit will refresh the data every 2 seconds if the user interacts with the page
@st.cache_data(ttl=2)
def load_data():
    # 1. Standard Telemetry
    try:
        df_tx = pd.read_sql("SELECT * FROM llm_transactions ORDER BY created_at DESC", conn)
        if not df_tx.empty:
            df_tx['cost_usd'] = df_tx['cost_usd'].astype(float) 
    except:
        df_tx = pd.DataFrame()

    # 2. Prompt Quality (Updated for Category Logic)
    try:
        df_quality = pd.read_sql("""
            SELECT t.app_id, t.created_at, p.original_prompt, p.enhanced_prompt, p.category, p.is_enhanced, p.detected_issues 
            FROM prompt_quality_scores p
            JOIN llm_transactions t ON p.transaction_id = t.id
            ORDER BY t.created_at DESC
        """, conn)
    except:
        df_quality = pd.DataFrame()

    # 3. App Budgets (Active Governance)
    try:
        df_budgets = pd.read_sql("SELECT * FROM app_budgets ORDER BY current_month_cost DESC", conn)
    except:
        df_budgets = pd.DataFrame()

    # 4. Instant Anomaly & Security Alerts
    try:
        df_alerts = pd.read_sql("SELECT * FROM alerts ORDER BY fired_at DESC LIMIT 50", conn)
    except:
        df_alerts = pd.DataFrame()

    return df_tx, df_quality, df_budgets, df_alerts

df, df_quality, df_budgets, df_alerts = load_data()

if df.empty and df_alerts.empty:
    st.info("No LLM transactions or alerts logged yet. Run your test script to generate traffic!")
    st.stop()

# --- TABBED LAYOUT ---
tab1, tab2, tab3 = st.tabs(["🌐 Network & Cost Telemetry", "🧠 Prompt Intelligence", "⚖️ Governance & Budgets"])

# ---------------------------------------------------------
# TAB 1: NETWORK & COST
# ---------------------------------------------------------
with tab1:
    col1, col2, col3, col4 = st.columns(4)
    total_requests = len(df)
    cache_hits = len(df[df['is_cached'] == True]) if not df.empty else 0
    savings_pct = (cache_hits / total_requests) * 100 if total_requests > 0 else 0
    total_tokens = df['prompt_tokens'].sum() + df['completion_tokens'].sum() if not df.empty else 0
    total_cost = df['cost_usd'].sum() if not df.empty else 0.0

    col1.metric("Total Network Requests", total_requests)
    col2.metric("Cache Hit Rate", f"{savings_pct:.1f}%")
    col3.metric("Total Tokens Consumed", f"{total_tokens:,}")
    col4.metric("Total API Cost", f"${total_cost:.5f}")
    st.divider()

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Token Consumption by Application")
        if not df.empty:
            app_tokens = df.groupby('app_id')[['prompt_tokens', 'completion_tokens']].sum()
            st.bar_chart(app_tokens)

    with colB:
        st.subheader("Cache Efficiency (Network vs. Local)")
        if not df.empty:
            cache_counts = df['is_cached'].value_counts().rename(index={True: 'Cached (Local)', False: 'Miss (Network)'})
            st.bar_chart(cache_counts, color="#ff4b4b")

    st.subheader("Recent Transactions Log")
    if not df.empty:
        # Combine prompt and completion tokens for a clean single-column view
        df['total_tokens'] = df['prompt_tokens'] + df['completion_tokens']
        
        display_df = df[['created_at', 'app_id', 'target_provider', 'total_tokens', 'latency_ms', 'cost_usd', 'is_cached']].copy()
        display_df.rename(columns={
            'created_at': 'Timestamp',
            'app_id': 'Application',
            'target_provider': 'Provider',
            'total_tokens': 'Total Tokens',
            'latency_ms': 'Latency (ms)',
            'cost_usd': 'Cost ($)',
            'is_cached': 'Cache Hit'
        }, inplace=True)
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# TAB 2: PROMPT INTELLIGENCE
# ---------------------------------------------------------
with tab2:
    st.subheader("Prompt Quality Categorization & Auto-Enhancement")
    st.markdown("Analyzes inbound queries. Rejects spam (Insufficient), automatically injects context for mid-tier prompts (Needs Context), and allows high-quality prompts to pass untouched (Optimal).")
    
    if df_quality.empty:
        st.info("No prompt quality data recorded yet.")
    else:
        # Categorical break down
        optimal_count = len(df_quality[df_quality['category'] == 'OPTIMAL'])
        enhanced_count = len(df_quality[df_quality['category'] == 'NEEDS_CONTEXT'])
        rejected_count = len(df_quality[df_quality['category'] == 'INSUFFICIENT'])
        
        col_q1, col_q2, col_q3 = st.columns(3)
        col_q1.metric("Optimal (Passed Directly)", optimal_count)
        col_q2.metric("Needs Context (Auto-Enhanced)", enhanced_count)
        col_q3.metric("Insufficient (Rejected)", rejected_count)
        
        st.divider()
        st.subheader("Intelligence Logging")
        
        display_quality_df = df_quality[['created_at', 'app_id', 'category', 'is_enhanced', 'original_prompt', 'enhanced_prompt']].copy()
        display_quality_df['enhanced_prompt'] = display_quality_df.apply(
            lambda x: x['enhanced_prompt'] if x['is_enhanced'] else "[No Action Needed / Intercepted]", axis=1
        )
        display_quality_df.rename(columns={
            'created_at': 'Timestamp',
            'app_id': 'App ID',
            'category': 'Category',
            'is_enhanced': 'Enhanced?',
            'original_prompt': 'Original Prompt',
            'enhanced_prompt': 'Action / Enhanced Output'
        }, inplace=True)
        
        st.dataframe(display_quality_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# TAB 3: GOVERNANCE & BUDGETS
# ---------------------------------------------------------
with tab3:
    st.subheader("Active Budget Enforcement")
    st.markdown("Applications exceeding these hard limits are automatically blocked at the proxy layer (HTTP 429).")
    
    if df_budgets.empty:
        st.info("No application budgets registered yet.")
    else:
        for _, row in df_budgets.iterrows():
            app_name = row['app_id']
            spent = float(row['current_month_cost'])
            limit = float(row['monthly_cost_limit_usd'])
            is_blocked = row['is_blocked']
            
            pct_used = min(spent / limit, 1.0) if limit > 0 else 1.0
            status_icon = "🔴 BLOCKED (429 ENFORCED)" if is_blocked else "🟢 ACTIVE"
            
            st.markdown(f"**{app_name}** — {status_icon}")
            st.progress(pct_used, text=f"Spent: ${spent:.4f} / Limit: ${limit:.2f} ({pct_used*100:.1f}%)")
            st.markdown("<br>", unsafe_allow_html=True) 

    st.divider()
    
    st.subheader("🚨 Incident & Compliance Monitoring Stream")
    st.markdown("Live feed of cost spikes, rate limit breaches, and DLP (Data Loss Prevention) triggers caught by the gateway.")
    
    if df_alerts.empty:
        st.success("All clear! No anomalies detected recently.")
    else:
        display_alerts = df_alerts[['fired_at', 'alert_type', 'app_id', 'message']].copy()
        display_alerts.rename(columns={
            'fired_at': 'Timestamp',
            'alert_type': 'Alert Type',
            'app_id': 'Application',
            'message': 'Anomaly Details'
        }, inplace=True)
        st.dataframe(display_alerts, use_container_width=True, hide_index=True)