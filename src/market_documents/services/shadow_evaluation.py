"""Track 7C.5 shadow evaluation: read-only comparison of the legacy
passage-alignment pipeline against the new semantic-unit / structured-table
pipeline, for the purpose of a cutover-readiness decision.

This module does not run, mutate, or persist anything -- it only reads
already-persisted output of both pipelines (`Passage`/`PassageAlignment` on
the legacy side; `SemanticUnit`/`SemanticUnitAlignment`/`AnalyticalDecision`/
`StructuredTable*` on the new side) and computes descriptive metrics.
Manual correspondence judgment against source-PDF evidence (docs/7c5-shadow-
replacement-readiness.md) is out of scope for automation and is not
attempted here -- see that document for the reviewed sample.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.analytical_comparison import AnalyticalDecisionRun
from market_documents.models.alignment import AlignmentRun
from market_documents.models.company import Company
from market_documents.models.enums import NormalizedSchedule, SemanticUnitAlignmentStatus
from market_documents.models.passage import Passage
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.models.semantic_unit import SemanticUnit, SemanticUnitRun
from market_documents.models.semantic_unit_alignment import SemanticUnitAlignmentRun
from market_documents.services.structured_table_comparison import get_current_alignment_run as get_current_structured_alignment_run
from market_documents.services.structured_table_config import table_family_configs_for
from market_documents.services.structured_table_reconstruction import get_current_extraction_run as get_current_structured_extraction_run

SHORT_PASSAGE_WORD_COUNT = 15


class DifferenceClassification:
    """The five outcome buckets from docs' Track 7C.5 Section 7 -- 'no
    forced numeric parity with legacy'. A plain string-constant namespace,
    not an enum stored anywhere, since this is a reporting-time label, not
    a persisted analytical fact.
    """

    EXPECTED_ARCHITECTURAL_IMPROVEMENT = "EXPECTED_ARCHITECTURAL_IMPROVEMENT"
    EQUIVALENT_RESULT_DIFFERENT_BOUNDARY = "EQUIVALENT_RESULT_DIFFERENT_BOUNDARY"
    NEW_PIPELINE_DEFECT = "NEW_PIPELINE_DEFECT"
    LEGACY_PIPELINE_DEFECT = "LEGACY_PIPELINE_DEFECT"
    INCONCLUSIVE = "INCONCLUSIVE_REVIEW_REQUIRED"


def classify_difference(
    new_status: SemanticUnitAlignmentStatus, *, known_new_pipeline_recall_defect: bool
) -> str:
    """Classify one semantic-unit-alignment outcome per Section 7's taxonomy.

    `known_new_pipeline_recall_defect` is supplied by the caller from a
    manually-verified real-corpus finding (e.g. "legacy shows the heading
    exists but the new pipeline reported it not found") -- this function
    never guesses that from statistics alone, since distinguishing a
    genuine absence from a missed extraction requires reading the actual
    source text (Section 5's manual review), not a heuristic.
    """
    if known_new_pipeline_recall_defect:
        return DifferenceClassification.NEW_PIPELINE_DEFECT
    if new_status == SemanticUnitAlignmentStatus.MATCHED:
        return DifferenceClassification.EQUIVALENT_RESULT_DIFFERENT_BOUNDARY
    if new_status == SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM:
        return DifferenceClassification.EXPECTED_ARCHITECTURAL_IMPROVEMENT
    return DifferenceClassification.INCONCLUSIVE


@dataclass(frozen=True)
class LegacyPassageStats:
    directory_year: int
    passage_count: int
    short_passage_count: int
    excluded_count: int
    passage_type_counts: dict[str, int]

    @property
    def short_passage_fraction(self) -> float | None:
        if self.passage_count == 0:
            return None
        return self.short_passage_count / self.passage_count


@dataclass(frozen=True)
class LegacyAlignmentStats:
    pair_label: str
    total: int
    status_counts: dict[str, int]
    confidence_counts: dict[str, int]

    @property
    def needs_review_fraction(self) -> float | None:
        if self.total == 0:
            return None
        return self.confidence_counts.get("NEEDS_REVIEW", 0) / self.total


@dataclass(frozen=True)
class NewUnitStats:
    directory_year: int
    unit_run_status: str | None
    resolved_unit_count: int
    provenance_complete: bool
    review_reason: str | None


@dataclass(frozen=True)
class NewAlignmentStats:
    pair_label: str
    alignment_run_status: str | None
    total: int
    status_counts: dict[str, int]
    decision_run_status: str | None
    analytical_mode_counts: dict[str, int]


@dataclass(frozen=True)
class StructuredTableStats:
    table_family_key: str
    directory_year: int
    reconstruction_status: str | None
    row_count: int
    column_count: int
    footnote_count: int


@dataclass(frozen=True)
class StructuredComparisonStats:
    table_family_key: str
    pair_label: str
    alignment_status: str | None
    row_status_counts: dict[str, int]
    value_change_event_counts: dict[str, int]


@dataclass
class TickerEvaluation:
    ticker: str
    legacy_passages: list[LegacyPassageStats] = field(default_factory=list)
    legacy_alignments: list[LegacyAlignmentStats] = field(default_factory=list)
    new_units: list[NewUnitStats] = field(default_factory=list)
    new_alignments: list[NewAlignmentStats] = field(default_factory=list)
    structured_tables: list[StructuredTableStats] = field(default_factory=list)
    structured_comparisons: list[StructuredComparisonStats] = field(default_factory=list)


@dataclass
class ShadowEvaluationReport:
    tickers: list[TickerEvaluation] = field(default_factory=list)


def _reports_for_ticker(session: Session, ticker: str) -> list[Report]:
    company = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        return []
    return sorted(
        session.scalars(select(Report).where(Report.company_id == company.id)).all(),
        key=lambda r: r.directory_year,
    )


def _pairs_for_ticker(session: Session, ticker: str) -> list[ReportPair]:
    company = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        return []
    return sorted(
        session.scalars(select(ReportPair).where(ReportPair.company_id == company.id)).all(),
        key=lambda p: p.earlier_report.directory_year,
    )


def compute_legacy_passage_stats(session: Session, report: Report) -> LegacyPassageStats:
    passages = session.scalars(select(Passage).where(Passage.report_id == report.id)).all()
    short = sum(1 for p in passages if p.word_count < SHORT_PASSAGE_WORD_COUNT)
    excluded = sum(1 for p in passages if p.excluded_from_alignment)
    type_counts = Counter(p.passage_type.value for p in passages)
    return LegacyPassageStats(
        directory_year=report.directory_year,
        passage_count=len(passages),
        short_passage_count=short,
        excluded_count=excluded,
        passage_type_counts=dict(type_counts),
    )


def compute_legacy_alignment_stats(session: Session, pair: ReportPair) -> LegacyAlignmentStats | None:
    run = session.scalar(
        select(AlignmentRun).where(AlignmentRun.report_pair_id == pair.id).order_by(AlignmentRun.completed_at.desc())
    )
    label = f"{pair.earlier_report.directory_year}->{pair.later_report.directory_year}"
    if run is None:
        return None
    status_counts = Counter(a.alignment_status.value for a in run.alignments)
    confidence_counts = Counter(a.confidence.value for a in run.alignments)
    return LegacyAlignmentStats(
        pair_label=label,
        total=len(run.alignments),
        status_counts=dict(status_counts),
        confidence_counts=dict(confidence_counts),
    )


def compute_new_unit_stats(session: Session, report: Report, schedule: NormalizedSchedule) -> NewUnitStats:
    run = session.scalar(
        select(SemanticUnitRun)
        .where(SemanticUnitRun.report_id == report.id, SemanticUnitRun.schedule == schedule)
        .order_by(SemanticUnitRun.completed_at.desc())
    )
    if run is None:
        return NewUnitStats(
            directory_year=report.directory_year,
            unit_run_status=None,
            resolved_unit_count=0,
            provenance_complete=True,
            review_reason=None,
        )
    resolved = [u for u in run.units if u.boundary_status.value == "RESOLVED"]
    provenance_complete = all(len(u.source_blocks) > 0 for u in resolved)
    return NewUnitStats(
        directory_year=report.directory_year,
        unit_run_status=run.status.value,
        resolved_unit_count=len(resolved),
        provenance_complete=provenance_complete,
        review_reason=run.review_reason,
    )


def compute_new_alignment_stats(
    session: Session, pair: ReportPair, schedule: NormalizedSchedule
) -> NewAlignmentStats | None:
    label = f"{pair.earlier_report.directory_year}->{pair.later_report.directory_year}"
    arun = session.scalar(
        select(SemanticUnitAlignmentRun)
        .where(SemanticUnitAlignmentRun.report_pair_id == pair.id, SemanticUnitAlignmentRun.schedule == schedule)
        .order_by(SemanticUnitAlignmentRun.completed_at.desc())
    )
    if arun is None:
        return None
    status_counts = Counter(a.status.value for a in arun.alignments)

    drun = session.scalar(
        select(AnalyticalDecisionRun)
        .where(AnalyticalDecisionRun.report_pair_id == pair.id, AnalyticalDecisionRun.schedule == schedule)
        .order_by(AnalyticalDecisionRun.completed_at.desc())
    )
    mode_counts: Counter[str] = Counter()
    if drun is not None:
        for d in drun.decisions:
            mode_counts[d.analytical_mode.value] += 1

    return NewAlignmentStats(
        pair_label=label,
        alignment_run_status=arun.status.value,
        total=len(arun.alignments),
        status_counts=dict(status_counts),
        decision_run_status=None if drun is None else drun.status.value,
        analytical_mode_counts=dict(mode_counts),
    )


def compute_structured_table_stats(
    session: Session, report: Report, table_family_key: str
) -> StructuredTableStats:
    run = get_current_structured_extraction_run(session, report.id, table_family_key)
    if run is None:
        return StructuredTableStats(
            table_family_key=table_family_key,
            directory_year=report.directory_year,
            reconstruction_status=None,
            row_count=0,
            column_count=0,
            footnote_count=0,
        )
    table = next((t for t in run.tables if t.table_family_key == table_family_key), None)
    return StructuredTableStats(
        table_family_key=table_family_key,
        directory_year=report.directory_year,
        reconstruction_status=table.reconstruction_status.value if table else run.status.value,
        row_count=len(table.rows) if table else 0,
        column_count=len(table.columns) if table else 0,
        footnote_count=len(table.footnotes) if table else 0,
    )


def compute_structured_comparison_stats(
    session: Session, pair: ReportPair, table_family_key: str
) -> StructuredComparisonStats | None:
    run = get_current_structured_alignment_run(session, pair.id, table_family_key)
    label = f"{pair.earlier_report.directory_year}->{pair.later_report.directory_year}"
    if run is None:
        return None
    row_counts = Counter(ra.status.value for ra in run.row_alignments)
    event_counts = Counter(ev.event_type.value for ev in run.value_change_events)
    return StructuredComparisonStats(
        table_family_key=table_family_key,
        pair_label=label,
        alignment_status=run.status.value,
        row_status_counts=dict(row_counts),
        value_change_event_counts=dict(event_counts),
    )


def run_shadow_evaluation(
    session: Session, tickers: list[str], schedule: NormalizedSchedule = NormalizedSchedule.FINANCIAL_PERFORMANCE
) -> ShadowEvaluationReport:
    """Read-only: computes descriptive statistics from already-persisted
    legacy and new-pipeline output. Never runs, writes, or mutates either
    pipeline.
    """
    report = ShadowEvaluationReport()
    for ticker in tickers:
        te = TickerEvaluation(ticker=ticker.upper())
        reports = _reports_for_ticker(session, ticker)
        pairs = _pairs_for_ticker(session, ticker)

        for r in reports:
            te.legacy_passages.append(compute_legacy_passage_stats(session, r))
            te.new_units.append(compute_new_unit_stats(session, r, schedule))

        for p in pairs:
            legacy_stats = compute_legacy_alignment_stats(session, p)
            if legacy_stats is not None:
                te.legacy_alignments.append(legacy_stats)
            new_stats = compute_new_alignment_stats(session, p, schedule)
            if new_stats is not None:
                te.new_alignments.append(new_stats)

        for family in table_family_configs_for(te.ticker, NormalizedSchedule.REMUNERATION):
            for r in reports:
                te.structured_tables.append(compute_structured_table_stats(session, r, family.table_family_key))
            for p in pairs:
                comp = compute_structured_comparison_stats(session, p, family.table_family_key)
                if comp is not None:
                    te.structured_comparisons.append(comp)

        report.tickers.append(te)
    return report


def render_markdown_report(report: ShadowEvaluationReport) -> str:
    lines: list[str] = ["# 7C.5 Shadow Evaluation -- Computed Metrics\n"]
    for te in report.tickers:
        lines.append(f"## {te.ticker}\n")

        lines.append("### Legacy passages\n")
        lines.append("| Year | Passages | Short (<15w) | Excluded |")
        lines.append("|---|---|---|---|")
        for s in te.legacy_passages:
            lines.append(f"| {s.directory_year} | {s.passage_count} | {s.short_passage_count} | {s.excluded_count} |")
        lines.append("")

        lines.append("### Legacy alignment\n")
        lines.append("| Pair | Total | NEEDS_REVIEW fraction | Statuses |")
        lines.append("|---|---|---|---|")
        for a in te.legacy_alignments:
            frac = "n/a" if a.needs_review_fraction is None else f"{a.needs_review_fraction:.0%}"
            lines.append(f"| {a.pair_label} | {a.total} | {frac} | {a.status_counts} |")
        lines.append("")

        lines.append("### New semantic units\n")
        lines.append("| Year | Run status | Resolved units | Provenance complete | Review reason |")
        lines.append("|---|---|---|---|---|")
        for u in te.new_units:
            lines.append(
                f"| {u.directory_year} | {u.unit_run_status} | {u.resolved_unit_count} | "
                f"{u.provenance_complete} | {u.review_reason or ''} |"
            )
        lines.append("")

        lines.append("### New semantic-unit alignment\n")
        lines.append("| Pair | Align status | Total | Statuses | Decision status | Modes |")
        lines.append("|---|---|---|---|---|---|")
        for a in te.new_alignments:
            lines.append(
                f"| {a.pair_label} | {a.alignment_run_status} | {a.total} | {a.status_counts} | "
                f"{a.decision_run_status} | {a.analytical_mode_counts} |"
            )
        lines.append("")

        if te.structured_tables:
            lines.append("### Structured tables\n")
            lines.append("| Family | Year | Status | Rows | Columns | Footnotes |")
            lines.append("|---|---|---|---|---|---|")
            for t in te.structured_tables:
                lines.append(
                    f"| {t.table_family_key} | {t.directory_year} | {t.reconstruction_status} | "
                    f"{t.row_count} | {t.column_count} | {t.footnote_count} |"
                )
            lines.append("")

        if te.structured_comparisons:
            lines.append("### Structured-table comparison\n")
            lines.append("| Family | Pair | Status | Row statuses | Value-change events |")
            lines.append("|---|---|---|---|---|")
            for c in te.structured_comparisons:
                lines.append(
                    f"| {c.table_family_key} | {c.pair_label} | {c.alignment_status} | "
                    f"{c.row_status_counts} | {c.value_change_event_counts} |"
                )
            lines.append("")

    return "\n".join(lines)
