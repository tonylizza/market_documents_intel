"""Oversized (token-limit-skipped) passage audit.

Mirrors `embedding_audit.py`'s per-report reporting, but at passage
granularity. A passage counts as "oversized-skipped" here if it belongs to
a segmentation run's current successful `EmbeddingRun`, is eligible (not
`excluded_from_alignment`), has no corresponding `PassageEmbedding` row, and
its token count -- recomputed with the pinned embedding model's own
tokenizer, not the segmentation-time lexical tokenizer behind
`Passage.token_count` -- exceeds `MAXIMUM_MODEL_TOKENS`. Passages skipped
for other reasons (an isolated per-passage embedding failure, or a wrong
output dimension) are excluded from this audit; those are integrity issues,
not size issues.

`participates_in_alignment_gap` is `True` when the passage's report side is
covered by a current successful `AlignmentRun` and the passage never
appears as the matched (`ONE_TO_ONE`) side of a `PassageAlignment` row in
it -- an unmatched passage still gets a persisted row (`UNMATCHED_EARLIER`/
`UNMATCHED_LATER`, per `passage_alignment.py`), so "does the passage_id
appear at all" is not sufficient. By construction, an unembedded passage
can never be found as a semantic candidate nor supply one to search with,
so it always becomes a spurious REMOVED (earlier side) or NEW (later side)
classification rather than a real content change. `None` when no alignment
run yet covers that side, so the caller must never read `None` as "no gap."

Rows are ordered deterministically (report directory_year/local_path, then
passage_index) so `cumulative_corpus_word_share` and CSV output are
reproducible across re-runs of an unchanged corpus.
"""

import csv
from dataclasses import dataclass, fields
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.alignment import AlignmentRun, PassageAlignment
from market_documents.models.embedding import PassageEmbedding
from market_documents.models.enums import AlignmentRunStatus, AlignmentType
from market_documents.models.extraction import NarrativeDocument
from market_documents.models.passage import Passage
from market_documents.models.report import Report
from market_documents.services.embedding_config import MAXIMUM_MODEL_TOKENS
from market_documents.services.extraction import get_current_runs_by_report
from market_documents.services.passage_embedding import EmbeddingModel, get_current_embedding_runs_by_segmentation_run
from market_documents.services.passage_segmentation import get_current_segmentation_runs_by_narrative_document


@dataclass
class OversizedPassageAuditRow:
    ticker: str
    report_id: str
    passage_id: str
    passage_type: str
    first_page_number: int
    last_page_number: int
    word_count: int
    token_count: int
    share_of_report_words: float
    participates_in_alignment_gap: bool | None
    cumulative_corpus_word_share: float


def _participates_in_alignment_gap(session: Session, embedding_run_id, passage_id) -> bool | None:
    covering_run_ids = session.scalars(
        select(AlignmentRun.id).where(
            AlignmentRun.status.in_((AlignmentRunStatus.COMPLETED, AlignmentRunStatus.COMPLETED_WITH_WARNINGS)),
            (AlignmentRun.earlier_embedding_run_id == embedding_run_id)
            | (AlignmentRun.later_embedding_run_id == embedding_run_id),
        )
    ).all()
    if not covering_run_ids:
        return None
    matched = session.scalars(
        select(PassageAlignment.id)
        .where(
            PassageAlignment.alignment_run_id.in_(covering_run_ids),
            (PassageAlignment.earlier_passage_id == passage_id) | (PassageAlignment.later_passage_id == passage_id),
            PassageAlignment.alignment_type == AlignmentType.ONE_TO_ONE,
        )
        .limit(1)
    ).first()
    return matched is None


def build_oversized_passage_audit_rows(session: Session, model: EmbeddingModel) -> list[OversizedPassageAuditRow]:
    """`model` recomputes each candidate's exact token count -- the pinned
    embedding model in production, a fake tokenizer in tests -- since only
    the real skip decision's tokenizer is authoritative for the 512-token
    limit that `Passage.token_count` (a different, lexical tokenizer) does
    not represent."""
    reports = session.scalars(select(Report).order_by(Report.directory_year, Report.local_path)).all()
    report_ids = [r.id for r in reports]
    current_extraction_runs = get_current_runs_by_report(session, report_ids)

    extraction_run_ids = [run.id for run in current_extraction_runs.values()]
    narratives = session.scalars(
        select(NarrativeDocument).where(NarrativeDocument.extraction_run_id.in_(extraction_run_ids))
    ).all()
    narrative_by_report_id = {n.report_id: n for n in narratives}

    narrative_ids = [n.id for n in narratives]
    current_segmentation_runs = get_current_segmentation_runs_by_narrative_document(session, narrative_ids)

    segmentation_run_ids = [run.id for run in current_segmentation_runs.values()]
    current_embedding_runs = get_current_embedding_runs_by_segmentation_run(session, segmentation_run_ids)

    corpus_total_words = sum(n.word_count for n in narratives) or 0

    rows: list[OversizedPassageAuditRow] = []
    cumulative_words = 0

    for report in reports:
        narrative = narrative_by_report_id.get(report.id)
        if narrative is None:
            continue
        segmentation_run = current_segmentation_runs.get(narrative.id)
        if segmentation_run is None:
            continue
        embedding_run = current_embedding_runs.get(segmentation_run.id)
        if embedding_run is None:
            continue

        eligible_passages = session.scalars(
            select(Passage)
            .where(Passage.segmentation_run_id == segmentation_run.id, Passage.excluded_from_alignment.is_(False))
            .order_by(Passage.passage_index)
        ).all()
        if not eligible_passages:
            continue

        embedded_passage_ids = set(
            session.scalars(
                select(PassageEmbedding.passage_id).where(PassageEmbedding.embedding_run_id == embedding_run.id)
            ).all()
        )

        for passage in eligible_passages:
            if passage.id in embedded_passage_ids:
                continue
            token_count = model.count_tokens(passage.raw_text)
            if token_count <= MAXIMUM_MODEL_TOKENS:
                continue  # skipped for a different reason (failure/wrong dimension), not size

            gap = _participates_in_alignment_gap(session, embedding_run.id, passage.id)
            cumulative_words += passage.word_count
            rows.append(
                OversizedPassageAuditRow(
                    ticker=report.company.ticker if report.company else "?",
                    report_id=str(report.id),
                    passage_id=str(passage.id),
                    passage_type=passage.passage_type.value,
                    first_page_number=passage.first_page_number,
                    last_page_number=passage.last_page_number,
                    word_count=passage.word_count,
                    token_count=token_count,
                    share_of_report_words=(passage.word_count / narrative.word_count) if narrative.word_count else 0.0,
                    participates_in_alignment_gap=gap,
                    cumulative_corpus_word_share=(
                        cumulative_words / corpus_total_words if corpus_total_words else 0.0
                    ),
                )
            )
    return rows


def write_oversized_passage_audit_csv(rows: list[OversizedPassageAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(OversizedPassageAuditRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))
