"""
action_executor.py
When the Arbiter decides auto_execute, this module creates a structured
action document in the pulse_actions index. This is what "execution" means
concretely -- a reviewable, auditable action record that a project manager
can act on immediately.
"""

import os
from datetime import datetime, timezone, timedelta
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv()

es = Elasticsearch(os.getenv("ES_URL"), api_key=os.getenv("ES_API_KEY"))


# Maps intervention names to concrete instructions
INTERVENTION_INSTRUCTIONS = {
    "internal_reallocation": (
        "1. Identify a senior consultant currently in stabilisation or closeout phase "
        "who can be partially reallocated to this project.\n"
        "2. Schedule a 3-day sprint reset with the delivery team -- no client communication yet.\n"
        "3. Rebaseline the sprint plan and velocity targets.\n"
        "4. Do not contact the client until velocity recovers for 2 consecutive weeks.\n"
        "5. Review progress in 10 days and escalate if velocity has not improved."
    ),
    "client_escalation": (
        "1. Schedule an executive alignment call with the client within 5 business days.\n"
        "2. Prepare a scope options document with 3 paths: descope, extend timeline, or add budget.\n"
        "3. Brief the partner leading the engagement before the call.\n"
        "4. Do not send written communication to the client before the call is confirmed.\n"
        "5. Document the agreed path in a formal change request within 48 hours of the call."
    ),
    "exec_intervention": (
        "1. Partner or MD to call the client CXO directly within 48 hours.\n"
        "2. Acknowledge the project concerns before presenting solutions.\n"
        "3. Assign a dedicated client success contact for weekly check-ins.\n"
        "4. Prepare a recovery plan document within 5 business days.\n"
        "5. Schedule a formal recovery review in 3 weeks."
    ),
    "scope_renegotiation": (
        "1. Prepare a scope audit document listing all changes since project kickoff.\n"
        "2. Quantify the cost and timeline impact of each scope addition.\n"
        "3. Present to client with options to formally accept, defer, or descope each item.\n"
        "4. Get written sign-off on agreed scope within 10 business days.\n"
        "5. Update the SOW and rebaseline the project plan."
    ),
    "timeline_extension": (
        "1. Prepare a revised project timeline with a realistic new delivery date.\n"
        "2. Identify the minimum scope required for the original date if preferred.\n"
        "3. Present both options to the client within 5 business days.\n"
        "4. Get written approval before communicating to the wider team.\n"
        "5. Update all project tracking systems with the new dates."
    ),
    "team_augmentation": (
        "1. Identify the specific skill gaps causing the velocity drop.\n"
        "2. Source 1-2 additional consultants with the required skills within 5 business days.\n"
        "3. Brief the augmented team members with full project context before onboarding.\n"
        "4. Run a team alignment session in the first week.\n"
        "5. Review velocity improvement after 2 sprints."
    ),
}

DEFAULT_INSTRUCTIONS = (
    "1. Review the arbiter reasoning and historical matches in the decision record.\n"
    "2. Convene the project leadership team within 48 hours.\n"
    "3. Agree on a concrete intervention plan with accountable owners.\n"
    "4. Communicate the plan to the client if appropriate.\n"
    "5. Review progress in 2 weeks."
)


def execute_action(project_id: str, intervention: str,
                   reasoning: str, confidence: float) -> str:
    """
    Creates a structured action document in pulse_actions.
    Returns the document ID for reference.
    """
    instructions = INTERVENTION_INSTRUCTIONS.get(intervention, DEFAULT_INSTRUCTIONS)
    review_date  = (datetime.now(timezone.utc) + timedelta(days=14)).date().isoformat()

    doc = {
        "project_id":    project_id,
        "action_type":   intervention,
        "created_at":    datetime.now(timezone.utc).isoformat(),
        "created_by":    "pulse-arbiter",
        "status":        "pending",
        "instructions":  instructions,
        "reasoning":     reasoning,
        "confidence":    confidence,
        "review_by":     review_date,
        "completed_at":  None,
        "outcome_notes": None,
    }

    resp = es.index(index="pulse_actions", document=doc)
    action_id = resp["_id"]
    print(f"  Action created in pulse_actions: {action_id}")
    print(f"  Intervention: {intervention}")
    print(f"  Review by: {review_date}")
    return action_id


if __name__ == "__main__":
    # Test
    action_id = execute_action(
        project_id   = "LIVE-001",
        intervention = "exec_intervention",
        reasoning    = "Test execution",
        confidence   = 0.88,
    )
    print(f"\nAction ID: {action_id}")
