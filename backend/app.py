"""FastAPI app serving the pipeline and the built frontend.

Run with:  .venv/Scripts/python -m uvicorn backend.app:app --port 8000
"""

import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.pipeline import config
from backend.pipeline.encounters import data_present, load_encounters, preview
from backend.pipeline.orchestrator import run_encounter

app = FastAPI(title="ClaimLoop", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS: dict[str, dict] = {}


class RunRequest(BaseModel):
    encounter_id: str | None = None
    custom_transcript: str | None = None
    cheap: bool = False


@app.get("/api/health")
def health() -> dict:
    import os
    return {
        "ok": True,
        "data_present": data_present(),
        "api_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "models": {"main": config.MODEL_MAIN, "cheap": config.MODEL_CHEAP},
    }


@app.get("/api/encounters")
def encounters() -> list[dict]:
    if not data_present():
        raise HTTPException(503, "Data not fetched yet. Run: python scripts/fetch_data.py")
    return [preview(e) for e in load_encounters()]


@app.post("/api/runs")
async def start_run(req: RunRequest) -> dict:
    if req.custom_transcript and req.custom_transcript.strip():
        encounter = {
            "encounter_id": f"CUSTOM-{uuid.uuid4().hex[:6].upper()}",
            "dataset": "custom",
            "dialogue": req.custom_transcript.strip(),
            "meta": {"patient_firstname": "Casey", "patient_familyname": "Sample",
                     "patient_age": 45, "patient_gender": "unknown",
                     "cc": "custom transcript"},
        }
    elif req.encounter_id:
        matches = [e for e in load_encounters() if e["encounter_id"] == req.encounter_id]
        if not matches:
            raise HTTPException(404, f"Unknown encounter {req.encounter_id}")
        encounter = matches[0]
    else:
        raise HTTPException(400, "Provide encounter_id or custom_transcript.")

    run_id = f"run-{encounter['encounter_id']}-{uuid.uuid4().hex[:6]}"
    RUNS[run_id] = {"run_id": run_id, "encounter_id": encounter["encounter_id"],
                    "status": "starting", "attempts": [], "stages": {}}

    def on_update(record: dict) -> None:
        RUNS[run_id] = record

    asyncio.create_task(run_encounter(encounter, cheap=req.cheap,
                                      on_update=on_update, run_id=run_id))
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    if run_id not in RUNS:
        raise HTTPException(404, "Unknown run id")
    return RUNS[run_id]


@app.get("/api/runs")
def list_runs() -> list[dict]:
    return [
        {"run_id": r["run_id"], "encounter_id": r["encounter_id"], "status": r["status"],
         "final": r.get("final"), "created_at": r.get("created_at")}
        for r in RUNS.values()
    ]


# serve the built frontend when it exists
_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
