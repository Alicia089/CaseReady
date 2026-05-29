# CaseReady

AI-powered surgical coordination for ambulatory surgery centers. CaseReady automates the 48-hour pre-surgery readiness window — vendor confirmations, loaner tray sterilization, implant inventory verification, preference card compliance, and patient prep — so surgeons walk into the OR knowing every dimension of their case is confirmed.

> Built by Komereglissade · Clinical AI Systems · Atlanta, GA

---

## The Problem

OR coordinators at ASCs manually stitch together 6 disconnected systems to confirm case readiness. Vendor reps go silent. Loaner trays arrive too late for sterilization. Implant sizes aren't verified against inventory. Surgeons find out about failures in the OR.

No existing ASC platform automates this coordination layer with AI. CaseReady does.

---

## Architecture

```
Surgeon / OR Coordinator
        │
   API Gateway (AWS)
        │
   Lambda + FastAPI        ← api/main.py
        │
   CaseReady Agent         ← agent/case_agent.py
        │
   ┌────┴────┬────────────┬──────────────┬──────────────┐
Vendor     SPD        Inventory   Preference     Patient
Status   Status       Status        Card          Prep
        │
  Claude claude-sonnet-4-6 (tool use)
        │
   SurgeryBrief (Pydantic)
        READY / AT_RISK / BLOCKED per dimension
```

---

## Surgery Briefing Agent

The core is a Claude-powered agentic system that gives surgeons a **complete, structured readiness brief** before they enter the OR.

### What it checks

| Dimension | What it verifies |
|-----------|-----------------|
| **Vendor / Rep** | Confirmation received, method, rep present day-of |
| **SPD / Sterilization** | Trays received, autoclave complete, sterility expiry, storage location |
| **Implant Inventory** | All components on-site, verified by scrub tech, backup sizes available |
| **Preference Card** | Card verified against this specific case, special requests surfaced |
| **Patient Prep** | Consents, H&P, NPO, labs reviewed, imaging available, allergy flags |

### Readiness levels

- `READY` — Confirmed and verified, no issues
- `AT_RISK` — Unresolved flag that needs attention before OR time
- `BLOCKED` — Case cannot safely proceed without immediate action

---

## Quick Start (local)

```bash
git clone https://github.com/Alicia089/CaseReady.git
cd CaseReady
pip install -r requirements.txt
cp .env.example .env      # fill in ANTHROPIC_API_KEY and CASEREADY_API_KEY

# Run the API server
uvicorn api.main:app --reload

# Or run the CLI directly
python -m agent.case_agent --case CR-2026-0841
python -m agent.case_agent --case CR-2026-0842   # blocked case
```

---

## API Endpoints

All endpoints (except `/health`) require the header `X-API-Key: <your-key>`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check — no auth required |
| `GET` | `/cases` | List today's cases with patient, surgeon, OR time |
| `GET` | `/cases/{case_id}` | Full case details |
| `POST` | `/brief/{case_id}` | Run the briefing agent — returns `SurgeryBrief` |

### Example: get a surgery brief

```bash
curl -X POST https://your-api-url/brief/CR-2026-0841 \
  -H "X-API-Key: your-key"
```

```json
{
  "case_id": "CR-2026-0841",
  "patient_name": "Margaret T.",
  "procedure": "Total Knee Arthroplasty",
  "surgeon": "Dr. James Hayes",
  "or_time": "07:30",
  "or_room": "OR-2",
  "overall_status": "READY",
  "vendor":        { "status": "READY",   "summary": "Kyle Marsh confirmed via email..." },
  "spd":           { "status": "READY",   "summary": "All trays sterilized, stored in SPD Cabinet 4B" },
  "inventory":     { "status": "READY",   "summary": "All Persona components verified on-site" },
  "preference_card": { "status": "READY", "summary": "Card verified by Amanda Torres CST" },
  "patient_prep":  { "status": "READY",   "summary": "Pre-op complete, no flags" },
  "critical_actions": ["Confirm component arrival at 05:30 with Kyle Marsh before patient transport"],
  "surgeon_notes": "Clean case. Components in transit — confirm on-site before bringing patient to OR."
}
```

---

## Deploy to AWS

### Prerequisites
- AWS CLI configured (`aws configure`)
- Docker running
- SAM CLI installed (`brew install aws-sam-cli` or see [AWS docs](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html))

### Store secrets in AWS Secrets Manager

```bash
# Anthropic API key
aws secretsmanager create-secret \
  --name caseready/anthropic-key \
  --secret-string '{"key":"sk-ant-..."}'

# CaseReady API key (any strong random string)
aws secretsmanager create-secret \
  --name caseready/api-secret \
  --secret-string '{"key":"your-strong-api-key"}'
```

### Deploy

```bash
chmod +x infra/deploy.sh
./infra/deploy.sh staging      # staging environment
./infra/deploy.sh production   # production environment
```

The script builds the Docker image, pushes to ECR, and deploys the Lambda + API Gateway stack via SAM. Prints the live API URL when done.

---

## Project Structure

```
CaseReady/
  agent/
    case_agent.py         ← Claude agentic loop with tool use
    tools.py              ← Five readiness check tools
    models.py             ← Pydantic schemas (SurgeryBrief, DimensionStatus)
    prompts.py            ← System prompt
  api/
    main.py               ← FastAPI app + Mangum Lambda handler
    auth.py               ← API key auth (Cognito-ready)
  data/
    sample_cases.json     ← Two sample cases (one READY, one BLOCKED)
  infra/
    template.yaml         ← AWS SAM (Lambda + API Gateway + ECR + CloudWatch)
    deploy.sh             ← One-command deploy script
  Dockerfile              ← Lambda container image
  requirements.txt
  .env.example
```

---

## Production Roadmap

| Phase | What gets added |
|-------|----------------|
| ✅ **Done** | Agent, API, AWS deployment config |
| **Next** | PostgreSQL/RDS — replace sample JSON with real case database |
| **Next** | AWS Cognito — replace API key auth with surgeon/staff login |
| **Later** | Epic FHIR integration — live EHR data |
| **Later** | Vendor portal + SPD system integrations |
| **Later** | Web dashboard + mobile brief view |
| **Later** | SNS push alerts when a case goes BLOCKED |

---

## Skills

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Claude API](https://img.shields.io/badge/Claude%20API-tool%20use-purple)
![AWS Lambda](https://img.shields.io/badge/AWS-Lambda%20%2B%20API%20Gateway-orange)
![Docker](https://img.shields.io/badge/Docker-ECR-blue)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-green)
