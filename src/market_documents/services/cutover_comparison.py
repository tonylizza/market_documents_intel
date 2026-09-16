"""Track 7C.6 normalized comparison responses
(docs/7c6-production-cutover.md).

Given one `ReportPair` and a narrative unit or structured-table family,
routes the request through `ComparisonPathRouter` and returns a
discriminated, read-only response:

    NarrativeComparisonResponse   -- SEMANTIC_UNIT backend
    StructuredComparisonResponse  -- STRUCTURED_TABLE backend
    LegacyComparisonResponse      -- LEGACY_PASSAGE backend (out of scope;
                                     legacy remains authoritative)

This module never runs, mutates, or persists anything -- it only reads
already-persisted 7C.1-7C.5 output (mirroring `shadow_evaluation.py`'s
read-only contract) and never re-derives extraction, alignment, or
comparison. Critically: when a request is in new-pipeline scope but the
new pipeline has not produced a trustworthy result, this module returns an
explicit UNRESOLVED_UPSTREAM/AMBIGUOUS/REVIEW_REQUIRED response -- it never
silently substitutes a legacy result and presents it as the new pipeline's
own (docs/7c6-...md Section 4).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import (
    AlignmentConfidence,
    AnalyticalMode,
    ComparisonBackend,
    ComparisonResponseStatus,
    NormalizedSchedule,
    SemanticUnitAlignmentStatus,
    StructuredColumnAlignmentStatus,
    StructuredComparabilityStatus,
    StructuredRowAlignmentStatus,
    StructuredValueChangeEventType,
)
from market_documents.models.report_pair import ReportPair
from market_documents.models.semantic_unit import SemanticUnit
from market_documents.models.structured_table import (
    StructuredColumnAlignment,
    StructuredRowAlignment,
    StructuredTable,
    StructuredTableFootnote,
    StructuredValueChangeEvent,
)
from market_documents.services.analytical_eligibility import get_current_decision_run
from market_documents.services.comparison_routing import ComparisonPathRouter
from market_documents.services.semantic_unit_alignment import get_current_alignment_run
from market_documents.services.structured_table_comparison import (
    get_current_alignment_run as get_current_structured_alignment_run,
)

SOURCE_EXCERPT_MAX_CHARS = 400


# --------------------------------------------------------------------------
# Response envelope
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProvenanceRef:
    """The minimum provenance every new-pipeline response must carry
    (docs/7c6-...md Section 9): the report, the page(s), a persisted
    source-block id, and the exact source text (or an excerpt of it)."""

    report_id: uuid.UUID
    directory_year: int
    start_page: int
    end_page: int | None
    source_block_ids: tuple[uuid.UUID, ...]
    source_excerpt: str | None


@dataclass(frozen=True)
class LexicalMetricsView:
    tfidf_cosine: float | None
    unigram_jaccard: float | None
    bigram_jaccard: float | None
    edit_similarity: float | None
    sequence_similarity: float | None
    word_count_change: int | None
    word_count_change_pct: float | None


@dataclass(frozen=True)
class NarrativeComparisonResponse:
    comparison_backend: ComparisonBackend
    status: ComparisonResponseStatus
    report_pair_id: uuid.UUID
    earlier_report_id: uuid.UUID
    later_report_id: uuid.UUID
    schedule: NormalizedSchedule
    unit_key: str
    alignment_status: SemanticUnitAlignmentStatus | None = None
    alignment_confidence: AlignmentConfidence | None = None
    analytical_mode: AnalyticalMode | None = None
    lexical_metrics: LexicalMetricsView | None = None
    earlier_word_count: int | None = None
    later_word_count: int | None = None
    earlier_provenance: ProvenanceRef | None = None
    later_provenance: ProvenanceRef | None = None
    review_reason: str | None = None


@dataclass(frozen=True)
class StructuredRowAlignmentView:
    earlier_row_identity: str | None
    later_row_identity: str | None
    status: StructuredRowAlignmentStatus
    confidence: AlignmentConfidence
    evidence: str


@dataclass(frozen=True)
class StructuredColumnAlignmentView:
    normalized_key: str | None
    is_restated: bool
    status: StructuredColumnAlignmentStatus
    comparability_status: StructuredComparabilityStatus


@dataclass(frozen=True)
class StructuredValueChangeEventView:
    row_identity: str | None
    column_normalized_key: str | None
    event_type: StructuredValueChangeEventType
    earlier_raw_value: str | None
    later_raw_value: str | None
    earlier_numeric: float | None
    later_numeric: float | None
    absolute_change: float | None
    pct_change: float | None


@dataclass(frozen=True)
class StructuredComparisonResponse:
    comparison_backend: ComparisonBackend
    status: ComparisonResponseStatus
    report_pair_id: uuid.UUID
    earlier_report_id: uuid.UUID
    later_report_id: uuid.UUID
    table_family_key: str
    row_alignments: tuple[StructuredRowAlignmentView, ...] = ()
    column_alignments: tuple[StructuredColumnAlignmentView, ...] = ()
    value_change_events: tuple[StructuredValueChangeEventView, ...] = ()
    footnotes: tuple[str, ...] = ()
    earlier_provenance: ProvenanceRef | None = None
    later_provenance: ProvenanceRef | None = None
    review_reason: str | None = None


@dataclass(frozen=True)
class LegacyComparisonResponse:
    """Returned whenever routing selects LEGACY_PASSAGE -- either the
    cutover flag is off, or the request is outside the 7C.6 scope. Carries
    no comparison payload of its own: this module never re-derives legacy
    output, only signals that the legacy pipeline (unchanged, still
    running) remains authoritative for this request."""

    comparison_backend: ComparisonBackend
    status: ComparisonResponseStatus
    report_pair_id: uuid.UUID
    note: str
    audit_hint: str | None = field(default=None)


ComparisonResponse = NarrativeComparisonResponse | StructuredComparisonResponse | LegacyComparisonResponse


# --------------------------------------------------------------------------
# Narrative (SEMANTIC_UNIT)
# --------------------------------------------------------------------------


def _unit_provenance(unit: SemanticUnit | None) -> ProvenanceRef | None:
    if unit is None or unit.source_text is None:
        return None
    excerpt = unit.source_text if len(unit.source_text) <= SOURCE_EXCERPT_MAX_CHARS else unit.source_text[:SOURCE_EXCERPT_MAX_CHARS] + "..."
    return ProvenanceRef(
        report_id=unit.report_id,
        directory_year=unit.report.directory_year,
        start_page=unit.start_page,
        end_page=unit.end_page,
        source_block_ids=tuple(b.text_block_id for b in unit.source_blocks),
        source_excerpt=excerpt,
    )


def get_narrative_comparison(
    session: Session,
    report_pair: ReportPair,
    schedule: NormalizedSchedule,
    unit_key: str,
    *,
    router: ComparisonPathRouter | None = None,
) -> NarrativeComparisonResponse | LegacyComparisonResponse:
    router = router or ComparisonPathRouter()
    ticker = report_pair.company.ticker
    backend = router.route_narrative(ticker=ticker, schedule=schedule, unit_key=unit_key)

    if backend == ComparisonBackend.LEGACY_PASSAGE:
        reason = (
            "SEMANTIC_COMPARISON_CUTOVER_ENABLED is off"
            if not router.is_enabled()
            else f"{ticker} {schedule.value} unit {unit_key!r} is outside the Track 7C.6 cutover scope"
        )
        return LegacyComparisonResponse(
            comparison_backend=ComparisonBackend.LEGACY_PASSAGE,
            status=ComparisonResponseStatus.NOT_AVAILABLE,
            report_pair_id=report_pair.id,
            note=f"{reason} -- the legacy passage-alignment pipeline remains authoritative for this request.",
        )

    base = {
        "comparison_backend": ComparisonBackend.SEMANTIC_UNIT,
        "report_pair_id": report_pair.id,
        "earlier_report_id": report_pair.earlier_report_id,
        "later_report_id": report_pair.later_report_id,
        "schedule": schedule,
        "unit_key": unit_key,
    }

    alignment_run = get_current_alignment_run(session, report_pair.id, schedule)
    if alignment_run is None:
        return NarrativeComparisonResponse(
            status=ComparisonResponseStatus.UNRESOLVED_UPSTREAM,
            review_reason=f"no current successful SemanticUnitAlignmentRun for {schedule.value} on this report pair",
            **base,
        )

    alignment = next(
        (
            a
            for a in alignment_run.alignments
            if (a.earlier_semantic_unit is not None and a.earlier_semantic_unit.unit_key == unit_key)
            or (a.later_semantic_unit is not None and a.later_semantic_unit.unit_key == unit_key)
        ),
        None,
    )
    if alignment is None:
        return NarrativeComparisonResponse(
            status=ComparisonResponseStatus.UNRESOLVED_UPSTREAM,
            review_reason=f"no SemanticUnitAlignment for unit_key {unit_key!r} in the current alignment run",
            **base,
        )

    earlier_prov = _unit_provenance(alignment.earlier_semantic_unit)
    later_prov = _unit_provenance(alignment.later_semantic_unit)

    if alignment.status == SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM:
        return NarrativeComparisonResponse(
            status=ComparisonResponseStatus.UNRESOLVED_UPSTREAM,
            alignment_status=alignment.status,
            alignment_confidence=alignment.confidence,
            earlier_provenance=earlier_prov,
            later_provenance=later_prov,
            review_reason=alignment.evidence,
            **base,
        )
    if alignment.status == SemanticUnitAlignmentStatus.AMBIGUOUS:
        return NarrativeComparisonResponse(
            status=ComparisonResponseStatus.AMBIGUOUS,
            alignment_status=alignment.status,
            alignment_confidence=alignment.confidence,
            earlier_provenance=earlier_prov,
            later_provenance=later_prov,
            review_reason=alignment.evidence,
            **base,
        )

    decision_run = get_current_decision_run(session, report_pair.id, schedule)
    decision = (
        next((d for d in decision_run.decisions if d.semantic_unit_alignment_id == alignment.id), None)
        if decision_run is not None
        else None
    )

    if decision is None:
        return NarrativeComparisonResponse(
            status=ComparisonResponseStatus.REVIEW_REQUIRED,
            alignment_status=alignment.status,
            alignment_confidence=alignment.confidence,
            earlier_provenance=earlier_prov,
            later_provenance=later_prov,
            earlier_word_count=alignment.earlier_semantic_unit.word_count if alignment.earlier_semantic_unit else None,
            later_word_count=alignment.later_semantic_unit.word_count if alignment.later_semantic_unit else None,
            review_reason=f"no current AnalyticalDecision for this alignment ({schedule.value})",
            **base,
        )

    lexical_view = None
    if decision.lexical_comparison is not None:
        lc = decision.lexical_comparison
        lexical_view = LexicalMetricsView(
            tfidf_cosine=lc.tfidf_cosine,
            unigram_jaccard=lc.unigram_jaccard,
            bigram_jaccard=lc.bigram_jaccard,
            edit_similarity=lc.edit_similarity,
            sequence_similarity=lc.sequence_similarity,
            word_count_change=lc.word_count_change,
            word_count_change_pct=lc.word_count_change_pct,
        )

    status = (
        ComparisonResponseStatus.RESOLVED
        if decision.analytical_mode != AnalyticalMode.NOT_ELIGIBLE
        else ComparisonResponseStatus.REVIEW_REQUIRED
    )

    return NarrativeComparisonResponse(
        status=status,
        alignment_status=alignment.status,
        alignment_confidence=alignment.confidence,
        analytical_mode=decision.analytical_mode,
        lexical_metrics=lexical_view,
        earlier_word_count=alignment.earlier_semantic_unit.word_count if alignment.earlier_semantic_unit else None,
        later_word_count=alignment.later_semantic_unit.word_count if alignment.later_semantic_unit else None,
        earlier_provenance=earlier_prov,
        later_provenance=later_prov,
        review_reason=decision.review_reason,
        **base,
    )


# --------------------------------------------------------------------------
# Structured (STRUCTURED_TABLE)
# --------------------------------------------------------------------------


def _table_provenance(table: StructuredTable | None) -> ProvenanceRef | None:
    if table is None:
        return None
    row_block_ids = tuple(r.source_block_id for r in table.rows)
    return ProvenanceRef(
        report_id=table.report_id,
        directory_year=table.report.directory_year,
        start_page=table.start_page,
        end_page=table.end_page,
        source_block_ids=row_block_ids,
        source_excerpt=table.source_heading,
    )


def get_structured_comparison(
    session: Session,
    report_pair: ReportPair,
    table_family_key: str,
    *,
    router: ComparisonPathRouter | None = None,
) -> StructuredComparisonResponse | LegacyComparisonResponse:
    router = router or ComparisonPathRouter()
    ticker = report_pair.company.ticker
    backend = router.route_structured(ticker=ticker, table_family_key=table_family_key)

    if backend == ComparisonBackend.LEGACY_PASSAGE:
        reason = (
            "SEMANTIC_COMPARISON_CUTOVER_ENABLED is off"
            if not router.is_enabled()
            else f"{ticker} table family {table_family_key!r} is outside the Track 7C.6 cutover scope"
        )
        return LegacyComparisonResponse(
            comparison_backend=ComparisonBackend.LEGACY_PASSAGE,
            status=ComparisonResponseStatus.NOT_AVAILABLE,
            report_pair_id=report_pair.id,
            note=f"{reason} -- the legacy passage-alignment pipeline remains authoritative for this request.",
        )

    base = {
        "comparison_backend": ComparisonBackend.STRUCTURED_TABLE,
        "report_pair_id": report_pair.id,
        "earlier_report_id": report_pair.earlier_report_id,
        "later_report_id": report_pair.later_report_id,
        "table_family_key": table_family_key,
    }

    alignment_run = get_current_structured_alignment_run(session, report_pair.id, table_family_key)
    if alignment_run is None:
        return StructuredComparisonResponse(
            status=ComparisonResponseStatus.UNRESOLVED_UPSTREAM,
            review_reason=f"no current successful StructuredTableAlignmentRun for {table_family_key!r} on this report pair",
            **base,
        )

    earlier_table = session.scalar(
        select(StructuredTable).where(
            StructuredTable.structured_table_extraction_run_id == alignment_run.earlier_structured_table_extraction_run_id
        )
    )
    later_table = session.scalar(
        select(StructuredTable).where(
            StructuredTable.structured_table_extraction_run_id == alignment_run.later_structured_table_extraction_run_id
        )
    )

    row_views = tuple(
        StructuredRowAlignmentView(
            earlier_row_identity=ra.earlier_row.normalized_identity if ra.earlier_row else None,
            later_row_identity=ra.later_row.normalized_identity if ra.later_row else None,
            status=ra.status,
            confidence=ra.confidence,
            evidence=ra.evidence,
        )
        for ra in alignment_run.row_alignments
    )
    column_views = tuple(
        StructuredColumnAlignmentView(
            normalized_key=(ca.earlier_column or ca.later_column).normalized_key if (ca.earlier_column or ca.later_column) else None,
            is_restated=(ca.earlier_column or ca.later_column).is_restated if (ca.earlier_column or ca.later_column) else False,
            status=ca.status,
            comparability_status=ca.comparability_status,
        )
        for ca in alignment_run.column_alignments
    )
    event_views = tuple(
        StructuredValueChangeEventView(
            row_identity=(ev.row_alignment.earlier_row or ev.row_alignment.later_row).normalized_identity
            if (ev.row_alignment.earlier_row or ev.row_alignment.later_row)
            else None,
            column_normalized_key=(ev.column_alignment.earlier_column or ev.column_alignment.later_column).normalized_key
            if (ev.column_alignment.earlier_column or ev.column_alignment.later_column)
            else None,
            event_type=ev.event_type,
            earlier_raw_value=ev.earlier_raw_value,
            later_raw_value=ev.later_raw_value,
            earlier_numeric=ev.earlier_numeric,
            later_numeric=ev.later_numeric,
            absolute_change=ev.absolute_change,
            pct_change=ev.pct_change,
        )
        for ev in alignment_run.value_change_events
    )
    footnotes = tuple(
        fn.text
        for table in (earlier_table, later_table)
        if table is not None
        for fn in session.scalars(select(StructuredTableFootnote).where(StructuredTableFootnote.structured_table_id == table.id)).all()
    )

    return StructuredComparisonResponse(
        status=ComparisonResponseStatus.RESOLVED,
        row_alignments=row_views,
        column_alignments=column_views,
        value_change_events=event_views,
        footnotes=footnotes,
        earlier_provenance=_table_provenance(earlier_table),
        later_provenance=_table_provenance(later_table),
        review_reason=alignment_run.review_reason,
        **base,
    )
