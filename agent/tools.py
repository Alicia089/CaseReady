import json
from pathlib import Path

_DATA_PATH = Path(__file__).parent.parent / "data" / "sample_cases.json"
_DB_PATH   = Path(__file__).parent.parent / "data" / "cases_db.json"


def _load() -> dict:
    # Load sample data
    data = json.loads(_DATA_PATH.read_text())

    # Merge any cases entered via the intake form
    if _DB_PATH.exists():
        db = json.loads(_DB_PATH.read_text())
        data["cases"].extend(db.get("cases", []))
        for key in ["vendor_status", "spd_status", "inventory_status", "preference_cards", "patient_prep"]:
            data[key].update(db.get(key, {}))

    return data


def check_vendor_status(case_id: str) -> dict:
    """Check vendor rep confirmation status for a surgical case."""
    data = _load()
    case = next((c for c in data["cases"] if c["case_id"] == case_id), None)
    if not case:
        return {"error": f"Case {case_id} not found"}

    vendor = data["vendor_status"].get(case_id, {})
    implant = case.get("implant_system", {})

    return {
        "case_id": case_id,
        "rep_name": implant.get("rep_name"),
        "rep_phone": implant.get("rep_phone"),
        "manufacturer": implant.get("manufacturer"),
        "system": implant.get("system"),
        "confirmed": vendor.get("confirmed"),
        "confirmation_method": vendor.get("confirmation_method"),
        "confirmed_at": vendor.get("confirmed_at"),
        "rep_present_day_of": vendor.get("rep_present"),
        "notes": vendor.get("notes"),
    }


def check_spd_status(case_id: str) -> dict:
    """Check loaner tray receipt and sterilization status for a surgical case."""
    data = _load()
    case = next((c for c in data["cases"] if c["case_id"] == case_id), None)
    if not case:
        return {"error": f"Case {case_id} not found"}

    spd = data["spd_status"].get(case_id, {})
    loaner = case.get("loaner_tray", {})

    return {
        "case_id": case_id,
        "tray_ids": loaner.get("tray_ids"),
        "required_by": loaner.get("required_by"),
        "spd_processor": loaner.get("spd_processor"),
        "trays_received": spd.get("trays_received"),
        "received_at": spd.get("received_at"),
        "sterilization_complete": spd.get("sterilization_complete"),
        "sterilization_method": spd.get("sterilization_method"),
        "cycle_completed_at": spd.get("cycle_completed_at"),
        "sterility_expiry": spd.get("sterility_expiry"),
        "storage_location": spd.get("storage_location"),
        "flags": spd.get("flags", []),
    }


def check_implant_inventory(case_id: str) -> dict:
    """Check implant component availability and on-site verification."""
    data = _load()
    case = next((c for c in data["cases"] if c["case_id"] == case_id), None)
    if not case:
        return {"error": f"Case {case_id} not found"}

    inv = data["inventory_status"].get(case_id, {})
    implant = case.get("implant_system", {})

    return {
        "case_id": case_id,
        "required_components": implant.get("component_sizes"),
        "all_components_verified": inv.get("all_components_verified"),
        "on_site": inv.get("on_site"),
        "verified_by": inv.get("verified_by"),
        "verified_at": inv.get("verified_at"),
        "missing_components": inv.get("missing_components", []),
        "backup_sizes_available": inv.get("backup_sizes_available", []),
    }


def check_preference_card(case_id: str) -> dict:
    """Check surgeon preference card verification for the case."""
    data = _load()
    case = next((c for c in data["cases"] if c["case_id"] == case_id), None)
    if not case:
        return {"error": f"Case {case_id} not found"}

    surgeon_id = case["surgeon"]["id"]
    card = data["preference_cards"].get(surgeon_id, {})

    return {
        "case_id": case_id,
        "surgeon": case["surgeon"]["name"],
        "procedure": case["procedure"]["type"],
        "card_last_updated": card.get("last_updated"),
        "verified_against_case": card.get("verified_against_case"),
        "verified_by": card.get("verified_by"),
        "special_requests": card.get("special_requests", []),
        "implant_notes": card.get("implant_notes"),
    }


def check_patient_prep(case_id: str) -> dict:
    """Check patient pre-operative readiness status."""
    data = _load()
    case = next((c for c in data["cases"] if c["case_id"] == case_id), None)
    if not case:
        return {"error": f"Case {case_id} not found"}

    prep = data["patient_prep"].get(case_id, {})
    patient = case.get("patient", {})
    procedure = case.get("procedure", {})
    anesthesia = case.get("anesthesia", {})

    return {
        "case_id": case_id,
        "patient_name": patient.get("name"),
        "asa_class": patient.get("asa_class"),
        "procedure": procedure.get("type"),
        "anesthesia_type": anesthesia.get("type"),
        "anesthesia_provider": anesthesia.get("provider"),
        "pre_op_complete": prep.get("pre_op_complete"),
        "consents_signed": prep.get("consents_signed"),
        "h_and_p_within_30_days": prep.get("h_and_p_within_30_days"),
        "npo_confirmed": prep.get("npo_confirmed"),
        "labs_reviewed": prep.get("labs_reviewed"),
        "imaging_available": prep.get("imaging_available"),
        "allergies_flagged": prep.get("allergies_flagged"),
        "flags": prep.get("flags", []),
    }


TOOL_DEFINITIONS = [
    {
        "name": "check_vendor_status",
        "description": "Check vendor rep confirmation status, contact info, and whether the rep will be present day-of for a surgical case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "The CaseReady case ID, e.g. CR-2026-0841"}
            },
            "required": ["case_id"]
        }
    },
    {
        "name": "check_spd_status",
        "description": "Check loaner tray receipt, sterilization status, and storage location for a surgical case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "The CaseReady case ID"}
            },
            "required": ["case_id"]
        }
    },
    {
        "name": "check_implant_inventory",
        "description": "Check implant component availability, on-site verification, and any missing components for a surgical case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "The CaseReady case ID"}
            },
            "required": ["case_id"]
        }
    },
    {
        "name": "check_preference_card",
        "description": "Check whether the surgeon's preference card has been verified against this specific case, and surface any special requests.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "The CaseReady case ID"}
            },
            "required": ["case_id"]
        }
    },
    {
        "name": "check_patient_prep",
        "description": "Check patient pre-operative readiness including consents, labs, NPO status, and any outstanding flags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "The CaseReady case ID"}
            },
            "required": ["case_id"]
        }
    },
]

TOOL_FUNCTIONS = {
    "check_vendor_status": check_vendor_status,
    "check_spd_status": check_spd_status,
    "check_implant_inventory": check_implant_inventory,
    "check_preference_card": check_preference_card,
    "check_patient_prep": check_patient_prep,
}
