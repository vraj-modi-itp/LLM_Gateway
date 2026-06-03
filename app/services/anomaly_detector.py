import os
import asyncio
import asyncpg
import httpx
import resend
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pandas as pd
from fpdf import FPDF
from dotenv import load_dotenv

# Force load environment variables
load_dotenv()

DB_DSN = "postgresql://proxy_user:proxy_password@localhost:5433/proxy_db"
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Initialize Resend
resend.api_key = os.getenv("RESEND_API_KEY")

async def send_slack_alert(message: str):
    """Pushes a message or alert to a Slack channel via Webhook."""
    if not SLACK_WEBHOOK_URL or "YOUR/WEBHOOK" in SLACK_WEBHOOK_URL:
        print("⚠️ Slack Webhook URL not configured. Skipping Slack dispatch.")
        return
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(SLACK_WEBHOOK_URL, json={"text": message})
            if response.status_code == 200:
                print("💬 Slack Message Dispatched Successfully.")
            else:
                print(f"⚠️ Slack Dispatch Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Failed to send Slack alert: {e}")

def send_email_alert(subject: str, body: str, attachment_path: str = None):
    """Dispatches email and optional PDF attachments via the Resend API."""
    sender = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    recipient = os.getenv("ALERT_RECIPIENT_EMAIL")
    
    if not resend.api_key or not recipient:
        print("⚠️ Resend API Key or Recipient Email missing. Skipping Email dispatch.")
        return

    params = {
        "from": sender,
        "to": recipient,
        "subject": subject,
        "html": f"<p><strong>System Alert:</strong></p><p>{body}</p>"
    }

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, 'rb') as f:
            file_bytes = f.read()
            params["attachments"] = [
                {
                    "filename": os.path.basename(attachment_path),
                    "content": list(file_bytes)
                }
            ]

    try:
        response = resend.Emails.send(params)
        print(f"📧 Resend Email Dispatched: {response}")
    except Exception as e:
        print(f"❌ Failed to send Resend email alert: {e}")

async def log_alert_to_db(conn, alert_type, app_id, message):
    """Persists the alert to PostgreSQL to prevent duplicate spamming."""
    recent_alert = await conn.fetchval("""
        SELECT COUNT(*) FROM alerts 
        WHERE alert_type = $1 AND app_id = $2 AND fired_at >= NOW() - INTERVAL '1 hour'
    """, alert_type, app_id)
    
    if recent_alert == 0:
        await conn.execute(
            "INSERT INTO alerts (alert_type, app_id, message) VALUES ($1, $2, $3)",
            alert_type, app_id, message
        )
        print(f"[{alert_type}] {app_id}: {message}")
        await send_slack_alert(f"🚨 *LLM Proxy Alert* [{alert_type}]\n{message}")
        send_email_alert(f"LLM Proxy Alert: {alert_type}", message)

# --- ANOMALY DETECTION LOGIC ---

async def check_cost_spikes(conn):
    query = """
    WITH last_hour AS (
        SELECT app_id, SUM(cost_usd) as current_spend
        FROM llm_transactions WHERE created_at >= NOW() - INTERVAL '1 hour'
        GROUP BY app_id
    ), historical AS (
        SELECT app_id, SUM(cost_usd) / (7 * 24.0) as avg_hourly_spend
        FROM llm_transactions WHERE created_at >= NOW() - INTERVAL '7 days'
        GROUP BY app_id
    )
    SELECT l.app_id, l.current_spend, h.avg_hourly_spend
    FROM last_hour l JOIN historical h ON l.app_id = h.app_id
    WHERE l.current_spend > (h.avg_hourly_spend * 2) 
      AND l.current_spend > 0.05;
    """
    spikes = await conn.fetch(query)
    for row in spikes:
        msg = f"App '{row['app_id']}' spent ${row['current_spend']:.4f} in the last hour. (Normal avg is ${row['avg_hourly_spend']:.4f}/hr)."
        await log_alert_to_db(conn, 'COST_SPIKE', row['app_id'], msg)

async def check_latency_outliers(conn):
    query = """
    WITH recent AS (
        SELECT app_id, percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_10m
        FROM llm_transactions WHERE created_at >= NOW() - INTERVAL '10 minutes'
        GROUP BY app_id
    ), baseline AS (
        SELECT app_id, percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_24h
        FROM llm_transactions WHERE created_at >= NOW() - INTERVAL '24 hours'
        GROUP BY app_id
    )
    SELECT r.app_id, r.p95_10m, b.p95_24h
    FROM recent r JOIN baseline b ON r.app_id = b.app_id
    WHERE r.p95_10m > (b.p95_24h * 3) AND r.p95_10m > 2000;
    """
    outliers = await conn.fetch(query)
    for row in outliers:
        msg = f"App '{row['app_id']}' is experiencing severe degradation. p95 Latency is {row['p95_10m']:.0f}ms (Baseline is {row['p95_24h']:.0f}ms)."
        await log_alert_to_db(conn, 'LATENCY_OUTLIER', row['app_id'], msg)

async def check_dlp_surges(conn):
    query = """
    SELECT t.app_id, COUNT(d.id) as incident_count
    FROM dlp_incidents d
    JOIN llm_transactions t ON d.transaction_id = t.id
    WHERE d.created_at >= NOW() - INTERVAL '15 minutes'
    GROUP BY t.app_id
    HAVING COUNT(d.id) >= 5;
    """
    surges = await conn.fetch(query)
    for row in surges:
        msg = f"App '{row['app_id']}' triggered {row['incident_count']} PII Data Loss Prevention blocks in the last 15 minutes. Possible malicious extraction attempt."
        await log_alert_to_db(conn, 'DLP_SURGE', row['app_id'], msg)

