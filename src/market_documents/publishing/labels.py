"""Pure, database-free helpers shared across the publishing package: the
deterministic-ID scheme, the passage publication exclusion policy, and
quality/metric label translation. No function here ever opens a session --
`source_dataset.py` is the only module allowed to query either database.
"""

import uuid
from dataclasses import dataclass
from statistics import quantiles

# ---------------------------------------------------------------------------
# Deterministic IDs
# ---------------------------------------------------------------------------

# Frozen forever once computed -- changing this constant would shift every
# historical publication's IDs. Derived once via
# uuid.uuid5(uuid.NAMESPACE_URL, "https://publishing.marketdocuments.internal")
# and hardcoded here so no environment can ever recompute a different value.
APP_ID_NAMESPACE = uuid.UUID("2b5b3b8e-7f0a-5b8b-9b0b-6a4c9b8f2e31")


def derive_id(publication_version: str, table: str, *parts: str) -> uuid.UUID:
    """Deterministic app-side UUID for one row.

    Same `publication_version` + same `table` + same `parts` (a research
    primary key, optionally combined with a pivot discriminator such as a
    language-metric category) always yields the same UUID -- this is what
    makes rebuilding an unchanged `publication_version` an idempotent
    upsert-in-place rather than a duplicate-inserting operation. A different
    `publication_version` always yields a different UUID, so two
    publications' rows never collide.
    """
    name = ":".join((publication_version, table, *parts))
    return uuid.uuid5(APP_ID_NAMESPACE, name)


# ---------------------------------------------------------------------------
# Track 7E.1: shared corpus IDs (publication-independent)
# ---------------------------------------------------------------------------

# Reserved "publication_version" value for `derive_id` calls that must yield
# the SAME id no matter which publication is being built -- used only for
# `app_corpus.*` rows (passage text, passage embeddings), whose content is a
# pure function of source data (never of publication_version). Never a real
# publication_version -- `Publication.publication_version` is a caller
# -supplied free-form string (see `docs/publishing.md`), and this sentinel is
# deliberately shaped so it can never collide with one.
CORPUS_SCOPE = "__corpus__"


def derive_corpus_id(table: str, *parts: str) -> uuid.UUID:
    """Deterministic id for one `app_corpus.*` row -- same `table` + `parts`
    (always source-side identifiers, e.g. `source_passage_id`, never a
    publication id/version) always yields the same UUID regardless of which
    publication is being built. This is what lets two publications built
    from the same unchanged source passage reuse the exact same corpus row
    instead of writing a second physical copy (see `publisher.py`'s
    Passage/PassageEmbedding construction and docs/7e1-publication-storage-
    lifecycle-hardening.md)."""
    return derive_id(CORPUS_SCOPE, table, *parts)


# ---------------------------------------------------------------------------
# Track 7F.7a.5: versioned shared artifact identities (publication-
# independent, like `CORPUS_SCOPE` above, but one axis per artifact family
# instead of one global sentinel -- a release that only changes, say, QA
# chunking must not force a new `passage_comparisons`/`retrieval_contexts`
# generation, and vice versa). Each constant is a real, bumpable version
# string (not a fixed sentinel like `CORPUS_SCOPE`): `derive_id(<this
# version>, table, *parts)` is called directly by the publisher wherever an
# `app_artifacts.*` row is constructed -- there is no `derive_artifact_id`
# wrapper, since the caller must supply the correct one of the three
# constants below for the family it's building, and a wrapper would make it
# too easy to default to the wrong one.
#
# Bump rules (docs/versioned-shared-artifacts-implementation-7f7a5.md has
# the full rationale):
#
#   ALIGNMENT_ARTIFACT_VERSION -- bump when passage-alignment logic, passage-
#     comparison scoring (semantic/lexical/heading similarity, content
#     score), or retrieval-context derivation/classification changes in a
#     way that would change any `app_artifacts.passage_comparisons` or
#     `app_artifacts.retrieval_contexts`(+children) row's content for
#     unchanged source data. Covers all four tables in that family (see
#     `models.py`'s `ArtifactRetrievalContext*` classes) -- retrieval-context
#     classification does not get its own axis because it is derived
#     entirely from the same alignment/passage-comparison inputs and has
#     never needed to change independently of them.
#   LANGUAGE_SIGNAL_ARTIFACT_VERSION -- bump when financial-language signal
#     extraction (category/subcategory counting, taxonomy, negation
#     handling) changes in a way that would change any `app_artifacts.
#     passage_language_signals` row's content for unchanged source data.
#     A metric-only research `SIGNAL_VERSION` bump (new pair-level derived
#     fields, no per-passage change) must NOT bump this: since signals_v2
#     the identity is the stable (research `passage_alignment_id`,
#     `report_side`, category, subcategory) tuple, never the transient
#     research `PassageLanguageSignal.id` a fresh `LanguageSignalRun` mints,
#     so such a rerun reuses the existing generation 100% (the content-hash
#     guard still fails loudly if per-passage content actually changed).
#     signals_v1 -> signals_v2 (Track 7F.10) was that identity-scheme change
#     itself -- see docs/fresh-neon-cutover-prep-7f10.md section 1.
#   QA_CHUNKING_ARTIFACT_VERSION -- bump when the QA chunk-window builder
#     (`qa_chunking.build_qa_chunks`) changes in a way that would change
#     chunk boundaries, membership, or text for unchanged source data. Chunk
#     *embeddings* additionally depend on the embedding model/revision,
#     which is why every `app_artifacts.qa_chunks` identity combines this
#     version with `embedding_model`/`embedding_model_revision` rather than
#     relying on this constant alone (see `ArtifactQaChunk` in `models.py`).
ALIGNMENT_ARTIFACT_VERSION = "alignment_v1"
LANGUAGE_SIGNAL_ARTIFACT_VERSION = "signals_v2"
QA_CHUNKING_ARTIFACT_VERSION = "qa_chunk_v1"


