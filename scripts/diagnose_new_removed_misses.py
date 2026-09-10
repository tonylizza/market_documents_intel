"""Milestone 7 disagreement investigation: for a specific flagged NEW/REMOVED
"likely missed correspondence" case, determine exactly where in the frozen
pipeline the true match was lost -- never retrieved as a semantic candidate,
retrieved but below the acceptance gate, or retrieved and accepted-eligible
but lost to a competing claimant in conflict resolution.

Read-only diagnostic. Does not modify the pipeline or persist anything.
"""

import sys
import uuid

from sqlalchemy import select

from market_documents.db.session import get_session
from market_documents.models.alignment import PassageAlignment
from market_documents.models.passage import Passage
from market_documents.services.alignment_candidates import get_semantic_candidates
from market_documents.services.alignment_config import ALIGNMENT_CONFIG
from market_documents.services.passage_alignment import (
    compute_content_score,
    compute_lexical_features,
    get_current_alignment_run,
    lexical_composite,
)


def diagnose(session, *, later_passage_id: str, earlier_candidate_hint_text: str, report_pair_earlier_id: str, report_pair_later_id: str):
    later_passage = session.get(Passage, uuid.UUID(later_passage_id))
    print(f"\n=== later passage {later_passage_id} ===")
    print(f"heading={later_passage.heading_text!r} type={later_passage.passage_type.value} words={later_passage.word_count}")
    print(f"text[:150]={later_passage.raw_text[:150]!r}")

    from market_documents.models.report_pair import ReportPair

    pair = session.scalar(
        select(ReportPair).where(
            ReportPair.earlier_report_id == uuid.UUID(report_pair_earlier_id),
            ReportPair.later_report_id == uuid.UUID(report_pair_later_id),
        )
    )
    run = get_current_alignment_run(session, pair.id)
    print(f"alignment_run={run.id} earlier_seg_run={run.earlier_segmentation_run_id} earlier_emb_run={run.earlier_embedding_run_id}")

    from market_documents.models.embedding import PassageEmbedding, PassageRetrievalChunk

    vector = session.scalar(
        select(PassageEmbedding.embedding).where(
            PassageEmbedding.embedding_run_id == run.later_embedding_run_id, PassageEmbedding.passage_id == later_passage.id
        )
    )
    basis = "canonical"
    if vector is None:
        vector = session.scalar(
            select(PassageRetrievalChunk.embedding)
            .where(
                PassageRetrievalChunk.embedding_run_id == run.later_embedding_run_id,
                PassageRetrievalChunk.passage_id == later_passage.id,
            )
            .order_by(PassageRetrievalChunk.chunk_index)
            .limit(1)
        )
        basis = "retrieval_chunk"
    print(f"later passage embedding basis: {basis}, vector present: {vector is not None}")

    candidates = get_semantic_candidates(
        session,
        later_embedding_vector=list(vector),
        earlier_embedding_run_id=run.earlier_embedding_run_id,
        top_k=ALIGNMENT_CONFIG.top_k,
        min_semantic_similarity=ALIGNMENT_CONFIG.min_semantic_similarity,
    )
    print(f"\ntop_k={ALIGNMENT_CONFIG.top_k} min_semantic_similarity={ALIGNMENT_CONFIG.min_semantic_similarity}")
    print(f"semantic candidates returned: {len(candidates)}")
    found = None
    for c in candidates:
        marker = ""
        if earlier_candidate_hint_text[:40].lower() in c.passage.raw_text[:200].lower():
            marker = "  <-- HINT MATCH"
            found = c
        print(f"  idx={c.passage.passage_index} sim={c.semantic_similarity:.4f} src={c.candidate_source} heading={c.passage.heading_text!r} text[:60]={c.passage.raw_text[:60]!r}{marker}")

    if found is None:
        # Not in top-k -- check raw similarity directly against the hinted candidate by locating it via text search.
        hinted = session.scalar(
            select(Passage).where(
                Passage.report_id == uuid.UUID(report_pair_earlier_id),
                Passage.raw_text.ilike(f"%{earlier_candidate_hint_text[:40]}%"),
            ).limit(1)
        )
        if hinted is None:
            print("  Could not locate hinted candidate passage by text search either.")
            return
        # Recompute this specific pair's semantic similarity directly (1 - cosine distance) via SQL.
        from sqlalchemy import text as sqltext

        session.execute(sqltext("SET LOCAL enable_indexscan = off"))
        session.execute(sqltext("SET LOCAL enable_bitmapscan = off"))
        dist = session.scalar(
            select(PassageEmbedding.embedding.cosine_distance(list(vector))).where(
                PassageEmbedding.embedding_run_id == run.earlier_embedding_run_id, PassageEmbedding.passage_id == hinted.id
            )
        )
        if dist is None:
            print(f"  Hinted candidate {hinted.id} has no canonical embedding in this run (may be a retrieval chunk case).")
        else:
            sim = 1.0 - float(dist)
            verdict = "BELOW min_semantic_similarity floor" if sim < ALIGNMENT_CONFIG.min_semantic_similarity else "above floor but outside top_k"
            print(f"  Hinted candidate {hinted.id} true semantic_similarity={sim:.4f} -- {verdict}")
        return

    # Found in top-k: score it and check the acceptance gate + conflict.
    features = compute_lexical_features(found.passage, later_passage)
    composite = lexical_composite(features)
    content_score = compute_content_score(
        semantic_similarity=found.semantic_similarity, lexical_composite=composite, heading_similarity=features.heading_similarity
    )
    print(f"\nHint candidate content_score={content_score:.4f} (gate: min_content_score_for_acceptance={ALIGNMENT_CONFIG.min_content_score_for_acceptance})")
    if content_score < ALIGNMENT_CONFIG.min_content_score_for_acceptance:
        print("  VERDICT: retrieved as a candidate but REJECTED by the content_score acceptance gate.")
        return

    # Passed the gate -- check whether it was accepted by a different later passage instead (conflict).
    existing = session.scalar(
        select(PassageAlignment).where(
            PassageAlignment.alignment_run_id == run.id,
            PassageAlignment.earlier_passage_id == found.passage.id,
            PassageAlignment.primary_alignment.is_(True),
        )
    )
    if existing is None:
        print("  VERDICT: cleared the gate and was NOT claimed by anyone else in the persisted result -- unexpected, needs closer look.")
    elif existing.later_passage_id == later_passage.id:
        print("  VERDICT: this pair IS the accepted alignment already -- pilot label may be miscounting a real match as missed.")
    else:
        winner = session.get(Passage, existing.later_passage_id)
        print(f"  VERDICT: cleared the gate but LOST to a competing claim -- earlier passage was instead matched to later passage_index={winner.passage_index if winner else '?'} (later_passage_id={existing.later_passage_id}), status={existing.alignment_status.value}, combined_score={existing.combined_score}")


