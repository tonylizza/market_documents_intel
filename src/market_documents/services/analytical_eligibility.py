"""Analytical eligibility routing + lexical comparison for aligned
semantic units (Track 7C.3,
docs/7c3-analytical-eligibility-and-lexical-comparison.md).

Consumes persisted `SemanticUnitAlignment` rows from 7C.2 and answers "how
should this aligned unit be compared" (`AnalyticalDecision`), and -- for
units routed to `LEXICAL_ONLY` -- "how much did the wording change"
(`LexicalUnitComparison`, `services.lexical_unit_comparison`). Alignment
and comparison remain separate concerns: this module never revisits or
overrides a `SemanticUnitAlignmentStatus`, and lexical similarity is never
used to redefine correspondence.

Routing is deterministic and configuration-driven: a `(ticker, unit_key)`
pair with no entry in `UNIT_ANALYTICAL_MODES` is never guessed into
eligibility, it routes to `NOT_ELIGIBLE`. Only `LEXICAL_ONLY` proceeds to
lexical metrics in this milestone -- `LEXICAL_WITH_NUMERIC_CONTEXT`,
`STRUCTURED_COMPARISON_PREFERRED`, and `PRESENCE_STATUS_ONLY` are declared
routing outcomes only.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.analytical_comparison import (
    AnalyticalDecision,
    AnalyticalDecisionRun,
    LexicalUnitComparison,
)
from market_documents.models.enums import (
    AlignmentConfidence,
    AnalyticalDecisionRunStatus,
    AnalyticalMode,
    NormalizedSchedule,
    SemanticUnitAlignmentStatus,
)
from market_documents.models.report_pair import ReportPair
from market_documents.models.semantic_unit_alignment import SemanticUnitAlignment, SemanticUnitAlignmentRun
from market_documents.services.lexical_unit_comparison import compute_lexical_metrics
from market_documents.services.semantic_unit_alignment import get_current_alignment_run

logger = logging.getLogger(__name__)

# v1.0.0 = initial routing: config-driven LEXICAL_ONLY for BEL gross_margin
# and ACT cfo_conclusion; ADDED/REMOVED -> PRESENCE_STATUS_ONLY (routing
# outcome only); everything else configured -> NOT_ELIGIBLE.
# v1.1.0 = Track 7D.2 (docs/7d2-financial-performance-unit-expansion.md):
# added ACT healthcare_services_review, LEXICAL_ONLY -- real-corpus
# inspection confirmed it is direct narrative prose with no embedded
# numeric/tabular content once excluded_from_narrative blocks are filtered
# out, the same profile as the two existing LEXICAL_ONLY units.
# v1.2.0 = Track 7D.3 (docs/7d3-corporate-governance-expansion.md): first
# CORPORATE_GOVERNANCE routing entries. ACT's three units (information_
# security_governance, governance_policies_processes, combined_assurance)
# are direct narrative prose, same profile as the existing LEXICAL_ONLY
# units -- routed LEXICAL_ONLY. BEL's board_composition_diversity is a
# demographic composition table (director designation/age/gender/race), not
# prose -- routed STRUCTURED_COMPARISON_PREFERRED (a declared routing
# outcome only; no structured-comparison engine runs for it here, per the
# milestone's scope).
# v1.3.0 = Track 7D.4 (docs/7d4-corpus-wide-remuneration-expansion.md):
# first REMUNERATION routing entries. All seven new units are direct
# narrative prose (committee-chair letters, policy-change statements,
# governance-framework intros, incentive-scheme mechanics descriptions),
# same profile as the existing LEXICAL_ONLY units -- including
# BEL_VARIABLE_REMUNERATION, which does contain incidental figures (hurdle
# percentages, dates) but is predominantly prose describing scheme design,
# not a table -- routed LEXICAL_ONLY, not LEXICAL_WITH_NUMERIC_CONTEXT (no
# engine for that mode exists in this milestone regardless).
ALGORITHM_VERSION = "1.3.0"

# Per docs/experiments/annual-report-bel-compact-validation.md Section 3
# and docs/7c1-schedule-localization-plan.md's original unit selection:
# both units are recurring, substantive, boilerplate-anchored prose with no
# embedded numeric table or presence/status framing -- clean LEXICAL_ONLY
# candidates in the research's own terminology (LEXICAL_DIRECT). Deliberately
# not derived from word count or unit_type alone (see module docstring of
# docs/7c3-analytical-eligibility-and-lexical-comparison.md, Section 2):
# function and validated analytical role, not length, drive eligibility.
# healthcare_services_review (Track 7D.2) meets the same bar: direct
# narrative prose, no numeric/tabular framing, a stable analytical role
# (medical-scheme-administration-cluster performance commentary) across its
# resolved years -- see
# docs/7d2-financial-performance-unit-expansion.md Section 6.
UNIT_ANALYTICAL_MODES: dict[tuple[str, str], AnalyticalMode] = {
    ("BEL", "gross_margin"): AnalyticalMode.LEXICAL_ONLY,
    ("ACT", "cfo_conclusion"): AnalyticalMode.LEXICAL_ONLY,
    ("ACT", "healthcare_services_review"): AnalyticalMode.LEXICAL_ONLY,
    ("ACT", "information_security_governance"): AnalyticalMode.LEXICAL_ONLY,
    ("ACT", "governance_policies_processes"): AnalyticalMode.LEXICAL_ONLY,
    ("ACT", "combined_assurance"): AnalyticalMode.LEXICAL_ONLY,
    ("BEL", "board_composition_diversity"): AnalyticalMode.STRUCTURED_COMPARISON_PREFERRED,
    ("ACT", "remco_chairperson_report"): AnalyticalMode.LEXICAL_ONLY,
    ("ACT", "remuneration_policy_changes"): AnalyticalMode.LEXICAL_ONLY,
    ("ACT", "remuneration_governance"): AnalyticalMode.LEXICAL_ONLY,
    ("BEL", "variable_remuneration"): AnalyticalMode.LEXICAL_ONLY,
    ("SUR", "remuneration_policy_changes_and_focus"): AnalyticalMode.LEXICAL_ONLY,
    ("SUR", "fair_responsible_remuneration"): AnalyticalMode.LEXICAL_ONLY,
    ("SUR", "remuneration_policy_shareholder_engagement"): AnalyticalMode.LEXICAL_ONLY,
}


def unit_analytical_mode_for(ticker: str, unit_key: str) -> AnalyticalMode | None:
    return UNIT_ANALYTICAL_MODES.get((ticker, unit_key))


def compute_configuration_hash() -> str:
    """Deterministic fingerprint of the routing configuration in effect, so
    adding/changing a `UNIT_ANALYTICAL_MODES` entry forces a fresh
    `AnalyticalDecisionRun` instead of a stale skip."""
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "modes": {f"{ticker}:{unit_key}": mode.value for (ticker, unit_key), mode in sorted(UNIT_ANALYTICAL_MODES.items())},
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Pure routing
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutingDecision:
    mode: AnalyticalMode
    confidence: AlignmentConfidence
    reason: str
    review_reason: str | None = None


# Alignment statuses that never produce an AnalyticalDecision at all: the
# correspondence itself is not trustworthy enough to license any
# analytical claim, substantive-absence or otherwise (docs/7c3-...md
# Section 3).
_NO_DECISION_STATUSES = frozenset(
    {SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, SemanticUnitAlignmentStatus.AMBIGUOUS}
)
# Alignment statuses that correspond to a genuine correspondence and are
# eligible for config-driven mode lookup.
_CORRESPONDENCE_STATUSES = frozenset(
    {SemanticUnitAlignmentStatus.MATCHED, SemanticUnitAlignmentStatus.RENAMED}
)


def route_alignment(
    *,
    status: SemanticUnitAlignmentStatus,
    ticker: str,
    earlier_unit_key: str | None,
    later_unit_key: str | None,
) -> RoutingDecision | None:
    """Route one `SemanticUnitAlignment` to an `AnalyticalMode`.

    Returns `None` for UNRESOLVED_UPSTREAM/AMBIGUOUS -- no
    `AnalyticalDecision` should be created for those at all. ADDED/REMOVED
    route to `PRESENCE_STATUS_ONLY` as a declared routing outcome; no
    presence/status comparison engine is implemented in 7C.3. MATCHED/
    RENAMED look up `(ticker, unit_key)` in `UNIT_ANALYTICAL_MODES`; a
    missing entry routes to `NOT_ELIGIBLE`, never guessed.
    """
    if status in _NO_DECISION_STATUSES:
        return None

    if status in (SemanticUnitAlignmentStatus.ADDED, SemanticUnitAlignmentStatus.REMOVED):
        return RoutingDecision(
            mode=AnalyticalMode.PRESENCE_STATUS_ONLY,
            confidence=AlignmentConfidence.HIGH,
            reason=f"{status.value}: presence/absence event, not a lexical comparison -- no comparison engine implemented for this mode yet",
        )

    assert status in _CORRESPONDENCE_STATUSES, f"unhandled SemanticUnitAlignmentStatus in routing: {status}"

    unit_key = earlier_unit_key or later_unit_key
    if unit_key is None:
        return RoutingDecision(
            mode=AnalyticalMode.NOT_ELIGIBLE,
            confidence=AlignmentConfidence.NEEDS_REVIEW,
            reason="no unit_key available on either side of the alignment",
            review_reason="alignment has no earlier or later unit_key -- cannot look up eligibility config",
        )

    configured_mode = unit_analytical_mode_for(ticker, unit_key)
    if configured_mode is None:
        return RoutingDecision(
            mode=AnalyticalMode.NOT_ELIGIBLE,
            confidence=AlignmentConfidence.NEEDS_REVIEW,
            reason=f"no analytical eligibility config for {ticker} unit_key {unit_key!r} -- not guessed",
            review_reason=f"add a UNIT_ANALYTICAL_MODES entry for ({ticker!r}, {unit_key!r}) if this unit should be analytically eligible",
        )

    return RoutingDecision(
        mode=configured_mode,
        confidence=AlignmentConfidence.HIGH,
        reason=f"configured {configured_mode.value} for {ticker} unit_key {unit_key!r}",
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def get_current_decision_run(
    session: Session, report_pair_id: uuid.UUID, schedule: NormalizedSchedule
) -> AnalyticalDecisionRun | None:
    return session.scalars(
        select(AnalyticalDecisionRun)
        .where(
            AnalyticalDecisionRun.report_pair_id == report_pair_id,
            AnalyticalDecisionRun.schedule == schedule,
            AnalyticalDecisionRun.status.in_(
                (AnalyticalDecisionRunStatus.COMPLETED, AnalyticalDecisionRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(AnalyticalDecisionRun.completed_at.desc())
        .limit(1)
    ).first()


@dataclass
class AnalyticalComparisonOutcome:
    report_pair_id: uuid.UUID
    run: AnalyticalDecisionRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def run_analytical_comparison(
    session: Session, report_pair: ReportPair, schedule: NormalizedSchedule, *, force: bool = False
) -> AnalyticalComparisonOutcome:
    """Route every `SemanticUnitAlignment` of the current successful
    `SemanticUnitAlignmentRun` for `(report_pair, schedule)`, and compute +
    persist lexical metrics for every `LEXICAL_ONLY` decision.

    Eligibility requires a current successful `SemanticUnitAlignmentRun`
    for `schedule` -- if none exists, this pair is reported ineligible and
    no `AnalyticalDecisionRun` row is created at all, mirroring
    `services.semantic_unit_alignment.run_alignment`'s own upstream-
    eligibility gate.

    Skips (returning the existing run) if the current successful decision
    run already used the identical source alignment run and configuration,
    and `force` was not set.
    """
    alignment_run = get_current_alignment_run(session, report_pair.id, schedule)
    if alignment_run is None:
        return AnalyticalComparisonOutcome(
            report_pair_id=report_pair.id, run=None, ineligible=True,
            ineligible_reason=f"no current successful semantic-unit-alignment run for {schedule.value} -- run `units align` first",
        )

    configuration_hash = compute_configuration_hash()

    current_run = get_current_decision_run(session, report_pair.id, schedule)
    if (
        current_run is not None
        and not force
        and current_run.alignment_run_id == alignment_run.id
        and current_run.configuration_hash == configuration_hash
    ):
        return AnalyticalComparisonOutcome(
            report_pair_id=report_pair.id, run=current_run, skipped=True,
            skip_reason="identical successful analytical-decision run already exists",
        )

    run = AnalyticalDecisionRun(
        alignment_run_id=alignment_run.id,
        report_pair_id=report_pair.id,
        schedule=schedule,
        algorithm_version=ALGORITHM_VERSION,
        configuration_hash=configuration_hash,
        status=AnalyticalDecisionRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_analytical_comparison(session, report_pair, alignment_run, run)
    except Exception as exc:  # never leave a run silently half-written
        run.status = AnalyticalDecisionRunStatus.FAILED
        run.error_message = f"analytical eligibility/comparison failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception(
            "analytical eligibility/comparison failed for report_pair=%s schedule=%s", report_pair.id, schedule.value
        )

    session.flush()
    return AnalyticalComparisonOutcome(report_pair_id=report_pair.id, run=run)


def _run_analytical_comparison(
    session: Session,
    report_pair: ReportPair,
    alignment_run: SemanticUnitAlignmentRun,
    run: AnalyticalDecisionRun,
) -> None:
    ticker = report_pair.company.ticker
    alignments = session.scalars(
        select(SemanticUnitAlignment).where(SemanticUnitAlignment.alignment_run_id == alignment_run.id)
    ).all()

    notes: list[str] = []
    for alignment in alignments:
        earlier_unit_key = alignment.earlier_semantic_unit.unit_key if alignment.earlier_semantic_unit else None
        later_unit_key = alignment.later_semantic_unit.unit_key if alignment.later_semantic_unit else None

        routing = route_alignment(
            status=alignment.status, ticker=ticker, earlier_unit_key=earlier_unit_key, later_unit_key=later_unit_key
        )
        if routing is None:
            continue

        decision = AnalyticalDecision(
            decision_run_id=run.id,
            semantic_unit_alignment_id=alignment.id,
            analytical_mode=routing.mode,
            confidence=routing.confidence,
            reason=routing.reason,
            review_reason=routing.review_reason,
        )
        session.add(decision)
        session.flush()

        if routing.mode == AnalyticalMode.NOT_ELIGIBLE:
            notes.append(f"NOT_ELIGIBLE: {routing.reason}")

        if routing.mode == AnalyticalMode.LEXICAL_ONLY:
            earlier_text = alignment.earlier_semantic_unit.source_text if alignment.earlier_semantic_unit else None
            later_text = alignment.later_semantic_unit.source_text if alignment.later_semantic_unit else None
            if earlier_text is None or later_text is None:
                # A MATCHED/RENAMED alignment's units are both boundary
                # RESOLVED by construction (see
                # services.semantic_unit_alignment.align_units step 1/2),
                # so source_text is always populated here in the current
                # corpus; this guards the invariant rather than expecting
                # to hit it.
                notes.append(
                    f"LEXICAL_ONLY decision for alignment {alignment.id} has no source_text on one side -- skipping metrics"
                )
                continue

            metrics = compute_lexical_metrics(earlier_text, later_text)
            session.add(
                LexicalUnitComparison(
                    analytical_decision_id=decision.id,
                    semantic_unit_alignment_id=alignment.id,
                    tfidf_cosine=metrics.tfidf_cosine,
                    unigram_jaccard=metrics.unigram_jaccard,
                    bigram_jaccard=metrics.bigram_jaccard,
                    edit_similarity=metrics.edit_similarity,
                    sequence_similarity=metrics.sequence_similarity,
                    earlier_word_count=metrics.earlier_word_count,
                    later_word_count=metrics.later_word_count,
                    word_count_change=metrics.word_count_change,
                    word_count_change_pct=metrics.word_count_change_pct,
                )
            )

    run.completed_at = datetime.now(UTC)
    run.review_reason = "; ".join(notes) if notes else None
    run.status = (
        AnalyticalDecisionRunStatus.COMPLETED if not notes else AnalyticalDecisionRunStatus.COMPLETED_WITH_WARNINGS
    )
