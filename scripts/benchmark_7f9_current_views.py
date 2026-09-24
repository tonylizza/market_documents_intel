"""Track 7F.9 (closing the 7F.7a.5 benchmark caveat): repeated-run latency of
representative `app.current_*` view queries.

Compares an app database whose active publication resolves content through
the versioned shared-artifact COALESCE joins (app_0014+) against one whose
active publication stores content inline in the thin tables (built before
app_0014). Read-only: SELECT statements only, never writes.

Usage:
    .venv/bin/python scripts/benchmark_7f9_current_views.py \
        --db shared=postgresql://.../market_documents_app_7f9 \
        --db inline=postgresql://.../market_documents_app [--runs 50] [--warmup 5]
"""

from __future__ import annotations

import argparse
import statistics
import time

import psycopg

# Each query takes one parameter chosen from the active publication itself
# (never hardcoded ids), so both databases run the same logical workload.
QUERIES: dict[str, tuple[str, str]] = {
    "comparison_by_id": (
        "SELECT id FROM app.current_report_comparisons ORDER BY earlier_period_end DESC NULLS LAST, id LIMIT 1",
        "SELECT * FROM app.current_report_comparisons WHERE id = %s",
    ),
    "passage_comparisons_for_comparison": (
        "SELECT id FROM app.current_report_comparisons ORDER BY earlier_period_end DESC NULLS LAST, id LIMIT 1",
        "SELECT id, alignment_status, confidence, content_score, collision_flag FROM app.current_passage_comparisons "
        "WHERE report_comparison_id = %s ORDER BY id LIMIT 200",
    ),
    "retrieval_contexts_for_comparison": (
        "SELECT id FROM app.current_report_comparisons ORDER BY earlier_period_end DESC NULLS LAST, id LIMIT 1",
        "SELECT id, passage_id, alignment_status, confidence, report_side FROM app.current_retrieval_contexts "
        "WHERE report_comparison_id = %s ORDER BY id LIMIT 200",
    ),
    "language_signals_for_comparison_category": (
        "SELECT id FROM app.current_report_comparisons ORDER BY earlier_period_end DESC NULLS LAST, id LIMIT 1",
        "SELECT passage_id, report_side, subcategory, raw_count, adjusted_count FROM app.current_passage_language_signals "
        "WHERE report_comparison_id = %s AND category = 'financial_condition'",
    ),
    "qa_chunks_for_report": (
        "SELECT report_id FROM app.current_qa_chunks ORDER BY report_id LIMIT 1",
        "SELECT id, chunk_index, text, page_start, page_end FROM app.current_qa_chunks "
        "WHERE report_id = %s ORDER BY chunk_index",
    ),
    "qa_chunk_vector_top10": (
        "SELECT embedding::text FROM app.current_qa_chunks ORDER BY id LIMIT 1",
        "SELECT id, report_id, chunk_index FROM app.current_qa_chunks ORDER BY embedding <=> %s::vector LIMIT 10",
    ),
}


def percentile(values: list[float], q: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def bench(url: str, runs: int, warmup: int) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    with psycopg.connect(url) as conn:
        conn.execute("SET default_transaction_read_only = on")
        for name, (param_sql, sql) in QUERIES.items():
            row = conn.execute(param_sql).fetchone()
            if row is None:
                out[name] = {"median_ms": float("nan"), "p95_ms": float("nan"), "rows": 0}
                continue
            timings = []
            n_rows = 0
            for i in range(warmup + runs):
                t0 = time.perf_counter()
                n_rows = len(conn.execute(sql, (row[0],)).fetchall())
                elapsed = (time.perf_counter() - t0) * 1000
                if i >= warmup:
                    timings.append(elapsed)
            out[name] = {
                "median_ms": statistics.median(timings),
                "p95_ms": percentile(timings, 0.95),
                "rows": n_rows,
            }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", action="append", required=True, help="label=postgresql://... (repeatable)")
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--warmup", type=int, default=5)
    a = ap.parse_args()
    results = {}
    for spec in a.db:
        label, url = spec.split("=", 1)
        results[label] = bench(url, a.runs, a.warmup)
    labels = list(results)
    print("| query | " + " | ".join(f"{lab} median ms | {lab} p95 ms | {lab} rows" for lab in labels) + " |")
    print("|---|" + "---|---|---|" * len(labels))
    for name in QUERIES:
        cells = []
        for lab in labels:
            r = results[lab][name]
            cells += [f"{r['median_ms']:.2f}", f"{r['p95_ms']:.2f}", str(r["rows"])]
        print(f"| {name} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
