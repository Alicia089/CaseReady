import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pydantic import BaseModel
from typing import Optional

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

_DATA_PATH   = Path(__file__).parent.parent / "data" / "sample_cases.json"
_DB_PATH     = Path(__file__).parent.parent / "data" / "cases_db.json"
_BRIEFS_PATH = Path(__file__).parent.parent / "data" / "sample_briefs.json"


def _load_cases() -> list[dict]:
    cases = json.loads(_DATA_PATH.read_text())["cases"]
    if _DB_PATH.exists():
        db = json.loads(_DB_PATH.read_text())
        cases = cases + db.get("cases", [])
    return cases


def _load_db() -> dict:
    if _DB_PATH.exists():
        return json.loads(_DB_PATH.read_text())
    return {"cases": [], "vendor_status": {}, "spd_status": {}, "inventory_status": {}, "preference_cards": {}, "patient_prep": {}}


def _save_db(db: dict) -> None:
    _DB_PATH.write_text(json.dumps(db, indent=2))


def _load_cached_briefs() -> dict:
    if _BRIEFS_PATH.exists():
        return json.loads(_BRIEFS_PATH.read_text())
    return {}


# ── Intake form schema ────────────────────────────────────────────────────────
class IntakeForm(BaseModel):
    # Case basics
    scheduled_date: str
    or_room: str
    or_time: str
    estimated_duration_min: int = 90

    # Patient
    patient_name: str
    asa_class: str

    # Procedure
    procedure_type: str
    laterality: str = "N/A"
    cpt_code: str = ""

    # Surgeon
    surgeon_name: str

    # Implant
    manufacturer: str
    implant_system: str
    rep_name: str
    rep_phone: str
    component_sizes: str = ""

    # Loaner trays
    tray_ids: str = ""
    trays_required_by: str = ""
    spd_processor: str = ""

    # Anesthesia
    anesthesia_type: str
    anesthesia_provider: str

    # Vendor status
    vendor_confirmed: bool = False
    vendor_confirmation_method: Optional[str] = None
    vendor_notes: str = ""

    # SPD status
    trays_received: bool = False
    sterilization_complete: bool = False

    # Inventory
    inventory_verified: bool = False
    inventory_verified_by: str = ""

    # Preference card
    pref_card_verified: bool = False
    pref_card_verified_by: str = ""
    pref_card_special_requests: str = ""

    # Patient prep
    pre_op_complete: bool = False
    consents_signed: bool = False
    h_and_p_within_30_days: bool = False
    npo_confirmed: bool = False
    labs_reviewed: bool = False
    imaging_available: bool = False
    allergies_flagged: bool = False
    prep_flags: str = ""


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


