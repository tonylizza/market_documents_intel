"""Milestone 7B.1d Phases 2-5: orchestrates qa_experiment schema setup,
deterministic chunk construction (chunk_strategies.py), token-budget
enforcement (token_budget.py), embedding (reusing the pinned research-layer
model wrapper), validation, and persistence -- entirely against the
APPLICATION database's active publication, entirely outside the
`app`/`app_internal` publication lifecycle.

Usage:
    .venv/bin/python -m market_documents.qa_experiment.build_chunks \
        [--strategies HEADING_PLUS_PASSAGE,LOCAL_WINDOW,...] [--reset]

Requires `APP_DATABASE_URL` pointed at an app_publisher-credentialed
connection (same requirement as `market-documents publish build`) -- this
script creates the `qa_experiment` schema and writes to it.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import math
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from market_documents.config import get_settings
from market_documents.publishing.session import app_session_scope
from market_documents.qa_experiment import chunk_strategies as strategies_mod
from market_documents.qa_experiment.labels import derive_chunk_id
from market_documents.qa_experiment.models import ChunkCandidate, ComparisonRow, PassageRow
from market_documents.qa_experiment.token_budget import enforce_token_budget
from market_documents.services.embedding_config import EMBEDDING_DIMENSION, MODEL_NAME, MODEL_REVISION
from market_documents.services.passage_embedding import get_embedding_model

logger = logging.getLogger(__name__)

SCHEMA_SQL_PATH = Path(__file__).resolve().parents[3] / "scripts" / "sql" / "qa_experiment_schema.sql"
AUDIT_DIR = Path(__file__).resolve().parents[3] / "data" / "audits"


def _split_sql_statements(script: str) -> list[str]:
    lines = [line for line in script.splitlines() if not line.strip().startswith("--")]
    statements = "\n".join(lines).split(";")
    return [s.strip() for s in statements if s.strip()]


def apply_schema(session: Session, *, reset: bool) -> None:
    if reset:
        session.execute(text("DROP SCHEMA IF EXISTS qa_experiment CASCADE"))
    for statement in _split_sql_statements(SCHEMA_SQL_PATH.read_text()):
        session.execute(text(statement))
    session.commit()


def load_active_publication_version(session: Session) -> str:
    row = session.execute(
        text(
            """
            SELECT p.publication_version
            FROM app_internal.application_state s
            JOIN app_internal.publications p ON p.id = s.active_publication_id
            WHERE s.singleton_key = 'active'
            """
        )
    ).first()
    if row is None:
        raise RuntimeError("No active publication -- run `market-documents publish build`/`activate` first.")
    return row[0]


def load_passages(session: Session) -> list[PassageRow]:
    rows = session.execute(
        text(
            """
            SELECT id, report_id, company_id, passage_index, heading, text, word_count,
                   first_page_number, last_page_number
            FROM app.current_passages
            ORDER BY report_id, passage_index
            """
        )
    ).all()
    return [
        PassageRow(
            id=r.id,
            report_id=r.report_id,
            company_id=r.company_id,
            passage_index=r.passage_index,
            heading=r.heading,
            text=r.text,
            word_count=r.word_count,
            first_page_number=r.first_page_number,
            last_page_number=r.last_page_number,
        )
        for r in rows
    ]


def load_comparisons(session: Session) -> list[ComparisonRow]:
    rows = session.execute(
        text(
            """
            SELECT pc.id, pc.report_comparison_id, rc.company_id, pc.earlier_passage_id,
                   pc.later_passage_id, pc.alignment_status, rc.earlier_period_end, rc.later_period_end
            FROM app.current_passage_comparisons pc
            JOIN app.current_report_comparisons rc ON rc.id = pc.report_comparison_id
            """
        )
    ).all()
    return [
        ComparisonRow(
            id=r.id,
            report_comparison_id=r.report_comparison_id,
            company_id=r.company_id,
            earlier_passage_id=r.earlier_passage_id,
            later_passage_id=r.later_passage_id,
            alignment_status=r.alignment_status,
            earlier_period_end=r.earlier_period_end,
            later_period_end=r.later_period_end,
        )
        for r in rows
    ]


def _group_by_report(passages: list[PassageRow]) -> dict[uuid.UUID, list[PassageRow]]:
    grouped: dict[uuid.UUID, list[PassageRow]] = defaultdict(list)
    for p in passages:
        grouped[p.report_id].append(p)
    return grouped


def build_candidates(
    strategy_names: list[str],
    passages_by_report: dict[uuid.UUID, list[PassageRow]],
    comparisons: list[ComparisonRow],
    passage_by_id: dict[uuid.UUID, PassageRow],
    count_tokens,
) -> list[ChunkCandidate]:
    candidates: list[ChunkCandidate] = []
    for report_passages in passages_by_report.values():
        if strategies_mod.STRATEGY_HEADING_PLUS_PASSAGE in strategy_names:
            candidates.extend(strategies_mod.build_heading_plus_passage_chunks(report_passages))
        if strategies_mod.STRATEGY_PREVIOUS_PLUS_CURRENT in strategy_names:
            candidates.extend(strategies_mod.build_previous_plus_current_chunks(report_passages))
        if strategies_mod.STRATEGY_CURRENT_PLUS_NEXT in strategy_names:
            candidates.extend(strategies_mod.build_current_plus_next_chunks(report_passages))
        if strategies_mod.STRATEGY_LOCAL_WINDOW in strategy_names:
            candidates.extend(strategies_mod.build_local_window_chunks(report_passages))
        if strategies_mod.STRATEGY_FIXED_TOKEN_WINDOW_256_64 in strategy_names:
            candidates.extend(strategies_mod.build_fixed_token_window_chunks(report_passages, count_tokens))
    if strategies_mod.STRATEGY_COMPARISON_PAIR in strategy_names:
        candidates.extend(strategies_mod.build_comparison_pair_chunks(comparisons, passage_by_id))
    return candidates


def _heading_text_for(candidate: ChunkCandidate, passages_by_report: dict[uuid.UUID, list[PassageRow]], passage_by_id: dict[uuid.UUID, PassageRow]) -> str | None:
    anchor = passage_by_id.get(candidate.anchor_passage_id)
    if anchor is None:
        return None
    report_passages = passages_by_report.get(anchor.report_id, [])
    heading, _source_id = strategies_mod.resolve_effective_heading(report_passages, anchor.passage_index)
    return heading


class DedupedChunk:
    __slots__ = ("chunk_id", "strategy", "text", "report_id", "company_id", "page_start", "page_end", "truncation_policy", "anchor_passage_ids", "members", "comparison_contexts")

    def __init__(self, chunk_id: uuid.UUID, candidate: ChunkCandidate) -> None:
        self.chunk_id = chunk_id
        self.strategy = candidate.strategy
        self.text = candidate.text
        self.report_id = candidate.report_id
        self.company_id = candidate.company_id
        self.page_start = candidate.page_start
        self.page_end = candidate.page_end
        self.truncation_policy = candidate.truncation_policy
        self.anchor_passage_ids: set[uuid.UUID] = {candidate.anchor_passage_id}
        self.members: set[tuple[uuid.UUID, str]] = {(m.passage_id, m.role) for m in candidate.members}
        self.comparison_contexts: set[tuple] = {
            (c.passage_comparison_id, c.report_comparison_id, c.report_side, c.alignment_status, c.earlier_period_end, c.later_period_end)
            for c in candidate.comparison_contexts
        }

    def merge(self, candidate: ChunkCandidate) -> None:
        self.anchor_passage_ids.add(candidate.anchor_passage_id)
        self.members |= {(m.passage_id, m.role) for m in candidate.members}
        self.comparison_contexts |= {
            (c.passage_comparison_id, c.report_comparison_id, c.report_side, c.alignment_status, c.earlier_period_end, c.later_period_end)
            for c in candidate.comparison_contexts
        }


def deduplicate(candidates: list[ChunkCandidate], publication_version: str) -> dict[uuid.UUID, DedupedChunk]:
    deduped: dict[uuid.UUID, DedupedChunk] = {}
    for c in candidates:
        text_hash = hashlib.sha256(c.text.encode("utf-8")).hexdigest()
        chunk_id = derive_chunk_id(publication_version, c.strategy, text_hash)
        if chunk_id in deduped:
            deduped[chunk_id].merge(c)
        else:
            deduped[chunk_id] = DedupedChunk(chunk_id, c)
    return deduped


def embed_chunks(deduped: dict[uuid.UUID, DedupedChunk], batch_size: int) -> dict[uuid.UUID, list[float]]:
    model = get_embedding_model()
    ids = list(deduped.keys())
    vectors: dict[uuid.UUID, list[float]] = {}
    for start in range(0, len(ids), batch_size):
        batch_ids = ids[start : start + batch_size]
        texts = [deduped[cid].text for cid in batch_ids]
        encoded = model.encode_batch(texts)
        for cid, enc in zip(batch_ids, encoded):
            vectors[cid] = enc.vector
    return vectors


def persist(
    session: Session,
    deduped: dict[uuid.UUID, DedupedChunk],
    vectors: dict[uuid.UUID, list[float]],
    publication_version: str,
    count_tokens,
) -> None:
    chunk_rows: list[dict[str, Any]] = []
    passage_rows: list[dict[str, Any]] = []
    context_rows: list[dict[str, Any]] = []

    for chunk_id, dc in deduped.items():
        vector = vectors[chunk_id]
        if not all(math.isfinite(x) for x in vector):
            raise ValueError(f"Non-finite vector component for chunk {chunk_id} ({dc.strategy})")
        if len(vector) != EMBEDDING_DIMENSION:
            raise ValueError(f"Wrong dimension for chunk {chunk_id}: {len(vector)} != {EMBEDDING_DIMENSION}")
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0.0:
            raise ValueError(f"Zero vector for chunk {chunk_id} ({dc.strategy})")
        text_hash = hashlib.sha256(dc.text.encode("utf-8")).hexdigest()
        anchor_passage_id = sorted(dc.anchor_passage_ids, key=str)[0]
        chunk_rows.append(
            {
                "id": chunk_id,
                "publication_version": publication_version,
                "report_id": dc.report_id,
                "company_id": dc.company_id,
                "anchor_passage_id": anchor_passage_id,
                "chunk_strategy": dc.strategy,
                "chunk_text": dc.text,
                "token_count": count_tokens(dc.text),
                "word_count": len(dc.text.split()),
                "page_start": dc.page_start,
                "page_end": dc.page_end,
                "text_hash": text_hash,
                "embedding_model": MODEL_NAME,
                "embedding_model_revision": MODEL_REVISION,
                "dimensions": EMBEDDING_DIMENSION,
                "embedding_literal": "[" + ",".join(repr(x) for x in vector) + "]",
                "truncation_policy": dc.truncation_policy,
            }
        )
        for order, (passage_id, role) in enumerate(sorted(dc.members, key=lambda m: (m[1], str(m[0])))):
            passage_rows.append(
                {"chunk_id": chunk_id, "passage_id": passage_id, "passage_order": order, "role": role}
            )
        for pc_id, rc_id, side, alignment_status, earlier_end, later_end in dc.comparison_contexts:
            context_rows.append(
                {
                    "chunk_id": chunk_id,
                    "report_comparison_id": rc_id,
                    "passage_comparison_id": pc_id,
                    "report_side": side,
                    "alignment_status": alignment_status,
                    "earlier_period_end": earlier_end,
                    "later_period_end": later_end,
                }
            )

    if chunk_rows:
        session.execute(
            text(
                """
                INSERT INTO qa_experiment.retrieval_chunks
                    (id, publication_version, report_id, company_id, anchor_passage_id, chunk_strategy,
                     chunk_text, token_count, word_count, page_start, page_end, text_hash,
                     embedding_model, embedding_model_revision, dimensions, embedding, truncation_policy)
                VALUES
                    (:id, :publication_version, :report_id, :company_id, :anchor_passage_id, :chunk_strategy,
                     :chunk_text, :token_count, :word_count, :page_start, :page_end, :text_hash,
                     :embedding_model, :embedding_model_revision, :dimensions,
                     CAST(:embedding_literal AS vector), :truncation_policy)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            chunk_rows,
        )
    if passage_rows:
        session.execute(
            text(
                """
                INSERT INTO qa_experiment.retrieval_chunk_passages (chunk_id, passage_id, passage_order, role)
                VALUES (:chunk_id, :passage_id, :passage_order, :role)
                ON CONFLICT (chunk_id, passage_id, role) DO NOTHING
                """
            ),
            passage_rows,
        )
    if context_rows:
        session.execute(
            text(
                """
                INSERT INTO qa_experiment.retrieval_chunk_contexts
                    (chunk_id, report_comparison_id, passage_comparison_id, report_side,
                     alignment_status, earlier_period_end, later_period_end)
                VALUES
                    (:chunk_id, :report_comparison_id, :passage_comparison_id, :report_side,
                     :alignment_status, :earlier_period_end, :later_period_end)
                ON CONFLICT (chunk_id, passage_comparison_id, report_side) DO NOTHING
                """
            ),
            context_rows,
        )
    session.commit()


