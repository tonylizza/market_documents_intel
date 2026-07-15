from pathlib import Path

import typer
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from market_documents.db.session import get_engine

app = typer.Typer(help="Database diagnostics.")

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _migration_status(engine) -> tuple[str | None, str | None]:
    cfg = AlembicConfig(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    head_rev = script.get_current_head()

    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_rev = context.get_current_revision()

    return current_rev, head_rev


@app.command()
def check() -> None:
    """Verify database connectivity, pgvector availability, and migration status."""
    engine = get_engine()

    connectivity_ok = False
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        connectivity_ok = True
        typer.echo("[OK]   database connectivity")
    except Exception as exc:
        typer.echo(f"[FAIL] database connectivity: {exc}")

    has_vector = False
    current_rev = head_rev = None

    if connectivity_ok:
        with engine.connect() as conn:
            has_vector = (
                conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).first()
                is not None
            )
        typer.echo("[OK]   pgvector extension enabled" if has_vector else "[FAIL] pgvector extension not enabled")

        current_rev, head_rev = _migration_status(engine)
        if current_rev == head_rev:
            typer.echo(f"[OK]   migrations up to date (revision {current_rev})")
        else:
            typer.echo(f"[FAIL] migrations out of date (current={current_rev}, head={head_rev})")

    all_ok = connectivity_ok and has_vector and current_rev == head_rev
    if not all_ok:
        raise typer.Exit(code=1)
