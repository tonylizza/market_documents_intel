"""Track 7A.3/7A.4: publish-time integration of the Track 7C.6 cutover
comparison layer (docs/7a3-7a4-live-comparison-integration.md).

For every report comparison being published, builds zero or more
`NarrativeUnitComparison`/`StructuredTableComparison` rows by calling the
already-validated `services.cutover_comparison.get_narrative_comparison`/
`get_structured_comparison` for each `(ticker, schedule, unit_key)` /
`(ticker, table_family_key)` entry in the fixed 7C.6 scope
(`services.cutover_config`) that matches this comparison's company.

The router used here is always force-enabled (`ComparisonPathRouter(
cutover_enabled=True)`), independent of the live
`SEMANTIC_COMPARISON_CUTOVER_ENABLED` setting at publish time -- mirroring
exactly what `market-documents units compare-cutover --force-enabled`
already does for diagnostics. Because every call here is for a
(ticker, schedule/table_family) pair drawn directly from the scope
frozensets, the router can only ever select the new backend for it, never
LEGACY_PASSAGE -- so this module only ever persists RESOLVED /
UNRESOLVED_UPSTREAM / AMBIGUOUS / REVIEW_REQUIRED rows, never a
`LegacyComparisonResponse`. Whether the live web application actually
*prefers* a persisted row over the legacy `ReportComparison` fields is a
separate, read-time decision made against the web app's own copy of the
flag -- see the docs file above for why the flag's enforcement point had to
move to the read side given this application's actual architecture (no live
HTTP boundary between Python and the web app).

This module never alters Track 7C.1-7C.6 comparison algorithms -- it only
adds a new caller of `cutover_comparison.py`'s existing, already-validated
functions, and maps their read-only response dataclasses into `AppBase` ORM
rows using the same field-by-field, explicit-dict style as the rest of
`publisher.py`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from market_documents.models.report_pair import ReportPair
from market_documents.publishing import labels
from market_documents.publishing.models import NarrativeUnitComparison, StructuredTableComparison
from market_documents.services.comparison_routing import ComparisonPathRouter
from market_documents.services.cutover_comparison import (
    LegacyComparisonResponse,
    LexicalMetricsView,
    NarrativeComparisonResponse,
    ProvenanceRef,
    StructuredComparisonResponse,
    get_narrative_comparison,
    get_structured_comparison,
)
from market_documents.services.cutover_config import (
    NEW_PIPELINE_NARRATIVE_SCOPE,
    NEW_PIPELINE_STRUCTURED_SCOPE,
)

_FORCE_ENABLED_ROUTER = ComparisonPathRouter(cutover_enabled=True)


def _provenance_dict(provenance: ProvenanceRef | None) -> dict[str, Any] | None:
    if provenance is None:
        return None
    return {
        "report_id": str(provenance.report_id),
        "directory_year": provenance.directory_year,
        "start_page": provenance.start_page,
        "end_page": provenance.end_page,
        "source_block_ids": [str(block_id) for block_id in provenance.source_block_ids],
        "source_excerpt": provenance.source_excerpt,
    }


def _lexical_metrics_dict(metrics: LexicalMetricsView | None) -> dict[str, Any] | None:
    if metrics is None:
        return None
    return {
        "tfidf_cosine": metrics.tfidf_cosine,
        "unigram_jaccard": metrics.unigram_jaccard,
        "bigram_jaccard": metrics.bigram_jaccard,
        "edit_similarity": metrics.edit_similarity,
        "sequence_similarity": metrics.sequence_similarity,
        "word_count_change": metrics.word_count_change,
        "word_count_change_pct": metrics.word_count_change_pct,
    }


def build_narrative_comparison_rows(
    research_session: Session,
    report_pair: ReportPair,
    *,
    app_comparison_id: uuid.UUID,
    publication_id: uuid.UUID,
    publication_version: str,
) -> list[NarrativeUnitComparison]:
    """One row per in-scope narrative unit for this report pair's ticker
    (current scope: at most one, but this does not assume that)."""
    ticker = report_pair.company.ticker.upper()
    rows: list[NarrativeUnitComparison] = []
    for scope_ticker, schedule, unit_key in NEW_PIPELINE_NARRATIVE_SCOPE:
        if scope_ticker != ticker:
            continue
        response = get_narrative_comparison(
            research_session, report_pair, schedule, unit_key, router=_FORCE_ENABLED_ROUTER
        )
        if isinstance(response, LegacyComparisonResponse):
            # Cannot happen given `router` is force-enabled and (ticker,
            # schedule, unit_key) is drawn directly from the scope this
            # response was routed against -- guarded defensively rather
            # than asserted, since routing logic is intentionally not
            # duplicated here.
            continue
        rows.append(_narrative_row(response, app_comparison_id, publication_id, publication_version))
    return rows


def build_structured_comparison_rows(
    research_session: Session,
    report_pair: ReportPair,
    *,
    app_comparison_id: uuid.UUID,
    publication_id: uuid.UUID,
    publication_version: str,
) -> list[StructuredTableComparison]:
    """One row per in-scope table family for this report pair's ticker
    (ACT currently has two)."""
    ticker = report_pair.company.ticker.upper()
    rows: list[StructuredTableComparison] = []
    for scope_ticker, table_family_key in NEW_PIPELINE_STRUCTURED_SCOPE:
        if scope_ticker != ticker:
            continue
        response = get_structured_comparison(
            research_session, report_pair, table_family_key, router=_FORCE_ENABLED_ROUTER
        )
        if isinstance(response, LegacyComparisonResponse):
            continue
        rows.append(_structured_row(response, app_comparison_id, publication_id, publication_version))
    return rows


def _narrative_row(
    response: NarrativeComparisonResponse,
    app_comparison_id: uuid.UUID,
    publication_id: uuid.UUID,
    publication_version: str,
) -> NarrativeUnitComparison:
    return NarrativeUnitComparison(
        id=labels.derive_id(
            publication_version, "narrative_unit_comparisons", str(response.report_pair_id), response.unit_key
        ),
        publication_id=publication_id,
        report_comparison_id=app_comparison_id,
        schedule=response.schedule.value,
        unit_key=response.unit_key,
        comparison_backend=response.comparison_backend.value,
        status=response.status.value,
        alignment_status=response.alignment_status.value if response.alignment_status else None,
        alignment_confidence=response.alignment_confidence.value if response.alignment_confidence else None,
        analytical_mode=response.analytical_mode.value if response.analytical_mode else None,
        lexical_metrics=_lexical_metrics_dict(response.lexical_metrics),
        earlier_word_count=response.earlier_word_count,
        later_word_count=response.later_word_count,
        earlier_provenance=_provenance_dict(response.earlier_provenance),
        later_provenance=_provenance_dict(response.later_provenance),
        review_reason=response.review_reason,
    )


def _structured_row(
    response: StructuredComparisonResponse,
    app_comparison_id: uuid.UUID,
    publication_id: uuid.UUID,
    publication_version: str,
) -> StructuredTableComparison:
    row_alignments = [
        {
            "earlier_row_identity": ra.earlier_row_identity,
            "later_row_identity": ra.later_row_identity,
            "status": ra.status.value,
            "confidence": ra.confidence.value,
            "evidence": ra.evidence,
        }
        for ra in response.row_alignments
    ]
    column_alignments = [
        {
            "normalized_key": ca.normalized_key,
            "is_restated": ca.is_restated,
            "status": ca.status.value,
            "comparability_status": ca.comparability_status.value,
        }
        for ca in response.column_alignments
    ]
    value_change_events = [
        {
            "row_identity": ev.row_identity,
            "column_normalized_key": ev.column_normalized_key,
            "event_type": ev.event_type.value,
            "earlier_raw_value": ev.earlier_raw_value,
            "later_raw_value": ev.later_raw_value,
            "earlier_numeric": ev.earlier_numeric,
            "later_numeric": ev.later_numeric,
            "absolute_change": ev.absolute_change,
            "pct_change": ev.pct_change,
        }
        for ev in response.value_change_events
    ]
    return StructuredTableComparison(
        id=labels.derive_id(
            publication_version,
            "structured_table_comparisons",
            str(response.report_pair_id),
            response.table_family_key,
        ),
        publication_id=publication_id,
        report_comparison_id=app_comparison_id,
        table_family_key=response.table_family_key,
        comparison_backend=response.comparison_backend.value,
        status=response.status.value,
        row_alignments=row_alignments,
        column_alignments=column_alignments,
        value_change_events=value_change_events,
        footnotes=list(response.footnotes),
        earlier_provenance=_provenance_dict(response.earlier_provenance),
        later_provenance=_provenance_dict(response.later_provenance),
        review_reason=response.review_reason,
    )