def write_audits(deduped: dict[uuid.UUID, DedupedChunk], vectors: dict[uuid.UUID, list[float]], publication_version: str) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    with (AUDIT_DIR / "qa_chunk_embedding_audit.csv").open("w") as f:
        f.write("chunk_id,strategy,dimensions,vector_norm,vector_is_nonzero\n")
        for chunk_id, dc in deduped.items():
            vector = vectors[chunk_id]
            norm = math.sqrt(sum(x * x for x in vector))
            f.write(f"{chunk_id},{dc.strategy},{len(vector)},{norm:.6f},{norm != 0.0}\n")

    with (AUDIT_DIR / "qa_chunk_lineage_audit.csv").open("w") as f:
        f.write("chunk_id,strategy,anchor_passage_ids,member_passage_ids,member_roles\n")
        for chunk_id, dc in deduped.items():
            members_sorted = sorted(dc.members, key=lambda m: (m[1], str(m[0])))
            f.write(
                f"{chunk_id},{dc.strategy},"
                f"{'|'.join(str(a) for a in sorted(dc.anchor_passage_ids, key=str))},"
                f"{'|'.join(str(p) for p, _ in members_sorted)},"
                f"{'|'.join(r for _, r in members_sorted)}\n"
            )

    with (AUDIT_DIR / "qa_chunk_vector_integrity_audit.csv").open("w") as f:
        f.write("chunk_id,strategy,dimensions_ok,vector_nonzero,text_hash_self_consistent\n")
        for chunk_id, dc in deduped.items():
            vector = vectors[chunk_id]
            dims_ok = len(vector) == EMBEDDING_DIMENSION
            norm = math.sqrt(sum(x * x for x in vector))
            recomputed_hash = hashlib.sha256(dc.text.encode("utf-8")).hexdigest()
            expected_id = derive_chunk_id(publication_version, dc.strategy, recomputed_hash)
            hash_self_consistent = expected_id == chunk_id
            f.write(f"{chunk_id},{dc.strategy},{dims_ok},{norm != 0.0},{hash_self_consistent}\n")

    with (AUDIT_DIR / "qa_chunk_duplicate_audit.csv").open("w") as f:
        f.write("text_hash,strategy,chunk_count\n")
        seen: dict[tuple[str, str], int] = {}
        for dc in deduped.values():
            h = hashlib.sha256(dc.text.encode("utf-8")).hexdigest()
            key = (h, dc.strategy)
            seen[key] = seen.get(key, 0) + 1
        for (h, strat), count in seen.items():
            if count > 1:
                f.write(f"{h},{strat},{count}\n")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strategies",
        default=",".join(strategies_mod.ALL_STRATEGIES),
        help="Comma-separated strategy names to build (default: all prioritized strategies).",
    )
    parser.add_argument("--reset", action="store_true", help="Drop and recreate qa_experiment schema first.")
    args = parser.parse_args()
    strategy_names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    for name in strategy_names:
        if name not in strategies_mod.ALL_STRATEGIES:
            raise SystemExit(f"Unknown strategy {name!r}; valid: {strategies_mod.ALL_STRATEGIES}")

    settings = get_settings()
    with app_session_scope(settings.app_database_url) as session:
        apply_schema(session, reset=args.reset)
        publication_version = load_active_publication_version(session)
        logger.info("Building strategies %s against publication %s", strategy_names, publication_version)

        passages = load_passages(session)
        comparisons = load_comparisons(session)
        passage_by_id = {p.id: p for p in passages}
        passages_by_report = _group_by_report(passages)
        text_by_passage_id = {p.id: p.text for p in passages}

        model = get_embedding_model()
        count_tokens = model.count_tokens

        candidates = build_candidates(strategy_names, passages_by_report, comparisons, passage_by_id, count_tokens)
        logger.info("Built %d raw chunk candidates before token-budget enforcement/dedup", len(candidates))

        for c in candidates:
            heading_text = _heading_text_for(c, passages_by_report, passage_by_id)
            enforce_token_budget(c, count_tokens, text_by_passage_id, heading_text=heading_text)

        deduped = deduplicate(candidates, publication_version)
        logger.info("Deduplicated to %d unique chunks", len(deduped))

        vectors = embed_chunks(deduped, batch_size=settings.embedding_batch_size)
        persist(session, deduped, vectors, publication_version, count_tokens)
        write_audits(deduped, vectors, publication_version)

    counts: dict[str, int] = {}
    for dc in deduped.values():
        counts[dc.strategy] = counts.get(dc.strategy, 0) + 1
    logger.info("Chunk counts by strategy: %s", counts)


if __name__ == "__main__":
    main()
