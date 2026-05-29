from enum import Enum
from typing import Optional
from pydantic import BaseModel


class ReadinessLevel(str, Enum):
    READY = "READY"
    AT_RISK = "AT_RISK"
    BLOCKED = "BLOCKED"


class DimensionStatus(BaseModel):
    status: ReadinessLevel
    summary: str
    flags: list[str] = []
    action_required: Optional[str] = None


class SurgeryBrief(BaseModel):
    case_id: str
    patient_name: str
    procedure: str
    surgeon: str
    or_time: str
    or_room: str
    overall_status: ReadinessLevel
    vendor: DimensionStatus
    spd: DimensionStatus
    inventory: DimensionStatus
    preference_card: DimensionStatus
    patient_prep: DimensionStatus
    critical_actions: list[str]
    surgeon_notes: str
    generated_at: str
