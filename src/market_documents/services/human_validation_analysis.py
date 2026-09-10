"""Milestone 7 human-validation metrics.

Pure functions over a labeled `human_validation_cases.csv`-shaped list of
rows (dicts). No database access -- this module only computes metrics from
whatever labels exist; it is safe to run against a partially-labeled file
(unlabeled rows are simply excluded from each metric that needs a label).

Per the milestone brief (Section 30): this module never generates labels.
It only scores human labels that already exist against the system's stored
fields. Kappa/Spearman are implemented from scratch (no scipy/sklearn
dependency in this project) using standard closed-form definitions.
"""

import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

CORRESPONDENCE_VALUES = {"YES", "NO", "UNCERTAIN"}
CHANGE_VALUES = {"EFFECTIVELY_UNCHANGED", "MINOR", "SUBSTANTIAL", "STRUCTURAL_AMBIGUOUS"}
CHANGE_ORDER = {"EFFECTIVELY_UNCHANGED": 0, "MINOR": 1, "SUBSTANTIAL": 2}
SYSTEM_CHANGE_ORDER = {"UNCHANGED": 0, "LIGHTLY_MODIFIED": 1, "SUBSTANTIALLY_MODIFIED": 2}
UNMATCHED_VALUES = {"NO_CORRESPONDENCE", "CORRESPONDENCE_EXISTS", "STRUCTURAL_SPLIT_MERGE", "UNCERTAIN"}


