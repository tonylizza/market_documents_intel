"""Read-only publication audit reporting, following the existing
`*_audit.py` convention (`services/alignment_audit.py`, etc.): dataclass
rows built with `build_*_rows(app_session, ...)`, written with a shared
`write_audit_csv(rows, output_path)`.
"""

import csv
import uuid
from dataclasses import dataclass, fields
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_documents.publishing.models import (
    APP_EMBEDDING_DIMENSION,
    Company,
    DiscoveryItem,
    LanguageMetric,
    MetricDefinition,
    MetricLabelThreshold,
    Passage,
    PassageComparison,
    PassageLanguageSignal,
    Publication,
    Report,
    ReportComparison,
    RetrievalContext,
)
from market_documents.publishing.models import PassageEmbedding as AppPassageEmbedding
from market_documents.publishing.models import QaChunk, QaChunkPassage
from market_documents.publishing.retrieval_contexts import vector_norm_nonzero


def write_audit_csv(rows: list, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output_path.write_text("")
        return
    fieldnames = [f.name for f in fields(rows[0])]
    with output_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


@dataclass
class PublicationRunAuditRow:
    publication_id: str
    publication_version: str
    status: str
    source_schema_version: str
    source_configuration_hash: str
    started_at: str | None
    completed_at: str | None
    activated_at: str | None
    company_count: int | None
    report_count: int | None
    comparison_count: int | None
    passage_count: int | None
    passage_comparison_count: int | None
    language_metric_count: int | None
    passage_language_signal_count: int | None
    discovery_item_count: int | None
    qa_chunk_count: int | None
    qa_chunk_passage_mapping_count: int | None
    failure_reason: str | None


def build_publication_run_audit_rows(app_session: Session) -> list[PublicationRunAuditRow]:
    publications = list(app_session.scalars(select(Publication).order_by(Publication.created_at)))
    return [
        PublicationRunAuditRow(
            publication_id=str(p.id),
            publication_version=p.publication_version,
            status=p.status,
            source_schema_version=p.source_schema_version,
            source_configuration_hash=p.source_configuration_hash,
            started_at=p.started_at.isoformat() if p.started_at else None,
            completed_at=p.completed_at.isoformat() if p.completed_at else None,
            activated_at=p.activated_at.isoformat() if p.activated_at else None,
            company_count=p.company_count,
            report_count=p.report_count,
            comparison_count=p.comparison_count,
            passage_count=p.passage_count,
            passage_comparison_count=p.passage_comparison_count,
            language_metric_count=p.language_metric_count,
            passage_language_signal_count=p.passage_language_signal_count,
            discovery_item_count=p.discovery_item_count,
            qa_chunk_count=p.qa_chunk_count,
            qa_chunk_passage_mapping_count=p.qa_chunk_passage_mapping_count,
            failure_reason=p.failure_reason,
        )
        for p in publications
    ]


@dataclass
class PublicationCompanyAuditRow:
    publication_id: str
    ticker: str
    source_company_id: str
    target_company_id: str
    report_count: int
    comparison_count: int
    first_report_period_end: str | None
    latest_report_period_end: str | None
    latest_comparison_id: str | None
    historical_peak_comparison_id: str | None
    has_current_data: bool


def build_publication_company_audit_rows(app_session: Session, publication_id: uuid.UUID) -> list[PublicationCompanyAuditRow]:
    companies = list(
        app_session.scalars(
            select(Company).where(Company.publication_id == publication_id).order_by(Company.display_order)
        )
    )
    return [
        PublicationCompanyAuditRow(
            publication_id=str(publication_id),
            ticker=c.ticker,
            source_company_id=str(c.source_company_id),
            target_company_id=str(c.id),
            report_count=c.report_count,
            comparison_count=c.comparison_count,
            first_report_period_end=c.first_report_period_end.isoformat() if c.first_report_period_end else None,
            latest_report_period_end=c.latest_report_period_end.isoformat() if c.latest_report_period_end else None,
            latest_comparison_id=str(c.latest_comparison_id) if c.latest_comparison_id else None,
            historical_peak_comparison_id=(
                str(c.historical_peak_comparison_id) if c.historical_peak_comparison_id else None
            ),
            has_current_data=c.has_current_data,
        )
        for c in companies
    ]


@dataclass
class PublicationComparisonAuditRow:
    publication_id: str
    ticker: str
    source_report_pair_id: str
    target_comparison_id: str
    earlier_period_end: str | None
    later_period_end: str | None
    gap_months: int
    is_transition: bool
    is_irregular_gap: bool
    is_latest_for_company: bool
    is_historical_peak_change: bool
    disclosure_change_score: float | None
    disclosure_change_label: str | None
    disclosure_change_quality: str | None
    disclosure_change_quality_label: str | None
    # Milestone 7A.1 follow-up ("review-qualified disclosure-change
    # publication") audit fields: "score available" reflects the raw
    # upstream value before FAILED-quality suppression (recovered from
    # `finding_payload`'s diagnostics, since the persisted
    # `disclosure_change_score` column itself is the post-suppression,
    # *displayed* value); "score displayed"/"score primary eligible" are
    # read directly off the persisted comparison row.
    disclosure_change_score_available: bool
    disclosure_change_score_displayed: bool
    disclosure_change_primary_eligible: bool | None
    discovery_exclusion_reason: str | None
    report_side_quality: str | None
    alignment_change_quality: str | None
    primary_finding_key: str | None
    secondary_finding_key: str | None
    tertiary_finding_key: str | None


def build_publication_comparison_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationComparisonAuditRow]:
    rows = list(
        app_session.execute(
            select(ReportComparison, Company.ticker)
            .join(Company, ReportComparison.company_id == Company.id)
            .where(ReportComparison.publication_id == publication_id)
            .order_by(Company.ticker, ReportComparison.chronological_index)
        ).all()
    )
    result = []
    for comp, ticker in rows:
        diagnostics = (comp.finding_payload or {}).get("_disclosure_change_diagnostics") or {}
        score_available = diagnostics.get("score_available")
        score_displayed = comp.disclosure_change_score is not None
        if comp.disclosure_change_primary_eligible:
            discovery_exclusion_reason = None
        else:
            reason = f"disclosure_change_quality={comp.disclosure_change_quality}"
            if comp.disclosure_change_warning:
                reason = f"{reason}; {comp.disclosure_change_warning}"
            discovery_exclusion_reason = reason
        result.append(
            PublicationComparisonAuditRow(
                publication_id=str(publication_id),
                ticker=ticker,
                source_report_pair_id=str(comp.source_report_pair_id),
                target_comparison_id=str(comp.id),
                earlier_period_end=comp.earlier_period_end.isoformat() if comp.earlier_period_end else None,
                later_period_end=comp.later_period_end.isoformat() if comp.later_period_end else None,
                gap_months=comp.gap_months,
                is_transition=comp.is_transition,
                is_irregular_gap=comp.is_irregular_gap,
                is_latest_for_company=comp.is_latest_for_company,
                is_historical_peak_change=comp.is_historical_peak_change,
                disclosure_change_score=comp.disclosure_change_score,
                disclosure_change_label=comp.disclosure_change_label,
                disclosure_change_quality=comp.disclosure_change_quality,
                disclosure_change_quality_label=comp.disclosure_change_quality_label,
                disclosure_change_score_available=bool(score_available),
                disclosure_change_score_displayed=score_displayed,
                disclosure_change_primary_eligible=comp.disclosure_change_primary_eligible,
                discovery_exclusion_reason=discovery_exclusion_reason,
                report_side_quality=comp.report_side_quality,
                alignment_change_quality=comp.alignment_change_quality,
                primary_finding_key=comp.primary_finding_key,
                secondary_finding_key=comp.secondary_finding_key,
                tertiary_finding_key=comp.tertiary_finding_key,
            )
        )
    return result


