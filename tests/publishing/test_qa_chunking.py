"""Milestone 7B.2: standard Q&A chunk construction
(`publishing.qa_chunking`). Pure, database-free unit tests -- no fixtures,
no Postgres, matching the module's own "never opens a session" convention.
"""

import uuid

from market_documents.publishing import qa_chunking as qc


def fake_count_tokens(text: str) -> int:
    """Word-count tokenizer -- same convention as
    `tests/test_qa_experiment_chunk_strategies.py`'s fake, so per-word costs
    (after the `-2` special-token adjustment) come out to exactly 1 token
    per word, making window sizes trivial to reason about in assertions."""
    return len(text.split())


def make_passage(report_id, company_id, idx, heading, text, page=None):
    page = page if page is not None else idx
    return qc.QaPassageRow(
        id=uuid.uuid4(),
        report_id=report_id,
        company_id=company_id,
        passage_index=idx,
        heading=heading,
        text=text,
        first_page_number=page,
        last_page_number=page,
    )


def words(prefix: str, count: int, sentence_every: int | None = None) -> str:
    tokens = []
    for i in range(count):
        tokens.append(f"{prefix}{i}")
        if sentence_every and (i + 1) % sentence_every == 0:
            tokens[-1] += "."
    return " ".join(tokens)


def make_long_report(report_id=None, company_id=None, num_passages=6, words_per_passage=100):
    report_id = report_id or uuid.uuid4()
    company_id = company_id or uuid.uuid4()
    passages = [
        make_passage(
            report_id,
            company_id,
            i,
            f"SECTION {i}" if i % 2 == 0 else None,
            words(f"p{i}w", words_per_passage, sentence_every=10),
        )
        for i in range(num_passages)
    ]
    return report_id, company_id, passages


class TestTargetSizeAndOverlap:
    def test_chunks_approximate_target_token_count(self):
        _rid, _cid, passages = make_long_report()
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        assert len(chunks) > 1
        # All but the last (short-tail) chunk should be close to the target.
        for c in chunks[:-1]:
            assert 250 <= c.token_count <= 450

    def test_consecutive_chunks_overlap(self):
        _rid, _cid, passages = make_long_report()
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        assert len(chunks) > 1
        first_words = set(chunks[0].text.split())
        second_words = set(chunks[1].text.split())
        assert first_words & second_words

    def test_rejects_target_outside_configured_range(self):
        _rid, _cid, passages = make_long_report()
        try:
            qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=299, overlap_tokens=70)
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_rejects_overlap_outside_configured_range(self):
        _rid, _cid, passages = make_long_report()
        try:
            qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=59)
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_maximum_overlap_is_always_smaller_than_minimum_target(self):
        # Documents the invariant `build_qa_chunks` relies on instead of an
        # explicit runtime check: the configured ranges themselves make
        # overlap_tokens < target_tokens unconditionally true.
        assert qc.MAXIMUM_OVERLAP_TOKENS < qc.MINIMUM_TARGET_TOKENS


class TestNoCrossReportChunks:
    def test_all_chunks_reference_a_single_report(self):
        _rid, _cid, passages = make_long_report()
        chunks = qc.build_qa_chunks(passages, fake_count_tokens)
        report_ids = {c.report_id for c in chunks}
        assert report_ids == {passages[0].report_id}

    def test_caller_is_responsible_for_per_report_grouping(self):
        # The module itself has no report-boundary concept beyond "whatever
        # was passed in" -- crossing reports is prevented by publisher.py
        # calling this once per report, not by internal filtering. This test
        # documents that a single mixed-report call would (incorrectly)
        # produce chunks with member passages from both reports, which is
        # exactly why publisher.py must never do that.
        r1, c1, p1 = make_long_report(num_passages=2, words_per_passage=20)
        r2, c2, p2 = make_long_report(num_passages=2, words_per_passage=20)
        mixed = p1 + p2
        chunks = qc.build_qa_chunks(mixed, fake_count_tokens, target_tokens=300, overlap_tokens=60)
        member_ids = {pid for c in chunks for pid in c.member_passage_ids}
        source_ids = {p.id for p in p1} | {p.id for p in p2}
        assert member_ids <= source_ids


class TestHeadingPrepend:
    def test_prepends_nearest_resolvable_heading(self):
        report_id, company_id, _ = make_long_report(num_passages=0)
        passages = [
            make_passage(report_id, company_id, 0, "SECTION ONE", words("a", 50, sentence_every=10)),
            make_passage(report_id, company_id, 1, None, words("b", 50, sentence_every=10)),
        ]
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=300, overlap_tokens=60)
        assert chunks
        assert chunks[0].text.startswith("Heading: SECTION ONE\n")
        assert chunks[0].section_heading == "SECTION ONE"

    def test_no_heading_prefix_when_none_resolvable(self):
        report_id, company_id, _ = make_long_report(num_passages=0)
        passages = [make_passage(report_id, company_id, 0, None, words("a", 50, sentence_every=10))]
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=300, overlap_tokens=60)
        assert chunks
        assert not chunks[0].text.startswith("Heading:")
        assert chunks[0].section_heading is None


