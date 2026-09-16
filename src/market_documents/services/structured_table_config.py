"""Per-`table_family_key` reconstruction/routing configuration for Track
7C.4 structured-table comparison (docs/7c4-structured-table-comparison.md).

Mirrors `semantic_unit_config.py`'s shape (a small frozen-dataclass
registry, keyed by (ticker, table_family_key)), but with a **year-agnostic
heading regex** rather than a literal heading string: both configured table
families' headings embed the fiscal year and drift in case across ACT's
five sampled reports ("Non-executive Directors' 2020 remuneration" vs.
"NON-EXECUTIVE DIRECTORS' 2023 REMUNERATION"), so `semantic_unit_config.py`'s
literal-substring matching cannot be reused unmodified -- this is the
specific reason 7C.4 does not route through `SemanticUnit`/`UnitConfig`.

Only ACT, only these two families, per the milestone's explicit scope.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field

from market_documents.models.enums import AnalyticalMode, NormalizedSchedule, StructuredRowIdentityType

# v1.0.0 = initial two-family configuration (ACT ned_remuneration_policy_table,
# ACT total_remuneration_outcomes), per
# docs/experiments/annual-report-structured-table-comparison.md.
CONFIG_VERSION = "1.0.0"

_QUOTE_TRANSLATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def normalize_apostrophes(text: str) -> str:
    return text.translate(_QUOTE_TRANSLATION)


@dataclass(frozen=True)
class ColumnSchemaEntry:
    """One semantic column, in printed left-to-right order. `normalized_key`
    is the stable cross-year identity (brief Section 8: "column identity
    must be semantic, not positional only"); `source_label_by_year` is
    populated only where the printed label is known to drift, purely for
    display/evidence -- the reconstruction algorithm never infers meaning
    from label text for these two families (see module docstring)."""

    normalized_key: str
    group_label: str | None = None
    year_offset: int | None = None  # relative to the report's own year, e.g. 0 or -1
    is_restated: bool = False
    unit_or_currency: str | None = None


@dataclass(frozen=True)
class ColumnSchemaChange:
    """A known, source-confirmed schema change on an otherwise-MATCHED
    column -- never inferred (brief Section 14: "for ambiguous semantic
    changes: do not guess"). `first_affected_year` is the earlier report's
    directory_year from which the later side of a pair is no longer
    directly comparable to the earlier side on this column."""

    normalized_key: str
    first_affected_year: int
    reason: str


@dataclass(frozen=True)
class TableFamilyConfig:
    table_family_key: str
    ticker: str
    schedule: NormalizedSchedule
    row_identity_type: StructuredRowIdentityType
    analytical_mode: AnalyticalMode
    # Year-agnostic: matches the heading regardless of which fiscal year is
    # embedded in it or how the surrounding text is cased.
    heading_pattern: re.Pattern
    column_schema: tuple[ColumnSchemaEntry, ...]
    schema_changes: tuple[ColumnSchemaChange, ...] = field(default_factory=tuple)
    # Row label that always terminates row scanning (both families' data
    # rows end with a "TOTAL" line; ned_remuneration_policy_table simply
    # never emits one, so this never fires there).
    terminal_row_label: str | None = "TOTAL"

    @property
    def expected_column_count(self) -> int:
        return len(self.column_schema)


NED_REMUNERATION_POLICY_TABLE = TableFamilyConfig(
    table_family_key="ned_remuneration_policy_table",
    ticker="ACT",
    schedule=NormalizedSchedule.REMUNERATION,
    row_identity_type=StructuredRowIdentityType.ROLE,
    analytical_mode=AnalyticalMode.STRUCTURED_COMPARISON_PREFERRED,
    heading_pattern=re.compile(r"non-executive directors'\s+\d{4}\s+remuneration", re.IGNORECASE),
    column_schema=(
        ColumnSchemaEntry(normalized_key="current_fee", year_offset=0),
        ColumnSchemaEntry(normalized_key="proposed_fee", year_offset=1),
        ColumnSchemaEntry(normalized_key="recommended_increase_pct"),
    ),
    terminal_row_label=None,
)

TOTAL_REMUNERATION_OUTCOMES = TableFamilyConfig(
    table_family_key="total_remuneration_outcomes",
    ticker="ACT",
    schedule=NormalizedSchedule.REMUNERATION,
    row_identity_type=StructuredRowIdentityType.PERSON,
    analytical_mode=AnalyticalMode.STRUCTURED_COMPARISON_PREFERRED,
    heading_pattern=re.compile(r"total remuneration outcomes", re.IGNORECASE),
    column_schema=(
        ColumnSchemaEntry(normalized_key="base_pay", group_label="Guaranteed pay", year_offset=0),
        ColumnSchemaEntry(
            normalized_key="base_pay", group_label="Guaranteed pay", year_offset=-1, is_restated=True
        ),
        ColumnSchemaEntry(normalized_key="benefits_and_allowances", group_label="Guaranteed pay", year_offset=0),
        ColumnSchemaEntry(
            normalized_key="benefits_and_allowances", group_label="Guaranteed pay", year_offset=-1, is_restated=True
        ),
        ColumnSchemaEntry(normalized_key="sti", group_label="Variable pay", year_offset=0),
        ColumnSchemaEntry(normalized_key="sti", group_label="Variable pay", year_offset=-1, is_restated=True),
        ColumnSchemaEntry(normalized_key="lti", group_label="Variable pay", year_offset=0),
        ColumnSchemaEntry(normalized_key="lti", group_label="Variable pay", year_offset=-1, is_restated=True),
        ColumnSchemaEntry(normalized_key="total_remuneration", year_offset=0),
        ColumnSchemaEntry(normalized_key="total_remuneration", year_offset=-1, is_restated=True),
    ),
    schema_changes=(
        ColumnSchemaChange(
            normalized_key="sti",
            first_affected_year=2023,
            reason=(
                "Column header renamed 'STI' -> 'STI and Retention Awards' starting the 2023 report: a 2022 "
                "Remco-commissioned benchmarking review found LTI-award shortcomings, and since backdating share "
                "awards is not possible, cash retention payments were made instead and folded into this column "
                "(docs/experiments/annual-report-structured-table-comparison.md Section 8.2/11) -- same column "
                "position and key, but 2022-and-earlier values are not directly comparable in composition to "
                "2023-and-later values."
            ),
        ),
    ),
    terminal_row_label="TOTAL",
)

TABLE_FAMILY_CONFIGS: tuple[TableFamilyConfig, ...] = (NED_REMUNERATION_POLICY_TABLE, TOTAL_REMUNERATION_OUTCOMES)


def table_family_configs_for(ticker: str, schedule: NormalizedSchedule) -> tuple[TableFamilyConfig, ...]:
    return tuple(c for c in TABLE_FAMILY_CONFIGS if c.ticker == ticker and c.schedule == schedule)


def table_family_config_for_key(table_family_key: str) -> TableFamilyConfig | None:
    return next((c for c in TABLE_FAMILY_CONFIGS if c.table_family_key == table_family_key), None)


def schema_change_for(config: TableFamilyConfig, normalized_key: str, earlier_year: int, later_year: int) -> ColumnSchemaChange | None:
    """A schema change applies to a cross-year comparison when the later
    side's year has reached the change's `first_affected_year` and the
    earlier side has not -- i.e. it explains exactly the transition where
    the printed label/composition actually changed, not every later pair."""
    for change in config.schema_changes:
        if change.normalized_key != normalized_key:
            continue
        if earlier_year < change.first_affected_year <= later_year:
            return change
    return None


def compute_configuration_hash(configs: tuple[TableFamilyConfig, ...] = TABLE_FAMILY_CONFIGS) -> str:
    """Deterministic fingerprint of the table-family configuration in
    effect, so adding/changing a TableFamilyConfig forces a fresh
    StructuredTableExtractionRun instead of a stale skip."""
    payload = {
        "config_version": CONFIG_VERSION,
        "families": [
            {
                "table_family_key": c.table_family_key,
                "ticker": c.ticker,
                "schedule": c.schedule.value,
                "row_identity_type": c.row_identity_type.value,
                "analytical_mode": c.analytical_mode.value,
                "heading_pattern": c.heading_pattern.pattern,
                "column_schema": [
                    {
                        "normalized_key": e.normalized_key,
                        "group_label": e.group_label,
                        "year_offset": e.year_offset,
                        "is_restated": e.is_restated,
                        "unit_or_currency": e.unit_or_currency,
                    }
                    for e in c.column_schema
                ],
                "schema_changes": [
                    {
                        "normalized_key": s.normalized_key,
                        "first_affected_year": s.first_affected_year,
                        "reason": s.reason,
                    }
                    for s in c.schema_changes
                ],
                "terminal_row_label": c.terminal_row_label,
            }
            for c in configs
        ],
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
