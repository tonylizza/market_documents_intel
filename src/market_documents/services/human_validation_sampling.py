"""Milestone 7 human-labeled construct-validation sample builder.

Builds a fixed, reproducible, stratified sample of passage-level cases for
blind human review of the *frozen* alignment pipeline (see
`docs/oversized-passage-retrieval-subchunks-experiment.md`, Section 20:
ACCEPT AND FREEZE). This module reads the corpus; it never touches
extraction, segmentation, embedding, candidate generation, or alignment
logic, and must not be changed in response to validation findings during
this milestone.

Current-run resolution follows the same chain every other current-run
consumer uses -- `ReportPair` -> `get_current_alignment_runs_by_pair`
(itself `completed_at DESC LIMIT 1` per pair, filtered to
COMPLETED/COMPLETED_WITH_WARNINGS) -- exactly as `review_sample.py` and the
`pairs review-sample` CLI already do. This deliberately reuses that
resolution rather than a fresh join, per the corrected-population rule in
`docs/oversized-passage-retrieval-subchunks-experiment.md` Section 8.1: a
naive join across every historical `NarrativeDocument`/run generation
previously overcounted eligible passages by ~4x (80,346 vs. the corrected
~21,016).

Sampling scheme (documented here so it is reproducible without reading the
code): for each `AlignmentStatus` bucket, candidates are first grouped by
`AlignmentConfidence`; per-confidence quotas are allocated by a
square-root-weighted largest-remainder method (dampens the largest
confidence bucket's dominance while respecting availability -- an empty
bucket gets zero). Within a confidence bucket, candidates are grouped by
`(ticker, length_bucket)` and drawn round-robin after a seeded shuffle
within each group, so the sample spreads across company and passage length
rather than being dominated by whatever the largest company/length
combination happens to be. `length_bucket` is SHORT (<60 words), MEDIUM
(60-200), LONG (>200), taken from the later passage for matched/NEW cases
and the earlier passage for REMOVED cases.

The AMBIGUOUS/difficult-structural pool additionally includes NEEDS_REVIEW
and ONE_TO_TWO/TWO_TO_ONE alignment types, since Milestone 7's "structural
ambiguity" construct (see the labeling guide) is broader than the single
AMBIGUOUS status value.
"""

import math
import random
import uuid
from dataclasses import dataclass, fields
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.alignment import PassageAlignment
from market_documents.models.company import Company
from market_documents.models.embedding import PassageEmbedding, PassageRetrievalChunk
from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, AlignmentType
from market_documents.models.passage import Passage
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services.alignment_candidates import get_semantic_candidates
from market_documents.services.passage_alignment import get_current_alignment_runs_by_pair
from market_documents.services.passage_embedding import get_current_embedding_run
from market_documents.services.similarity_metrics import lexical_cosine_similarity
from market_documents.services.similarity_tokenization import tokenize

DEFAULT_SEED = 20260910  # date this validation sample was first frozen (2026-09-10)

DEFAULT_TARGET_COUNTS: dict[str, int] = {
    "UNCHANGED": 60,
    "LIGHTLY_MODIFIED": 60,
    "SUBSTANTIALLY_MODIFIED": 60,
    "NEW": 50,
    "REMOVED": 50,
    "AMBIGUOUS": 20,
}

LengthBucket = Literal["SHORT", "MEDIUM", "LONG"]


def _length_bucket(word_count: int) -> LengthBucket:
    if word_count < 60:
        return "SHORT"
    if word_count <= 200:
        return "MEDIUM"
    return "LONG"


def _page_range(passage: Passage | None) -> str | None:
    if passage is None:
        return None
    if passage.first_page_number == passage.last_page_number:
        return str(passage.first_page_number)
    return f"{passage.first_page_number}-{passage.last_page_number}"


