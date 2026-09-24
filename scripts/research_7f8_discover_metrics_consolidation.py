"""Track 7F.8 research-only script: Discover metrics methodology consolidation.

Read-only corpus analysis supporting
`docs/discover-metrics-methodology-consolidation-7f8.md`.

Reconstructs every Discover metric (financial-condition, governance, net tone,
uncertainty, risk introduction/removal, disclosure-change score) plus the
candidate alternative formulas evaluated in 7F.8, from raw
`passage_language_signals` / `passage_language_category_hits` / `passages`
rows of the *current* language-signal run per pair (same
`get_current_language_signal_runs_by_pair` selection rule as 7F.1-7F.7a),
over two analytical passage populations:

    CURRENT             -- production `feature_eligible_primary`
    CLEANED_DIAGNOSTIC  -- CURRENT minus transparent low-information rules
                           (see `cleaning_flags`); diagnostic only, never a
                           production eligibility rule.

Every reconstructed production metric is cross-checked against its persisted
`report_pair_language_features` / `report_pair_features` column.

Never writes to any table, config, taxonomy, or CandidateSpec. Uses only
SELECTs. Retained under scripts/ per the 7D.5a/7F.3/7F.7a convention for
ad hoc, read-only milestone analysis.

Usage:
    .venv/bin/python scripts/research_7f8_discover_metrics_consolidation.py [--cache PATH] [--json OUT]
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

CUSTOM = ("risk", "financial_condition", "governance", "strategy")
CORE = ("positive", "negative", "uncertainty", "litigious", "constraining", "strong_modal", "weak_modal")
FC_SUBS = None  # filled lazily from services config
GOV_SUBS = None


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


@dataclass
class Row:
    passage_id: str
    report_id: str
    side: str  # EARLIER / LATER
    status: str
    confidence: str
    passage_type: str
    category: str | None
    words: int
    core: dict[str, int]
    negated: int
    custom: dict[tuple[str, str], int]
    custom_negated: dict[tuple[str, str], int]
    text: str
    content_hash: str
    heading: str | None
    page: int
    collision: bool
    alignment_id: str = ""


@dataclass
class Pair:
    ticker: str
    pair_id: str
    earlier: str
    later: str
    gap_months: int
    is_transition: bool
    rs_quality: str
    rs_primary: bool
    ac_quality: str
    ac_primary: bool
    feat_quality: str
    feat_primary: bool
    document_quality: str | None
    persisted: dict[str, float | None]
    feat_persisted: dict[str, float | None]
    rows: list[Row] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.ticker} {self.earlier[:4]}->{self.later[:4]}"


PERSISTED_LF = [
    "net_tone_change", "net_tone_earlier", "net_tone_later", "uncertainty_intensity_change",
    "risk_language_introduction", "risk_language_removal", "governance_language_change",
    "financial_condition_language_change", "financial_condition_share_change",
    "financial_condition_topic_mix_change", "governance_share_change", "governance_topic_mix_change",
    "positive_count_earlier", "positive_count_later", "negative_count_earlier", "negative_count_later",
    "uncertainty_count_earlier", "uncertainty_count_later",
]
PERSISTED_F = [
    "disclosure_change_score", "score_lightly_modified_component", "score_substantially_modified_component",
    "score_new_component", "score_removed_component", "score_ambiguous_component",
    "eligible_unchanged_words", "eligible_lightly_modified_words", "eligible_substantially_modified_words",
    "eligible_new_words", "eligible_removed_words", "eligible_ambiguous_words",
    "alignment_coverage_words", "embedded_coverage_earlier", "embedded_coverage_later",
    "review_required_share", "high_confidence_share", "new_rate_words", "removed_rate_words",
    "document_cosine_similarity",
]


def load_from_db() -> list[Pair]:
    from sqlalchemy import select

    from market_documents.db.session import get_session
    from market_documents.models.alignment import PassageAlignment
    from market_documents.models.company import Company
    from market_documents.models.feature import ReportPairFeatures
    from market_documents.models.financial_language import (
        PassageLanguageCategoryHit,
        PassageLanguageSignal,
        ReportPairLanguageFeatures,
    )
    from market_documents.models.passage import Passage
    from market_documents.models.report_pair import ReportPair
    from market_documents.services.feature_extraction import get_current_feature_runs_by_pair
    from market_documents.services.financial_language_metrics import classify_collision
    from market_documents.services.financial_language_signals import get_current_language_signal_runs_by_pair

    out: list[Pair] = []
    with get_session() as s:
        pairs = s.scalars(select(ReportPair)).all()
        ids = [p.id for p in pairs]
        lruns = get_current_language_signal_runs_by_pair(s, ids)
        fruns = get_current_feature_runs_by_pair(s, ids)
        tick = {c.id: c.ticker for c in s.scalars(select(Company)).all()}
        for p in pairs:
            run = lruns.get(p.id)
            frun = fruns.get(p.id)
            if run is None:
                continue
            lf = s.scalar(select(ReportPairLanguageFeatures).where(ReportPairLanguageFeatures.language_signal_run_id == run.id))
            rf = s.scalar(select(ReportPairFeatures).where(ReportPairFeatures.feature_run_id == frun.id)) if frun else None
            if lf is None:
                continue
            pr = Pair(
                ticker=tick[p.company_id], pair_id=str(p.id),
                earlier=str(p.earlier_report.period_end), later=str(p.later_report.period_end),
                gap_months=p.gap_months, is_transition=p.is_transition,
                rs_quality=lf.report_side_signal_quality.value, rs_primary=lf.report_side_primary_eligible,
                ac_quality=lf.alignment_change_signal_quality.value, ac_primary=lf.alignment_change_primary_eligible,
                feat_quality=rf.feature_quality.value if rf else "NONE", feat_primary=bool(rf and rf.primary_eligible),
                document_quality=(rf.document_quality.value if rf and rf.document_quality else None),
                persisted={k: getattr(lf, k) for k in PERSISTED_LF},
                feat_persisted={k: (getattr(rf, k) if rf else None) for k in PERSISTED_F},
            )
            sigs = s.scalars(
                select(PassageLanguageSignal).where(
                    PassageLanguageSignal.language_signal_run_id == run.id,
                    PassageLanguageSignal.primary_narrative_eligible.is_(True),
                    PassageLanguageSignal.feature_eligible.is_(True),
                )
            ).all()
            sig_ids = [x.id for x in sigs]
            hits: dict = defaultdict(dict)
            neg: dict = defaultdict(dict)
            for h in s.scalars(select(PassageLanguageCategoryHit).where(PassageLanguageCategoryHit.passage_language_signal_id.in_(sig_ids))).all():
                hits[h.passage_language_signal_id][(h.category, h.subcategory)] = h.hit_count
                neg[h.passage_language_signal_id][(h.category, h.subcategory)] = h.negated_hit_count
            passages = {x.id: x for x in s.scalars(select(Passage).where(Passage.id.in_([x.passage_id for x in sigs]))).all()}
            aligns = {a.id: a for a in s.scalars(select(PassageAlignment).where(PassageAlignment.id.in_([x.passage_alignment_id for x in sigs]))).all()}
            for x in sigs:
                ps = passages[x.passage_id]
                pr.rows.append(Row(
                    passage_id=str(x.passage_id), report_id=str(ps.report_id), side=x.report_side.value,
                    status=x.alignment_status.value, confidence=x.confidence.value, passage_type=x.passage_type.value,
                    category=x.structured_content_category, words=x.passage_word_count,
                    core={c: getattr(x, f"{c}_count") for c in CORE}, negated=x.negated_hit_count,
                    custom=hits.get(x.id, {}), custom_negated=neg.get(x.id, {}),
                    text=ps.raw_text, content_hash=ps.content_hash, heading=ps.heading_text,
                    page=ps.first_page_number, collision=bool(classify_collision(aligns[x.passage_alignment_id].review_reason)),
                    alignment_id=str(x.passage_alignment_id),
                ))
            out.append(pr)
    out.sort(key=lambda q: (q.ticker, q.earlier, q.later))
    return out


def load(cache: Path | None) -> list[Pair]:
    if cache and cache.exists():
        return pickle.loads(cache.read_bytes())
    pairs = load_from_db()
    if cache:
        cache.write_bytes(pickle.dumps(pairs))
    return pairs


# --------------------------------------------------------------------------
# CLEANED_DIAGNOSTIC population rules (transparent, diagnostic only)
# --------------------------------------------------------------------------

_NUM = re.compile(r"^[\(\-–]?[R$€£]?\d[\d,\.\s%]*\)?%?$")
_LEADER = re.compile(r"\.{4,}|…{2,}|(\s\.){4,}")
_PAGE_REF = re.compile(r"(?:^|\s)(?:page|p\.)\s*\d+", re.I)


def token_stats(text: str) -> tuple[int, float, float]:
    toks = text.split()
    if not toks:
        return 0, 0.0, 0.0
    numeric = sum(1 for t in toks if _NUM.match(t))
    alpha = sum(1 for t in toks if any(ch.isalpha() for ch in t))
    return len(toks), numeric / len(toks), alpha / len(toks)


def furniture_shingles(rows: list[Row], k: int = 6, min_df_share: float = 0.02, min_df: int = 8) -> set[tuple[str, ...]]:
    """k-word shingles recurring across many passages of ONE report --
    running headers/footers/page furniture candidates. Computed per report
    over every eligible passage of that report in this pair."""
    df: Counter = Counter()
    for r in rows:
        toks = r.text.lower().split()
        df.update({tuple(toks[i:i + k]) for i in range(max(0, len(toks) - k + 1))})
    n = len(rows)
    thr = max(min_df, int(min_df_share * n))
    return {sh for sh, c in df.items() if c >= thr}


def cleaning_flags(pair: Pair) -> dict[int, list[str]]:
    """Map row index -> list of diagnostic exclusion reasons."""
    flags: dict[int, list[str]] = defaultdict(list)
    for side in ("EARLIER", "LATER"):
        idx = [i for i, r in enumerate(pair.rows) if r.side == side]
        rows = [pair.rows[i] for i in idx]
        furn = furniture_shingles(rows)
        seen_hash: set[str] = set()
        for i, r in zip(idx, rows):
            n, num_share, alpha_share = token_stats(r.text)
            if num_share >= 0.30:
                flags[i].append("numeric_heavy")
            if alpha_share < 0.60:
                flags[i].append("low_alpha")
            if _LEADER.search(r.text) or len(_PAGE_REF.findall(r.text)) >= 3:
                flags[i].append("toc_like")
            if r.content_hash in seen_hash:
                flags[i].append("intra_report_duplicate")
            seen_hash.add(r.content_hash)
            if furn:
                toks = r.text.lower().split()
                shs = [tuple(toks[j:j + 6]) for j in range(max(0, len(toks) - 5))]
                if shs:
                    fshare = sum(1 for sh in shs if sh in furn) / len(shs)
                    if fshare >= 0.50:
                        flags[i].append("furniture_dominated")
            if r.category in ("table_context", "currency_exposure_table_mixed"):
                flags[i].append("table_residue_category")
    return flags


def population(pair: Pair, name: str, flags: dict[int, list[str]] | None = None) -> list[Row]:
    if name == "CURRENT":
        return pair.rows
    assert flags is not None
    return [r for i, r in enumerate(pair.rows) if i not in flags]


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


@dataclass
class Side:
    words: int = 0
    passages: int = 0
    core: Counter = field(default_factory=Counter)
    cat: Counter = field(default_factory=Counter)
    sub: Counter = field(default_factory=Counter)  # (cat, sub)
    cat_negated: Counter = field(default_factory=Counter)
    cat_passages: Counter = field(default_factory=Counter)  # passages with >=1 hit


def aggregate(rows: list[Row], side: str, statuses: tuple[str, ...] | None = None) -> Side:
    s = Side()
    for r in rows:
        if r.side != side or (statuses and r.status not in statuses):
            continue
        s.words += r.words
        s.passages += 1
        s.core.update(r.core)
        seen = set()
        for (c, sc), h in r.custom.items():
            s.cat[c] += h
            s.sub[(c, sc)] += h
            s.cat_negated[c] += r.custom_negated.get((c, sc), 0)
            if h > 0:
                seen.add(c)
        for c in seen:
            s.cat_passages[c] += 1
    return s


def rate(h: float, w: float) -> float | None:
    return 1000.0 * h / w if w else None


def share(h: float, H: float) -> float | None:
    return h / H if H else None


def cosdist(a: list[float], b: list[float]) -> float | None:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if not na or not nb:
        return None
    return 1 - sum(x * y for x, y in zip(a, b)) / (na * nb)


# --------------------------------------------------------------------------
# Stats helpers
# --------------------------------------------------------------------------


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    if not s:
        return float("nan")
    k = (len(s) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def describe(values: list[float]) -> dict[str, float]:
    v = [x for x in values if x is not None]
    if not v:
        return {}
    med = statistics.median(v)
    return {
        "n": len(v), "min": min(v), "median": med, "max": max(v),
        "mad": statistics.median([abs(x - med) for x in v]),
        **{f"p{int(q * 100)}": pct(v, q) for q in (0.01, 0.05, 0.10, 0.25, 0.75, 0.80, 0.85, 0.90, 0.95, 0.99)},
    }


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = ranks(a), ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else float("nan")


def topk(labels: list[str], values: list[float], k: int = 10, key: Callable[[float], float] = abs) -> list[str]:
    return [labels[i] for i in sorted(range(len(values)), key=lambda i: -key(values[i]))[:k]]



# --------------------------------------------------------------------------
# Topic-category candidates (financial_condition, governance)
# --------------------------------------------------------------------------


def hm(a: float, b: float) -> float:
    return 2 * a * b / (a + b)


def topic_candidates(E: Side, L: Side, cat: str, company_median_w: float, corpus_median_w: float) -> dict[str, float | None]:
    h1, h2 = E.cat[cat], L.cat[cat]
    w1, w2 = E.words, L.words
    H1, H2 = sum(E.cat[c] for c in CUSTOM), sum(L.cat[c] for c in CUSTOM)
    wbar = (w1 + w2) / 2
    subs = sorted({sc for (c, sc) in list(E.sub) + list(L.sub) if c == cat})
    v1 = [E.sub[(cat, sc)] for sc in subs]
    v2 = [L.sub[(cat, sc)] for sc in subs]
    t1, t2 = sum(v1), sum(v2)
    # Shapley decompositions
    m1 = 1000 * (h2 / w2 - h1 / w1)
    m1_volume = 1000 * (h2 - h1) / hm(w1, w2)  # exact Shapley own-count component of M1
    m1_length = m1 - m1_volume  # = 1000 * hbar * (1/w2 - 1/w1)
    o1, o2 = H1 - h1, H2 - h2

    def sh(h: float, o: float) -> float:
        return h / (h + o) if (h + o) else 0.0

    m3 = h2 / H2 - h1 / H1
    m3_own = 0.5 * ((sh(h2, o1) - sh(h1, o1)) + (sh(h2, o2) - sh(h1, o2)))
    m3_other = m3 - m3_own
    return {
        "h1": h1, "h2": h2, "w1": w1, "w2": w2, "H1": H1, "H2": H2,
        "A_raw": h2 - h1,
        "B_M1_density": m1,
        "C_M2_earlier_w": 1000 * (h2 - h1) / w1,
        "D_pairmean_AM": 1000 * (h2 - h1) / wbar,
        "D_pairmean_HM": m1_volume,
        "D_pairmean_GM": 1000 * (h2 - h1) / math.sqrt(w1 * w2),
        "E_company_median": 1000 * (h2 - h1) / company_median_w,
        "F_corpus_median": 1000 * (h2 - h1) / corpus_median_w,
        "G_M3_share": m3,
        "H_log_ratio": math.log(h2 / h1) if h1 and h2 else None,
        "H_log_density_ratio": math.log((h2 / w2) / (h1 / w1)) if h1 and h2 else None,
        "I_topic_mix": cosdist([x / t1 for x in v1], [x / t2 for x in v2]) if t1 and t2 else None,
        "M1_length_component": m1_length,
        "M3_own_component": m3_own,
        "M3_other_component": m3_other,
        "length_change": (w2 - w1) / wbar,
        "other_taxonomy_change": (o2 - o1) / ((o1 + o2) / 2) if (o1 + o2) else None,
    }


def report_lengths(pairs: list[Pair], pop: str, flags_by_pair: dict[str, dict]) -> tuple[dict[str, float], float]:
    """Per-company median and corpus median eligible words per unique report."""
    per_report: dict[str, tuple[str, int]] = {}
    for p in pairs:
        rows = population(p, pop, flags_by_pair.get(p.pair_id))
        for side in ("EARLIER", "LATER"):
            srows = [r for r in rows if r.side == side]
            if srows:
                per_report[srows[0].report_id] = (p.ticker, sum(r.words for r in srows))
    by_co: dict[str, list[int]] = defaultdict(list)
    for t, w in per_report.values():
        by_co[t].append(w)
    return {t: statistics.median(v) for t, v in by_co.items()}, statistics.median([w for _, w in per_report.values()])


def report_side_ok(p: Pair) -> bool:
    return p.rs_quality in ("GOOD", "USABLE") and p.rs_primary


def alignment_ok(p: Pair) -> bool:
    return p.ac_quality in ("GOOD", "USABLE") and p.ac_primary



def conjunction(volume: float, prominence: float) -> float:
    """Topic-specific change: counted only where the category's own count
    change (volume, per 1,000 pair-average words) and its density change
    (prominence, per 1,000 words) agree in sign; magnitude is the smaller of
    the two. Zero when either leg is zero or they disagree."""
    if volume * prominence <= 0:
        return 0.0
    return math.copysign(min(abs(volume), abs(prominence)), volume)


def row_hits(r: Row, cat: str) -> int:
    if cat in CORE:
        return r.core[cat]
    return sum(h for (c, _), h in r.custom.items() if c == cat)


def change_evidence(rows: list[Row], cat: str) -> dict[str, float]:
    """Decompose later-minus-earlier hit change into alignment units."""
    units: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # earlier, later, status-code
    status_of: dict[str, str] = {}
    for r in rows:
        u = units[r.alignment_id]
        u[0 if r.side == "EARLIER" else 1] += row_hits(r, cat)
        status_of[r.alignment_id] = r.status
    by_status: Counter = Counter()
    deltas = []
    for aid, (e, l, _) in units.items():
        d = l - e
        by_status[status_of[aid]] += d
        if d:
            deltas.append(d)
    gross = sum(abs(d) for d in deltas)
    net = sum(deltas)
    top = sorted((abs(d) for d in deltas), reverse=True)
    ss = sum(d * d for d in deltas)
    return {
        "net": net, "gross": gross,
        # Within-pair sign-flip statistic: net change relative to the spread
        # expected if each alignment unit's observed change were equally
        # likely to point either way. Scale-free; not corpus-calibrated.
        "signflip_z": (net / math.sqrt(ss)) if ss else 0.0, "net_gross": (abs(net) / gross) if gross else 0.0,
        "units_changed": len(deltas),
        "top1_share": top[0] / gross if gross else 0.0,
        "top3_share": sum(top[:3]) / gross if gross else 0.0,
        **{f"d_{k}": v for k, v in by_status.items()},
    }


def subcategory_concentration(E: Side, L: Side, cat: str) -> tuple[str, float]:
    d = {sc: L.sub[(c, sc)] - E.sub[(c, sc)] for (c, sc) in set(E.sub) | set(L.sub) if c == cat}
    gross = sum(abs(v) for v in d.values())
    if not gross:
        return "", 0.0
    sc = max(d, key=lambda k: abs(d[k]))
    return sc, abs(d[sc]) / gross


# --------------------------------------------------------------------------
# Report-side metric builders (current + proposed), per pair and population
# --------------------------------------------------------------------------

CURRENT_SPECS = {
    # metric: (current value key, current epsilon, direction filter, gate)
    "financial_condition": ("G_M3_share", 0.04, None, "rs"),
    "governance": ("G_M3_share", 0.05, None, "rs"),
    "uncertainty": ("B_M1_density", 1.0, 1, "rs"),
    "net_tone": ("B_M1_density", 1.0, -1, "rs"),
}
# Provisional 7F.8 thresholds: ~10% of the metric's corpus-median exposure
# density per 1,000 words, rounded to the nearest 0.25 (see doc Section 15).
PROPOSED_SPECS = {
    "financial_condition": ("C_conj", 0.25, None, "rs"),
    "governance": ("C_conj", 0.25, None, "rs"),
    "uncertainty": ("C_conj", 0.75, 1, "rs"),
    "net_tone": ("B_M1_density", 2.25, -1, "rs"),
}


def core_candidates(E: Side, L: Side, cat: str) -> dict[str, float]:
    if cat == "net_tone":
        h1 = E.core["positive"] - E.core["negative"]
        h2 = L.core["positive"] - L.core["negative"]
    else:
        h1, h2 = E.core[cat], L.core[cat]
    w1, w2 = E.words, L.words
    wbar = (w1 + w2) / 2
    m1 = 1000 * (h2 / w2 - h1 / w1)
    v = 1000 * (h2 - h1) / wbar
    return {"h1": h1, "h2": h2, "w1": w1, "w2": w2, "A_raw": h2 - h1, "B_M1_density": m1,
            "D_pairmean_AM": v, "C_conj": conjunction(v, m1), "length_change": (w2 - w1) / wbar}


def build_metric_table(pairs: list[Pair], pop: str, flags: dict[str, dict]) -> dict[str, dict[str, dict]]:
    co_med, corp_med = report_lengths(pairs, pop, flags)
    table: dict[str, dict[str, dict]] = defaultdict(dict)
    for p in pairs:
        rows = population(p, pop, flags.get(p.pair_id))
        E, L = aggregate(rows, "EARLIER"), aggregate(rows, "LATER")
        for cat in ("financial_condition", "governance"):
            t = topic_candidates(E, L, cat, co_med[p.ticker], corp_med)
            t["C_conj"] = conjunction(t["D_pairmean_AM"], t["B_M1_density"])
            t.update(change_evidence(rows, cat))
            t["subcat"], t["subcat_share"] = subcategory_concentration(E, L, cat)
            table[cat][p.label] = t
        for cat in ("uncertainty", "net_tone"):
            t = core_candidates(E, L, cat)
            if cat == "net_tone":
                t["d_pos_rate"] = 1000 * (L.core["positive"] / L.words - E.core["positive"] / E.words)
                t["d_neg_rate"] = 1000 * (L.core["negative"] / L.words - E.core["negative"] / E.words)
                units: dict[str, list[int]] = defaultdict(lambda: [0, 0])
                for r in rows:
                    units[r.alignment_id][0 if r.side == "EARLIER" else 1] += r.core["positive"] - r.core["negative"]
                ds = [b - a for a, b in units.values() if a != b]
                t["signflip_z"] = sum(ds) / math.sqrt(sum(d * d for d in ds)) if ds else 0.0
            else:
                t.update(change_evidence(rows, cat))
            table[cat][p.label] = t
    return table


def eligible_under(spec: tuple, value: float | None, gate_ok: bool) -> bool:
    key, eps, direction, _ = spec
    if value is None or not gate_ok:
        return False
    if direction is not None and value * direction <= 0:
        return False
    return abs(value) >= eps


def diff_rows(pairs: list[Pair], table: dict[str, dict[str, dict]], metric: str) -> list[dict]:
    cur, prop = CURRENT_SPECS[metric], PROPOSED_SPECS[metric]
    recs = []
    for p in pairs:
        t = table[metric][p.label]
        g = report_side_ok(p)
        recs.append({"pair": p.label, "gate": g, "cur": t[cur[0]], "prop": t[prop[0]],
                     "cur_elig": eligible_under(cur, t[cur[0]], g), "prop_elig": eligible_under(prop, t[prop[0]], g),
                     "z": t.get("signflip_z")})

    def rank(key: str, elig: str) -> dict[str, int]:
        el = sorted((r for r in recs if r[elig]), key=lambda r: -abs(r[key]))
        return {r["pair"]: i + 1 for i, r in enumerate(el)}

    rc, rp = rank("cur", "cur_elig"), rank("prop", "prop_elig")
    for r in recs:
        r["cur_rank"], r["prop_rank"] = rc.get(r["pair"]), rp.get(r["pair"])
    return recs


def threshold_grid(values: list[float], base: float, direction: int | None) -> list[tuple[str, float, int]]:
    mags = [abs(v) for v in values]
    med = statistics.median(mags)
    mad = statistics.median([abs(x - med) for x in mags]) * 1.4826
    rules = [(f"base x{k}", base * k) for k in (0.5, 0.75, 1.0, 1.25, 1.5)]
    rules += [(f"p{int(q * 100)}|v|", pct(mags, q)) for q in (0.75, 0.80, 0.85, 0.90)]
    rules += [(f"med+{k}xMADs", med + k * mad) for k in (1, 2, 3)]
    out = []
    for name, thr in rules:
        n = sum(1 for v in values if abs(v) >= thr and (direction is None or v * direction > 0))
        out.append((name, thr, n))
    return out


# --------------------------------------------------------------------------
# Risk introduction / removal candidates
# --------------------------------------------------------------------------


def shingles(text: str, k: int = 5) -> set[tuple[str, ...]]:
    w = re.findall(r"[a-z]+", text.lower())
    return {tuple(w[i:i + k]) for i in range(max(0, len(w) - k + 1))}


def risk_candidates(p: Pair) -> dict[str, dict[str, float]]:
    E = [r for r in p.rows if r.side == "EARLIER"]
    L = [r for r in p.rows if r.side == "LATER"]
    wbar = (sum(r.words for r in E) + sum(r.words for r in L)) / 2
    shE: set = set().union(*[shingles(r.text) for r in E]) if E else set()
    shL: set = set().union(*[shingles(r.text) for r in L]) if L else set()
    units: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in p.rows:
        units[r.alignment_id][0 if r.side == "EARLIER" else 1] += row_hits(r, "risk")
    out = {}
    for kind, rows, status, other in (("intro", L, "NEW", shE), ("removal", E, "REMOVED", shL)):
        pop = [r for r in rows if r.status == status]
        hits = [row_hits(r, "risk") for r in pop]
        words = sum(r.words for r in pop)
        moved = 0
        for r, h in zip(pop, hits):
            if h:
                sh = shingles(r.text)
                if sh and len(sh & other) / len(sh) >= 0.5:
                    moved += h
        gross = sum(max(0, b - a) for a, b in units.values()) if kind == "intro" else sum(max(0, a - b) for a, b in units.values())
        out[kind] = {
            "current_rate": 1000 * sum(hits) / words if words else 0.0,
            "hits": sum(hits), "words": words, "passages": len(pop),
            "risk_passages": sum(1 for h in hits if h), "risk_passage_share": (sum(1 for h in hits if h) / len(pop)) if pop else 0.0,
            "pair_normalized": 1000 * sum(hits) / wbar, "gross_all_units": 1000 * gross / wbar, "gross_hits": gross,
            "moved_hits": moved, "top_passage_share": (max(hits) / sum(hits)) if sum(hits) else 0.0,
        }
    return out


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def fmt(x: object) -> str:
    if isinstance(x, float):
        return f"{x:.4f}"
    return str(x)


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    print("| " + " | ".join(headers) + " |")
    print("|" + "---|" * len(headers))
    for r in rows:
        print("| " + " | ".join(fmt(x) for x in r) + " |")
    print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=None, help="optional pickle cache of loaded rows (read-only DB access otherwise)")
    ap.add_argument("--json", type=Path, default=None, help="optional path for machine-readable results")
    a = ap.parse_args()
    pairs = load(a.cache)
    flags = {p.pair_id: cleaning_flags(p) for p in pairs}
    gated = [p for p in pairs if report_side_ok(p)]
    results: dict = {}

    # 1. Population audit
    print("## 1. Passage-population audit (CURRENT = feature_eligible_primary)\n")
    allw = [r.words for p in pairs for r in p.rows]
    d = describe(allw)
    print_table(["n passages (pair-side rows)", "words", "min", "p1", "p5", "p10", "median", "p90", "p95", "p99", "max"],
                [[len(allw), sum(allw), d["min"], d["p1"], d["p5"], d["p10"], d["median"], d["p90"], d["p95"], d["p99"], d["max"]]])
    print_table(["below", "count", "word share"], [[t, sum(1 for w in allw if w < t), sum(w for w in allw if w < t) / sum(allw)] for t in (3, 5, 10, 20, 40, 60, 80)])
    reports: dict[str, list] = {}
    for p in pairs:
        for side in ("EARLIER", "LATER"):
            idx = [i for i, r in enumerate(p.rows) if r.side == side]
            rid = p.rows[idx[0]].report_id
            if rid in reports:
                continue
            rows = [p.rows[i] for i in idx]
            f = flags[p.pair_id]
            per = Counter(x for i in idx for x in f.get(i, []))
            short_body = sum(1 for r in rows if r.passage_type == "HEADING_WITH_BODY" and r.heading and r.words - len(r.heading.split()) < 20)
            reports[rid] = [p.ticker, (p.earlier if side == "EARLIER" else p.later), len(rows), sum(r.words for r in rows),
                            statistics.median([r.words for r in rows]), sum(1 for r in rows if r.words < 60),
                            sum(1 for r in rows if r.passage_type == "HEADING_WITH_BODY"), short_body,
                            per["toc_like"], per["numeric_heavy"] + per["low_alpha"], per["intra_report_duplicate"], per["furniture_dominated"],
                            sum(p.rows[i].words for i in idx if i in f) / sum(r.words for r in rows)]
    print_table(["ticker", "period_end", "passages", "words", "median len", "<60w", "HEADING_WITH_BODY", "body<20w", "toc_like", "numeric/low-alpha", "dup", "furniture", "CLEANED-excluded word share"],
                sorted(reports.values(), key=lambda r: (r[0], r[1])))

    # 2. Topic candidates
    tables = {pop: build_metric_table(pairs, pop, flags) for pop in ("CURRENT", "CLEANED")}
    T, Tc = tables["CURRENT"], tables["CLEANED"]
    keys = ["A_raw", "B_M1_density", "C_M2_earlier_w", "D_pairmean_AM", "D_pairmean_HM", "D_pairmean_GM", "E_company_median",
            "F_corpus_median", "G_M3_share", "H_log_ratio", "H_log_density_ratio", "I_topic_mix", "C_conj"]
    labels = [p.label for p in gated]
    for cat in ("financial_condition", "governance"):
        print(f"## 2. {cat} candidate formulas (N={len(gated)} report-side-gated pairs)\n")
        cur = [T[cat][l]["G_M3_share"] for l in labels]
        rows = []
        for k in keys:
            v = [T[cat][l][k] for l in labels]
            vc = [Tc[cat][l][k] for l in labels]
            dd, da = describe(v), describe([abs(x) for x in v])
            rows.append([k, dd["min"], dd["median"], dd["max"], dd["mad"], da["p75"], da["p80"], da["p85"], da["p90"], da["p95"],
                         spearman([abs(x) for x in v], [abs(x) for x in cur]), len(set(topk(labels, v)) & set(topk(labels, cur))),
                         spearman(v, vc), len(set(topk(labels, v)) & set(topk(labels, vc))), sum(1 for x, y in zip(v, vc) if x * y < 0)])
        print_table(["candidate", "min", "median", "max", "MAD", "p75|v|", "p80|v|", "p85|v|", "p90|v|", "p95|v|", "rho |v| vs |M3|", "top10 vs M3",
                     "rho CURRENT vs CLEANED", "top10 CUR vs CLN", "sign flips CUR->CLN"], rows)
        print_table(["pair", "h1", "h2", "w1", "w2", "H1", "H2", "M1", "M1 volume part", "M1 length part", "M3", "M3 own part", "M3 other part",
                     "V (pair-mean)", "C (conj)", "topic mix", "net/gross", "sign-flip z", "top subcat (share of gross)"],
                    [[l, *(T[cat][l][k] for k in ("h1", "h2", "w1", "w2", "H1", "H2", "B_M1_density", "D_pairmean_HM", "M1_length_component",
                                                     "G_M3_share", "M3_own_component", "M3_other_component", "D_pairmean_AM", "C_conj", "I_topic_mix",
                                                     "net_gross", "signflip_z")), f'{T[cat][l]["subcat"]} ({T[cat][l]["subcat_share"]:.2f})'] for l in labels])
        rev = Counter()
        for l in labels:
            t = T[cat][l]
            for m, k in (("M1", "B_M1_density"), ("M3", "G_M3_share")):
                if t["A_raw"] != 0 and t[k] * t["A_raw"] < 0:
                    rev[m] += 1
                if t["A_raw"] == 0 and t[k] != 0:
                    rev[m + " (flat count, nonzero metric)"] += 1
        print("sign disagreement with own-count change:", dict(rev), "\n")
        results[cat] = {l: T[cat][l] for l in labels}

    # 3. Uncertainty / tone
    for cat in ("uncertainty", "net_tone"):
        print(f"## 3. {cat}\n")
        cols = ["h1", "h2", "w1", "w2", "A_raw", "B_M1_density", "D_pairmean_AM", "C_conj", "signflip_z"]
        if cat == "net_tone":
            cols += ["d_pos_rate", "d_neg_rate"]
        print_table(["pair", *cols, "CLEANED M1"], [[l, *(T[cat][l].get(k) for k in cols), Tc[cat][l]["B_M1_density"]] for l in labels])
        v = [T[cat][l]["B_M1_density"] for l in labels]
        c = [T[cat][l]["C_conj"] for l in labels]
        print(f"rho(M1, conj)={spearman(v, c):.3f}; count/density sign disagreements="
              f"{sum(1 for l in labels if T[cat][l]['A_raw'] * T[cat][l]['B_M1_density'] < 0)}\n")
        results[cat] = {l: T[cat][l] for l in labels}

    # 4. Risk introduction / removal
    print("## 4. Risk introduction / removal\n")
    rk = {p.label: risk_candidates(p) for p in pairs}
    ag = [p for p in pairs if alignment_ok(p)]
    for kind in ("intro", "removal"):
        print_table(["pair", "gate", "current rate", "hits", "words", "passages", "risk passages", "share", "pair-normalized", "gross (all units)", "moved hits", "top passage share"],
                    [[p.label, alignment_ok(p), *(rk[p.label][kind][k] for k in ("current_rate", "hits", "words", "passages", "risk_passages", "risk_passage_share",
                                                                                   "pair_normalized", "gross_all_units", "moved_hits", "top_passage_share"))]
                     for p in sorted(pairs, key=lambda q: -rk[q.label][kind]["current_rate"])])
        cur = [rk[p.label][kind]["current_rate"] for p in ag]
        lab = [p.label for p in ag]
        print_table(["candidate", "rho vs current", "top10 overlap", "zeros"],
                    [[k, spearman([rk[p.label][kind][k] for p in ag], cur), len(set(topk(lab, [rk[p.label][kind][k] for p in ag])) & set(topk(lab, cur))),
                      sum(1 for p in ag if rk[p.label][kind][k] == 0)] for k in ("hits", "risk_passages", "risk_passage_share", "pair_normalized", "gross_all_units")])
        print(f"total {kind} hits (gated) = {sum(rk[p.label][kind]['hits'] for p in ag)}; in likely-moved passages = {sum(rk[p.label][kind]['moved_hits'] for p in ag)}\n")
    results["risk"] = rk

    # 5. Disclosure-change score
    print("## 5. Disclosure-change score weight sensitivity\n")
    K = ["unchanged", "lightly_modified", "substantially_modified", "new", "removed", "ambiguous"]
    schemes = {"current": [0, .25, .65, .85, .85, .5], "exclude_ambiguous": [0, .25, .65, .85, .85, None], "new_removed_1.0": [0, .25, .65, 1, 1, .5],
               "new_removed_only": [0, 0, 0, 1, 1, 0], "linear_thirds": [0, 1 / 3, 2 / 3, 1, 1, .5], "no_lightly_modified": [0, 0, .65, .85, .85, .5],
               "new_gt_removed": [0, .25, .65, 1, .7, .5]}
    vals: dict[str, list[float]] = defaultdict(list)
    cosd = []
    for p in pairs:
        f = p.feat_persisted
        w = [f[f"eligible_{k}_words"] for k in K]
        tot = sum(w)
        cosd.append(1 - (f["document_cosine_similarity"] or 0))
        for n, ws in schemes.items():
            if ws[5] is None:
                vals[n].append(sum(x * y for x, y in zip(ws[:5], w[:5])) / (tot - w[5]))
            else:
                vals[n].append(sum(x * y for x, y in zip(ws, w)) / tot)
    lab = [p.label for p in pairs]
    print_table(["scheme", "rho vs current", "top10 overlap", "rho vs (1 - doc cosine)"],
                [[n, spearman(vals[n], vals["current"]), len(set(topk(lab, vals[n])) & set(topk(lab, vals["current"]))), spearman(vals[n], cosd)] for n in schemes])
    print_table(["pair", "feature quality", "document quality", "score"], [[p.label, p.feat_quality, p.document_quality, p.feat_persisted["disclosure_change_score"]] for p in pairs])

    # 6. Current vs proposed diff + thresholds
    print("## 6. Current vs proposed Discover eligibility (report-side metrics)\n")
    for m in ("financial_condition", "governance", "uncertainty", "net_tone"):
        recs = diff_rows(pairs, T, m)
        print(f"### {m}: current {CURRENT_SPECS[m]} -> proposed {PROPOSED_SPECS[m]}\n")
        print_table(["pair", "current value", "current eligible", "current rank", "proposed value", "proposed eligible", "proposed rank", "sign-flip z"],
                    [[r["pair"], r["cur"], r["cur_elig"], r["cur_rank"], r["prop"], r["prop_elig"], r["prop_rank"], r["z"]]
                     for r in recs if r["cur_elig"] or r["prop_elig"]])
        spec = PROPOSED_SPECS[m]
        print_table(["threshold rule", "threshold", "eligible (magnitude+direction)"], threshold_grid([T[m][l][spec[0]] for l in labels], spec[1], spec[2]))

    # 7. Redundancy
    print("## 7. Redundancy (signed Spearman, gated pairs)\n")
    S = {
        "FC conj": [T["financial_condition"][l]["C_conj"] for l in labels], "FC M1": [T["financial_condition"][l]["B_M1_density"] for l in labels],
        "FC M3": [T["financial_condition"][l]["G_M3_share"] for l in labels], "FC volume": [T["financial_condition"][l]["D_pairmean_AM"] for l in labels],
        "FC mix": [T["financial_condition"][l]["I_topic_mix"] for l in labels],
        "GOV conj": [T["governance"][l]["C_conj"] for l in labels], "GOV M1": [T["governance"][l]["B_M1_density"] for l in labels],
        "GOV M3": [T["governance"][l]["G_M3_share"] for l in labels], "GOV volume": [T["governance"][l]["D_pairmean_AM"] for l in labels],
        "GOV mix": [T["governance"][l]["I_topic_mix"] for l in labels],
        "net tone": [T["net_tone"][l]["B_M1_density"] for l in labels], "uncertainty conj": [T["uncertainty"][l]["C_conj"] for l in labels],
        "uncertainty M1": [T["uncertainty"][l]["B_M1_density"] for l in labels], "length change": [T["governance"][l]["length_change"] for l in labels],
    }
    combos = [("FC conj", "FC M1"), ("FC conj", "FC volume"), ("FC conj", "FC M3"), ("FC M3", "FC mix"), ("GOV conj", "GOV M1"), ("GOV conj", "GOV volume"),
              ("GOV conj", "GOV M3"), ("GOV M3", "GOV mix"), ("FC M3", "GOV M3"), ("FC M1", "GOV M1"), ("FC conj", "GOV conj"), ("net tone", "uncertainty M1"),
              ("FC volume", "length change"), ("GOV volume", "length change"), ("FC M1", "length change"), ("GOV M1", "length change")]
    print_table(["a", "b", "rho"], [[x, y, spearman(S[x], S[y])] for x, y in combos])

    if a.json:
        a.json.write_text(json.dumps(results, default=str, indent=1))


if __name__ == "__main__":
    main()
