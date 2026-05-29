# CaseReady — Full Demo Setup Runbook

**Project:** CaseReady by Komereglissade  
**What it is:** An AI agent that gives surgeons and OR coordinators a complete pre-surgery readiness brief across 5 dimensions — vendor confirmation, SPD sterilization, implant inventory, preference card, and patient prep.  
**Built on:** Python + Claude API + FastAPI + AWS Lambda + Docker + GitHub

---

## Part 1 — What We Built and Why

Before the step-by-step, here is the architecture so you understand what each piece does and why it exists.

```
dashboard.html  (what the coordinator sees in the browser)
      ↓  calls
AWS API Gateway + Lambda Function URL  (the live HTTPS endpoint)
      ↓  runs
FastAPI app  (api/main.py — routes requests to the right place)
      ↓  calls
CaseReady Agent  (agent/case_agent.py — the AI brain)
      ↓  uses
Claude claude-sonnet-4-6 with 5 tool calls
      ↓  reads from
data/sample_cases.json  (case data — replace with real DB in production)
      ↓  returns
SurgeryBrief  (structured JSON with READY / AT_RISK / BLOCKED per dimension)
```

**Why Lambda?**  
Lambda is a serverless function on AWS. You don't manage a server — you just deploy code and AWS runs it on demand. You only pay when someone actually calls your API (roughly $0.0000002 per request — essentially free at demo scale).

**Why Docker?**  
Docker packages your entire application — Python, all libraries, all code — into a single portable container image. AWS Lambda needs this image to know exactly what environment to run your code in. Without Docker, Lambda wouldn't know which version of Python or which libraries to use.

**Why FastAPI?**  
FastAPI is a Python web framework that turns your agent into a real HTTP API. Without it, there's no way to call your agent from a browser or another system. It handles routing (`/health`, `/cases`, `/brief/{id}`), authentication, and error handling.

**Why Mangum?**  
Mangum is the bridge between AWS Lambda and FastAPI. Lambda expects a specific event format; FastAPI expects HTTP requests. Mangum translates between the two so FastAPI runs inside Lambda without changes.

---

## Part 2 — Step-by-Step: What We Did

### Step 1 — Built the Agent Core

**Files created:**
- `agent/models.py` — Defines the data shapes using Pydantic. `SurgeryBrief` is the main output schema. `DimensionStatus` holds the status (READY/AT_RISK/BLOCKED), a summary, flags, and action required for each of the 5 dimensions.
- `agent/prompts.py` — The system prompt that tells Claude what role it plays. It instructs Claude to call all 5 tools before forming any assessment, to be direct, and to output structured JSON.
- `agent/tools.py` — Five Python functions that each retrieve one dimension of readiness data:
  - `check_vendor_status(case_id)` — Was the vendor rep confirmed? When? Will they be present?
  - `check_spd_status(case_id)` — Were loaner trays received? Is sterilization complete?
  - `check_implant_inventory(case_id)` — Are all implant components on site and verified?
  - `check_preference_card(case_id)` — Was the surgeon's preference card verified for this specific case?
  - `check_patient_prep(case_id)` — Are consents signed, labs reviewed, NPO confirmed?
  
  Each tool also contains its `TOOL_DEFINITIONS` — a JSON schema that tells Claude what the tool does and what parameters it takes. This is how Claude knows to call `check_vendor_status` with a `case_id` argument.

- `agent/case_agent.py` — The main agent loop. Here is exactly what happens when you call `brief_surgeon("CR-2026-0841")`:
  1. Sends a message to Claude asking for a complete brief
  2. Claude reads the system prompt and decides to call `check_vendor_status`
  3. The code intercepts that tool call, runs the Python function, and sends the result back to Claude
  4. Claude then calls `check_spd_status`, then `check_implant_inventory`, and so on until all 5 tools are called
  5. Once all 5 results are in, Claude synthesizes everything into a `SurgeryBrief` JSON object
  6. The code parses that JSON into a Pydantic `SurgeryBrief` and returns it
  
  This loop (send → tool call → result → next tool call → ... → final response) is called an **agentic loop**. It continues until Claude stops calling tools and produces a final text response.

