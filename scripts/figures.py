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

# shared palette for the diagram figures, matching the app and slide design
MUTED = "#57606A"
FAINT = "#8A9099"
EDGE = "#B9B5AC"
AGENT_FILL = "#E7EEF7"
CODE_FILL = "#EEEDE8"
INPUT_FILL = "#FFFFFF"
RESOLVER_FILL = "#F7F1E3"
EXT_FILL = "#F2EEF6"
BAND_FILL = "#FBFAF8"


def _fit_text(fig, ax, x, y, s, max_width, fontsize, **kwargs):
    """Draw centered text, shrinking the font until it fits max_width.

    max_width is in axes fraction. Guarantees no label ever overflows its
    box, which hand-tuned font sizes cannot promise across label edits.
    """
    t = ax.text(x, y, s, ha=kwargs.pop("ha", "center"), va=kwargs.pop("va", "center"),
                fontsize=fontsize, **kwargs)
    fig.canvas.draw()
    inv = ax.transAxes.inverted()
    for _ in range(14):
        bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
        x0, _ = inv.transform((bb.x0, bb.y0))
        x1, _ = inv.transform((bb.x1, bb.y1))
        if (x1 - x0) <= max_width or fontsize <= 4.5:
            break
        fontsize -= 0.4
        t.set_fontsize(fontsize)
        fig.canvas.draw()
    return t


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
    """Figure 1: the five pipeline stages and the denial loop.

    Layout is deliberately orthogonal: the loop edges are straight vertical
    drops so no arrow ever crosses a box. The denial resolver sits directly
    beneath the claim builder and the payer, which are the two stages it
    connects, so the loop reads without any curved routing. Every label is
    drawn through _fit_text, so no text can overflow its box.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11, 4.0))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    boxes = [
        ("Encounter\ntranscript", "patient and provider\ndialogue (ACI-Bench)", INPUT_FILL, None),
        ("1. Scribe", "transcript to a\nstructured visit note", AGENT_FILL, "agent"),
        ("2. Coder", "ICD-10-CM and CPT,\nevery code tool-verified", AGENT_FILL, "agent"),
        ("3. Claim builder", "assembles the\nprofessional claim", CODE_FILL, "code"),
        ("4. Mock payer", "rules adjudication,\nCARC / RARC denials", CODE_FILL, "code"),
    ]
    w, h, gap = 0.174, 0.40, 0.029
    y = 0.46
    pad = 0.020
    centers = []
    for i, (title, sub, fill, kind) in enumerate(boxes):
        x = 0.007 + i * (w + gap)
        cx = x + w / 2
        centers.append(cx)
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor=fill, edgecolor=EDGE, lw=1.0))
        if kind:
            ax.text(x + 0.010, y + h - 0.050, kind.upper(), fontsize=6.5,
                    fontweight="bold", color=ACCENT if kind == "agent" else FAINT,
                    ha="left", va="center")
        _fit_text(fig, ax, cx, y + h - 0.145, title, w - pad, 10.5,
                  fontweight="bold", color=INK)
        _fit_text(fig, ax, cx, y + 0.095, sub, w - pad, 8.5, color=MUTED)
        if i < len(boxes) - 1:
            ax.annotate("", xy=(x + w + gap, y + h / 2), xytext=(x + w, y + h / 2),
                        arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.1,
                                        shrinkA=0, shrinkB=0, mutation_scale=11))

    x_claim, x_payer = centers[3], centers[4]

    # denial resolver, spanning beneath the two stages it connects
    rx0, rx1 = x_claim - w / 2 - 0.030, 0.995
    ry0, ry1 = 0.05, 0.29
    ax.add_patch(plt.Rectangle((rx0, ry0), rx1 - rx0, ry1 - ry0,
                               facecolor=RESOLVER_FILL, edgecolor=EDGE, lw=1.0))
    rcx = (rx0 + rx1) / 2
    ax.text(rx0 + 0.010, ry1 - 0.042, "AGENT", fontsize=6.5, fontweight="bold",
            color=ACCENT, ha="left", va="center")
    _fit_text(fig, ax, rcx, ry1 - 0.082, "5. Denial resolver", rx1 - rx0 - pad, 10.5,
              fontweight="bold", color=INK)
    _fit_text(fig, ax, rcx, ry0 + 0.072,
              "fix and resubmit  ·  request prior authorization\nwrite an appeal  ·  abandon",
              rx1 - rx0 - pad, 8.5, color=MUTED)

    # loop edges: two straight vertical drops, no crossings
    ax.annotate("", xy=(x_payer, ry1), xytext=(x_payer, y),
                arrowprops=dict(arrowstyle="-|>", color=BAD, lw=1.3,
                                shrinkA=0, shrinkB=0, mutation_scale=12))
    ax.text(x_payer + 0.012, (y + ry1) / 2, "denied", fontsize=8.5, color=BAD,
            ha="left", va="center")
    ax.annotate("", xy=(x_claim, y), xytext=(x_claim, ry1),
                arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.3,
                                shrinkA=0, shrinkB=0, mutation_scale=12))
    ax.text(x_claim - 0.012, (y + ry1) / 2, "resubmit", fontsize=8.5, color=ACCENT,
            ha="right", va="center")
    ax.text(rcx, ry0 - 0.032, "at most three submissions per encounter",
            fontsize=8, color=FAINT, ha="center", va="center", style="italic")

    # accepted exit
    ax.annotate("", xy=(x_payer, y + h + 0.075), xytext=(x_payer, y + h),
                arrowprops=dict(arrowstyle="-|>", color=GOOD, lw=1.3,
                                shrinkA=0, shrinkB=0, mutation_scale=12))
    ax.text(x_payer, y + h + 0.100, "accepted: paid", fontsize=8.5, color=GOOD,
            ha="center", va="bottom", fontweight="bold")

    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def make_architecture_figure(path: Path) -> None:
    """Figure 2: the layered system architecture.

    Where Figure 1 shows what flows, this shows what is built: which layer
    owns which responsibility, where the Agents SDK sits, what each agent
    declares as its structured output and tools, and which components are
    deterministic code rather than model calls.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(11.5, 7.4))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    gx = 0.128           # gutter width for layer names
    cx0, cx1 = 0.142, 0.998
    cw = cx1 - cx0
    pad = 0.024
    # three equal columns inside a band, never wider than the band itself
    col_x0 = cx0 + pad
    col_gap = 0.024
    col_w = (cw - 2 * pad - 2 * col_gap) / 3

    def band(y0, y1, name, fill=BAND_FILL):
        ax.add_patch(plt.Rectangle((cx0, y0), cw, y1 - y0,
                                   facecolor=fill, edgecolor=EDGE, lw=1.0))
        ax.text(gx, (y0 + y1) / 2, name, fontsize=8.5, fontweight="bold",
                color=FAINT, ha="right", va="center", linespacing=1.5)

    def connector(y_top, y_bottom, label, both=False):
        style = "<|-|>" if both else "-|>"
        ax.annotate("", xy=(0.30, y_bottom), xytext=(0.30, y_top),
                    arrowprops=dict(arrowstyle=style, color=FAINT, lw=1.0,
                                    shrinkA=0, shrinkB=0, mutation_scale=9))
        ax.text(0.322, (y_top + y_bottom) / 2, label, fontsize=7.5,
                color=FAINT, ha="left", va="center")

    # ---------------------------------------------------------- interface
    band(0.880, 0.992, "INTERFACE")
    _fit_text(fig, ax, cx0 + pad, 0.958, "React 19 + Vite console", cw / 2, 10,
              fontweight="bold", color=INK, ha="left")
    _fit_text(fig, ax, cx0 + pad, 0.912,
              "transcript viewer  ·  pipeline rail  ·  activity log (token stream, tool calls)  ·  "
              "claim document  ·  verdict stamps",
              cw - 2 * pad, 8.5, color=MUTED, ha="left")

    connector(0.880, 0.845, "REST + Server-Sent Events", both=True)

    # ------------------------------------------------------------ service
    band(0.733, 0.845, "SERVICE")
    _fit_text(fig, ax, cx0 + pad, 0.811, "FastAPI application", cw / 2, 10,
              fontweight="bold", color=INK, ha="left")
    _fit_text(fig, ax, cx0 + pad, 0.765,
              "GET /api/encounters  ·  GET /api/encounters/{id}  ·  POST /api/runs  ·  "
              "GET /api/runs/{id}/events (SSE, replayable buffer)",
              cw - 2 * pad, 8.5, color=MUTED, ha="left")

    connector(0.733, 0.695, "starts a background run, streams every event")

    # ------------------------------------------------------ orchestration
    band(0.583, 0.695, "ORCHESTRATION")
    _fit_text(fig, ax, cx0 + pad, 0.661, "orchestrator.run_encounter()", cw / 2, 10,
              fontweight="bold", color=INK, ha="left")
    _fit_text(fig, ax, cx0 + pad, 0.615,
              "plain async loop, no agent handoffs  ·  at most 3 submissions  ·  "
              "per-stage token and cost accounting  ·  retries transient API errors  ·  run records to runs/*.json",
              cw - 2 * pad, 8.5, color=MUTED, ha="left")

    connector(0.583, 0.545, "Runner.run_streamed()   /   token, tool and item events", both=True)

    # ------------------------------------------------------------- agents
    band(0.300, 0.545, "AGENTS")
    _fit_text(fig, ax, col_x0, 0.520,
              "OpenAI Agents SDK over the Responses API  ·  streamed  ·  strict structured outputs  ·  "
              "model per stage from the active profile",
              cw - 2 * pad, 8.5, fontweight="bold", color=ACCENT, ha="left")

    agents = [
        ("Scribe", "output_type = EncounterNote", "no tools", "never invents findings"),
        ("Coder", "output_type = CodingResult", "tool: search_icd10", "may only bill verified codes"),
        ("DenialResolver", "output_type = ResolutionDecision",
         "tools: search_icd10,\nrequest_prior_auth", "never fabricates clinical facts"),
    ]
    ay0, ay1 = 0.316, 0.492
    for i, (name, out, tools, rule) in enumerate(agents):
        x = col_x0 + i * (col_w + col_gap)
        ax.add_patch(plt.Rectangle((x, ay0), col_w, ay1 - ay0,
                                   facecolor=AGENT_FILL, edgecolor=EDGE, lw=1.0))
        _fit_text(fig, ax, x + 0.012, ay1 - 0.030, name, col_w - 0.024, 9.5,
                  fontweight="bold", color=INK, ha="left")
        _fit_text(fig, ax, x + 0.012, ay1 - 0.066, out, col_w - 0.024, 8,
                  color=MUTED, ha="left", family="monospace")
        _fit_text(fig, ax, x + 0.012, ay1 - 0.106, tools, col_w - 0.024, 8,
                  color=ACCENT, ha="left", family="monospace")
        _fit_text(fig, ax, x + 0.012, ay0 + 0.022, rule, col_w - 0.024, 7.5,
                  color=FAINT, ha="left", style="italic")

    connector(0.300, 0.262, "the loop calls these directly, no model in the path")

    # ------------------------------------------------------ deterministic
    band(0.150, 0.262, "DETERMINISTIC\nCORE")
    det = [
        ("claim_builder.build_claim()", "assembles patient, provider,\ndiagnoses and service lines"),
        ("payer.MockPayer", "7 rules to CARC / RARC codes,\nduplicate detection"),
        ("payer.appeal()", "re-reads the full diagnosis list,\nupholds or overturns"),
    ]
    dy0, dy1 = 0.163, 0.249
    for i, (name, desc) in enumerate(det):
        x = col_x0 + i * (col_w + col_gap)
        ax.add_patch(plt.Rectangle((x, dy0), col_w, dy1 - dy0,
                                   facecolor=CODE_FILL, edgecolor=EDGE, lw=1.0))
        _fit_text(fig, ax, x + 0.012, dy1 - 0.024, name, col_w - 0.024, 8.5,
                  fontweight="bold", color=INK, ha="left", family="monospace")
        _fit_text(fig, ax, x + 0.012, dy0 + 0.028, desc, col_w - 0.024, 7.5,
                  color=MUTED, ha="left")

    connector(0.150, 0.112, "HTTPS tool call   /   local CSV load")

    # -------------------------------------------------- external and data
    band(0.000, 0.112, "EXTERNAL\n+ DATA")
    ext = [
        ("NLM ICD-10-CM API", "public, keyless,\ncurrent code table"),
        ("ACI-Bench corpus", "CC BY 4.0, fetched at a pinned\ncommit, never committed"),
        ("CPT subset table", "paraphrased demo subset,\nAMA licenses the full set"),
    ]
    ey0, ey1 = 0.012, 0.098
    for i, (name, desc) in enumerate(ext):
        x = col_x0 + i * (col_w + col_gap)
        ax.add_patch(plt.Rectangle((x, ey0), col_w, ey1 - ey0,
                                   facecolor=EXT_FILL, edgecolor=EDGE, lw=1.0))
        _fit_text(fig, ax, x + 0.012, ey1 - 0.024, name, col_w - 0.024, 8.5,
                  fontweight="bold", color=INK, ha="left")
        _fit_text(fig, ax, x + 0.012, ey0 + 0.028, desc, col_w - 0.024, 7.5,
                  color=MUTED, ha="left")

    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    figs = Path(__file__).resolve().parents[1] / "report" / "figures"
    make_workflow_figure(figs / "workflow.png")
    make_architecture_figure(figs / "architecture.png")
    print("workflow and architecture figures written")
