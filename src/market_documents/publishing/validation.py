"""Post-publish validation. Collects every failure into one summary rather
than raising on the first, mirroring the project's existing "never leave a
run silently half-written, surface every reason" idiom (`ExtractionOutcome`,
`AlignmentOutcome`, etc.).

`validate_persisted` works entirely from what is already written to the app
database for one `publication_id` -- no research-database access required --
so it can run both inline right after a build (before the publication is
marked READY) and standalone later via `market-documents publish validate`.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.publishing import labels
from market_documents.publishing.models import (
    Company,
    DiscoveryItem,
    MetricDefinition,
    Passage,
    PassageComparison,
    Report,
    ReportComparison,
)


@dataclass(frozen=True)
class ValidationFailure:
    check: str
    detail: str


@dataclass
class ValidationSummary:
    checks_run: int = 0
    failures: list[ValidationFailure] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks_run": self.checks_run,
            "failures": [{"check": f.check, "detail": f.detail} for f in self.failures],
        }


_MATCHED_STATUSES = frozenset({"UNCHANGED", "LIGHTLY_MODIFIED", "SUBSTANTIALLY_MODIFIED"})


def validate_persisted(app_session: Session, publication_id: uuid.UUID) -> ValidationSummary:
    summary = ValidationSummary()

    def check(name: str, condition: bool, detail: str = "") -> None:
        summary.checks_run += 1
        if not condition:
            summary.failures.append(ValidationFailure(name, detail))

    companies = list(app_session.scalars(select(Company).where(Company.publication_id == publication_id)))
    reports = list(app_session.scalars(select(Report).where(Report.publication_id == publication_id)))
    comparisons = list(
        app_session.scalars(select(ReportComparison).where(ReportComparison.publication_id == publication_id))
    )
    passages = list(app_session.scalars(select(Passage).where(Passage.publication_id == publication_id)))
    passage_comparisons = list(
        app_session.scalars(select(PassageComparison).where(PassageComparison.publication_id == publication_id))
    )
    discovery_items = list(
        app_session.scalars(select(DiscoveryItem).where(DiscoveryItem.publication_id == publication_id))
    )
    metric_defs = {
        m.metric_key
        for m in app_session.scalars(select(MetricDefinition).where(MetricDefinition.publication_id == publication_id))
    }

    reports_by_company: dict[uuid.UUID, list[Report]] = defaultdict(list)
    for r in reports:
        reports_by_company[r.company_id].append(r)
    for c in companies:
        check("company_has_report", len(reports_by_company.get(c.id, [])) > 0, f"company {c.ticker}")

    check(
        "no_duplicate_source_company_id",
        len({c.source_company_id for c in companies}) == len(companies),
    )
    check("no_duplicate_source_report_id", len({r.source_report_id for r in reports}) == len(reports))
    check(
        "no_duplicate_source_pair_id",
        len({c.source_report_pair_id for c in comparisons}) == len(comparisons),
    )
    check(
        "no_duplicate_source_alignment_id",
        len({pc.source_alignment_id for pc in passage_comparisons}) == len(passage_comparisons),
    )

    reports_by_id = {r.id: r for r in reports}
    for comp in comparisons:
        earlier = reports_by_id.get(comp.earlier_report_id)
        later = reports_by_id.get(comp.later_report_id)
        check("comparison_reports_exist", earlier is not None and later is not None, str(comp.id))
        if earlier is not None and later is not None:
            check(
                "comparison_same_company",
                earlier.company_id == comp.company_id == later.company_id,
                str(comp.id),
            )
        if comp.earlier_period_end is not None and comp.later_period_end is not None:
            check("comparison_period_order", comp.earlier_period_end < comp.later_period_end, str(comp.id))

    comps_by_company: dict[uuid.UUID, list[ReportComparison]] = defaultdict(list)
    for comp in comparisons:
        comps_by_company[comp.company_id].append(comp)
    for company_id, comps in comps_by_company.items():
        indices = sorted(c.chronological_index for c in comps)
        check("chronological_index_contiguous", indices == list(range(len(comps))), str(company_id))
        latest_flags = [c for c in comps if c.is_latest_for_company]
        check("exactly_one_latest_per_company", len(latest_flags) == 1, str(company_id))

    check(
        "no_excluded_categories_published",
        all(p.structured_content_category not in labels.PUBLICATION_EXCLUDED_CATEGORIES for p in passages),
    )
    check(
        "search_vectors_populated",
        all(p.search_vector is not None for p in passages),
    )

    for pc in passage_comparisons:
        check(
            "passage_comparison_one_side_present",
            pc.earlier_passage_id is not None or pc.later_passage_id is not None,
            str(pc.id),
        )
        if pc.alignment_status == "NEW":
            check("new_has_no_earlier_passage", pc.earlier_passage_id is None, str(pc.id))
        elif pc.alignment_status == "REMOVED":
            check("removed_has_no_later_passage", pc.later_passage_id is None, str(pc.id))
        elif pc.alignment_status in _MATCHED_STATUSES:
            check(
                "matched_status_has_both_sides",
                pc.earlier_passage_id is not None and pc.later_passage_id is not None,
                str(pc.id),
            )

    discovery_groups: dict[tuple, list[DiscoveryItem]] = defaultdict(list)
    for item in discovery_items:
        scope_key = item.company_id if item.rank_scope == "company_history" else None
        discovery_groups[(item.discovery_type, item.rank_scope, scope_key)].append(item)
    for key, items in discovery_groups.items():
        ranks = sorted(i.rank for i in items)
        check("discovery_rank_contiguous", ranks == list(range(1, len(items) + 1)), str(key))

    used_metric_keys = {item.supporting_metric_key for item in discovery_items}
    for metric_key in used_metric_keys:
        check("metric_definition_exists_for_discovery", metric_key in metric_defs, metric_key)

    valid_report_side_labels = set(labels.REPORT_SIDE_QUALITY_LABELS.values())
    valid_alignment_labels = set(labels.ALIGNMENT_CHANGE_QUALITY_LABELS.values())
    for comp in comparisons:
        if comp.report_side_quality_label is not None:
            check(
                "report_side_quality_label_in_vocabulary",
                comp.report_side_quality_label in valid_report_side_labels,
                comp.report_side_quality_label,
            )
        if comp.alignment_change_quality_label is not None:
            check(
                "alignment_change_quality_label_in_vocabulary",
                comp.alignment_change_quality_label in valid_alignment_labels,
                comp.alignment_change_quality_label,
            )
        if comp.report_side_primary_eligible and comp.report_side_quality is not None:
            check(
                "report_side_primary_eligible_implies_ok_quality",
                comp.report_side_quality in ("GOOD", "USABLE"),
                str(comp.id),
            )
        if comp.alignment_change_primary_eligible and comp.alignment_change_quality is not None:
            check(
                "alignment_change_primary_eligible_implies_ok_quality",
                comp.alignment_change_quality in ("GOOD", "USABLE"),
                str(comp.id),
            )

    # --- Disclosure-change quality (Milestone 7A.1 follow-up: review-
    # qualified disclosure-change publication) ---
    valid_generic_labels = set(labels.GENERIC_QUALITY_LABELS.values())
    for comp in comparisons:
        check(
            "disclosure_change_quality_always_present",
            comp.disclosure_change_quality is not None,
            str(comp.id),
        )
        if comp.disclosure_change_quality_label is not None:
            check(
                "disclosure_change_quality_label_in_vocabulary",
                comp.disclosure_change_quality_label in valid_generic_labels,
                comp.disclosure_change_quality_label,
            )
        if comp.disclosure_change_quality == "FAILED":
            check(
                "disclosure_change_failed_quality_implies_no_displayed_score",
                comp.disclosure_change_score is None,
                str(comp.id),
            )
        if comp.disclosure_change_primary_eligible and comp.disclosure_change_quality is not None:
            check(
                "disclosure_change_primary_eligible_implies_ok_quality",
                comp.disclosure_change_quality in ("GOOD", "USABLE"),
                str(comp.id),
            )

    # Feature-quality-gated discovery types must never rank a non-primary-
    # eligible comparison, regardless of how permissively the score itself
    # is displayed on the comparison row.
    comparisons_by_id = {comp.id: comp for comp in comparisons}
    feature_gated_discovery_types = {"largest_overall_change", "largest_new_disclosure_share"}
    for item in discovery_items:
        if item.discovery_type not in feature_gated_discovery_types:
            continue
        comp = comparisons_by_id.get(item.report_comparison_id)
        check(
            "feature_gated_discovery_excludes_non_primary_eligible",
            comp is not None and bool(comp.disclosure_change_primary_eligible),
            f"{item.discovery_type}:{item.report_comparison_id}",
        )

    return summary
