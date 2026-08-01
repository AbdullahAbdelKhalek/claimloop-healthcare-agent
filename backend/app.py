"""FastAPI app serving the pipeline, a live event stream, and the built frontend.

Run with:  .venv/Scripts/python -m uvicorn backend.app:app --port 8000

The interesting endpoint is /api/runs/{id}/events: a Server-Sent Events
stream that replays everything that has happened in a run and then follows
it live (agent token deltas, tool calls, claims, adjudications). The
frontend console is built entirely on it.
"""

import asyncio
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.pipeline import config
from backend.pipeline.dev_mock import run_mock
from backend.pipeline.encounters import data_present, load_encounters, preview
from backend.pipeline.orchestrator import run_encounter

app = FastAPI(title="ClaimLoop", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS: dict[str, dict] = {}
EVENTS: dict[str, dict] = {}  # run_id -> {"buffer": [...], "queues": set()}
MAX_BUFFERED_EVENTS = 50_000
TERMINAL = {"run_finished", "error"}


class RunRequest(BaseModel):
    encounter_id: str | None = None
    custom_transcript: str | None = None
    profile: str = config.DEFAULT_PROFILE
    mock: bool = False


def _make_emit(run_id: str):
    state = EVENTS[run_id] = {"buffer": [], "queues": set()}

    def emit(event: dict) -> None:
        if len(state["buffer"]) < MAX_BUFFERED_EVENTS:
            state["buffer"].append(event)
        for q in list(state["queues"]):
            q.put_nowait(event)

    return emit


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "data_present": data_present(),
        "api_key_present": bool(os.getenv("OPENAI_API_KEY")),
        "profiles": config.PROFILES,
        "default_profile": config.DEFAULT_PROFILE,
        "prices_per_mtok": config.PRICES_PER_MTOK,
    }


@app.get("/api/encounters")
def encounters() -> list[dict]:
    if not data_present():
        raise HTTPException(503, "Data not fetched yet. Run: python scripts/fetch_data.py")
    return [preview(e) for e in load_encounters()]


@app.get("/api/encounters/{encounter_id}")
def encounter_detail(encounter_id: str) -> dict:
    matches = [e for e in load_encounters() if e["encounter_id"] == encounter_id]
    if not matches:
        raise HTTPException(404, f"Unknown encounter {encounter_id}")
    e = matches[0]
    return {"encounter_id": e["encounter_id"], "split": e["split"],
            "dataset": e["dataset"], "dialogue": e["dialogue"], "meta": e["meta"]}


@app.post("/api/runs")
async def start_run(req: RunRequest) -> dict:
    if req.mock:
        run_id = f"run-mock-{uuid.uuid4().hex[:6]}"
        RUNS[run_id] = {"run_id": run_id, "encounter_id": "MOCK-DEMO",
                        "status": "starting", "mock": True, "attempts": [], "stages": {}}
        emit = _make_emit(run_id)

        def on_update(record: dict) -> None:
            RUNS[run_id] = record

        asyncio.create_task(run_mock(emit, on_update=on_update, run_id=run_id))
        return {"run_id": run_id, "mock": True}

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

    if req.profile not in config.PROFILES:
        raise HTTPException(400, f"Unknown profile {req.profile}. "
                                 f"Options: {', '.join(config.PROFILES)}")

    run_id = f"run-{encounter['encounter_id']}-{uuid.uuid4().hex[:6]}"
    RUNS[run_id] = {"run_id": run_id, "encounter_id": encounter["encounter_id"],
                    "status": "starting", "attempts": [], "stages": {}}
    emit = _make_emit(run_id)

    def on_update(record: dict) -> None:
        RUNS[run_id] = record

    asyncio.create_task(run_encounter(encounter, profile=req.profile,
                                      on_update=on_update, run_id=run_id, emit=emit))
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str):
    if run_id not in EVENTS:
        raise HTTPException(404, "Unknown run id")
    state = EVENTS[run_id]

    async def gen():
        q: asyncio.Queue = asyncio.Queue()
        state["queues"].add(q)
        try:
            replay = list(state["buffer"])
            for ev in replay:
                yield f"data: {json.dumps(ev, default=str)}\n\n"
            if replay and replay[-1].get("type") in TERMINAL:
                return
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=25)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev, default=str)}\n\n"
                if ev.get("type") in TERMINAL:
                    return
        finally:
            state["queues"].discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


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


# Serve the built frontend when it exists. The build output is gitignored, so
# a fresh clone will not have it until `npm run build` has run. Rather than
# answering a bare 404, say exactly what to do about it.
_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"

if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
else:
    _BUILD_HINT = """<!doctype html>
<html><head><title>ClaimLoop: frontend not built yet</title>
<style>
 body{font-family:system-ui,Segoe UI,sans-serif;background:#faf9f6;color:#1f2328;
      max-width:44rem;margin:12vh auto;padding:0 1.5rem;line-height:1.6}
 h1{font-size:1.4rem;margin-bottom:.3rem} p{color:#57606a}
 pre{background:#fff;border:1px solid #e3e0da;border-radius:6px;padding:.9rem 1rem;
     overflow-x:auto;font-size:.85rem}
 code{background:#f5f3ef;border:1px solid #e3e0da;border-radius:3px;padding:0 .3rem}
</style></head><body>
<h1>The backend is running. The frontend has not been built yet.</h1>
<p>The compiled interface is not checked into git, so a fresh clone has to
build it once. From the repository root:</p>
<pre>cd frontend
npm install
npm run build</pre>
<p>Then restart this server and reload the page. The build output is picked up
at startup, so a server started before the build will not see it.</p>
<p>The API is already live: try <code>/api/health</code>.</p>
</body></html>"""

    @app.get("/", include_in_schema=False)
    def frontend_missing() -> HTMLResponse:
        return HTMLResponse(_BUILD_HINT, status_code=503)

    print("\n  ClaimLoop: frontend/dist not found, serving build instructions at /."
          "\n  Build it with:  cd frontend && npm install && npm run build\n")