**Why this architecture?**  
If you just asked Claude "is this case ready?" it would hallucinate or guess. By forcing it to call real data tools first, every statement in the brief is grounded in actual case data. The AI handles reasoning and synthesis; the tools handle facts.

---

### Step 2 — Built the Sample Data

**File created:** `data/sample_cases.json`

This file contains 4 simulated surgical cases with realistic data:
- Patient demographics (name, DOB, ASA class, weight)
- Procedure details (type, OR room, time, CPT code)
- Surgeon info
- Implant system details (manufacturer, rep name, rep phone, component sizes)
- Loaner tray IDs and sterilization deadlines
- Anesthesia plan

It also contains the "live" status for each case — vendor confirmation status, SPD receipt status, inventory verification, preference card status, and patient prep flags.

**Two purposely different scenarios:**
- `CR-2026-0841` and `CR-2026-0843` — READY cases. Everything confirmed, sterilized, verified.
- `CR-2026-0842` — BLOCKED case. Vendor not responding for 3 days, trays not received, labs unreviewed.
- `CR-2026-0844` — AT_RISK case. Vendor only partially confirmed, everything else green.

This range demonstrates the value of the system to a hospital administrator: one view tells you which cases are safe to run and exactly what needs action on the others.

---

### Step 3 — Built the API Layer

**Files created:**
- `api/auth.py` — API key authentication. Every request to a protected endpoint must include the header `X-API-Key: <your-key>`. Without it the API returns 401 Unauthorized. This is designed to be swapped for AWS Cognito (proper user login with username/password) later without changing any endpoint code.
- `api/main.py` — The FastAPI application with 4 endpoints:
  - `GET /health` — No auth required. Returns `{"status":"ok"}`. Used by monitoring tools to check if the service is up.
  - `GET /cases` — Returns the list of today's cases with basic info (procedure, surgeon, OR room, time).
  - `GET /cases/{case_id}` — Returns full case details for one case.
  - `POST /brief/{case_id}` — Runs the agent and returns a complete `SurgeryBrief`. This is the main endpoint. It first checks the cache (`data/sample_briefs.json`). If a cached brief exists it returns instantly. If not, it runs the live agent.

The file ends with:
```python
handler = Mangum(app, lifespan="off")
```
This single line is what makes the entire FastAPI app work inside AWS Lambda. Mangum wraps the app and translates AWS Lambda's event format into the HTTP request format FastAPI understands.

---

### Step 4 — Built the Docker Container

**File created:** `Dockerfile`

```dockerfile
FROM public.ecr.aws/lambda/python:3.11   ← Start from Amazon's official Lambda Python image
WORKDIR ${LAMBDA_TASK_ROOT}              ← Set the working directory Lambda expects
COPY requirements.txt .                  ← Copy dependency list
RUN pip install -r requirements.txt      ← Install all Python libraries
COPY agent/ agent/                       ← Copy the agent code
COPY api/ api/                           ← Copy the API code
COPY data/ data/                         ← Copy the sample data
CMD ["api.main.handler"]                 ← Tell Lambda to call the Mangum handler
```

**What Docker actually did in our process:**

1. `docker build` — Read the Dockerfile top to bottom and created a container image. This image contains Python 3.11, all your libraries (anthropic, fastapi, pydantic, mangum, etc.), and all your code.

2. `docker push` — Uploaded that image to **ECR** (Elastic Container Registry) — Amazon's private container storage. Think of ECR like a private GitHub, but instead of storing code it stores container images.

3. When Lambda runs, it pulls that image from ECR and executes it. Your code runs inside that container in the cloud.

