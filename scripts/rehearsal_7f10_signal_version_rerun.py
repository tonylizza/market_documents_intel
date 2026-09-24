"""Track 7F.10 rehearsal only: simulate a metric-only `SIGNAL_VERSION` bump.

Creates a fresh `LanguageSignalRun` for every pair (as
`pairs language-build-all` would after a real `SIGNAL_VERSION` bump), under
a rehearsal-only signal version. Per-passage signal content is byte-for-byte
identical; only the research `PassageLanguageSignal.id`s (and the run's
`configuration_hash`) change, which is exactly what made 7F.9's re-run
duplicate the shared signal-artifact generation.

Refuses to run unless DATABASE_URL names a database whose name ends in
`_rehearsal`. It must never touch the research system of record: clone
it first (CREATE DATABASE <name>_rehearsal TEMPLATE market_documents).

Usage:
    DATABASE_URL=postgresql+psycopg://.../market_documents_7f10_rehearsal \
        .venv/bin/python scripts/rehearsal_7f10_signal_version_rerun.py
"""

from __future__ import annotations

from urllib.parse import urlsplit

from market_documents.config import get_settings
from market_documents.db.session import get_session
from market_documents.services import financial_language_config, financial_language_signals

REHEARSAL_SIGNAL_VERSION = "1.4.0+7f10-rehearsal"


def main() -> None:
    database = urlsplit(get_settings().database_url).path.lstrip("/")
    if not database.endswith("_rehearsal"):
        raise SystemExit(f"refusing to run against {database!r}: DATABASE_URL must name a *_rehearsal clone")

    # `compute_configuration_hash` reads the config module's global; the run
    # row's `signal_version` comes from the name imported into the service.
    financial_language_config.SIGNAL_VERSION = REHEARSAL_SIGNAL_VERSION
    financial_language_signals.SIGNAL_VERSION = REHEARSAL_SIGNAL_VERSION

    # No `force`: the changed configuration_hash alone must trigger a rebuild,
    # exactly as a real SIGNAL_VERSION bump does.
    with get_session() as session:
        outcome = financial_language_signals.build_eligible_language_signals(session)
    print(f"database={database} signal_version={REHEARSAL_SIGNAL_VERSION}")
    print(
        f"completed={len(outcome.completed)} with_warnings={len(outcome.completed_with_warnings)} "
        f"skipped={len(outcome.skipped)} ineligible={len(outcome.ineligible)} failed={len(outcome.failed)}"
    )


if __name__ == "__main__":
    main()