# --- DAILY PDF & SLACK REPORTING ---

async def generate_daily_pdf_report():
    print("Generating Daily PDF & Slack Report...")
    conn = await asyncpg.connect(DB_DSN)
    
    query = """
    SELECT app_id, SUM(prompt_tokens + completion_tokens) as total_tokens, SUM(cost_usd) as total_cost, COUNT(id) as total_requests
    FROM llm_transactions WHERE created_at >= NOW() - INTERVAL '24 hours'
    GROUP BY app_id
    """
    
    import psycopg2
    sync_conn = psycopg2.connect(DB_DSN)
    df = pd.read_sql(query, sync_conn)
    sync_conn.close()
    await conn.close()

    if df.empty:
        print("No transactions in the last 24 hours to report.")
        return

    # 1. Generate PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    pdf.cell(200, 10, txt="Daily AI Gateway Cost & Telemetry Report", ln=True, align='C')
    pdf.set_font("Helvetica", size=10)
    pdf.cell(200, 10, txt=f"Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", ln=True, align='C')
    pdf.ln(10)

    pdf.set_font("Helvetica", style="B", size=10)
    col_width = pdf.w / 4.5
    th = pdf.font_size * 2
    pdf.cell(col_width, th, "Application ID", border=1)
    pdf.cell(col_width, th, "Total Requests", border=1)
    pdf.cell(col_width, th, "Total Tokens", border=1)
    pdf.cell(col_width, th, "Total Cost (USD)", border=1)
    pdf.ln(th)

    pdf.set_font("Helvetica", size=10)
    total_spend = 0.0
    total_reqs = 0
    total_toks = 0
    
    # 2. Build Slack Markdown Message
    slack_lines = [
        "📊 *Daily AI Gateway Summary Report*",
        f"📅 _Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "```",
        f"{'App ID':<20} | {'Requests':<8} | {'Tokens':<10} | {'Cost (USD)':<10}",
        "-" * 55
    ]

    for idx, row in df.iterrows():
        # PDF Rows
        pdf.cell(col_width, th, str(row['app_id']), border=1)
        pdf.cell(col_width, th, str(row['total_requests']), border=1)
        pdf.cell(col_width, th, f"{row['total_tokens']:,}", border=1)
        pdf.cell(col_width, th, f"${row['total_cost']:.4f}", border=1)
        pdf.ln(th)
        
        total_spend += row['total_cost']
        total_reqs += int(row['total_requests'])
        total_toks += int(row['total_tokens'])
        
        # Slack Rows
        slack_lines.append(f"{str(row['app_id']):<20} | {row['total_requests']:<8} | {row['total_tokens']:<10,} | ${row['total_cost']:.4f}")

    pdf.ln(10)
    pdf.set_font("Helvetica", style="B", size=12)
    pdf.cell(200, 10, txt=f"Total 24h Spend Across All Apps: ${total_spend:.4f}", ln=True)

    os.makedirs("reports", exist_ok=True)
    report_path = "reports/daily_cost_report.pdf"
    pdf.output(report_path)

    slack_lines.append("-" * 55)
    slack_lines.append(f"{'TOTALS':<20} | {total_reqs:<8} | {total_toks:<10,} | ${total_spend:.4f}")
    slack_lines.append("```")
    slack_lines.append("📧 _Full PDF report breakdown has been dispatched via Resend to your inbox._")
    slack_msg = "\n".join(slack_lines)

    # 3. DUAL DISPATCH: Fire Email & Slack
    send_email_alert(
        subject="📊 Daily AI Proxy Report", 
        body="Attached is your 24-hour summary of LLM token consumption and costs.", 
        attachment_path=report_path
    )
    
    await send_slack_alert(slack_msg)

# --- EXECUTION BLOCK FOR TESTING ---

if __name__ == "__main__":
    print("🧪 Running manual test for Daily PDF Report (Email + Slack)...")
    try:
        asyncio.run(generate_daily_pdf_report())
        print("✅ Test complete. Check your inbox and your Slack channel!")
    except Exception as e:
        print(f"❌ Test failed: {e}")

# --- EXECUTION BLOCK FOR ACTUAL PURPOSE --- ## --- EXECUTION BLOCK (DAEMON MODE) ---

# if __name__ == "__main__":
#     print("🛡️ Starting AI Proxy Anomaly Detector Daemon...")
    
#     # Initialize the background scheduler
#     scheduler = AsyncIOScheduler()
    
#     # 1. INTERVAL JOB: Run the anomaly scans every 5 minutes
#     scheduler.add_job(run_anomaly_checks, 'interval', minutes=5)
    
#     # 2. CRON JOB: Run the PDF reporting job at exactly 8:00 AM UTC every day
#     scheduler.add_job(generate_daily_pdf_report, 'cron', hour=8, minute=0)
    
#     # Start the scheduler
#     scheduler.start()
    
#     # Keep the Python script alive forever to listen for schedule triggers
#     try:
#         asyncio.get_event_loop().run_forever()
#     except (KeyboardInterrupt, SystemExit):
#         print("\n🛑 Shutting down Anomaly Detector Daemon.")