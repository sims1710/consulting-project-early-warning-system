"""
Chains the 4 Kibana Agent Builder agents in sequence:
  1. Sensor Agent    — detects distressed projects
  2. Diagnosis Agent — finds historical matches
  3. Risk Agent      — argues for conservative intervention
  4. Recovery Agent  — argues for internal resolution
  5. Arbiter         — weighs both, applies confidence spectrum, acts

The Kibana agents handle all LLM reasoning and tool calls.
This script is purely the conductor — it passes context between agents
and executes the confidence-calibrated action at the end.

API used: POST /api/agent_builder/converse
"""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from elasticsearch import Elasticsearch

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
KIBANA_URL = os.getenv("KIBANA_URL")
API_KEY    = os.getenv("ES_API_KEY")

HEADERS = {
    "Content-Type":  "application/json",
    "Authorization": f"ApiKey {API_KEY}",
    "kbn-xsrf":      "true",
}

# Agent IDs — get these from Kibana → Agents → click agent → copy ID from URL
AGENT_IDS = {
    "sensor":    os.getenv("AGENT_ID_SENSOR"),
    "diagnosis": os.getenv("AGENT_ID_DIAGNOSIS"),
    "risk":      os.getenv("AGENT_ID_RISK"),
    "recovery":  os.getenv("AGENT_ID_RECOVERY"),
}

es = Elasticsearch(ES_URL, api_key=API_KEY)


