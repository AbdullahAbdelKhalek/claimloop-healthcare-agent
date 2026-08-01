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
    """The methodology figure for the report: the five pipeline stages.

    Layout is deliberately orthogonal: the loop edges are straight vertical
    drops so no arrow ever crosses a box. The denial resolver sits directly
    beneath the claim builder and the payer, which are the two stages it
    connects, so the loop reads without any curved routing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    AGENT_FILL = "#E7EEF7"
    CODE_FILL = "#EEEDE8"
    INPUT_FILL = "#FFFFFF"
    RESOLVER_FILL = "#F7F1E3"
    EDGE = "#B9B5AC"

    fig, ax = plt.subplots(figsize=(10, 3.9))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    boxes = [
        ("Encounter transcript", "patient and provider\ndialogue (ACI-Bench)", INPUT_FILL, "input"),
        ("1. Scribe agent", "structured\nvisit note", AGENT_FILL, "agent"),
        ("2. Coder agent", "ICD-10-CM + CPT,\nevery code tool-verified", AGENT_FILL, "agent"),
        ("3. Claim builder", "professional claim\nassembly", CODE_FILL, "code"),
        ("4. Mock payer", "rules adjudication,\nCARC / RARC denials", CODE_FILL, "code"),
    ]
    w, h, gap = 0.172, 0.40, 0.030
    y = 0.46
    centers = []
    for i, (title, sub, fill, kind) in enumerate(boxes):
        x = 0.01 + i * (w + gap)
        cx = x + w / 2
        centers.append(cx)
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=fill, edgecolor=EDGE, lw=1.0))
        if kind in ("agent", "code"):
            ax.text(x + 0.012, y + h - 0.055, kind.upper(), fontsize=6.5,
                    fontweight="bold", color=ACCENT if kind == "agent" else "#8A9099",
                    ha="left", va="center")
        ax.text(cx, y + h - 0.135, title, ha="center", va="center",
                fontsize=10, fontweight="bold", color=INK)
        ax.text(cx, y + 0.10, sub, ha="center", va="center", fontsize=8.5, color="#57606A")
        if i < len(boxes) - 1:
            ax.annotate("", xy=(x + w + gap, y + h / 2), xytext=(x + w, y + h / 2),
                        arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.1,
                                        shrinkA=0, shrinkB=0, mutation_scale=11))

    x_claim, x_payer = centers[3], centers[4]

    # denial resolver, spanning beneath the two stages it connects
    rx0, rx1 = x_claim - w / 2 - 0.035, 0.99
    ry0, ry1 = 0.05, 0.29
    ax.add_patch(plt.Rectangle((rx0, ry0), rx1 - rx0, ry1 - ry0,
                               facecolor=RESOLVER_FILL, edgecolor=EDGE, lw=1.0))
    rcx = (rx0 + rx1) / 2
    ax.text(rx0 + 0.012, ry1 - 0.045, "AGENT", fontsize=6.5, fontweight="bold",
            color=ACCENT, ha="left", va="center")
    ax.text(rcx, ry1 - 0.085, "5. Denial resolution agent", ha="center", va="center",
            fontsize=10, fontweight="bold", color=INK)
    ax.text(rcx, ry0 + 0.075, "fix and resubmit  ·  request prior authorization\n"
                              "write an appeal  ·  abandon",
            ha="center", va="center", fontsize=8.5, color="#57606A")

    # loop edges: two straight vertical drops, no crossings
    ax.annotate("", xy=(x_payer, ry1), xytext=(x_payer, y),
                arrowprops=dict(arrowstyle="-|>", color=BAD, lw=1.3,
                                shrinkA=0, shrinkB=0, mutation_scale=12))
    ax.text(x_payer + 0.014, (y + ry1) / 2, "denied", fontsize=8.5, color=BAD,
            ha="left", va="center")
    ax.annotate("", xy=(x_claim, y), xytext=(x_claim, ry1),
                arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.3,
                                shrinkA=0, shrinkB=0, mutation_scale=12))
    ax.text(x_claim - 0.014, (y + ry1) / 2, "resubmit", fontsize=8.5, color=ACCENT,
            ha="right", va="center")
    ax.text(rcx, ry0 - 0.035, "at most three submissions per encounter",
            fontsize=8, color="#8A9099", ha="center", va="center", style="italic")

    # accepted exit
    ax.annotate("", xy=(x_payer, y + h + 0.075), xytext=(x_payer, y + h),
                arrowprops=dict(arrowstyle="-|>", color=GOOD, lw=1.3,
                                shrinkA=0, shrinkB=0, mutation_scale=12))
    ax.text(x_payer, y + h + 0.105, "accepted: paid", fontsize=8.5, color=GOOD,
            ha="center", va="bottom", fontweight="bold")

    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    make_workflow_figure(Path(__file__).resolve().parents[1] / "report" / "figures" / "workflow.png")
    print("workflow figure written")