@dataclass
class ValidationCase:
    case_id: str
    sample_bucket: str  # UNCHANGED | LIGHTLY_MODIFIED | SUBSTANTIALLY_MODIFIED | NEW | REMOVED | AMBIGUOUS
    company: str
    earlier_report_id: str | None
    later_report_id: str | None
    earlier_report_period_end: str | None
    later_report_period_end: str | None
    earlier_report_pdf_path: str | None
    later_report_pdf_path: str | None
    earlier_passage_id: str | None
    later_passage_id: str | None
    earlier_heading: str | None
    later_heading: str | None
    earlier_page: str | None
    later_page: str | None
    earlier_text: str | None
    later_text: str | None
    earlier_context_before: str | None
    earlier_context_after: str | None
    later_context_before: str | None
    later_context_after: str | None
    # NEW/REMOVED diagnostic alternatives -- see module docstring section on
    # opposite-side candidates. Populated only for sample_bucket NEW/REMOVED.
    opposite_top_lexical_text: str | None
    opposite_top_lexical_heading: str | None
    opposite_top_lexical_page: str | None
    opposite_top_semantic_text: str | None
    opposite_top_semantic_heading: str | None
    opposite_top_semantic_page: str | None
    opposite_nearest_positional_text: str | None
    opposite_nearest_positional_heading: str | None
    opposite_nearest_positional_page: str | None
    # System fields -- omitted entirely from the blinded reviewer export.
    system_alignment_status: str
    system_alignment_type: str
    system_confidence: str
    system_semantic_similarity: float | None
    system_lexical_cosine_similarity: float | None
    system_jaccard_similarity: float | None
    system_edit_similarity: float | None
    system_combined_score: float | None
    system_review_reason: str | None
    # Human-labeling columns -- blank until a reviewer fills them in.
    human_correspondence: str = ""
    human_change: str = ""
    human_significance: str = ""
    human_unmatched_label: str = ""
    reviewer_id: str = ""
    notes: str = ""


BLINDED_FIELDS = [
    "case_id",
    "sample_bucket",
    "company",
    "earlier_report_period_end",
    "later_report_period_end",
    "earlier_report_pdf_path",
    "later_report_pdf_path",
    "earlier_heading",
    "later_heading",
    "earlier_page",
    "later_page",
    "earlier_text",
    "later_text",
    "earlier_context_before",
    "earlier_context_after",
    "later_context_before",
    "later_context_after",
    "opposite_top_lexical_text",
    "opposite_top_lexical_heading",
    "opposite_top_lexical_page",
    "opposite_top_semantic_text",
    "opposite_top_semantic_heading",
    "opposite_top_semantic_page",
    "opposite_nearest_positional_text",
    "opposite_nearest_positional_heading",
    "opposite_nearest_positional_page",
    "human_correspondence",
    "human_change",
    "human_significance",
    "human_unmatched_label",
    "reviewer_id",
    "notes",
]


def _sqrt_weighted_quota(counts: dict[str, int], target: int) -> dict[str, int]:
    """Largest-remainder allocation of `target` across buckets, weighted by
    sqrt(available) so the single largest bucket cannot dominate the sample,
    while a bucket with zero availability always gets zero."""
    nonzero = {k: v for k, v in counts.items() if v > 0}
    if not nonzero:
        return {k: 0 for k in counts}
    weights = {k: math.sqrt(v) for k, v in nonzero.items()}
    total_weight = sum(weights.values())
    raw = {k: target * w / total_weight for k, w in weights.items()}
    floored = {k: min(int(raw[k]), nonzero[k]) for k in nonzero}
    remaining = target - sum(floored.values())
    remainders = sorted(
        nonzero.keys(),
        key=lambda k: (-(raw[k] - int(raw[k])), k),
    )
    i = 0
    while remaining > 0 and any(floored[k] < nonzero[k] for k in nonzero):
        k = remainders[i % len(remainders)]
        if floored[k] < nonzero[k]:
            floored[k] += 1
            remaining -= 1
        i += 1
    return {k: floored.get(k, 0) for k in counts}


def _diversified_pick(rng: random.Random, candidates: list, key_fn, k: int) -> list:
    """Round-robin draw across `key_fn(candidate)` groups after a seeded
    shuffle within each group, so the pick spreads across (company, length
    bucket) rather than favoring whichever group is largest."""
    groups: dict = {}
    for c in candidates:
        groups.setdefault(key_fn(c), []).append(c)
    for group_items in groups.values():
        group_items.sort(key=lambda c: str(c.id))  # stable order before seeded shuffle
        rng.shuffle(group_items)
    group_keys = sorted(groups.keys(), key=str)
    picked = []
    idx = 0
    while len(picked) < k and any(groups[gk] for gk in group_keys):
        gk = group_keys[idx % len(group_keys)]
        if groups[gk]:
            picked.append(groups[gk].pop())
        idx += 1
    return picked


def _context_passage(
    passages_by_run_and_index: dict[tuple[uuid.UUID, int], Passage], passage: Passage | None, offset: int
) -> str | None:
    if passage is None:
        return None
    neighbor = passages_by_run_and_index.get((passage.segmentation_run_id, passage.passage_index + offset))
    if neighbor is None:
        return None
    heading = f"[{neighbor.heading_text}] " if neighbor.heading_text else ""
    return f"{heading}{neighbor.raw_text[:300]}"


