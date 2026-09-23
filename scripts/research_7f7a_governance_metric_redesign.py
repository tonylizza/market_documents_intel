"""Track 7F.7a reconnaissance-only research script.

Read-only corpus analysis supporting `docs/governance-metric-redesign-7f7a.md`.
Mirrors `scripts/research_7f3_m3_ranking_calibration.py`'s method exactly, but
for the `governance` custom-taxonomy category instead of `financial_condition`:
reconstructs M1-G (rate difference, the current production metric), M2-G
(length-controlled hit change), M3-G (hit-share difference), and M6-G
(subcategory composition distance over governance's 9 subcategories) for
every current `ReportPairLanguageFeatures` row, from raw
`passage_language_signals` / `passage_language_category_hits` rows, using the
exact `feature_eligible_primary` population and the exact custom-taxonomy
category set (risk, financial_condition, governance, strategy) that
`financial_language_signals._aggregate_pair_features` uses in production.

Cross-checks the M1-G reconstruction against the persisted
`governance_rate_earlier`/`_later` columns for every pair.

Never writes to any production table, `findings.py`, config, or taxonomy.
Retained under scripts/ as a research artifact per the 7D.5a/7F.3-established
convention for this kind of ad hoc, read-only milestone analysis.
"""

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select

from market_documents.db.session import get_session
from market_documents.models.company import Company
from market_documents.models.enums import ReportSide
from market_documents.models.financial_language import (
    PassageLanguageCategoryHit,
    PassageLanguageSignal,
    ReportPairLanguageFeatures,
)
from market_documents.models.report_pair import ReportPair
from market_documents.services.financial_language_signals import get_current_language_signal_runs_by_pair

TICKERS = ["ACT", "BEL", "KP2", "SBP", "SDL", "SUR"]
CUSTOM_TAXONOMY_CATEGORIES = ("risk", "financial_condition", "governance", "strategy")
GOVERNANCE_SUBCATEGORIES = [
    "board",
    "audit",
    "internal_controls",
    "remuneration",
    "ethics",
    "regulatory_compliance",
    "litigation",
    "shareholder_rights",
    "related_party",
]


@dataclass
class SidePop:
    words: int = 0
    category_hits: dict = field(default_factory=lambda: defaultdict(int))
    subcat_hits: dict = field(default_factory=lambda: defaultdict(int))  # governance only


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
    persisted_m1g: float | None


def rate_per_1000(hits: int, words: int) -> float | None:
    return (1000.0 * hits / words) if words > 0 else None


def m1g(pr: PairResult) -> float | None:
    re_ = rate_per_1000(pr.earlier.category_hits["governance"], pr.earlier.words)
    rl = rate_per_1000(pr.later.category_hits["governance"], pr.later.words)
    if re_ is None or rl is None:
        return None
    return rl - re_


def m2g(pr: PairResult) -> float | None:
    """Length-controlled: later-side hits re-normalized by the EARLIER
    side's word count, holding the denominator fixed (same convention 7F.1/
    7F.2/7F.6 used: 'earlier words held fixed')."""
    we = pr.earlier.words
    if we <= 0:
        return None
    re_ = rate_per_1000(pr.earlier.category_hits["governance"], we)
    rl_lengthctl = rate_per_1000(pr.later.category_hits["governance"], we)
    if re_ is None or rl_lengthctl is None:
        return None
    return rl_lengthctl - re_


def total_taxonomy_hits(side: SidePop) -> int:
    return sum(side.category_hits[c] for c in CUSTOM_TAXONOMY_CATEGORIES)


def m3g(pr: PairResult) -> float | None:
    h_e = pr.earlier.category_hits["governance"]
    h_l = pr.later.category_hits["governance"]
    H_e = total_taxonomy_hits(pr.earlier)
    H_l = total_taxonomy_hits(pr.later)
    if H_e == 0 or H_l == 0:
        return None
    return (h_l / H_l) - (h_e / H_e)


def subcat_composition(side: SidePop) -> list[float]:
    total = sum(side.subcat_hits[s] for s in GOVERNANCE_SUBCATEGORIES)
    if total == 0:
        return [0.0] * len(GOVERNANCE_SUBCATEGORIES)
    return [side.subcat_hits[s] / total for s in GOVERNANCE_SUBCATEGORIES]


