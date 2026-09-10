"""Milestone 7 Section 11: passage-quality review subset.

Independently samples ~100 passages (not passage *pairs*) from the same
frozen current corpus, for a reviewer to rate whether the canonical passage
itself is a coherent analytical unit -- a different construct from
correspondence or change classification. Deliberately draws from the same
current-run-resolved population as `human_validation_sampling.py` (see that
module's docstring for the resolution chain), stratified by company and
`passage_type` so the subset isn't dominated by one report style.
"""

import random
from dataclasses import dataclass, fields

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.company import Company
from market_documents.models.passage import Passage
from market_documents.models.report_pair import ReportPair
from market_documents.services.human_validation_sampling import _diversified_pick, _page_range
from market_documents.services.passage_alignment import get_current_alignment_runs_by_pair

DEFAULT_SEED = 20260910
DEFAULT_TARGET = 100


@dataclass
class QualityReviewCase:
    case_id: str
    company: str
    report_pdf_path: str
    passage_id: str
    heading: str | None
    page: str | None
    passage_type: str
    text: str
    quality_rating: str = ""
    reviewer_id: str = ""
    notes: str = ""


def build_quality_sample(
    session: Session, *, seed: int = DEFAULT_SEED, target: int = DEFAULT_TARGET
) -> list[QualityReviewCase]:
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
    ).all()
    pairs_by_id = {p.id: p for p in pairs}
    current_runs = get_current_alignment_runs_by_pair(session, list(pairs_by_id))
    if not current_runs:
        return []

    segmentation_run_ids: set = set()
    ticker_by_report_id: dict = {}
    pdf_by_report_id: dict = {}
    for pair_id, run in current_runs.items():
        pair = pairs_by_id[pair_id]
        segmentation_run_ids.add(run.earlier_segmentation_run_id)
        segmentation_run_ids.add(run.later_segmentation_run_id)
        ticker_by_report_id[pair.earlier_report_id] = pair.company.ticker
        ticker_by_report_id[pair.later_report_id] = pair.company.ticker
        pdf_by_report_id[pair.earlier_report_id] = pair.earlier_report.local_path
        pdf_by_report_id[pair.later_report_id] = pair.later_report.local_path

    passages = session.scalars(
        select(Passage).where(
            Passage.segmentation_run_id.in_(segmentation_run_ids), Passage.excluded_from_alignment.is_(False)
        )
    ).all()

    rng = random.Random(seed)
    picked = _diversified_pick(
        rng,
        list(passages),
        lambda p: f"{ticker_by_report_id.get(p.report_id, 'UNKNOWN')}:{p.passage_type.value}",
        target,
    )

    cases = []
    for i, p in enumerate(picked, start=1):
        cases.append(
            QualityReviewCase(
                case_id=f"M7-QUALITY-{i:04d}",
                company=ticker_by_report_id.get(p.report_id, "UNKNOWN"),
                report_pdf_path=pdf_by_report_id.get(p.report_id, ""),
                passage_id=str(p.id),
                heading=p.heading_text,
                page=_page_range(p),
                passage_type=p.passage_type.value,
                text=p.raw_text,
            )
        )
    return cases


def write_quality_sample_csv(cases: list[QualityReviewCase], output_path) -> None:
    import csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(QualityReviewCase)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in cases:
            writer.writerow(vars(c))
