"""Track 7F.9 read-only cross-check: research formula == persisted implementation.

Recomputes every 7F.9 topic-change field from raw passage rows with the
unchanged 7F.8/7F.8a research loaders/aggregation
(`research_7f8_discover_metrics_consolidation`,
`research_7f8a_topic_conjunction_evidence`) and compares it, pair by pair,
with the columns persisted on the current `report_pair_language_features`
row. Optionally also lists the Discover findings of the active publication
in an app database, ranked from persisted data.

SELECT-only. Usage:
    .venv/bin/python scripts/research_7f9_implementation_crosscheck.py [--app-url postgresql://...]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import research_7f8_discover_metrics_consolidation as base  # noqa: E402
import research_7f8a_topic_conjunction_evidence as r8a  # noqa: E402

CATS = ("financial_condition", "governance", "uncertainty")


def persisted_features() -> dict[str, dict]:
    from sqlalchemy import select

    from market_documents.db.session import get_session
    from market_documents.models.company import Company
    from market_documents.models.financial_language import ReportPairLanguageFeatures
    from market_documents.models.report_pair import ReportPair
    from market_documents.services.financial_language_signals import get_current_language_signal_runs_by_pair

    out: dict[str, dict] = {}
    with get_session() as s:
        pairs = s.scalars(select(ReportPair)).all()
        runs = get_current_language_signal_runs_by_pair(s, [p.id for p in pairs])
        tick = {c.id: c.ticker for c in s.scalars(select(Company)).all()}
        for p in pairs:
            run = runs.get(p.id)
            if run is None:
                continue
            lf = s.scalar(select(ReportPairLanguageFeatures).where(ReportPairLanguageFeatures.language_signal_run_id == run.id))
            label = f"{tick[p.company_id]} {str(p.earlier_report.period_end)[:4]}->{str(p.later_report.period_end)[:4]}"
            out[label] = {"signal_version": run.signal_version, "lf": lf}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-url", default=None)
    a = ap.parse_args()

    pairs = base.load(None)
    research = r8a.build(pairs)  # all pairs, not only gated -- the implementation persists every pair
    persisted = persisted_features()

    worst: dict[str, float] = {}
    mismatches: list[str] = []
    versions = {v["signal_version"] for v in persisted.values()}
    for p in pairs:
        lf = persisted[p.label]["lf"]
        E, L = base.aggregate(p.rows, "EARLIER"), base.aggregate(p.rows, "LATER")
        checks = {
            "feature_eligible_primary_words_earlier": (E.words, lf.feature_eligible_primary_words_earlier),
            "feature_eligible_primary_words_later": (L.words, lf.feature_eligible_primary_words_later),
            "financial_condition_hits_earlier": (E.cat["financial_condition"], lf.financial_condition_hits_earlier),
            "financial_condition_hits_later": (L.cat["financial_condition"], lf.financial_condition_hits_later),
            "governance_hits_earlier": (E.cat["governance"], lf.governance_hits_earlier),
            "uncertainty_count_earlier": (E.core["uncertainty"], lf.uncertainty_count_earlier),
        }
        for cat in CATS:
            t = research[cat][p.label]
            direction = (t["net"] > 0) - (t["net"] < 0)
            checks.update({
                f"{cat}_count_change_per_1000": (t["D"], getattr(lf, f"{cat}_count_change_per_1000")),
                f"{cat}_topic_change": (t["C_min"], getattr(lf, f"{cat}_topic_change")),
                f"{cat}_change_consistency_ratio": (t["E_ng"], getattr(lf, f"{cat}_change_consistency_ratio")),
                f"{cat}_largest_passage_share": (t["top1"], getattr(lf, f"{cat}_largest_passage_share")),
                f"{cat}_supporting_hits": (t["same_hits"] if direction else 0, getattr(lf, f"{cat}_supporting_hits")),
                f"{cat}_opposing_hits": (t["opp_hits"] if direction else 0, getattr(lf, f"{cat}_opposing_hits")),
            })
        for name, (want, got) in checks.items():
            if got is None:
                mismatches.append(f"{p.label} {name}: persisted NULL")
                continue
            diff = abs(float(want) - float(got))
            worst[name] = max(worst.get(name, 0.0), diff)
            if diff > 1e-9:
                mismatches.append(f"{p.label} {name}: research {want} vs persisted {got}")

    print(f"pairs compared: {len(pairs)}; persisted signal_version(s): {sorted(versions)}")
    print("| field | max abs diff |\n|---|---|")
    for name in sorted(worst):
        print(f"| {name} | {worst[name]:.3e} |")
    print(f"\nmismatches (> 1e-9): {len(mismatches)}")
    for m in mismatches[:20]:
        print("  " + m)

    print("\n## Anchor values (persisted)\n")
    for cat, labels in r8a.ANCHORS.items():
        for label in labels:
            print(f"- {cat} {label}: {getattr(persisted[label]['lf'], f'{cat}_topic_change'):+.6f}")

    if a.app_url:
        import psycopg

        with psycopg.connect(a.app_url) as conn:
            rows = conn.execute(
                """SELECT d.discovery_type, d.rank, c.ticker, rc.earlier_period_end, rc.later_period_end,
                          d.supporting_metric_key, d.supporting_value
                   FROM app.current_discovery_items d
                   JOIN app.current_companies c ON c.id = d.company_id
                   JOIN app.current_report_comparisons rc ON rc.id = d.report_comparison_id
                   WHERE d.rank_scope = 'corpus'
                   ORDER BY d.discovery_type, d.rank"""
            ).fetchall()
        print("\n## Active publication Discover findings (corpus scope)\n")
        print("| type | rank | pair | metric | value |\n|---|---|---|---|---|")
        for dtype, rank, ticker, e, l, key, value in rows:
            print(f"| {dtype} | {rank} | {ticker} {e.year}->{l.year} | {key} | {value:+.6f} |")


if __name__ == "__main__":
    main()
