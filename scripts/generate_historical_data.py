"""
Consulting Project Early Warning System
Data Generator — Historical Projects

Run AFTER you have created all 4 index mappings in Kibana Dev Tools.
Live projects, sentiment, and playbooks are in elastic/bulk/ as NDJSON
and can be pasted directly into Dev Tools.

Prerequisites:
  pip install elasticsearch faker numpy python-dotenv
"""

import random
import numpy as np
from datetime import datetime
from faker import Faker
from elasticsearch import Elasticsearch
from dotenv import load_dotenv
import os

load_dotenv()

# ── Connection ────────────────────────────────────────────────────────────────
ES_URL     = os.getenv("ES_URL", "http://localhost:9200")
ES_API_KEY = os.getenv("ES_API_KEY")

es = (
  Elasticsearch(ES_URL, api_key=ES_API_KEY)
)

fake = Faker()
random.seed(42)
np.random.seed(42)

# ── Constants ─────────────────────────────────────────────────────────────────
INDUSTRIES    = ["fintech", "healthcare", "retail", "logistics", "public sector", "insurance"]
PHASES        = ["discovery", "design", "delivery", "stabilisation", "closeout"]
OUTCOMES      = ["rescued", "escalated", "delivered_clean", "lost"]
INTERVENTIONS = [
    "internal_reallocation",
    "client_escalation",
    "scope_renegotiation",
    "timeline_extension",
    "team_augmentation",
    "exec_intervention",
]
PROJECT_SUFFIXES = [
    "Transformation", "Migration", "Implementation",
    "Optimisation", "Integration", "Modernisation"
]


# ── Fingerprint ───────────────────────────────────────────────────────────────
def make_fingerprint(
    burn_rate_acceleration: float,
    velocity_delta: float,
    sentiment_slope: float,
    phase: str,
    team_size: int,
    client_tenure_months: int,
    days_to_milestone: int,
    margin_at_risk_pct: float,
) -> list[float]:
    return [
        float(np.clip(burn_rate_acceleration, -1, 1)),
        float(np.clip(velocity_delta, -1, 1)),
        float(np.clip(sentiment_slope, -1, 1)),
        float(PHASES.index(phase) / (len(PHASES) - 1)),
        float(min(team_size / 20, 1.0)),
        float(min(client_tenure_months / 36, 1.0)),
        float(min(days_to_milestone / 60, 1.0)),
        float(np.clip(margin_at_risk_pct / 50, -1, 1)),
    ]


# ── Generate historical projects ──────────────────────────────────────────────
def generate_historical(n: int = 60) -> list[dict]:
    docs = []
    outcome_weights = [0.35, 0.25, 0.30, 0.10]

    for i in range(n):
        outcome   = random.choices(OUTCOMES, weights=outcome_weights)[0]
        phase     = random.choice(PHASES)
        industry  = random.choice(INDUSTRIES)
        team_size = random.randint(3, 18)
        tenure    = random.randint(1, 48)
        milestone = random.randint(5, 55)

        # Distress severity scales with outcome badness
        severity = {"rescued": 0.5, "escalated": 0.7, "delivered_clean": 0.1, "lost": 0.9}[outcome]

        burn_acc    = round(random.uniform(0.1 * severity, severity), 3)
        vel_delta   = round(random.uniform(-severity, -0.05 * severity), 3)
        sent_slope  = round(random.uniform(-severity, 0.1), 3)
        margin_risk = round(random.uniform(10 * severity, 50 * severity), 1)

        margin_impact = {
            "rescued":         round(random.uniform(-15, -5), 1),
            "escalated":       round(random.uniform(-30, -15), 1),
            "delivered_clean": round(random.uniform(-5, 5), 1),
            "lost":            round(random.uniform(-50, -30), 1),
        }[outcome]

        closed = fake.date_between(start_date="-3y", end_date="-1m")

        docs.append({
            "project_id":             f"HIST-{i+1:03d}",
            "project_name":           f"{fake.company()} {random.choice(PROJECT_SUFFIXES)}",
            "industry":               industry,
            "phase_at_detection":     phase,
            "team_size":              team_size,
            "client_tenure_months":   tenure,
            "days_to_milestone":      milestone,
            "burn_rate_acceleration": burn_acc,
            "velocity_delta":         vel_delta,
            "sentiment_slope":        sent_slope,
            "margin_at_risk_pct":     margin_risk,
            "intervention":           random.choice(INTERVENTIONS),
            "outcome":                outcome,
            "margin_impact_pct":      margin_impact,
            "weeks_to_resolution":    random.randint(1, 8),
            "partner_overrode_agent": random.random() < 0.2,
            "notes":                  fake.sentence(nb_words=12),
            "closed_date":            closed.isoformat(),
            "fingerprint":            make_fingerprint(
                burn_acc, vel_delta, sent_slope,
                phase, team_size, tenure, milestone, margin_risk
            ),
        })

    return docs


# ── Bulk index ────────────────────────────────────────────────────────────────
def bulk_index(index: str, docs: list[dict], id_field: str):
    operations = []
    for doc in docs:
        operations.append({"index": {"_index": index, "_id": doc[id_field]}})
        operations.append(doc)

    resp   = es.bulk(operations=operations)
    errors = [item for item in resp["items"] if "error" in item.get("index", {})]

    status = f"{len(docs) - len(errors)}/{len(docs)} indexed"
    if errors:
        status += f" | {len(errors)} errors: {errors[0]}"
    print(f"  {index}: {status}")


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n=== Generating historical project data ===\n")

    info = es.info()
    print(f"Connected: {info['cluster_name']} (v{info['version']['number']})\n")

    print("Indexing 60 historical projects...")
    historical = generate_historical(60)
    bulk_index("projects_historical", historical, "project_id")

    count = es.count(index="projects_historical")["count"]
    print(f"\n✅ Done — {count} historical projects in Elasticsearch")
    print("\nNext: paste elastic/bulk/*.ndjson into Kibana Dev Tools")
    print("      for live projects, sentiment, and playbooks.\n")