CASES = [
    dict(
        later_passage_id="386aded7-5c15-48e4-9937-72535eeaf4fe",
        earlier_candidate_hint_text="The economic outlook remains uncertain. The private healthcare market is experiencing a sta",
        report_pair_earlier_id="71c5bb69-2abf-4b9a-8167-cc0fc0645540",
        report_pair_later_id="627c643f-cfeb-4d8c-a6aa-cae4f04f54ae",
    ),
    dict(
        later_passage_id="9c94fd59-e75b-45c6-9fc4-263983046f48",
        earlier_candidate_hint_text="As the Group is focused on mineral exploration in Central Africa, management make resource allocatio",
        report_pair_earlier_id="15fb5b0d-cb2a-4633-8851-a31c37abe2f1",
        report_pair_later_id="8ac44907-16b3-41be-b0aa-a2047f51d366",
    ),
    dict(
        later_passage_id="804f9295-e10d-4bc8-bda8-024fef2dd69e",
        earlier_candidate_hint_text="Environmental Responsibility and Stewardship Southern Palladium entrenches principles of environment",
        report_pair_earlier_id="67ce190f-2d0c-4c58-ab57-aee35a812471",
        report_pair_later_id="1bcb0b78-58e8-4ac2-a2ee-0c25ef6364a3",
    ),
]


if __name__ == "__main__":
    with get_session() as session:
        for case in CASES:
            diagnose(session, **case)