# ---------------------------------------------------------------------------
# Passage publication policy
# ---------------------------------------------------------------------------

# Deliberately narrower than, and independent from,
# `financial_language_metrics.PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES` (6
# members, gates *feature/signal* eligibility). These two categories are the
# only ones meaning "not coherent text at all" -- everything else (list
# items, table context, captions, ...) is real document content and is
# published as a real, searchable passage; the other categories' nuance is
# carried entirely by `primary_narrative_eligible`/`feature_eligible` flags,
# never by omitting the passage.
PUBLICATION_EXCLUDED_CATEGORIES = frozenset({"short_fragment_invalid", "broken_fragment_sequence"})


# ---------------------------------------------------------------------------
# Quality-tier label translation (Python owns all plain-language labels)
# ---------------------------------------------------------------------------

REPORT_SIDE_QUALITY_LABELS: dict[str, str] = {
    "GOOD": "Analysis ready",
    "USABLE": "Ready with caution",
    "NEEDS_REVIEW": "Review recommended",
    "FAILED": "Unavailable",
}

ALIGNMENT_CHANGE_QUALITY_LABELS: dict[str, str] = {
    "GOOD": "Strong attribution",
    "USABLE": "Usable attribution",
    "NEEDS_REVIEW": "Attribution uncertain",
    "FAILED": "Attribution unavailable",
}

# Every other 4-tier quality enum in the research schema (ExtractionQuality,
# SimilarityResultQuality, FeatureQuality) shares the identical
# GOOD/USABLE/NEEDS_REVIEW/FAILED vocabulary; the report-side vocabulary
# reads naturally for all of them (extraction, disclosure-change).
GENERIC_QUALITY_LABELS: dict[str, str] = REPORT_SIDE_QUALITY_LABELS


ALIGNMENT_CONFIDENCE_LABELS: dict[str, str] = {
    "HIGH": "High confidence",
    "MEDIUM": "Medium confidence",
    "LOW": "Low confidence",
    "NEEDS_REVIEW": "Needs review",
}


def confidence_label(confidence: str | None) -> str | None:
    if confidence is None:
        return None
    return ALIGNMENT_CONFIDENCE_LABELS.get(confidence)


def quality_label(quality: str | None, scope: str = "generic") -> str | None:
    if quality is None:
        return None
    table = {
        "report_side": REPORT_SIDE_QUALITY_LABELS,
        "alignment_change": ALIGNMENT_CHANGE_QUALITY_LABELS,
        "generic": GENERIC_QUALITY_LABELS,
    }[scope]
    return table.get(quality)