@dataclass
class PublicationLineageAuditRow:
    entity_type: str
    source_id: str
    target_id: str
    publication_id: str


def build_publication_lineage_audit_rows(app_session: Session, publication_id: uuid.UUID) -> list[PublicationLineageAuditRow]:
    rows: list[PublicationLineageAuditRow] = []
    for c in app_session.scalars(select(Company).where(Company.publication_id == publication_id)):
        rows.append(PublicationLineageAuditRow("company", str(c.source_company_id), str(c.id), str(publication_id)))
    for r in app_session.scalars(select(Report).where(Report.publication_id == publication_id)):
        rows.append(PublicationLineageAuditRow("report", str(r.source_report_id), str(r.id), str(publication_id)))
    for comp in app_session.scalars(select(ReportComparison).where(ReportComparison.publication_id == publication_id)):
        rows.append(
            PublicationLineageAuditRow("report_comparison", str(comp.source_report_pair_id), str(comp.id), str(publication_id))
        )
    for pc in app_session.scalars(select(PassageComparison).where(PassageComparison.publication_id == publication_id)):
        rows.append(
            PublicationLineageAuditRow("passage_comparison", str(pc.source_alignment_id), str(pc.id), str(publication_id))
        )
    for p in app_session.scalars(select(Passage).where(Passage.publication_id == publication_id)):
        rows.append(PublicationLineageAuditRow("passage", str(p.source_passage_id), str(p.id), str(publication_id)))
    return rows


