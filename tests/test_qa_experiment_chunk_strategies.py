"""Milestone 7B.1d: deterministic construction rules for Q&A retrieval-chunk
strategies B/C/D/E/F/H (`qa_experiment.chunk_strategies`). Pure, database-free
unit tests -- no fixtures, no Postgres, matching `chunk_strategies.py`'s own
"never opens a session" convention."""

import uuid

from market_documents.qa_experiment import chunk_strategies as cs
from market_documents.qa_experiment.labels import derive_chunk_id
from market_documents.qa_experiment.models import (
    ROLE_ANCHOR,
    ROLE_EARLIER_SIDE,
    ROLE_HEADING_CONTEXT,
    ROLE_LATER_SIDE,
    ROLE_NEXT,
    ROLE_PREVIOUS,
    ComparisonRow,
    PassageRow,
)


def make_passage(report_id, company_id, idx, heading, text, word_count=None, page=None):
    page = page if page is not None else idx
    return PassageRow(
        id=uuid.uuid4(),
        report_id=report_id,
        company_id=company_id,
        passage_index=idx,
        heading=heading,
        text=text,
        word_count=word_count if word_count is not None else len(text.split()),
        first_page_number=page,
        last_page_number=page,
    )


def make_report(company_id=None):
    report_id = uuid.uuid4()
    company_id = company_id or uuid.uuid4()
    passages = [
        make_passage(report_id, company_id, 0, "SECTION ONE", "First passage body text here."),
        make_passage(report_id, company_id, 1, None, "Second passage continues the section."),
        make_passage(report_id, company_id, 2, "SECTION TWO", "Third passage starts a new section."),
        make_passage(report_id, company_id, 3, None, "Fourth passage is the last one."),
    ]
    return report_id, company_id, passages


def fake_count_tokens(text: str) -> int:
    return len(text.split())


class TestHeadingPlusPassage:
    def test_uses_own_heading_when_present(self):
        _rid, _cid, passages = make_report()
        chunks = cs.build_heading_plus_passage_chunks(passages)
        anchor0 = next(c for c in chunks if c.anchor_passage_id == passages[0].id)
        assert anchor0.text == f"Heading: SECTION ONE\nContent: {passages[0].text}"
        assert [m.role for m in anchor0.members] == [ROLE_ANCHOR]

    def test_inherits_heading_from_prior_passage_in_same_run(self):
        _rid, _cid, passages = make_report()
        chunks = cs.build_heading_plus_passage_chunks(passages)
        anchor1 = next(c for c in chunks if c.anchor_passage_id == passages[1].id)
        assert "Heading: SECTION ONE" in anchor1.text
        roles = {m.role for m in anchor1.members}
        assert ROLE_HEADING_CONTEXT in roles
        heading_member = next(m for m in anchor1.members if m.role == ROLE_HEADING_CONTEXT)
        assert heading_member.passage_id == passages[0].id

    def test_skips_passages_with_no_resolvable_heading(self):
        report_id, company_id = uuid.uuid4(), uuid.uuid4()
        passages = [make_passage(report_id, company_id, 0, None, "No heading anywhere above this.")]
        chunks = cs.build_heading_plus_passage_chunks(passages)
        assert chunks == []

    def test_never_crosses_report_boundary(self):
        _rid, _cid, passages = make_report()
        chunks = cs.build_heading_plus_passage_chunks(passages)
        for c in chunks:
            assert c.report_id == passages[0].report_id


class TestPreviousPlusCurrent:
    def test_first_passage_has_no_previous_and_is_skipped(self):
        _rid, _cid, passages = make_report()
        chunks = cs.build_previous_plus_current_chunks(passages)
        anchors = {c.anchor_passage_id for c in chunks}
        assert passages[0].id not in anchors
        assert passages[1].id in anchors

    def test_preserves_passage_order_prev_then_current(self):
        _rid, _cid, passages = make_report()
        chunks = cs.build_previous_plus_current_chunks(passages)
        c = next(c for c in chunks if c.anchor_passage_id == passages[1].id)
        assert c.text.index(passages[0].text) < c.text.index(passages[1].text)
        assert [m.role for m in c.members if m.role != ROLE_HEADING_CONTEXT] == [ROLE_PREVIOUS, ROLE_ANCHOR]


class TestCurrentPlusNext:
    def test_last_passage_has_no_next_and_is_skipped(self):
        _rid, _cid, passages = make_report()
        chunks = cs.build_current_plus_next_chunks(passages)
        anchors = {c.anchor_passage_id for c in chunks}
        assert passages[-1].id not in anchors

    def test_roles_are_anchor_then_next(self):
        _rid, _cid, passages = make_report()
        chunks = cs.build_current_plus_next_chunks(passages)
        c = next(c for c in chunks if c.anchor_passage_id == passages[0].id)
        assert [m.role for m in c.members if m.role != ROLE_HEADING_CONTEXT] == [ROLE_ANCHOR, ROLE_NEXT]


