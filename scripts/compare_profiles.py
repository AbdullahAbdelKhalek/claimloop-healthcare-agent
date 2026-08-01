"""Builds the model-tier comparison from per-profile eval results.

Reads results/<profile>/summary.json for every profile that has run and
writes results/comparison.md plus a grouped bar chart for the report.

Usage: python scripts/compare_profiles.py
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from backend.pipeline import config  # noqa: E402

INK = "#1f2933"
COLORS = {"budget": "#2563eb", "balanced": "#7c3aed", "premium": "#d97706"}


def load_all() -> dict[str, dict]:
    out = {}
    for profile in config.PROFILES:
        p = config.RESULTS_DIR / profile / "summary.json"
        c = config.RESULTS_DIR / profile / "eval_config.json"
        if p.exists():
            out[profile] = {"summary": json.loads(p.read_text(encoding="utf-8")),
                            "config": json.loads(c.read_text(encoding="utf-8"))}
    return out


def main() -> int:
    data = load_all()
    if len(data) < 2:
        print(f"Need at least two profile results to compare, found: {list(data)}")
        return 1

    lines = [
        "# Model tier comparison",
        "",
        "Note: profiles may cover different encounter subsets; see each",
        "results/<profile>/eval_config.json. Rates are within-profile.",
        "",
        "| metric | " + " | ".join(data) + " |",
        "| --- |" + " --- |" * len(data),
    ]

    def row(label, fn, fmt="{}"):
        cells = [fmt.format(fn(d["summary"], d["config"])) for d in data.values()]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    row("encounters", lambda s, c: s["n_completed"])
    row("models", lambda s, c: " / ".join(dict.fromkeys(c["models"].values())))
    row("first pass acceptance", lambda s, c: s["first_pass_acceptance_rate"])
    row("final acceptance", lambda s, c: s["final_acceptance_rate"])
    row("recovered by loop", lambda s, c: s["resolved_after_denial"])
    row("mean attempts", lambda s, c: s["mean_attempts"])
    row("ROUGE-L (note)", lambda s, c: s["note_rouge_f"]["rougeL"])
    row("mean seconds/encounter", lambda s, c: s["mean_total_seconds"])
    row("mean cost/encounter", lambda s, c: s["estimated_cost_usd"]["mean_per_encounter"], "${}")
    row("batch cost", lambda s, c: s["estimated_cost_usd"]["total"], "${}")

    out_md = config.RESULTS_DIR / "comparison.md"
    out_md.write_text("\n".join(lines), encoding="utf-8")

    # grouped bars: acceptance rates per profile
    metrics = ["first_pass_acceptance_rate", "final_acceptance_rate"]
    labels = ["first pass", "after denial loop"]
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    width = 0.8 / len(data)
    for i, (profile, d) in enumerate(data.items()):
        vals = [d["summary"][m] or 0 for m in metrics]
        xs = [j + i * width for j in range(len(metrics))]
        bars = ax.bar(xs, vals, width=width * 0.92,
                      color=COLORS.get(profile, "#64748b"), label=profile)
        ax.bar_label(bars, fmt="%.2f", padding=2, fontsize=9, color=INK)
    ax.set_xticks([j + width * (len(data) - 1) / 2 for j in range(len(metrics))], labels)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("acceptance rate")
    ax.set_title("Claim acceptance by model tier")
    ax.legend(frameon=False, ncols=len(data))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig_dir = config.RESULTS_DIR / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(fig_dir / "tier_comparison.png", dpi=200)

    print("\n".join(lines))
    print(f"\nWrote {out_md} and figures/tier_comparison.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
