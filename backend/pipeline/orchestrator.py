"""The pipeline itself: one readable function that walks an encounter through
scribe, coder, claim, adjudication, and the denial loop.

This is deliberately a plain loop instead of agent handoffs: the workflow
order never changes, so code owns the control flow and agents own the
language work.

Streaming: when an emit callback is provided, every agent runs in streamed
mode and the pipeline forwards fine-grained events (token deltas, tool calls,
stage artifacts) so a UI can show the agents working live. Without emit, the
agents run in plain mode, which is what the batch evaluation uses.
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


async def _run_agent(agent, input_text: str, stage: str, emit):
    """Run one agent, streaming events through emit when it is provided."""
    if emit is None:
        result = await Runner.run(agent, input_text)
        return result.final_output, _usage_of(result)

    stream = Runner.run_streamed(agent, input_text)
    async for ev in stream.stream_events():
        if ev.type == "raw_response_event":
            data = ev.data
            kind = type(data).__name__
            if kind == "ResponseTextDeltaEvent":
                emit({"type": "token", "stage": stage, "delta": data.delta})
            elif kind == "ResponseReasoningSummaryTextDeltaEvent":
                emit({"type": "reasoning", "stage": stage, "delta": data.delta})
        elif ev.type == "run_item_stream_event":
            item = ev.item
            if item.type == "tool_call_item":
                raw = item.raw_item
                emit({"type": "tool_call", "stage": stage,
                      "name": getattr(raw, "name", "tool"),
                      "args": str(getattr(raw, "arguments", ""))[:300]})
            elif item.type == "tool_call_output_item":
                emit({"type": "tool_result", "stage": stage,
                      "output": str(item.output)[:400]})
    return stream.final_output, _usage_of(stream)


async def run_encounter(encounter: dict, profile: str = None, on_update=None,
                        run_id: str | None = None, emit=None) -> dict:
    """Run one encounter end to end. Returns the full run record as a dict.

    encounter needs: encounter_id, dialogue, and optionally dataset,
    reference note ("note") and metadata ("meta").
    """
    profile = profile or config.DEFAULT_PROFILE
    models = config.profile_models(profile)
    run_id = run_id or f"run-{encounter['encounter_id']}-{uuid.uuid4().hex[:6]}"
    emit = emit or (lambda ev: None)

    record: dict = {
        "run_id": run_id,
        "encounter_id": encounter["encounter_id"],
        "dataset": encounter.get("dataset", "custom"),
        "profile": profile,
        "models": models,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "running",
        "current_stage": "scribe",
        "dialogue": encounter["dialogue"],
        "reference_note": encounter.get("note"),
        "stages": {},
        "attempts": [],
        "final": None,
        "usage_totals": {"requests": 0, "input_tokens": 0, "output_tokens": 0},
        "estimated_cost_usd": 0.0,
    }

    def checkpoint():
        _save(record)
        if on_update:
            on_update(record)

    def add_usage(stage_model: str, u: dict):
        for k in record["usage_totals"]:
            record["usage_totals"][k] += u.get(k, 0)
        record["estimated_cost_usd"] = round(
            record["estimated_cost_usd"]
            + config.estimate_cost_usd(stage_model, u["input_tokens"], u["output_tokens"]), 6)

    started = time.time()
    emit({"type": "run_started", "run_id": run_id,
          "encounter_id": encounter["encounter_id"], "profile": profile, "models": models})
    checkpoint()

    try:
        # stage 1: scribe
        emit({"type": "stage_started", "stage": "scribe", "model": models["scribe"],
              "label": "Scribe agent is drafting the visit note"})
        t0 = time.time()
        note, usage = await _run_agent(build_scribe(models["scribe"]),
                                       encounter["dialogue"], "scribe", emit)
        note: EncounterNote
        add_usage(models["scribe"], usage)
        record["stages"]["scribe"] = {
            "note": note.model_dump(),
            "note_text": note.to_text(),
            "model": models["scribe"],
            "seconds": round(time.time() - t0, 2),
            "usage": usage,
        }
        emit({"type": "stage_done", "stage": "scribe",
              "artifact": record["stages"]["scribe"]})
        record["current_stage"] = "coder"
        checkpoint()

        # stage 2: coder
        emit({"type": "stage_started", "stage": "coder", "model": models["coder"],
              "label": "Coder agent is assigning ICD-10-CM and CPT codes"})
        t0 = time.time()
        coding, usage = await _run_agent(build_coder(models["coder"]),
                                         "VISIT NOTE\n" + note.to_text(), "coder", emit)
        coding: CodingResult
        add_usage(models["coder"], usage)
        record["stages"]["coding"] = {
            "coding": coding.model_dump(),
            "model": models["coder"],
            "seconds": round(time.time() - t0, 2),
            "usage": usage,
        }
        emit({"type": "stage_done", "stage": "coder",
              "artifact": record["stages"]["coding"]})
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
            emit({"type": "claim_built", "attempt": attempt, "claim": claim.model_dump()})

            adjudication = payer.submit(claim)
            attempt_rec = {
                "attempt": attempt,
                "claim": claim.model_dump(),
                "adjudication": adjudication.model_dump(),
                "resolution": None,
                "appeal": None,
            }
            record["attempts"].append(attempt_rec)
            record["current_stage"] = "payer"
            emit({"type": "adjudication", "attempt": attempt,
                  "result": adjudication.model_dump()})
            checkpoint()

            if adjudication.status == "accepted":
                final_status = "accepted"
                break
            if attempt == MAX_ATTEMPTS:
                final_status = "denied"
                break

            # denial resolution
            record["current_stage"] = "resolver"
            emit({"type": "stage_started", "stage": "resolver", "model": models["resolver"],
                  "attempt": attempt,
                  "label": f"Denial resolver is working attempt {attempt} denial"})
            checkpoint()
            t0 = time.time()
            decision, usage = await _run_agent(
                build_resolver(models["resolver"]),
                resolver_input(note, coding, claim, adjudication), "resolver", emit)
            decision: ResolutionDecision
            add_usage(models["resolver"], usage)
            attempt_rec["resolution"] = {
                "decision": decision.model_dump(),
                "model": models["resolver"],
                "seconds": round(time.time() - t0, 2),
                "usage": usage,
            }
            emit({"type": "resolution", "attempt": attempt,
                  "decision": decision.model_dump()})
            checkpoint()

            if decision.action == "abandon":
                final_status = "abandoned"
                break

            if decision.action == "appeal":
                outcome = payer.appeal(claim, decision.appeal_letter)
                attempt_rec["appeal"] = outcome.model_dump()
                emit({"type": "appeal", "attempt": attempt, "outcome": outcome.model_dump()})
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
            "estimated_cost_usd": record["estimated_cost_usd"],
        }
        record["status"] = "done"
        emit({"type": "run_finished", "final": record["final"],
              "usage_totals": record["usage_totals"],
              "total_seconds": round(time.time() - started, 2)})
    except Exception as exc:
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
        emit({"type": "error", "message": record["error"]})
    finally:
        record["current_stage"] = "finished"
        record["total_seconds"] = round(time.time() - started, 2)
        checkpoint()

    return record
