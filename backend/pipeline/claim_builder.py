"""Assembles a claim from the coding result. Plain deterministic code.

The builder is intentionally dumb: it does not second-guess the coder. If the
coder produced a bad code or a bad pointer, that claim goes out the door and
the payer catches it, which is exactly the dynamic the project studies.
"""

from . import config
from .cpt_reference import FEE_SCHEDULE
from .demographics import DEMO_PAYER_ID, DEMO_PROVIDER, build_patient
from .schemas import (
    Claim,
    ClaimDiagnosis,
    CodingResult,
    FieldFix,
    ServiceLine,
)


def build_claim(
    encounter_id: str,
    meta: dict,
    coding: CodingResult,
    attempt: int,
    field_fixes: list[FieldFix] | None = None,
    resubmission_of: str | None = None,
) -> Claim:
    diagnoses = [
        ClaimDiagnosis(sequence=i, icd10_code=dx.icd10_code.strip().upper(), description=dx.description)
        for i, dx in enumerate(coding.diagnoses, start=1)
    ]

    # prior auth numbers arrive as field fixes shaped "prior_auth:<cpt>"
    auth_by_cpt: dict[str, str] = {}
    for fix in field_fixes or []:
        if fix.field.startswith("prior_auth:"):
            auth_by_cpt[fix.field.split(":", 1)[1]] = fix.value

    lines = []
    total = 0
    for i, proc in enumerate(coding.procedures, start=1):
        cpt = proc.cpt_code.strip()
        charge = FEE_SCHEDULE.get(cpt, {}).get("charge_cents", 0) * max(proc.units, 1)
        total += charge
        lines.append(ServiceLine(
            sequence=i,
            cpt_code=cpt,
            description=proc.description,
            units=max(proc.units, 1),
            charge_cents=charge,
            dx_pointers=proc.dx_pointers,
            prior_auth_number=auth_by_cpt.get(cpt),
        ))

    return Claim(
        claim_id=f"CLM-{encounter_id}-{attempt}",
        encounter_id=encounter_id,
        attempt=attempt,
        resubmission_of=resubmission_of,
        patient=build_patient(encounter_id, meta),
        provider=DEMO_PROVIDER,
        payer_id=DEMO_PAYER_ID,
        service_date=config.SERVICE_DATE,
        diagnoses=diagnoses,
        service_lines=lines,
        total_charge_cents=total,
    )
