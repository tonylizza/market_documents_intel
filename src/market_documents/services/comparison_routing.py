"""Track 7C.6 comparison-path routing (docs/7c6-production-cutover.md).

`ComparisonPathRouter` answers exactly one question -- "which pipeline
should serve this comparison request" -- deterministically, from the
explicit scope registry in `cutover_config` and the
`SEMANTIC_COMPARISON_CUTOVER_ENABLED` feature flag. It never inspects the
database, never infers scope from whether rows happen to exist, and
carries no comparison logic of its own: `services.cutover_comparison` is
the layer that actually resolves a routed request into a comparison
result.
"""

from dataclasses import dataclass

from market_documents.config import get_settings
from market_documents.models.enums import ComparisonBackend, NormalizedSchedule
from market_documents.services.cutover_config import (
    is_narrative_unit_in_scope,
    is_structured_table_in_scope,
)


@dataclass(frozen=True)
class ComparisonPathRouter:
    """Deterministic, config-driven router. `cutover_enabled=None` (the
    default) reads the live `SEMANTIC_COMPARISON_CUTOVER_ENABLED` setting
    at construction time; passing an explicit bool (as tests do) makes
    routing independent of process-wide settings/env state.
    """

    cutover_enabled: bool | None = None

    def is_enabled(self) -> bool:
        """Whether the cutover flag is active for this router -- exposed so
        callers building a diagnostic message can distinguish "flag off"
        from "genuinely out of the configured scope" (docs/7c6-...md
        Section 5)."""
        if self.cutover_enabled is not None:
            return self.cutover_enabled
        return get_settings().semantic_comparison_cutover_enabled

    def route_narrative(self, *, ticker: str, schedule: NormalizedSchedule, unit_key: str) -> ComparisonBackend:
        """Route one (ticker, schedule, unit_key) narrative comparison
        request. LEGACY_PASSAGE whenever the cutover flag is off, or the
        unit is outside the explicit narrative scope -- never guessed from
        data availability."""
        if not self.is_enabled():
            return ComparisonBackend.LEGACY_PASSAGE
        if is_narrative_unit_in_scope(ticker, schedule, unit_key):
            return ComparisonBackend.SEMANTIC_UNIT
        return ComparisonBackend.LEGACY_PASSAGE

    def route_structured(self, *, ticker: str, table_family_key: str) -> ComparisonBackend:
        """Route one (ticker, table_family_key) structured-table comparison
        request. LEGACY_PASSAGE whenever the cutover flag is off, or the
        table family is outside the explicit structured scope."""
        if not self.is_enabled():
            return ComparisonBackend.LEGACY_PASSAGE
        if is_structured_table_in_scope(ticker, table_family_key):
            return ComparisonBackend.STRUCTURED_TABLE
        return ComparisonBackend.LEGACY_PASSAGE