@dataclass
class PublicationValidationFailureRow:
    publication_id: str
    check: str
    detail: str


def build_publication_validation_failure_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationValidationFailureRow]:
    publication = app_session.get(Publication, publication_id)
    if publication is None or not publication.validation_summary:
        return []
    return [
        PublicationValidationFailureRow(publication_id=str(publication_id), check=f["check"], detail=f["detail"])
        for f in publication.validation_summary.get("failures", [])
    ]


@dataclass
class PublicationDiscoveryRankingAuditRow:
    publication_id: str
    discovery_type: str
    rank_scope: str
    rank: int
    percentile: float | None
    score: float
    supporting_metric_key: str
    supporting_value: float
    ticker: str
    target_comparison_id: str


def build_publication_discovery_ranking_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationDiscoveryRankingAuditRow]:
    rows = list(
        app_session.execute(
            select(DiscoveryItem, Company.ticker)
            .join(Company, DiscoveryItem.company_id == Company.id)
            .where(DiscoveryItem.publication_id == publication_id)
            .order_by(DiscoveryItem.discovery_type, DiscoveryItem.rank_scope, DiscoveryItem.rank)
        ).all()
    )
    return [
        PublicationDiscoveryRankingAuditRow(
            publication_id=str(publication_id),
            discovery_type=item.discovery_type,
            rank_scope=item.rank_scope,
            rank=item.rank,
            percentile=item.percentile,
            score=item.score,
            supporting_metric_key=item.supporting_metric_key,
            supporting_value=item.supporting_value,
            ticker=ticker,
            target_comparison_id=str(item.report_comparison_id),
        )
        for item, ticker in rows
    ]


@dataclass
class PublicationTableCountRow:
    publication_id: str
    table_name: str
    row_count: int


def build_publication_table_count_rows(app_session: Session, publication_id: uuid.UUID) -> list[PublicationTableCountRow]:
    tables = {
        "companies": Company,
        "reports": Report,
        "report_comparisons": ReportComparison,
        "language_metrics": LanguageMetric,
        "passages": Passage,
        "passage_comparisons": PassageComparison,
        "passage_language_signals": PassageLanguageSignal,
        "discovery_items": DiscoveryItem,
        "metric_definitions": MetricDefinition,
        "metric_label_thresholds": MetricLabelThreshold,
        "qa_chunks": QaChunk,
        "qa_chunk_passages": QaChunkPassage,
    }
    rows = []
    for name, model in tables.items():
        count = app_session.scalar(select(func.count()).select_from(model).where(model.publication_id == publication_id))
        rows.append(PublicationTableCountRow(publication_id=str(publication_id), table_name=name, row_count=count or 0))
    return rows


@dataclass
class DeterministicPublicationReviewSampleRow:
    publication_id: str
    ticker: str
    source_report_pair_id: str
    target_comparison_id: str
    disclosure_change_score: float | None
    sample_reason: str


