"""Batch evaluation over ACI-Bench encounters.

Runs the full pipeline for each encounter, then aggregates workflow metrics
(acceptance, denial categories, resolution behavior), note quality (ROUGE
against the ACI-Bench reference note), and token/latency accounting.

Usage:
  python scripts/run_eval.py --splits valid --limit 5 --cheap
  python scripts/run_eval.py --splits valid,test1 --concurrency 4

Outputs:
  results/raw/<run_id>.json   full run records (gitignored, contain data text)
  results/eval_config.json    what was run, for reproducibility
  results/summary.json        aggregate numbers
  results/summary.md          readable summary table
  results/figures/*.png       charts used by the report and slides
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline import config  # noqa: E402
from backend.pipeline.encounters import load_encounters  # noqa: E402
from backend.pipeline.orchestrator import run_encounter  # noqa: E402

async def run_batch(encounters: list[dict], profile: str, concurrency: int,
                    raw_dir: Path) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def one(enc):
        nonlocal done
        async with sem:
            record = await run_encounter(enc, profile=profile)
            done += 1
            status = record.get("final", {}).get("status") if record.get("final") else record["status"]
            print(f"  [{done}/{len(encounters)}] {enc['encounter_id']}: {status}")
            (raw_dir / f"{record['run_id']}.json").write_text(
                json.dumps(record, indent=2, default=str), encoding="utf-8")
            return record

    return list(await asyncio.gather(*(one(e) for e in encounters)))


def rouge_scores(records: list[dict]) -> dict:
    from rouge_score import rouge_scorer
    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
    per_metric = {m: [] for m in ["rouge1", "rouge2", "rougeL"]}
    for r in records:
        ref = r.get("reference_note")
        gen = r.get("stages", {}).get("scribe", {}).get("note_text")
        if not ref or not gen:
            continue
        scores = scorer.score(ref, gen)
        for m in per_metric:
            per_metric[m].append(scores[m].fmeasure)
    return {m: round(statistics.mean(v), 4) if v else None for m, v in per_metric.items()}


def first_attempt_carcs(record: dict) -> set[str]:
    if not record["attempts"]:
        return set()
    adj = record["attempts"][0]["adjudication"]
    out = {d["carc"] for d in adj["claim_level_denials"]}
    for lo in adj["line_outcomes"]:
        out |= {d["carc"] for d in lo["denials"]}
    return out


def aggregate(records: list[dict]) -> dict:
    ok = [r for r in records if r["status"] == "done"]
    errors = [r for r in records if r["status"] != "done"]

    firsts = [r for r in ok if r["final"]["first_pass_accepted"]]
    resolved = [r for r in ok if r["final"]["resolved_after_denial"]]
    final_accepted = [r for r in ok if r["final"]["status"] == "accepted"]

    denial_counter: Counter = Counter()
    fixed_counter: Counter = Counter()
    for r in ok:
        carcs = first_attempt_carcs(r)
        for c in carcs:
            denial_counter[c] += 1
            if r["final"]["status"] == "accepted":
                fixed_counter[c] += 1

    def mean_of(path_fn):
        vals = [path_fn(r) for r in ok if path_fn(r) is not None]
        return round(statistics.mean(vals), 2) if vals else None

    stage_tokens = {}
    for stage in ("scribe", "coding"):
        stage_tokens[stage] = {
            "input": mean_of(lambda r, s=stage: r["stages"].get(s, {}).get("usage", {}).get("input_tokens")),
            "output": mean_of(lambda r, s=stage: r["stages"].get(s, {}).get("usage", {}).get("output_tokens")),
            "seconds": mean_of(lambda r, s=stage: r["stages"].get(s, {}).get("seconds")),
        }

    appeal_records = [a for r in ok for a in r["attempts"] if a.get("appeal")]

    return {
        "n_runs": len(records),
        "n_completed": len(ok),
        "n_errors": len(errors),
        "first_pass_acceptance_rate": round(len(firsts) / len(ok), 4) if ok else None,
        "final_acceptance_rate": round(len(final_accepted) / len(ok), 4) if ok else None,
        "resolved_after_denial": len(resolved),
        "denied_first_pass": len(ok) - len(firsts),
        "mean_attempts": mean_of(lambda r: r["final"]["attempts_used"]),
        "denials_by_carc_first_attempt": dict(denial_counter.most_common()),
        "fixed_by_carc": dict(fixed_counter.most_common()),
        "appeals": {
            "count": len(appeal_records),
            "overturned": sum(1 for a in appeal_records if a["appeal"]["decision"] == "overturned"),
        },
        "abandoned": sum(1 for r in ok if r["final"]["status"] == "abandoned"),
        "note_rouge_f": rouge_scores(ok),
        "mean_stage_metrics": stage_tokens,
        "mean_total_seconds": mean_of(lambda r: r.get("total_seconds")),
        "mean_tokens_per_run": {
            "input": mean_of(lambda r: r["usage_totals"]["input_tokens"]),
            "output": mean_of(lambda r: r["usage_totals"]["output_tokens"]),
        },
        "total_tokens": {
            "input": sum(r["usage_totals"]["input_tokens"] for r in ok),
            "output": sum(r["usage_totals"]["output_tokens"] for r in ok),
        },
        "estimated_cost_usd": {
            "total": round(sum(r.get("estimated_cost_usd", 0) for r in ok), 4),
            "mean_per_encounter": mean_of(lambda r: r.get("estimated_cost_usd")),
        },
    }


def write_summary_md(summary: dict, cfg: dict) -> str:
    lines = [
        "# ClaimLoop evaluation summary",
        "",
        f"Splits: {cfg['splits']}, encounters: {summary['n_runs']}, "
        f"model profile: {cfg['model_profile']} ({cfg['models']}), "
        f"reasoning effort: {cfg['reasoning_effort']}",
        "",
        "## Workflow outcomes",
        "",
        "| metric | value |",
        "| --- | --- |",
        f"| completed runs | {summary['n_completed']} of {summary['n_runs']} |",
        f"| first pass acceptance | {summary['first_pass_acceptance_rate']} |",
        f"| final acceptance | {summary['final_acceptance_rate']} |",
        f"| denied on first pass | {summary['denied_first_pass']} |",
        f"| recovered by the denial loop | {summary['resolved_after_denial']} |",
        f"| abandoned | {summary['abandoned']} |",
        f"| appeals (overturned) | {summary['appeals']['count']} ({summary['appeals']['overturned']}) |",
        f"| mean attempts | {summary['mean_attempts']} |",
        "",
        "## First-attempt denials by CARC",
        "",
        "| CARC | denials | later fixed |",
        "| --- | --- | --- |",
    ]
    for carc, n in summary["denials_by_carc_first_attempt"].items():
        lines.append(f"| CO-{carc} | {n} | {summary['fixed_by_carc'].get(carc, 0)} |")
    r = summary["note_rouge_f"]
    lines += [
        "",
        "## Note quality (scribe vs ACI-Bench reference)",
        "",
        f"ROUGE-1 {r['rouge1']}, ROUGE-2 {r['rouge2']}, ROUGE-L {r['rougeL']} (mean F1)",
        "",
        "## Cost and latency",
        "",
        f"Mean tokens per encounter: {summary['mean_tokens_per_run']['input']} in / "
        f"{summary['mean_tokens_per_run']['output']} out. "
        f"Mean wall time {summary['mean_total_seconds']} s.",
        f"Batch totals: {summary['total_tokens']['input']} input tokens, "
        f"{summary['total_tokens']['output']} output tokens, "
        f"estimated ${summary['estimated_cost_usd']['total']} "
        f"(prices per backend/pipeline/config.py).",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--splits", default="valid")
    parser.add_argument("--limit", type=int, default=0, help="0 means the whole split")
    parser.add_argument("--profile", default=config.DEFAULT_PROFILE,
                        choices=sorted(config.PROFILES), help="per-stage model profile")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    splits = [s.strip() for s in args.splits.split(",") if s.strip()]
    encounters = load_encounters(splits)
    if args.limit:
        encounters = encounters[: args.limit]

    out_dir = config.RESULTS_DIR / args.profile
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "splits": splits,
        "limit": args.limit,
        "n_encounters": len(encounters),
        "encounter_ids": [e["encounter_id"] for e in encounters],
        "profile": args.profile,
        "models": config.PROFILES[args.profile],
        "reasoning_effort": config.REASONING_EFFORT,
        "service_date": config.SERVICE_DATE,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    print(f"Evaluating {len(encounters)} encounters from {splits} "
          f"with the {args.profile} profile {cfg['models']}...")

    records = asyncio.run(run_batch(encounters, args.profile, args.concurrency, raw_dir))
    summary = aggregate(records)

    (out_dir / "eval_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "summary.md").write_text(write_summary_md(summary, cfg), encoding="utf-8")

    try:
        from figures import make_eval_figures
        make_eval_figures(summary, out_dir / "figures")
    except Exception as exc:
        print(f"figure generation skipped: {exc}")

    print(json.dumps(summary, indent=2))
    print(f"\nWrote results to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
