"""Cross-year semantic-unit alignment: deterministic correspondence
matching and run orchestration.

Track 7C.2 (docs/7c2-semantic-unit-alignment.md). Answers only "which
semantic unit in the later report corresponds to which semantic unit in
the earlier report" -- never "how much did it change" (7C.3). Reads only
persisted `SemanticUnit`/`SemanticUnitRun` output; never re-localizes
schedules, re-extracts units, or reads `Passage`/`PassageAlignment`/legacy
`TextBlock`.

No embeddings, LLMs, VLMs, or lexical similarity metrics are used: matching
is a conservative, deterministic cascade (exact unit_key, then normalized
heading, then presence-based ADDED/REMOVED/UNRESOLVED_UPSTREAM/AMBIGUOUS).
"""

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import (
    AlignmentConfidence,
    NormalizedSchedule,
    SemanticUnitAlignmentRunStatus,
    SemanticUnitAlignmentStatus,
    SemanticUnitBoundaryStatus,
    SemanticUnitRunStatus,
)
from market_documents.models.report_pair import ReportPair
from market_documents.models.semantic_unit import SemanticUnit, SemanticUnitRun
from market_documents.models.semantic_unit_alignment import SemanticUnitAlignment, SemanticUnitAlignmentRun
from market_documents.services.semantic_unit_extraction import get_current_unit_run

logger = logging.getLogger(__name__)

# v1.0.0 = initial deterministic cascade: exact unit_key, then normalized
# heading, then presence-based ADDED/REMOVED/UNRESOLVED_UPSTREAM/AMBIGUOUS.
ALGORITHM_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Pure data structures and algorithm
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitCandidate:
    """A minimal, ORM-free view of one SemanticUnit, for the pure algorithm."""

    id: uuid.UUID
    unit_key: str
    source_heading: str
    boundary_status: SemanticUnitBoundaryStatus


@dataclass(frozen=True)
class AlignmentDecision:
    earlier_unit_id: uuid.UUID | None
    later_unit_id: uuid.UUID | None
    status: SemanticUnitAlignmentStatus
    confidence: AlignmentConfidence
    evidence: str


_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_LEADING_NUMBERING_RE = re.compile(r"^\s*[\d]+(\.[\d]+)*[.)]?\s+")
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_heading(text: str) -> str:
    """Case, whitespace, punctuation, and numbering-prefix normalization,
    per docs/7c2-semantic-unit-alignment.md's matching cascade step 2."""
    stripped = _LEADING_NUMBERING_RE.sub("", text.strip())
    no_punctuation = _PUNCTUATION_RE.sub("", stripped)
    return _WHITESPACE_RE.sub(" ", no_punctuation).strip().lower()


