"""The pipeline itself: one readable function that walks an encounter through
scribe, coder, claim, adjudication, and the denial loop.

This is deliberately a plain loop instead of agent handoffs: the workflow
order never changes, so code owns the control flow and agents own the
language work.
"""

import json
import time
import uuid

from agents import Runner

from . import config
from .agents import (
    build_coder,
    build_resolver,
    build_scribe,
    resolver_input,
)
from .claim_builder import build_claim
from .payer import MockPayer
from .schemas import CodingResult, EncounterNote, ResolutionDecision

MAX_ATTEMPTS = 3


def _usage_of(result) -> dict:
    u = getattr(getattr(result, "context_wrapper", None), "usage", None)
    return {
        "requests": getattr(u, "requests", 0) or 0,
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
    }


def _save(record: dict) -> None:
    path = config.RUNS_DIR / f"{record['run_id']}.json"
    path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")


async def run_encounter(encounter: dict, cheap: bool = False, on_update=None,
                        run_id: str | None = None) -> dict:
    """Run one encounter end to end. Returns the full run record as a dict.

    encounter needs: encounter_id, dialogue, and optionally dataset,
    reference note ("note") and metadata ("meta").
    """
    run_id = run_id or f"run-{encounter['encounter_id']}-{uuid.uuid4().hex[:6]}"
    record: dict = {
        "run_id": run_id,
        "encounter_id": encounter["encounter_id"],
        "dataset": encounter.get("dataset", "custom"),
        "model_profile": "cheap" if cheap else "main",
        "models": {"main": config.MODEL_MAIN, "cheap": config.MODEL_CHEAP},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "running",
        "current_stage": "scribe",
        "dialogue": encounter["dialogue"],
        "reference_note": encounter.get("note"),
        "stages": {},
        "attempts": [],
        "final": None,
        "usage_totals": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
    }

    def checkpoint():
        _save(record)
        if on_update:
            on_update(record)

    def add_usage(u: dict):
        for k in record["usage_totals"]:
            record["usage_totals"][k] += u.get(k, 0)

    started = time.time()
    checkpoint()

    try:
        # stage 1: scribe
        t0 = time.time()
        scribe_result = await Runner.run(build_scribe(cheap), encounter["dialogue"])
        note: EncounterNote = scribe_result.final_output
        usage = _usage_of(scribe_result)
        add_usage(usage)
        record["stages"]["scribe"] = {
            "note": note.model_dump(),
            "note_text": note.to_text(),
            "seconds": round(time.time() - t0, 2),
            "usage": usage,
        }
        record["current_stage"] = "coding"
        checkpoint()

        # stage 2: coder
        t0 = time.time()
        coder_result = await Runner.run(build_coder(cheap), "VISIT NOTE\n" + note.to_text())
        coding: CodingResult = coder_result.final_output
        usage = _usage_of(coder_result)
        add_usage(usage)
        record["stages"]["coding"] = {
            "coding": coding.model_dump(),
            "seconds": round(time.time() - t0, 2),
            "usage": usage,
        }
        record["current_stage"] = "claim"
        checkpoint()

        # stages 3 to 5: claim, adjudication, denial loop
        payer = MockPayer()
        field_fixes = []
        prev_claim_id = None
        final_status = "denied"
        meta = encounter.get("meta", {})

        for attempt in range(1, MAX_ATTEMPTS + 1):
            claim = build_claim(encounter["encounter_id"], meta, coding, attempt,
                                field_fixes=field_fixes, resubmission_of=prev_claim_id)
            prev_claim_id = claim.claim_id
            adjudication = payer.submit(claim)
            attempt_rec = {
                "attempt": attempt,
                "claim": claim.model_dump(),
                "adjudication": adjudication.model_dump(),
                "resolution": None,
                "appeal": None,
            }
            record["attempts"].append(attempt_rec)
            record["current_stage"] = "adjudication"
            checkpoint()

            if adjudication.status == "accepted":
                final_status = "accepted"
                break
            if attempt == MAX_ATTEMPTS:
                final_status = "denied"
                break

            # denial resolution
            record["current_stage"] = "resolution"
            checkpoint()
            t0 = time.time()
            resolver_result = await Runner.run(
                build_resolver(cheap), resolver_input(note, coding, claim, adjudication))
            decision: ResolutionDecision = resolver_result.final_output
            usage = _usage_of(resolver_result)
            add_usage(usage)
            attempt_rec["resolution"] = {
                "decision": decision.model_dump(),
                "seconds": round(time.time() - t0, 2),
                "usage": usage,
            }
            checkpoint()

            if decision.action == "abandon":
                final_status = "abandoned"
                break

            if decision.action == "appeal":
                outcome = payer.appeal(claim, decision.appeal_letter)
                attempt_rec["appeal"] = outcome.model_dump()
                final_status = "accepted" if outcome.decision == "overturned" else "denied"
                if outcome.decision == "overturned":
                    attempt_rec["adjudication"]["status"] = "accepted"
                    attempt_rec["adjudication"]["paid_total_cents"] = claim.total_charge_cents
                break

            # fix_and_resubmit
            coding = CodingResult(
                diagnoses=decision.revised_diagnoses,
                procedures=decision.revised_procedures,
                coding_notes=decision.rationale,
            )
            field_fixes = field_fixes + decision.field_fixes

        first = record["attempts"][0]["adjudication"]["status"] == "accepted"
        record["final"] = {
            "status": final_status,
            "attempts_used": len(record["attempts"]),
            "first_pass_accepted": first,
            "resolved_after_denial": final_status == "accepted" and not first,
            "paid_total_cents": record["attempts"][-1]["adjudication"]["paid_total_cents"],
        }
        record["status"] = "done"
    except Exception as exc:
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        record["current_stage"] = "finished"
        record["total_seconds"] = round(time.time() - started, 2)
        checkpoint()

    return record
