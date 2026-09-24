"""Track 7F.8a research-only script: topic-conjunction and evidence-gate challenge test.

Read-only analysis supporting `docs/topic-conjunction-evidence-challenge-7f8a.md`.

Reuses the 7F.8 loader, CURRENT passage population and aggregation unchanged
(`research_7f8_discover_metrics_consolidation`), and evaluates for the
financial-condition, governance and uncertainty topic metrics:

    * five sign-agreement combination rules for the count leg
      D = 1000 * (h2 - h1) / mean(w1, w2) and the density leg
      M1 = 1000 * (h2/w2 - h1/w1):
        C_min, C_count, C_density, C_geo, C_harm;
    * alternative within-pair evidence measures over alignment-unit deltas:
        net / L2 churn (the 7F.8 "sign-flip z"), net / gross, dominant-unit
        share, same-sign vs opposing unit counts, and no evidence floor.

Never writes to any table, config, taxonomy, or CandidateSpec. Uses only
SELECTs (via the 7F.8 loader).

Usage:
    .venv/bin/python scripts/research_7f8a_topic_conjunction_evidence.py [--cache PATH]
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import research_7f8_discover_metrics_consolidation as base  # noqa: E402
from research_7f8_discover_metrics_consolidation import (  # noqa: E402
    Pair,
    Row,
    aggregate,
    describe,
    print_table,
    report_side_ok,
    row_hits,
    spearman,
    topk,
)

CATS = ("financial_condition", "governance", "uncertainty")
SHORT = {"financial_condition": "FC", "governance": "GOV", "uncertainty": "UNC", "risk": "RISK"}
# Provisional 7F.8 magnitude thresholds (per 1,000 words) and direction filters.
THRESHOLD = {"financial_condition": 0.25, "governance": 0.25, "uncertainty": 0.75}
DIRECTION = {"financial_condition": None, "governance": None, "uncertainty": 1}

ANCHORS = {
    "financial_condition": ["ACT 2017->2018", "SBP 2023->2024", "BEL 2019->2020", "BEL 2020->2021", "ACT 2016->2017"],
    "governance": ["ACT 2017->2018", "BEL 2018->2019", "BEL 2016->2017", "ACT 2023->2024", "SUR 2023->2024"],
    "uncertainty": ["BEL 2019->2020", "BEL 2020->2021", "ACT 2019->2020", "SBP 2023->2024"],
}
# Existing 7F.8 manual content reviews (doc Sections 3, 4, 8, 14). "NOT" marks
# anchor pairs the 7F.8 review read as not being a topic event at all.
MANUAL = {
    "financial_condition": {
        "ACT 2016->2017": "CAUTION", "SBP 2023->2024": "CAUTION", "BEL 2017->2018": "PASS",
        "SUR 2024->2025": "CAUTION", "BEL 2020->2021": "PASS",
        "ACT 2017->2018": "NOT", "BEL 2019->2020": "NOT",
    },
    "governance": {
        "BEL 2016->2017": "PASS", "ACT 2023->2024": "PASS", "ACT 2017->2018": "CAUTION",
        "SDL 2024->2025": "FAIL", "ACT 2020->2021": "CAUTION",
        "BEL 2018->2019": "NOT", "SUR 2023->2024": "NOT",
    },
    "uncertainty": {"ACT 2019->2020": "CAUTION", "BEL 2019->2020": "NOT"},
}


# --------------------------------------------------------------------------
# Combination rules
# --------------------------------------------------------------------------


def _agree(d: float, m: float) -> bool:
    return d * m > 0


def c_min(d: float, m: float) -> float:
    return math.copysign(min(abs(d), abs(m)), d) if _agree(d, m) else 0.0


def c_count(d: float, m: float) -> float:
    return d if _agree(d, m) else 0.0


def c_density(d: float, m: float) -> float:
    return m if _agree(d, m) else 0.0


def c_geo(d: float, m: float) -> float:
    return math.copysign(math.sqrt(abs(d) * abs(m)), d) if _agree(d, m) else 0.0


def c_harm(d: float, m: float) -> float:
    return math.copysign(2 * abs(d) * abs(m) / (abs(d) + abs(m)), d) if _agree(d, m) else 0.0


RULES: dict[str, Callable[[float, float], float]] = {
    "C_min": c_min, "C_count": c_count, "C_density": c_density, "C_geo": c_geo, "C_harm": c_harm,
}


# --------------------------------------------------------------------------
# Evidence measures over alignment-unit deltas
# --------------------------------------------------------------------------


def unit_deltas(rows: list[Row], cat: str) -> list[tuple[str, int, str, int]]:
    """(alignment_id, later-minus-earlier hits, status, first page) per alignment unit."""
    units: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    status: dict[str, str] = {}
    page: dict[str, int] = {}
    for r in rows:
        units[r.alignment_id][0 if r.side == "EARLIER" else 1] += row_hits(r, cat)
        status[r.alignment_id] = r.status
        page[r.alignment_id] = min(page.get(r.alignment_id, 10**6), r.page)
    return [(a, l - e, status[a], page[a]) for a, (e, l) in units.items()]


def evidence(deltas: list[int]) -> dict[str, float]:
    d = [x for x in deltas if x]
    net = sum(d)
    gross = sum(abs(x) for x in d)
    l2 = math.sqrt(sum(x * x for x in d))
    n_eff = (gross / l2) ** 2 if l2 else 0.0
    s = 1 if net > 0 else -1 if net < 0 else 0
    return {
        "net": net, "gross": gross, "n_units": len(d),
        "E_l2": net / l2 if l2 else 0.0,  # 7F.8 "signflip_z"
        "E_ng": net / gross if gross else 0.0,  # signed net/gross in [-1, 1]
        "top1": max((abs(x) for x in d), default=0) / gross if gross else 0.0,
        "n_eff": n_eff,
        "same_units": sum(1 for x in d if x * s > 0),
        "opp_units": sum(1 for x in d if x * s < 0),
        "same_hits": sum(abs(x) for x in d if x * s > 0),
        "opp_hits": sum(abs(x) for x in d if x * s < 0),
    }


# --------------------------------------------------------------------------
# Per-pair table
# --------------------------------------------------------------------------


def build(pairs: list[Pair]) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = defaultdict(dict)
    for p in pairs:
        E, L = aggregate(p.rows, "EARLIER"), aggregate(p.rows, "LATER")
        w1, w2 = E.words, L.words
        wbar = (w1 + w2) / 2
        for cat in CATS:
            h1, h2 = (E.core[cat], L.core[cat]) if cat in base.CORE else (E.cat[cat], L.cat[cat])
            d = 1000 * (h2 - h1) / wbar
            m = 1000 * (h2 / w2 - h1 / w1)
            hm = 2 * w1 * w2 / (w1 + w2)
            t: dict = {"h1": h1, "h2": h2, "w1": w1, "w2": w2, "D": d, "M1": m,
                       "M1_volume": 1000 * (h2 - h1) / hm, "M1_length": m - 1000 * (h2 - h1) / hm,
                       "length_change": (w2 - w1) / wbar}
            t.update({k: f(d, m) for k, f in RULES.items()})
            ud = unit_deltas(p.rows, cat)
            t["units"] = ud
            t.update(evidence([x[1] for x in ud]))
            out[cat][p.label] = t
    return out


def eligible(cat: str, v: float, thr: float | None = None) -> bool:
    thr = THRESHOLD[cat] if thr is None else thr
    dirn = DIRECTION[cat]
    if dirn is not None and v * dirn <= 0:
        return False
    return abs(v) >= thr


def fmt_label(label: str) -> str:
    return label.replace("->", "→")


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=None, help="optional pickle cache (see 7F.8 script)")
    a = ap.parse_args()
    pairs = base.load(a.cache)
    gated = [p for p in pairs if report_side_ok(p)]
    labels = [p.label for p in gated]
    tick = {p.label: p.ticker for p in gated}
    T = build(gated)

    # Cross-check against 7F.8 C_conj.
    t78 = base.build_metric_table(gated, "CURRENT", {})
    diff = max(abs(T[c][l]["C_min"] - t78[c][l]["C_conj"]) for c in CATS for l in labels)
    zdiff = max(abs(T[c][l]["E_l2"] - t78[c][l]["signflip_z"]) for c in CATS for l in labels)
    print(f"Cross-check vs 7F.8: max |C_min - C_conj| = {diff:.2e}; max |E_l2 - signflip_z| = {zdiff:.2e}\n")

    for cat in CATS:
        S = SHORT[cat]
        rows = T[cat]
        print(f"## {S}: combination rules (N={len(labels)} gated pairs)\n")
        # Distribution
        hdr = ["rule", "zeros", "median|v|", "MAD|v|", "p75", "p90", "p95", "max|v|", "min>0 |v|", f"eligible @ {THRESHOLD[cat]}"]
        out = []
        for r in RULES:
            v = [rows[l][r] for l in labels]
            mags = [abs(x) for x in v]
            dd = describe(mags)
            nz = [x for x in mags if x > 0]
            out.append([r, sum(1 for x in v if x == 0), dd["median"], dd["mad"], dd["p75"], dd["p90"], dd["p95"], dd["max"],
                        min(nz) if nz else 0.0, sum(1 for x in v if eligible(cat, x))])
        print_table(hdr, out)
        # Rank correlations / top-10 overlap vs C_min
        out = []
        for r in RULES:
            v = [rows[l][r] for l in labels]
            ref = [rows[l]["C_min"] for l in labels]
            out.append([r, spearman(v, ref), spearman([abs(x) for x in v], [abs(x) for x in ref]),
                        len(set(topk(labels, v)) & set(topk(labels, ref))),
                        spearman(v, [rows[l]["D"] for l in labels]), spearman(v, [rows[l]["M1"] for l in labels]),
                        spearman(v, [rows[l]["length_change"] for l in labels])])
        print_table(["rule", "ρ signed vs C_min", "ρ |v| vs C_min", "top-10 ∩ C_min", "ρ vs D", "ρ vs M1", "ρ vs length change"], out)
        # Company-level largest
        out = []
        for co in sorted(set(tick.values())):
            ls = [l for l in labels if tick[l] == co]
            row = [co]
            for r in RULES:
                cand = [l for l in ls if DIRECTION[cat] is None or rows[l][r] * DIRECTION[cat] > 0]
                if not cand or max(abs(rows[l][r]) for l in cand) == 0:
                    row.append("—")
                    continue
                best = max(cand, key=lambda l: abs(rows[l][r]))
                row.append(f"{best[4:]} ({rows[best][r]:+.3f})")
            out.append(row)
        print_table(["company"] + list(RULES), out)
        # Anchors
        out = []
        for l in ANCHORS[cat]:
            t = rows[l]
            out.append([fmt_label(l), f"{t['h1']}→{t['h2']}", f"{t['length_change']:+.2f}", t["D"], t["M1"]]
                       + [t[r] for r in RULES] + [t["E_l2"], t["E_ng"], t["top1"]])
        print_table(["pair", "hits", "Δlen", "D", "M1"] + list(RULES) + ["E_l2", "E_ng", "top1"], out)
        # Threshold sensitivity
        out = []
        for k in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
            thr = THRESHOLD[cat] * k
            out.append([f"x{k} ({thr:.3f})"] + [sum(1 for l in labels if eligible(cat, rows[l][r], thr)) for r in RULES])
        print_table(["threshold"] + list(RULES), out)
        # Eligible sets + manual labels
        man = MANUAL[cat]
        elig_sets = {r: [l for l in labels if eligible(cat, rows[l][r])] for r in RULES}
        union = sorted(set().union(*elig_sets.values()) | {l for l in man if l in rows},
                       key=lambda l: -abs(rows[l]["C_min"]))
        out = []
        for l in union:
            t = rows[l]
            dh = t["h2"] - t["h1"]
            # Share of the observed count change that proportional scaling with report length would predict.
            scaling = (t["h1"] * t["w2"] / t["w1"] - t["h1"]) / dh if dh else float("nan")
            out.append([fmt_label(l), man.get(l, "unreviewed"), scaling] + [f"{t[r]:+.3f}{'*' if l in elig_sets[r] else ''}" for r in RULES]
                       + [t["E_l2"], t["E_ng"], t["top1"], f"{t['same_units']}/{t['opp_units']}", f"{t['same_hits']}/{t['opp_hits']}"])
        print("(* = eligible at base threshold, magnitude + direction only)\n")
        print_table(["pair", "manual", "scaling share"] + list(RULES) + ["E_l2", "E_ng", "top1", "units same/opp", "hits same/opp"], out)
        # Unreviewed entrants: evidence detail
        for l in union:
            if l in man:
                continue
            t = rows[l]
            top = sorted(t["units"], key=lambda x: -abs(x[1]))[:4]
            print(f"- unreviewed {S} {fmt_label(l)}: hits {t['h1']}→{t['h2']}, Δlen {t['length_change']:+.2f}, "
                  f"D {t['D']:+.3f}, M1 {t['M1']:+.3f} (vol {t['M1_volume']:+.3f} / len {t['M1_length']:+.3f}); "
                  f"top units: " + ", ".join(f"{s}:{d:+d}@p{pg}" for _, d, s, pg in top))
        print()

    # Evidence-measure properties
    print("## Evidence measures: identity and dependence\n")
    worst = 0.0
    for cat in CATS:
        for l in labels:
            t = T[cat][l]
            if t["gross"]:
                worst = max(worst, abs(t["E_l2"] - t["E_ng"] * math.sqrt(t["n_eff"])))
    print(f"Identity E_l2 = E_ng * sqrt(n_eff), n_eff = (gross/L2)^2: max abs error {worst:.2e}\n")
    out = []
    for cat in CATS:
        el2 = [abs(T[cat][l]["E_l2"]) for l in labels]
        eng = [abs(T[cat][l]["E_ng"]) for l in labels]
        neff = [T[cat][l]["n_eff"] for l in labels]
        nun = [T[cat][l]["n_units"] for l in labels]
        top1 = [T[cat][l]["top1"] for l in labels]
        out.append([SHORT[cat], statistics.median(nun), statistics.median(neff),
                    spearman(el2, eng), spearman(el2, neff), spearman(eng, neff), spearman(el2, top1), spearman(eng, top1),
                    sum(1 for x in el2 if x >= 1), sum(1 for x in eng if x >= 0.25)])
    print_table(["cat", "median units", "median n_eff", "ρ(|E_l2|,|E_ng|)", "ρ(|E_l2|,n_eff)", "ρ(|E_ng|,n_eff)",
                 "ρ(|E_l2|,top1)", "ρ(|E_ng|,top1)", "#|E_l2|≥1", "#|E_ng|≥0.25"], out)

    # Independence check: lag-1 correlation of unit deltas ordered by page, pooled.
    out = []
    for cat in CATS:
        xs, ys = [], []
        for l in labels:
            ud = sorted((x for x in T[cat][l]["units"] if x[1]), key=lambda x: x[3])
            for u, v in zip(ud, ud[1:]):
                xs.append(u[1])
                ys.append(v[1])
        mx, my = statistics.mean(xs), statistics.mean(ys)
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        r = cov / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
        # Offsetting REMOVED/NEW of equal magnitude (moved-content signature).
        pairs_eq = 0
        for l in labels:
            rem = [abs(d) for _, d, s, _ in T[cat][l]["units"] if s == "REMOVED" and d]
            new = [abs(d) for _, d, s, _ in T[cat][l]["units"] if s == "NEW" and d]
            for x in rem:
                if x in new:
                    new.remove(x)
                    pairs_eq += 1
        out.append([SHORT[cat], len(xs), r, spearman(xs, ys), pairs_eq])
    print_table(["cat", "adjacent unit pairs", "lag-1 Pearson", "lag-1 Spearman", "equal-magnitude REMOVED/NEW pairs"], out)

    # Stylised behaviour
    print("## Stylised cases (hit deltas per alignment unit)\n")
    cases = {
        "one material passage, no other churn": [12],
        "one material passage + balanced noise (±2 x10)": [12] + [2, -2] * 5,
        "one material passage + balanced noise (±3 x20)": [12] + [3, -3] * 10,
        "same +12 spread over 4 passages": [3, 3, 3, 3],
        "same +12 spread over 12 passages": [1] * 12,
        "moved passage (REMOVED -8, NEW +8)": [-8, 8],
        "moved passage + small real +2": [-8, 8, 2],
        "heavy churn, net +19 (ACT gov-like)": [10, -9, 8, -6, 5, 5, -4, 4, 3, 3, 3, -2, 2, 2, 2, 2, 1, 1, -1, -1] + [1] * 5,
    }
    out = []
    for name, d in cases.items():
        e = evidence(d)
        out.append([name, e["net"], e["gross"], e["E_l2"], e["E_ng"], e["top1"], e["n_eff"]])
    print_table(["case", "net", "gross", "E_l2", "E_ng", "top1", "n_eff"], out)

    # Topic single-passage counterfactual: the pair's largest alignment unit as
    # the only net change, with the pair's observed remaining churn kept.
    print("## Topic single-passage counterfactual (largest unit alone clears the magnitude threshold)\n")
    out = []
    for cat in CATS:
        for l in labels:
            t = T[cat][l]
            ds = [x[1] for x in t["units"] if x[1]]
            if not ds:
                continue
            big = max(ds, key=abs)
            d_alone = 1000 * abs(big) / ((t["w1"] + t["w2"]) / 2)
            if d_alone < THRESHOLD[cat]:
                continue
            rest = list(ds)
            rest.remove(big)
            l2 = math.sqrt(sum(x * x for x in rest))
            gross = sum(abs(x) for x in rest)
            out.append([SHORT[cat], fmt_label(l), big, d_alone, len(rest), big / math.sqrt(big * big + l2 * l2),
                        big / (abs(big) + gross), abs(big) / (abs(big) + gross)])
    print_table(["cat", "pair", "largest unit Δhits", "D if alone", "other changed units", "E_l2", "E_ng", "top1"], out)

    # Risk-audit single-passage exemplars (conceptual: risk category over all units).
    print("## Single-passage exemplars from the 7F.6/7F.8 risk audit (risk hits, all alignment units)\n")
    by_label = {p.label: p for p in pairs}
    out = []
    for l, note in (("KP2 2020->2021", "auditor going-concern material-uncertainty paragraph removed (PASS)"),
                    ("BEL 2019->2020", "new supply-chain business-continuity risk section (PASS)"),
                    ("KP2 2022->2023", "Note 14 tables moved (FAIL for removal)"),
                    ("BEL 2016->2017", "GOING CONCERN paragraph moved (FAIL for removal)")):
        p = by_label.get(l)
        if p is None:
            continue
        ud = unit_deltas(p.rows, "risk")
        e = evidence([x[1] for x in ud])
        top = sorted(ud, key=lambda x: -abs(x[1]))[:3]
        out.append([fmt_label(l), note, e["net"], e["gross"], e["n_units"], e["E_l2"], e["E_ng"], e["top1"],
                    ", ".join(f"{s}:{d:+d}" for _, d, s, _ in top)])
    print_table(["pair", "event", "net", "gross", "units", "E_l2", "E_ng", "top1", "top units"], out)

    # Evidence vs manual labels: every reviewed topic finding under C_min at base threshold.
    print("## Evidence measures vs manual labels (reviewed magnitude-eligible topic findings, C_min)\n")
    rules = {
        "E: none": lambda t: True,
        "A: |E_l2| ≥ 1": lambda t: abs(t["E_l2"]) >= 1,
        "B: |E_ng| ≥ 0.25": lambda t: abs(t["E_ng"]) >= 0.25,
        "B: |E_ng| ≥ 0.33": lambda t: abs(t["E_ng"]) >= 1 / 3,
        "C: top1 ≤ 0.5": lambda t: t["top1"] <= 0.5,
        "D: same units > opp units": lambda t: t["same_units"] > t["opp_units"],
    }
    recs = []
    for cat in CATS:
        for l, lab in MANUAL[cat].items():
            t = T[cat].get(l)
            if t is None or lab == "NOT" or not eligible(cat, t["C_min"]):
                continue
            recs.append((cat, l, lab, t))
    out = []
    for name, f in rules.items():
        cnt = {k: [0, 0] for k in ("PASS", "CAUTION", "FAIL")}
        for _, _, lab, t in recs:
            cnt[lab][0 if f(t) else 1] += 1
        out.append([name] + [f"{v[0]}/{v[0] + v[1]}" for v in cnt.values()])
    print_table(["evidence rule", "PASS retained", "CAUTION retained", "FAIL retained"], out)
    print_table(["cat", "pair", "manual", "C_min", "E_l2", "E_ng", "top1", "n_eff", "units same/opp"],
                [[SHORT[c], fmt_label(l), lab, t["C_min"], t["E_l2"], t["E_ng"], t["top1"], t["n_eff"],
                  f"{t['same_units']}/{t['opp_units']}"] for c, l, lab, t in recs])


if __name__ == "__main__":
    main()
