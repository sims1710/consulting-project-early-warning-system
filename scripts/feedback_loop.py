"""
feedback_loop.py
Records partner approval/override decisions back into Elasticsearch.
This is how pulse learns -- every human decision improves future recommendations.

Usage:
    python feedback_loop.py list
    python feedback_loop.py <decision_id> approved [notes]
    python feedback_loop.py <decision_id> overridden [notes]
"""

import sys
import os
from datetime import datetime, timezone
from elasticsearch import Elasticsearch
from dotenv import load_dotenv

load_dotenv()

es = Elasticsearch(os.getenv("ES_URL"), api_key=os.getenv("ES_API_KEY"))


def record_decision(decision_id: str, human_choice: str, notes: str = ""):
    """Updates a decision document with the partner's response."""
    es.update(
        index="pulse_decisions",
        id=decision_id,
        body={
            "doc": {
                "human_approved": human_choice == "approved",
                "human_choice":   human_choice,
                "human_notes":    notes,
                "resolved_at":    datetime.now(timezone.utc).isoformat(),
            }
        }
    )
    print(f"Decision {decision_id} recorded as: {human_choice}")


def list_pending():
    """Lists all decisions awaiting partner approval."""
    resp = es.search(
        index="pulse_decisions",
        body={
            "query": {
                "bool": {
                    "must": [
                        {"term": {"action_taken.action": "draft_for_approval"}},
                    ],
                    "must_not": [
                        {"exists": {"field": "resolved_at"}}
                    ]
                }
            },
            "sort": [{"timestamp": {"order": "desc"}}],
            "size": 20,
        }
    )
    hits = resp["hits"]["hits"]
    if not hits:
        print("No decisions pending approval.")
        return
    print(f"\n{len(hits)} decision(s) pending approval:\n")
    for h in hits:
        doc = h["_source"]
        print(f"  ID:      {h['_id']}")
        print(f"  Project: {doc.get('project_id', '—')}")
        print(f"  Time:    {doc.get('timestamp', '—')}")
        print(f"  Action:  {doc.get('action_taken', {}).get('action', '—')}")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python feedback_loop.py list")
        print("  python feedback_loop.py <decision_id> approved [notes]")
        print("  python feedback_loop.py <decision_id> overridden [notes]")
        sys.exit(0)

    if sys.argv[1] == "list":
        list_pending()
    else:
        decision_id  = sys.argv[1]
        human_choice = sys.argv[2] if len(sys.argv) > 2 else "approved"
        notes        = sys.argv[3] if len(sys.argv) > 3 else ""
        record_decision(decision_id, human_choice, notes)