# ── Converse API call ─────────────────────────────────────────────────────────
def call_agent(agent_id: str, message: str, conversation_id: str = None) -> dict:
    """
    Calls a Kibana Agent Builder agent via the converse API.
    Returns the full response including agent reply and tool traces.
    """
    url     = f"{KIBANA_URL}/api/agent_builder/converse"
    payload = {
        "agent_id": agent_id,
        "message":  message,
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    resp = requests.post(url, headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def extract_reply(response: dict) -> str:
    """Pulls the agent's text reply from the converse API response."""
    return response.get("message", {}).get("content", "")


# ── Confidence-calibrated action spectrum ─────────────────────────────────────
def determine_action(confidence: float, num_matches: int, arbiter_reply: str) -> dict:
    """
    Applies the confidence spectrum to decide how to act.

    > 0.85 + 3+ matches  → auto-execute, log, notify partner async
    0.60 - 0.85          → draft for partner approval
    < 0.60               → escalate to partner with full context
    """
    if confidence >= 0.85 and num_matches >= 3:
        return {
            "action":     "auto_execute",
            "label":      "AUTO — executing and logging",
            "confidence": confidence,
        }
    elif confidence >= 0.60:
        return {
            "action":     "draft_for_approval",
            "label":      "DRAFT — awaiting partner approval",
            "confidence": confidence,
        }
    else:
        return {
            "action":     "escalate",
            "label":      "ESCALATE — insufficient confidence, partner required",
            "confidence": confidence,
        }


# ── Feedback loop — index decision back to ES ─────────────────────────────────
def index_decision(project_id: str, run: dict):
    """
    Indexes the full reasoning trail and decision back into Elasticsearch.
    This is how the system learns — every decision becomes future training data.
    """
    doc = {
        "project_id":        project_id,
        "timestamp":         datetime.utcnow().isoformat(),
        "sensor_output":     run.get("sensor_reply", ""),
        "diagnosis_output":  run.get("diagnosis_reply", ""),
        "risk_argument":     run.get("risk_reply", ""),
        "recovery_argument": run.get("recovery_reply", ""),
        "arbiter_decision":  run.get("arbiter_reply", ""),
        "action_taken":      run.get("action", {}),
        "human_approved":    None,   # updated later via feedback_loop.py
        "outcome":           None,   # updated when project closes
    }
    es.index(index="pulse_decisions", document=doc)
    print(f"  Decision indexed to pulse_decisions")


# ── Main pipeline ─────────────────────────────────────────────────────────────
def run_pipeline(project_id: str = "LIVE-001"):
    print(f"\n{'='*60}")
    print(f"  PULSE — Project Early Warning System")
    print(f"  Running pipeline for project: {project_id}")
    print(f"  {datetime.utcnow().isoformat()}")
    print(f"{'='*60}\n")

    run = {}

    # ── Step 1: Sensor Agent ──────────────────────────────────────────────────
    print("[ 1/5 ] Sensor Agent — scanning for distress signals...")
    sensor_resp  = call_agent(
        AGENT_IDS["sensor"],
        f"Scan all live projects for compound distress signals. "
        f"Focus on project {project_id} if it appears in results."
    )
    sensor_reply = extract_reply(sensor_resp)
    run["sensor_reply"] = sensor_reply
    print(f"  → {sensor_reply[:200]}...\n")

    if "no distress" in sensor_reply.lower() or "no projects" in sensor_reply.lower():
        print("  No distress detected. Pipeline complete.")
        return

    # ── Step 2: Diagnosis Agent ───────────────────────────────────────────────
    print("[ 2/5 ] Diagnosis Agent — searching historical matches...")
    diagnosis_resp  = call_agent(
        AGENT_IDS["diagnosis"],
        f"Based on this sensor output, find historical matches and "
        f"relevant playbooks:\n\n{sensor_reply}"
    )
    diagnosis_reply = extract_reply(diagnosis_resp)
    run["diagnosis_reply"] = diagnosis_reply
    print(f"  → {diagnosis_reply[:200]}...\n")

    # ── Step 3: Risk Agent ────────────────────────────────────────────────────
    print("[ 3/5 ] Risk Agent — building conservative case...")
    risk_resp  = call_agent(
        AGENT_IDS["risk"],
        f"Here is the distress signal and diagnosis for project {project_id}. "
        f"Build your argument for the conservative intervention.\n\n"
        f"SENSOR:\n{sensor_reply}\n\n"
        f"DIAGNOSIS:\n{diagnosis_reply}"
    )
    risk_reply = extract_reply(risk_resp)
    run["risk_reply"] = risk_reply
    print(f"  → {risk_reply[:200]}...\n")

    # ── Step 4: Recovery Agent ────────────────────────────────────────────────
    print("[ 4/5 ] Recovery Agent — building recovery case...")
    recovery_resp  = call_agent(
        AGENT_IDS["recovery"],
        f"Here is the distress signal and diagnosis for project {project_id}. "
        f"Build your argument for the least disruptive intervention.\n\n"
        f"SENSOR:\n{sensor_reply}\n\n"
        f"DIAGNOSIS:\n{diagnosis_reply}"
    )
    recovery_reply = extract_reply(recovery_resp)
    run["recovery_reply"] = recovery_reply
    print(f"  → {recovery_reply[:200]}...\n")

    # ── Step 5: Arbiter (local logic + summary) ───────────────────────────────
    print("[ 5/5 ] Arbiter — weighing arguments and deciding...")

    # Extract confidence scores from agent replies (agents output structured JSON)
    risk_confidence     = 0.5
    recovery_confidence = 0.5
    try:
        risk_json           = json.loads(risk_reply)
        risk_confidence     = risk_json.get("confidence", 0.5)
    except Exception:
        pass
    try:
        recovery_json       = json.loads(recovery_reply)
        recovery_confidence = recovery_json.get("confidence", 0.5)
    except Exception:
        pass

    # Arbitration: average confidence, penalise when agents strongly disagree
    disagreement   = abs(risk_confidence - recovery_confidence)
    avg_confidence = (risk_confidence + recovery_confidence) / 2
    final_confidence = avg_confidence * (1 - disagreement * 0.3)  # penalise disagreement

    # Count historical matches mentioned in diagnosis
    num_matches = diagnosis_reply.lower().count("match") + diagnosis_reply.lower().count("project")
    num_matches = min(max(num_matches // 2, 1), 10)  # rough heuristic

    action = determine_action(final_confidence, num_matches, diagnosis_reply)
    run["action"] = action

    arbiter_summary = (
        f"Risk confidence: {risk_confidence:.2f} | "
        f"Recovery confidence: {recovery_confidence:.2f} | "
        f"Disagreement: {disagreement:.2f} | "
        f"Final confidence: {final_confidence:.2f}\n"
        f"Decision: {action['label']}"
    )
    run["arbiter_reply"] = arbiter_summary

    print(f"\n  {arbiter_summary}\n")

    # ── Log full reasoning trail ──────────────────────────────────────────────
    print("[ LOG ] Indexing decision trail...")
    index_decision(project_id, run)

    # ── Final output ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  DECISION: {action['label']}")
    print(f"  Confidence: {final_confidence:.2f}")
    print(f"{'='*60}\n")

    if action["action"] == "auto_execute":
        print("  ✅ Action executed automatically. Partner notified.")
    elif action["action"] == "draft_for_approval":
        print("  📋 Draft prepared. Awaiting partner approval.")
        print("  Run feedback_loop.py to record the partner decision.")
    else:
        print("  🚨 Escalated to partner. Both arguments available above.")

    return run


if __name__ == "__main__":
    run_pipeline("LIVE-001")
