"""
orchestrator.py
Chains 5 Kibana Agent Builder agents in sequence, then sends
an email alert based on the Arbiter's confidence score.
"""

import os
import re
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from action_executor import execute_action

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
KIBANA_URL = os.getenv("KIBANA_URL")
ES_URL     = os.getenv("ES_URL")
API_KEY    = os.getenv("ES_API_KEY")

HEADERS = {
    "Content-Type":  "application/json",
    "Authorization": f"ApiKey {API_KEY}",
    "kbn-xsrf":      "true",
}

AGENT_IDS = {
    "sensor":    os.getenv("AGENT_ID_SENSOR"),
    "diagnosis": os.getenv("AGENT_ID_DIAGNOSIS"),
    "risk":      os.getenv("AGENT_ID_RISK"),
    "recovery":  os.getenv("AGENT_ID_RECOVERY"),
    "arbiter":   os.getenv("AGENT_ID_ARBITER"),
}

EMAIL_SENDER    = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD  = os.getenv("EMAIL_PASSWORD")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT")

es = Elasticsearch(ES_URL, api_key=API_KEY)


# ── Agent call ────────────────────────────────────────────────────────────────
def call_agent(agent_id: str, message: str, retries: int = 2) -> str:
    url = f"{KIBANA_URL}/api/agent_builder/converse"
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                url,
                headers=HEADERS,
                json={"agent_id": agent_id, "input": message},
                timeout=300,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", {}).get("message", "")
        except requests.exceptions.ReadTimeout:
            if attempt < retries:
                print(f"  Timeout on attempt {attempt + 1}, retrying...")
            else:
                raise
        except requests.exceptions.HTTPError as e:
            print(f"  HTTP {e.response.status_code}: {e.response.text[:300]}")
            raise


# ── JSON parsing ──────────────────────────────────────────────────────────────
def parse_json(text: str) -> dict:
    """Strip markdown fences and parse JSON from agent response."""
    clean = text.strip()
    # Remove ```json ... ``` or ``` ... ``` fences
    clean = re.sub(r"^```[a-z]*\n?", "", clean)
    clean = re.sub(r"\n?```$", "", clean)
    return json.loads(clean.strip())


