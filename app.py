import streamlit as st
import anthropic
import csv
import json
import io
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

st.set_page_config(page_title="Finance Agent — Gulf Region", layout="wide")

st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: bold; color: #1F4E79; }
    .sub-header { font-size: 1rem; color: #666; margin-bottom: 2rem; }
    .tool-badge { background: #E8F4FD; padding: 4px 10px; border-radius: 12px; font-size: 0.8rem; color: #2E75B6; margin: 2px; display: inline-block; }
</style>
""", unsafe_allow_html=True)

client = anthropic.Anthropic()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

if "history" not in st.session_state:
    st.session_state.history = []
if "goal" not in st.session_state:
    st.session_state.goal = ""

# ── DATA FUNCTIONS ──
def read_overhead_data(file_content=None):
    data = {}
    if file_content:
        reader = csv.DictReader(io.StringIO(file_content))
    else:
        reader = csv.DictReader(open(os.path.join(BASE_DIR, 'overhead.csv'), 'r'))
    for row in reader:
        data[row['Category']] = float(row['Amount'])
    return data

def read_bank_statement(file_content=None):
    transactions = []
    if file_content:
        reader = csv.DictReader(io.StringIO(file_content))
    else:
        reader = csv.DictReader(open(os.path.join(BASE_DIR, 'bank_statement.csv'), 'r'))
    for row in reader:
        transactions.append(row)
    return transactions

def read_monthly_overhead(month):
    filename = os.path.join(BASE_DIR, f"overhead_{month.lower()}.csv")
    data = {}
    try:
        with open(filename, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                data[row['Category']] = float(row['Amount'])
        return {"month": month, "data": data, "total": sum(data.values())}
    except FileNotFoundError:
        return {"error": f"File for {month} not found"}

def compare_months(month1, month2):
    data1 = read_monthly_overhead(month1)
    data2 = read_monthly_overhead(month2)
    if "error" in data1 or "error" in data2:
        return {"error": "One or both months not found"}
    comparison = {}
    for category in data1["data"]:
        amount1 = data1["data"][category]
        amount2 = data2["data"].get(category, 0)
        variance = amount2 - amount1
        variance_pct = (variance / amount1) * 100 if amount1 != 0 else 0
        comparison[category] = {
            "month1": month1, "amount1": amount1,
            "month2": month2, "amount2": amount2,
            "variance": variance, "variance_pct": round(variance_pct, 2)
        }
    return comparison

def calculate_savings(category, amount, percentage):
    saving = amount * (percentage / 100)
    return {"category": category, "current_amount": amount, "saving": saving, "new_amount": amount - saving}

def generate_report(title, content):
    filename = os.path.join(BASE_DIR, f"report_{title.replace(' ', '_')}.txt")
    with open(filename, 'w') as f:
        f.write(f"FINANCE REPORT: {title}\n")
        f.write("=" * 50 + "\n")
        f.write(content)
    return f"Report saved as {filename}"

def send_email_report(to_email, subject, body, from_email, app_password):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(from_email, app_password)
            server.sendmail(from_email, to_email, msg.as_string())
        return True
    except Exception as e:
        return str(e)

tools = [
    {"name": "read_overhead_data", "description": "Reads overhead cost data from uploaded file or default CSV", "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "read_bank_statement", "description": "Reads bank statement transactions from uploaded file or default CSV", "input_schema": {"type": "object", "properties": {}, "required": []}},
    {"name": "read_monthly_overhead", "description": "Reads overhead data for a specific month (jan, feb, mar)", "input_schema": {"type": "object", "properties": {"month": {"type": "string", "description": "Month: jan, feb, or mar"}}, "required": ["month"]}},
    {"name": "compare_months", "description": "Compares overhead costs between two months and calculates variances", "input_schema": {"type": "object", "properties": {"month1": {"type": "string"}, "month2": {"type": "string"}}, "required": ["month1", "month2"]}},
    {"name": "calculate_savings", "description": "Calculates savings for a specific overhead category", "input_schema": {"type": "object", "properties": {"category": {"type": "string"}, "amount": {"type": "number"}, "percentage": {"type": "number"}}, "required": ["category", "amount", "percentage"]}},
    {"name": "generate_report", "description": "Saves analysis findings to a report file", "input_schema": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}, "required": ["title", "content"]}},
]

def process_tool_call(tool_name, tool_input, overhead_content=None, bank_content=None):
    if tool_name == "read_overhead_data":
        return read_overhead_data(overhead_content)
    elif tool_name == "read_bank_statement":
        return read_bank_statement(bank_content)
    elif tool_name == "read_monthly_overhead":
        return read_monthly_overhead(tool_input["month"])
    elif tool_name == "compare_months":
        return compare_months(tool_input["month1"], tool_input["month2"])
    elif tool_name == "calculate_savings":
        return calculate_savings(tool_input["category"], tool_input["amount"], tool_input["percentage"])
    elif tool_name == "generate_report":
        return generate_report(tool_input["title"], tool_input["content"])

def run_agent(user_goal, overhead_content=None, bank_content=None):
    messages = [{"role": "user", "content": user_goal}]
    tool_log = []
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system="""You are a senior finance analyst agent for an international
heavy equipment rental company in the Gulf Region.
You have access to January, February and March overhead data plus bank statements.
IMPORTANT RULES:
- NEVER ask the user for data — always use your tools
- Always read relevant data first before analyzing
- Flag variances above 5% as significant
- Save important findings using generate_report
- Use financial language and be precise""",
            tools=tools,
            messages=messages
        )
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_log.append(block.name)
                    result = process_tool_call(block.name, block.input, overhead_content, bank_content)
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result)})
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        elif response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text, tool_log
            break
    return "No response generated.", tool_log

# ── LAYOUT ──
col1, col2 = st.columns([1, 3])

with col1:
    st.markdown("### Quick Analysis")
    if st.button("📊 Total Overhead", use_container_width=True):
        st.session_state.goal = "What is our total overhead cost by category?"
    if st.button("🔴 Top 3 Risks", use_container_width=True):
        st.session_state.goal = "Analyze our bank statement and identify the top 3 financial risks"
    if st.button("💰 Savings Opportunities", use_container_width=True):
        st.session_state.goal = "Calculate 10% savings for all overhead categories and rank them"
    if st.button("📈 Cash Flow Summary", use_container_width=True):
        st.session_state.goal = "Summarize our cash flow — total inflows, outflows, and net position"

    st.markdown("---")
    st.markdown("### Multi-Month Comparison")
    month1 = st.selectbox("From month", ["jan", "feb", "mar"], index=0)
    month2 = st.selectbox("To month", ["jan", "feb", "mar"], index=2)
    if st.button("📅 Compare Months", use_container_width=True):
        st.session_state.goal = f"Use the compare_months tool with month1='{month1}' and month2='{month2}' to compare overhead costs. Show all variances and flag anything above 5%."
    if st.button("📉 Show All Trends", use_container_width=True):
        st.session_state.goal = "Read January, February and March overhead data and identify all cost trends across the three months"

    st.markdown("---")
    st.markdown("### Upload Your Data")
    overhead_file = st.file_uploader("Overhead CSV", type="csv", key="overhead")
    bank_file = st.file_uploader("Bank Statement CSV", type="csv", key="bank")
    if overhead_file:
        st.success("✅ Overhead file loaded")
    if bank_file:
        st.success("✅ Bank statement loaded")

    st.markdown("---")
    if st.session_state.history:
        st.markdown("### Previous Analyses")
        for i, item in enumerate(reversed(st.session_state.history[-5:])):
            with st.expander(f"#{len(st.session_state.history)-i}: {item['goal'][:30]}..."):
                st.markdown(item['response'])

with col2:
    st.markdown('<div class="main-header">Finance Agent — Gulf Region</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">AI-powered financial analysis for heavy equipment rental operations</div>', unsafe_allow_html=True)

    goal = st.text_input(
        "What would you like to analyze?",
        value=st.session_state.get("goal", ""),
        placeholder="e.g. Compare January to March and identify cost trends"
    )

    if st.button("🔍 Analyze", type="primary", use_container_width=True):
        if goal:
            overhead_content = overhead_file.read().decode("utf-8") if overhead_file else None
            bank_content = bank_file.read().decode("utf-8") if bank_file else None
            with st.spinner("Agent is analyzing your data..."):
                response, tool_log = run_agent(goal, overhead_content, bank_content)
            if tool_log:
                st.markdown("**Tools used:** " + " ".join([f'<span class="tool-badge">🔧 {t}</span>' for t in tool_log]), unsafe_allow_html=True)
            st.markdown("---")
            st.markdown("### Analysis Result")
            st.markdown(response)
            st.session_state.history.append({"goal": goal, "response": response})
            st.session_state.last_response = response
            st.session_state.last_goal = goal
            st.session_state.goal = ""
        else:
            st.warning("Please enter a goal or click a Quick Analysis button.")

    if "last_response" in st.session_state:
        st.markdown("---")
        st.markdown("### 📧 Email This Report")
        with st.expander("Send report by email"):
            from_email = st.text_input("Your Gmail address", placeholder="you@gmail.com")
            app_password = st.text_input("Gmail app password", type="password", placeholder="16-character app password")
            to_email = st.text_input("Send to", placeholder="recipient@example.com")
            if st.button("📤 Send Report", type="primary"):
                if from_email and app_password and to_email:
                    with st.spinner("Sending..."):
                        subject = f"Finance Report: {st.session_state.last_goal[:50]}"
                        result = send_email_report(to_email, subject, st.session_state.last_response, from_email, app_password)
                    if result is True:
                        st.success("✅ Report sent successfully!")
                    else:
                        st.error(f"❌ Failed to send: {result}")
                else:
                    st.warning("Please fill in all email fields.")
