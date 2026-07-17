"""Change classification, semantic/lexical disagreement, and confidence
assessment for accepted passage alignments.

Pure functions operating on already-computed component scores -- no
database access. Applies only to *accepted* correspondences; NEW, REMOVED,
and AMBIGUOUS are decided by the conflict-resolution orchestration in
`passage_alignment.py`, not here.
"""

from dataclasses import dataclass

from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, ExtractionQuality
from market_documents.services.alignment_config import ALIGNMENT_CONFIG, AlignmentConfig


def classify_alignment(
    *,
    semantic_similarity: float,
    lexical_composite: float | None,
    length_ratio: float | None,
    config: AlignmentConfig = ALIGNMENT_CONFIG,
) -> AlignmentStatus:
    """Classify one accepted correspondence's degree of change.

    Semantic similarity is the primary gate; lexical agreement and length
    only add *stricter* requirements for the UNCHANGED tier, never an
    additional gate on LIGHTLY_MODIFIED. This is deliberate: a high-semantic/
    low-lexical paraphrase must not be penalized to SUBSTANTIALLY_MODIFIED
    solely because its wording differs (a low lexical_composite alone is not
    evidence of material change when semantic similarity is high). Symmetrically,
    a high-lexical reused-boilerplate passage never reaches UNCHANGED (or even
    LIGHTLY_MODIFIED) unless semantic similarity is *also* high -- lexical
    overlap alone is not proof of unchanged meaning.
    """
    lc = lexical_composite if lexical_composite is not None else 0.0
    lr = length_ratio if length_ratio is not None else 0.0

    if (
        semantic_similarity >= config.unchanged_semantic_threshold
        and lc >= config.unchanged_lexical_threshold
        and lr >= config.unchanged_length_ratio_min
    ):
        return AlignmentStatus.UNCHANGED
    if semantic_similarity >= config.lightly_modified_semantic_threshold:
        return AlignmentStatus.LIGHTLY_MODIFIED
    return AlignmentStatus.SUBSTANTIALLY_MODIFIED


def detect_disagreement(
    *, semantic_similarity: float, lexical_composite: float | None, config: AlignmentConfig = ALIGNMENT_CONFIG
) -> str | None:
    """Flag the two "evidence conflicts" patterns explicitly, rather than
    collapsing them into the opaque combined score.

    High-semantic/high-lexical and low-semantic/low-lexical are not flagged
    here -- those are the two "evidence agrees" patterns and need no
    special note.
    """
    if lexical_composite is None:
        return None
    if semantic_similarity >= config.disagreement_high_semantic_threshold and lexical_composite <= config.disagreement_low_lexical_threshold:
        return "high semantic / low lexical: likely paraphrase or rewrite with similar meaning"
    if semantic_similarity <= config.disagreement_low_semantic_threshold and lexical_composite >= config.disagreement_high_lexical_threshold:
        return "low semantic / high lexical: possible subtle change inside reused boilerplate, or model weakness"
    return None


@dataclass(frozen=True)
class ConfidenceAssessment:
    confidence: AlignmentConfidence
    review_reason: str | None


def assess_confidence(
    *,
    best_second_margin: float | None,
    disagreement: str | None,
    split_merge_flag: str | None,
    earlier_extraction_quality: ExtractionQuality | None,
    later_extraction_quality: ExtractionQuality | None,
    is_transition: bool,
    gap_months: int,
    config: AlignmentConfig = ALIGNMENT_CONFIG,
) -> ConfidenceAssessment:
    """Assess confidence for one accepted correspondence.

    An irregular reporting gap or transition status is contextual
    information that can pull HIGH down to MEDIUM, never an automatic
    failure on its own. Disagreement or an unresolved split/merge signal
    always forces NEEDS_REVIEW regardless of margin, since those indicate
    the evidence itself is inconsistent, not just close.
    """
    reasons: list[str] = []
    if split_merge_flag:
        reasons.append(split_merge_flag)
    if disagreement:
        reasons.append(disagreement)
    if earlier_extraction_quality == ExtractionQuality.NEEDS_REVIEW:
        reasons.append("earlier source extraction quality is NEEDS_REVIEW")
    if later_extraction_quality == ExtractionQuality.NEEDS_REVIEW:
        reasons.append("later source extraction quality is NEEDS_REVIEW")
    if is_transition:
        reasons.append("transition-period pair")
    if gap_months > config.irregular_gap_months_threshold:
        reasons.append(f"irregular reporting gap ({gap_months} months)")

    if split_merge_flag or disagreement:
        confidence = AlignmentConfidence.NEEDS_REVIEW
    else:
        # No competing candidate at all is the strongest possible margin signal.
        margin = best_second_margin if best_second_margin is not None else 1.0
        if margin < config.low_margin_threshold:
            confidence = AlignmentConfidence.LOW
        elif margin < config.medium_margin_threshold or reasons:
            confidence = AlignmentConfidence.MEDIUM
        else:
            confidence = AlignmentConfidence.HIGH

    return ConfidenceAssessment(confidence=confidence, review_reason="; ".join(reasons) if reasons else None)
