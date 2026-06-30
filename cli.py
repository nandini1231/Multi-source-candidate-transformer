"""CLI entry point for the candidate data transformer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from src.pipeline import Pipeline

app = typer.Typer(
    name="candidate-transform",
    help="Multi-source candidate data transformer — deterministic, explainable, configurable.",
    add_completion=False,
)
console = Console()


@app.command()
def transform(
    csv: Optional[Path] = typer.Option(
        None, "--csv", help="Path to recruiter CSV export.", exists=False,
    ),
    resume_dir: Optional[Path] = typer.Option(
        None, "--resume-dir", help="Directory containing resume files (PDF / DOCX).",
    ),
    config: Path = typer.Option(
        Path("config/projection_config.json"),
        "--config",
        help="Path to projection config JSON.",
    ),
    engine_config: Path = typer.Option(
        Path("config/engine_config.json"),
        "--engine-config",
        help="Path to engine config JSON.",
    ),
    output: Path = typer.Option(
        Path("data/sample_outputs/output.json"),
        "--output",
        help="Path to write output JSON.",
    ),
    pretty: bool = typer.Option(True, "--pretty/--compact", help="Pretty-print output JSON."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run the full transformation pipeline on provided sources."""
    if verbose:
        logging.getLogger("eightfold").setLevel(logging.DEBUG)

    if csv is None and resume_dir is None:
        console.print("[red]Error:[/red] Provide at least one of --csv or --resume-dir.")
        raise typer.Exit(code=1)

    if csv is not None and not csv.exists():
        console.print(f"[red]Error:[/red] CSV file not found: {csv}")
        raise typer.Exit(code=1)

    if resume_dir is not None and not resume_dir.is_dir():
        console.print(f"[red]Error:[/red] Resume directory not found: {resume_dir}")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Eightfold Candidate Transformer[/bold cyan]")
    console.print(f"  Engine config  : {engine_config}")
    console.print(f"  Projection     : {config}")
    console.print(f"  Output         : {output}")
    console.print()

    pipeline = Pipeline(engine_config_path=engine_config, projection_config_path=config)

    with console.status("[bold green]Processing…[/bold green]"):
        result = pipeline.run(csv_path=csv, resume_dir=resume_dir)

    pipeline.write_output(result, output_path=output, pretty=pretty)

    # Print summary table
    table = Table(title="Run Summary", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Total candidates", str(result.summary.total))
    table.add_row("Active", str(result.summary.active))
    table.add_row("Manual review", str(result.summary.manual_review))
    table.add_row("Errors / skipped", str(result.summary.errors))
    console.print(table)
    console.print(f"\n[green]Done.[/green] Output written to [bold]{output}[/bold]")


if __name__ == "__main__":
    app()