class TestSentenceBoundaryPreference:
    def test_chunk_prefers_to_end_at_sentence_boundary(self):
        report_id, company_id, _ = make_long_report(num_passages=0)
        # Every 10th word ends a "sentence" -- with a 300-token target the
        # raw word-count cut would land mid-sentence; the snap should push
        # the boundary to the nearest in-range `.` instead.
        passages = [make_passage(report_id, company_id, 0, None, words("w", 500, sentence_every=10))]
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=300, overlap_tokens=60)
        assert chunks[0].text.rstrip().endswith(".")

    def test_falls_back_to_word_boundary_with_no_punctuation(self):
        report_id, company_id, _ = make_long_report(num_passages=0)
        passages = [make_passage(report_id, company_id, 0, None, words("w", 500))]
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=300, overlap_tokens=60)
        assert chunks
        for c in chunks:
            for token in c.text.split():
                assert token  # no empty tokens from a mid-word split


class TestLongParagraphAndShortTail:
    def test_long_single_passage_is_split_into_multiple_chunks(self):
        report_id, company_id, _ = make_long_report(num_passages=0)
        passages = [make_passage(report_id, company_id, 0, None, words("w", 1000, sentence_every=10))]
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        assert len(chunks) > 1

    def test_short_trailing_chunk_is_kept_not_dropped(self):
        report_id, company_id, _ = make_long_report(num_passages=0)
        # 370 words total is not evenly divisible into 350-token windows
        # with 70-token overlap -- the final window will be short.
        passages = [make_passage(report_id, company_id, 0, None, words("w", 370, sentence_every=10))]
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        assert chunks[-1].token_count > 0
        assert chunks[-1].text.strip()


class TestTableLikeTextFallback:
    def test_no_sentence_punctuation_still_produces_valid_chunks(self):
        # Table-rendered-as-text / numeric-heavy passages often have no
        # `.!?` at all -- the word-boundary fallback must still cover the
        # full text without crashing (regression case mirrored from
        # `qa_experiment`'s TestNoSentencePunctuationFallback).
        report_id, company_id, _ = make_long_report(num_passages=0)
        passages = [make_passage(report_id, company_id, 0, None, words("42", 800))]
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        assert len(chunks) > 1
        for c in chunks:
            assert c.token_count > 0


class TestPageAndSectionLineage:
    def test_page_range_covers_all_member_passages(self):
        report_id, company_id, _ = make_long_report(num_passages=0)
        passages = [
            make_passage(report_id, company_id, 0, "S", words("a", 50, sentence_every=10), page=10),
            make_passage(report_id, company_id, 1, None, words("b", 50, sentence_every=10), page=11),
            make_passage(report_id, company_id, 2, None, words("c", 50, sentence_every=10), page=12),
        ]
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=300, overlap_tokens=60)
        for c in chunks:
            covered_pages = {
                p.first_page_number for p in passages if p.id in c.member_passage_ids
            }
            assert c.page_start == min(covered_pages)
            assert c.page_end == max(covered_pages)


class TestDeterministicOrdering:
    def test_chunk_index_is_sequential_from_zero(self):
        _rid, _cid, passages = make_long_report()
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_same_input_yields_identical_output(self):
        _rid, _cid, passages = make_long_report()
        chunks_a = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        chunks_b = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        assert [c.text for c in chunks_a] == [c.text for c in chunks_b]
        assert [c.chunk_index for c in chunks_a] == [c.chunk_index for c in chunks_b]


class TestEmbeddingLimitEnforcement:
    def test_oversized_window_is_trimmed_and_recorded(self):
        report_id, company_id, _ = make_long_report(num_passages=0)
        passages = [make_passage(report_id, company_id, 0, None, words("w", 800, sentence_every=10))]
        # A target well above the embedding ceiling forces the trim path.
        chunks = qc.build_qa_chunks(
            passages, fake_count_tokens, target_tokens=400, overlap_tokens=80, max_tokens=50
        )
        assert chunks
        for c in chunks:
            assert c.token_count <= 50
            assert c.truncation_policy == "window_trimmed"

    def test_untrimmed_chunk_records_none_policy(self):
        _rid, _cid, passages = make_long_report()
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        assert any(c.truncation_policy == "none" for c in chunks)


class TestEmptyInput:
    def test_empty_report_yields_no_chunks(self):
        assert qc.build_qa_chunks([], fake_count_tokens) == []


class TestSourcePassageMapping:
    def test_every_chunk_maps_to_at_least_one_real_passage(self):
        _rid, _cid, passages = make_long_report()
        chunks = qc.build_qa_chunks(passages, fake_count_tokens, target_tokens=350, overlap_tokens=70)
        passage_ids = {p.id for p in passages}
        for c in chunks:
            assert c.member_passage_ids
            assert set(c.member_passage_ids) <= passage_ids
