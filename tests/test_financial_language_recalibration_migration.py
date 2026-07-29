"""Migration round-trip validation for 18e705b62fee (Milestone 6
recalibration: report-side/alignment-change quality split).

Runs downgrade -> upgrade against the same test database the rest of the
suite uses, always restoring `head` in a `finally` block so a failure here
never leaves the schema downgraded for subsequent tests. Uses its own
Alembic `Config` (same construction as `conftest.engine`) rather than the
shared `db_session` fixture, since DDL is not contained by that fixture's
per-test savepoint.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from tests.conftest import TEST_DATABASE_URL

REPO_ROOT = Path(__file__).resolve().parents[1]

NEW_COLUMNS = {
    "report_side_signal_quality",
    "report_side_primary_eligible",
    "report_side_warning_reasons",
    "report_side_exclusion_reasons",
    "alignment_change_signal_quality",
    "alignment_change_primary_eligible",
    "alignment_change_warning_reasons",
    "alignment_change_exclusion_reasons",
    "dictionary_match_rate_earlier",
    "dictionary_match_rate_later",
    "collision_flagged_word_share",
    "unmatched_word_share",
    "alignment_change_analyzed_words_all",
    "alignment_change_analyzed_words_excl_ambiguous",
    "alignment_change_analyzed_words_hml",
    "alignment_change_analyzed_words_hm",
    "alignment_change_analyzed_words_h",
    "ambiguous_words_in_report_side",
}


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def _table_columns(engine) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("report_pair_language_features")}


def test_migration_downgrade_and_re_upgrade_round_trips(engine):
    """`engine` (session-scoped, already at head) guarantees the DB exists
    and starts at head before this test runs."""
    cfg = _alembic_config()
    try:
        columns_before = _table_columns(engine)
        assert NEW_COLUMNS.issubset(columns_before)

        command.downgrade(cfg, "-1")
        columns_after_downgrade = _table_columns(engine)
        assert NEW_COLUMNS.isdisjoint(columns_after_downgrade)

        command.upgrade(cfg, "head")
        columns_after_reupgrade = _table_columns(engine)
        assert NEW_COLUMNS.issubset(columns_after_reupgrade)
    finally:
        # Always leave the shared test database at head, regardless of
        # whether an assertion above failed mid-sequence.
        command.upgrade(cfg, "head")


def test_migration_reuses_existing_enum_type_no_duplicate(engine):
    from sqlalchemy import text

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT typname, count(*) FROM pg_type WHERE typname = 'language_signal_quality' GROUP BY typname")
        ).all()
    assert rows == [("language_signal_quality", 1)]
