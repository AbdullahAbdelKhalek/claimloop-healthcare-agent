"""Mock playback for frontend development and UI preview.

This replays a scripted claim lifecycle through the same event channel the
real pipeline uses, so the console UI can be built and demonstrated without
spending API tokens. The agent text below is hand-written fixture content,
clearly labeled as mock in the UI; the claim builder and payer adjudication
in this playback are the real deterministic code paths, so the denial and
recovery you see are genuine rule outcomes, only the LLM text is canned.
Never used by the evaluation.
"""

import asyncio
import time

from .claim_builder import build_claim
from .payer import MockPayer, grant_prior_auth
from .schemas import (
    CodedDiagnosis,
    CodedProcedure,
    CodingResult,
    EncounterNote,
    FieldFix,
    ProblemPlan,
)

MOCK_NOTE = EncounterNote(
    chief_complaint="Right knee pain (mock playback)",
    history_of_present_illness=(
        "Patient reports three weeks of right knee pain after recreational "
        "soccer, worse with stairs, partial relief with ibuprofen."),
    past_medical_history="Hypertension.",
    medications="Lisinopril 10 mg daily. Ibuprofen as needed.",
    allergies="No known drug allergies.",
    physical_exam=(
        "Right knee with medial joint line tenderness, mild effusion, "
        "stable ligament exam."),
    results_review="Not documented.",
    assessment_and_plan=[
        ProblemPlan(
            problem="Right knee pain, suspected internal derangement",
            assessment="Medial joint line tenderness and effusion after twisting injury.",
            plan="Order MRI right knee. Continue NSAIDs. Follow up after imaging."),
        ProblemPlan(
            problem="Hypertension",
            assessment="Stable on lisinopril.",
            plan="Continue current dose, recheck at next visit."),
    ],
    follow_up="Return after MRI results, sooner if worsening.",
)

MOCK_CODING = CodingResult(
    diagnoses=[
        CodedDiagnosis(icd10_code="M25.561", description="Pain in right knee",
                       rationale="Documented right knee pain (mock).", confidence=0.92),
        CodedDiagnosis(icd10_code="I10", description="Essential hypertension",
                       rationale="Chronic problem addressed at visit (mock).", confidence=0.95),
    ],
    procedures=[
        CodedProcedure(cpt_code="99214", description="Established visit, moderate complexity",
                       units=1, dx_pointers=[1, 2], rationale="Two problems managed (mock).",
                       confidence=0.85),
        CodedProcedure(cpt_code="73721", description="MRI lower extremity joint",
                       units=1, dx_pointers=[1], rationale="MRI ordered for knee (mock).",
                       confidence=0.8),
    ],
    coding_notes="Mock playback fixture, not model output.",
)

MOCK_META = {"patient_firstname": "Demo", "patient_familyname": "Patient",
             "patient_age": 41, "patient_gender": "female", "cc": "right knee pain"}

SCRIBE_STREAM = MOCK_NOTE.model_dump_json(indent=2)
CODER_STREAM = MOCK_CODING.model_dump_json(indent=2)

RESOLVER_STREAM = (
    '{\n  "action": "fix_and_resubmit",\n'
    '  "rationale": "CARC 197: the MRI needs prior authorization. Requesting '
    'auth through the payer portal for CPT 73721 with the documented knee '
    'diagnosis, then resubmitting with the authorization number attached.",\n'
    '  ...\n}')


async def _stream_text(emit, stage: str, text: str, chunk: int = 24, delay: float = 0.02):
    for i in range(0, len(text), chunk):
        emit({"type": "token", "stage": stage, "delta": text[i:i + chunk]})
        await asyncio.sleep(delay)