**Why you didn't see a container running:**  
Docker containers used for Lambda are not "always running" like a normal server. The container starts up when an API request comes in (called a **cold start** — this is why the first request takes a few seconds), handles the request, and then shuts down. You won't see it running in Docker Desktop because it runs inside AWS, not on your machine. In Docker Desktop you can see the image under the **Images** tab — that's the packaged application before it gets sent to AWS.

**The platform issue we hit:**  
Docker Desktop on Windows by default builds images for multiple platforms (called a manifest list). AWS Lambda only accepts single-platform images for `linux/amd64`. We had to use:
```bash
docker buildx build --platform linux/amd64 --provenance=false
```
The `--provenance=false` flag prevents Docker from adding attestation metadata that turns it into a multi-platform manifest list.

---

### Step 5 — Stored Secrets in AWS

**Why secrets matter:**  
Your Anthropic API key and CaseReady API key should never be hardcoded in code or committed to GitHub. If they were, anyone who clones your repo could use your Anthropic account and run up charges.

We stored them in **AWS Secrets Manager**:
```
caseready/anthropic-key  →  your Anthropic API key (sk-ant-...)
caseready/api-secret     →  your CaseReady API key (Y8a1GjW0...)
```

The Lambda function pulls these at runtime using IAM permissions. The keys are never in your code — Lambda asks AWS "give me the secret named caseready/anthropic-key" and AWS checks that the Lambda has permission to access it before returning the value.

---

### Step 6 — Deployed to AWS with SAM

**File created:** `infra/template.yaml`

SAM (Serverless Application Model) is AWS's tool for deploying serverless infrastructure. The template describes everything that needs to exist in AWS:

| Resource | What it is | Why it exists |
|---------|-----------|---------------|
| `CaseReadyFunction` | The Lambda function | Runs your agent code |
| `CaseReadyHttpApi` | API Gateway | Public HTTPS endpoint with routing |
| `CaseReadyFunctionUrl` | Lambda Function URL | Direct URL with no timeout limit (for `/brief`) |
| `CaseReadyFunctionRole` | IAM Role | Gives Lambda permission to read secrets and write logs |
| `CaseReadyLogGroup` | CloudWatch Log Group | Stores logs for every request (90-day retention) |

**The deploy process:**
1. SAM uploaded the template to S3
2. AWS CloudFormation read the template and created all 5 resources in the right order
3. Lambda got configured to pull the container image from ECR
4. API Gateway got configured to route requests to Lambda
5. IAM role got permissions to read from Secrets Manager

**The timeout problem we solved:**  
API Gateway has a hard 29-second timeout. Our agent calls Claude with 5 tool calls which takes 30-60 seconds. We added a Lambda Function URL (separate from API Gateway) which has no timeout limit. The `/brief` endpoint uses the Function URL; the other endpoints use API Gateway.

---

### Step 7 — Built the Dashboard

**File created:** `dashboard.html`

A single HTML file with inline CSS and JavaScript. No build step, no React, no npm. Open it in any browser and it works.

**How it works:**
1. On load it immediately shows embedded sample data (works from `file://`)
2. It simultaneously tries to call the live AWS API
3. If the API responds (when served from a real server), it replaces the embedded data with live data
4. Each row in the table is clickable — clicking expands a detail panel showing all 5 dimensions

**Why embedded data?**  
Browsers block API calls from `file://` URLs for security (CORS policy). Since you're opening the file directly from your Desktop, the browser won't let it call the AWS API. The embedded data makes it work as a standalone demo file. When you eventually host it on a proper URL (Netlify, GitHub Pages, etc.) the live API calls will work automatically.

---

### Step 8 — Pushed to GitHub

Repository: `github.com/Alicia089/CaseReady`

Each commit tells the story:
1. `feat: CaseReady surgery briefing agent` — initial agent, tools, models, sample data
2. `feat: FastAPI wrapper + AWS SAM deployment config` — API layer and infra
3. `feat: live simulation with sample briefs + Lambda Function URL` — cached briefs, Function URL
4. `feat: coordinator morning view dashboard + 4 sample cases` — the dashboard
5. `fix: embed sample data so dashboard works from file://` — the CORS fix