def disclosure_change_score_displayed(quality: str | None, score: float | None) -> bool:
    """Whether a comparison's `disclosure_change_score` should be published
    at all -- independent of whether it's *primary eligible*.

    A NEEDS_REVIEW (or USABLE/GOOD) score is still displayed, with its
    quality made explicit via `disclosure_change_quality_label` -- only a
    `FAILED` quality or a missing score (`None`) withholds the value
    entirely. `primary_eligible` never factors in here: eligibility governs
    discovery *ranking*, not display (see `findings._gate_feature`,
    `publisher.py`'s population-selection for the percentile bands, and the
    Milestone 7A.1 follow-up brief: "review-qualified disclosure-change
    publication").
    """
    return score is not None and quality != "FAILED"


# ---------------------------------------------------------------------------
# Metric magnitude labels (disclosure-change score, language-signal deltas)
# ---------------------------------------------------------------------------

METRIC_THRESHOLD_VERSION = "percentile_v1"

# Percentile split over |value| computed from THIS publication's own
# eligible population -- never a hardcoded absolute number, so a corpus
# shift naturally recalibrates the bands on the next `publish build` rather
# than silently drifting out of sync with an arbitrary constant.
_BAND_DEFINITIONS: tuple[tuple[str, float, float, str], ...] = (
    ("Minimal", 0.0, 0.50, "Below the median magnitude of change observed in this publication."),
    ("Moderate", 0.50, 0.80, "Above the median but below the 80th percentile of observed magnitude."),
    ("Notable", 0.80, 0.95, "Among the largest 20% of observed magnitude."),
    ("Substantial", 0.95, 1.00, "Among the largest 5% of observed magnitude."),
)


@dataclass(frozen=True)
class MetricBand:
    metric_key: str
    label: str
    minimum_value: float | None
    maximum_value: float | None
    display_order: int
    explanation: str


def compute_percentile_bands(metric_key: str, values: list[float]) -> list[MetricBand]:
    """Four-band percentile split (P50/P80/P95) over `abs(value)` for one
    metric, computed from this publication's own eligible population.

    Bands are over magnitude, not signed value -- direction is composed
    separately at label time (`label_for_signed_metric`) so one set of
    bands serves both increases and decreases symmetrically. Returns an
    empty list if `values` is empty (no eligible comparisons for this
    metric in this publication) -- callers must never fabricate bands from
    zero data.
    """
    magnitudes = sorted(abs(v) for v in values)
    if not magnitudes:
        return []
    if len(magnitudes) == 1:
        cut_p50 = cut_p80 = cut_p95 = magnitudes[0]
    else:
        # `statistics.quantiles` needs at least 2 data points; with very
        # few points several cuts legitimately coincide, which just means
        # some bands never get populated in this publication -- expected,
        # not an error.
        qs = quantiles(magnitudes, n=100, method="inclusive")
        cut_p50, cut_p80, cut_p95 = qs[49], qs[78], qs[93]
    bounds = (0.0, cut_p50, cut_p80, cut_p95, float("inf"))
    bands = []
    for order, (label, _lo_pct, _hi_pct, explanation) in enumerate(_BAND_DEFINITIONS):
        bands.append(
            MetricBand(
                metric_key=metric_key,
                label=label,
                minimum_value=bounds[order],
                maximum_value=bounds[order + 1],
                display_order=order,
                explanation=explanation,
            )
        )
    return bands


def _band_for_magnitude(magnitude: float, bands: list[MetricBand]) -> MetricBand | None:
    for band in bands:
        lo = band.minimum_value if band.minimum_value is not None else float("-inf")
        hi = band.maximum_value if band.maximum_value is not None else float("inf")
        if lo <= magnitude <= hi:
            return band
    return bands[-1] if bands else None


def label_for_signed_metric(value: float | None, bands: list[MetricBand]) -> str | None:
    """Label a signed change metric (e.g. `net_tone_change`): band adjective
    plus a direction word. `None` when the value or the bands are
    unavailable -- never a fabricated label for missing data."""
    if value is None or not bands:
        return None
    band = _band_for_magnitude(abs(value), bands)
    if band is None:
        return None
    if value > 0:
        direction = "increase"
    elif value < 0:
        direction = "decrease"
    else:
        return "No change"
    return f"{band.label} {direction}"


def label_for_unsigned_metric(value: float | None, bands: list[MetricBand]) -> str | None:
    """Label an unsigned magnitude metric (e.g. `disclosure_change_score`):
    band adjective plus 'change', no direction."""
    if value is None or not bands:
        return None
    band = _band_for_magnitude(abs(value), bands)
    return f"{band.label} change" if band is not None else None
