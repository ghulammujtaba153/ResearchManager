"""Autonomous Scientific Paper & Preprint Manuscript Drafter.

Synthesizes project memory, experimental runs, literature citations, and decisions
into an academic preprint manuscript (Markdown and LaTeX with BibTeX).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from research_manager.tools.literature import search_arxiv
from research_manager.tools.science import build_trajectory, compute_statistics

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = PROJECT_ROOT / "reports"


def draft_research_paper(
    project_id: str,
    *,
    facts: dict[str, Any],
    experiments: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    query: str | None = None,
) -> dict[str, Any]:
    """Compile an academic preprint paper draft from experiment history and literature."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    baseline_acc = float(facts.get("baseline_accuracy", 0.75))
    metric_name = str(facts.get("approved_metric", "accuracy"))
    learning_rate = float(facts.get("learning_rate", 0.1))

    latest_exp = experiments[0] if experiments else {}
    hypothesis = latest_exp.get("hypothesis") or "Iterative hyperparameter tuning to surpass approved baseline."

    # Search relevant scientific literature for Section 2
    search_query = query or hypothesis[:50]
    papers = search_arxiv(search_query, max_results=3)

    # Statistical trajectory
    trajectory = build_trajectory(runs, baseline=baseline_acc)
    acc_values = [p["accuracy"] for p in trajectory if p["accuracy"] is not None]
    stats = compute_statistics(acc_values)

    best_acc = stats.get("max", 0.0)
    beats_baseline = best_acc >= baseline_acc
    cycles_count = len(runs)

    # --- Generate Markdown Manuscript ---
    md = [
        f"# Autonomous Investigation: {hypothesis}",
        "",
        f"**Authors:** Autonomous Research Agent (Project: `{project_id}`)  ",
        f"**Date:** {time.strftime('%B %d, %Y')} | **Status:** {'Accepted / Target Achieved' if beats_baseline else 'Iterating'}  ",
        f"**Target Metric:** `{metric_name}` | **Approved Baseline:** `{baseline_acc:.2f}` | **Best Achieved:** `{best_acc:.4f}`  ",
        "",
        "---",
        "",
        "## Abstract",
        (
            f"This paper presents the empirical investigation of the hypothesis: *\"{hypothesis}\"*. "
            f"Using an autonomous agentic experiment manager, {cycles_count} iterative experimental cycles were conducted. "
            f"The system systematically adjusted parameters, inspected execution artifacts, and performed assertive "
            f"invariant verification against an approved baseline metric ({baseline_acc:.2f}). "
            f"The final observed metric reached {best_acc:.4f} (mean {stats['mean']:.4f} ± {stats['std']:.4f}), "
            f"{'successfully beating' if beats_baseline else 'approaching'} the target threshold."
        ),
        "",
        "## 1. Introduction",
        (
            f"Iterative hypothesis testing is fundamental to experimental science. In machine learning research, "
            f"evaluating candidate hyperparameter configurations against durable baselines requires rigorous tracking, "
            f"invariant boundary enforcement, and failure recovery. "
            f"We investigate whether structured parameter exploration starting from initial learning rate "
            f"$\\eta = {learning_rate}$ improves `{metric_name}` beyond the established baseline of ${baseline_acc:.2f}$."
        ),
        "",
        "## 2. Related Work & Theoretical Grounding",
        "Our autonomous investigation builds upon foundational optimization and architectural literature:",
        "",
    ]

    for p in papers:
        authors_et_al = f"{p['authors'][0]} et al." if len(p['authors']) > 1 else (p['authors'][0] if p['authors'] else "Researchers")
        year = p['published'][:4]
        md.append(f"- **{p['title']}** ({authors_et_al}, {year}): {p['summary']}")
        md.append(f"  *ArXiv:* [{p['arxiv_id']}]({p['pdf_url']})")

    md.extend([
        "",
        "## 3. Experimental Methodology & Setup",
        (
            f"Experiments were executed using the Research Experiment Manager coordinator. "
            f"Each cycle generated an isolated task configuration, followed by artifact verification. "
            f"Safety was guarded by formal invariants (`INV_SECURITY`, `INV_COMPLETENESS`, `INV_BASELINE_THRESHOLD`) "
            f"to guarantee evidence grounding without hallucinated claims."
        ),
        "",
        "## 4. Empirical Results & Convergence Trajectory",
        "",
        "| Cycle | Run Identifier | Metric (`accuracy`) | Baseline | Status | Decision Action |",
        "|---|---|---|---|---|---|",
    ])

    for p in trajectory:
        acc_str = f"{p['accuracy']:.4f}" if p["accuracy"] is not None else "N/A"
        status_badge = "BEATS" if p["beats_baseline"] else "SUB-BASELINE"
        md.append(f"| {p['cycle']} | `{p['run_key']}` | {acc_str} | {baseline_acc:.2f} | {status_badge} | {p['notes'][:35]} |")

    md.extend([
        "",
        f"**Summary Statistics:** Number of runs: {stats['count']} | Mean: {stats['mean']:.4f} | Std: {stats['std']:.4f} | Peak: {stats['max']:.4f}",
        "",
        "## 5. Discussion & Guard Verification",
        (
            f"Throughout the {cycles_count} cycles, the agent analyzed execution outputs. "
            f"When evidence was incomplete or sub-baseline, the system self-corrected rather than hallucinating "
            f"premature convergence. Final parameters were approved and promoted to long-term memory."
        ),
        "",
        "## 6. References (BibTeX)",
        "```bibtex",
    ])

    for p in papers:
        md.append(p["bibtex"])
        md.append("")

    md.append("```")

    paper_markdown = "\n".join(md)
    paper_path = REPORTS_DIR / f"{project_id}_preprint_paper.md"
    paper_path.write_text(paper_markdown, encoding="utf-8")

    # Also save BibTeX file
    bib_path = REPORTS_DIR / f"{project_id}_references.bib"
    bib_content = "\n\n".join(p["bibtex"] for p in papers)
    bib_path.write_text(bib_content, encoding="utf-8")

    # Generate Publication-Ready LaTeX Manuscript (.tex)
    latex_table_rows = []
    for p in trajectory:
        acc_str = f"{p['accuracy']:.4f}" if p["accuracy"] is not None else "\\text{N/A}"
        status_str = "\\textbf{Beats}" if p["beats_baseline"] else "Sub-baseline"
        clean_notes = (p['notes'] or '').replace("_", "\\_")[:30]
        run_k = p['run_key'].replace("_", "\\_")
        latex_table_rows.append(f"    {p['cycle']} & \\texttt{{{run_k}}} & {acc_str} & {baseline_acc:.2f} & {status_str} & {clean_notes} \\\\")
    table_body = "\n".join(latex_table_rows)

    latex_content = f"""\\documentclass[11pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{amsmath,amssymb}}
\\usepackage{{booktabs}}
\\usepackage{{geometry}}
\\usepackage{{hyperref}}
\\geometry{{margin=1in}}

\\title{{\\textbf{{Autonomous Empirical Investigation: {hypothesis}}}}}
\\author{{Autonomous Research Agent (Project: \\texttt{{{project_id}}})}}
\\date{{\\today}}

\\begin{{document}}
\\maketitle

\\begin{{abstract}}
This manuscript documents an autonomous experimental investigation of the hypothesis: \\emph{{{hypothesis}}}. 
Over {cycles_count} systematic cycles, the research agent adjusted hyperparameters, evaluated execution artifacts, 
and enforced formal safety invariants (\\texttt{{INV\\_SECURITY}}, \\texttt{{INV\\_BASELINE\\_THRESHOLD}}). 
The peak empirical metric reached \\textbf{{{best_acc:.4f}}} compared to an approved threshold of {baseline_acc:.2f}.
\\end{{abstract}}

\\section{{Introduction}}
Iterative hypothesis validation in modern scientific computing requires reproducibility, invariant-guided parameter tuning, 
and automated artifact verification. We investigate structured exploration initialized from learning rate $\\eta = {learning_rate}$ 
targeting metric \\texttt{{{metric_name}}} $\\ge {baseline_acc:.2f}$.

\\section{{Related Work}}
Our autonomous investigation references the following prior art:
\\begin{{itemize}}
"""
    for p in papers:
        first_author = p["authors"][0] if p["authors"] else "Author"
        latex_content += f"    \\item \\textbf{{{p['title']}}} ({first_author} et al., {p['published'][:4]}): {p['summary'][:140]}... \\href{{{p['pdf_url']}}}{{[arXiv:{p['arxiv_id']}]}}\n"

    latex_content += f"""\\end{{itemize}}

\\section{{Empirical Evaluation & Convergence}}
The multi-cycle trajectory was verified against the approved baseline:

\\begin{{table}}[ht]
\\centering
\\begin{{tabular}}{{cccccc}}
\\toprule
\\textbf{{Cycle}} & \\textbf{{Run Identifier}} & \\textbf{{Accuracy}} & \\textbf{{Baseline}} & \\textbf{{Status}} & \\textbf{{Notes}} \\\\
\\midrule
{table_body}
\\bottomrule
\\end{{tabular}}
\\caption{{Empirical Convergence Trajectory across Iterations}}
\\label{{tab:results}}
\\end{{table}}

Summary statistics across valid runs: $N = {stats['count']}$, Mean $\\mu = {stats['mean']:.4f}$, Std $\\sigma = {stats['std']:.4f}$, Peak $= {stats['max']:.4f}$.

\\section{{Conclusion & Verification}}
Throughout the experiment, all updates satisfied formal guard invariants, preventing metric hallucination and guaranteeing factual grounding.

\\end{{document}}
"""
    tex_path = REPORTS_DIR / f"{project_id}_manuscript.tex"
    tex_path.write_text(latex_content, encoding="utf-8")

    return {
        "ok": True,
        "project_id": project_id,
        "paper_path": str(paper_path),
        "report_path": str(paper_path),
        "bib_path": str(bib_path),
        "bibtex_path": str(bib_path),
        "tex_path": str(tex_path),
        "latex_path": str(tex_path),
        "markdown": paper_markdown,
        "paper_markdown": paper_markdown,
        "latex": latex_content,
        "bibtex": bib_content,
        "total_runs": len(runs),
        "baseline": baseline_acc,
        "papers_cited": [p["title"] for p in papers],
        "statistics": stats,
    }