---

## Part 3 — Your Live AWS Resources

| Resource | Location in AWS Console | Value |
|---------|------------------------|-------|
| Lambda function | Lambda → Functions → caseready-api-staging | Runs your agent |
| API Gateway | API Gateway → caseready-staging | Routes /health, /cases |
| Function URL | Lambda → caseready-api-staging → Configuration → Function URL | Routes /brief (no timeout) |
| Container image | ECR → caseready-staging | Your packaged app |
| Secrets | Secrets Manager → caseready/* | API keys |
| Logs | CloudWatch → Log groups → /aws/lambda/caseready-api-staging | Every request logged |
| Full stack | CloudFormation → caseready-staging → Resources | All 7 resources |

**Your API endpoints:**
```
Base URL:  https://onisg2kjda.execute-api.us-east-1.amazonaws.com
           https://ezsspeeaair46nqlxblyqkndle0rxoju.lambda-url.us-east-1.on.aws

GET  /health                    No auth — health check
GET  /cases                     X-API-Key header required
GET  /cases/{case_id}           X-API-Key header required
POST /brief/{case_id}           X-API-Key header required  ← use Function URL for this one
```

**Your API key:** `Y8a1GjW0lXpRJwcDOtzCugysP67on3Z4`

---

## Part 4 — How to Load Real Hospital Data

When a hospital gives you real data, here is exactly where each piece goes.

### Option A — Update the JSON files (fastest, no database needed)

Replace the contents of `data/sample_cases.json` with real case data following the same structure. Each case needs:

```json
{
  "case_id": "unique ID",
  "patient": {
    "name": "Patient name",
    "asa_class": "I / II / III / IV"
  },
  "procedure": {
    "type": "Procedure name",
    "or_time": "07:30",
    "or_room": "OR-1",
    "scheduled_date": "2026-06-15"
  },
  "surgeon": {
    "id": "unique surgeon ID",
    "name": "Dr. Full Name"
  },
  "implant_system": {
    "manufacturer": "Zimmer Biomet / Medtronic / DePuy / Arthrex / Stryker",
    "system": "System name",
    "rep_name": "Rep Full Name",
    "rep_phone": "404-555-0000"
  },
  "loaner_tray": {
    "tray_ids": ["TRAY-001", "TRAY-002"],
    "required_by": "2026-06-14T16:00:00"
  },
  "anesthesia": {
    "type": "General / Spinal / Regional",
    "provider": "Dr. Name, CRNA"
  }
}
```

And add corresponding status records in:
- `vendor_status` — did the rep confirm?
- `spd_status` — are trays received and sterilized?
- `inventory_status` — are components on site?
- `preference_cards` — is the surgeon's card verified?
- `patient_prep` — is the patient ready?

Then rebuild and redeploy:
```bash
docker buildx build --platform linux/amd64 --provenance=false -t 975050128851.dkr.ecr.us-east-1.amazonaws.com/caseready-staging:latest --push .
aws lambda update-function-code --function-name caseready-api-staging --image-uri 975050128851.dkr.ecr.us-east-1.amazonaws.com/caseready-staging:latest --region us-east-1
```

---

### Option B — Connect to a Real Database (production path)

Replace the 5 tool functions in `agent/tools.py`. Right now each tool reads from the JSON file. You swap that read for a database query.

**Example — vendor status from a real database:**

```python
# Current (reads JSON)
def check_vendor_status(case_id: str) -> dict:
    data = _load()
    vendor = data["vendor_status"].get(case_id, {})
    return { ... }

# Production (reads from PostgreSQL/RDS)
import psycopg2

def check_vendor_status(case_id: str) -> dict:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT * FROM vendor_confirmations WHERE case_id = %s", (case_id,))
    row = cur.fetchone()
    return { "confirmed": row["confirmed"], "rep_name": row["rep_name"], ... }
```

The agent, the API, and the dashboard all stay exactly the same. You only change the internals of the 5 tool functions.

**Recommended AWS database:** RDS PostgreSQL (managed, HIPAA-eligible, automatic backups).

---

### Option C — Connect to the Hospital's EHR System

Most large hospitals run Epic. Epic exposes data through **FHIR APIs** (a healthcare data standard).

The tool functions would call Epic's API:

```python
import requests

def check_patient_prep(case_id: str) -> dict:
    # Call Epic FHIR API
    response = requests.get(
        f"https://hospital.epic.com/api/FHIR/R4/Appointment/{case_id}",
        headers={"Authorization": f"Bearer {epic_token}"}
    )
    appointment = response.json()
    # Map Epic data format → your tool output format
    return {
        "consents_signed": appointment["extension"]["consents_complete"],
        "labs_reviewed": appointment["extension"]["labs_reviewed"],
        ...
    }
```

**Note on Epic integration:** Epic requires a formal credentialing and app registration process. Plan 3-6 months for this. Start with the JSON or database approach for pilots and add Epic integration once you have paying customers.

---

### What HIPAA Requires When Using Real Data

Before loading real patient data, these things must be in place:

1. **Business Associate Agreement (BAA) with AWS** — AWS offers this. Go to AWS Console → Artifact → Agreements and sign the BAA.
2. **BAA with Anthropic** — Required before sending any PHI to Claude. Contact Anthropic's enterprise team.
3. **No PHI in Claude prompts** — The agent should pass `case_id` only, not patient names or dates of birth. Patient identity stays in your database; Claude only sees operational readiness data.
4. **Encryption** — AWS Lambda + RDS encrypt data at rest by default. Enable encryption in transit (TLS) for all database connections.
5. **Audit logging** — CloudWatch already logs every API call. For HIPAA you need to log who accessed which patient record and when.
6. **De-identify test data** — Never use real patient names/DOBs in your sample data files. The synthetic names in `sample_cases.json` (Margaret T., Robert K.) are correct — generic initials only, no real identifiers.

---

## Part 5 — Quick Reference: How to Re-Deploy

If you make changes to the code and need to push them to AWS:

```bash
# Step 1 — Authenticate Docker to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 975050128851.dkr.ecr.us-east-1.amazonaws.com

# Step 2 — Build and push new image
docker buildx build --platform linux/amd64 --provenance=false \
  -t 975050128851.dkr.ecr.us-east-1.amazonaws.com/caseready-staging:latest \
  --push \
  C:\Users\eradi\OneDrive\Desktop\CaseReady

# Step 3 — Tell Lambda to use the new image
aws lambda update-function-code \
  --function-name caseready-api-staging \
  --image-uri 975050128851.dkr.ecr.us-east-1.amazonaws.com/caseready-staging:latest \
  --region us-east-1
```

Lambda will update in about 30 seconds. The next request after that uses your new code.

---

## Summary

| What | Why | Where |
|------|-----|-------|
| Claude agent with 5 tools | AI reads real data before forming any assessment | `agent/` |
| FastAPI | Turns the agent into a callable HTTPS API | `api/` |
| Docker container | Packages everything into one portable image for AWS | `Dockerfile` |
| ECR | Stores the container image in AWS | AWS Console → ECR |
| Lambda | Runs the container on demand, no server to manage | AWS Console → Lambda |
| API Gateway + Function URL | Public HTTPS endpoints, routes requests to Lambda | AWS Console → API Gateway |
| Secrets Manager | Stores API keys safely, never in code | AWS Console → Secrets Manager |
| CloudWatch | Logs every request for debugging and audit trail | AWS Console → CloudWatch |
| dashboard.html | Coordinator's morning view, calls the live API | Open in browser |
| GitHub | Source of truth for all code | github.com/Alicia089/CaseReady |
