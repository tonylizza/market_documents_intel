import subprocess
import uuid
from pathlib import Path

import typer
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select, text

from market_documents.config import get_settings
from market_documents.db.session import get_session
from market_documents.publishing import audit
from market_documents.publishing.models import ApplicationState, Company, Publication, PublicationStatus
from market_documents.publishing.publisher import PublicationBuilder, activate_publication, cleanup_publications
from market_documents.publishing.retrieval_benchmark import (
    run_company_filtered_benchmark,
    run_unfiltered_benchmark,
)
from market_documents.publishing.session import app_session_scope, assert_distinct_databases
from market_documents.publishing.validation import validate_persisted

app = typer.Typer(help="Application/publication-layer commands (Milestone 7A.1).")

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _target_url(target_database_url: str | None) -> str:
    return target_database_url or get_settings().app_database_url


def _app_alembic_config(target_database_url: str) -> AlembicConfig:
    cfg = AlembicConfig(str(_REPO_ROOT / "alembic_app.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations_app"))
    cfg.set_main_option("sqlalchemy.url", target_database_url)
    return cfg


@app.command("app-init")
def app_init(
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
) -> None:
    """Initialize (or upgrade) a blank application database to the current schema head."""
    url = _target_url(target_database_url)
    settings = get_settings()
    assert_distinct_databases(settings.database_url, url, settings.allow_same_database_dev_mode)
    cfg = _app_alembic_config(url)
    command.upgrade(cfg, "head")
    typer.echo("[OK]   application schema initialized/upgraded to head")


@app.command("app-status")
def app_status(
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
) -> None:
    """Verify application-database connectivity, migration status, and active publication."""
    url = _target_url(target_database_url)
    from market_documents.publishing.session import create_app_engine

    engine = create_app_engine(url)

    connectivity_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        connectivity_ok = True
        typer.echo("[OK]   database connectivity")
    except Exception as exc:
        typer.echo(f"[FAIL] database connectivity: {exc}")

    all_ok = connectivity_ok
    if connectivity_ok:
        cfg = _app_alembic_config(url)
        script = ScriptDirectory.from_config(cfg)
        head_rev = script.get_current_head()
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"version_table_schema": "app_internal"})
            current_rev = context.get_current_revision()
        migrations_ok = current_rev == head_rev
        typer.echo(
            f"[OK]   migrations up to date (revision {current_rev})"
            if migrations_ok
            else f"[FAIL] migrations out of date (current={current_rev}, head={head_rev})"
        )
        all_ok = all_ok and migrations_ok

        with app_session_scope(url) as session:
            state = session.get(ApplicationState, "active")
            if state is None or state.active_publication_id is None:
                typer.echo("[INFO] no active publication")
            else:
                pub = session.get(Publication, state.active_publication_id)
                typer.echo(
                    f"[INFO] active publication: {pub.publication_version} "
                    f"(id={pub.id}, status={pub.status}, activated_at={pub.activated_at})"
                )

    if not all_ok:
        raise typer.Exit(code=1)


