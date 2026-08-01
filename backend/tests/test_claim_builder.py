"""Unit tests for claim assembly."""

from backend.pipeline.claim_builder import build_claim
from backend.pipeline.schemas import CodedDiagnosis, CodedProcedure, CodingResult, FieldFix


def coding():
    return CodingResult(
        diagnoses=[
            CodedDiagnosis(icd10_code="m17.11", description="Right knee OA",
                           rationale="documented", confidence=0.9),
        ],
        procedures=[
            CodedProcedure(cpt_code="99214", description="Established visit",
                           units=1, dx_pointers=[1], rationale="follow-up", confidence=0.8),
            CodedProcedure(cpt_code="73721", description="Knee MRI",
                           units=1, dx_pointers=[1], rationale="ordered", confidence=0.7),
        ],
        coding_notes="",
    )


def test_codes_are_normalized_and_charges_summed():
    claim = build_claim("D2N999", {"patient_age": 58, "patient_gender": "male",
                                   "patient_firstname": "Brian", "patient_familyname": "White"},
                        coding(), attempt=1)
    assert claim.diagnoses[0].icd10_code == "M17.11"
    assert claim.total_charge_cents == 13500 + 45000
    assert claim.patient.first_name == "Brian"
    assert claim.patient.date_of_birth.startswith("1968")
    assert claim.claim_id == "CLM-D2N999-1"


def test_prior_auth_field_fix_lands_on_line():
    fixes = [FieldFix(field="prior_auth:73721", value="PA123456")]
    claim = build_claim("D2N999", {}, coding(), attempt=2, field_fixes=fixes,
                        resubmission_of="CLM-D2N999-1")
    mri = [l for l in claim.service_lines if l.cpt_code == "73721"][0]
    assert mri.prior_auth_number == "PA123456"
    assert claim.resubmission_of == "CLM-D2N999-1"


def test_deterministic_demographics():
    a = build_claim("D2N068", {"patient_age": 58}, coding(), 1)
    b = build_claim("D2N068", {"patient_age": 58}, coding(), 1)
    assert a.patient.member_id == b.patient.member_id
    assert a.patient.date_of_birth == b.patient.date_of_birth


def test_age_formats_from_aci_bench():
    from backend.pipeline.demographics import parse_age
    assert parse_age("58") == 58
    assert parse_age("45.0") == 45
    assert parse_age("22-month") == 1
    assert parse_age("9-month") == 0
    assert parse_age("nan") == 45
    assert parse_age(None) == 45
    assert parse_age(61.0) == 61
