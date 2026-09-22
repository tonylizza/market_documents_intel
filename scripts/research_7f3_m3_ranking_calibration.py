"""Track 7F.3 reconnaissance-only research script.

Read-only corpus analysis supporting `docs/financial-condition-ranking-calibration-7f3.md`.
Reconstructs M1 (rate difference), M3 (hit-share difference), and M6b
(subcategory composition distance) for every current `ReportPairLanguageFeatures`
row from raw `passage_language_signals` / `passage_language_category_hits` rows,
using the exact `feature_eligible_primary` population (primary_narrative_eligible
AND feature_eligible) and the exact custom-taxonomy category set (risk,
financial_condition, governance, strategy) that
`financial_language_signals._aggregate_pair_features` uses in production.

Cross-checks the M1 reconstruction against the persisted
`financial_condition_rate_earlier`/`_later` columns for every pair (must match
exactly, mirroring 7F.1/7F.2's own convention).

Never writes to any production table, `findings.py`, or config. Retained under
scripts/ as a research artifact per the 7D.5a-established convention for this
kind of ad hoc, read-only milestone analysis.
"""

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select

from market_documents.db.session import get_session
from market_documents.models.company import Company
from market_documents.models.enums import LanguageSignalQuality, ReportSide
from market_documents.models.financial_language import (
    PassageLanguageCategoryHit,
    PassageLanguageSignal,
    ReportPairLanguageFeatures,
)
from market_documents.models.report_pair import ReportPair
from market_documents.services.financial_language_signals import get_current_language_signal_runs_by_pair

TICKERS = ["ACT", "BEL", "KP2", "SBP", "SDL", "SUR"]
CUSTOM_TAXONOMY_CATEGORIES = ("risk", "financial_condition", "governance", "strategy")
SUBCATEGORIES = [
    "revenue",
    "cost_margin",
    "cash_flow",
    "debt",
    "liquidity",
    "capital_expenditure",
    "impairment",
    "working_capital",
    "dividends",
    "tax",
    "restructuring",
    "acquisitions_disposals",
]


@dataclass
class SidePop:
    words: int = 0
    category_hits: dict = field(default_factory=lambda: defaultdict(int))
    subcat_hits: dict = field(default_factory=lambda: defaultdict(int))  # financial_condition only


@dataclass
class PairResult:
    ticker: str
    pair_id: str
    earlier_period_end: str
    later_period_end: str
    quality: str
    primary_eligible: bool
    earlier: SidePop
    later: SidePop
    persisted_rate_earlier: float | None
    persisted_rate_later: float | None
    persisted_m1: float | None


def rate_per_1000(hits: int, words: int) -> float | None:
    return (1000.0 * hits / words) if words > 0 else None


def m1(pr: PairResult) -> float | None:
    re_ = rate_per_1000(pr.earlier.category_hits["financial_condition"], pr.earlier.words)
    rl = rate_per_1000(pr.later.category_hits["financial_condition"], pr.later.words)
    if re_ is None or rl is None:
        return None
    return rl - re_


def total_taxonomy_hits(side: SidePop) -> int:
    return sum(side.category_hits[c] for c in CUSTOM_TAXONOMY_CATEGORIES)


def m3(pr: PairResult) -> float | None:
    h_e = pr.earlier.category_hits["financial_condition"]
    h_l = pr.later.category_hits["financial_condition"]
    H_e = total_taxonomy_hits(pr.earlier)
    H_l = total_taxonomy_hits(pr.later)
    if H_e == 0 or H_l == 0:
        return None
    return (h_l / H_l) - (h_e / H_e)


def subcat_composition(side: SidePop) -> list[float]:
    total = sum(side.subcat_hits[s] for s in SUBCATEGORIES)
    if total == 0:
        return [0.0] * len(SUBCATEGORIES)
    return [side.subcat_hits[s] / total for s in SUBCATEGORIES]


def cosine(a: list[float], b: list[float]) -> float | None:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)


def m6b(pr: PairResult) -> float | None:
    ce = subcat_composition(pr.earlier)
    cl = subcat_composition(pr.later)
    cos = cosine(ce, cl)
    if cos is None:
        return None
    return 1 - cos