@app.command("app-init-roles")
def app_init_roles(
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
    publisher_password_env: str = typer.Option(..., "--publisher-password-env"),
    readonly_password_env: str = typer.Option(..., "--readonly-password-env"),
    sql_path: Path = typer.Option(_REPO_ROOT / "scripts" / "sql" / "app_roles.sql", "--sql-path"),
) -> None:
    """Create/update the app_publisher and app_readonly roles via psql, reading passwords from env vars."""
    import os

    url = _target_url(target_database_url)
    # psql's libpq URL parser doesn't understand SQLAlchemy's `+driver`
    # dialect suffix (e.g. `postgresql+psycopg://`) -- strip it down to the
    # plain `postgresql://` scheme libpq expects.
    psql_url = url.replace("postgresql+psycopg://", "postgresql://")
    publisher_pw = os.environ.get(publisher_password_env)
    readonly_pw = os.environ.get(readonly_password_env)
    if not publisher_pw or not readonly_pw:
        typer.echo(f"[FAIL] {publisher_password_env} and {readonly_password_env} must both be set in the environment")
        raise typer.Exit(code=1)

    result = subprocess.run(
        [
            "psql",
            psql_url,
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            f"publisher_pw={publisher_pw}",
            "-v",
            f"readonly_pw={readonly_pw}",
            "-f",
            str(sql_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        typer.echo(f"[FAIL] role setup failed: {result.stderr or result.stdout}")
        raise typer.Exit(code=1)
    typer.echo("[OK]   app_publisher/app_readonly roles created or already present")


@app.command("build")
def build(
    publication_version: str = typer.Option(..., "--publication-version"),
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
) -> None:
    """Build a new publication from the current accepted research dataset."""
    url = _target_url(target_database_url)
    settings = get_settings()
    assert_distinct_databases(settings.database_url, url, settings.allow_same_database_dev_mode)

    builder = PublicationBuilder(publication_version=publication_version, settings=settings)
    with get_session() as research_session:
        with app_session_scope(url) as app_session:
            publication = builder.build(research_session, app_session)

    typer.echo(f"status={publication.status} publication_id={publication.id} version={publication.publication_version}")
    if publication.status == PublicationStatus.FAILED.value:
        typer.echo(f"failure_reason: {publication.failure_reason}")
        raise typer.Exit(code=1)


@app.command("validate")
def validate(
    publication_id: uuid.UUID = typer.Option(..., "--publication-id"),
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
) -> None:
    """Re-run validation against an already-built publication."""
    url = _target_url(target_database_url)
    with app_session_scope(url) as session:
        summary = validate_persisted(session, publication_id)
        publication = session.get(Publication, publication_id)
        if publication is not None:
            publication.validation_summary = summary.to_dict()

    typer.echo(f"checks_run={summary.checks_run} passed={summary.passed}")
    for failure in summary.failures:
        typer.echo(f"  [FAIL] {failure.check}: {failure.detail}")
    if not summary.passed:
        raise typer.Exit(code=1)


@app.command("promote")
def promote(
    publication_id: uuid.UUID = typer.Option(..., "--publication-id"),
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
) -> None:
    """Atomically activate a READY publication, superseding the prior ACTIVE one."""
    url = _target_url(target_database_url)
    with app_session_scope(url) as session:
        try:
            activate_publication(session, publication_id)
        except ValueError as exc:
            typer.echo(f"[FAIL] {exc}")
            raise typer.Exit(code=1) from exc
    typer.echo(f"[OK]   publication {publication_id} is now ACTIVE")


@app.command("list")
def list_publications(
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
) -> None:
    """List all publications and their status."""
    from sqlalchemy import select

    url = _target_url(target_database_url)
    with app_session_scope(url) as session:
        publications = list(session.scalars(select(Publication).order_by(Publication.created_at)))
        for p in publications:
            typer.echo(f"{p.publication_version}\t{p.id}\t{p.status}\tcomparisons={p.comparison_count}")


@app.command("show")
def show(
    publication_id: uuid.UUID = typer.Option(..., "--publication-id"),
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
) -> None:
    """Show full detail for one publication."""
    url = _target_url(target_database_url)
    with app_session_scope(url) as session:
        p = session.get(Publication, publication_id)
        if p is None:
            typer.echo(f"[FAIL] no publication with id {publication_id}")
            raise typer.Exit(code=1)
        typer.echo(f"publication_version: {p.publication_version}")
        typer.echo(f"status: {p.status}")
        typer.echo(f"source_schema_version: {p.source_schema_version}")
        typer.echo(f"source_configuration_hash: {p.source_configuration_hash}")
        typer.echo(f"started_at: {p.started_at}")
        typer.echo(f"completed_at: {p.completed_at}")
        typer.echo(f"activated_at: {p.activated_at}")
        typer.echo(f"company_count: {p.company_count}")
        typer.echo(f"report_count: {p.report_count}")
        typer.echo(f"comparison_count: {p.comparison_count}")
        typer.echo(f"passage_count: {p.passage_count}")
        typer.echo(f"passage_comparison_count: {p.passage_comparison_count}")
        typer.echo(f"language_metric_count: {p.language_metric_count}")
        typer.echo(f"passage_language_signal_count: {p.passage_language_signal_count}")
        typer.echo(f"discovery_item_count: {p.discovery_item_count}")
        typer.echo(f"failure_reason: {p.failure_reason}")


@app.command("audit")
def audit_cmd(
    publication_id: uuid.UUID = typer.Option(..., "--publication-id"),
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
    output_dir: Path = typer.Option(Path("data/audits"), "--output-dir"),
) -> None:
    """Write the full set of publication audit CSVs."""
    url = _target_url(target_database_url)
    with app_session_scope(url) as session:
        audit.write_audit_csv(audit.build_publication_run_audit_rows(session), output_dir / "publication_run_audit.csv")
        audit.write_audit_csv(
            audit.build_publication_company_audit_rows(session, publication_id),
            output_dir / "publication_company_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_comparison_audit_rows(session, publication_id),
            output_dir / "publication_comparison_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_lineage_audit_rows(session, publication_id),
            output_dir / "publication_lineage_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_validation_failure_rows(session, publication_id),
            output_dir / "publication_validation_failures.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_discovery_ranking_audit_rows(session, publication_id),
            output_dir / "publication_discovery_ranking_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_table_count_rows(session, publication_id),
            output_dir / "publication_table_counts.csv",
        )
        audit.write_audit_csv(
            audit.build_deterministic_publication_review_sample_rows(session, publication_id),
            output_dir / "deterministic_publication_review_sample.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_embedding_audit_rows(session, publication_id),
            output_dir / "publication_embedding_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_embedding_lineage_audit_rows(session, publication_id),
            output_dir / "publication_embedding_lineage_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_embedding_missing_audit_rows(session, publication_id),
            output_dir / "publication_embedding_missing_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_vector_integrity_audit_rows(session, publication_id),
            output_dir / "publication_vector_integrity_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_retrieval_context_audit_rows(session, publication_id),
            output_dir / "publication_retrieval_context_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_retrieval_context_duplicate_audit_rows(session, publication_id),
            output_dir / "publication_retrieval_context_duplicate_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_qa_chunk_embedding_audit_rows(session, publication_id),
            output_dir / "qa_chunk_embedding_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_qa_chunk_lineage_audit_rows(session, publication_id),
            output_dir / "qa_chunk_lineage_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_qa_chunk_duplicate_audit_rows(session, publication_id),
            output_dir / "qa_chunk_duplicate_audit.csv",
        )
        audit.write_audit_csv(
            audit.build_publication_qa_chunk_vector_integrity_audit_rows(session, publication_id),
            output_dir / "qa_chunk_vector_integrity_audit.csv",
        )
    typer.echo(f"[OK]   audit CSVs written to {output_dir}")


@app.command("benchmark")
def benchmark_cmd(
    publication_id: uuid.UUID = typer.Option(..., "--publication-id"),
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
    output_dir: Path = typer.Option(Path("data/audits"), "--output-dir"),
    top_k: int = typer.Option(10, "--top-k"),
) -> None:
    """Compare exact vs. HNSW retrieval on this publication's embeddings and
    write `publication_retrieval_benchmark.csv`."""
    url = _target_url(target_database_url)
    rows = []
    with app_session_scope(url) as session:
        unfiltered = run_unfiltered_benchmark(session, publication_id, top_k=top_k)
        rows.append(unfiltered)
        typer.echo(f"[unfiltered] {unfiltered}")

        first_company_id = session.execute(
            select(Company.id).where(Company.publication_id == publication_id).order_by(Company.display_order).limit(1)
        ).scalar_one_or_none()
        if first_company_id is not None:
            filtered = run_company_filtered_benchmark(session, publication_id, first_company_id, top_k=top_k)
            rows.append(filtered)
            typer.echo(f"[company-filtered] {filtered}")

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "publication_retrieval_benchmark.csv"
    with csv_path.open("w", newline="") as fh:
        import csv as csv_module

        writer = csv_module.DictWriter(
            fh,
            fieldnames=[
                "scope",
                "query_count",
                "recall_at_1",
                "recall_at_5",
                "recall_at_10",
                "mean_exact_latency_ms",
                "mean_indexed_latency_ms",
                "indexed_plan_uses_vector_index",
                "meets_minimum_recall_at_10",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(vars(r))
    typer.echo(f"[OK]   benchmark CSV written to {csv_path}")


@app.command("cleanup")
def cleanup(
    target_database_url: str = typer.Option(None, "--target-database-url", envvar="APP_DATABASE_URL"),
    keep: int = typer.Option(2, "--keep"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Remove FAILED and old SUPERSEDED publications, retaining ACTIVE and the latest `keep`."""
    url = _target_url(target_database_url)
    with app_session_scope(url) as session:
        removed = cleanup_publications(session, keep=keep, dry_run=dry_run)
    verb = "would remove" if dry_run else "removed"
    typer.echo(f"[OK]   {verb} {len(removed)} publication(s)")
    for p in removed:
        typer.echo(f"  {p.publication_version}\t{p.id}\t{p.status}")
