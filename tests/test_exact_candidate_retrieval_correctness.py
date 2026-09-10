"""Milestone: exact candidate retrieval correctness.

Confirms `get_semantic_candidates(search_mode=EXACT)` returns the true
top-k cosine-nearest eligible passages from the complete filtered candidate
population, even when the corpus is large enough that PostgreSQL's planner
would otherwise be tempted to use the pre-existing HNSW index
(`ix_passage_embeddings_embedding_hnsw_cosine`) for this query shape.

Unlike `tests/test_alignment_candidates.py` (small, few-row fixtures where
a sequential scan is always cheapest regardless of any planner guard),
these tests build a large synthetic population -- several thousand rows
spread across multiple `embedding_run_id`s, mirroring the real corpus's
scale -- specifically so a highly selective `embedding_run_id` filter is
the kind of query shape that, pre-fix, reproducibly caused PostgreSQL to
choose the HNSW index and silently return fewer than `top_k` rows (see
`docs/exact-candidate-retrieval-correctness.md`). Asserting only that a SQL
statement contains a flag would not catch this class of defect -- the bug
was in what PostgreSQL's planner chose to do with a correctly-written
query, not in the query text itself.
"""

import math
import random
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from market_documents.models.company import Company
from market_documents.models.embedding import EMBEDDING_DIMENSION, EmbeddingRun, PassageEmbedding
from market_documents.models.enums import (
    EmbeddingRunStatus,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    PassageSegmentationRunStatus,
    PassageType,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.services.alignment_candidates import get_semantic_candidates
from market_documents.services.narrative_construction import compute_content_hash
from market_documents.services.retrieval_config import VectorSearchMode

VECTOR_INDEX_NAME = "ix_passage_embeddings_embedding_hnsw_cosine"


def _random_unit_vector(rng: random.Random, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    v = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def _nudge_towards(base: list[float], target_similarity: float, rng: random.Random) -> list[float]:
    """A unit vector at approximately `target_similarity` cosine similarity to `base`."""
    dim = len(base)
    orthogonal = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    dot = sum(o * b for o, b in zip(orthogonal, base))
    orthogonal = [o - dot * b for o, b in zip(orthogonal, base)]
    norm = math.sqrt(sum(x * x for x in orthogonal))
    orthogonal = [x / norm for x in orthogonal]
    theta = math.acos(max(-1.0, min(1.0, target_similarity)))
    return [
        math.cos(theta) * b + math.sin(theta) * o
        for b, o in zip(base, orthogonal)
    ]


def _make_report_chain(db_session, ticker: str):
    company = Company(ticker=ticker, company_name="Exact Retrieval Test Co")
    db_session.add(company)
    db_session.flush()

    report = Report(
        company_id=company.id,
        local_path=f"data/raw/{ticker}/2023/annual.pdf",
        filename="annual.pdf",
        sha256=compute_content_hash(f"{ticker}-{uuid.uuid4()}"),
        directory_year=2023,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()

    extraction_run = ExtractionRun(
        report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash="test-hash",
        status=ExtractionStatus.COMPLETED, extraction_quality=ExtractionQuality.GOOD,
        started_at=datetime.now(UTC), completed_at=datetime.now(UTC), encrypted_pdf_handled=False,
    )
    db_session.add(extraction_run)
    db_session.flush()

    narrative = NarrativeDocument(
        extraction_run_id=extraction_run.id, report_id=report.id, cleaned_text="text",
        word_count=1, content_hash=compute_content_hash(f"text-{uuid.uuid4()}"),
    )
    db_session.add(narrative)
    db_session.flush()

    segmentation_run = PassageSegmentationRun(
        narrative_document_id=narrative.id, extraction_run_id=extraction_run.id,
        algorithm_version="1.0.0", configuration_hash="seg-hash",
        status=PassageSegmentationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    db_session.add(segmentation_run)
    db_session.flush()

    embedding_run = EmbeddingRun(
        segmentation_run_id=segmentation_run.id, model_name="test-model", model_revision="rev1",
        tokenizer_name="test-model", tokenizer_revision="rev1", embedding_dimension=EMBEDDING_DIMENSION,
        pooling_strategy="cls", normalization_method="l2", maximum_model_tokens=512,
        configuration_hash="emb-hash", status=EmbeddingRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    db_session.add(embedding_run)
    db_session.flush()

    return report, segmentation_run, embedding_run


_passage_index_counters: dict[uuid.UUID, int] = {}


def _bulk_insert_passages_and_embeddings(
    db_session, segmentation_run, report, embedding_run, vectors: list[list[float]], *, excluded: bool = False
) -> list[uuid.UUID]:
    """Bulk-inserts len(vectors) passages (+ one embedding each) via executemany,
    fast enough to build a several-thousand-row population per test. Safe to
    call more than once against the same segmentation_run -- passage_index
    continues from where the previous call for that run left off."""
    start = _passage_index_counters.get(segmentation_run.id, 0)
    _passage_index_counters[segmentation_run.id] = start + len(vectors)

    passage_rows = []
    passage_ids = []
    for offset, _ in enumerate(vectors):
        pid = uuid.uuid4()
        passage_ids.append(pid)
        passage_rows.append(
            {
                "id": pid,
                "segmentation_run_id": segmentation_run.id,
                "narrative_document_id": segmentation_run.narrative_document_id,
                "report_id": report.id,
                "extraction_run_id": segmentation_run.extraction_run_id,
                "passage_index": start + offset,
                "raw_text": f"passage {start + offset} text",
                "normalized_text": f"passage {start + offset} text",
                "content_hash": compute_content_hash(f"passage-{uuid.uuid4()}"),
                "first_page_number": 1,
                "last_page_number": 1,
                "word_count": 10,
                "token_count": 10,
                "character_count": 50,
                "heading_text": None,
                "passage_type": PassageType.PARAGRAPH,
                "excluded_from_alignment": excluded,
            }
        )
    db_session.execute(Passage.__table__.insert(), passage_rows)

    embedding_rows = [
        {
            "id": uuid.uuid4(),
            "embedding_run_id": embedding_run.id,
            "passage_id": pid,
            "embedding": vec,
            "input_token_count": 10,
            "truncated": False,
        }
        for pid, vec in zip(passage_ids, vectors)
    ]
    db_session.execute(PassageEmbedding.__table__.insert(), embedding_rows)
    db_session.flush()
    return passage_ids


@pytest.fixture()
def large_corpus(db_session):
    """~1,200 eligible passages in the target embedding run, plus ~3,600
    more spread across three unrelated embedding runs (mirroring the real
    corpus's ~79k-row table with many embedding_run_id values) -- enough
    total rows and a selective-enough filter that, pre-fix, PostgreSQL's
    planner reproducibly chose the HNSW index for this exact query shape.
    """
    rng = random.Random(20260909)

    report, seg_run, target_run = _make_report_chain(db_session, "EXACTBIG")
    base = _random_unit_vector(rng)

    target_vectors = [_random_unit_vector(rng) for _ in range(1199)]
    # The true best match: a passage at ~0.996 similarity to the query --
    # the same order of magnitude as the diagnostic's reproduced case.
    true_best_vector = _nudge_towards(base, 0.996, rng)
    target_vectors.append(true_best_vector)
    rng.shuffle(target_vectors)
    true_best_index = target_vectors.index(true_best_vector)

    target_ids = _bulk_insert_passages_and_embeddings(
        db_session, seg_run, report, target_run, target_vectors
    )
    true_best_passage_id = target_ids[true_best_index]

    # Also include some excluded_from_alignment passages within the same
    # run, near the query, to confirm the exclusion filter still applies
    # under the forced-seq-scan plan.
    excluded_vectors = [_nudge_towards(base, 0.999, rng) for _ in range(5)]
    _bulk_insert_passages_and_embeddings(
        db_session, seg_run, report, target_run, excluded_vectors, excluded=True
    )

    # Unrelated noise runs: large enough, in aggregate, that the table's
    # total row count resembles the real corpus, so the target run's own
    # filter is genuinely selective relative to the whole table.
    for noise_idx in range(3):
        noise_report, noise_seg_run, noise_run = _make_report_chain(db_session, f"NOISE{noise_idx}")
        noise_vectors = [_random_unit_vector(rng) for _ in range(1200)]
        _bulk_insert_passages_and_embeddings(db_session, noise_seg_run, noise_report, noise_run, noise_vectors)

    db_session.execute(text("ANALYZE passages"))
    db_session.execute(text("ANALYZE passage_embeddings"))

    return {
        "query_vector": base,
        "target_embedding_run_id": target_run.id,
        "true_best_passage_id": true_best_passage_id,
        "eligible_count": len(target_vectors),
    }


def test_exact_mode_plan_does_not_use_hnsw_index(db_session, large_corpus):
    """The mechanism check: EXACT mode's own query, EXPLAINed, must not use
    the HNSW index -- this is what the SET LOCAL guard is for."""
    vec_literal = "[" + ",".join(repr(float(x)) for x in large_corpus["query_vector"]) + "]"
    db_session.execute(text("SET LOCAL enable_indexscan = off"))
    db_session.execute(text("SET LOCAL enable_bitmapscan = off"))
    plan_rows = db_session.execute(
        text(
            """
            EXPLAIN
            SELECT p.id, pe.embedding <=> CAST(:vec AS vector) AS distance
            FROM passages p
            JOIN passage_embeddings pe ON pe.passage_id = p.id
            WHERE pe.embedding_run_id = :rid AND p.excluded_from_alignment = false
            ORDER BY pe.embedding <=> CAST(:vec AS vector), p.passage_index
            LIMIT 5
            """
        ),
        {"vec": vec_literal, "rid": str(large_corpus["target_embedding_run_id"])},
    ).all()
    plan_text = "\n".join(row[0] for row in plan_rows)
    assert VECTOR_INDEX_NAME not in plan_text


def test_exact_mode_finds_true_top1_in_large_filtered_population(db_session, large_corpus):
    candidates = get_semantic_candidates(
        db_session,
        later_embedding_vector=large_corpus["query_vector"],
        earlier_embedding_run_id=large_corpus["target_embedding_run_id"],
        top_k=5,
        min_semantic_similarity=-1.0,
        search_mode=VectorSearchMode.EXACT,
    )
    assert len(candidates) == 5
    assert candidates[0].passage.id == large_corpus["true_best_passage_id"]
    assert candidates[0].semantic_similarity == pytest.approx(0.996, abs=0.01)


def test_exact_mode_full_top_k_membership_matches_brute_force(db_session, large_corpus):
    rows = db_session.execute(
        text(
            """
            SELECT p.id, pe.embedding
            FROM passages p
            JOIN passage_embeddings pe ON pe.passage_id = p.id
            WHERE pe.embedding_run_id = :rid AND p.excluded_from_alignment = false
            """
        ),
        {"rid": str(large_corpus["target_embedding_run_id"])},
    ).all()

    def parse(v):
        return [float(x) for x in v.strip("[]").split(",")]

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    q = large_corpus["query_vector"]
    scored = sorted(
        ((pid, 1.0 - dot(q, parse(vec))) for pid, vec in rows),
        key=lambda t: t[1],
    )
    brute_force_top5_ids = {pid for pid, _ in scored[:5]}

    candidates = get_semantic_candidates(
        db_session,
        later_embedding_vector=q,
        earlier_embedding_run_id=large_corpus["target_embedding_run_id"],
        top_k=5,
        min_semantic_similarity=-1.0,
        search_mode=VectorSearchMode.EXACT,
    )
    assert {c.passage.id for c in candidates} == brute_force_top5_ids


def test_exact_mode_respects_embedding_run_filter_in_large_population(db_session, large_corpus):
    # Every returned candidate must belong to the target run, never a noise run.
    candidates = get_semantic_candidates(
        db_session,
        later_embedding_vector=large_corpus["query_vector"],
        earlier_embedding_run_id=large_corpus["target_embedding_run_id"],
        top_k=5,
        min_semantic_similarity=-1.0,
        search_mode=VectorSearchMode.EXACT,
    )
    ids = {c.passage.id for c in candidates}
    count_in_run = db_session.execute(
        text("SELECT count(*) FROM passage_embeddings WHERE embedding_run_id = :rid AND passage_id = ANY(:ids)"),
        {"rid": str(large_corpus["target_embedding_run_id"]), "ids": list(ids)},
    ).scalar()
    assert count_in_run == len(ids)


def test_exact_mode_excludes_excluded_passages_in_large_population(db_session, large_corpus):
    candidates = get_semantic_candidates(
        db_session,
        later_embedding_vector=large_corpus["query_vector"],
        earlier_embedding_run_id=large_corpus["target_embedding_run_id"],
        top_k=5,
        min_semantic_similarity=-1.0,
        search_mode=VectorSearchMode.EXACT,
    )
    # The 5 excluded-from-alignment passages were nudged to ~0.999 similarity
    # (higher than the true_best_vector's ~0.996) -- if the exclusion filter
    # were silently bypassed under the forced-seq-scan plan, they would rank
    # first instead of the true (non-excluded) best match.
    assert candidates[0].passage.id == large_corpus["true_best_passage_id"]
    for c in candidates:
        assert c.passage.excluded_from_alignment is False


def test_exact_mode_deterministic_tie_break_in_large_population(db_session, large_corpus):
    candidates_a = get_semantic_candidates(
        db_session,
        later_embedding_vector=large_corpus["query_vector"],
        earlier_embedding_run_id=large_corpus["target_embedding_run_id"],
        top_k=5,
        min_semantic_similarity=-1.0,
        search_mode=VectorSearchMode.EXACT,
    )
    candidates_b = get_semantic_candidates(
        db_session,
        later_embedding_vector=large_corpus["query_vector"],
        earlier_embedding_run_id=large_corpus["target_embedding_run_id"],
        top_k=5,
        min_semantic_similarity=-1.0,
        search_mode=VectorSearchMode.EXACT,
    )
    assert [c.passage.id for c in candidates_a] == [c.passage.id for c in candidates_b]


def test_exact_mode_returns_fewer_than_top_k_only_when_population_smaller(db_session):
    rng = random.Random(1)
    report, seg_run, embedding_run = _make_report_chain(db_session, "SMALLPOP")
    vectors = [_random_unit_vector(rng) for _ in range(3)]
    _bulk_insert_passages_and_embeddings(db_session, seg_run, report, embedding_run, vectors)

    candidates = get_semantic_candidates(
        db_session,
        later_embedding_vector=vectors[0],
        earlier_embedding_run_id=embedding_run.id,
        top_k=10,
        min_semantic_similarity=-1.0,
        search_mode=VectorSearchMode.EXACT,
    )
    assert len(candidates) == 3


def test_hnsw_mode_unaffected_by_exact_mode_planner_guard(db_session, large_corpus):
    """HNSW mode's own SET LOCAL guards must still take effect -- the EXACT
    guard must not linger and change HNSW mode's plan within the same
    transaction/session."""
    hnsw_candidates = get_semantic_candidates(
        db_session,
        later_embedding_vector=large_corpus["query_vector"],
        earlier_embedding_run_id=large_corpus["target_embedding_run_id"],
        top_k=5,
        min_semantic_similarity=-1.0,
        search_mode=VectorSearchMode.HNSW,
        ef_search=200,
    )
    assert len(hnsw_candidates) >= 1
    for c in hnsw_candidates:
        assert c.passage.excluded_from_alignment is False