def load_labeled_csv(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _labeled(rows: list[dict], *field_names: str) -> list[dict]:
    return [r for r in rows if all((r.get(f) or "").strip() for f in field_names)]


# --------------------------------------------------------------------------
# Section 16: correspondence precision
# --------------------------------------------------------------------------


def correspondence_precision(rows: list[dict], group_by: str | None = None) -> dict:
    """Proportion of matched (non-NEW/REMOVED) cases humans confirm as the
    same underlying disclosure (`human_correspondence == YES`), overall and
    optionally broken down by `group_by` (e.g. "system_confidence",
    "company", "sample_bucket")."""
    matched = [r for r in rows if r.get("sample_bucket") in ("UNCHANGED", "LIGHTLY_MODIFIED", "SUBSTANTIALLY_MODIFIED", "AMBIGUOUS")]
    labeled = _labeled(matched, "human_correspondence")

    def _rate(subset: list[dict]) -> dict:
        yes = sum(1 for r in subset if r["human_correspondence"] == "YES")
        return {"n": len(subset), "yes": yes, "precision": yes / len(subset) if subset else None}

    result = {"overall": _rate(labeled)}
    if group_by:
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in labeled:
            groups[r.get(group_by, "")].append(r)
        result["by_group"] = {k: _rate(v) for k, v in sorted(groups.items())}
    return result


# --------------------------------------------------------------------------
# Section 17: NEW/REMOVED validity
# --------------------------------------------------------------------------


def unmatched_validity(rows: list[dict]) -> dict:
    for bucket in ("NEW", "REMOVED"):
        subset = _labeled([r for r in rows if r.get("sample_bucket") == bucket], "human_unmatched_label")
        counts = Counter(r["human_unmatched_label"] for r in subset)
        n = len(subset)
        yield bucket, {
            "n": n,
            "counts": dict(counts),
            "precision_no_correspondence": (counts.get("NO_CORRESPONDENCE", 0) / n) if n else None,
            "missed_correspondence_rate": (counts.get("CORRESPONDENCE_EXISTS", 0) / n) if n else None,
            "structural_split_merge_rate": (counts.get("STRUCTURAL_SPLIT_MERGE", 0) / n) if n else None,
            "uncertain_rate": (counts.get("UNCERTAIN", 0) / n) if n else None,
        }


# --------------------------------------------------------------------------
# Section 18/19: change-classification agreement (3-level and binary)
# --------------------------------------------------------------------------


def change_confusion_matrix(rows: list[dict]) -> dict:
    """Human (rows) x system (columns) confusion matrix for confirmed
    correspondences (human_correspondence == YES), 3-level severity."""
    confirmed = _labeled(
        [r for r in rows if r.get("human_correspondence") == "YES"], "human_change", "system_alignment_status"
    )
    confirmed = [r for r in confirmed if r["human_change"] in CHANGE_ORDER and r["system_alignment_status"] in SYSTEM_CHANGE_ORDER]
    matrix: dict[str, dict[str, int]] = {h: {s: 0 for s in SYSTEM_CHANGE_ORDER} for h in CHANGE_ORDER}
    for r in confirmed:
        matrix[r["human_change"]][r["system_alignment_status"]] += 1
    n = len(confirmed)
    exact = sum(
        1 for r in confirmed if CHANGE_ORDER[r["human_change"]] == SYSTEM_CHANGE_ORDER[r["system_alignment_status"]]
    )
    adjacent = 0
    for r in confirmed:
        if abs(CHANGE_ORDER[r["human_change"]] - SYSTEM_CHANGE_ORDER[r["system_alignment_status"]]) <= 1:
            adjacent += 1
    return {
        "n": n,
        "matrix": matrix,
        "exact_agreement": exact / n if n else None,
        "within_one_category": adjacent / n if n else None,
        "weighted_kappa": weighted_kappa(
            [CHANGE_ORDER[r["human_change"]] for r in confirmed],
            [SYSTEM_CHANGE_ORDER[r["system_alignment_status"]] for r in confirmed],
            num_categories=3,
        )
        if n
        else None,
    }


def binary_change_metrics(rows: list[dict]) -> dict:
    confirmed = _labeled(
        [r for r in rows if r.get("human_correspondence") == "YES"], "human_change", "system_alignment_status"
    )
    confirmed = [r for r in confirmed if r["human_change"] in CHANGE_ORDER and r["system_alignment_status"] in SYSTEM_CHANGE_ORDER]
    tp = fp = tn = fn = 0
    for r in confirmed:
        human_changed = r["human_change"] != "EFFECTIVELY_UNCHANGED"
        system_changed = r["system_alignment_status"] != "UNCHANGED"
        if human_changed and system_changed:
            tp += 1
        elif not human_changed and not system_changed:
            tn += 1
        elif not human_changed and system_changed:
            fp += 1
        else:
            fn += 1
    n = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
    return {
        "n": n,
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "accuracy": (tp + tn) / n if n else None,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


# --------------------------------------------------------------------------
# Section 20: ordered change validation
# --------------------------------------------------------------------------


def ordered_change_agreement(rows: list[dict]) -> dict:
    confirmed = _labeled(
        [r for r in rows if r.get("human_correspondence") == "YES"], "human_change", "system_alignment_status"
    )
    confirmed = [r for r in confirmed if r["human_change"] in CHANGE_ORDER and r["system_alignment_status"] in SYSTEM_CHANGE_ORDER]
    human_vals = [CHANGE_ORDER[r["human_change"]] for r in confirmed]
    system_vals = [SYSTEM_CHANGE_ORDER[r["system_alignment_status"]] for r in confirmed]
    n = len(confirmed)
    mean_abs_diff = sum(abs(h - s) for h, s in zip(human_vals, system_vals)) / n if n else None
    return {
        "n": n,
        "spearman": spearman_correlation(human_vals, system_vals) if n else None,
        "mean_absolute_category_difference": mean_abs_diff,
    }


# --------------------------------------------------------------------------
# Section 21: continuous similarity metrics vs. human change judgment
# --------------------------------------------------------------------------


SIMILARITY_FIELDS = [
    "system_semantic_similarity",
    "system_lexical_cosine_similarity",
    "system_jaccard_similarity",
    "system_edit_similarity",
    "system_combined_score",
]


def similarity_vs_human_change(rows: list[dict]) -> dict:
    confirmed = [r for r in rows if r.get("human_correspondence") == "YES" and (r.get("human_change") or "") in CHANGE_ORDER]
    result = {}
    human_vals_all = [CHANGE_ORDER[r["human_change"]] for r in confirmed]
    for field in SIMILARITY_FIELDS:
        pairs = [
            (CHANGE_ORDER[r["human_change"]], float(r[field]))
            for r in confirmed
            if (r.get(field) or "").strip() not in ("", "None")
        ]
        if not pairs:
            result[field] = {"n": 0, "spearman": None, "by_category_mean": {}}
            continue
        human_vals = [p[0] for p in pairs]
        metric_vals = [p[1] for p in pairs]
        by_cat: dict[str, list[float]] = defaultdict(list)
        for r in confirmed:
            if (r.get(field) or "").strip() not in ("", "None"):
                by_cat[r["human_change"]].append(float(r[field]))
        result[field] = {
            "n": len(pairs),
            "spearman": spearman_correlation(human_vals, metric_vals),
            "by_category_mean": {k: sum(v) / len(v) for k, v in by_cat.items()},
        }
    return result


# --------------------------------------------------------------------------
# Section 15: inter-rater reliability
# --------------------------------------------------------------------------


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> float | None:
    n = len(labels_a)
    if n == 0 or n != len(labels_b):
        return None
    categories = sorted(set(labels_a) | set(labels_b))
    observed_agreement = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    count_a = Counter(labels_a)
    count_b = Counter(labels_b)
    expected_agreement = sum((count_a[c] / n) * (count_b[c] / n) for c in categories)
    if expected_agreement == 1.0:
        return 1.0 if observed_agreement == 1.0 else None
    return (observed_agreement - expected_agreement) / (1 - expected_agreement)


def weighted_kappa(values_a: list[int], values_b: list[int], num_categories: int) -> float | None:
    """Quadratic-weighted kappa for ordinal categories 0..num_categories-1."""
    n = len(values_a)
    if n == 0 or n != len(values_b):
        return None
    observed = [[0] * num_categories for _ in range(num_categories)]
    for a, b in zip(values_a, values_b):
        observed[a][b] += 1
    hist_a = [sum(row) for row in observed]
    hist_b = [sum(observed[r][c] for r in range(num_categories)) for c in range(num_categories)]
    weights = [[((i - j) ** 2) / ((num_categories - 1) ** 2) for j in range(num_categories)] for i in range(num_categories)]
    observed_disagreement = sum(weights[i][j] * observed[i][j] for i in range(num_categories) for j in range(num_categories)) / n
    expected_disagreement = sum(
        weights[i][j] * hist_a[i] * hist_b[j] for i in range(num_categories) for j in range(num_categories)
    ) / (n * n)
    if expected_disagreement == 0:
        return 1.0 if observed_disagreement == 0 else None
    return 1 - observed_disagreement / expected_disagreement


def spearman_correlation(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 2 or n != len(y):
        return None

    def _ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            i = j + 1
        return ranks

    rx, ry = _ranks(x), _ranks(y)
    mean_rx, mean_ry = sum(rx) / n, sum(ry) / n
    cov = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    var_x = sum((a - mean_rx) ** 2 for a in rx)
    var_y = sum((b - mean_ry) ** 2 for b in ry)
    denom = math.sqrt(var_x * var_y)
    return cov / denom if denom else None


@dataclass
class InterRaterReport:
    n_overlap: int
    correspondence_raw_agreement: float | None
    correspondence_kappa: float | None
    change_weighted_kappa: float | None


def inter_rater_reliability(reviewer_a_rows: list[dict], reviewer_b_rows: list[dict]) -> InterRaterReport:
    """`reviewer_a_rows`/`reviewer_b_rows`: labeled rows for the same
    `case_id` set (the overlap subset), one dict per case_id per reviewer.
    Rows are matched by `case_id`."""
    by_id_a = {r["case_id"]: r for r in reviewer_a_rows}
    by_id_b = {r["case_id"]: r for r in reviewer_b_rows}
    common_ids = sorted(set(by_id_a) & set(by_id_b))

    corr_pairs = [
        (by_id_a[cid]["human_correspondence"], by_id_b[cid]["human_correspondence"])
        for cid in common_ids
        if by_id_a[cid].get("human_correspondence") and by_id_b[cid].get("human_correspondence")
    ]
    raw_agreement = sum(1 for a, b in corr_pairs if a == b) / len(corr_pairs) if corr_pairs else None
    kappa = cohens_kappa([a for a, _ in corr_pairs], [b for _, b in corr_pairs]) if corr_pairs else None

    change_pairs = [
        (CHANGE_ORDER[by_id_a[cid]["human_change"]], CHANGE_ORDER[by_id_b[cid]["human_change"]])
        for cid in common_ids
        if by_id_a[cid].get("human_change") in CHANGE_ORDER and by_id_b[cid].get("human_change") in CHANGE_ORDER
    ]
    w_kappa = (
        weighted_kappa([a for a, _ in change_pairs], [b for _, b in change_pairs], num_categories=3)
        if change_pairs
        else None
    )

    return InterRaterReport(
        n_overlap=len(common_ids),
        correspondence_raw_agreement=raw_agreement,
        correspondence_kappa=kappa,
        change_weighted_kappa=w_kappa,
    )