def build_deterministic_publication_review_sample_rows(
    app_session: Session, publication_id: uuid.UUID, sample_size: int = 5
) -> list[DeterministicPublicationReviewSampleRow]:
    """A small, deterministic sample for manual spot review: the largest and
    smallest `disclosure_change_score` comparisons, tie-broken by
    `source_report_pair_id` so the sample is identical across re-runs."""
    rows = list(
        app_session.execute(
            select(ReportComparison, Company.ticker)
            .join(Company, ReportComparison.company_id == Company.id)
            .where(ReportComparison.publication_id == publication_id, ReportComparison.disclosure_change_score.isnot(None))
        ).all()
    )
    ranked = sorted(rows, key=lambda pair: (pair[0].disclosure_change_score, str(pair[0].source_report_pair_id)))
    lowest = ranked[:sample_size]
    highest = list(reversed(ranked[-sample_size:])) if len(ranked) > sample_size else []

    out = []
    for comp, ticker in highest:
        out.append(
            DeterministicPublicationReviewSampleRow(
                publication_id=str(publication_id),
                ticker=ticker,
                source_report_pair_id=str(comp.source_report_pair_id),
                target_comparison_id=str(comp.id),
                disclosure_change_score=comp.disclosure_change_score,
                sample_reason="highest_disclosure_change_score",
            )
        )
    for comp, ticker in lowest:
        out.append(
            DeterministicPublicationReviewSampleRow(
                publication_id=str(publication_id),
                ticker=ticker,
                source_report_pair_id=str(comp.source_report_pair_id),
                target_comparison_id=str(comp.id),
                disclosure_change_score=comp.disclosure_change_score,
                sample_reason="lowest_disclosure_change_score",
            )
        )
    return out


# ---------------------------------------------------------------------------
# Milestone 7B.1: passage embeddings and retrieval contexts
# ---------------------------------------------------------------------------


@dataclass
class PublicationEmbeddingAuditRow:
    publication_id: str
    target_passage_id: str
    target_embedding_id: str
    embedding_model: str
    embedding_model_revision: str
    dimensions: int
    vector_norm: float
    vector_is_nonzero: bool


def build_publication_embedding_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationEmbeddingAuditRow]:
    embeddings = list(
        app_session.scalars(
            select(AppPassageEmbedding)
            .where(AppPassageEmbedding.publication_id == publication_id)
            .order_by(AppPassageEmbedding.passage_id)
        )
    )
    return [
        PublicationEmbeddingAuditRow(
            publication_id=str(publication_id),
            target_passage_id=str(e.passage_id),
            target_embedding_id=str(e.id),
            embedding_model=e.embedding_model,
            embedding_model_revision=e.embedding_model_revision,
            dimensions=e.dimensions,
            vector_norm=e.vector_norm,
            vector_is_nonzero=vector_norm_nonzero(e.embedding),
        )
        for e in embeddings
    ]


@dataclass
class PublicationEmbeddingLineageAuditRow:
    publication_id: str
    target_passage_id: str
    target_embedding_id: str
    source_embedding_id: str
    source_embedding_run_id: str


def build_publication_embedding_lineage_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationEmbeddingLineageAuditRow]:
    embeddings = list(
        app_session.scalars(
            select(AppPassageEmbedding)
            .where(AppPassageEmbedding.publication_id == publication_id)
            .order_by(AppPassageEmbedding.passage_id)
        )
    )
    return [
        PublicationEmbeddingLineageAuditRow(
            publication_id=str(publication_id),
            target_passage_id=str(e.passage_id),
            target_embedding_id=str(e.id),
            source_embedding_id=str(e.source_embedding_id),
            source_embedding_run_id=str(e.source_embedding_run_id),
        )
        for e in embeddings
    ]


@dataclass
class PublicationEmbeddingMissingAuditRow:
    publication_id: str
    target_passage_id: str
    ticker: str
    source_passage_id: str
    heading: str | None


def build_publication_embedding_missing_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationEmbeddingMissingAuditRow]:
    """Every currently-published passage with no corresponding
    `app.passage_embeddings` row -- non-empty means the default eligibility
    policy (every current passage must have a current accepted source
    embedding) was not met, which also fails `validate_persisted`."""
    passages = list(
        app_session.execute(
            select(Passage, Company.ticker)
            .join(Company, Passage.company_id == Company.id)
            .where(Passage.publication_id == publication_id)
            .order_by(Company.ticker, Passage.passage_index)
        ).all()
    )
    embedded_passage_ids = set(
        app_session.scalars(
            select(AppPassageEmbedding.passage_id).where(AppPassageEmbedding.publication_id == publication_id)
        )
    )
    return [
        PublicationEmbeddingMissingAuditRow(
            publication_id=str(publication_id),
            target_passage_id=str(p.id),
            ticker=ticker,
            source_passage_id=str(p.source_passage_id),
            heading=p.heading,
        )
        for p, ticker in passages
        if p.id not in embedded_passage_ids
    ]