def cosine(a: list[float], b: list[float]) -> float | None:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)


def m6g(pr: PairResult) -> float | None:
    ce = subcat_composition(pr.earlier)
    cl = subcat_composition(pr.later)
    cos = cosine(ce, cl)
    if cos is None:
        return None
    return 1 - cos


def m6g_intensity(pr: PairResult) -> float:
    we = pr.earlier.words
    wl = pr.later.words
    inten_e = [rate_per_1000(pr.earlier.subcat_hits[s], we) or 0.0 for s in GOVERNANCE_SUBCATEGORIES]
    inten_l = [rate_per_1000(pr.later.subcat_hits[s], wl) or 0.0 for s in GOVERNANCE_SUBCATEGORIES]
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
                        if hr.category == "governance":
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
                        persisted_rate_earlier=lf.governance_rate_earlier,
                        persisted_rate_later=lf.governance_rate_later,
                        persisted_m1g=lf.governance_language_change,
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


def spearman(a, b):
    ra = {v: i for i, v in enumerate(sorted(a))}
    rb = {v: i for i, v in enumerate(sorted(b))}
    ranks_a = [ra[v] for v in a]
    ranks_b = [rb[v] for v in b]
    n = len(a)
    d2 = sum((x - y) ** 2 for x, y in zip(ranks_a, ranks_b))
    return 1 - (6 * d2) / (n * (n * n - 1))