# ── Markdown to simple HTML ───────────────────────────────────────────────────
def md_to_html(text: str) -> str:
    """
    Convert basic markdown to HTML for email display.
    Handles: headers, bold, tables, bullet lists, code blocks.
    """
    # Code blocks (run before headers/bold to avoid mangling fence content)
    text = re.sub(
        r"```(?:[a-z]*)?\n?(.*?)```",
        r'<pre style="background:#f4f4f4;padding:10px;border-radius:4px;font-size:12px;overflow-x:auto;white-space:pre-wrap">\1</pre>',
        text, flags=re.DOTALL
    )
    # Inline code
    text = re.sub(r"`([^`]+)`", r'<code style="background:#f4f4f4;padding:1px 4px;border-radius:3px;font-size:12px">\1</code>', text)
    # Headers (#### must come before ### etc)
    text = re.sub(r"^#### (.+)$", r"<h5 style='margin:10px 0 3px;font-size:13px'>\1</h5>", text, flags=re.MULTILINE)
    text = re.sub(r"^### (.+)$",  r"<h4 style='margin:12px 0 4px'>\1</h4>",               text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$",   r"<h3 style='margin:14px 0 6px'>\1</h3>",               text, flags=re.MULTILINE)
    text = re.sub(r"^# (.+)$",    r"<h2 style='margin:16px 0 8px'>\1</h2>",               text, flags=re.MULTILINE)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Markdown tables -- convert to HTML table
    def convert_table(match):
        lines = match.group(0).strip().split("\n")
        rows = [l for l in lines if not re.match(r"^\|[-| :]+\|$", l)]
        html = ['<table style="width:100%;border-collapse:collapse;margin:12px 0;font-size:13px">']
        for i, row in enumerate(rows):
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            tag = "th" if i == 0 else "td"
            style = "padding:6px 10px;border:1px solid #ddd;" + ("background:#f5f5f5;font-weight:bold;" if i == 0 else "")
            html.append("<tr>" + "".join(f'<{tag} style="{style}">{c}</{tag}>' for c in cells) + "</tr>")
        html.append("</table>")
        return "\n".join(html)
    text = re.sub(r"(\|.+\|\n)+", convert_table, text)
    # Bullet lists
    text = re.sub(r"^[-*] (.+)$", r"<li style='margin:3px 0'>\1</li>", text, flags=re.MULTILINE)
    text = re.sub(r"(<li.*</li>\n?)+", r'<ul style="margin:8px 0;padding-left:20px">\g<0></ul>', text)
    # Horizontal rules
    text = re.sub(r"^---+$", "<hr style='border:none;border-top:1px solid #eee;margin:12px 0'>", text, flags=re.MULTILINE)
    # Line breaks
    text = text.replace("\n\n", "</p><p style='margin:8px 0'>")
    text = f"<p style='margin:8px 0'>{text}</p>"
    return text


# ── Email ─────────────────────────────────────────────────────────────────────
def send_email(subject: str, body_html: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())

    print(f"  Email sent to {EMAIL_RECIPIENT}")


def build_email_body(action: str, arbiter: dict,
                     sensor_reply: str, risk_reply: str,
                     recovery_reply: str, project_id: str) -> str:

    colors = {
        "auto_execute":       "#2e7d32",
        "draft_for_approval": "#e65100",
        "escalate":           "#b71c1c",
    }
    labels = {
        "auto_execute":       "Action Executed Automatically",
        "draft_for_approval": "Action Pending Your Approval",
        "escalate":           "Urgent — Your Intervention Required",
    }
    color = colors.get(action, "#333")
    label = labels.get(action, action)

    confidence    = arbiter.get("confidence", 0)
    confidence_pct = f"{confidence:.0%}" if isinstance(confidence, float) else str(confidence)

    action_box = ""
    if action == "draft_for_approval":
        action_box = """
        <div style="background:#fff3e0;border-left:4px solid #e65100;padding:12px;margin:16px 0">
          <strong>Action required:</strong> Reply to this email with APPROVE or OVERRIDE to proceed.
        </div>"""
    elif action == "escalate":
        reason = arbiter.get("escalate_reason", "Confidence too low for automated action.")
        action_box = f"""
        <div style="background:#ffebee;border-left:4px solid #b71c1c;padding:12px;margin:16px 0">
          <strong>Urgent:</strong> {reason}
        </div>"""

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:720px;margin:0 auto">

      <div style="background:{color};color:white;padding:16px 20px;border-radius:6px 6px 0 0">
        <h2 style="margin:0">pulse</h2>
        <p style="margin:4px 0 0;font-size:14px">{label}</p>
      </div>

      <div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 6px 6px">

        <p style="font-size:15px;color:#333">{arbiter.get("email_summary", "See reasoning trail below.")}</p>

        <table style="width:100%;border-collapse:collapse;margin:16px 0;font-size:14px">
          <tr>
            <td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;width:35%;border:1px solid #eee">Project</td>
            <td style="padding:8px 12px;border:1px solid #eee">{project_id}</td>
          </tr>
          <tr>
            <td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #eee">Recommended intervention</td>
            <td style="padding:8px 12px;border:1px solid #eee">{arbiter.get("recommended_intervention", "—")}</td>
          </tr>
          <tr>
            <td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #eee">Confidence</td>
            <td style="padding:8px 12px;border:1px solid #eee">{confidence_pct}</td>
          </tr>
          <tr>
            <td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #eee">Urgency</td>
            <td style="padding:8px 12px;border:1px solid #eee">{arbiter.get("urgency", "—")}</td>
          </tr>
          <tr>
            <td style="padding:8px 12px;background:#f5f5f5;font-weight:bold;border:1px solid #eee">Reasoning</td>
            <td style="padding:8px 12px;border:1px solid #eee">{arbiter.get("reasoning", "—")}</td>
          </tr>
        </table>

        {action_box}

        <h3 style="margin:20px 0 8px;font-size:14px;color:#555;border-bottom:1px solid #eee;padding-bottom:6px">
          SENSOR SIGNAL
        </h3>
        {md_to_html(sensor_reply[:1200])}

        <h3 style="margin:20px 0 8px;font-size:14px;color:#555;border-bottom:1px solid #eee;padding-bottom:6px">
          RISK AGENT
        </h3>
        {md_to_html(risk_reply[:1200])}

        <h3 style="margin:20px 0 8px;font-size:14px;color:#555;border-bottom:1px solid #eee;padding-bottom:6px">
          RECOVERY AGENT
        </h3>
        {md_to_html(recovery_reply[:1200])}

        <hr style="margin:20px 0;border:none;border-top:1px solid #eee">
        <p style="color:#aaa;font-size:11px">
          pulse — Consulting Project Early Warning System<br>
          {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
        </p>
      </div>
    </div>
    """


# ── ES decision log ───────────────────────────────────────────────────────────
def index_decision(project_id: str, run: dict):
    doc = {
        "project_id":        project_id,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "sensor_output":     run.get("sensor_reply", ""),
        "diagnosis_output":  run.get("diagnosis_reply", ""),
        "risk_argument":     run.get("risk_reply", ""),
        "recovery_argument": run.get("recovery_reply", ""),
        "arbiter_decision":  run.get("arbiter_reply", ""),
        "action_taken":      run.get("action", {}),
        "human_approved":    None,
        "outcome":           None,
    }
    es.index(index="pulse_decisions", document=doc)
    print(f"  Decision indexed to pulse_decisions")


# ── Main pipeline ─────────────────────────────────────────────────────────────
def run_pipeline(project_id: str = "LIVE-001"):
    print(f"\n{'='*60}")
    print(f"  PULSE — Project Early Warning System")
    print(f"  Running pipeline for: {project_id}")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}\n")

    run = {}

    # ── Step 1: Sensor ────────────────────────────────────────────────────────
    print("[ 1/5 ] Sensor Agent — scanning for distress signals...")
    sensor_reply = call_agent(
        AGENT_IDS["sensor"],
        f"Scan all live projects for compound distress signals. "
        f"Focus on project {project_id} if it appears in results."
    )
    run["sensor_reply"] = sensor_reply
    print(f"  -> {sensor_reply[:200]}...\n")

    if "no distress" in sensor_reply.lower() or "no projects" in sensor_reply.lower():
        print("  No distress detected. Pipeline complete.")
        return

    # ── Step 2: Diagnosis ─────────────────────────────────────────────────────
    print("[ 2/5 ] Diagnosis Agent — searching historical matches...")
    diagnosis_reply = call_agent(
        AGENT_IDS["diagnosis"],
        f"Based on this sensor output, find historical matches and "
        f"relevant playbooks:\n\n{sensor_reply}"
    )
    run["diagnosis_reply"] = diagnosis_reply
    print(f"  -> {diagnosis_reply[:200]}...\n")

    # ── Step 3: Risk ──────────────────────────────────────────────────────────
    print("[ 3/5 ] Risk Agent — building conservative case...")
    risk_reply = call_agent(
        AGENT_IDS["risk"],
        f"Distress signal and diagnosis for {project_id}. "
        f"Build your conservative intervention argument.\n\n"
        f"SENSOR:\n{sensor_reply}\n\nDIAGNOSIS:\n{diagnosis_reply}"
    )
    run["risk_reply"] = risk_reply
    print(f"  -> {risk_reply[:200]}...\n")

    # ── Step 4: Recovery ──────────────────────────────────────────────────────
    print("[ 4/5 ] Recovery Agent — building recovery case...")
    recovery_reply = call_agent(
        AGENT_IDS["recovery"],
        f"Distress signal and diagnosis for {project_id}. "
        f"Build your internal resolution argument.\n\n"
        f"SENSOR:\n{sensor_reply}\n\nDIAGNOSIS:\n{diagnosis_reply}"
    )
    run["recovery_reply"] = recovery_reply
    print(f"  -> {recovery_reply[:200]}...\n")

    # ── Step 5: Arbiter ───────────────────────────────────────────────────────
    print("[ 5/5 ] Arbiter Agent — making final call...")
    arbiter_reply = call_agent(
        AGENT_IDS["arbiter"],
        f"Make the final call for project {project_id}.\n\n"
        f"SENSOR:\n{sensor_reply}\n\n"
        f"DIAGNOSIS:\n{diagnosis_reply}\n\n"
        f"RISK AGENT:\n{risk_reply}\n\n"
        f"RECOVERY AGENT:\n{recovery_reply}"
    )
    run["arbiter_reply"] = arbiter_reply
    print(f"  -> {arbiter_reply[:300]}...\n")

    # Parse arbiter JSON -- strip markdown fences first
    arbiter_json     = {}
    final_confidence = 0.5
    action_spectrum  = "escalate"
    try:
        arbiter_json     = parse_json(arbiter_reply)
        final_confidence = arbiter_json.get("confidence", 0.5)
        action_spectrum  = arbiter_json.get("action_spectrum", "escalate")
        print(f"  Arbiter confidence: {final_confidence:.0%} | Action: {action_spectrum}")
    except Exception as ex:
        print(f"  Could not parse arbiter JSON ({ex}) — defaulting to escalate")

    run["action"] = {"action": action_spectrum, "confidence": final_confidence}

    # ── Log decision ──────────────────────────────────────────────────────────
    print("[ LOG ] Indexing decision trail...")
    index_decision(project_id, run)

    # ── Execute action if confidence is high enough ───────────────────────────
    if action_spectrum == "auto_execute":
        print("[ EXECUTE ] Creating action record...")
        execute_action(
            project_id   = project_id,
            intervention = arbiter_json.get("recommended_intervention", "exec_intervention"),
            reasoning    = arbiter_json.get("reasoning", ""),
            confidence   = final_confidence,
        )

    # ── Send email ────────────────────────────────────────────────────────────
    print("[ EMAIL ] Sending partner alert...")
    subject = arbiter_json.get(
        "email_subject",
        f"[pulse] {project_id} — {action_spectrum.replace('_', ' ').title()}"
    )
    body = build_email_body(
        action         = action_spectrum,
        arbiter        = arbiter_json,
        sensor_reply   = sensor_reply,
        risk_reply     = risk_reply,
        recovery_reply = recovery_reply,
        project_id     = project_id,
    )
    send_email(subject, body)

    # ── Final output ──────────────────────────────────────────────────────────
    outcome_labels = {
        "auto_execute":       "AUTO — executed and logged",
        "draft_for_approval": "DRAFT — approval email sent to partner",
        "escalate":           "ESCALATE — urgent email sent to partner",
    }
    print(f"\n{'='*60}")
    print(f"  DECISION: {outcome_labels.get(action_spectrum, action_spectrum)}")
    print(f"  Confidence: {final_confidence:.0%}")
    print(f"{'='*60}\n")

    return run


if __name__ == "__main__":
    run_pipeline("LIVE-001")