def m6a(pr: PairResult) -> float:
    we = pr.earlier.words
    wl = pr.later.words
    inten_e = [rate_per_1000(pr.earlier.subcat_hits[s], we) or 0.0 for s in SUBCATEGORIES]
    inten_l = [rate_per_1000(pr.later.subcat_hits[s], wl) or 0.0 for s in SUBCATEGORIES]
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(inten_e, inten_l)))


def load_pairs() -> list[PairResult]:
    results: list[PairResult] = []
    with get_session() as session:
        for ticker in TICKERS:
            company = session.scalar(select(Company).where(Company.ticker == ticker))
            if company is None:
                continue
            pairs = session.scalars(select(ReportPair).where(ReportPair.company_id == company.id)).all()
            pair_ids = [p.id for p in pairs]
            current_runs = get_current_language_signal_runs_by_pair(session, pair_ids)
            for pair in pairs:
                run = current_runs.get(pair.id)
                if run is None:
                    continue
                lf = session.scalar(
                    select(ReportPairLanguageFeatures).where(ReportPairLanguageFeatures.language_signal_run_id == run.id)
                )
                if lf is None:
                    continue

                signals = session.scalars(
                    select(PassageLanguageSignal).where(
                        PassageLanguageSignal.language_signal_run_id == run.id,
                        PassageLanguageSignal.primary_narrative_eligible.is_(True),
                        PassageLanguageSignal.feature_eligible.is_(True),
                    )
                ).all()
                sig_ids = [s.id for s in signals]
                side_by_sig = {s.id: s.report_side for s in signals}
                words_by_side = {ReportSide.EARLIER: 0, ReportSide.LATER: 0}
                for s in signals:
                    words_by_side[s.report_side] += s.passage_word_count

                earlier = SidePop(words=words_by_side[ReportSide.EARLIER])
                later = SidePop(words=words_by_side[ReportSide.LATER])

                if sig_ids:
                    hit_rows = session.scalars(
                        select(PassageLanguageCategoryHit).where(
                            PassageLanguageCategoryHit.passage_language_signal_id.in_(sig_ids)
                        )
                    ).all()
                    for hr in hit_rows:
                        side = side_by_sig[hr.passage_language_signal_id]
                        target = earlier if side == ReportSide.EARLIER else later
                        target.category_hits[hr.category] += hr.hit_count
                        if hr.category == "financial_condition":
                            target.subcat_hits[hr.subcategory] += hr.hit_count

                results.append(
                    PairResult(
                        ticker=ticker,
                        pair_id=str(pair.id),
                        earlier_period_end=str(pair.earlier_report.period_end),
                        later_period_end=str(pair.later_report.period_end),
                        quality=lf.report_side_signal_quality.value,
                        primary_eligible=lf.report_side_primary_eligible,
                        earlier=earlier,
                        later=later,
                        persisted_rate_earlier=lf.financial_condition_rate_earlier,
                        persisted_rate_later=lf.financial_condition_rate_later,
                        persisted_m1=lf.financial_condition_language_change,
                    )
                )
    return results