def main() -> None:
    pairs = load_pairs()
    print(f"# loaded {len(pairs)} current pairs\n")

    mismatches = 0
    for pr in pairs:
        recon_e = rate_per_1000(pr.earlier.category_hits["governance"], pr.earlier.words)
        recon_l = rate_per_1000(pr.later.category_hits["governance"], pr.later.words)
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
            "h_e": pr.earlier.category_hits["governance"],
            "h_l": pr.later.category_hits["governance"],
            "H_e": total_taxonomy_hits(pr.earlier),
            "H_l": total_taxonomy_hits(pr.later),
            "w_e": pr.earlier.words,
            "w_l": pr.later.words,
            "M1G": m1g(pr),
            "M2G": m2g(pr),
            "M3G": m3g(pr),
            "M6Gint": m6g_intensity(pr),
            "M6G": m6g(pr),
        }
        rows.append(row)

    print("# per-pair rows sorted by |M3G|\n")
    rows_sorted = sorted(rows, key=lambda r: abs(r["M3G"]) if r["M3G"] is not None else -1, reverse=True)
    for r in rows_sorted:
        print(json.dumps(r))

    m1_vals = [r["M1G"] for r in rows if r["M1G"] is not None]
    m3_vals = [r["M3G"] for r in rows if r["M3G"] is not None]
    m3_abs = [abs(v) for v in m3_vals]

    print("\n# M1G signed distribution\n", json.dumps(pstats(m1_vals), indent=2))
    print("\n# M3G signed distribution\n", json.dumps(pstats(m3_vals), indent=2))
    print("\n# M3G |absolute| distribution\n", json.dumps(pstats(m3_abs), indent=2))

    # Spearman corr M1G vs M3G (magnitude), over ALL non-null pairs (gate-agnostic, matching 7F.6 sec7 convention)
    both = [(abs(r["M1G"]), abs(r["M3G"])) for r in rows if r["M1G"] is not None and r["M3G"] is not None]
    a = [x[0] for x in both]
    b = [x[1] for x in both]
    print(f"\n# Spearman rho(|M1G|, |M3G|) over all {len(both)} non-null pairs = {spearman(a,b):.4f}")

    m1_top10 = {(r['ticker'], r['earlier']) for r in sorted(rows, key=lambda r: abs(r['M1G']) if r['M1G'] is not None else -1, reverse=True)[:10]}
    m3_top10 = {(r['ticker'], r['earlier']) for r in sorted(rows, key=lambda r: abs(r['M3G']) if r['M3G'] is not None else -1, reverse=True)[:10]}
    print(f"# top-10 overlap M1G vs M3G (magnitude, gate-agnostic) = {len(m1_top10 & m3_top10)}/10")

    print("\n# company-level |M1G| vs |M3G|\n")
    by_ticker = defaultdict(list)
    for r in rows:
        by_ticker[r["ticker"]].append(r)
    for t in TICKERS:
        trows = by_ticker.get(t, [])
        if not trows:
            print(f"{t}: no pairs")
            continue
        m1abs = [abs(r["M1G"]) for r in trows if r["M1G"] is not None]
        m3abs = [abs(r["M3G"]) for r in trows if r["M3G"] is not None]
        largest_m1 = max((r for r in trows if r["M1G"] is not None), key=lambda r: abs(r["M1G"]), default=None)
        largest_m3 = max((r for r in trows if r["M3G"] is not None), key=lambda r: abs(r["M3G"]), default=None)
        print(f"{t}: n={len(trows)} "
              f"M1G[min={min(m1abs):.4f} median={statistics.median(m1abs):.4f} max={max(m1abs):.4f}] "
              f"M3G[min={min(m3abs):.4f} median={statistics.median(m3abs):.4f} max={max(m3abs):.4f}] "
              f"largest_M1G_pair={largest_m1['earlier']}->{largest_m1['later']} "
              f"largest_M3G_pair={largest_m3['earlier']}->{largest_m3['later']} "
              f"identity_changes={largest_m1['earlier'] != largest_m3['earlier']}")

    print("\n# QUALITY GATE BREAKDOWN (all 25 current pairs)\n")
    for r in sorted(rows, key=lambda r: (r["ticker"], r["earlier"])):
        gate = eligible(r)
        print(f"{r['ticker']} {r['earlier']}->{r['later']}: quality={r['quality']} "
              f"primary_eligible={r['primary_eligible']} gate_pass={gate} "
              f"h_e={r['h_e']} h_l={r['h_l']} w_e={r['w_e']} w_l={r['w_l']} "
              f"H_e={r['H_e']} H_l={r['H_l']} M1G={r['M1G']} M2G={r['M2G']} M3G={r['M3G']}")

    # threshold sensitivity for M3G
    elig_rows = [r for r in rows if eligible(r) and r["M3G"] is not None]
    print(f"\n# THRESHOLD SENSITIVITY M3G (eligible pairs only, n={len(elig_rows)})\n")

    def report(label: str, thresh: float):
        passing = [r for r in elig_rows if abs(r["M3G"]) >= thresh]
        companies = sorted({r["ticker"] for r in passing})
        top = sorted(passing, key=lambda r: abs(r["M3G"]), reverse=True)[:6]
        print(f"{label} (thresh={thresh:.4f}): n={len(passing)} ({100*len(passing)/len(elig_rows):.0f}%) companies={companies}")
        for r in top:
            print(f"    {r['ticker']} {r['earlier']}->{r['later']} M3G={r['M3G']:.4f} h=({r['h_e']},{r['h_l']}) H=({r['H_e']},{r['H_l']})")

    print("-- A. Absolute share-point thresholds --")
    for t in [0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10]:
        report(f"abs>={t}", t)

    abs_vals = sorted(abs(r["M3G"]) for r in elig_rows)
    ps = pstats(abs_vals)
    print("\n-- B. Percentile thresholds (of eligible |M3G| distribution) --")
    for p in ["p75", "p80", "p85", "p90", "p95"]:
        report(p, ps[p])

    med = statistics.median([r["M3G"] for r in elig_rows])
    mad = statistics.median([abs(r["M3G"] - med) for r in elig_rows])
    print(f"\n-- C. Robust statistical thresholds (median(M3G signed)={med:.4f}, MAD={mad:.4f}, "
          f"scaled MAD (x1.4826)={mad*1.4826:.4f}) --")
    for k in [1.0, 1.5, 2.0]:
        report(f"median+{k}MAD_scaled", abs(med) + k * mad * 1.4826)

    print("\n-- D. Hybrid thresholds: max(min_abs, percentile) --")
    for min_abs in [0.01, 0.02]:
        for p in ["p75", "p85"]:
            report(f"hybrid(min_abs={min_abs},{p})", max(min_abs, ps[p]))

    # denominator adequacy
    minH = [min(r["H_e"], r["H_l"]) for r in elig_rows]
    absm3 = [abs(r["M3G"]) for r in elig_rows]
    print(f"\n# min(H) range: {min(minH)}-{max(minH)}; Spearman rho(min(H), |M3G|) = {spearman(minH, absm3):.4f}")

    # perturbation on top 10
    top10 = sorted(elig_rows, key=lambda r: abs(r["M3G"]), reverse=True)[:10]
    print(f"\n# COUNT-PERTURBATION STABILITY (top 10 |M3G| eligible pairs)\n")
    for r in top10:
        h_e, h_l, H_e, H_l = r["h_e"], r["h_l"], r["H_e"], r["H_l"]
        base = (h_l / H_l) - (h_e / H_e)
        variants = {}
        for delta in [-5, -2, -1, 1, 2, 5]:
            new_h_l = max(0, h_l + delta)
            new_H_l = max(new_h_l, H_l + delta)
            variants[f"later{delta:+d}"] = (new_h_l / new_H_l) - (h_e / H_e) if new_H_l > 0 else None
        print(f"{r['ticker']} {r['earlier']}->{r['later']}: base_M3G={base:.4f} h_l={h_l} H_l={H_l}")
        print(f"    perturbations: {json.dumps({k: (round(v,4) if v is not None else None) for k,v in variants.items()})}")

    # M6-G subcategory breakdown for top 10 |M3G| eligible pairs (manual validation)
    print("\n# GOVERNANCE SUBCATEGORY HIT BREAKDOWN for top 10 |M3G| eligible pairs\n")
    top10_ids = {(r["ticker"], r["earlier"], r["later"]) for r in top10}
    for pr in pairs:
        if (pr.ticker, pr.earlier_period_end, pr.later_period_end) not in top10_ids:
            continue
        print(f"{pr.ticker} {pr.earlier_period_end}->{pr.later_period_end}: "
              f"total_h_e={pr.earlier.category_hits['governance']} total_h_l={pr.later.category_hits['governance']}")
        for s in GOVERNANCE_SUBCATEGORIES:
            he, hl = pr.earlier.subcat_hits[s], pr.later.subcat_hits[s]
            if he or hl:
                print(f"    {s}: earlier={he} later={hl} delta={hl-he}")

    # taxonomy diagnostics: overall governance subcategory totals across corpus
    print("\n# GOVERNANCE SUBCATEGORY TOTALS ACROSS CORPUS (all 25 pairs, both sides summed)\n")
    subcat_corpus_totals = defaultdict(int)
    for pr in pairs:
        for s in GOVERNANCE_SUBCATEGORIES:
            subcat_corpus_totals[s] += pr.earlier.subcat_hits[s] + pr.later.subcat_hits[s]
    total_all = sum(subcat_corpus_totals.values())
    for s in GOVERNANCE_SUBCATEGORIES:
        cnt = subcat_corpus_totals[s]
        print(f"    {s}: {cnt} ({100*cnt/total_all:.1f}%)" if total_all else f"    {s}: {cnt}")

    # ANCHOR CASES
    print("\n# ANCHOR CASES\n")
    anchors = [("ACT", "2017-06-30"), ("BEL", "2016-12-31"), ("BEL", "2018-12-31"), ("ACT", "2023-06-30")]
    for tk, ee in anchors:
        r = next((r for r in rows if r["ticker"] == tk and r["earlier"] == ee), None)
        if r is None:
            print(f"{tk} {ee}: NOT FOUND")
            continue
        print(json.dumps(r, indent=2))

    # DISCOVER SIMULATION: current M1-G (eps=1.0, report-side gate) vs proposed M3-G at candidate thresholds
    print("\n# DISCOVER SIMULATION\n")
    current_eligible = [r for r in elig_rows if r["M1G"] is not None and abs(r["M1G"]) >= 1.0]
    print(f"CURRENT (M1G, eps=1.0, report-side gate): n={len(current_eligible)}")
    for r in sorted(current_eligible, key=lambda r: abs(r["M1G"]), reverse=True):
        print(f"    {r['ticker']} {r['earlier']}->{r['later']} M1G={r['M1G']:.4f}")

    for thresh in [0.02, 0.03, 0.04]:
        proposed_eligible = [r for r in elig_rows if abs(r["M3G"]) >= thresh]
        print(f"\nPROPOSED (M3G, thresh={thresh}, report-side gate): n={len(proposed_eligible)}")
        for r in sorted(proposed_eligible, key=lambda r: abs(r["M3G"]), reverse=True):
            print(f"    {r['ticker']} {r['earlier']}->{r['later']} M3G={r['M3G']:.4f} (M1G={r['M1G']})")


if __name__ == "__main__":
    main()
