"""Track 7F.10: QA chunk vector search, before vs after.

- **before:** the pre-7F.10 production query. It orders
  `app.current_qa_chunks` by `COALESCE(t.embedding, art.embedding) <=> q`,
  which no index covers, so every query is a full scan + top-N sort (exact).
- **after:** the 7F.10 repository query (`VECTOR_VIEW_SEMANTIC_SQL` in
  `web/lib/repositories/postgres-qa-chunk-repository.ts`, copied verbatim
  below). It runs through `app.current_qa_chunk_vectors`: HNSW on
  `app_artifacts.qa_chunks`, a nested-loop lookup of the active
  publication's thin rows, then a re-sort by exact distance.

Both run under the same session settings the web tier's `queryVector()`
applies in "hnsw" mode (`hnsw.iterative_scan = relaxed_order`,
`hnsw.ef_search`, 200 for the QA path, see `QA_HNSW_EF_SEARCH`), inside a
read-only transaction.

Query vectors are deterministic (seeded) normalized midpoints of two
distinct active chunks' embeddings, so no query is identical to a stored
chunk. Recall is measured against exact ground truth (the "before" query,
which is exact by construction).

Usage:
    .venv/bin/python scripts/benchmark_7f10_qa_vector_search.py \
        --db postgresql://.../market_documents_app_7f10 [--runs 50] [--warmup 5] [--queries 20] [--k 25]
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import time

import psycopg

BEFORE_SQL = """
SELECT qc.id::text AS chunk_id, (1 - (qc.embedding <=> %(q)s::vector)) AS similarity
FROM app.current_qa_chunks qc
ORDER BY qc.embedding <=> %(q)s::vector
LIMIT %(k)s
"""

AFTER_SQL = """
WITH nn AS MATERIALIZED (
  SELECT v.id, v.report_id, v.company_id, v.chunk_index,
         v.embedding <=> %(q)s::vector AS distance,
         v.text, v.section_heading, v.page_start, v.page_end, v.token_count
  FROM app.current_qa_chunk_vectors v
  ORDER BY v.embedding <=> %(q)s::vector
  LIMIT %(k)s
)
SELECT nn.id::text AS chunk_id, (1 - nn.distance) AS similarity
FROM nn
ORDER BY nn.distance, nn.id
"""

# Exact ground truth for the correctness comparison: BEFORE_SQL with an id
# tie-break (BEFORE_SQL's order among exactly-equal distances is arbitrary).
EXACT_SQL = """
SELECT qc.id::text AS chunk_id, (1 - (qc.embedding <=> %(q)s::vector)) AS similarity
FROM app.current_qa_chunks qc
ORDER BY qc.embedding <=> %(q)s::vector, qc.id
LIMIT %(k)s
"""

# Unchanged by 7F.10 (company-scoped searches stay exact on the view); timed
# for context only.
COMPANY_SQL = """
SELECT qc.id::text AS chunk_id, (1 - (qc.embedding <=> %(q)s::vector)) AS similarity
FROM app.current_qa_chunks qc
JOIN app.current_companies c ON c.id = qc.company_id
WHERE c.ticker = %(ticker)s
ORDER BY qc.embedding <=> %(q)s::vector
LIMIT %(k)s
"""


# Overridable via --ef-search; the web tier's value is QA_HNSW_EF_SEARCH in
# postgres-qa-chunk-repository.ts.
EF_SEARCH = 200


def percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def parse_vector(text: str) -> list[float]:
    return [float(x) for x in text.strip("[]").split(",")]


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in values) + "]"


def build_queries(conn: psycopg.Connection, n: int, seed: int) -> list[str]:
    rows = conn.execute(
        "SELECT embedding::text FROM app.current_qa_chunk_vectors ORDER BY id"
    ).fetchall()
    rng = random.Random(seed)
    queries = []
    for _ in range(n):
        a, b = rng.sample(range(len(rows)), 2)
        va, vb = parse_vector(rows[a][0]), parse_vector(rows[b][0])
        mid = [(x + y) / 2 for x, y in zip(va, vb)]
        norm = math.sqrt(sum(x * x for x in mid)) or 1.0
        queries.append(vector_literal([x / norm for x in mid]))
    return queries


def run(conn: psycopg.Connection, sql: str, params: dict) -> list[tuple[str, float]]:
    with conn.transaction():
        conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
        conn.execute(f"SET LOCAL hnsw.ef_search = {EF_SEARCH}")
        return [(r[0], r[1]) for r in conn.execute(sql, params).fetchall()]


def explain(conn: psycopg.Connection, sql: str, params: dict) -> str:
    with conn.transaction():
        conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
        conn.execute(f"SET LOCAL hnsw.ef_search = {EF_SEARCH}")
        rows = conn.execute("EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY ON) " + sql, params).fetchall()
    # Drop the (very long) literal query vector from Order By / Sort Key lines.
    lines = []
    for (line,) in rows:
        if "'[" in line:
            line = line[: line.index("'[")] + "'<query vector>'::vector)"
        lines.append(line)
    return "\n".join(lines)


def time_variant(conn, sql, queries, k, runs, warmup, extra=None) -> dict:
    timings = []
    for i in range(warmup + runs):
        params = {"q": queries[i % len(queries)], "k": k, **(extra or {})}
        t0 = time.perf_counter()
        run(conn, sql, params)
        elapsed = (time.perf_counter() - t0) * 1000
        if i >= warmup:
            timings.append(elapsed)
    return {"median_ms": statistics.median(timings), "p95_ms": percentile(timings, 0.95), "n": len(timings)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--queries", type=int, default=20)
    ap.add_argument("--k", type=int, default=25)
    ap.add_argument("--seed", type=int, default=7010)
    ap.add_argument("--ticker", default="SBP")
    ap.add_argument("--ef-search", type=int, default=200)
    ap.add_argument("--skip-plans", action="store_true")
    a = ap.parse_args()
    global EF_SEARCH
    EF_SEARCH = a.ef_search
    print(f"hnsw.ef_search={EF_SEARCH}")

    with psycopg.connect(a.db, autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = on")
        active_chunks = conn.execute("SELECT count(*) FROM app.current_qa_chunks").fetchone()[0]
        vector_chunks = conn.execute("SELECT count(*) FROM app.current_qa_chunk_vectors").fetchone()[0]
        artifact_chunks = conn.execute("SELECT count(*) FROM app_artifacts.qa_chunks").fetchone()[0]
        print(f"active chunks (current_qa_chunks)={active_chunks} vector view={vector_chunks} "
              f"artifact rows (all generations)={artifact_chunks}")

        queries = build_queries(conn, a.queries, a.seed)

        # Correctness: every query, before (exact) vs after, at k and at 10.
        identical_lists = same_sets = 0
        recalls_k, recalls_10, max_sim_diff, counts = [], [], 0.0, set()
        for q in queries:
            exact = run(conn, EXACT_SQL, {"q": q, "k": a.k})
            after = run(conn, AFTER_SQL, {"q": q, "k": a.k})
            counts.add((len(exact), len(after)))
            exact_ids, after_ids = [r[0] for r in exact], [r[0] for r in after]
            identical_lists += exact_ids == after_ids
            same_sets += set(exact_ids) == set(after_ids)
            recalls_k.append(len(set(exact_ids) & set(after_ids)) / len(exact_ids))
            recalls_10.append(len(set(exact_ids[:10]) & set(after_ids[:10])) / 10)
            exact_sim = dict(exact)
            for cid, sim in after:
                if cid in exact_sim:
                    max_sim_diff = max(max_sim_diff, abs(exact_sim[cid] - sim))
        print(f"\nqueries={len(queries)} k={a.k} result counts (exact, after)={sorted(counts)}")
        print(f"identical ordered top-{a.k}: {identical_lists}/{len(queries)}")
        print(f"identical top-{a.k} set:     {same_sets}/{len(queries)}")
        print(f"mean recall@{a.k}={statistics.mean(recalls_k):.4f} min={min(recalls_k):.4f}")
        print(f"mean recall@10={statistics.mean(recalls_10):.4f} min={min(recalls_10):.4f}")
        print(f"max |similarity diff| on shared ids={max_sim_diff:.2e}")

        print("\n| query | median ms | p95 ms | timed runs |")
        print("|---|---|---|---|")
        for label, sql, extra in (
            ("before: current_qa_chunks (COALESCE)", BEFORE_SQL, None),
            ("after: current_qa_chunk_vectors (HNSW)", AFTER_SQL, None),
            (f"company-scoped ({a.ticker}), unchanged path", COMPANY_SQL, {"ticker": a.ticker}),
        ):
            r = time_variant(conn, sql, queries, a.k, a.runs, a.warmup, extra)
            print(f"| {label} | {r['median_ms']:.2f} | {r['p95_ms']:.2f} | {r['n']} |")

        for label, sql in () if a.skip_plans else (("BEFORE", BEFORE_SQL), ("AFTER", AFTER_SQL)):
            plan = explain(conn, sql, {"q": queries[0], "k": a.k})
            print(f"\n--- {label} plan ---\n{plan}")
            print(f"HNSW index used: {'ix_app_artifacts_qa_chunks_hnsw_cosine' in plan}")


if __name__ == "__main__":
    main()