def align_units(
    earlier_units: list[UnitCandidate],
    later_units: list[UnitCandidate],
    *,
    earlier_run_clean: bool,
    later_run_clean: bool,
) -> list[AlignmentDecision]:
    """Deterministically align `earlier_units` against `later_units`.

    `earlier_run_clean`/`later_run_clean` mean the source SemanticUnitRun
    completed with zero warnings -- i.e. every unit it attempted resolved
    successfully. Only then is a missing counterpart on that side treated
    as confirmed absence (ADDED/REMOVED); a missing counterpart in a run
    that completed WITH warnings is indistinguishable, from persisted data
    alone, between "genuinely never existed" and "extraction missed it," so
    it is surfaced as UNRESOLVED_UPSTREAM instead (see the module and
    `SemanticUnitAlignmentStatus` docstrings, and the BEL 2020 gross_margin
    case in docs/7c2-semantic-unit-alignment.md).

    Assumes at most one `SemanticUnit` per (run, unit_key) -- guaranteed by
    `uq_semantic_units_run_instance_unit_key` for a single-schedule-instance
    run, the only case 7C.1 produces.
    """
    earlier_by_key = {u.unit_key: u for u in earlier_units}
    later_by_key = {u.unit_key: u for u in later_units}

    decisions: list[AlignmentDecision] = []
    consumed_earlier: set[str] = set()
    consumed_later: set[str] = set()

    # Step 1: exact unit_key match, both sides RESOLVED -- the primary
    # happy path for the currently configured BEL gross_margin / ACT
    # cfo_conclusion units, which keep the same unit_key across years.
    for key in sorted(earlier_by_key):
        e = earlier_by_key[key]
        l = later_by_key.get(key)
        if e.boundary_status == SemanticUnitBoundaryStatus.RESOLVED and l is not None and l.boundary_status == SemanticUnitBoundaryStatus.RESOLVED:
            decisions.append(
                AlignmentDecision(
                    e.id, l.id, SemanticUnitAlignmentStatus.MATCHED, AlignmentConfidence.HIGH,
                    f"exact unit_key match: {key!r}",
                )
            )
            consumed_earlier.add(key)
            consumed_later.add(key)

    # Step 2: normalized heading match among remaining RESOLVED units with
    # different unit_keys. Only a *unique* normalized match on each side is
    # accepted -- ambiguous candidates are surfaced for review, never guessed.
    leftover_earlier = [
        (k, u) for k, u in earlier_by_key.items()
        if k not in consumed_earlier and u.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    ]
    leftover_later = [
        (k, u) for k, u in later_by_key.items()
        if k not in consumed_later and u.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    ]

    for k_e, e in leftover_earlier:
        norm = _normalize_heading(e.source_heading)
        candidates = [(k_l, l) for k_l, l in leftover_later if k_l not in consumed_later and _normalize_heading(l.source_heading) == norm]
        if len(candidates) == 1:
            # RENAMED is a declared but currently-unsupported status (see
            # `SemanticUnitAlignmentStatus`'s docstring): distinguishing a
            # genuine rename from cosmetic normalization noise would need
            # fuzzier evidence than this deterministic cascade allows, so
            # every unique normalized-heading match is MATCHED, just at
            # lower confidence than an exact unit_key match.
            k_l, l = candidates[0]
            decisions.append(
                AlignmentDecision(
                    e.id, l.id, SemanticUnitAlignmentStatus.MATCHED, AlignmentConfidence.MEDIUM,
                    f"normalized heading match {norm!r} (unit_key {k_e!r} -> {k_l!r})",
                )
            )
            consumed_earlier.add(k_e)
            consumed_later.add(k_l)
        elif len(candidates) > 1:
            decisions.append(
                AlignmentDecision(
                    e.id, None, SemanticUnitAlignmentStatus.AMBIGUOUS, AlignmentConfidence.NEEDS_REVIEW,
                    f"{len(candidates)} later units match normalized heading {norm!r} -- not guessed",
                )
            )
            consumed_earlier.add(k_e)
            # The candidates themselves are also consumed: they were
            # considered and rejected for ambiguity, not literally absent,
            # so they must not fall through to ADDED/REMOVED in step 3.
            consumed_later.update(k_l for k_l, _ in candidates)

    # Step 3: everything not yet consumed -- REMOVED/ADDED (only when the
    # *other* side's run was clean), UNRESOLVED_UPSTREAM otherwise.
    all_keys = sorted(set(earlier_by_key) | set(later_by_key))
    for key in all_keys:
        if key in consumed_earlier and key in consumed_later:
            continue
        e = earlier_by_key.get(key) if key not in consumed_earlier else None
        l = later_by_key.get(key) if key not in consumed_later else None
        if e is None and l is None:
            continue

        if e is not None and e.boundary_status == SemanticUnitBoundaryStatus.UNRESOLVED:
            decisions.append(
                AlignmentDecision(
                    e.id, l.id if l is not None else None,
                    SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, AlignmentConfidence.NEEDS_REVIEW,
                    f"earlier {key!r} present but boundary UNRESOLVED",
                )
            )
            continue
        if l is not None and l.boundary_status == SemanticUnitBoundaryStatus.UNRESOLVED:
            decisions.append(
                AlignmentDecision(
                    e.id if e is not None else None, l.id,
                    SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, AlignmentConfidence.NEEDS_REVIEW,
                    f"later {key!r} present but boundary UNRESOLVED",
                )
            )
            continue

        if e is not None and l is None:
            # e is necessarily RESOLVED here (UNRESOLVED handled above).
            if later_run_clean:
                decisions.append(
                    AlignmentDecision(
                        e.id, None, SemanticUnitAlignmentStatus.REMOVED, AlignmentConfidence.HIGH,
                        f"{key!r} resolved earlier; later run completed with zero warnings and has no {key!r} unit",
                    )
                )
            else:
                decisions.append(
                    AlignmentDecision(
                        e.id, None, SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, AlignmentConfidence.NEEDS_REVIEW,
                        f"later run completed with warnings and has no {key!r} unit -- extraction limitation, not confirmed removal",
                    )
                )
            continue

        if l is not None and e is None:
            if earlier_run_clean:
                decisions.append(
                    AlignmentDecision(
                        None, l.id, SemanticUnitAlignmentStatus.ADDED, AlignmentConfidence.HIGH,
                        f"{key!r} resolved later; earlier run completed with zero warnings and has no {key!r} unit",
                    )
                )
            else:
                decisions.append(
                    AlignmentDecision(
                        None, l.id, SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, AlignmentConfidence.NEEDS_REVIEW,
                        f"earlier run completed with warnings and has no {key!r} unit -- extraction limitation, not confirmed addition",
                    )
                )
            continue

    return decisions