async def run_mock(emit, on_update=None, run_id: str = "run-mock") -> dict:
    started = time.time()
    record = {
        "run_id": run_id, "encounter_id": "MOCK-DEMO", "dataset": "mock",
        "profile": "mock playback", "models": {"scribe": "mock", "coder": "mock", "resolver": "mock"},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "running", "current_stage": "scribe", "mock": True,
        "dialogue": "[doctor] mock playback for UI development. [patient] no tokens were spent.",
        "stages": {}, "attempts": [], "final": None,
        "usage_totals": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "estimated_cost_usd": 0.0,
    }

    def push():
        if on_update:
            on_update(record)

    emit({"type": "run_started", "run_id": run_id, "encounter_id": "MOCK-DEMO",
          "profile": "mock playback", "models": record["models"], "mock": True})
    push()

    # scribe
    emit({"type": "stage_started", "stage": "scribe", "model": "mock",
          "label": "Scribe agent is drafting the visit note"})
    await _stream_text(emit, "scribe", SCRIBE_STREAM)
    record["stages"]["scribe"] = {"note": MOCK_NOTE.model_dump(),
                                  "note_text": MOCK_NOTE.to_text(),
                                  "model": "mock", "seconds": 2.1,
                                  "usage": {"requests": 0, "input_tokens": 0, "output_tokens": 0}}
    emit({"type": "stage_done", "stage": "scribe", "artifact": record["stages"]["scribe"]})
    record["current_stage"] = "coder"
    push()

    # coder with a tool call
    emit({"type": "stage_started", "stage": "coder", "model": "mock",
          "label": "Coder agent is assigning ICD-10-CM and CPT codes"})
    await asyncio.sleep(0.3)
    emit({"type": "tool_call", "stage": "coder", "name": "search_icd10",
          "args": '{"query": "right knee pain"}'})
    await asyncio.sleep(0.5)
    emit({"type": "tool_result", "stage": "coder",
          "output": '[{"code": "M25.561", "name": "Pain in right knee"}]'})
    await _stream_text(emit, "coder", CODER_STREAM)
    record["stages"]["coding"] = {"coding": MOCK_CODING.model_dump(), "model": "mock",
                                  "seconds": 3.4,
                                  "usage": {"requests": 0, "input_tokens": 0, "output_tokens": 0}}
    emit({"type": "stage_done", "stage": "coder", "artifact": record["stages"]["coding"]})
    push()

    # attempt 1: real claim builder and real payer, MRI has no auth -> CO-197
    payer = MockPayer()
    claim1 = build_claim("MOCK-DEMO", MOCK_META, MOCK_CODING, 1)
    emit({"type": "claim_built", "attempt": 1, "claim": claim1.model_dump()})
    await asyncio.sleep(0.6)
    adj1 = payer.submit(claim1)
    record["attempts"].append({"attempt": 1, "claim": claim1.model_dump(),
                               "adjudication": adj1.model_dump(),
                               "resolution": None, "appeal": None})
    emit({"type": "adjudication", "attempt": 1, "result": adj1.model_dump()})
    push()

    # resolver with the prior auth portal tool
    emit({"type": "stage_started", "stage": "resolver", "model": "mock", "attempt": 1,
          "label": "Denial resolver is working attempt 1 denial"})
    await _stream_text(emit, "resolver", RESOLVER_STREAM)
    emit({"type": "tool_call", "stage": "resolver", "name": "request_prior_auth",
          "args": '{"cpt_code": "73721", "icd10_codes": ["M25.561"]}'})
    await asyncio.sleep(0.5)
    auth = grant_prior_auth("73721", ["M25.561"])
    emit({"type": "tool_result", "stage": "resolver",
          "output": f'{{"status": "approved", "auth_number": "{auth}"}}'})
    decision = {"action": "fix_and_resubmit",
                "revised_diagnoses": [d.model_dump() for d in MOCK_CODING.diagnoses],
                "revised_procedures": [p.model_dump() for p in MOCK_CODING.procedures],
                "field_fixes": [{"field": "prior_auth:73721", "value": auth}],
                "appeal_letter": "",
                "rationale": "Authorization obtained for the MRI, resubmitting with the number attached."}
    record["attempts"][0]["resolution"] = {"decision": decision, "model": "mock",
                                           "seconds": 2.8,
                                           "usage": {"requests": 0, "input_tokens": 0, "output_tokens": 0}}
    emit({"type": "resolution", "attempt": 1, "decision": decision})
    push()

    # attempt 2 with the auth attached: real payer accepts
    claim2 = build_claim("MOCK-DEMO", MOCK_META, MOCK_CODING, 2,
                         field_fixes=[FieldFix(field="prior_auth:73721", value=auth)],
                         resubmission_of=claim1.claim_id)
    emit({"type": "claim_built", "attempt": 2, "claim": claim2.model_dump()})
    await asyncio.sleep(0.6)
    adj2 = payer.submit(claim2)
    record["attempts"].append({"attempt": 2, "claim": claim2.model_dump(),
                               "adjudication": adj2.model_dump(),
                               "resolution": None, "appeal": None})
    emit({"type": "adjudication", "attempt": 2, "result": adj2.model_dump()})

    record["final"] = {"status": adj2.status, "attempts_used": 2,
                       "first_pass_accepted": False,
                       "resolved_after_denial": adj2.status == "accepted",
                       "paid_total_cents": adj2.paid_total_cents,
                       "estimated_cost_usd": 0.0}
    record["status"] = "done"
    record["current_stage"] = "finished"
    record["total_seconds"] = round(time.time() - started, 2)
    emit({"type": "run_finished", "final": record["final"],
          "usage_totals": record["usage_totals"],
          "total_seconds": record["total_seconds"]})
    push()
    return record
