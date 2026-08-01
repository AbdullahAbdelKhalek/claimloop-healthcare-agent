"""One-encounter smoke test. Usage: python scripts/smoke.py [--profile budget]"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline import config  # noqa: E402
from backend.pipeline.encounters import load_split  # noqa: E402
from backend.pipeline.orchestrator import run_encounter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=config.DEFAULT_PROFILE,
                        choices=sorted(config.PROFILES))
    parser.add_argument("--index", type=int, default=0, help="encounter index in valid split")
    args = parser.parse_args()

    enc = load_split("valid")[args.index]
    print(f"Smoke test on {enc['encounter_id']} with the {args.profile} profile "
          f"{config.PROFILES[args.profile]}")
    rec = asyncio.run(run_encounter(enc, profile=args.profile))

    if rec["status"] == "error":
        print("ERROR:", rec["error"])
        return 1

    out = {
        "encounter": rec["encounter_id"],
        "final": rec["final"],
        "attempts": [
            {"attempt": a["attempt"],
             "status": a["adjudication"]["status"],
             "denials": sorted({d["carc"] for lo in a["adjudication"]["line_outcomes"]
                                for d in lo["denials"]}
                               | {d["carc"] for d in a["adjudication"]["claim_level_denials"]}),
             "resolution": a["resolution"]["decision"]["action"] if a["resolution"] else None}
            for a in rec["attempts"]
        ],
        "diagnoses": [d["icd10_code"] for d in rec["stages"]["coding"]["coding"]["diagnoses"]],
        "procedures": [p["cpt_code"] for p in rec["stages"]["coding"]["coding"]["procedures"]],
        "usage_totals": rec["usage_totals"],
        "estimated_cost_usd": rec["estimated_cost_usd"],
        "total_seconds": rec["total_seconds"],
        "run_file": str(config.RUNS_DIR / (rec["run_id"] + ".json")),
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
