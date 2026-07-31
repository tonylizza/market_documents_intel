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
    APP_EMBEDDING_DIMENSION,
    Company,
    DiscoveryItem,
    MetricDefinition,
    Passage,
    PassageComparison,
    PassageLanguageSignal,
    Report,
    ReportComparison,
)
from market_documents.publishing.models import PassageEmbedding as AppPassageEmbedding
from market_documents.publishing.models import QaChunk, QaChunkPassage
from market_documents.publishing.models import (
    RetrievalContext,
    RetrievalContextLanguageCategory,
    RetrievalContextRiskSubcategory,
)
from market_documents.publishing.retrieval_contexts import embedding_text_hash as compute_embedding_text_hash
from market_documents.publishing.retrieval_contexts import vector_norm_nonzero


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

# Milestone 7B.1 embedding-coverage policy: the research embedding pipeline
# skips (never truncates) any passage whose token count exceeds the model's
# maximum (currently 512) -- a deliberate, documented research-side choice
# (see `services/passage_embedding.py::_run_embedding`), not a lineage bug.
# On the real corpus this affects a small, real minority of passages
# (measured at publish time: ~1% -- see `publication_embedding_missing_
# audit.csv`). Rather than either (a) hard-failing on every single missing
# embedding, which would make semantic-search coverage all-or-nothing and
# block promotion over a handful of unusually long passages, or (b) silently
# ignoring the gap, this threshold requires the *aggregate* coverage to stay
# high while always recording every individual gap in the audit CSV for
# human review. 95% is a genuine quality floor with real headroom below the
# ~99% actually observed -- not fitted to this run's exact numbers.
MINIMUM_EMBEDDING_COVERAGE = 0.95


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

    # --- Milestone 7B.1: passage embeddings ---
    embeddings = list(
        app_session.scalars(
            select(AppPassageEmbedding).where(AppPassageEmbedding.publication_id == publication_id)
        )
    )
    embedding_by_passage_id = {e.passage_id: e for e in embeddings}
    passages_by_id = {p.id: p for p in passages}

    check(
        "no_duplicate_passage_embeddings",
        len({(e.passage_id, e.embedding_model, e.embedding_model_revision) for e in embeddings})
        == len(embeddings),
    )
    missing_embedding_count = sum(1 for p in passages if p.id not in embedding_by_passage_id)
    embedding_coverage = 1.0 - (missing_embedding_count / len(passages)) if passages else 1.0
    check(
        "embedding_coverage_meets_minimum",
        len(passages) == 0 or embedding_coverage >= MINIMUM_EMBEDDING_COVERAGE,
        f"{missing_embedding_count}/{len(passages)} passages missing a current source embedding "
        f"({embedding_coverage:.4f} coverage, minimum {MINIMUM_EMBEDDING_COVERAGE})",
    )
    for e in embeddings:
        check("passage_embedding_references_published_passage", e.passage_id in passages_by_id, str(e.id))
        check(
            "passage_embedding_dimensions_match_configured_column",
            e.dimensions == APP_EMBEDDING_DIMENSION == len(e.embedding),
            str(e.id),
        )
        check("passage_embedding_vector_not_zero", vector_norm_nonzero(e.embedding), str(e.id))
        app_passage = passages_by_id.get(e.passage_id)
        if app_passage is not None:
            check(
                "passage_embedding_text_hash_self_consistent",
                e.embedding_text_hash == compute_embedding_text_hash(app_passage.text),
                str(e.id),
            )

    # --- Milestone 7B.1: retrieval contexts ---
    contexts = list(
        app_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == publication_id))
    )
    passage_comparisons_by_id = {pc.id: pc for pc in passage_comparisons}
    check(
        "no_duplicate_retrieval_contexts",
        len(
            {
                (ctx.passage_id, ctx.passage_comparison_id, ctx.report_side, ctx.context_type)
                for ctx in contexts
            }
        )
        == len(contexts),
    )
    for ctx in contexts:
        check("retrieval_context_references_published_passage", ctx.passage_id in passages_by_id, str(ctx.id))
        embedding = embedding_by_passage_id.get(ctx.passage_id)
        check(
            "retrieval_context_references_published_embedding",
            embedding is not None and ctx.passage_embedding_id == embedding.id,
            str(ctx.id),
        )
        if ctx.context_type == "REPORT_ONLY":
            check(
                "report_only_context_has_no_comparison_fields",
                ctx.passage_comparison_id is None
                and ctx.report_comparison_id is None
                and ctx.report_side is None,
                str(ctx.id),
            )
            continue

        check("comparison_linked_context_has_report_side", ctx.report_side in ("EARLIER", "LATER"), str(ctx.id))
        pc = passage_comparisons_by_id.get(ctx.passage_comparison_id)
        check(
            "comparison_linked_context_references_published_passage_comparison",
            pc is not None,
            str(ctx.id),
        )
        if pc is None:
            continue
        side_passage_id = pc.earlier_passage_id if ctx.report_side == "EARLIER" else pc.later_passage_id
        check(
            "retrieval_context_side_matches_passage_comparison_side",
            ctx.passage_id == side_passage_id,
            str(ctx.id),
        )
        if pc.alignment_status == "NEW":
            check("new_context_is_later_side", ctx.report_side == "LATER", str(ctx.id))
        elif pc.alignment_status == "REMOVED":
            check("removed_context_is_earlier_side", ctx.report_side == "EARLIER", str(ctx.id))
        comp = comparisons_by_id.get(ctx.report_comparison_id)
        check(
            "retrieval_context_quality_matches_parent_comparison",
            comp is not None
            and ctx.report_side_quality == comp.report_side_quality
            and ctx.alignment_change_quality == comp.alignment_change_quality
            and ctx.irregular_gap_flag == comp.is_irregular_gap,
            str(ctx.id),
        )

    # --- Milestone 7B.1: retrieval-context categories agree with published
    # passage-language signals for the same (passage_comparison_id, side) ---
    signals = list(
        app_session.scalars(
            select(PassageLanguageSignal).where(PassageLanguageSignal.publication_id == publication_id)
        )
    )
    nonzero_categories_by_scope: dict[tuple, set[str]] = defaultdict(set)
    nonzero_risk_subcats_by_scope: dict[tuple, set[str]] = defaultdict(set)
    for s in signals:
        if s.adjusted_count <= 0:
            continue
        scope = (s.passage_comparison_id, s.report_side)
        nonzero_categories_by_scope[scope].add(s.category)
        if s.category == "risk" and s.subcategory is not None:
            nonzero_risk_subcats_by_scope[scope].add(s.subcategory)

    context_ids = {ctx.id for ctx in contexts}
    categories = list(
        app_session.scalars(
            select(RetrievalContextLanguageCategory).where(
                RetrievalContextLanguageCategory.publication_id == publication_id
            )
        )
    )
    risk_subcats = list(
        app_session.scalars(
            select(RetrievalContextRiskSubcategory).where(
                RetrievalContextRiskSubcategory.publication_id == publication_id
            )
        )
    )
    categories_by_context: dict[uuid.UUID, set[str]] = defaultdict(set)
    for c in categories:
        check("retrieval_context_category_references_published_context", c.retrieval_context_id in context_ids, str(c.id))
        categories_by_context[c.retrieval_context_id].add(c.category)
    risk_subcats_by_context: dict[uuid.UUID, set[str]] = defaultdict(set)
    for rs in risk_subcats:
        check(
            "retrieval_context_risk_subcategory_references_published_context",
            rs.retrieval_context_id in context_ids,
            str(rs.id),
        )
        risk_subcats_by_context[rs.retrieval_context_id].add(rs.subcategory)

    for ctx in contexts:
        if ctx.context_type != "COMPARISON_LINKED":
            continue
        scope = (ctx.passage_comparison_id, ctx.report_side)
        check(
            "retrieval_context_language_categories_match_passage_language_signals",
            categories_by_context.get(ctx.id, set()) == nonzero_categories_by_scope.get(scope, set()),
            str(ctx.id),
        )
        check(
            "retrieval_context_risk_subcategories_match_passage_language_signals",
            risk_subcats_by_context.get(ctx.id, set()) == nonzero_risk_subcats_by_scope.get(scope, set()),
            str(ctx.id),
        )

    # --- Milestone 7B.2: Q&A retrieval chunks ---
    qa_chunks = list(app_session.scalars(select(QaChunk).where(QaChunk.publication_id == publication_id)))
    qa_chunk_passages = list(
        app_session.scalars(select(QaChunkPassage).where(QaChunkPassage.publication_id == publication_id))
    )
    qa_chunks_by_id = {c.id: c for c in qa_chunks}

    check(
        "no_duplicate_qa_chunk_index",
        len({(c.publication_id, c.report_id, c.chunk_index) for c in qa_chunks}) == len(qa_chunks),
    )
    hashes_by_report: dict[uuid.UUID, set[str]] = defaultdict(set)
    for c in qa_chunks:
        check("qa_chunk_references_published_report", c.report_id in reports_by_id, str(c.id))
        report = reports_by_id.get(c.report_id)
        if report is not None:
            # Zero cross-report chunks: a chunk's company must match its own
            # report's company -- `build_qa_chunks` only ever sees one
            # report's passages per call, so any mismatch here would mean a
            # publisher wiring bug, not a chunking-algorithm bug.
            check("qa_chunk_company_matches_report_company", c.company_id == report.company_id, str(c.id))
        check("qa_chunk_page_range_valid", c.page_start <= c.page_end, str(c.id))
        check(
            "qa_chunk_dimensions_match_configured_column",
            c.dimensions == APP_EMBEDDING_DIMENSION == len(c.embedding),
            str(c.id),
        )
        check("qa_chunk_vector_not_zero", vector_norm_nonzero(c.embedding), str(c.id))
        check(
            "qa_chunk_embedding_text_hash_self_consistent",
            c.embedding_text_hash == compute_embedding_text_hash(c.text),
            str(c.id),
        )
        check(
            "no_duplicate_qa_chunk_text_hash_within_report",
            c.embedding_text_hash not in hashes_by_report[c.report_id],
            str(c.id),
        )
        hashes_by_report[c.report_id].add(c.embedding_text_hash)

    mapping_counts_by_chunk: dict[uuid.UUID, int] = defaultdict(int)
    for m in qa_chunk_passages:
        check("qa_chunk_passage_references_published_chunk", m.qa_chunk_id in qa_chunks_by_id, str(m.id))
        check("qa_chunk_passage_references_published_passage", m.passage_id in passages_by_id, str(m.id))
        chunk = qa_chunks_by_id.get(m.qa_chunk_id)
        passage = passages_by_id.get(m.passage_id)
        if chunk is not None and passage is not None:
            # No orphan mappings across a report boundary either: a chunk's
            # member passage must belong to the same report as the chunk.
            check("qa_chunk_passage_same_report", chunk.report_id == passage.report_id, str(m.id))
        mapping_counts_by_chunk[m.qa_chunk_id] += 1

    for c in qa_chunks:
        check(
            "qa_chunk_has_complete_source_lineage",
            mapping_counts_by_chunk.get(c.id, 0) > 0,
            str(c.id),
        )

    return summary
