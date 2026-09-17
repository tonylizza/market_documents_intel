"""Coverage registry: what the semantic-unit/analytical pipeline supports,
not what rows happen to exist in the database (Track 7D.2,
docs/7d2-financial-performance-unit-expansion.md Section 14).

Unifies three previously scattered declarations into one place a reader can
consult to answer "what does the semantic comparison system actually
support?" without cross-referencing three modules:

- `semantic_unit_config.UNIT_CONFIGS` -- which (ticker, schedule, unit_key)
  has a HEADED_NARRATIVE_UNIT extraction configured at all.
- `analytical_eligibility.UNIT_ANALYTICAL_MODES` -- the analytical routing
  mode a MATCHED/RENAMED alignment of that unit is routed to.
- `cutover_config.NEW_PIPELINE_NARRATIVE_SCOPE` -- whether the unit is
  scoped into the live production cutover path.

This module derives its entries from those three at import time -- it is
never a second, independently-maintained source of truth for any of them,
and it declares no new capability. Mirrors the same shape every other
`*_config.py` in this codebase uses: a frozen dataclass, a module-level
tuple, a version string, and a `compute_configuration_hash()`. Alignment
support is not separately configured anywhere in this codebase -- 7C.2's
`align_units` runs for any unit_key found on either side of a ReportPair
without its own per-unit allowlist -- so `alignment_supported` here is
always `True` for a unit with an extraction config; the field exists so a
future unit that genuinely cannot use the shared alignment pipeline (none
exist yet) has somewhere to declare that.
"""

import hashlib
import json
from dataclasses import dataclass

from market_documents.models.enums import AnalyticalMode, NormalizedSchedule
from market_documents.services.analytical_eligibility import UNIT_ANALYTICAL_MODES
from market_documents.services.cutover_config import NEW_PIPELINE_NARRATIVE_SCOPE
from market_documents.services.semantic_unit_config import UNIT_CONFIGS

# v1.0.0 = initial registry, derived from the four HEADED_NARRATIVE_UNIT
# configs in effect after Track 7D.2 (BEL gross_margin, ACT cfo_conclusion,
# ACT capital_management, ACT healthcare_services_review).
REGISTRY_VERSION = "1.0.0"


@dataclass(frozen=True)
class CoverageEntry:
    ticker: str
    schedule: NormalizedSchedule
    unit_key: str
    extraction_supported: bool
    alignment_supported: bool
    analytical_mode: AnalyticalMode | None
    production_status: str  # "enabled" | "candidate" | "not_ready"


def _production_status(ticker: str, schedule: NormalizedSchedule, unit_key: str) -> str:
    if (ticker, schedule, unit_key) in NEW_PIPELINE_NARRATIVE_SCOPE:
        return "enabled"
    return "candidate"


def _build_registry() -> tuple[CoverageEntry, ...]:
    entries = []
    for config in UNIT_CONFIGS:
        entries.append(
            CoverageEntry(
                ticker=config.ticker,
                schedule=config.schedule,
                unit_key=config.unit_key,
                extraction_supported=True,
                alignment_supported=True,
                analytical_mode=UNIT_ANALYTICAL_MODES.get((config.ticker, config.unit_key)),
                production_status=_production_status(config.ticker, config.schedule, config.unit_key),
            )
        )
    return tuple(entries)


COVERAGE_REGISTRY: tuple[CoverageEntry, ...] = _build_registry()


def coverage_for(ticker: str, schedule: NormalizedSchedule, unit_key: str) -> CoverageEntry | None:
    return next(
        (e for e in COVERAGE_REGISTRY if e.ticker == ticker and e.schedule == schedule and e.unit_key == unit_key),
        None,
    )


def compute_configuration_hash() -> str:
    """Deterministic fingerprint of the registry in effect -- changes
    whenever any of the three source configs it derives from changes."""
    entries = [
        {
            "ticker": e.ticker,
            "schedule": e.schedule.value,
            "unit_key": e.unit_key,
            "extraction_supported": e.extraction_supported,
            "alignment_supported": e.alignment_supported,
            "analytical_mode": e.analytical_mode.value if e.analytical_mode else None,
            "production_status": e.production_status,
        }
        for e in COVERAGE_REGISTRY
    ]
    entries.sort(key=lambda d: (d["ticker"], d["schedule"], d["unit_key"]))
    payload = {"registry_version": REGISTRY_VERSION, "entries": entries}
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
