"""Unit tests for the mock payer rules. Run: python -m pytest backend/tests -q

The ICD validity check normally calls the NLM API; tests patch it so the
suite runs offline and deterministically.
"""

import pytest

import backend.pipeline.payer as payer_mod
from backend.pipeline.payer import MockPayer, grant_prior_auth
from backend.pipeline.schemas import (
    Claim,
    ClaimDiagnosis,
    Patient,
    Provider,
    ServiceLine,
)

KNOWN_CODES = {"M17.11", "I10", "E11.9", "I50.22", "M25.561", "R07.9"}


@pytest.fixture(autouse=True)
def offline_icd(monkeypatch):
    monkeypatch.setattr(
        payer_mod, "validate_code",
        lambda code: {"code": code, "valid": code.upper() in KNOWN_CODES, "name": ""},
    )


def make_claim(dx_codes=("M17.11",), lines=None, member_id="MBR00000001", attempt=1):
    dx = [ClaimDiagnosis(sequence=i, icd10_code=c, description="") for i, c in enumerate(dx_codes, 1)]
    if lines is None:
        lines = [{"cpt": "99213", "pointers": [1]}]
    service_lines = [
        ServiceLine(sequence=i, cpt_code=l["cpt"], description="", units=l.get("units", 1),
                    charge_cents=l.get("charge", 9500), dx_pointers=l["pointers"],
                    prior_auth_number=l.get("auth"))
        for i, l in enumerate(lines, 1)
    ]
    return Claim(
        claim_id=f"CLM-TEST-{attempt}", encounter_id="TEST", attempt=attempt,
        patient=Patient(first_name="Pat", last_name="Test", gender="female", age=50,
                        date_of_birth="1976-03-14", member_id=member_id),
        provider=Provider(name="Demo Clinic", npi="1234567893"),
        payer_id="CLP-DEMO-PAYER", service_date="2026-05-15",
        diagnoses=dx, service_lines=service_lines,
        total_charge_cents=sum(sl.charge_cents for sl in service_lines),
    )


def carcs(adj):
    out = {d.carc for d in adj.claim_level_denials}
    for lo in adj.line_outcomes:
        out |= {d.carc for d in lo.denials}
    return out


def test_clean_claim_accepted():
    adj = MockPayer().submit(make_claim())
    assert adj.status == "accepted"
    assert adj.paid_total_cents > 0


def test_missing_member_id_is_co16():
    adj = MockPayer().submit(make_claim(member_id=""))
    assert adj.status == "denied"
    assert "16" in carcs(adj)


def test_unknown_cpt_is_co181():
    adj = MockPayer().submit(make_claim(lines=[{"cpt": "99999", "pointers": [1]}]))
    assert adj.status == "denied"
    assert "181" in carcs(adj)


def test_invalid_dx_is_co146():
    adj = MockPayer().submit(make_claim(dx_codes=("Z99.999",)))
    assert adj.status == "denied"
    assert "146" in carcs(adj)


def test_necessity_mismatch_is_co50():
    # ECG billed against knee osteoarthritis only
    adj = MockPayer().submit(make_claim(
        dx_codes=("M17.11",),
        lines=[{"cpt": "99213", "pointers": [1]}, {"cpt": "93000", "pointers": [1]}]))
    assert adj.status == "denied"
    assert "50" in carcs(adj)


def test_prior_auth_missing_then_valid():
    dx = ("M25.561",)
    payer = MockPayer()
    adj = payer.submit(make_claim(dx_codes=dx, lines=[
        {"cpt": "99213", "pointers": [1]}, {"cpt": "73721", "pointers": [1]}]))
    assert "197" in carcs(adj)

    auth = grant_prior_auth("73721", list(dx))
    assert auth and auth.startswith("PA")
    adj2 = payer.submit(make_claim(dx_codes=dx, attempt=2, lines=[
        {"cpt": "99213", "pointers": [1]}, {"cpt": "73721", "pointers": [1], "auth": auth}]))
    assert adj2.status == "accepted"


def test_exact_duplicate_is_co18():
    payer = MockPayer()
    claim = make_claim()
    assert payer.submit(claim).status == "accepted"
    dup = payer.submit(make_claim(attempt=2))  # same content, new claim id
    assert dup.status == "denied"
    assert "18" in carcs(dup)


def test_high_em_needs_three_dx_co150():
    adj = MockPayer().submit(make_claim(lines=[{"cpt": "99215", "pointers": [1]}]))
    assert "150" in carcs(adj)
    adj2 = MockPayer().submit(make_claim(
        dx_codes=("M17.11", "I10", "E11.9"), lines=[{"cpt": "99215", "pointers": [1]}]))
    assert adj2.status == "accepted"


def test_bad_pointer_is_co16():
    adj = MockPayer().submit(make_claim(lines=[{"cpt": "99213", "pointers": [7]}]))
    assert adj.status == "denied"
    assert "16" in carcs(adj)


def test_appeal_overturns_co50_when_unpointed_dx_supports():
    # ECG pointed at knee OA (fails), but hypertension is on the claim unpointed
    payer = MockPayer()
    claim = make_claim(dx_codes=("M17.11", "I10"), lines=[
        {"cpt": "93000", "pointers": [1]}])
    adj = payer.submit(claim)
    assert "50" in carcs(adj)
    outcome = payer.appeal(claim, "The record documents hypertension follow-up with rhythm review.")
    assert outcome.decision == "overturned"


def test_appeal_upheld_without_support():
    payer = MockPayer()
    claim = make_claim(dx_codes=("M17.11",), lines=[{"cpt": "93000", "pointers": [1]}])
    payer.submit(claim)
    outcome = payer.appeal(claim, "Please reconsider.")
    assert outcome.decision == "upheld"
