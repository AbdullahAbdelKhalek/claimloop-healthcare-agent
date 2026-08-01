"""Chart generation for the evaluation results and the report workflow figure.

Matplotlib only, PNG output, one chart per figure, no styling libraries.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK = "#1f2933"
ACCENT = "#2563eb"
GOOD = "#16a34a"
BAD = "#dc2626"
WARN = "#d97706"


def make_eval_figures(summary: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _funnel(summary, out_dir / "outcome_funnel.png")
    _denials(summary, out_dir / "denials_by_carc.png")
    _tokens(summary, out_dir / "tokens_by_stage.png")


def _funnel(summary: dict, path: Path) -> None:
    n = summary["n_completed"]
    first = round(summary["first_pass_acceptance_rate"] * n) if n else 0
    resolved = summary["resolved_after_denial"]
    rest = n - first - resolved
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    bars = ax.barh(
        ["accepted first pass", "recovered by denial loop", "still denied or abandoned"],
        [first, resolved, rest], color=[GOOD, ACCENT, BAD], height=0.55)
    ax.bar_label(bars, padding=4, color=INK)
    ax.set_xlabel("encounters")
    ax.set_title(f"Claim outcomes across {n} encounters")
    ax.spines[["top", "right"]].set_visible(False)
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _denials(summary: dict, path: Path) -> None:
    data = summary["denials_by_carc_first_attempt"]
    if not data:
        return
    carcs = [f"CO-{c}" for c in data]
    totals = list(data.values())
    fixed = [summary["fixed_by_carc"].get(c, 0) for c in data]
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.bar(carcs, totals, color=WARN, label="denied first attempt")
    ax.bar(carcs, fixed, color=GOOD, label="eventually paid")
    ax.set_ylabel("encounters")
    ax.set_title("First-attempt denials by CARC and recovery")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def _tokens(summary: dict, path: Path) -> None:
    stages = summary["mean_stage_metrics"]
    names = list(stages.keys())
    inputs = [stages[s]["input"] or 0 for s in names]
    outputs = [stages[s]["output"] or 0 for s in names]
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    x = range(len(names))
    ax.bar([i - 0.18 for i in x], inputs, width=0.36, color=ACCENT, label="input tokens")
    ax.bar([i + 0.18 for i in x], outputs, width=0.36, color=INK, label="output tokens")
    ax.set_xticks(list(x), names)
    ax.set_ylabel("mean tokens per encounter")
    ax.set_title("Token usage by LLM stage")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def make_workflow_figure(path: Path) -> None:
    """The methodology figure for the report: the five pipeline stages."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.axis("off")

    boxes = [
        ("Transcript", "ACI-Bench\nencounter dialogue", "#e0e7ff"),
        ("1. Scribe agent", "structured\nvisit note", "#dbeafe"),
        ("2. Coder agent", "ICD-10-CM + CPT\nNLM code lookup tool", "#dbeafe"),
        ("3. Claim builder", "FHIR-shaped claim\n(deterministic)", "#dcfce7"),
        ("4. Mock payer", "rules engine\nCARC/RARC denials", "#dcfce7"),
    ]
    w, h, gap, y = 0.16, 0.42, 0.045, 0.42
    for i, (title, sub, color) in enumerate(boxes):
        x = 0.02 + i * (w + gap)
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=color, edgecolor=INK, lw=1.2))
        ax.text(x + w / 2, y + h - 0.10, title, ha="center", va="center",
                fontsize=10, fontweight="bold", color=INK)
        ax.text(x + w / 2, y + h / 2 - 0.07, sub, ha="center", va="center", fontsize=8.5, color=INK)
        if i < len(boxes) - 1:
            ax.annotate("", xy=(x + w + gap - 0.005, y + h / 2), xytext=(x + w + 0.005, y + h / 2),
                        arrowprops=dict(arrowstyle="->", color=INK, lw=1.4))

    # denial loop back edge
    x_payer = 0.02 + 4 * (w + gap) + w / 2
    x_res = 0.02 + 2.5 * (w + gap)
    ax.add_patch(plt.Rectangle((x_res - w / 2, 0.04), w + 0.06, 0.24,
                               facecolor="#fef3c7", edgecolor=INK, lw=1.2))
    ax.text(x_res + 0.03, 0.21, "5. Denial resolution agent", ha="center", va="center",
            fontsize=10, fontweight="bold", color=INK)
    ax.text(x_res + 0.03, 0.11, "fix and resubmit, prior auth tool,\nappeal letter, or abandon",
            ha="center", va="center", fontsize=8.5, color=INK)
    ax.annotate("", xy=(x_res + w / 2 + 0.06, 0.16), xytext=(x_payer, y),
                arrowprops=dict(arrowstyle="->", color=BAD, lw=1.4,
                                connectionstyle="arc3,rad=0.25"))
    ax.text(x_payer - 0.035, 0.30, "denied", fontsize=9, color=BAD)
    ax.annotate("", xy=(0.02 + 3 * (w + gap) + w / 2, y), xytext=(x_res - 0.04, 0.16),
                arrowprops=dict(arrowstyle="->", color=ACCENT, lw=1.4,
                                connectionstyle="arc3,rad=0.25"))
    ax.text(x_res - 0.10, 0.30, "resubmit", fontsize=9, color=ACCENT)
    ax.text(x_payer + 0.05, y + h / 2, "accepted:\npaid", fontsize=9, color=GOOD, va="center")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    make_workflow_figure(Path(__file__).resolve().parents[1] / "report" / "figures" / "workflow.png")
    print("workflow figure written")
