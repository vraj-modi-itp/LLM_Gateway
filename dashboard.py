import streamlit as st
import pandas as pd
import json
from sqlalchemy import create_engine

st.set_page_config(page_title="LLM Proxy Dashboard", layout="wide")

# --- SQLALCHEMY ENGINE SETUP ---
@st.cache_resource
def get_db_engine():
    return create_engine("postgresql://proxy_user:proxy_password@localhost:5433/proxy_db")

engine = get_db_engine()

st.title("🛡️ AI Proxy Governance & Analytics")
st.markdown("Live telemetry, active governance, and asynchronous background intelligence.")
st.divider()

# --- FETCH DATA ---
@st.cache_data(ttl=2)
def load_data():
    try:
        df_tx = pd.read_sql("SELECT * FROM llm_transactions ORDER BY created_at DESC", engine)
        if not df_tx.empty:
            df_tx['cost_usd'] = df_tx['cost_usd'].astype(float) 
    except:
        df_tx = pd.DataFrame()

    try:
        df_quality = pd.read_sql("""
            SELECT t.app_id, COALESCE(t.created_at, p.created_at) as created_at, 
                   p.original_prompt, p.enhanced_prompt, p.category, p.is_enhanced, p.detected_issues 
            FROM prompt_quality_scores p
            LEFT JOIN llm_transactions t ON p.transaction_id = t.id
            ORDER BY COALESCE(t.created_at, p.created_at) DESC
        """, engine)
    except:
        df_quality = pd.DataFrame()

    try:
        df_budgets = pd.read_sql("SELECT * FROM app_budgets ORDER BY current_month_cost DESC", engine)
    except:
        df_budgets = pd.DataFrame()

    try:
        df_alerts = pd.read_sql("SELECT * FROM alerts ORDER BY fired_at DESC LIMIT 50", engine)
    except:
        df_alerts = pd.DataFrame()

    try:
        df_audit = pd.read_sql("SELECT * FROM audit_chat_history ORDER BY created_at DESC LIMIT 200", engine)
    except:
        df_audit = pd.DataFrame()

    try:
        df_blacklist = pd.read_sql("SELECT * FROM dynamic_blacklist ORDER BY created_at DESC", engine)
    except:
        df_blacklist = pd.DataFrame()

    return df_tx, df_quality, df_budgets, df_alerts, df_audit, df_blacklist

df, df_quality, df_budgets, df_alerts, df_audit, df_blacklist = load_data()

if df.empty and df_alerts.empty and df_audit.empty:
    st.info("No LLM transactions, alerts, or audit logs recorded yet. Run your test scripts to generate traffic!")
    st.stop()

# --- TABBED LAYOUT ---
tab1, tab2, tab3, tab4 = st.tabs(["🌐 Network & Cost Telemetry", "🧠 Prompt Intelligence", "⚖️ Governance & Security", "🕵️ Session Explorer"])

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
    st.subheader("Semantic Categorization & Background Optimization")
    st.markdown("Prompts are instantly categorized via vector centroids (0ms latency). Sparse 'Draft' prompts are sent to the background worker to generate highly optimized suggestions for the user.")
    
    if df_quality.empty:
        st.info("No prompt quality data recorded yet.")
    else:
        # We still count the raw metrics directly from the database for accuracy
        prime_count = len(df_quality[df_quality['category'] == 'PRIME'])
        draft_count = len(df_quality[df_quality['category'] == 'DRAFT'])
        
        col_q1, col_q2 = st.columns(2)
        col_q1.metric("🌟 Prime Prompts (High-Fidelity)", prime_count, help="Passed straight through perfectly.")
        col_q2.metric("📝 Draft Prompts (Sparse)", draft_count, help="Offloaded to background for optimization.")
        
        st.divider()
        st.subheader("Async Optimization Log")
        
        display_quality_df = df_quality[['created_at', 'category', 'is_enhanced', 'original_prompt', 'enhanced_prompt']].copy()
        
        # FIX: The Dashboard "Sunglasses"
        # We keep PRIME prompts visible, but we completely HIDE DRAFT prompts until Ollama finishes its job (is_enhanced == True)
        display_quality_df = display_quality_df[
            (display_quality_df['category'] == 'PRIME') | 
            ((display_quality_df['category'] == 'DRAFT') & (display_quality_df['is_enhanced'] == True))
        ].copy()
        
        # Clean up duplicates just in case
        display_quality_df = display_quality_df.sort_values('created_at', ascending=False).drop_duplicates(subset=['original_prompt', 'category'])
        
        display_quality_df.rename(columns={
            'created_at': 'Timestamp',
            'category': 'Category',
            'original_prompt': 'Original Request',
            'enhanced_prompt': 'Background Suggestion (For Next Time)'
        }, inplace=True)
        
        # Hide the boolean flag from the user interface
        display_quality_df.drop(columns=['is_enhanced'], inplace=True, errors='ignore')
        
        st.dataframe(display_quality_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# TAB 3: GOVERNANCE & SECURITY
# ---------------------------------------------------------
with tab3:
    st.subheader("🔒 Dynamic DLP Blacklist (Aho-Corasick Fast-Map)")
    st.markdown("The background AI continuously scans traffic for unmapped entities and adds them here. The proxy masks these at runtime in O(n) time.")
    
    if df_blacklist.empty:
        st.info("No custom entities learned yet.")
    else:
        col_b1, col_b2 = st.columns([1, 2])
        with col_b1:
            st.metric("Total Learned Entities", len(df_blacklist))
        with col_b2:
            display_bl = df_blacklist[['created_at', 'original_word', 'mask_tag']].copy()
            st.dataframe(display_bl, use_container_width=True, hide_index=True)
    
    st.divider()

    st.subheader("Active Budget Enforcement")
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
    
    st.subheader("🚨 Incident & Compliance Alerts")
    if df_alerts.empty:
        st.success("All clear! No anomalies detected recently.")
    else:
        display_alerts = df_alerts[['fired_at', 'alert_type', 'app_id', 'message']].copy()
        st.dataframe(display_alerts, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# TAB 4: SESSION EXPLORER (AUDIT)
# ---------------------------------------------------------
with tab4:
    st.subheader("🕵️ Centralized Audit Log")
    if df_audit.empty:
        st.info("No audit logs available.")
    else:
        session_ids = df_audit['session_id'].unique()
        selected_session = st.selectbox("Select a Session ID to replay:", session_ids)
        
        session_data = df_audit[df_audit['session_id'] == selected_session].iloc[0]
        
        colA, colB, colC = st.columns(3)
        colA.metric("Application ID", session_data['app_id'])
        colB.metric("Routing Provider", session_data['provider'].upper())
        colC.metric("Model Executed", session_data['model_used'])
        st.divider()
        
        try:
            msg_data = session_data['messages']
            messages_array = msg_data if isinstance(msg_data, list) else json.loads(msg_data)
        except Exception as e:
            messages_array = []
            
        for msg in messages_array:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            avatar = "👤" if role == "user" else "⚙️" if role == "system" else "🤖"
            with st.chat_message(role, avatar=avatar):
                st.markdown(content)
                
        with st.chat_message("assistant", avatar="🛡️"):
            st.markdown(f"**Gateway Output (Final Turn):**\n\n{session_data['response']}")