@app.post("/cases", dependencies=[Depends(require_api_key)])
def create_case(form: IntakeForm):
    """
    Submit a new surgical case via the intake form.
    Generates a unique case ID, saves all readiness data, and returns the new case ID.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    case_id = f"CR-{datetime.now(timezone.utc).year}-{ts}"

    surgeon_id = f"DR-{form.surgeon_name.upper().replace(' ', '-').replace('.', '')}"

    new_case = {
        "case_id": case_id,
        "patient": {
            "name": form.patient_name,
            "asa_class": form.asa_class,
        },
        "procedure": {
            "type": form.procedure_type,
            "laterality": form.laterality,
            "cpt_code": form.cpt_code,
            "scheduled_date": form.scheduled_date,
            "or_time": form.or_time,
            "or_room": form.or_room,
            "estimated_duration_min": form.estimated_duration_min,
        },
        "surgeon": {
            "id": surgeon_id,
            "name": form.surgeon_name,
        },
        "implant_system": {
            "manufacturer": form.manufacturer,
            "system": form.implant_system,
            "rep_name": form.rep_name,
            "rep_phone": form.rep_phone,
            "component_sizes": form.component_sizes,
        },
        "loaner_tray": {
            "tray_ids": [t.strip() for t in form.tray_ids.split(",") if t.strip()],
            "required_by": form.trays_required_by,
            "spd_processor": form.spd_processor,
        },
        "anesthesia": {
            "type": form.anesthesia_type,
            "provider": form.anesthesia_provider,
        },
    }

    vendor_status = {
        case_id: {
            "confirmed": form.vendor_confirmed,
            "confirmation_method": form.vendor_confirmation_method,
            "confirmed_at": datetime.now(timezone.utc).isoformat() if form.vendor_confirmed else None,
            "rep_present": None,
            "notes": form.vendor_notes,
        }
    }

    spd_status = {
        case_id: {
            "trays_received": form.trays_received,
            "received_at": datetime.now(timezone.utc).isoformat() if form.trays_received else None,
            "sterilization_complete": form.sterilization_complete,
            "sterilization_method": "Steam autoclave" if form.sterilization_complete else None,
            "cycle_completed_at": datetime.now(timezone.utc).isoformat() if form.sterilization_complete else None,
            "sterility_expiry": None,
            "storage_location": None,
            "flags": [] if form.trays_received else ["TRAYS NOT RECEIVED"],
        }
    }

    inventory_status = {
        case_id: {
            "all_components_verified": form.inventory_verified,
            "on_site": form.inventory_verified,
            "verified_by": form.inventory_verified_by or None,
            "verified_at": datetime.now(timezone.utc).isoformat() if form.inventory_verified else None,
            "missing_components": [] if form.inventory_verified else ["Inventory not yet verified"],
            "backup_sizes_available": [],
        }
    }

    preference_cards = {
        surgeon_id: {
            "procedure": form.procedure_type,
            "last_updated": form.scheduled_date,
            "verified_against_case": form.pref_card_verified,
            "verified_by": form.pref_card_verified_by or None,
            "special_requests": [r.strip() for r in form.pref_card_special_requests.split(",") if r.strip()],
            "implant_notes": f"{form.implant_system} — verify with surgeon before case",
        }
    }

    prep_flags = [f.strip() for f in form.prep_flags.split(",") if f.strip()]
    if not form.labs_reviewed:
        prep_flags.append("LABS NOT REVIEWED")

    patient_prep = {
        case_id: {
            "pre_op_complete": form.pre_op_complete,
            "consents_signed": form.consents_signed,
            "h_and_p_within_30_days": form.h_and_p_within_30_days,
            "npo_confirmed": form.npo_confirmed,
            "labs_reviewed": form.labs_reviewed,
            "imaging_available": form.imaging_available,
            "allergies_flagged": form.allergies_flagged,
            "flags": prep_flags,
        }
    }

    db = _load_db()
    db["cases"].append(new_case)
    db["vendor_status"].update(vendor_status)
    db["spd_status"].update(spd_status)
    db["inventory_status"].update(inventory_status)
    db["preference_cards"].update(preference_cards)
    db["patient_prep"].update(patient_prep)
    _save_db(db)

    return {
        "case_id": case_id,
        "message": f"Case created. Run POST /brief/{case_id} to generate the readiness brief.",
        "or_room": form.or_room,
        "or_time": form.or_time,
        "procedure": form.procedure_type,
        "surgeon": form.surgeon_name,
    }


@app.delete("/cases/{case_id}", dependencies=[Depends(require_api_key)])
def delete_case(case_id: str):
    """Remove a case entered in error."""
    db = _load_db()
    original_count = len(db["cases"])
    db["cases"] = [c for c in db["cases"] if c["case_id"] != case_id]
    if len(db["cases"]) == original_count:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} not found in intake database")
    for key in ["vendor_status", "spd_status", "inventory_status", "patient_prep"]:
        db[key].pop(case_id, None)
    _save_db(db)
    return {"message": f"Case {case_id} deleted"}


@app.post("/brief/{case_id}", response_model=SurgeryBrief, dependencies=[Depends(require_api_key)])
def get_brief(case_id: str):
    """
    Return the surgery readiness brief for a case.

    For demo cases (CR-2026-0841, CR-2026-0842) returns a pre-computed brief instantly.
    For new case IDs the agent runs live — allow up to 60 seconds.

    Readiness levels:
    - READY: Confirmed and verified across all dimensions
    - AT_RISK: One or more flags need attention before OR time
    - BLOCKED: Case cannot safely proceed without immediate action
    """
    cases = _load_cases()
    if not any(c["case_id"] == case_id for c in cases):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} not found")

    # Return cached brief instantly if available (avoids API Gateway 29s timeout)
    cached = _load_cached_briefs()
    if case_id in cached:
        return SurgeryBrief(**cached[case_id])

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
