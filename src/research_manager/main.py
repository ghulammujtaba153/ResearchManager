"""CLI for Research Experiment Manager."""

from __future__ import annotations

import json

import typer

from research_manager.agent import workflow

app = typer.Typer(add_completion=False, help="Research Experiment Manager", no_args_is_help=True)


@app.command()
def demo(project_id: str = "demo", cycles: int = 3) -> None:
    """Run the full multi-cycle demo."""
    state = workflow.run_demo(project_id=project_id, max_cycles=cycles)
    typer.echo(json.dumps(state.model_dump(), indent=2))


@app.command()
def onboard(project_id: str = "demo", baseline: float = 0.75) -> None:
    result = workflow.onboard_project(project_id, baseline_accuracy=baseline)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def cycle(
    project_id: str = "demo",
    memory: bool = True,
    key: str | None = None,
    real: bool = typer.Option(False, "--real", help="Run real training script in OS subprocess"),
) -> None:
    runner_mode = "real" if real else "simulator"
    result = workflow.run_cycle(
        project_id,
        use_memory=memory,
        idempotency_key=key,
        runner_mode=runner_mode,
    )
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command()
def resume(project_id: str = "demo") -> None:
    result = workflow.resume_project(project_id)
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command("correct-fact")
def correct_fact_cmd(project_id: str, fact_key: str, value: str) -> None:
    parsed: object
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = float(value)
        except ValueError:
            parsed = value
    result = workflow.correct_fact(project_id, fact_key, parsed)
    typer.echo(json.dumps(result, indent=2))


@app.command()
def approve(
    project_id: str = "demo",
    reject: bool = typer.Option(False, "--reject", help="Reject the decision instead of approving"),
    comment: str = typer.Option("", "--comment", "-c", help="Supervisor guidance or comment"),
    learning_rate: float | None = typer.Option(None, "--lr", help="Override learning rate"),
) -> None:
    """Approve or reject pending decision with optional parameter overrides."""
    overrides = {}
    if learning_rate is not None:
        overrides["learning_rate"] = learning_rate
    result = workflow.approve_decision(
        project_id,
        approved=not reject,
        comment=comment,
        override_params=overrides if overrides else None,
    )
    typer.echo(json.dumps(result, indent=2))


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        demo()


if __name__ == "__main__":
    app()
