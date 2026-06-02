import streamlit as st
import pandas as pd
import psycopg2

st.set_page_config(page_title="LLM Proxy Dashboard", layout="wide")

@st.cache_resource
def get_db_connection():
    return psycopg2.connect("postgresql://proxy_user:proxy_password@localhost:5433/proxy_db")

conn = get_db_connection()

st.title("🛡️ AI Proxy Governance & Analytics")
st.markdown("Live telemetry and security monitoring for internal LLM traffic.")
st.divider()

# --- FETCH DATA ---
@st.cache_data(ttl=5)
def load_data():
    df_tx = pd.read_sql("SELECT * FROM llm_transactions ORDER BY created_at DESC", conn)
    df_tx['cost_usd'] = df_tx['cost_usd'].astype(float) 
    
    # NEW: Fetch Prompt Quality Data
    df_quality = pd.read_sql("""
        SELECT t.app_id, t.created_at, p.original_prompt, p.enhanced_prompt, p.score, p.is_enhanced, p.detected_issues 
        FROM prompt_quality_scores p
        JOIN llm_transactions t ON p.transaction_id = t.id
        ORDER BY t.created_at DESC
    """, conn)
    
    return df_tx, df_quality

df, df_quality = load_data()

if df.empty:
    st.info("No LLM transactions logged yet. Run your test script to generate traffic!")
    st.stop()

# --- TABBED LAYOUT ---
tab1, tab2 = st.tabs(["🌐 Network & Cost Telemetry", "🧠 Prompt Intelligence"])

with tab1:
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

    colA, colB = st.columns(2)
    with colA:
        st.subheader("Token Consumption by Application")
        app_tokens = df.groupby('app_id')[['prompt_tokens', 'completion_tokens']].sum()
        st.bar_chart(app_tokens)

    with colB:
        st.subheader("Cache Efficiency (Network vs. Local)")
        cache_counts = df['is_cached'].value_counts().rename(index={True: 'Cached (Local)', False: 'Miss (Network)'})
        st.bar_chart(cache_counts, color="#ff4b4b")

    st.subheader("Recent Transactions Log")
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

with tab2:
    st.subheader("Prompt Quality & Auto-Enhancement")
    st.markdown("Analyzes inbound queries for structural integrity and auto-injects context when instructions fall below the quality threshold.")
    
    if df_quality.empty:
        st.info("No prompt quality data recorded yet.")
    else:
        avg_score = df_quality['score'].mean()
        enhanced_count = df_quality['is_enhanced'].sum()
        
        col_q1, col_q2 = st.columns(2)
        col_q1.metric("Average Inbound Quality Score", f"{avg_score:.1f} / 100")
        col_q2.metric("Prompts Auto-Enhanced", f"{enhanced_count}")
        
        st.divider()
        st.subheader("Quality Log")
        
        # Display the prompt data clearly
        display_quality_df = df_quality[['created_at', 'app_id', 'score', 'is_enhanced', 'original_prompt', 'enhanced_prompt']].copy()
        
        # Ensure 'No Change' is explicitly shown if not enhanced
        display_quality_df['enhanced_prompt'] = display_quality_df.apply(
            lambda x: x['enhanced_prompt'] if x['is_enhanced'] else "[No Change Needed - Passed Threshold]", axis=1
        )
        
        display_quality_df.rename(columns={
            'created_at': 'Timestamp',
            'app_id': 'App ID',
            'score': 'Score',
            'is_enhanced': 'Enhanced?',
            'original_prompt': 'Original Prompt',
            'enhanced_prompt': 'Enhanced Output'
        }, inplace=True)
        
        st.dataframe(display_quality_df, use_container_width=True, hide_index=True)