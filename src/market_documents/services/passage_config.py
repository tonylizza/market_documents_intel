"""Centralized, versioned passage-segmentation thresholds and configuration.

Mirrors `extraction_config.py`/`similarity_config.py`: these are analysis
parameters, not per-deployment settings, so they live here as typed
constants. Bump the relevant `*_VERSION` constant whenever a boundary rule,
exclusion rule, or size threshold changes -- that is what forces a fresh
`PassageSegmentationRun` instead of silently reusing a stale one.

Size thresholds were set from the real corpus's TextBlock word-count
distribution (median 6 words/block, p95=71, p99=159 for included blocks;
NarrativeDocument word counts range 18k-85k across 30 reports) -- individual
blocks are too small to be usable passages on their own, so passages are
built by aggregating consecutive blocks up to these targets.
"""

import hashlib
import json
from dataclasses import asdict, dataclass

from market_documents.services.similarity_tokenization import TOKENIZER_VERSION

# v1.0.0 = initial word-count packer.
# v1.1.0 = oversized-single-block ceiling bypass fixed: a block larger than
# `max_words` on its own (previously always accepted unconditionally into
# its own passage, since the ceiling check only ever fired when a group
# already had content) is now split deterministically at sentence
# boundaries (word-boundary fallback for one oversized sentence) before
# packing. See `_split_oversized_block_text` and
# docs/embedding-eligibility-token-limit-diagnostic.md Section 4.1.
# v1.1.1 = the v1.1.0 fix only actually fired when the oversized block was
# the first thing packed into an empty `current` group. An oversized block
# arriving after other already-accumulated content in the same run (the
# common case -- e.g. following a short heading/intro block) fell through
# to the untouched `current and current_words + words > max_words` branch
# and was accepted unsplit, exactly reproducing the original bug. Found via
# the Milestone 6 controlled corpus rebuild (KP2 still had 560 passages
# over max_words, max 723 words, after v1.1.0 was deployed and only 16 of
# ~560+ affected blocks were actually split). Fixed by checking `words >
# max_words` unconditionally and flushing any accumulated `current` group
# first. See docs/oversized-passage-retrieval-subchunks-experiment.md.
ALGORITHM_VERSION = "1.1.1"

BOUNDARY_RULES_VERSION = 1
EXCLUSION_RULES_VERSION = 1


@dataclass(frozen=True)
class PassageConfig:
    # Passage size targets, in words (see module docstring for how these
    # were derived from the real corpus's block-size distribution).
    min_preferred_words: int = 60
    target_min_words: int = 150
    target_max_words: int = 250
    # Hard ceiling before an oversized passage is deterministically split.
    # Kept comfortably under the embedding model's 512-token limit (see
    # embedding_config.py) since ~400 words is typically 500-600 subword
    # tokens for dense financial text -- segmentation, not embedding, is
    # responsible for preventing truncation.
    max_words: int = 400

    # A passage below this word count that isn't a legitimate short heading
    # (i.e. has no heading_text and couldn't be merged with an adjacent
    # passage without crossing a heading boundary) is excluded as too short
    # to carry independent meaning.
    min_words_hard_floor: int = 15

    # A passage whose raw-text digit ratio is at or above this threshold is
    # excluded as numeric-heavy, mirroring ExtractionConfig's
    # `max_numeric_density_for_narrative` block-level check -- this is a
    # secondary net for paragraphs whose *aggregate* text is number-dense
    # even though no single contributing block was numeric-dominant enough
    # to be excluded at the block-classification stage.
    numeric_density_exclusion_threshold: float = 0.35
    # Only applied to passages at least this long, so a short passage that
    # happens to mention a few figures isn't falsely flagged.
    numeric_density_min_words: int = 20


PASSAGE_CONFIG = PassageConfig()


def compute_configuration_hash(config: PassageConfig = PASSAGE_CONFIG) -> str:
    """Deterministic fingerprint of everything that can change segmentation output.

    An identical fingerprint means: same algorithm version, same boundary/
    exclusion rule versions, same tokenizer version (passage.token_count
    reuses the M3 tokenizer), same size thresholds. Any change to those
    inputs produces a different hash, which is what triggers a fresh
    `PassageSegmentationRun` instead of a skip.
    """
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "boundary_rules_version": BOUNDARY_RULES_VERSION,
        "exclusion_rules_version": EXCLUSION_RULES_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "config": asdict(config),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
