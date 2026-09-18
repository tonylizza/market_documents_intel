"""Track 7D.5a reconnaissance-only research script.

Runs a broad heading-candidate inventory across the full corpus (every
company, every report year) for the remaining normalized-schedule
candidates (CEO_REVIEW, CHAIR_REVIEW, STRATEGY, OUTLOOK, LEGAL_REGULATORY,
MATERIAL_MATTERS, OPERATING_ENVIRONMENT). Read-only: it never writes to
`schedule_localization.py`, `schedule_config.py`, or any production table.

Sourced from the canonical PDF representation (Track 7C.1a) via
`source_adapter`, exactly like `schedule_localization.py`'s own heading
detection -- never a separate, divergent heuristic. Falls back to legacy
`TextBlock` HEADING_CANDIDATE rows only when a report has no canonical
extraction run, mirroring 7D.5's own stated method.

Not part of the production CLI. Retained under scripts/ as a research
artifact per 7D.5a's scope note (temporary research scripts are allowed to
be retained under an appropriate research/docs path).
"""

import re
from dataclasses import dataclass

from sqlalchemy import select

from market_documents.db.session import get_session
from market_documents.models.company import Company
from market_documents.models.enums import BlockType
from market_documents.models.extraction import ExtractionRun, Page, TextBlock
from market_documents.models.report import Report
from market_documents.services import source_adapter
from market_documents.services.canonical_extraction import get_current_canonical_run
from market_documents.services.extraction import get_current_extraction_run

TICKERS = ["ACT", "BEL", "KP2", "SBP", "SDL", "SUR"]

# Broad, deliberately over-inclusive keyword families -- recall over
# precision, since this is a screening pass and every hit is reviewed by
# eye, not auto-classified into a schedule.
KEYWORD_FAMILIES: dict[str, list[str]] = {
    "CEO_REVIEW": [
        r"chief executive", r"\bceo\b", r"group ceo",
    ],
    "CHAIR_REVIEW": [
        r"chairman", r"chairperson", r"chair'?s report", r"chair'?s review",
    ],
    "STRATEGY": [
        r"\bstrateg", r"our approach to",
    ],
    "OUTLOOK": [
        r"\boutlook\b", r"looking ahead", r"priorities for", r"prospects\b",
    ],
    "LEGAL_REGULATORY": [
        r"legal proceed", r"litigation", r"regulat", r"compliance matters",
        r"legal and regulatory",
    ],
    "MATERIAL_MATTERS": [
        r"material matters", r"material issues", r"material themes",
        r"materiality",
    ],
    "OPERATING_ENVIRONMENT": [
        r"operating environment", r"macro", r"industry environment",
        r"market conditions", r"external environment",
    ],
}

_PATTERNS = {
    schedule: re.compile("|".join(pats), re.IGNORECASE) for schedule, pats in KEYWORD_FAMILIES.items()
}


@dataclass
class Hit:
    ticker: str
    year: int
    schedule_guesses: list[str]
    heading_text: str
    page_number: int
    source: str  # "canonical" or "legacy_textblock"


def _classify_text(text: str) -> list[str]:
    hits = []
    for schedule, pattern in _PATTERNS.items():
        if pattern.search(text):
            hits.append(schedule)
    return hits


def _canonical_headings(session, report: Report) -> list[tuple[str, int]] | None:
    run = get_current_canonical_run(session, report.id)
    if run is None:
        return None
    pages = source_adapter.load_source_pages(session, run.id)
    classified = source_adapter.classify_source_pages(pages)
    headings = source_adapter.build_heading_blocks(classified)
    return [(h.text, h.page_number) for h in headings]


def _legacy_headings(session, report: Report) -> list[tuple[str, int]]:
    run = get_current_extraction_run(session, report.id)
    if run is None:
        return []
    rows = session.execute(
        select(TextBlock.raw_text, Page.page_number)
        .join(Page, TextBlock.page_id == Page.id)
        .where(
            Page.extraction_run_id == run.id,
            TextBlock.block_type == BlockType.HEADING_CANDIDATE,
        )
        .order_by(Page.page_number, TextBlock.reading_order)
    ).all()
    return [(text, page_number) for text, page_number in rows]


def main() -> None:
    hits: list[Hit] = []
    with get_session() as session:
        for ticker in TICKERS:
            company = session.scalar(select(Company).where(Company.ticker == ticker))
            if company is None:
                print(f"# no company for {ticker}")
                continue
            reports = sorted(
                session.scalars(select(Report).where(Report.company_id == company.id)).all(),
                key=lambda r: r.directory_year,
            )
            for report in reports:
                canonical = _canonical_headings(session, report)
                if canonical is not None:
                    headings, source = canonical, "canonical"
                else:
                    headings, source = _legacy_headings(session, report), "legacy_textblock"

                for text, page_number in headings:
                    guesses = _classify_text(text)
                    if guesses:
                        hits.append(
                            Hit(
                                ticker=ticker,
                                year=report.directory_year,
                                schedule_guesses=guesses,
                                heading_text=" ".join(text.split()),
                                page_number=page_number,
                                source=source,
                            )
                        )

    print(f"total heading hits: {len(hits)}\n")
    for schedule in KEYWORD_FAMILIES:
        schedule_hits = [h for h in hits if schedule in h.schedule_guesses]
        print(f"=== {schedule} ({len(schedule_hits)} hits) ===")
        for h in schedule_hits:
            print(f"{h.ticker}\t{h.year}\t{h.source}\tp{h.page_number}\t{h.heading_text}")
        print()


if __name__ == "__main__":
    main()
