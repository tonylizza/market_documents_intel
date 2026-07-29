"""The only module in `publishing/` allowed to query the research `Base`
models.

Resolves the entire pinned lineage per comparison the same way
`financial_language_signals.select_language_signal_source` already does:
current segmentation run per report, current feature run per pair, and the
feature run's own pinned `alignment_run_id` -- never independently
re-resolving "current" for a downstream stage. Returns ORM instances bundled
into typed dataclasses rather than a second, hand-duplicated set of fields;
the research session stays open for the lifetime of one `publish build`
call (see `publisher.py`), so attribute access on these instances after
`resolve_research_snapshot` returns is safe.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from market_documents.models import (
    AlignmentRun,
    Company,
    ExtractionRun,
    FeatureRun,
    LanguageSignalRun,
    NarrativeDocument,
    Passage,
    PassageAlignment,
    PassageLanguageCategoryHit,
    PassageLanguageSignal,
    PassageSourceBlock,
    Report,
    ReportPair,
    ReportPairFeatures,
    ReportPairLanguageFeatures,
    TextBlock,
)
from market_documents.models.enums import MetadataStatus
from market_documents.publishing.labels import PUBLICATION_EXCLUDED_CATEGORIES
from market_documents.services.extraction import get_narrative_document
from market_documents.services.feature_extraction import (
    get_current_feature_run,
    get_current_report_pair_features,
)
from market_documents.services.financial_language_signals import (
    get_current_language_signal_run,
    get_current_pair_language_features,
)
from market_documents.services.passage_segmentation import get_current_segmentation_run
from market_documents.services.structured_content_audit import (
    Classification,
    PassageAuditInput,
    classify_passage,
)


@dataclass(frozen=True)
class PassageDataset:
    passage: Passage
    classification: Classification | None
    excluded_as_artifact: bool


@dataclass(frozen=True)
class ComparisonDataset:
    pair: ReportPair
    feature_run: FeatureRun
    features: ReportPairFeatures
    alignment_run: AlignmentRun
    passage_alignments: list[PassageAlignment]
    language_run: LanguageSignalRun | None
    language_features: ReportPairLanguageFeatures | None
    # True when a current LanguageSignalRun exists but pins a different
    # alignment_run than the one this comparison's FeatureRun pins --
    # language output is then excluded from publication for this
    # comparison entirely rather than silently mixing two lineages.
    language_lineage_mismatch: bool
    passage_language_signals: list[PassageLanguageSignal]
    category_hits_by_signal_id: dict[uuid.UUID, list[PassageLanguageCategoryHit]]


@dataclass(frozen=True)
class CompanyDataset:
    company: Company
    reports: list[Report]


@dataclass(frozen=True)
class ReportExtractionInfo:
    narrative_document: NarrativeDocument | None
    extraction_run: ExtractionRun | None


@dataclass(frozen=True)
class ResearchSnapshot:
    research_schema_version: str
    companies: list[CompanyDataset]
    comparisons: list[ComparisonDataset]
    passages_by_report: dict[uuid.UUID, list[PassageDataset]] = field(default_factory=dict)
    extraction_by_report: dict[uuid.UUID, ReportExtractionInfo] = field(default_factory=dict)


def _research_schema_version(session: Session) -> str:
    row = session.execute(text("SELECT version_num FROM alembic_version")).first()
    return row[0] if row is not None else "unknown"


def _block_types_by_passage(session: Session, passage_ids: list[uuid.UUID]) -> dict[uuid.UUID, list]:
    if not passage_ids:
        return {}
    rows = session.execute(
        select(PassageSourceBlock.passage_id, TextBlock.block_type)
        .join(TextBlock, PassageSourceBlock.text_block_id == TextBlock.id)
        .where(PassageSourceBlock.passage_id.in_(passage_ids))
    ).all()
    out: dict[uuid.UUID, list] = defaultdict(list)
    for passage_id, block_type in rows:
        out[passage_id].append(block_type)
    return out


def _resolve_report_extraction(session: Session, report: Report) -> ReportExtractionInfo:
    narrative_document = get_narrative_document(session, report.id)
    extraction_run = (
        session.get(ExtractionRun, narrative_document.extraction_run_id)
        if narrative_document is not None
        else None
    )
    return ReportExtractionInfo(narrative_document=narrative_document, extraction_run=extraction_run)


def _resolve_passages_for_report(
    session: Session, report: Report, narrative_document: NarrativeDocument | None
) -> list[PassageDataset]:
    if narrative_document is None:
        return []
    segmentation_run = get_current_segmentation_run(session, narrative_document.id)
    if segmentation_run is None:
        return []
    passages = list(
        session.scalars(
            select(Passage)
            .where(Passage.segmentation_run_id == segmentation_run.id)
            .order_by(Passage.passage_index)
        )
    )
    block_types_by_passage = _block_types_by_passage(session, [p.id for p in passages])

    datasets = []
    for passage in passages:
        ctx = PassageAuditInput(
            passage_id=passage.id,
            raw_text=passage.raw_text,
            heading_text=passage.heading_text,
            word_count=passage.word_count,
            passage_type=passage.passage_type,
            block_types=tuple(block_types_by_passage.get(passage.id, [])),
        )
        classification = classify_passage(ctx)
        category = classification.category if classification is not None else None

        datasets.append(
            PassageDataset(
                passage=passage,
                classification=classification,
                excluded_as_artifact=category in PUBLICATION_EXCLUDED_CATEGORIES,
            )
        )
    return datasets


def _resolve_comparison(session: Session, pair: ReportPair) -> ComparisonDataset | None:
    feature_run = get_current_feature_run(session, pair.id)
    if feature_run is None:
        return None
    features = get_current_report_pair_features(session, pair.id)
    if features is None:
        return None

    alignment_run = session.get(AlignmentRun, feature_run.alignment_run_id)
    if alignment_run is None:
        return None

    passage_alignments = list(
        session.scalars(
            select(PassageAlignment)
            .where(
                PassageAlignment.alignment_run_id == alignment_run.id,
                PassageAlignment.primary_alignment.is_(True),
            )
            .order_by(
                PassageAlignment.earlier_passage_id.nulls_last(),
                PassageAlignment.later_passage_id.nulls_last(),
            )
        )
    )

    language_run = get_current_language_signal_run(session, pair.id)
    language_features = None
    language_lineage_mismatch = False
    passage_language_signals: list[PassageLanguageSignal] = []
    category_hits_by_signal_id: dict[uuid.UUID, list[PassageLanguageCategoryHit]] = {}

    if language_run is not None:
        if language_run.alignment_run_id != alignment_run.id:
            # The pair has moved on to a newer current FeatureRun/alignment
            # since language signals were last built -- never mix a stale
            # language lineage with a newer feature lineage.
            language_lineage_mismatch = True
        else:
            language_features = get_current_pair_language_features(session, pair.id)
            if language_features is not None:
                passage_language_signals = list(
                    session.scalars(
                        select(PassageLanguageSignal).where(
                            PassageLanguageSignal.language_signal_run_id == language_run.id
                        )
                    )
                )
                signal_ids = [s.id for s in passage_language_signals]
                if signal_ids:
                    hit_rows = list(
                        session.scalars(
                            select(PassageLanguageCategoryHit).where(
                                PassageLanguageCategoryHit.passage_language_signal_id.in_(signal_ids)
                            )
                        )
                    )
                    for hit in hit_rows:
                        category_hits_by_signal_id.setdefault(hit.passage_language_signal_id, []).append(hit)

    return ComparisonDataset(
        pair=pair,
        feature_run=feature_run,
        features=features,
        alignment_run=alignment_run,
        passage_alignments=passage_alignments,
        language_run=language_run,
        language_features=language_features,
        language_lineage_mismatch=language_lineage_mismatch,
        passage_language_signals=passage_language_signals,
        category_hits_by_signal_id=category_hits_by_signal_id,
    )


def resolve_research_snapshot(session: Session) -> ResearchSnapshot:
    """Resolve every accepted-current entity the publisher needs, in one
    pass, using this session for the remainder of the build."""
    research_schema_version = _research_schema_version(session)

    companies_with_reports: list[CompanyDataset] = []
    all_companies = list(session.scalars(select(Company).order_by(Company.ticker)))
    for company in all_companies:
        reports = list(
            session.scalars(
                select(Report)
                .where(
                    Report.company_id == company.id,
                    Report.metadata_status == MetadataStatus.VALIDATED,
                )
                .order_by(Report.period_end, Report.directory_year)
            )
        )
        if reports:
            companies_with_reports.append(CompanyDataset(company=company, reports=reports))

    published_report_ids = {
        report.id for cd in companies_with_reports for report in cd.reports
    }

    comparisons: list[ComparisonDataset] = []
    pairs = list(
        session.scalars(
            select(ReportPair).where(
                ReportPair.earlier_report_id.in_(published_report_ids),
                ReportPair.later_report_id.in_(published_report_ids),
            )
        )
    )
    for pair in pairs:
        dataset = _resolve_comparison(session, pair)
        if dataset is not None:
            comparisons.append(dataset)

    passages_by_report: dict[uuid.UUID, list[PassageDataset]] = {}
    extraction_by_report: dict[uuid.UUID, ReportExtractionInfo] = {}
    for cd in companies_with_reports:
        for report in cd.reports:
            extraction_info = _resolve_report_extraction(session, report)
            extraction_by_report[report.id] = extraction_info
            passages_by_report[report.id] = _resolve_passages_for_report(
                session, report, extraction_info.narrative_document
            )

    return ResearchSnapshot(
        research_schema_version=research_schema_version,
        companies=companies_with_reports,
        comparisons=comparisons,
        passages_by_report=passages_by_report,
        extraction_by_report=extraction_by_report,
    )