def _passage_vector(session: Session, passage: Passage, embedding_run_id: uuid.UUID) -> list[float] | None:
    canonical = session.scalar(
        select(PassageEmbedding.embedding).where(
            PassageEmbedding.embedding_run_id == embedding_run_id, PassageEmbedding.passage_id == passage.id
        )
    )
    if canonical is not None:
        return list(canonical)
    chunk = session.scalar(
        select(PassageRetrievalChunk.embedding)
        .where(
            PassageRetrievalChunk.embedding_run_id == embedding_run_id,
            PassageRetrievalChunk.passage_id == passage.id,
        )
        .order_by(PassageRetrievalChunk.chunk_index)
        .limit(1)
    )
    return list(chunk) if chunk is not None else None


def _opposite_candidates(
    session: Session,
    passage: Passage,
    own_embedding_run_id: uuid.UUID,
    opposite_embedding_run_id: uuid.UUID,
    opposite_passages: list[Passage],
) -> dict[str, Passage | None]:
    """Best lexical, best semantic, and nearest-positional candidate for an
    unmatched (NEW/REMOVED) passage, drawn from the opposite report's
    current eligible population. Diagnostic only -- never exposed as "the
    system's preferred candidate" to the reviewer (see labeling guide)."""
    best_lexical: tuple[float, Passage] | None = None
    own_tokens = tokenize(passage.raw_text)
    for other in opposite_passages:
        score = lexical_cosine_similarity(own_tokens, tokenize(other.raw_text))
        if score is not None and (best_lexical is None or score > best_lexical[0]):
            best_lexical = (score, other)

    best_semantic: Passage | None = None
    vector = _passage_vector(session, passage, own_embedding_run_id)
    if vector is not None:
        matches = get_semantic_candidates(
            session,
            later_embedding_vector=vector,
            earlier_embedding_run_id=opposite_embedding_run_id,
            top_k=1,
            min_semantic_similarity=0.0,
        )
        if matches:
            best_semantic = matches[0].passage

    best_positional: Passage | None = None
    if opposite_passages:
        own_max_index = max((p.passage_index for p in opposite_passages), default=0) or 1
        own_relative = passage.passage_index / (own_max_index or 1)
        best_positional = min(
            opposite_passages,
            key=lambda p: (abs((p.passage_index / (own_max_index or 1)) - own_relative), p.passage_index),
        )

    return {
        "lexical": best_lexical[1] if best_lexical else None,
        "semantic": best_semantic,
        "positional": best_positional,
    }