@dataclass
class PublicationVectorIntegrityAuditRow:
    publication_id: str
    target_embedding_id: str
    target_passage_id: str
    dimensions_ok: bool
    vector_nonzero: bool


def build_publication_vector_integrity_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationVectorIntegrityAuditRow]:
    embeddings = list(
        app_session.scalars(
            select(AppPassageEmbedding)
            .where(AppPassageEmbedding.publication_id == publication_id)
            .order_by(AppPassageEmbedding.passage_id)
        )
    )
    return [
        PublicationVectorIntegrityAuditRow(
            publication_id=str(publication_id),
            target_embedding_id=str(e.id),
            target_passage_id=str(e.passage_id),
            dimensions_ok=e.dimensions == APP_EMBEDDING_DIMENSION == len(e.embedding),
            vector_nonzero=vector_norm_nonzero(e.embedding),
        )
        for e in embeddings
    ]


@dataclass
class PublicationRetrievalContextAuditRow:
    publication_id: str
    target_context_id: str
    target_passage_id: str
    context_type: str
    report_side: str | None
    alignment_status: str | None
    target_passage_comparison_id: str | None
    target_report_comparison_id: str | None
    ticker: str


def build_publication_retrieval_context_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationRetrievalContextAuditRow]:
    rows = list(
        app_session.execute(
            select(RetrievalContext, Company.ticker)
            .join(Company, RetrievalContext.company_id == Company.id)
            .where(RetrievalContext.publication_id == publication_id)
            .order_by(Company.ticker, RetrievalContext.passage_id, RetrievalContext.report_side)
        ).all()
    )
    return [
        PublicationRetrievalContextAuditRow(
            publication_id=str(publication_id),
            target_context_id=str(ctx.id),
            target_passage_id=str(ctx.passage_id),
            context_type=ctx.context_type,
            report_side=ctx.report_side,
            alignment_status=ctx.alignment_status,
            target_passage_comparison_id=str(ctx.passage_comparison_id) if ctx.passage_comparison_id else None,
            target_report_comparison_id=str(ctx.report_comparison_id) if ctx.report_comparison_id else None,
            ticker=ticker,
        )
        for ctx, ticker in rows
    ]


@dataclass
class PublicationRetrievalContextDuplicateAuditRow:
    publication_id: str
    passage_id: str
    passage_comparison_id: str | None
    report_side: str | None
    context_type: str
    duplicate_count: int


def build_publication_retrieval_context_duplicate_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationRetrievalContextDuplicateAuditRow]:
    """Expected to be empty -- the DB unique constraint already prevents
    this, so a non-empty result here would indicate the constraint itself
    was bypassed (e.g. a raw SQL path outside the ORM)."""
    contexts = list(
        app_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == publication_id))
    )
    counts: dict[tuple, int] = {}
    for ctx in contexts:
        key = (ctx.passage_id, ctx.passage_comparison_id, ctx.report_side, ctx.context_type)
        counts[key] = counts.get(key, 0) + 1
    return [
        PublicationRetrievalContextDuplicateAuditRow(
            publication_id=str(publication_id),
            passage_id=str(key[0]),
            passage_comparison_id=str(key[1]) if key[1] else None,
            report_side=key[2],
            context_type=key[3],
            duplicate_count=count,
        )
        for key, count in counts.items()
        if count > 1
    ]


# ---------------------------------------------------------------------------
# Milestone 7B.2: Q&A retrieval chunks
# ---------------------------------------------------------------------------


@dataclass
class PublicationQaChunkEmbeddingAuditRow:
    publication_id: str
    target_chunk_id: str
    target_report_id: str
    chunk_index: int
    embedding_model: str
    embedding_model_revision: str
    dimensions: int
    vector_norm: float
    vector_is_nonzero: bool
    truncation_policy: str
    token_count: int


