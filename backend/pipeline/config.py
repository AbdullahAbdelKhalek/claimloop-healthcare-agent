"""Central configuration. Everything tunable lives in .env, see .env.example."""

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

# The GPT-5.6 family, August 2026. Override any of these in .env.
MODEL_SOL = os.getenv("CLAIMLOOP_MODEL_SOL", "gpt-5.6-sol")
MODEL_TERRA = os.getenv("CLAIMLOOP_MODEL_TERRA", "gpt-5.6-terra")
MODEL_LUNA = os.getenv("CLAIMLOOP_MODEL_LUNA", "gpt-5.6-luna")

# Which model runs each agent stage. The eval compares profiles head to head.
PROFILES: dict[str, dict[str, str]] = {
    "budget": {"scribe": MODEL_LUNA, "coder": MODEL_LUNA, "resolver": MODEL_LUNA},
    "balanced": {"scribe": MODEL_LUNA, "coder": MODEL_TERRA, "resolver": MODEL_TERRA},
    "premium": {"scribe": MODEL_TERRA, "coder": MODEL_TERRA, "resolver": MODEL_SOL},
}
DEFAULT_PROFILE = os.getenv("CLAIMLOOP_PROFILE", "budget")

# Published prices in dollars per million tokens as of 2026-08-01, after the
# July 30 price cuts (Luna minus 80 percent, Terra minus 20 percent). Cost
# numbers in results are estimates computed from these constants; edit here
# if prices move again.
PRICES_PER_MTOK: dict[str, dict[str, float]] = {
    MODEL_SOL: {"input": 5.00, "output": 30.00},
    MODEL_TERRA: {"input": 2.00, "output": 12.00},
    MODEL_LUNA: {"input": 0.20, "output": 1.20},
}

REASONING_EFFORT = os.getenv("CLAIMLOOP_REASONING_EFFORT", "medium")
SERVICE_DATE = os.getenv("CLAIMLOOP_SERVICE_DATE", "2026-05-15")
SPLITS = [s.strip() for s in os.getenv("CLAIMLOOP_SPLITS", "valid,test1").split(",") if s.strip()]

DATA_DIR = REPO_ROOT / "data"
ACI_DIR = DATA_DIR / "aci-bench"
RUNS_DIR = REPO_ROOT / "runs"
RESULTS_DIR = REPO_ROOT / "results"

for _d in (RUNS_DIR, RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def profile_models(name: str) -> dict[str, str]:
    return PROFILES.get(name, PROFILES[DEFAULT_PROFILE])


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    p = PRICES_PER_MTOK.get(model)
    if not p:
        return 0.0
    return round((input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000, 6)