def compute_configuration_hash() -> str:
    """Deterministic fingerprint of the alignment algorithm's own behavior
    (no external per-company configuration exists for 7C.2), so a future
    change to the matching cascade forces a fresh
    `SemanticUnitAlignmentRun` instead of a stale skip."""
    payload = {"algorithm_version": ALGORITHM_VERSION}
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def get_current_alignment_run(
    session: Session, report_pair_id: uuid.UUID, schedule: NormalizedSchedule
) -> SemanticUnitAlignmentRun | None:
    return session.scalars(
        select(SemanticUnitAlignmentRun)
        .where(
            SemanticUnitAlignmentRun.report_pair_id == report_pair_id,
            SemanticUnitAlignmentRun.schedule == schedule,
            SemanticUnitAlignmentRun.status.in_(
                (SemanticUnitAlignmentRunStatus.COMPLETED, SemanticUnitAlignmentRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(SemanticUnitAlignmentRun.completed_at.desc())
        .limit(1)
    ).first()


@dataclass
class AlignmentOutcome:
    report_pair_id: uuid.UUID
    run: SemanticUnitAlignmentRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def _to_candidate(unit: SemanticUnit) -> UnitCandidate:
    return UnitCandidate(
        id=unit.id, unit_key=unit.unit_key, source_heading=unit.source_heading, boundary_status=unit.boundary_status
    )


def run_alignment(
    session: Session, report_pair: ReportPair, schedule: NormalizedSchedule, *, force: bool = False
) -> AlignmentOutcome:
    """Align every SemanticUnit for one adjacent-year ReportPair and schedule.

    Eligibility requires a current successful SemanticUnitRun for `schedule`
    on both the earlier and later report. If either side has none, this
    pair is reported ineligible ("upstream unit unavailable") and no
    `SemanticUnitAlignmentRun` row is created at all -- distinct from the
    per-unit UNRESOLVED_UPSTREAM result, which requires a successful run to
    exist but some individual unit within it to be missing or unresolved.

    Skips (returning the existing run) if the current successful alignment
    already used identical source SemanticUnitRuns and configuration, and
    `force` was not set.
    """
    earlier_run = get_current_unit_run(session, report_pair.earlier_report_id, schedule)
    later_run = get_current_unit_run(session, report_pair.later_report_id, schedule)
    if earlier_run is None or later_run is None:
        missing_side = "earlier" if earlier_run is None else "later"
        return AlignmentOutcome(
            report_pair_id=report_pair.id, run=None, ineligible=True,
            ineligible_reason=f"{missing_side} report has no current successful {schedule.value} semantic-unit run -- upstream unit unavailable",
        )

    configuration_hash = compute_configuration_hash()

    current_run = get_current_alignment_run(session, report_pair.id, schedule)
    if (
        current_run is not None
        and not force
        and current_run.earlier_semantic_unit_run_id == earlier_run.id
        and current_run.later_semantic_unit_run_id == later_run.id
        and current_run.configuration_hash == configuration_hash
    ):
        return AlignmentOutcome(
            report_pair_id=report_pair.id, run=current_run, skipped=True,
            skip_reason="identical successful alignment run already exists",
        )

    run = SemanticUnitAlignmentRun(
        report_pair_id=report_pair.id,
        earlier_semantic_unit_run_id=earlier_run.id,
        later_semantic_unit_run_id=later_run.id,
        schedule=schedule,
        algorithm_version=ALGORITHM_VERSION,
        configuration_hash=configuration_hash,
        status=SemanticUnitAlignmentRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_alignment(session, report_pair, earlier_run, later_run, run)
    except Exception as exc:  # never leave a run silently half-written
        run.status = SemanticUnitAlignmentRunStatus.FAILED
        run.error_message = f"semantic unit alignment failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception(
            "semantic unit alignment failed for report_pair=%s schedule=%s", report_pair.id, schedule.value
        )

    session.flush()
    return AlignmentOutcome(report_pair_id=report_pair.id, run=run)


def _run_alignment(
    session: Session,
    report_pair: ReportPair,
    earlier_run: SemanticUnitRun,
    later_run: SemanticUnitRun,
    run: SemanticUnitAlignmentRun,
) -> None:
    earlier_units = session.scalars(select(SemanticUnit).where(SemanticUnit.semantic_unit_run_id == earlier_run.id)).all()
    later_units = session.scalars(select(SemanticUnit).where(SemanticUnit.semantic_unit_run_id == later_run.id)).all()

    decisions = align_units(
        [_to_candidate(u) for u in earlier_units],
        [_to_candidate(u) for u in later_units],
        earlier_run_clean=earlier_run.status == SemanticUnitRunStatus.COMPLETED,
        later_run_clean=later_run.status == SemanticUnitRunStatus.COMPLETED,
    )

    notes: list[str] = []
    for decision in decisions:
        session.add(
            SemanticUnitAlignment(
                alignment_run_id=run.id,
                report_pair_id=report_pair.id,
                earlier_semantic_unit_id=decision.earlier_unit_id,
                later_semantic_unit_id=decision.later_unit_id,
                status=decision.status,
                confidence=decision.confidence,
                evidence=decision.evidence,
            )
        )
        if decision.status in (SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, SemanticUnitAlignmentStatus.AMBIGUOUS):
            notes.append(f"{decision.status.value}: {decision.evidence}")

    run.completed_at = datetime.now(UTC)
    run.review_reason = "; ".join(notes) if notes else None
    run.status = (
        SemanticUnitAlignmentRunStatus.COMPLETED if not notes else SemanticUnitAlignmentRunStatus.COMPLETED_WITH_WARNINGS
    )