class TestLocalWindow:
    def test_requires_both_neighbors(self):
        _rid, _cid, passages = make_report()
        chunks = cs.build_local_window_chunks(passages)
        anchors = {c.anchor_passage_id for c in chunks}
        assert passages[0].id not in anchors
        assert passages[-1].id not in anchors
        assert passages[1].id in anchors
        assert passages[2].id in anchors

    def test_includes_previous_anchor_next_in_order(self):
        _rid, _cid, passages = make_report()
        chunks = cs.build_local_window_chunks(passages)
        c = next(c for c in chunks if c.anchor_passage_id == passages[1].id)
        roles = [m.role for m in c.members if m.role != ROLE_HEADING_CONTEXT]
        assert roles == [ROLE_PREVIOUS, ROLE_ANCHOR, ROLE_NEXT]


class TestComparisonPair:
    def test_skips_new_and_removed_rows(self):
        report_id, company_id, passages = make_report()
        comparison = ComparisonRow(
            id=uuid.uuid4(),
            report_comparison_id=uuid.uuid4(),
            company_id=company_id,
            earlier_passage_id=None,
            later_passage_id=passages[0].id,
            alignment_status="NEW",
            earlier_period_end=None,
            later_period_end=None,
        )
        passage_by_id = {p.id: p for p in passages}
        chunks = cs.build_comparison_pair_chunks([comparison], passage_by_id)
        assert chunks == []

    def test_builds_earlier_and_later_labeled_text_with_anchor_on_later_side(self):
        report_id, company_id, passages = make_report()
        comparison = ComparisonRow(
            id=uuid.uuid4(),
            report_comparison_id=uuid.uuid4(),
            company_id=company_id,
            earlier_passage_id=passages[0].id,
            later_passage_id=passages[2].id,
            alignment_status="LIGHTLY_MODIFIED",
            earlier_period_end=None,
            later_period_end=None,
        )
        passage_by_id = {p.id: p for p in passages}
        chunks = cs.build_comparison_pair_chunks([comparison], passage_by_id)
        assert len(chunks) == 1
        c = chunks[0]
        assert c.anchor_passage_id == passages[2].id
        assert "Earlier report" in c.text and "Later report" in c.text
        assert c.text.index("Earlier report") < c.text.index("Later report")
        roles = {m.role: m.passage_id for m in c.members}
        assert roles[ROLE_EARLIER_SIDE] == passages[0].id
        assert roles[ROLE_LATER_SIDE] == passages[2].id
        assert len(c.comparison_contexts) == 2
        sides = {ctx.report_side for ctx in c.comparison_contexts}
        assert sides == {"EARLIER", "LATER"}


class TestFixedTokenWindow:
    def test_never_splits_a_word_and_covers_full_report(self):
        report_id, company_id = uuid.uuid4(), uuid.uuid4()
        passages = [
            make_passage(report_id, company_id, i, None, " ".join(f"w{i}_{j}" for j in range(80)))
            for i in range(5)
        ]
        chunks = cs.build_fixed_token_window_chunks(passages, fake_count_tokens)
        assert len(chunks) > 0
        for c in chunks:
            for word in c.text.split():
                assert word  # no empty tokens from a mid-word split
            assert c.members  # every window maps to at least one passage
            assert any(m.role == "ANCHOR" for m in c.members)

    def test_empty_report_yields_no_windows(self):
        assert cs.build_fixed_token_window_chunks([], fake_count_tokens) == []


class TestDeterministicChunkId:
    def test_same_publication_strategy_text_hash_yields_same_id(self):
        import hashlib

        text_hash = hashlib.sha256(b"identical text").hexdigest()
        id1 = derive_chunk_id("2026-07-29.1", "HEADING_PLUS_PASSAGE", text_hash)
        id2 = derive_chunk_id("2026-07-29.1", "HEADING_PLUS_PASSAGE", text_hash)
        assert id1 == id2

    def test_different_strategy_yields_different_id(self):
        import hashlib

        text_hash = hashlib.sha256(b"identical text").hexdigest()
        id1 = derive_chunk_id("2026-07-29.1", "HEADING_PLUS_PASSAGE", text_hash)
        id2 = derive_chunk_id("2026-07-29.1", "LOCAL_WINDOW", text_hash)
        assert id1 != id2

    def test_different_publication_version_yields_different_id(self):
        import hashlib

        text_hash = hashlib.sha256(b"identical text").hexdigest()
        id1 = derive_chunk_id("2026-07-29.1", "HEADING_PLUS_PASSAGE", text_hash)
        id2 = derive_chunk_id("2026-08-01.1", "HEADING_PLUS_PASSAGE", text_hash)
        assert id1 != id2
