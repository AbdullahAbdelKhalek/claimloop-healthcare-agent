"""Central configuration. Everything tunable lives in .env, see .env.example."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

MODEL_MAIN = os.getenv("CLAIMLOOP_MODEL_MAIN", "gpt-5.6-terra")
MODEL_CHEAP = os.getenv("CLAIMLOOP_MODEL_CHEAP", "gpt-5.6-luna")
REASONING_EFFORT = os.getenv("CLAIMLOOP_REASONING_EFFORT", "medium")
SERVICE_DATE = os.getenv("CLAIMLOOP_SERVICE_DATE", "2026-05-15")
SPLITS = [s.strip() for s in os.getenv("CLAIMLOOP_SPLITS", "valid,test1").split(",") if s.strip()]

DATA_DIR = REPO_ROOT / "data"
ACI_DIR = DATA_DIR / "aci-bench"
RUNS_DIR = REPO_ROOT / "runs"
RESULTS_DIR = REPO_ROOT / "results"

for _d in (RUNS_DIR, RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
