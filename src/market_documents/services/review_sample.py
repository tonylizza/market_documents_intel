"""Deterministic manual-review sampling across all current alignment results.

Passage text is included only when the caller explicitly asks for it
(`include_text=True`) -- the default export is safe to inspect or share
without leaking report content. Never commit an `include_text=True` export.
"""

import csv
import random
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.alignment import PassageAlignment
from market_documents.models.company import Company
from market_documents.models.enums import AlignmentConfidence, AlignmentStatus
from market_documents.models.passage import Passage
from market_documents.models.report_pair import ReportPair
from market_documents.services.alignment_config import ALIGNMENT_CONFIG
from market_documents.services.passage_alignment import get_current_alignment_runs_by_pair

DEFAULT_SEED = 42
DEFAULT_PER_CATEGORY = 3


@dataclass
class ReviewSampleRow:
    category: str
    ticker: str
    report_pair_id: str
    gap_months: int
    is_transition: bool
    earlier_passage_id: str | None
    later_passage_id: str | None
    earlier_page_range: str | None
    later_page_range: str | None
    alignment_status: str
    alignment_type: str
    confidence: str
    semantic_similarity: float | None
    lexical_cosine_similarity: float | None
    jaccard_similarity: float | None
    edit_similarity: float | None
    heading_similarity: float | None
    length_ratio: float | None
    combined_score: float | None
    review_reason: str | None
    earlier_text: str | None = None
    later_text: str | None = None


def _page_range(passage: Passage | None) -> str | None:
    if passage is None:
        return None
    if passage.first_page_number == passage.last_page_number:
        return str(passage.first_page_number)
    return f"{passage.first_page_number}-{passage.last_page_number}"


def _category_predicates(irregular_gap_threshold: int) -> dict[str, Callable[[PassageAlignment, ReportPair], bool]]:
    return {
        "high_confidence_unchanged": lambda a, p: a.alignment_status == AlignmentStatus.UNCHANGED and a.confidence == AlignmentConfidence.HIGH,
        "lightly_modified": lambda a, p: a.alignment_status == AlignmentStatus.LIGHTLY_MODIFIED,
        "substantially_modified": lambda a, p: a.alignment_status == AlignmentStatus.SUBSTANTIALLY_MODIFIED,
        "high_semantic_low_lexical": lambda a, p: bool(a.review_reason) and "paraphrase" in a.review_reason,
        "low_semantic_high_lexical": lambda a, p: bool(a.review_reason) and "boilerplate" in a.review_reason,
        "new": lambda a, p: a.alignment_status == AlignmentStatus.NEW,
        "removed": lambda a, p: a.alignment_status == AlignmentStatus.REMOVED,
        "ambiguous": lambda a, p: a.alignment_status == AlignmentStatus.AMBIGUOUS,
        "likely_split_merge": lambda a, p: bool(a.review_reason) and ("split" in a.review_reason or "merge" in a.review_reason),
        "repeated_boilerplate": lambda a, p: (
            a.alignment_status == AlignmentStatus.UNCHANGED
            and a.lexical_cosine_similarity is not None
            and a.lexical_cosine_similarity >= 0.98
        ),
        "irregular_gap_pair": lambda a, p: p.gap_months > irregular_gap_threshold,
    }


def build_review_sample(
    session: Session,
    *,
    seed: int = DEFAULT_SEED,
    per_category: int = DEFAULT_PER_CATEGORY,
    include_text: bool = False,
) -> list[ReviewSampleRow]:
    """Deterministic, seeded sample of alignment results for manual review.

    Each category is sampled independently (an alignment can appear in more
    than one category, e.g. an irregular-gap pair's UNCHANGED match). Uses a
    plain `random.Random(seed)` shuffle-then-take, so the same corpus state
    always produces the same sample.
    """
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
    ).all()
    pairs_by_id = {p.id: p for p in pairs}
    current_runs = get_current_alignment_runs_by_pair(session, list(pairs_by_id))
    run_ids = [run.id for run in current_runs.values()]
    run_by_pair_id = {pair_id: run.id for pair_id, run in current_runs.items()}
    run_id_to_pair_id = {run_id: pair_id for pair_id, run_id in run_by_pair_id.items()}

    if not run_ids:
        return []

    alignments = session.scalars(
        select(PassageAlignment).where(PassageAlignment.alignment_run_id.in_(run_ids))
    ).all()

    passage_ids = {a.earlier_passage_id for a in alignments if a.earlier_passage_id} | {
        a.later_passage_id for a in alignments if a.later_passage_id
    }
    passages_by_id = {
        p.id: p for p in session.scalars(select(Passage).where(Passage.id.in_(passage_ids))).all()
    } if passage_ids else {}

    predicates = _category_predicates(ALIGNMENT_CONFIG.irregular_gap_months_threshold)
    rng = random.Random(seed)

    rows: list[ReviewSampleRow] = []
    for category, predicate in predicates.items():
        matches = [
            a for a in alignments if predicate(a, pairs_by_id[run_id_to_pair_id[a.alignment_run_id]])
        ]
        matches_sorted = sorted(matches, key=lambda a: str(a.id))  # stable order before seeded shuffle
        rng.shuffle(matches_sorted)
        for alignment in matches_sorted[:per_category]:
            pair = pairs_by_id[run_id_to_pair_id[alignment.alignment_run_id]]
            earlier_passage = passages_by_id.get(alignment.earlier_passage_id) if alignment.earlier_passage_id else None
            later_passage = passages_by_id.get(alignment.later_passage_id) if alignment.later_passage_id else None
            rows.append(
                ReviewSampleRow(
                    category=category,
                    ticker=pair.company.ticker,
                    report_pair_id=str(pair.id),
                    gap_months=pair.gap_months,
                    is_transition=pair.is_transition,
                    earlier_passage_id=str(alignment.earlier_passage_id) if alignment.earlier_passage_id else None,
                    later_passage_id=str(alignment.later_passage_id) if alignment.later_passage_id else None,
                    earlier_page_range=_page_range(earlier_passage),
                    later_page_range=_page_range(later_passage),
                    alignment_status=alignment.alignment_status.value,
                    alignment_type=alignment.alignment_type.value,
                    confidence=alignment.confidence.value,
                    semantic_similarity=alignment.semantic_similarity,
                    lexical_cosine_similarity=alignment.lexical_cosine_similarity,
                    jaccard_similarity=alignment.jaccard_similarity,
                    edit_similarity=alignment.edit_similarity,
                    heading_similarity=alignment.heading_similarity,
                    length_ratio=alignment.length_ratio,
                    combined_score=alignment.combined_score,
                    review_reason=alignment.review_reason,
                    earlier_text=(earlier_passage.raw_text if include_text and earlier_passage else None),
                    later_text=(later_passage.raw_text if include_text and later_passage else None),
                )
            )
    return rows


def write_review_sample_csv(rows: list[ReviewSampleRow], output_path: Path) -> None:
    """Write the review sample to CSV. Callers must never commit an export
    written with `include_text=True` passed to `build_review_sample`."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(ReviewSampleRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))
