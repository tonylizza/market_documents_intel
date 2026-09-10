"""Milestone 7 human-labeled construct-validation CLI.

Thin handlers only -- sampling logic lives in
`services/human_validation_sampling.py`, metrics in
`services/human_validation_analysis.py`.
"""

import json
from pathlib import Path

import typer

from market_documents.db.session import get_session
from market_documents.services import human_validation_analysis as analysis
from market_documents.services import human_validation_quality_sample as quality_sample
from market_documents.services import human_validation_sampling as sampling

app = typer.Typer(help="Milestone 7: human-labeled construct validation.")


@app.command("build-sample")
def build_sample_cmd(
    output_dir: Path = typer.Option(Path("validation"), "--output-dir", help="Directory for the CSV artifacts."),
    seed: int = typer.Option(sampling.DEFAULT_SEED, "--seed", help="Deterministic sampling seed."),
) -> None:
    """Build the Milestone 7 validation sample: full (internal) and blinded (reviewer) CSVs."""
    with get_session() as session:
        cases, available = sampling.build_validation_sample(session, seed=seed)

    full_path = output_dir / "human_validation_cases.csv"
    blinded_path = output_dir / "human_validation_cases_blinded.csv"
    sampling.write_full_csv(cases, full_path)
    sampling.write_blinded_csv(cases, blinded_path)

    typer.echo(f"Available population by bucket: {available}")
    typer.echo(f"Wrote {len(cases)} case(s) to {full_path}")
    typer.echo(f"Wrote blinded reviewer export to {blinded_path}")


@app.command("build-quality-sample")
def build_quality_sample_cmd(
    output_dir: Path = typer.Option(Path("validation"), "--output-dir", help="Directory for the CSV artifact."),
    seed: int = typer.Option(quality_sample.DEFAULT_SEED, "--seed", help="Deterministic sampling seed."),
    target: int = typer.Option(quality_sample.DEFAULT_TARGET, "--target", help="Target sample size."),
) -> None:
    """Build the Milestone 7 Section 11 passage-quality review subset."""
    with get_session() as session:
        cases = quality_sample.build_quality_sample(session, seed=seed, target=target)

    output_path = output_dir / "passage_quality_review_sample.csv"
    quality_sample.write_quality_sample_csv(cases, output_path)
    typer.echo(f"Wrote {len(cases)} case(s) to {output_path}")


@app.command("analyze")
def analyze_cmd(
    labeled_csv: Path = typer.Argument(..., help="Path to a labeled human_validation_cases*.csv."),
    output: Path = typer.Option(None, "--output", "-o", help="Optional path to write the metrics as JSON."),
) -> None:
    """Compute Milestone 7 construct-validation metrics from labeled cases."""
    rows = analysis.load_labeled_csv(labeled_csv)

    report = {
        "n_rows": len(rows),
        "correspondence_precision_overall": analysis.correspondence_precision(rows),
        "correspondence_precision_by_confidence": analysis.correspondence_precision(rows, group_by="system_confidence"),
        "correspondence_precision_by_company": analysis.correspondence_precision(rows, group_by="company"),
        "unmatched_validity": dict(analysis.unmatched_validity(rows)),
        "change_confusion_matrix": analysis.change_confusion_matrix(rows),
        "binary_change_metrics": analysis.binary_change_metrics(rows),
        "ordered_change_agreement": analysis.ordered_change_agreement(rows),
        "similarity_vs_human_change": analysis.similarity_vs_human_change(rows),
    }

    text = json.dumps(report, indent=2, default=str)
    if output:
        output.write_text(text)
        typer.echo(f"Wrote metrics to {output}")
    else:
        typer.echo(text)