def pstats(values: list[float]) -> dict:
    if not values:
        return {}
    s = sorted(values)
    n = len(s)

    def pct(p: float) -> float:
        if n == 1:
            return s[0]
        k = (n - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return s[int(k)]
        return s[f] + (s[c] - s[f]) * (k - f)

    mean = sum(s) / n
    med = statistics.median(s)
    mad = statistics.median([abs(x - med) for x in s])
    return {
        "N": n,
        "min": s[0],
        "max": s[-1],
        "mean": mean,
        "median": med,
        "stdev": statistics.pstdev(s),
        "MAD": mad,
        "MAD_scaled_1.4826": mad * 1.4826,
        "p25": pct(0.25),
        "p50": pct(0.50),
        "p75": pct(0.75),
        "p80": pct(0.80),
        "p85": pct(0.85),
        "p90": pct(0.90),
        "p95": pct(0.95),
        "p99": pct(0.99),
    }


def eligible(pr_row: dict) -> bool:
    return pr_row["quality"] in ("GOOD", "USABLE") and pr_row["primary_eligible"]


def threshold_sensitivity(rows: list[dict]) -> None:
    elig_rows = [r for r in rows if eligible(r) and r["M3"] is not None]
    print(f"\n# THRESHOLD SENSITIVITY (eligible pairs only, n={len(elig_rows)})\n")

    def report(label: str, thresh: float):
        passing = [r for r in elig_rows if abs(r["M3"]) >= thresh]
        companies = sorted({r["ticker"] for r in passing})
        top = sorted(passing, key=lambda r: abs(r["M3"]), reverse=True)[:5]
        sbp_included = any(r["ticker"] == "SBP" and r["earlier"] == "2023-12-31" for r in passing)
        act_included = any(r["ticker"] == "ACT" and r["earlier"] == "2017-06-30" for r in passing)
        bel_included = any(r["ticker"] == "BEL" for r in passing)
        print(f"{label} (thresh={thresh:.4f}): n={len(passing)} ({100*len(passing)/len(elig_rows):.0f}%) "
              f"companies={companies} SBP23-24={sbp_included} ACT17-18={act_included} BEL_any={bel_included}")
        for r in top:
            print(f"    {r['ticker']} {r['earlier']}->{r['later']} M3={r['M3']:.4f} h=({r['h_e']},{r['h_l']}) H=({r['H_e']},{r['H_l']})")

    print("-- A. Absolute share-point thresholds --")
    for t in [0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10]:
        report(f"abs>={t}", t)

    abs_vals = sorted(abs(r["M3"]) for r in elig_rows)
    ps = pstats(abs_vals)
    print("\n-- B. Percentile thresholds (of eligible |M3| distribution) --")
    for p in ["p75", "p80", "p85", "p90", "p95"]:
        report(p, ps[p])

    med = statistics.median([r["M3"] for r in elig_rows])
    mad = statistics.median([abs(r["M3"] - med) for r in elig_rows])
    print(f"\n-- C. Robust statistical thresholds (median|M3| over signed corpus)="
          f"{med:.4f}, MAD={mad:.4f}, scaled MAD (x1.4826)={mad*1.4826:.4f} --")
    for k in [1.0, 1.5, 2.0]:
        report(f"median+{k}MAD_scaled", abs(med) + k * mad * 1.4826)

    print("\n-- D. Hybrid thresholds: max(min_abs, percentile) --")
    for min_abs in [0.02, 0.03]:
        for p in ["p75", "p85"]:
            report(f"hybrid(min_abs={min_abs},{p})", max(min_abs, ps[p]))


def quality_gate_breakdown(rows: list[dict]) -> None:
    print("\n# QUALITY GATE BREAKDOWN (all 25 current pairs)\n")
    for r in sorted(rows, key=lambda r: (r["ticker"], r["earlier"])):
        gate = eligible(r)
        print(f"{r['ticker']} {r['earlier']}->{r['later']}: quality={r['quality']} "
              f"primary_eligible={r['primary_eligible']} gate_pass={gate} "
              f"H_e={r['H_e']} H_l={r['H_l']} M3={r['M3']}")


def m1_m3_m6b_classification(rows: list[dict]) -> None:
    elig_rows = [r for r in rows if eligible(r) and r["M3"] is not None]
    m1_abs = sorted(abs(r["M1"]) for r in elig_rows if r["M1"] is not None)
    m3_abs = sorted(abs(r["M3"]) for r in elig_rows)
    m6b_abs = sorted(r["M6b"] for r in elig_rows if r["M6b"] is not None)
    m1_hi = pstats(m1_abs)["p75"]
    m3_hi = pstats(m3_abs)["p75"]
    m6b_hi = pstats(m6b_abs)["p75"]
    print(f"\n# M1/M3/M6b CLASSIFICATION (p75 cutoffs: M1={m1_hi:.4f}, M3={m3_hi:.4f}, M6b={m6b_hi:.4f})\n")
    for r in sorted(elig_rows, key=lambda r: abs(r["M3"]), reverse=True):
        m1h = abs(r["M1"]) >= m1_hi
        m3h = abs(r["M3"]) >= m3_hi
        m6h = r["M6b"] >= m6b_hi
        if m1h and m3h and m6h:
            cls = "A_all_agree_large"
        elif m1h and not m3h:
            cls = "B_M1_high_M3_low"
        elif m3h and not m1h:
            cls = "C_M3_high_M1_low"
        elif m6h and not m1h and not m3h:
            cls = "D_composition_high_only"
        else:
            cls = "E_all_low_or_mixed"
        print(f"{r['ticker']} {r['earlier']}->{r['later']}: M1={r['M1']:.4f} M3={r['M3']:.4f} "
              f"M6b={r['M6b']:.4f} class={cls}")


def bootstrap_perturbation(rows: list[dict], top_n: int = 10) -> None:
    elig_rows = [r for r in rows if eligible(r) and r["M3"] is not None]
    top = sorted(elig_rows, key=lambda r: abs(r["M3"]), reverse=True)[:top_n]
    print(f"\n# COUNT-PERTURBATION STABILITY (top {top_n} |M3| eligible pairs)\n")
    for r in top:
        h_e, h_l, H_e, H_l = r["h_e"], r["h_l"], r["H_e"], r["H_l"]
        base = (h_l / H_l) - (h_e / H_e)
        variants = {}
        for delta in [-5, -2, -1, 1, 2, 5]:
            new_h_l = max(0, h_l + delta)
            new_H_l = max(new_h_l, H_l + delta)
            variants[f"later{delta:+d}"] = (new_h_l / new_H_l) - (h_e / H_e) if new_H_l > 0 else None
        p = h_l / H_l if H_l else 0
        se = math.sqrt(p * (1 - p) / H_l) if H_l else 0
        ci95 = (base - 1.96 * se, base + 1.96 * se)
        print(f"{r['ticker']} {r['earlier']}->{r['later']}: base_M3={base:.4f} h_l={h_l} H_l={H_l} "
              f"binomial_se(later_share)={se:.4f} approx_95CI_M3=({ci95[0]:.4f},{ci95[1]:.4f})")
        print(f"    perturbations: {json.dumps({k: (round(v,4) if v is not None else None) for k,v in variants.items()})}")


def main() -> None:
    pairs = load_pairs()
    print(f"# loaded {len(pairs)} current pairs\n")

    # cross-check M1 reconstruction against persisted columns
    mismatches = 0
    for pr in pairs:
        recon_e = rate_per_1000(pr.earlier.category_hits["financial_condition"], pr.earlier.words)
        recon_l = rate_per_1000(pr.later.category_hits["financial_condition"], pr.later.words)
        pe, pl = pr.persisted_rate_earlier, pr.persisted_rate_later
        ok_e = pe is None and recon_e is None or (pe is not None and recon_e is not None and abs(pe - recon_e) < 1e-6)
        ok_l = pl is None and recon_l is None or (pl is not None and recon_l is not None and abs(pl - recon_l) < 1e-6)
        if not (ok_e and ok_l):
            mismatches += 1
            print(f"MISMATCH {pr.ticker} {pr.earlier_period_end}->{pr.later_period_end}: "
                  f"recon=({recon_e},{recon_l}) persisted=({pe},{pl})")
    print(f"# cross-check mismatches: {mismatches}/{len(pairs)}\n")

    rows = []
    for pr in pairs:
        row = {
            "ticker": pr.ticker,
            "earlier": pr.earlier_period_end,
            "later": pr.later_period_end,
            "quality": pr.quality,
            "primary_eligible": pr.primary_eligible,
            "h_e": pr.earlier.category_hits["financial_condition"],
            "h_l": pr.later.category_hits["financial_condition"],
            "H_e": total_taxonomy_hits(pr.earlier),
            "H_l": total_taxonomy_hits(pr.later),
            "w_e": pr.earlier.words,
            "w_l": pr.later.words,
            "M1": m1(pr),
            "M3": m3(pr),
            "M6a": m6a(pr),
            "M6b": m6b(pr),
        }
        rows.append(row)

    print("# per-pair rows sorted by |M3|\n")
    rows_sorted = sorted(rows, key=lambda r: abs(r["M3"]) if r["M3"] is not None else -1, reverse=True)
    for r in rows_sorted:
        print(json.dumps(r))

    m3_vals = [r["M3"] for r in rows if r["M3"] is not None]
    m3_abs = [abs(v) for v in m3_vals]
    m1_vals = [r["M1"] for r in rows if r["M1"] is not None]

    print("\n# M3 signed distribution\n", json.dumps(pstats(m3_vals), indent=2))
    print("\n# M3 |absolute| distribution\n", json.dumps(pstats(m3_abs), indent=2))
    print("\n# M1 (for cross-reference) signed distribution\n", json.dumps(pstats(m1_vals), indent=2))

    print("\n# company-level |M3|\n")
    by_ticker = defaultdict(list)
    for r in rows:
        if r["M3"] is not None:
            by_ticker[r["ticker"]].append(r)
    for t in TICKERS:
        trows = by_ticker.get(t, [])
        if not trows:
            print(f"{t}: no eligible pairs")
            continue
        abs_vals = [abs(r["M3"]) for r in trows]
        largest = max(trows, key=lambda r: abs(r["M3"]))
        print(f"{t}: n={len(trows)} min={min(abs_vals):.4f} median={statistics.median(abs_vals):.4f} "
              f"max={max(abs_vals):.4f} largest_pair={largest['earlier']}->{largest['later']} "
              f"M3={largest['M3']:.4f} quality={largest['quality']} h_e={largest['h_e']} h_l={largest['h_l']} "
              f"H_e={largest['H_e']} H_l={largest['H_l']}")

    print("\n# H (denominator) vs |M3| raw pairs for correlation check\n")
    for r in rows_sorted:
        print(f"{r['ticker']} {r['earlier']}->{r['later']}: H_e={r['H_e']} H_l={r['H_l']} "
              f"min_H={min(r['H_e'], r['H_l'])} |M3|={abs(r['M3']) if r['M3'] is not None else None:.4f}"
              if r["M3"] is not None else f"{r['ticker']}: M3=None")

    quality_gate_breakdown(rows)
    threshold_sensitivity(rows)
    m1_m3_m6b_classification(rows)
    bootstrap_perturbation(rows)

    # Spearman correlation min(H_e,H_l) vs |M3| (eligible only)
    elig = [r for r in rows if eligible(r) and r["M3"] is not None]
    minH = [min(r["H_e"], r["H_l"]) for r in elig]
    absm3 = [abs(r["M3"]) for r in elig]
    def spearman(a, b):
        ra = {v: i for i, v in enumerate(sorted(a))}
        rb = {v: i for i, v in enumerate(sorted(b))}
        ranks_a = [ra[v] for v in a]
        ranks_b = [rb[v] for v in b]
        n = len(a)
        d2 = sum((x - y) ** 2 for x, y in zip(ranks_a, ranks_b))
        return 1 - (6 * d2) / (n * (n * n - 1))
    print(f"\n# Spearman rho(min(H_e,H_l), |M3|) over eligible pairs = {spearman(minH, absm3):.4f}")

    print("\n# SUBCATEGORY HIT BREAKDOWN for top 10 |M3| eligible pairs (for manual content validation)\n")
    top10 = sorted(elig, key=lambda r: abs(r["M3"]), reverse=True)[:10]
    top10_ids = {(r["ticker"], r["earlier"], r["later"]) for r in top10}
    for pr in pairs:
        if (pr.ticker, pr.earlier_period_end, pr.later_period_end) not in top10_ids:
            continue
        print(f"{pr.ticker} {pr.earlier_period_end}->{pr.later_period_end}:")
        for s in SUBCATEGORIES:
            he, hl = pr.earlier.subcat_hits[s], pr.later.subcat_hits[s]
            if he or hl:
                print(f"    {s}: earlier={he} later={hl} delta={hl-he}")


if __name__ == "__main__":
    main()