def build_publication_qa_chunk_embedding_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationQaChunkEmbeddingAuditRow]:
    chunks = list(
        app_session.scalars(
            select(QaChunk)
            .where(QaChunk.publication_id == publication_id)
            .order_by(QaChunk.report_id, QaChunk.chunk_index)
        )
    )
    return [
        PublicationQaChunkEmbeddingAuditRow(
            publication_id=str(publication_id),
            target_chunk_id=str(c.id),
            target_report_id=str(c.report_id),
            chunk_index=c.chunk_index,
            embedding_model=c.embedding_model,
            embedding_model_revision=c.embedding_model_revision,
            dimensions=c.dimensions,
            vector_norm=c.vector_norm,
            vector_is_nonzero=vector_norm_nonzero(c.embedding),
            truncation_policy=c.truncation_policy,
            token_count=c.token_count,
        )
        for c in chunks
    ]


@dataclass
class PublicationQaChunkLineageAuditRow:
    publication_id: str
    target_chunk_id: str
    target_report_id: str
    ticker: str
    chunk_index: int
    page_start: int
    page_end: int
    section_heading: str | None
    member_passage_count: int


def build_publication_qa_chunk_lineage_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationQaChunkLineageAuditRow]:
    rows = list(
        app_session.execute(
            select(QaChunk, Company.ticker)
            .join(Company, QaChunk.company_id == Company.id)
            .where(QaChunk.publication_id == publication_id)
            .order_by(Company.ticker, QaChunk.report_id, QaChunk.chunk_index)
        ).all()
    )
    mapping_counts: dict[uuid.UUID, int] = {}
    for chunk_id, count in app_session.execute(
        select(QaChunkPassage.qa_chunk_id, func.count())
        .where(QaChunkPassage.publication_id == publication_id)
        .group_by(QaChunkPassage.qa_chunk_id)
    ).all():
        mapping_counts[chunk_id] = count
    return [
        PublicationQaChunkLineageAuditRow(
            publication_id=str(publication_id),
            target_chunk_id=str(c.id),
            target_report_id=str(c.report_id),
            ticker=ticker,
            chunk_index=c.chunk_index,
            page_start=c.page_start,
            page_end=c.page_end,
            section_heading=c.section_heading,
            member_passage_count=mapping_counts.get(c.id, 0),
        )
        for c, ticker in rows
    ]


@dataclass
class PublicationQaChunkDuplicateAuditRow:
    publication_id: str
    target_report_id: str
    embedding_text_hash: str
    duplicate_count: int


def build_publication_qa_chunk_duplicate_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationQaChunkDuplicateAuditRow]:
    """Expected to be empty -- `publisher.py` already deduplicates
    byte-identical chunk text within a report before persisting, so a
    non-empty result here would indicate that dedup step was bypassed."""
    chunks = list(app_session.scalars(select(QaChunk).where(QaChunk.publication_id == publication_id)))
    counts: dict[tuple, int] = {}
    for c in chunks:
        key = (c.report_id, c.embedding_text_hash)
        counts[key] = counts.get(key, 0) + 1
    return [
        PublicationQaChunkDuplicateAuditRow(
            publication_id=str(publication_id),
            target_report_id=str(key[0]),
            embedding_text_hash=key[1],
            duplicate_count=count,
        )
        for key, count in counts.items()
        if count > 1
    ]


@dataclass
class PublicationQaChunkVectorIntegrityAuditRow:
    publication_id: str
    target_chunk_id: str
    target_report_id: str
    dimensions_ok: bool
    vector_nonzero: bool


def build_publication_qa_chunk_vector_integrity_audit_rows(
    app_session: Session, publication_id: uuid.UUID
) -> list[PublicationQaChunkVectorIntegrityAuditRow]:
    chunks = list(
        app_session.scalars(
            select(QaChunk).where(QaChunk.publication_id == publication_id).order_by(QaChunk.report_id, QaChunk.chunk_index)
        )
    )
    return [
        PublicationQaChunkVectorIntegrityAuditRow(
            publication_id=str(publication_id),
            target_chunk_id=str(c.id),
            target_report_id=str(c.report_id),
            dimensions_ok=c.dimensions == APP_EMBEDDING_DIMENSION == len(c.embedding),
            vector_nonzero=vector_norm_nonzero(c.embedding),
        )
        for c in chunks
    ]
