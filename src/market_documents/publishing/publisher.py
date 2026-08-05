"""Thin orchestration: build -> validate -> promote lifecycle for one
publication. The only module in `publishing/` that opens/commits the
destination (app) database session. Field-by-field mapping from research
ORM objects (via `source_dataset.py`) into `AppBase` rows also lives here,
since it is orchestration detail rather than reusable pure logic.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from market_documents.config import Settings, get_settings
from market_documents.models.enums import AlignmentStatus, AlignmentType, ReportSide
from market_documents.publishing import labels
from market_documents.publishing.discovery import DiscoveryCandidate, rank_discovery_items
from market_documents.publishing.findings import ComparisonMetrics, eligible_candidates, select_findings
from market_documents.publishing.models import (
    APP_EMBEDDING_DIMENSION,
    ApplicationState,
    Company,
    DiscoveryItem,
    LanguageMetric,
    MetricDefinition,
    MetricLabelThreshold,
    Passage,
    PassageComparison,
    PassageLanguageSignal,
)
from market_documents.publishing.models import PassageEmbedding as AppPassageEmbedding
from market_documents.publishing.models import QaChunk as AppQaChunk
from market_documents.publishing.models import QaChunkPassage as AppQaChunkPassage
from market_documents.publishing.models import (
    Publication,
    PublicationStatus,
    Report,
    ReportComparison,
    RetrievalContext,
    RetrievalContextLanguageCategory,
    RetrievalContextRiskSubcategory,
)
from market_documents.publishing.qa_chunking import QaPassageRow, build_qa_chunks
from market_documents.publishing.retrieval_contexts import (
    LanguageSignalTag,
    distinct_categories,
    distinct_risk_subcategories,
    embedding_text_hash,
    vector_norm,
)
from market_documents.publishing.source_dataset import ComparisonDataset, ResearchSnapshot, resolve_research_snapshot
from market_documents.publishing.validation import validate_persisted
from market_documents.services.embedding_config import EMBEDDING_CONFIG, MODEL_NAME, MODEL_REVISION
from market_documents.services.financial_language_config import CORE_CATEGORIES, CUSTOM_TAXONOMY_CATEGORIES
from market_documents.services.financial_language_metrics import (
    PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES,
    classify_collision,
    safe_ratio,
)
from market_documents.services.feature_config import FEATURE_CONFIG
from market_documents.services.feature_metrics import passage_excluded_from_features
from market_documents.services.passage_embedding import get_embedding_model

# Which quality dimension gates each discovery/finding candidate -- used to
# choose which already-computed quality label to attach to a discovery item.
_CANDIDATE_QUALITY_SCOPE = {
    "largest_overall_change": "feature",
    "largest_new_disclosure_share": "feature",
    "largest_uncertainty_increase": "report_side",
    "largest_negative_tone_shift": "report_side",
    "largest_governance_shift": "report_side",
    "largest_financial_condition_shift": "report_side",
    "largest_risk_introduction": "alignment_change",
    "largest_risk_removal": "alignment_change",
}

METRIC_CATALOG: tuple[dict, ...] = (
    dict(
        metric_key="disclosure_change_score",
        display_name="Overall disclosure change",
        short_description="How much a report's disclosures changed compared to the prior report.",
        technical_description="Composite score over lexical/structural passage-alignment change classes, weighted per `feature_extraction`'s score_version.",
        unit="score_0_1",
        direction_interpretation="Higher means more change; the score does not indicate whether the change is positive or negative for the company.",
        methodology_anchor="Milestone 3/6: services.feature_extraction.build_features, ReportPairFeatures.disclosure_change_score",
    ),
    dict(
        metric_key="net_tone_change",
        display_name="Net tone change",
        short_description="Whether the report's overall language tone became more positive or more negative.",
        technical_description="Change in (positive_rate - negative_rate) per 1,000 analyzed words, earlier vs. later report.",
        unit="rate_per_1000_words",
        direction_interpretation="Positive means tone became more positive; negative means tone became more negative.",
        methodology_anchor="Milestone 6: services.financial_language_metrics, ReportPairLanguageFeatures.net_tone_change",
    ),
    dict(
        metric_key="uncertainty_intensity_change",
        display_name="Uncertainty language change",
        short_description="Whether uncertainty-related language increased or decreased.",
        technical_description="Change in uncertainty-category dictionary hit rate per 1,000 analyzed words.",
        unit="rate_per_1000_words",
        direction_interpretation="Positive means more uncertainty language; negative means less.",
        methodology_anchor="Milestone 6: ReportPairLanguageFeatures.uncertainty_intensity_change",
    ),
    dict(
        metric_key="risk_language_introduction",
        display_name="Risk language introduced",
        short_description="How much new risk-related language was introduced in modified/new passages.",
        technical_description="Risk-category dictionary hits attributable to NEW/SUBSTANTIALLY_MODIFIED-introduced passage content, rate per 1,000 words of the alignment-change-analyzed population.",
        unit="rate_per_1000_words",
        direction_interpretation="Higher means more newly introduced risk language.",
        methodology_anchor="Milestone 6: ReportPairLanguageFeatures.risk_language_introduction",
    ),
    dict(
        metric_key="risk_language_removal",
        display_name="Risk language removed",
        short_description="How much previously-present risk-related language was removed.",
        technical_description="Risk-category dictionary hits attributable to REMOVED/SUBSTANTIALLY_MODIFIED-removed passage content, rate per 1,000 words of the alignment-change-analyzed population.",
        unit="rate_per_1000_words",
        direction_interpretation="Higher means more risk language removed.",
        methodology_anchor="Milestone 6: ReportPairLanguageFeatures.risk_language_removal",
    ),
    dict(
        metric_key="governance_language_change",
        display_name="Governance language change",
        short_description="Change in governance-related language.",
        technical_description="Change in custom-taxonomy governance-category rate per 1,000 analyzed words.",
        unit="rate_per_1000_words",
        direction_interpretation="Positive means more governance language; negative means less.",
        methodology_anchor="Milestone 6: ReportPairLanguageFeatures.governance_language_change",
    ),
    dict(
        metric_key="financial_condition_language_change",
        display_name="Financial condition language change",
        short_description="Change in language describing financial condition.",
        technical_description="Change in custom-taxonomy financial-condition-category rate per 1,000 analyzed words.",
        unit="rate_per_1000_words",
        direction_interpretation="Positive means more financial-condition language; negative means less.",
        methodology_anchor="Milestone 6: ReportPairLanguageFeatures.financial_condition_language_change",
    ),
    dict(
        metric_key="new_rate_words",
        display_name="New disclosure share",
        short_description="Share of the report (by word) that is entirely new disclosure content.",
        technical_description="`new_words / (unchanged+lightly_modified+substantially_modified+new+removed+ambiguous words)`.",
        unit="share",
        direction_interpretation="Higher means a larger share of the report is new content.",
        methodology_anchor="Milestone 3: ReportPairFeatures.new_words / feature-eligible word totals",
    ),
)


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    netloc = parts.hostname or ""
    if parts.port:
        netloc += f":{parts.port}"
    path = parts.path
    return urlunsplit((parts.scheme, netloc, path, "", ""))


def _source_configuration_hash(research_schema_version: str) -> str:
    payload = "|".join(
        [
            research_schema_version,
            labels.METRIC_THRESHOLD_VERSION,
            str(sorted(labels.PUBLICATION_EXCLUDED_CATEGORIES)),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _new_rate_words(features) -> float | None:
    denom = (
        features.eligible_unchanged_words
        + features.eligible_lightly_modified_words
        + features.eligible_substantially_modified_words
        + features.eligible_new_words
        + features.eligible_removed_words
        + features.eligible_ambiguous_words
    )
    return safe_ratio(features.eligible_new_words, denom)


def _comparison_metrics(comparison: ComparisonDataset) -> ComparisonMetrics:
    f = comparison.features
    lf = comparison.language_features
    return ComparisonMetrics(
        disclosure_change_score=f.disclosure_change_score,
        feature_quality_ok=f.feature_quality.value in ("GOOD", "USABLE"),
        feature_primary_eligible=f.primary_eligible,
        net_tone_change=lf.net_tone_change if lf else None,
        uncertainty_intensity_change=lf.uncertainty_intensity_change if lf else None,
        risk_language_introduction=lf.risk_language_introduction if lf else None,
        risk_language_removal=lf.risk_language_removal if lf else None,
        governance_language_change=lf.governance_language_change if lf else None,
        financial_condition_language_change=lf.financial_condition_language_change if lf else None,
        report_side_quality_ok=(lf.report_side_signal_quality.value in ("GOOD", "USABLE")) if lf else False,
        report_side_primary_eligible=lf.report_side_primary_eligible if lf else False,
        alignment_change_quality_ok=(lf.alignment_change_signal_quality.value in ("GOOD", "USABLE")) if lf else False,
        alignment_change_primary_eligible=lf.alignment_change_primary_eligible if lf else False,
        new_rate_words=_new_rate_words(f),
    )


class PublicationBuilder:
    """Builds one publication's worth of `app`/`app_internal` rows from a
    `ResearchSnapshot`, entirely in memory, then writes them in one
    transactional pass. Never mutates `application_state`."""

    def __init__(self, publication_version: str, settings: Settings | None = None):
        self.publication_version = publication_version
        self.settings = settings or get_settings()

    def build(self, research_session: Session, app_session: Session) -> Publication:
        snapshot = resolve_research_snapshot(research_session)

        publication = Publication(
            id=labels.derive_id(self.publication_version, "publications"),
            publication_version=self.publication_version,
            source_database_identifier=_redact_url(self.settings.database_url),
            source_schema_version=snapshot.research_schema_version,
            source_configuration_hash=_source_configuration_hash(snapshot.research_schema_version),
            status=PublicationStatus.BUILDING.value,
            started_at=datetime.now(timezone.utc),
        )
        app_session.add(publication)
        app_session.flush()

        try:
            counts = self._build_rows(app_session, publication, snapshot)
        except Exception as exc:  # noqa: BLE001 -- must record failure, never re-raise silently past this point
            publication.status = PublicationStatus.FAILED.value
            publication.failure_reason = str(exc)
            publication.completed_at = datetime.now(timezone.utc)
            app_session.flush()
            raise

        for key, value in counts.items():
            setattr(publication, key, value)
        app_session.flush()

        publication.status = PublicationStatus.VALIDATING.value
        app_session.flush()
        summary = validate_persisted(app_session, publication.id)
        publication.validation_summary = summary.to_dict()
        if summary.passed:
            publication.status = PublicationStatus.READY.value
        else:
            publication.status = PublicationStatus.FAILED.value
            publication.failure_reason = f"validation failed: {len(summary.failures)} check(s) did not pass"
        publication.completed_at = datetime.now(timezone.utc)
        app_session.flush()
        return publication

    def _build_rows(self, app_session: Session, publication: Publication, snapshot: ResearchSnapshot) -> dict:
        pub_id = publication.id
        pv = self.publication_version

        app_companies: dict[uuid.UUID, Company] = {}
        app_reports: dict[uuid.UUID, Report] = {}
        report_source_to_app: dict[uuid.UUID, uuid.UUID] = {}
        company_of_report: dict[uuid.UUID, uuid.UUID] = {}

        for company_index, cd in enumerate(snapshot.companies):
            company = cd.company
            app_company_id = labels.derive_id(pv, "companies", str(company.id))
            reports_sorted = cd.reports  # already ordered by period_end in source_dataset
            app_company = Company(
                id=app_company_id,
                publication_id=pub_id,
                source_company_id=company.id,
                ticker=company.ticker,
                name=company.company_name,
                short_name=None,
                sector=company.sector,
                description=None,
                first_report_period_end=reports_sorted[0].period_end,
                latest_report_period_end=reports_sorted[-1].period_end,
                report_count=len(reports_sorted),
                comparison_count=0,
                latest_comparison_id=None,
                historical_peak_comparison_id=None,
                display_order=company_index,
                has_current_data=True,
            )
            app_companies[company.id] = app_company
            app_session.add(app_company)

            for chron_index, report in enumerate(reports_sorted):
                extraction_info = snapshot.extraction_by_report.get(report.id)
                narrative_document = extraction_info.narrative_document if extraction_info else None
                extraction_run = extraction_info.extraction_run if extraction_info else None
                app_report_id = labels.derive_id(pv, "reports", str(report.id))
                title = f"{company.ticker} report for period ended {report.period_end or report.fiscal_label or report.directory_year}"
                extraction_quality = (
                    extraction_run.extraction_quality.value
                    if extraction_run is not None and extraction_run.extraction_quality is not None
                    else None
                )
                app_report = Report(
                    id=app_report_id,
                    publication_id=pub_id,
                    source_report_id=report.id,
                    company_id=app_company_id,
                    title=title,
                    filename=report.filename,
                    directory_year=report.directory_year,
                    period_start=report.period_start,
                    period_end=report.period_end,
                    page_count=report.page_count,
                    narrative_word_count=narrative_document.word_count if narrative_document else None,
                    extraction_quality=extraction_quality,
                    extraction_quality_label=labels.quality_label(extraction_quality, "generic"),
                    extraction_warning=extraction_run.review_reason if extraction_run else None,
                    chronological_index=chron_index,
                )
                app_reports[report.id] = app_report
                report_source_to_app[report.id] = app_report_id
                company_of_report[report.id] = company.id
                app_session.add(app_report)

        app_session.flush()

        # --- Percentile bands over this publication's own eligible population ---
        # `disclosure_change_score` is banded over every *displayed* score
        # (quality != FAILED, score not null) -- deliberately broader than
        # primary-eligibility, per the Milestone 7A.1 follow-up ("review-
        # qualified disclosure-change publication"): a NEEDS_REVIEW score is
        # still shown, with its own quality made explicit, rather than
        # withheld. `new_rate_words` is discovery-ranking-only (never
        # displayed as its own field on report_comparisons), so it keeps the
        # original primary-eligible-only population unchanged.
        metric_values: dict[str, list[float]] = {m["metric_key"]: [] for m in METRIC_CATALOG}
        for cd in snapshot.comparisons:
            metrics = _comparison_metrics(cd)
            f = cd.features
            if labels.disclosure_change_score_displayed(f.feature_quality.value, f.disclosure_change_score):
                metric_values["disclosure_change_score"].append(f.disclosure_change_score)
            if metrics.feature_quality_ok and metrics.feature_primary_eligible:
                if metrics.new_rate_words is not None:
                    metric_values["new_rate_words"].append(metrics.new_rate_words)
            if metrics.report_side_quality_ok and metrics.report_side_primary_eligible:
                for key in (
                    "net_tone_change",
                    "uncertainty_intensity_change",
                    "governance_language_change",
                    "financial_condition_language_change",
                ):
                    value = getattr(metrics, key)
                    if value is not None:
                        metric_values[key].append(value)
            if metrics.alignment_change_quality_ok and metrics.alignment_change_primary_eligible:
                for key in ("risk_language_introduction", "risk_language_removal"):
                    value = getattr(metrics, key)
                    if value is not None:
                        metric_values[key].append(value)

        bands_by_metric = {
            key: labels.compute_percentile_bands(key, values) for key, values in metric_values.items()
        }

        for order, m in enumerate(METRIC_CATALOG):
            app_session.add(
                MetricDefinition(
                    id=labels.derive_id(pv, "metric_definitions", m["metric_key"]),
                    publication_id=pub_id,
                    **m,
                )
            )
            for band in bands_by_metric[m["metric_key"]]:
                app_session.add(
                    MetricLabelThreshold(
                        id=labels.derive_id(
                            pv, "metric_label_thresholds", m["metric_key"], labels.METRIC_THRESHOLD_VERSION, band.label
                        ),
                        publication_id=pub_id,
                        metric_key=band.metric_key,
                        threshold_version=labels.METRIC_THRESHOLD_VERSION,
                        label=band.label,
                        minimum_value=band.minimum_value,
                        maximum_value=band.maximum_value,
                        display_order=band.display_order,
                        explanation=band.explanation,
                    )
                )

        def _pct_rank(value: float | None, key: str) -> float | None:
            if value is None or not metric_values[key]:
                return None
            pool = sorted(metric_values[key])
            below_or_equal = sum(1 for v in pool if abs(v) <= abs(value))
            return 100.0 * below_or_equal / len(pool)

        # --- Comparisons ---
        app_comparisons: dict[uuid.UUID, ReportComparison] = {}
        comparisons_by_company: dict[uuid.UUID, list[ComparisonDataset]] = {}
        comparison_metrics_by_source: dict[uuid.UUID, ComparisonMetrics] = {}

        for cd in snapshot.comparisons:
            pair = cd.pair
            f = cd.features
            lf = cd.language_features if not cd.language_lineage_mismatch else None
            metrics = _comparison_metrics(cd)
            comparison_metrics_by_source[pair.id] = metrics

            earlier_report = app_reports.get(pair.earlier_report_id)
            later_report = app_reports.get(pair.later_report_id)
            if earlier_report is None or later_report is None:
                continue
            company_source_id = company_of_report[pair.earlier_report_id]
            app_comparison_id = labels.derive_id(pv, "report_comparisons", str(pair.id))

            report_side_quality = lf.report_side_signal_quality.value if lf else None
            alignment_change_quality = lf.alignment_change_signal_quality.value if lf else None

            structured_content_exclusion_share = (
                safe_ratio(
                    lf.excluded_structured_content_words,
                    lf.all_passages_earlier_words + lf.all_passages_later_words,
                )
                if lf
                else None
            )

            primary_finding, secondary_finding, tertiary_finding = select_findings(metrics)
            finding_payload = {
                c.key: {"value": c.value, "magnitude": c.magnitude} for c in eligible_candidates(metrics)
            }
            # Diagnostic-only: whether the *raw* upstream disclosure_change_
            # score existed before the FAILED-quality suppression below --
            # not reconstructable from the persisted (possibly-suppressed)
            # `disclosure_change_score` column alone, so it's captured here
            # for `publication_comparison_audit.csv`'s "score available"
            # field rather than adding a dedicated schema column for it.
            finding_payload["_disclosure_change_diagnostics"] = {
                "score_available": f.disclosure_change_score is not None
            }

            disclosure_change_quality = f.feature_quality.value
            score_displayed = labels.disclosure_change_score_displayed(
                disclosure_change_quality, f.disclosure_change_score
            )
            displayed_score = f.disclosure_change_score if score_displayed else None
            warning_parts = [
                part
                for part in (
                    f"warning: {f.warning_reasons}" if f.warning_reasons else None,
                    f"exclusion: {f.exclusion_reasons}" if f.exclusion_reasons else None,
                )
                if part
            ]

            app_comparison = ReportComparison(
                id=app_comparison_id,
                publication_id=pub_id,
                source_report_pair_id=pair.id,
                company_id=app_companies[company_source_id].id,
                earlier_report_id=earlier_report.id,
                later_report_id=later_report.id,
                earlier_period_end=earlier_report.period_end,
                later_period_end=later_report.period_end,
                gap_months=pair.gap_months,
                chronological_index=0,  # assigned below, per company
                is_transition=pair.is_transition,
                is_irregular_gap=f.irregular_gap,
                is_latest_for_company=False,  # assigned below
                is_historical_peak_change=False,  # assigned below
                disclosure_change_score=displayed_score,
                disclosure_change_label=labels.label_for_unsigned_metric(
                    displayed_score, bands_by_metric["disclosure_change_score"]
                ),
                disclosure_change_percentile=_pct_rank(displayed_score, "disclosure_change_score"),
                disclosure_change_quality=disclosure_change_quality,
                disclosure_change_quality_label=labels.quality_label(disclosure_change_quality, "generic"),
                disclosure_change_primary_eligible=f.primary_eligible,
                disclosure_change_warning="; ".join(warning_parts) if warning_parts else None,
                net_tone_change=lf.net_tone_change if lf else None,
                net_tone_change_label=labels.label_for_signed_metric(
                    lf.net_tone_change if lf else None, bands_by_metric["net_tone_change"]
                ),
                uncertainty_change=lf.uncertainty_intensity_change if lf else None,
                uncertainty_change_label=labels.label_for_signed_metric(
                    lf.uncertainty_intensity_change if lf else None, bands_by_metric["uncertainty_intensity_change"]
                ),
                risk_introduction_rate=lf.risk_language_introduction if lf else None,
                risk_introduction_label=labels.label_for_signed_metric(
                    lf.risk_language_introduction if lf else None, bands_by_metric["risk_language_introduction"]
                ),
                risk_removal_rate=lf.risk_language_removal if lf else None,
                risk_removal_label=labels.label_for_signed_metric(
                    lf.risk_language_removal if lf else None, bands_by_metric["risk_language_removal"]
                ),
                governance_change=lf.governance_language_change if lf else None,
                governance_change_label=labels.label_for_signed_metric(
                    lf.governance_language_change if lf else None, bands_by_metric["governance_language_change"]
                ),
                financial_condition_change=lf.financial_condition_language_change if lf else None,
                financial_condition_change_label=labels.label_for_signed_metric(
                    lf.financial_condition_language_change if lf else None,
                    bands_by_metric["financial_condition_language_change"],
                ),
                forward_looking_change=lf.forward_looking_caution_change if lf else None,
                forward_looking_change_label=None,
                new_passage_count=f.new_count,
                removed_passage_count=f.removed_count,
                lightly_modified_passage_count=f.lightly_modified_count,
                substantially_modified_passage_count=f.substantially_modified_count,
                ambiguous_passage_count=f.ambiguous_count,
                report_side_quality=report_side_quality,
                report_side_quality_label=labels.quality_label(report_side_quality, "report_side"),
                report_side_primary_eligible=lf.report_side_primary_eligible if lf else None,
                report_side_warning=lf.report_side_warning_reasons if lf else None,
                alignment_change_quality=alignment_change_quality,
                alignment_change_quality_label=labels.quality_label(alignment_change_quality, "alignment_change"),
                alignment_change_primary_eligible=lf.alignment_change_primary_eligible if lf else None,
                alignment_change_warning=lf.alignment_change_warning_reasons if lf else None,
                dictionary_match_rate_earlier=lf.dictionary_match_rate_earlier if lf else None,
                dictionary_match_rate_later=lf.dictionary_match_rate_later if lf else None,
                ambiguous_word_share=lf.ambiguous_alignment_share if lf else None,
                collision_flagged_word_share=lf.collision_flagged_word_share if lf else None,
                unmatched_word_share=lf.unmatched_word_share if lf else None,
                structured_content_exclusion_share=structured_content_exclusion_share,
                primary_finding_key=primary_finding.key if primary_finding else None,
                secondary_finding_key=secondary_finding.key if secondary_finding else None,
                tertiary_finding_key=tertiary_finding.key if tertiary_finding else None,
                finding_payload=finding_payload,
            )
            app_comparisons[pair.id] = app_comparison
            comparisons_by_company.setdefault(company_source_id, []).append(cd)
            app_session.add(app_comparison)

        app_session.flush()

        # --- Per-company chronology, latest, and historical-peak assignment ---
        for company_source_id, cds in comparisons_by_company.items():
            ordered = sorted(
                cds, key=lambda cd: app_reports[cd.pair.later_report_id].period_end or datetime.min.date()
            )
            for idx, cd in enumerate(ordered):
                app_comparisons[cd.pair.id].chronological_index = idx
            latest_cd = ordered[-1]
            app_comparisons[latest_cd.pair.id].is_latest_for_company = True

            peak_candidates = [
                cd for cd in ordered
                if comparison_metrics_by_source[cd.pair.id].feature_quality_ok
                and comparison_metrics_by_source[cd.pair.id].feature_primary_eligible
                and comparison_metrics_by_source[cd.pair.id].disclosure_change_score is not None
            ]
            peak_cd = None
            if peak_candidates:
                peak_cd = max(
                    peak_candidates,
                    key=lambda cd: (
                        comparison_metrics_by_source[cd.pair.id].disclosure_change_score,
                        app_reports[cd.pair.later_report_id].period_end or datetime.min.date(),
                    ),
                )
                app_comparisons[peak_cd.pair.id].is_historical_peak_change = True

            app_company = app_companies[company_source_id]
            app_company.comparison_count = len(ordered)
            app_company.latest_comparison_id = app_comparisons[latest_cd.pair.id].id
            if peak_cd is not None:
                app_company.historical_peak_comparison_id = app_comparisons[peak_cd.pair.id].id

        app_session.flush()

        # --- Passages ---
        app_passages: dict[uuid.UUID, Passage] = {}
        # Milestone 7B.1: one deduplicated vector per published passage,
        # keyed by *source* passage id (same key space as app_passages) so
        # the retrieval-context pass below can look both up together.
        app_passage_embeddings: dict[uuid.UUID, AppPassageEmbedding] = {}
        for report_source_id, passage_datasets in snapshot.passages_by_report.items():
            app_report = app_reports.get(report_source_id)
            if app_report is None:
                continue
            for pd in passage_datasets:
                if pd.excluded_as_artifact:
                    continue
                passage = pd.passage
                category = pd.classification.category if pd.classification is not None else None
                app_passage_id = labels.derive_id(pv, "passages", str(passage.id))
                app_passage = Passage(
                    id=app_passage_id,
                    publication_id=pub_id,
                    source_passage_id=passage.id,
                    company_id=app_report.company_id,
                    report_id=app_report.id,
                    report_period_end=app_report.period_end,
                    passage_index=passage.passage_index,
                    first_page_number=passage.first_page_number,
                    last_page_number=passage.last_page_number,
                    heading=passage.heading_text,
                    passage_type=passage.passage_type.value,
                    text=passage.raw_text,
                    word_count=passage.word_count,
                    structured_content_category=category,
                    primary_narrative_eligible=category not in PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES,
                    feature_eligible=not passage_excluded_from_features(
                        passage.word_count, passage.passage_type, FEATURE_CONFIG
                    ),
                )
                app_passages[passage.id] = app_passage
                app_session.add(app_passage)

                source_embedding = pd.embedding
                if source_embedding is None:
                    # No current accepted source embedding -- left out of
                    # app_passage_embeddings entirely (never a zero/placeholder
                    # vector). `validate_persisted` fails the publication
                    # unless this passage is a documented exclusion.
                    continue
                embedding_run = source_embedding.embedding_run
                vector = list(source_embedding.embedding)
                app_embedding = AppPassageEmbedding(
                    id=labels.derive_id(pv, "passage_embeddings", str(passage.id)),
                    publication_id=pub_id,
                    passage_id=app_passage_id,
                    source_embedding_id=source_embedding.id,
                    source_embedding_run_id=embedding_run.id,
                    embedding_model=embedding_run.model_name,
                    embedding_model_revision=embedding_run.model_revision,
                    dimensions=len(vector),
                    embedding_text_hash=embedding_text_hash(app_passage.text),
                    embedding=vector,
                    vector_norm=vector_norm(vector),
                )
                app_passage_embeddings[passage.id] = app_embedding
                app_session.add(app_embedding)

        app_session.flush()

        # --- Passage comparisons and passage-language signals ---
        passage_comparison_count = 0
        passage_language_signal_count = 0
        language_metric_count = 0
        # Milestone 7B.1 bookkeeping, filled in alongside the loop below and
        # consumed by the "Retrieval contexts" pass after it: one record per
        # created PassageComparison (so contexts can be derived without a
        # second query pass), plus every language-signal category/subcategory
        # observed per (passage_comparison_id, report_side) so context
        # category rows can be deduplicated deterministically.
        pc_records: list[tuple[PassageComparison, ReportComparison, Passage | None, Passage | None]] = []
        signal_tags_by_pc_side: dict[tuple[uuid.UUID, str], list[LanguageSignalTag]] = {}

        for cd in snapshot.comparisons:
            app_comparison = app_comparisons.get(cd.pair.id)
            if app_comparison is None:
                continue

            app_alignment_by_source: dict[uuid.UUID, uuid.UUID] = {}
            for alignment in cd.passage_alignments:
                earlier_app = app_passages.get(alignment.earlier_passage_id) if alignment.earlier_passage_id else None
                later_app = app_passages.get(alignment.later_passage_id) if alignment.later_passage_id else None
                if earlier_app is None and later_app is None:
                    continue  # both sides were publication-excluded artifacts
                if alignment.alignment_status in (
                    AlignmentStatus.UNCHANGED,
                    AlignmentStatus.LIGHTLY_MODIFIED,
                    AlignmentStatus.SUBSTANTIALLY_MODIFIED,
                ) and (earlier_app is None or later_app is None):
                    # A matched status implies two real, published passages.
                    # If the alignment engine matched this pair but one side
                    # was subsequently excluded here as an invalid extraction
                    # artifact (short_fragment_invalid/broken_fragment_
                    # sequence), publishing a one-sided "matched" row would
                    # misrepresent the alignment_status -- skip entirely
                    # rather than publish a broken half-match.
                    continue
                if alignment.alignment_status == AlignmentStatus.NEW and later_app is None:
                    continue
                if alignment.alignment_status == AlignmentStatus.REMOVED and earlier_app is None:
                    continue
                app_pc_id = labels.derive_id(pv, "passage_comparisons", str(alignment.id))
                app_pc = PassageComparison(
                    id=app_pc_id,
                    publication_id=pub_id,
                    source_alignment_id=alignment.id,
                    report_comparison_id=app_comparison.id,
                    earlier_passage_id=earlier_app.id if earlier_app else None,
                    later_passage_id=later_app.id if later_app else None,
                    alignment_status=alignment.alignment_status.value,
                    alignment_type=alignment.alignment_type.value,
                    confidence=alignment.confidence.value,
                    confidence_label=labels.confidence_label(alignment.confidence.value),
                    semantic_similarity=alignment.semantic_similarity,
                    lexical_similarity=alignment.lexical_cosine_similarity,
                    heading_similarity=alignment.heading_similarity,
                    content_score=alignment.combined_score,
                    position_difference=alignment.position_difference,
                    collision_flag=classify_collision(alignment.review_reason),
                    split_merge_flag=alignment.alignment_type
                    in (AlignmentType.ONE_TO_TWO, AlignmentType.TWO_TO_ONE),
                    primary_alignment=alignment.primary_alignment,
                    review_reason=alignment.review_reason,
                )
                app_session.add(app_pc)
                app_alignment_by_source[alignment.id] = app_pc_id
                pc_records.append((app_pc, app_comparison, earlier_app, later_app))
                passage_comparison_count += 1

            app_session.flush()

            if cd.language_features is not None and not cd.language_lineage_mismatch:
                lf = cd.language_features
                # --- language_metrics (report_side + alignment_change) ---
                for category in CORE_CATEGORIES:
                    app_session.add(
                        LanguageMetric(
                            id=labels.derive_id(pv, "language_metrics", str(cd.pair.id), "report_side", category),
                            publication_id=pub_id,
                            report_comparison_id=app_comparison.id,
                            metric_scope="report_side",
                            population="primary_narrative",
                            category=category,
                            subcategory=None,
                            earlier_count=getattr(lf, f"{category}_count_earlier"),
                            later_count=getattr(lf, f"{category}_count_later"),
                            earlier_rate_per_1000=getattr(lf, f"{category}_rate_earlier"),
                            later_rate_per_1000=getattr(lf, f"{category}_rate_later"),
                            rate_change=getattr(lf, f"{category}_rate_change"),
                            absolute_rate_change=getattr(lf, f"{category}_rate_change_abs"),
                            introduced_count=None,
                            introduced_rate_per_1000=None,
                            removed_count=None,
                            removed_rate_per_1000=None,
                            retained_count=None,
                            negated_count=None,
                            quality=lf.report_side_signal_quality.value,
                            primary_eligible=lf.report_side_primary_eligible,
                        )
                    )
                    language_metric_count += 1

                    introduced = getattr(lf, f"{category}_hits_new")
                    removed = getattr(lf, f"{category}_hits_removed")
                    denom = lf.alignment_change_analyzed_words_excl_ambiguous
                    app_session.add(
                        LanguageMetric(
                            id=labels.derive_id(pv, "language_metrics", str(cd.pair.id), "alignment_change", category),
                            publication_id=pub_id,
                            report_comparison_id=app_comparison.id,
                            metric_scope="alignment_change",
                            population="primary_narrative_excl_ambiguous",
                            category=category,
                            subcategory=None,
                            earlier_count=None,
                            later_count=None,
                            earlier_rate_per_1000=None,
                            later_rate_per_1000=None,
                            rate_change=None,
                            absolute_rate_change=None,
                            introduced_count=introduced,
                            introduced_rate_per_1000=safe_ratio(introduced * 1000, denom) if denom else None,
                            removed_count=removed,
                            removed_rate_per_1000=safe_ratio(removed * 1000, denom) if denom else None,
                            retained_count=None,
                            negated_count=None,
                            quality=lf.alignment_change_signal_quality.value,
                            primary_eligible=lf.alignment_change_primary_eligible,
                        )
                    )
                    language_metric_count += 1

                for category in CUSTOM_TAXONOMY_CATEGORIES:
                    earlier_rate = getattr(lf, f"{category}_rate_earlier")
                    later_rate = getattr(lf, f"{category}_rate_later")
                    rate_change = (
                        later_rate - earlier_rate if earlier_rate is not None and later_rate is not None else None
                    )
                    app_session.add(
                        LanguageMetric(
                            id=labels.derive_id(pv, "language_metrics", str(cd.pair.id), "report_side", category),
                            publication_id=pub_id,
                            report_comparison_id=app_comparison.id,
                            metric_scope="report_side",
                            population="custom_taxonomy",
                            category=category,
                            subcategory=None,
                            earlier_count=None,
                            later_count=None,
                            earlier_rate_per_1000=earlier_rate,
                            later_rate_per_1000=later_rate,
                            rate_change=rate_change,
                            absolute_rate_change=abs(rate_change) if rate_change is not None else None,
                            introduced_count=None,
                            introduced_rate_per_1000=None,
                            removed_count=None,
                            removed_rate_per_1000=None,
                            retained_count=None,
                            negated_count=None,
                            quality=lf.report_side_signal_quality.value,
                            primary_eligible=lf.report_side_primary_eligible,
                        )
                    )
                    language_metric_count += 1

                # --- passage_language_signals ---
                for signal in cd.passage_language_signals:
                    app_passage = app_passages.get(signal.passage_id)
                    app_pc_id = app_alignment_by_source.get(signal.passage_alignment_id)
                    if app_passage is None or app_pc_id is None:
                        continue
                    is_introduced = signal.alignment_status == AlignmentStatus.NEW and signal.report_side == ReportSide.LATER
                    is_removed = signal.alignment_status == AlignmentStatus.REMOVED and signal.report_side == ReportSide.EARLIER
                    is_retained = signal.alignment_status in (
                        AlignmentStatus.UNCHANGED,
                        AlignmentStatus.LIGHTLY_MODIFIED,
                        AlignmentStatus.SUBSTANTIALLY_MODIFIED,
                    )
                    for category in CORE_CATEGORIES:
                        raw_count = getattr(signal, f"{category}_count")
                        if raw_count == 0:
                            continue
                        rate = safe_ratio(raw_count * 1000, signal.passage_word_count)
                        app_session.add(
                            PassageLanguageSignal(
                                id=labels.derive_id(
                                    pv, "passage_language_signals", str(signal.id), category, ""
                                ),
                                publication_id=pub_id,
                                passage_id=app_passage.id,
                                passage_comparison_id=app_pc_id,
                                report_comparison_id=app_comparison.id,
                                report_side=signal.report_side.value,
                                category=category,
                                subcategory=None,
                                raw_count=raw_count,
                                negated_count=None,
                                adjusted_count=raw_count,
                                rate_per_1000=rate,
                                is_introduced=is_introduced,
                                is_removed=is_removed,
                                is_retained=is_retained,
                            )
                        )
                        passage_language_signal_count += 1
                        signal_tags_by_pc_side.setdefault((app_pc_id, signal.report_side.value), []).append(
                            LanguageSignalTag(category=category, subcategory=None, adjusted_count=raw_count)
                        )

                    for hit in cd.category_hits_by_signal_id.get(signal.id, []):
                        if hit.hit_count <= 0:
                            continue
                        adjusted = max(hit.hit_count - hit.negated_hit_count, 0)
                        rate = safe_ratio(hit.hit_count * 1000, signal.passage_word_count)
                        app_session.add(
                            PassageLanguageSignal(
                                id=labels.derive_id(
                                    pv, "passage_language_signals", str(signal.id), hit.category, hit.subcategory
                                ),
                                publication_id=pub_id,
                                passage_id=app_passage.id,
                                passage_comparison_id=app_pc_id,
                                report_comparison_id=app_comparison.id,
                                report_side=signal.report_side.value,
                                category=hit.category,
                                subcategory=hit.subcategory,
                                raw_count=hit.hit_count,
                                negated_count=hit.negated_hit_count,
                                adjusted_count=adjusted,
                                rate_per_1000=rate,
                                is_introduced=is_introduced,
                                is_removed=is_removed,
                                is_retained=is_retained,
                            )
                        )
                        passage_language_signal_count += 1
                        signal_tags_by_pc_side.setdefault((app_pc_id, signal.report_side.value), []).append(
                            LanguageSignalTag(
                                category=hit.category, subcategory=hit.subcategory, adjusted_count=adjusted
                            )
                        )

        app_session.flush()

        # --- Retrieval contexts (Milestone 7B.1) ---
        # One context per non-null side pointer on each created
        # PassageComparison -- this single rule is what naturally implements
        # every alignment-status side rule the milestone requires: NEW rows
        # only ever have later_passage_id set (later-side context only),
        # REMOVED rows only ever have earlier_passage_id set (earlier-side
        # only), matched statuses have both set (both sides), and one-sided
        # AMBIGUOUS rows preserve whichever side is actually present. No
        # alignment_status branching is needed here.
        retrieval_context_count = 0
        comparison_participant_source_ids: set[uuid.UUID] = set()

        for app_pc, app_comparison, earlier_app, later_app in pc_records:
            sides = (
                ("EARLIER", earlier_app, app_comparison.earlier_report_id, app_comparison.earlier_period_end),
                ("LATER", later_app, app_comparison.later_report_id, app_comparison.later_period_end),
            )
            for side_value, side_app, side_report_id, side_period_end in sides:
                if side_app is None:
                    continue
                comparison_participant_source_ids.add(side_app.source_passage_id)
                side_embedding = app_passage_embeddings.get(side_app.source_passage_id)
                if side_embedding is None:
                    # No current source embedding for this side -- no
                    # retrieval context can be built (FK requires one), but
                    # the passage/comparison rows themselves are still
                    # published; `validate_persisted` surfaces the gap.
                    continue
                tags = signal_tags_by_pc_side.get((app_pc.id, side_value), [])
                app_session.add(
                    RetrievalContext(
                        id=labels.derive_id(pv, "retrieval_contexts", str(app_pc.id), side_value),
                        publication_id=pub_id,
                        passage_id=side_app.id,
                        passage_embedding_id=side_embedding.id,
                        passage_comparison_id=app_pc.id,
                        report_comparison_id=app_comparison.id,
                        report_id=side_report_id,
                        company_id=app_comparison.company_id,
                        context_type="COMPARISON_LINKED",
                        report_side=side_value,
                        alignment_status=app_pc.alignment_status,
                        alignment_type=app_pc.alignment_type,
                        confidence=app_pc.confidence,
                        report_period_end=side_period_end,
                        earlier_period_end=app_comparison.earlier_period_end,
                        later_period_end=app_comparison.later_period_end,
                        heading=side_app.heading,
                        passage_type=side_app.passage_type,
                        primary_narrative_eligible=side_app.primary_narrative_eligible,
                        feature_eligible=side_app.feature_eligible,
                        structured_content_category=side_app.structured_content_category,
                        report_side_quality=app_comparison.report_side_quality,
                        alignment_change_quality=app_comparison.alignment_change_quality,
                        collision_flag=app_pc.collision_flag,
                        split_merge_flag=app_pc.split_merge_flag,
                        irregular_gap_flag=app_comparison.is_irregular_gap,
                    )
                )
                retrieval_context_count += 1
                for category in distinct_categories(tags):
                    app_session.add(
                        RetrievalContextLanguageCategory(
                            id=labels.derive_id(
                                pv, "retrieval_context_language_categories", str(app_pc.id), side_value, category
                            ),
                            publication_id=pub_id,
                            retrieval_context_id=labels.derive_id(
                                pv, "retrieval_contexts", str(app_pc.id), side_value
                            ),
                            category=category,
                        )
                    )
                for subcategory in distinct_risk_subcategories(tags):
                    app_session.add(
                        RetrievalContextRiskSubcategory(
                            id=labels.derive_id(
                                pv, "retrieval_context_risk_subcategories", str(app_pc.id), side_value, subcategory
                            ),
                            publication_id=pub_id,
                            retrieval_context_id=labels.derive_id(
                                pv, "retrieval_contexts", str(app_pc.id), side_value
                            ),
                            subcategory=subcategory,
                        )
                    )

        # --- Retrieval contexts: REPORT_ONLY ---
        # A passage that never occupies any side of any published passage
        # comparison (no alignment ever referenced it, or every alignment
        # that could have referenced it was excluded) would otherwise be
        # entirely unretrievable via semantic/hybrid search -- publish a
        # minimal context so it stays searchable, per the milestone's
        # "recommended eligibility" policy. Real corpus measurement (see the
        # Milestone 7B.1 report) found this affects ~0.1% of passages.
        for source_passage_id, app_passage in app_passages.items():
            if source_passage_id in comparison_participant_source_ids:
                continue
            embedding = app_passage_embeddings.get(source_passage_id)
            if embedding is None:
                continue
            app_session.add(
                RetrievalContext(
                    id=labels.derive_id(pv, "retrieval_contexts", str(app_passage.id), "REPORT_ONLY"),
                    publication_id=pub_id,
                    passage_id=app_passage.id,
                    passage_embedding_id=embedding.id,
                    passage_comparison_id=None,
                    report_comparison_id=None,
                    report_id=app_passage.report_id,
                    company_id=app_passage.company_id,
                    context_type="REPORT_ONLY",
                    report_side=None,
                    alignment_status=None,
                    alignment_type=None,
                    confidence=None,
                    report_period_end=app_passage.report_period_end,
                    earlier_period_end=None,
                    later_period_end=None,
                    heading=app_passage.heading,
                    passage_type=app_passage.passage_type,
                    primary_narrative_eligible=app_passage.primary_narrative_eligible,
                    feature_eligible=app_passage.feature_eligible,
                    structured_content_category=app_passage.structured_content_category,
                    report_side_quality=None,
                    alignment_change_quality=None,
                    collision_flag=False,
                    split_merge_flag=False,
                    irregular_gap_flag=False,
                )
            )
            retrieval_context_count += 1

        app_session.flush()

        # --- Q&A retrieval chunks (Milestone 7B.2) ---
        # A second, additive vector representation, never a replacement for
        # `app_passage_embeddings` above -- see the module docstring on
        # `QaChunk`. Built per report (never crossing a report boundary,
        # enforced here by construction: `build_qa_chunks` is called once
        # per report's own sorted passage list, never a merged list) from
        # `app_passages`' already-published, artifact-filtered rows -- a
        # source passage excluded upstream (artifact, or no accepted
        # embedding) simply isn't a QaPassageRow member and can't be quoted
        # in a chunk.
        embedding_model = get_embedding_model()
        qa_chunk_count = 0
        qa_chunk_passage_mapping_count = 0
        for report_source_id, passage_datasets in snapshot.passages_by_report.items():
            app_report = app_reports.get(report_source_id)
            if app_report is None:
                continue
            report_passage_rows: list[QaPassageRow] = []
            for pd in sorted(passage_datasets, key=lambda pd: pd.passage.passage_index):
                if pd.excluded_as_artifact:
                    continue
                app_passage = app_passages.get(pd.passage.id)
                if app_passage is None:
                    continue
                report_passage_rows.append(
                    QaPassageRow(
                        id=app_passage.id,
                        report_id=app_passage.report_id,
                        company_id=app_passage.company_id,
                        passage_index=pd.passage.passage_index,
                        heading=app_passage.heading,
                        text=app_passage.text,
                        first_page_number=app_passage.first_page_number,
                        last_page_number=app_passage.last_page_number,
                    )
                )
            if not report_passage_rows:
                continue

            chunk_candidates = build_qa_chunks(report_passage_rows, embedding_model.count_tokens)
            if not chunk_candidates:
                continue

            # Batched, never one giant single-call encode of an entire
            # report's chunks -- `encode_batch` forwards `batch_size=len
            # (texts)` straight to the model (a single unbatched forward
            # pass), which is fine for canonical-passage-sized inputs but
            # exhausts GPU/MPS memory once a report has hundreds of chunks.
            # Same batch size the canonical embedding pipeline already uses
            # (`services.passage_embedding._run_embedding`).
            encoded: list = []
            texts = [c.text for c in chunk_candidates]
            for batch_start in range(0, len(texts), EMBEDDING_CONFIG.batch_size):
                batch = texts[batch_start : batch_start + EMBEDDING_CONFIG.batch_size]
                encoded.extend(embedding_model.encode_batch(batch))
            seen_hashes: set[str] = set()
            for candidate, enc in zip(chunk_candidates, encoded):
                text_hash = embedding_text_hash(candidate.text)
                if text_hash in seen_hashes:
                    # Two windows in the same report producing byte-identical
                    # text (short trailing chunks are the common case) --
                    # `uq_app_qa_chunks_pub_report_index` would still accept
                    # a second row (chunk_index differs), but a duplicate
                    # vector adds retrieval noise with zero new coverage, so
                    # it's skipped here rather than persisted and later
                    # flagged by validate_persisted's duplicate-hash check.
                    continue
                seen_hashes.add(text_hash)

                chunk_id = labels.derive_id(
                    pv, "qa_chunks", str(candidate.report_id), str(candidate.chunk_index)
                )
                vector = list(enc.vector)
                app_session.add(
                    AppQaChunk(
                        id=chunk_id,
                        publication_id=pub_id,
                        report_id=candidate.report_id,
                        company_id=candidate.company_id,
                        chunk_index=candidate.chunk_index,
                        text=candidate.text,
                        section_heading=candidate.section_heading,
                        page_start=candidate.page_start,
                        page_end=candidate.page_end,
                        token_count=candidate.token_count,
                        truncation_policy=candidate.truncation_policy,
                        embedding_model=MODEL_NAME,
                        embedding_model_revision=MODEL_REVISION,
                        dimensions=len(vector),
                        embedding_text_hash=text_hash,
                        embedding=vector,
                        vector_norm=vector_norm(vector),
                    )
                )
                qa_chunk_count += 1
                for member_order, member_passage_id in enumerate(candidate.member_passage_ids):
                    app_session.add(
                        AppQaChunkPassage(
                            id=labels.derive_id(
                                pv, "qa_chunk_passages", str(chunk_id), str(member_passage_id)
                            ),
                            publication_id=pub_id,
                            qa_chunk_id=chunk_id,
                            passage_id=member_passage_id,
                            member_order=member_order,
                        )
                    )
                    qa_chunk_passage_mapping_count += 1

        app_session.flush()

        # --- Discovery items ---
        discovery_candidates = [
            DiscoveryCandidate(
                report_comparison_id=app_comparisons[cd.pair.id].id,
                company_id=app_comparisons[cd.pair.id].company_id,
                is_latest_for_company=app_comparisons[cd.pair.id].is_latest_for_company,
                metrics=comparison_metrics_by_source[cd.pair.id],
            )
            for cd in snapshot.comparisons
            if cd.pair.id in app_comparisons
        ]
        ranked_items = rank_discovery_items(discovery_candidates)
        comparisons_by_app_id = {c.id: c for c in app_comparisons.values()}
        for item in ranked_items:
            quality_scope = _CANDIDATE_QUALITY_SCOPE[item.discovery_type]
            comparison = comparisons_by_app_id[item.report_comparison_id]
            quality_label = {
                "feature": labels.quality_label("GOOD", "generic"),
                "report_side": comparison.report_side_quality_label,
                "alignment_change": comparison.alignment_change_quality_label,
            }[quality_scope]
            app_session.add(
                DiscoveryItem(
                    id=labels.derive_id(
                        pv, "discovery_items", item.discovery_type, item.rank_scope, str(item.report_comparison_id)
                    ),
                    publication_id=pub_id,
                    company_id=item.company_id,
                    report_comparison_id=item.report_comparison_id,
                    discovery_type=item.discovery_type,
                    rank_scope=item.rank_scope,
                    score=item.score,
                    rank=item.rank,
                    percentile=item.percentile,
                    finding_key=item.finding_key,
                    supporting_metric_key=item.supporting_metric_key,
                    supporting_value=item.supporting_value,
                    supporting_unit=item.supporting_unit,
                    quality_label=quality_label or "Analysis ready",
                )
            )

        app_session.flush()

        return {
            "company_count": len(app_companies),
            "report_count": len(app_reports),
            "comparison_count": len(app_comparisons),
            "passage_count": len(app_passages),
            "passage_comparison_count": passage_comparison_count,
            "language_metric_count": language_metric_count,
            "passage_language_signal_count": passage_language_signal_count,
            "discovery_item_count": len(ranked_items),
            "qa_chunk_count": qa_chunk_count,
            "qa_chunk_passage_mapping_count": qa_chunk_passage_mapping_count,
        }


def activate_publication(app_session: Session, publication_id: uuid.UUID) -> None:
    """Atomically supersede the prior ACTIVE publication and activate this
    one. Refuses unless the target is READY."""
    publication = app_session.get(Publication, publication_id)
    if publication is None:
        raise ValueError(f"no publication with id {publication_id}")
    if publication.status != PublicationStatus.READY.value:
        raise ValueError(f"publication {publication_id} is {publication.status}, not READY -- cannot activate")

    state = app_session.get(ApplicationState, "active")
    if state is None:
        state = ApplicationState(singleton_key="active", active_publication_id=None)
        app_session.add(state)
        app_session.flush()

    if state.active_publication_id is not None:
        prior = app_session.get(Publication, state.active_publication_id)
        if prior is not None and prior.status == PublicationStatus.ACTIVE.value:
            prior.status = PublicationStatus.SUPERSEDED.value

    publication.status = PublicationStatus.ACTIVE.value
    publication.activated_at = datetime.now(timezone.utc)
    state.active_publication_id = publication.id
    app_session.flush()


def cleanup_publications(app_session: Session, keep: int = 2, dry_run: bool = False) -> list[Publication]:
    """Delete FAILED and old SUPERSEDED publications, retaining ACTIVE and
    the latest `keep` successful (READY/ACTIVE/SUPERSEDED) publications by
    `completed_at`. Never deletes ACTIVE."""
    all_pubs = list(app_session.scalars(select(Publication).order_by(Publication.completed_at.desc())))
    successful = [p for p in all_pubs if p.status in (PublicationStatus.READY.value, PublicationStatus.ACTIVE.value, PublicationStatus.SUPERSEDED.value)]
    keep_ids = {p.id for p in successful[:keep]}
    active_ids = {p.id for p in all_pubs if p.status == PublicationStatus.ACTIVE.value}

    to_delete = [p for p in all_pubs if p.id not in keep_ids and p.id not in active_ids]
    if not dry_run:
        for p in to_delete:
            app_session.execute(delete(Publication).where(Publication.id == p.id))
        app_session.flush()
    return to_delete
