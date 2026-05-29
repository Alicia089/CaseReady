import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from agent.case_agent import brief_surgeon
from agent.models import SurgeryBrief
from api.auth import require_api_key

app = FastAPI(
    title="CaseReady API",
    description="AI-powered surgical coordination — pre-OR readiness briefing for surgeons.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend domain in production
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_DATA_PATH = Path(__file__).parent.parent / "data" / "sample_cases.json"


def _load_cases() -> list[dict]:
    return json.loads(_DATA_PATH.read_text())["cases"]


@app.get("/health")
def health():
    """Health check — no auth required."""
    return {"status": "ok", "service": "CaseReady", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/cases", dependencies=[Depends(require_api_key)])
def list_cases():
    """
    List all cases with basic info.
    In production this queries the database filtered by today's date and the caller's facility.
    """
    cases = _load_cases()
    return [
        {
            "case_id": c["case_id"],
            "patient_name": c["patient"]["name"],
            "procedure": c["procedure"]["type"],
            "surgeon": c["surgeon"]["name"],
            "or_time": c["procedure"]["or_time"],
            "or_room": c["procedure"]["or_room"],
            "scheduled_date": c["procedure"]["scheduled_date"],
        }
        for c in cases
    ]


@app.get("/cases/{case_id}", dependencies=[Depends(require_api_key)])
def get_case(case_id: str):
    """
    Return full case details for a given case ID.
    In production this queries the EHR/case management database.
    """
    cases = _load_cases()
    case = next((c for c in cases if c["case_id"] == case_id), None)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} not found")
    return case


@app.post("/brief/{case_id}", response_model=SurgeryBrief, dependencies=[Depends(require_api_key)])
def get_brief(case_id: str):
    """
    Run the CaseReady briefing agent for a surgical case.
    Checks all five readiness dimensions and returns a structured SurgeryBrief.

    Readiness levels:
    - READY: Confirmed and verified across all dimensions
    - AT_RISK: One or more flags need attention before OR time
    - BLOCKED: Case cannot safely proceed without immediate action
    """
    cases = _load_cases()
    if not any(c["case_id"] == case_id for c in cases):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} not found")

    try:
        brief = brief_surgeon(case_id)
    except EnvironmentError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {str(e)}",
        )

    return brief


# AWS Lambda entry point — Mangum wraps the FastAPI ASGI app
handler = Mangum(app, lifespan="off")
