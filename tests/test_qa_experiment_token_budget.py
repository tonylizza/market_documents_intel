"""Milestone 7B.1d: token-budget reduction policy
(`qa_experiment.token_budget`) for chunks exceeding the pinned model's
512-token ceiling. Pure unit tests with a cheap word-count-based fake
tokenizer, matching `chunk_strategies.py`'s injection convention."""

import uuid

from market_documents.qa_experiment import chunk_strategies as cs
from market_documents.qa_experiment.models import (
    ROLE_ANCHOR,
    ROLE_EARLIER_SIDE,
    ROLE_HEADING_CONTEXT,
    ROLE_LATER_SIDE,
    ROLE_NEXT,
    ROLE_PREVIOUS,
    ChunkCandidate,
    ChunkMember,
)
from market_documents.qa_experiment.token_budget import enforce_token_budget


def count_tokens(text: str) -> int:
    return len(text.split())


def words(prefix: str, n: int) -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


class TestUnderBudget:
    def test_leaves_candidate_unchanged(self):
        anchor_id = uuid.uuid4()
        text_by_id = {anchor_id: "short text"}
        candidate = ChunkCandidate(
            strategy=cs.STRATEGY_HEADING_PLUS_PASSAGE,
            report_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            anchor_passage_id=anchor_id,
            text="short text",
            members=(ChunkMember(anchor_id, ROLE_ANCHOR, 0),),
            page_start=1,
            page_end=1,
        )
        result = enforce_token_budget(candidate, count_tokens, text_by_id, max_tokens=100)
        assert result.text == "short text"
        assert result.truncation_policy == "none"


class TestNeighborStrategyDropOrder:
    def _local_window_candidate(self):
        prev_id, anchor_id, next_id, head_id = (uuid.uuid4() for _ in range(4))
        text_by_id = {prev_id: words("p", 60), anchor_id: words("a", 60), next_id: words("n", 60)}
        candidate = ChunkCandidate(
            strategy=cs.STRATEGY_LOCAL_WINDOW,
            report_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            anchor_passage_id=anchor_id,
            text=f"Heading: H\n{text_by_id[prev_id]}\n\n{text_by_id[anchor_id]}\n\n{text_by_id[next_id]}",
            members=(
                ChunkMember(head_id, ROLE_HEADING_CONTEXT, -1),
                ChunkMember(prev_id, ROLE_PREVIOUS, 0),
                ChunkMember(anchor_id, ROLE_ANCHOR, 1),
                ChunkMember(next_id, ROLE_NEXT, 2),
            ),
            page_start=1,
            page_end=1,
        )
        return candidate, text_by_id, prev_id, anchor_id, next_id

    def test_drops_heading_before_neighbors(self):
        candidate, text_by_id, prev_id, anchor_id, next_id = self._local_window_candidate()
        # 3*60 + 2(heading) = 182 tokens; budget just under that forces one drop.
        result = enforce_token_budget(candidate, count_tokens, text_by_id, heading_text="H", max_tokens=180)
        assert result.truncation_policy == "dropped_heading_context"
        assert all(m.role != ROLE_HEADING_CONTEXT for m in result.members)
        assert any(m.passage_id == prev_id for m in result.members)
        assert any(m.passage_id == next_id for m in result.members)

    def test_never_drops_anchor(self):
        candidate, text_by_id, _prev_id, anchor_id, _next_id = self._local_window_candidate()
        result = enforce_token_budget(candidate, count_tokens, text_by_id, heading_text="H", max_tokens=10)
        assert any(m.passage_id == anchor_id and m.role == ROLE_ANCHOR for m in result.members)
        assert count_tokens(result.text) <= 10 or result.truncation_policy == "anchor_trimmed"

    def test_result_always_within_budget_when_possible(self):
        candidate, text_by_id, _prev_id, _anchor_id, _next_id = self._local_window_candidate()
        result = enforce_token_budget(candidate, count_tokens, text_by_id, heading_text="H", max_tokens=100)
        assert count_tokens(result.text) <= 100


class TestComparisonPairReduction:
    def test_trims_both_sides_never_drops_either(self):
        earlier_id, later_id = uuid.uuid4(), uuid.uuid4()
        text_by_id = {
            earlier_id: ". ".join(f"Earlier sentence {i}" for i in range(80)) + ".",
            later_id: ". ".join(f"Later sentence {i}" for i in range(80)) + ".",
        }
        candidate = ChunkCandidate(
            strategy=cs.STRATEGY_COMPARISON_PAIR,
            report_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            anchor_passage_id=later_id,
            text=f"Earlier report: {text_by_id[earlier_id]}\n\nLater report: {text_by_id[later_id]}",
            members=(ChunkMember(earlier_id, ROLE_EARLIER_SIDE, 0), ChunkMember(later_id, ROLE_LATER_SIDE, 1)),
            page_start=1,
            page_end=1,
        )
        result = enforce_token_budget(candidate, count_tokens, text_by_id, max_tokens=100)
        assert "Earlier report" in result.text
        assert "Later report" in result.text
        assert result.truncation_policy.startswith("trimmed")
        assert count_tokens(result.text) <= 100


class TestNoSentencePunctuationFallback:
    def test_anchor_trim_falls_back_to_word_level_when_no_sentences(self):
        # Regression test for the bug that produced a >512-token embed input
        # during the live corpus build: a run-on anchor with no `.!?` at all
        # (common in table-like/numeric passages) must still be reducible.
        anchor_id = uuid.uuid4()
        run_on_text = words("tok", 200)  # no punctuation anywhere
        text_by_id = {anchor_id: run_on_text}
        candidate = ChunkCandidate(
            strategy=cs.STRATEGY_HEADING_PLUS_PASSAGE,
            report_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            anchor_passage_id=anchor_id,
            text=run_on_text,
            members=(ChunkMember(anchor_id, ROLE_ANCHOR, 0),),
            page_start=1,
            page_end=1,
        )
        result = enforce_token_budget(candidate, count_tokens, text_by_id, max_tokens=50)
        assert count_tokens(result.text) <= 50
        assert result.truncation_policy == "anchor_trimmed"
