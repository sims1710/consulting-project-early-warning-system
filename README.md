# pulse
### Consulting Project Early Warning System

> Watches live consulting projects for compound distress signals, searches 60 historical cases for similar patterns, runs a Risk vs Recovery agent debate, and emails the partner before the margin is gone.

---

## The Problem

Consulting projects don't fail suddenly — they fail slowly, with visible signals scattered across tools that no one watches simultaneously. Budget burn accelerates. Velocity drops. Client emails get shorter and more pointed. By the time a partner notices, the margin is already gone and the relationship is damaged.

The signals exist. No one is correlating them.

---

## How pulse Works

Five agents, one pipeline, one email.
```
Live Projects (ES|QL)
       │
       ▼
 [Sensor Agent] ──── compound signal detection + 4-week trend analysis
       │
       ▼
[Diagnosis Agent] ── k-NN vector search against 60 historical projects
       │
       ├──────────────────────┐
       ▼                      ▼
 [Risk Agent]          [Recovery Agent]
 conservative          internal resolution
 intervention          argument
       │                      │
       └──────────┬───────────┘
                  ▼
          [Arbiter Agent] ─── weighs debate, applies confidence spectrum
                  │
         ┌────────┼────────┐
         ▼        ▼        ▼
       AUTO     DRAFT   ESCALATE
      execute  approval  urgent
      + email  + email   email
                  │
                  ▼
         [pulse_decisions] ── full reasoning trail indexed back
```

---

## Agent Roles

| Agent | Tools | Job |
|---|---|---|
| Sensor | `pulse-sensor`, `pulse-trend-analysis`, `pulse-sentiment-trend` | Detects compound distress + 4-week trajectory |
| Diagnosis | `pulse-historical-search`, `pulse-playbooks` | k-NN search for similar historical cases |
| Risk | `pulse-historical-search` | Argues for conservative intervention with evidence |
| Recovery | `pulse-historical-search`, `pulse-playbooks` | Argues for internal resolution with evidence |
| Arbiter | `pulse-historical-search` | Weighs debate, decides, triggers email |

---

## The Distress Fingerprint

Each project is encoded as an 8-dimensional vector for k-NN similarity search:
```
[burn_rate_acceleration, velocity_delta, sentiment_slope,
 phase, team_size, client_tenure, days_to_milestone, margin_at_risk]
```

When a live project triggers the sensor, the Diagnosis Agent finds historical projects with structurally similar distress profiles — not keyword matches, but projects that failed or were rescued under comparable conditions.

---

## Confidence-Calibrated Action Spectrum

| Confidence | Action |
|---|---|
| > 85% | Auto-execute + FYI email to partner |
| 60-85% | Block action + approval request email |
| < 60% | Block action + urgent escalation email |

The Arbiter is required to run an additional historical search before deciding if the Risk and Recovery agents disagree by more than 0.15 confidence points.

---

## Data Architecture

| Index | Contents | Size |
|---|---|---|
| `projects_historical` | 60 past engagements in 6 scenario clusters | 60 docs |
| `projects_live` | Current project snapshots | 3 docs |
| `projects_live_timeseries` | 4-week weekly history per project | 12 docs |
| `projects_sentiment` | 14-day client sentiment time series | 15 docs |
| `project_playbooks` | Intervention strategies with success rates | 4 docs |
| `pulse_decisions` | Full reasoning trail for every pipeline run | grows |
| `pulse_actions` | Structured action records for auto_execute | grows |

### Historical Data Clusters

| Cluster | Industry | Phase | Pattern | Typical Outcome |
|---|---|---|---|---|
| A | Fintech | Delivery | Scope creep | Escalated |
| B | Healthcare | Delivery | Team burnout | Rescued via reallocation |
| C | Retail | Design | Sentiment drop | Mixed |
| D | Logistics | Stabilisation | Budget overrun | Lost |
| E | Public sector | Discovery | Velocity drop | Rescued via timeline extension |
| F | Insurance | Closeout | Late scope change | Mixed |

---

## Project Structure
```
pulse/
├── agents/
│   ├── pulse-sensor-agent.txt        # Sensor agent role + instructions
│   ├── pulse-diagnosis-agent.txt     # Diagnosis agent role + instructions
│   ├── pulse-risk-agent.txt          # Risk agent role + instructions
│   ├── pulse-recovery-agent.txt      # Recovery agent role + instructions
│   └── pulse-arbiter-agent.txt       # Arbiter agent role + instructions
│
├── component_templates/              # Elastic component templates (mappings)
│   ├── live-timeseries-mappings.json
│   ├── decisions-mappings.json
│   ├── historical-mappings.json
│   ├── sentiment-mappings.json
│   ├── playbooks-mappings.json
│   └── actions-mappings.json
│
├── index_templates/                  # Composable index templates
│   ├── pulse-live.json
│   ├── pulse-historical.json
│   ├── pulse-playbooks.json
│   └── pulse-sentiment.json
│
├── data/                             # Seed data
│   ├── projects_live.ndjson
│   ├── projects_live_timeseries.ndjson
│   ├── projects_sentiment.ndjson
│   ├── project_playbooks.ndjson
│   └── bulk_commands.ps1
│
├── saved_objects/                    # Kibana exports (dashboards + data views)
│
├── scripts/                          # Python orchestration layer
│   ├── orchestrator.py               # Main pipeline — chains all 5 agents
│   ├── action_executor.py            # Creates action records for auto_execute
│   ├── feedback_loop.py              # Records partner decisions back to ES
│   └── generate_historical_data.py  # Generates 60 clustered historical projects
│
├── tools/                            # Agent tool definitions
│   ├── pulse-sensor.json
│   ├── pulse-historical-search.json
│   ├── pulse-playbooks.json
│   ├── pulse-sentiment-trend.json
│   └── pulse-trend-analysis.json
│
├── settings/
│   └── settings.json
│
├── .env.example
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Setup

### Prerequisites
- Elasticsearch Serverless project (Elastic Cloud)
- Kibana Agent Builder enabled
- Python 3.10+
- Gmail account with App Password

### Installation
```bash
git clone https://github.com/sims1710/consulting-project-early-warning-system
cd consulting-project-early-warning-system
pip install -r requirements.txt
cp .env.example .env
# fill in .env with your credentials
```

### Environment variables
```
ES_URL=https://your-project.es.us-central1.gcp.elastic.cloud
ES_API_KEY=your_api_key
KIBANA_URL=https://your-project.kb.us-central1.gcp.elastic.cloud

AGENT_ID_SENSOR=
AGENT_ID_DIAGNOSIS=
AGENT_ID_RISK=
AGENT_ID_RECOVERY=
AGENT_ID_ARBITER=

EMAIL_SENDER=your@gmail.com
EMAIL_PASSWORD=your-16-char-app-password
EMAIL_RECIPIENT=partner@example.com
```

### Load data
```bash
# Generate and index 60 historical projects
python scripts/generate_historical_data.py

# Load static data (Windows)
scripts/data/bulk_commands.ps1
```

### Run
```bash
python scripts/orchestrator.py
```

---

## Built With

- **Elasticsearch** — k-NN vector search, ES|QL compound queries, bulk indexing
- **Kibana Agent Builder** — 5 native agents with tool orchestration
- **Elastic Serverless** — GCP us-central1
- **Claude (Anthropic)** — LLM powering all agents
- **Python** — orchestration, data generation, email alerting
- **Gmail SMTP** — HTML partner alert emails
- **NumPy / Faker** — clustered synthetic data generation
