"""Track 7D.6 (docs/7d6-corpus-wide-ceo-chair-review-expansion.md): corpus-wide
CEO_REVIEW/CHAIR_REVIEW schedule localization. Real-corpus inspection found
exactly one semantic-unit candidate worth actually running against the full
corpus (ACT's "Strategy in action" subheading inside the CEO review), but it
only resolved in 1 of 9 real ACT years once extracted -- below the same
multi-year-recurrence bar Track 7D.2 already used to reject ACT's "Capital
management" candidate -- so this milestone configured *zero*
`UnitConfig`/`UNIT_ANALYTICAL_MODES` entries for either schedule, deliberately,
mirroring `tests/test_material_risks_expansion.py`'s own precedent. These
tests document and guard that decision, not a mistake to be silently "fixed"
by a future track without re-doing the real-corpus unit-extraction check.
"""

from market_documents.models.enums import NormalizedSchedule
from market_documents.services import coverage_registry
from market_documents.services.analytical_eligibility import UNIT_ANALYTICAL_MODES
from market_documents.services.cutover_config import NEW_PIPELINE_NARRATIVE_SCOPE
from market_documents.services.schedule_config import SCHEDULE_CONFIG
from market_documents.services.semantic_unit_config import UNIT_CONFIGS

_CEO_CHAIR_SCHEDULES = (NormalizedSchedule.CEO_REVIEW, NormalizedSchedule.CHAIR_REVIEW)


def test_ceo_review_and_chair_review_have_no_configured_narrative_units():
    """Deliberate, documented outcome -- not an oversight. A future track
    that adds a real CEO_REVIEW/CHAIR_REVIEW unit should update this test
    alongside the new UnitConfig, not delete it blindly."""
    assert not [c for c in UNIT_CONFIGS if c.schedule in _CEO_CHAIR_SCHEDULES]


def test_ceo_review_and_chair_review_have_no_analytical_routing_entries():
    unit_keys = {c.unit_key for c in UNIT_CONFIGS if c.schedule in _CEO_CHAIR_SCHEDULES}
    assert not unit_keys
    assert not any(unit_key in unit_keys for _, unit_key in UNIT_ANALYTICAL_MODES)


def test_ceo_review_and_chair_review_have_no_coverage_registry_entries():
    assert not [e for e in coverage_registry.COVERAGE_REGISTRY if e.schedule in _CEO_CHAIR_SCHEDULES]


def test_ceo_review_and_chair_review_not_in_cutover_scope():
    assert not [entry for entry in NEW_PIPELINE_NARRATIVE_SCOPE if entry[1] in _CEO_CHAIR_SCHEDULES]


def test_ceo_review_vocabulary_excludes_bare_role_words():
    """A confirmed real-corpus false-positive risk (see schedule_config.py's
    CEO_REVIEW comment): bare "Chairman"/"CEO"/"Chief Executive" without a
    following functional word recur constantly as director-bio captions and
    org-chart labels throughout every issuer's corpus. None may be
    configured as a standalone vocabulary entry."""
    vocabulary = {v.strip().lower() for v in SCHEDULE_CONFIG.heading_vocabulary[NormalizedSchedule.CEO_REVIEW]}
    forbidden_bare_words = ("chairman", "ceo", "chief executive", "chairperson")
    for word in forbidden_bare_words:
        assert word not in vocabulary, f"{word!r} is a bare role word, not a chapter title"


def test_chair_review_vocabulary_excludes_bare_role_words():
    vocabulary = {v.strip().lower() for v in SCHEDULE_CONFIG.heading_vocabulary[NormalizedSchedule.CHAIR_REVIEW]}
    forbidden_bare_words = ("chairman", "ceo", "chief executive", "chairperson")
    for word in forbidden_bare_words:
        assert word not in vocabulary, f"{word!r} is a bare role word, not a chapter title"


def test_joint_chapter_phrases_are_shared_between_ceo_and_chair_vocabulary():
    """BEL's/SDL's joint chapter headings must be configured under BOTH
    schedules -- the functional-mapping design decision (docs/7d6-...md) --
    not just one of them."""
    ceo_vocabulary = {v.strip().lower() for v in SCHEDULE_CONFIG.heading_vocabulary[NormalizedSchedule.CEO_REVIEW]}
    chair_vocabulary = {v.strip().lower() for v in SCHEDULE_CONFIG.heading_vocabulary[NormalizedSchedule.CHAIR_REVIEW]}
    joint_phrases = {"joint report by the chairman and chief executive", "chairman and ceo report"}
    assert joint_phrases <= ceo_vocabulary
    assert joint_phrases <= chair_vocabulary
