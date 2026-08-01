"""Pydantic models for every artifact that moves through the pipeline.

The first three models (EncounterNote, CodingResult, ResolutionDecision) are
LLM outputs: the Agents SDK turns them into strict JSON schemas, so they use
plain types only. The rest are built and consumed by deterministic code.
"""

from typing import Literal, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------- stage 1: note

class ProblemPlan(BaseModel):
    problem: str
    assessment: str
    plan: str


class EncounterNote(BaseModel):
    chief_complaint: str
    history_of_present_illness: str
    past_medical_history: str
    medications: str
    allergies: str
    physical_exam: str
    results_review: str
    assessment_and_plan: list[ProblemPlan]
    follow_up: str

    def to_text(self) -> str:
        """Flatten to plain text, used for display and ROUGE scoring."""
        parts = [
            "CHIEF COMPLAINT", self.chief_complaint,
            "HISTORY OF PRESENT ILLNESS", self.history_of_present_illness,
            "PAST MEDICAL HISTORY", self.past_medical_history,
            "MEDICATIONS", self.medications,
            "ALLERGIES", self.allergies,
            "PHYSICAL EXAM", self.physical_exam,
            "RESULTS", self.results_review,
            "ASSESSMENT AND PLAN",
        ]
        for i, ap in enumerate(self.assessment_and_plan, 1):
            parts.append(f"{i}. {ap.problem}")
            parts.append(ap.assessment)
            parts.append(ap.plan)
        parts += ["FOLLOW UP", self.follow_up]
        return "\n".join(p for p in parts if p)


# -------------------------------------------------------------- stage 2: codes

class CodedDiagnosis(BaseModel):
    icd10_code: str
    description: str
    rationale: str
    confidence: float  # 0 to 1, the coder's own estimate


class CodedProcedure(BaseModel):
    cpt_code: str
    description: str
    units: int
    dx_pointers: list[int]  # 1-based indices into the diagnosis list
    rationale: str
    confidence: float


class CodingResult(BaseModel):
    diagnoses: list[CodedDiagnosis]
    procedures: list[CodedProcedure]
    coding_notes: str


# -------------------------------------------------------------- stage 3: claim

class Patient(BaseModel):
    first_name: str
    last_name: str
    gender: str
    age: int
    date_of_birth: str
    member_id: str


class Provider(BaseModel):
    name: str
    npi: str


class ClaimDiagnosis(BaseModel):
    sequence: int
    icd10_code: str
    description: str


class ServiceLine(BaseModel):
    sequence: int
    cpt_code: str
    description: str
    units: int
    charge_cents: int
    dx_pointers: list[int]
    prior_auth_number: Optional[str] = None


class Claim(BaseModel):
    claim_id: str
    encounter_id: str
    attempt: int
    resubmission_of: Optional[str] = None
    patient: Patient
    provider: Provider
    payer_id: str
    service_date: str
    diagnoses: list[ClaimDiagnosis]
    service_lines: list[ServiceLine]
    total_charge_cents: int


# ------------------------------------------------------- stage 4: adjudication

class DenialReason(BaseModel):
    group: str  # CO = contractual obligation, the group used for hard denials
    carc: str
    rarc: Optional[str] = None
    description: str
    field: Optional[str] = None  # which claim field triggered it, when known


class LineOutcome(BaseModel):
    sequence: int
    cpt_code: str
    status: Literal["accepted", "denied"]
    paid_cents: int
    denials: list[DenialReason]


class AdjudicationResult(BaseModel):
    claim_id: str
    status: Literal["accepted", "denied"]
    line_outcomes: list[LineOutcome]
    claim_level_denials: list[DenialReason]
    paid_total_cents: int
    remittance_notes: list[str]  # human-readable EOB style lines


class AppealOutcome(BaseModel):
    claim_id: str
    decision: Literal["overturned", "upheld"]
    explanation: str


# --------------------------------------------------------- stage 5: resolution

class FieldFix(BaseModel):
    field: str
    value: str


class ResolutionDecision(BaseModel):
    action: Literal["fix_and_resubmit", "appeal", "abandon"]
    revised_diagnoses: list[CodedDiagnosis]
    revised_procedures: list[CodedProcedure]
    field_fixes: list[FieldFix]
    appeal_letter: str  # empty string unless action is appeal
    rationale: str