def build_validation_sample(
    session: Session,
    *,
    seed: int = DEFAULT_SEED,
    target_counts: dict[str, int] | None = None,
) -> tuple[list[ValidationCase], dict[str, int]]:
    """Deterministic, seeded, stratified Milestone 7 validation sample.

    Returns the case list and a dict of {bucket: available_count} so callers
    can report where the corpus could not support the target (see
    `docs/human-construct-validation.md`).
    """
    targets = dict(target_counts or DEFAULT_TARGET_COUNTS)

    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
    ).all()
    pairs_by_id = {p.id: p for p in pairs}
    current_runs = get_current_alignment_runs_by_pair(session, list(pairs_by_id))
    run_id_to_pair_id = {run.id: pair_id for pair_id, run in current_runs.items()}
    run_ids = list(run_id_to_pair_id)
    if not run_ids:
        return [], {k: 0 for k in targets}

    alignments = session.scalars(
        select(PassageAlignment).where(
            PassageAlignment.alignment_run_id.in_(run_ids), PassageAlignment.primary_alignment.is_(True)
        )
    ).all()

    passage_ids = {a.earlier_passage_id for a in alignments if a.earlier_passage_id} | {
        a.later_passage_id for a in alignments if a.later_passage_id
    }
    passages_by_id: dict[uuid.UUID, Passage] = (
        {p.id: p for p in session.scalars(select(Passage).where(Passage.id.in_(passage_ids))).all()}
        if passage_ids
        else {}
    )
    reports_by_id = {
        r.id: r for r in session.scalars(select(Report).where(Report.company_id.in_({p.company_id for p in pairs}))).all()
    }

    # For context passages and opposite-side (NEW/REMOVED) candidates: full
    # eligible population per segmentation run, covering both every run any
    # matched passage belongs to and every run pinned by a current
    # AlignmentRun (so an opposite-side run with zero matched passages in
    # this pair is still available for candidate diagnostics).
    segmentation_run_ids = {p.segmentation_run_id for p in passages_by_id.values()}
    for run in current_runs.values():
        segmentation_run_ids.add(run.earlier_segmentation_run_id)
        segmentation_run_ids.add(run.later_segmentation_run_id)
    all_run_passages = (
        session.scalars(
            select(Passage).where(
                Passage.segmentation_run_id.in_(segmentation_run_ids), Passage.excluded_from_alignment.is_(False)
            )
        ).all()
        if segmentation_run_ids
        else []
    )
    passages_by_run_and_index = {(p.segmentation_run_id, p.passage_index): p for p in all_run_passages}
    passages_by_run: dict[uuid.UUID, list[Passage]] = {}
    for p in all_run_passages:
        passages_by_run.setdefault(p.segmentation_run_id, []).append(p)
    alignment_runs_by_id = {run.id: run for run in current_runs.values()}

    # Bucket alignments.
    buckets: dict[str, list[PassageAlignment]] = {k: [] for k in targets}
    difficult_ids: set[uuid.UUID] = set()
    for a in alignments:
        if a.alignment_status == AlignmentStatus.UNCHANGED:
            buckets["UNCHANGED"].append(a)
        elif a.alignment_status == AlignmentStatus.LIGHTLY_MODIFIED:
            buckets["LIGHTLY_MODIFIED"].append(a)
        elif a.alignment_status == AlignmentStatus.SUBSTANTIALLY_MODIFIED:
            buckets["SUBSTANTIALLY_MODIFIED"].append(a)
        elif a.alignment_status == AlignmentStatus.NEW:
            buckets["NEW"].append(a)
        elif a.alignment_status == AlignmentStatus.REMOVED:
            buckets["REMOVED"].append(a)
        if (
            a.alignment_status == AlignmentStatus.AMBIGUOUS
            or a.confidence == AlignmentConfidence.NEEDS_REVIEW
            or a.alignment_type in (AlignmentType.ONE_TO_TWO, AlignmentType.TWO_TO_ONE)
        ) and a.id not in difficult_ids:
            buckets["AMBIGUOUS"].append(a)
            difficult_ids.add(a.id)

    available_counts = {k: len(v) for k, v in buckets.items()}

    rng = random.Random(seed)
    selected: dict[str, list[PassageAlignment]] = {}
    for bucket, alignment_list in buckets.items():
        by_confidence: dict[str, list[PassageAlignment]] = {}
        for a in alignment_list:
            by_confidence.setdefault(a.confidence.value, []).append(a)
        quota = _sqrt_weighted_quota({k: len(v) for k, v in by_confidence.items()}, min(targets[bucket], len(alignment_list)))
        picked: list[PassageAlignment] = []
        for confidence_value, n in quota.items():
            if n <= 0:
                continue

            def _length_key(a: PassageAlignment) -> str:
                ref = passages_by_id.get(a.later_passage_id) or passages_by_id.get(a.earlier_passage_id)
                ticker = pairs_by_id[run_id_to_pair_id[a.alignment_run_id]].company.ticker
                lb = _length_bucket(ref.word_count) if ref else "MEDIUM"
                return f"{ticker}:{lb}"

            picked.extend(_diversified_pick(rng, by_confidence[confidence_value], _length_key, n))
        selected[bucket] = picked

    cases: list[ValidationCase] = []
    for bucket, alignment_list in selected.items():
        for case_counter, a in enumerate(alignment_list, start=1):
            case_id = f"M7-{bucket}-{case_counter:04d}"
            pair = pairs_by_id[run_id_to_pair_id[a.alignment_run_id]]
            earlier_passage = passages_by_id.get(a.earlier_passage_id) if a.earlier_passage_id else None
            later_passage = passages_by_id.get(a.later_passage_id) if a.later_passage_id else None
            earlier_report = reports_by_id.get(pair.earlier_report_id)
            later_report = reports_by_id.get(pair.later_report_id)

            opp = {"lexical": None, "semantic": None, "positional": None}
            alignment_run = alignment_runs_by_id.get(a.alignment_run_id)
            if bucket == "NEW" and later_passage is not None and alignment_run is not None:
                # Opposite side for a NEW (later) passage is the earlier
                # report's eligible population, from the segmentation run
                # this AlignmentRun actually pinned -- not a fresh lookup,
                # so it matches exactly what alignment scored against.
                opposite_passages = passages_by_run.get(alignment_run.earlier_segmentation_run_id, [])
                if opposite_passages:
                    opp = _opposite_candidates(
                        session,
                        later_passage,
                        alignment_run.later_embedding_run_id,
                        alignment_run.earlier_embedding_run_id,
                        opposite_passages,
                    )
            elif bucket == "REMOVED" and earlier_passage is not None and alignment_run is not None:
                opposite_passages = passages_by_run.get(alignment_run.later_segmentation_run_id, [])
                if opposite_passages:
                    opp = _opposite_candidates(
                        session,
                        earlier_passage,
                        alignment_run.earlier_embedding_run_id,
                        alignment_run.later_embedding_run_id,
                        opposite_passages,
                    )

            def _fmt(p: Passage | None) -> tuple[str | None, str | None, str | None]:
                if p is None:
                    return None, None, None
                return p.raw_text, p.heading_text, _page_range(p)

            opp_lex_text, opp_lex_heading, opp_lex_page = _fmt(opp["lexical"])
            opp_sem_text, opp_sem_heading, opp_sem_page = _fmt(opp["semantic"])
            opp_pos_text, opp_pos_heading, opp_pos_page = _fmt(opp["positional"])

            cases.append(
                ValidationCase(
                    case_id=case_id,
                    sample_bucket=bucket,
                    company=pair.company.ticker,
                    earlier_report_id=str(pair.earlier_report_id),
                    later_report_id=str(pair.later_report_id),
                    earlier_report_period_end=str(earlier_report.period_end) if earlier_report and earlier_report.period_end else None,
                    later_report_period_end=str(later_report.period_end) if later_report and later_report.period_end else None,
                    earlier_report_pdf_path=earlier_report.local_path if earlier_report else None,
                    later_report_pdf_path=later_report.local_path if later_report else None,
                    earlier_passage_id=str(earlier_passage.id) if earlier_passage else None,
                    later_passage_id=str(later_passage.id) if later_passage else None,
                    earlier_heading=earlier_passage.heading_text if earlier_passage else None,
                    later_heading=later_passage.heading_text if later_passage else None,
                    earlier_page=_page_range(earlier_passage),
                    later_page=_page_range(later_passage),
                    earlier_text=earlier_passage.raw_text if earlier_passage else None,
                    later_text=later_passage.raw_text if later_passage else None,
                    earlier_context_before=_context_passage(passages_by_run_and_index, earlier_passage, -1),
                    earlier_context_after=_context_passage(passages_by_run_and_index, earlier_passage, 1),
                    later_context_before=_context_passage(passages_by_run_and_index, later_passage, -1),
                    later_context_after=_context_passage(passages_by_run_and_index, later_passage, 1),
                    opposite_top_lexical_text=opp_lex_text,
                    opposite_top_lexical_heading=opp_lex_heading,
                    opposite_top_lexical_page=opp_lex_page,
                    opposite_top_semantic_text=opp_sem_text,
                    opposite_top_semantic_heading=opp_sem_heading,
                    opposite_top_semantic_page=opp_sem_page,
                    opposite_nearest_positional_text=opp_pos_text,
                    opposite_nearest_positional_heading=opp_pos_heading,
                    opposite_nearest_positional_page=opp_pos_page,
                    system_alignment_status=a.alignment_status.value,
                    system_alignment_type=a.alignment_type.value,
                    system_confidence=a.confidence.value,
                    system_semantic_similarity=a.semantic_similarity,
                    system_lexical_cosine_similarity=a.lexical_cosine_similarity,
                    system_jaccard_similarity=a.jaccard_similarity,
                    system_edit_similarity=a.edit_similarity,
                    system_combined_score=a.combined_score,
                    system_review_reason=a.review_reason,
                )
            )

    return cases, available_counts


def write_full_csv(cases: list[ValidationCase], output_path) -> None:
    import csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(ValidationCase)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in cases:
            writer.writerow(vars(c))


def write_blinded_csv(cases: list[ValidationCase], output_path) -> None:
    """Reviewer-facing export: omits system_* fields entirely (see
    Section 8/13 of the milestone brief -- human labels must not be able to
    reproduce the system's own thresholds)."""
    import csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BLINDED_FIELDS)
        writer.writeheader()
        for c in cases:
            row = {k: v for k, v in vars(c).items() if k in BLINDED_FIELDS}
            writer.writerow(row)
