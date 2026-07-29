"""Corpus-wide `discovery_items` ranking: the same 8 candidate signals as
`findings.py`, ranked across three `rank_scope`s (`corpus`,
`company_history`, `latest_comparisons`) instead of picked per-comparison.

Pure and database-free, like `findings.py` -- operates only on
`DiscoveryCandidate` (a `ComparisonMetrics` plus the identity/scope fields
needed for grouping). Re-running against unchanged source data reproduces
byte-identical ranks: sort key is `(-magnitude, report_comparison_id)`,
never insertion order.
"""

import uuid
from dataclasses import dataclass

from market_documents.publishing.findings import CANDIDATES, ComparisonMetrics

# Cap the number of persisted rows per (discovery_type, rank_scope, scope_key)
# pool -- a scope with fewer eligible/material candidates than this simply
# gets fewer rows, never padded.
TOP_K = 20

RANK_SCOPES: tuple[str, ...] = ("corpus", "company_history", "latest_comparisons")


@dataclass(frozen=True)
class DiscoveryCandidate:
    report_comparison_id: uuid.UUID
    company_id: uuid.UUID
    is_latest_for_company: bool
    metrics: ComparisonMetrics


@dataclass(frozen=True)
class RankedDiscoveryItem:
    report_comparison_id: uuid.UUID
    company_id: uuid.UUID
    discovery_type: str
    rank_scope: str
    score: float
    rank: int
    percentile: float
    finding_key: str
    supporting_metric_key: str
    supporting_value: float
    supporting_unit: str


def _pool_groups(
    scope: str, eligible: list[tuple[DiscoveryCandidate, float, float]]
) -> dict[object, list[tuple[DiscoveryCandidate, float, float]]]:
    if scope == "corpus":
        return {"__corpus__": eligible}
    if scope == "latest_comparisons":
        return {"__latest__": [e for e in eligible if e[0].is_latest_for_company]}
    if scope == "company_history":
        groups: dict[object, list[tuple[DiscoveryCandidate, float, float]]] = {}
        for e in eligible:
            groups.setdefault(e[0].company_id, []).append(e)
        return groups
    raise ValueError(f"unknown rank_scope: {scope}")


def rank_discovery_items(candidates: list[DiscoveryCandidate]) -> list[RankedDiscoveryItem]:
    results: list[RankedDiscoveryItem] = []

    for spec in CANDIDATES:
        eligible: list[tuple[DiscoveryCandidate, float, float]] = []
        for candidate in candidates:
            if not spec.gate(candidate.metrics):
                continue
            value = spec.get_value(candidate.metrics)
            if value is None or not spec.direction_ok(value):
                continue
            magnitude = abs(value) / spec.epsilon
            if magnitude < 1.0:
                continue
            eligible.append((candidate, value, magnitude))

        for scope in RANK_SCOPES:
            for _scope_key, group in _pool_groups(scope, eligible).items():
                pool_size = len(group)
                if pool_size == 0:
                    continue
                ranked = sorted(
                    group, key=lambda e: (-e[2], str(e[0].report_comparison_id))
                )
                for idx, (candidate, value, magnitude) in enumerate(ranked[:TOP_K], start=1):
                    percentile = 100.0 * (pool_size - idx + 1) / pool_size
                    results.append(
                        RankedDiscoveryItem(
                            report_comparison_id=candidate.report_comparison_id,
                            company_id=candidate.company_id,
                            discovery_type=spec.key,
                            rank_scope=scope,
                            score=magnitude,
                            rank=idx,
                            percentile=percentile,
                            finding_key=spec.key,
                            supporting_metric_key=spec.metric_key,
                            supporting_value=value,
                            supporting_unit=spec.unit,
                        )
                    )
    return results
