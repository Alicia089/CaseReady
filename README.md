# CaseReady

AI-powered surgical coordination for ambulatory surgery centers. CaseReady automates the 48-hour pre-surgery readiness window — vendor confirmations, loaner tray sterilization, implant inventory verification, preference card compliance, and patient prep — so surgeons walk into the OR knowing every dimension of their case is confirmed.

> Built by Komereglissade · Clinical AI Systems · Atlanta, GA

---

## The Problem

OR coordinators at ASCs manually stitch together 6 disconnected systems to confirm case readiness. Vendor reps go silent. Loaner trays arrive too late for sterilization. Implant sizes aren't verified against inventory. Surgeons find out about failures in the OR.

No existing ASC platform automates this coordination layer with AI. CaseReady does.

---

## Surgery Briefing Agent

The core of this repo is a Claude-powered agentic system that gives surgeons a **complete, structured readiness brief** for their case — before they enter the OR.

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

### Sample output

```
================================================================
  CASEREADY SURGERY BRIEF
================================================================
  Case:      CR-2026-0841
  Patient:   Margaret T.
  Procedure: Total Knee Arthroplasty — Right
  Surgeon:   Dr. James Hayes
  OR Time:   07:30  |  Room: OR-2
  Status:    READY
----------------------------------------------------------------

  Vendor / Rep  [READY]
    Kyle Marsh (Zimmer Biomet) confirmed via email 05-28. Components in transit, ETA 05:30.

  SPD / Sterilization  [READY]
    All 3 trays received 05-28, steam autoclave complete 16:45. Stored in SPD Cabinet 4B.

  Implant Inventory  [READY]
    All Persona Knee components verified on-site by Lisa Monroe RN. Backup sizes available.

  Preference Card  [READY]
    Card verified by Amanda Torres CST. Tourniquet 300mmHg, pulse lavage before cementing.

  Patient Prep  [READY]
    Pre-op complete. Consents signed, H&P current, NPO confirmed, labs reviewed.
================================================================
```

---

## Quick Start

```bash
git clone https://github.com/Alicia089/CaseReady.git
cd CaseReady
pip install -r requirements.txt
cp .env.example .env   # add your ANTHROPIC_API_KEY

# Brief a surgeon on case CR-2026-0841 (ready case)
python -m agent.case_agent --case CR-2026-0841

# Brief a surgeon on case CR-2026-0842 (blocked case — vendor unconfirmed, trays not received)
python -m agent.case_agent --case CR-2026-0842

# JSON output
python -m agent.case_agent --case CR-2026-0841 --json
```

---

## Project Structure

```
CaseReady/
  agent/
    case_agent.py         ← Claude agentic loop with tool use
    tools.py              ← Five readiness check tools + tool definitions
    models.py             ← Pydantic schemas (SurgeryBrief, DimensionStatus)
    prompts.py            ← System prompt for the briefing agent
  data/
    sample_cases.json     ← Two realistic surgical cases (one ready, one blocked)
  requirements.txt
  .env.example
```

---

## How the Agent Works

The agent uses Claude's tool use API in an agentic loop:

1. Surgeon requests a brief for a case ID
2. Claude calls all five readiness tools in sequence
3. Each tool queries the case data and returns structured JSON
4. Claude synthesizes results into a `SurgeryBrief` with per-dimension status and critical actions
5. The brief is returned as a structured Pydantic object and printed to the terminal

```
Surgeon request
    → Claude (claude-sonnet-4-6)
        → check_vendor_status(case_id)
        → check_spd_status(case_id)
        → check_implant_inventory(case_id)
        → check_preference_card(case_id)
        → check_patient_prep(case_id)
    → Structured SurgeryBrief
        → READY / AT_RISK / BLOCKED per dimension
        → Critical actions list
        → Surgeon notes
```

---

## Skills

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Claude API](https://img.shields.io/badge/Claude%20API-tool%20use-purple)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-green)
![Healthcare AI](https://img.shields.io/badge/Healthcare%20AI-ASC%20Coordination-red)
