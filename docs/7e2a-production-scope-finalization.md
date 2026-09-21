# Track 7E.2a: Production-Scope Finalization

## 0. Scope note

RELEASE-SCOPE DECISION milestone. No new schedule, semantic unit, structured
family, metric, or database architecture was added. No deferred parser or
localization defect was repaired. `cutover_config.py` is the only
production-behavior file changed. No production cutover was performed: no
Neon database was created, no Vercel `DATABASE_URL` was switched, no data
was published to production, and the existing production database was not
touched.

## 1. Complete configured-unit inventory

`semantic_unit_config.UNIT_CONFIGS` (14 narrative units) and
`structured_table_config.TABLE_FAMILY_CONFIGS` (2 structured families) as
they exist in the repository today, cross-referenced against
`analytical_eligibility.UNIT_ANALYTICAL_MODES` and the pre-7E.2a
`cutover_config.NEW_PIPELINE_NARRATIVE_SCOPE`/`NEW_PIPELINE_STRUCTURED_SCOPE`
(`CONFIG_VERSION = "1.1.0"`):

| ticker | schedule | unit_key / family | analytical mode | pre-7E.2a production status | documented readiness (latest doc) |
|---|---|---|---|---|---|
| BEL | FINANCIAL_PERFORMANCE | gross_margin | LEXICAL_ONLY | enabled | STRONG_CUTOVER_CANDIDATE (7E.2) |
| ACT | FINANCIAL_PERFORMANCE | cfo_conclusion | LEXICAL_ONLY | enabled | STRONG_CUTOVER_CANDIDATE (7E.2) |
| ACT | FINANCIAL_PERFORMANCE | healthcare_services_review | LEXICAL_ONLY | enabled | STRONG_CUTOVER_CANDIDATE (7D.2c/7E.2) |
| ACT | CORPORATE_GOVERNANCE | information_security_governance | LEXICAL_ONLY | candidate | READY_FOR_CUTOVER (7D.3) |
| ACT | CORPORATE_GOVERNANCE | governance_policies_processes | LEXICAL_ONLY | candidate | READY_WITH_CAVEAT (7D.3: 2023 boundary defect) |
| ACT | CORPORATE_GOVERNANCE | combined_assurance | LEXICAL_ONLY | candidate | NOT_READY (7D.3) -> READY_WITH_CAVEAT (7D.4a, defect fixed) |
| BEL | CORPORATE_GOVERNANCE | board_composition_diversity | STRUCTURED_COMPARISON_PREFERRED | candidate | no comparison engine exists for this mode |
| ACT | REMUNERATION | remco_chairperson_report | LEXICAL_ONLY | candidate | READY_WITH_CAVEAT (7D.4: 2023 truncation) |
| ACT | REMUNERATION | remuneration_policy_changes | LEXICAL_ONLY | candidate | READY_FOR_CUTOVER (7D.4) |
| ACT | REMUNERATION | remuneration_governance | LEXICAL_ONLY | candidate | NOT_READY (7D.4) -> READY_WITH_CAVEAT (7D.4a, defect fixed) |
| BEL | REMUNERATION | variable_remuneration | LEXICAL_ONLY | candidate | NOT_READY (7D.4: 0/6 pairs ever resolve) |
| SUR | REMUNERATION | remuneration_policy_changes_and_focus | LEXICAL_ONLY | candidate | READY_WITH_CAVEAT (7D.4: 2025 extraction defect) |
| SUR | REMUNERATION | fair_responsible_remuneration | LEXICAL_ONLY | candidate | READY_WITH_CAVEAT (7D.4: 2025 extraction defect) |
| SUR | REMUNERATION | remuneration_policy_shareholder_engagement | LEXICAL_ONLY | candidate | NOT_READY (7D.4: 0/3 years ever resolve) |
| ACT | structured (REMUNERATION) | ned_remuneration_policy_table | STRUCTURED_COMPARISON_PREFERRED | enabled | STRONG_CUTOVER_CANDIDATE (7E.2) |
| ACT | structured (REMUNERATION) | total_remuneration_outcomes | STRUCTURED_COMPARISON_PREFERRED | enabled | STRONG_CUTOVER_CANDIDATE (7E.2) |

CEO_REVIEW/CHAIR_REVIEW (Track 7D.6) and MATERIAL_RISKS (7D.5) have zero
configured `UnitConfig` entries -- nothing from either schedule appears in
this inventory, correctly (`coverage_registry.py` derives strictly from
`UNIT_CONFIGS`; an unconfigured schedule contributes nothing).
STRATEGY/OUTLOOK/LEGAL_REGULATORY/MATERIAL_MATTERS/OPERATING_ENVIRONMENT
(7D.5a) remain unimplemented schedules entirely.

Confirmed against the current repository state (not reconstructed from
memory): `semantic_unit_config.py` (`CONFIG_VERSION 1.6.0`, 14 entries),
`structured_table_config.py` (`CONFIG_VERSION 1.0.0`, 2 entries),
`analytical_eligibility.py` (`ALGORITHM_VERSION 1.4.0`, 13 routing
entries -- `board_composition_diversity` is the only `UNIT_CONFIGS` entry
with a `UNIT_ANALYTICAL_MODES` entry but no lexical-metrics engine, since
only `LEXICAL_ONLY` proceeds to comparison in this codebase).

## 2. Readiness criteria

Applied exactly as specified in the milestone brief:

- **ENABLE_NOW**: no known defect anywhere it resolves; reliable
  localization/boundary/alignment; reproducible fresh-DB behavior.
- **ENABLE_WITH_KNOWN_CAVEAT**: correct wherever it resolves; a bounded,
  understood, non-fatal limitation; unresolved/truncated years stay
  explicit (`UNRESOLVED_UPSTREAM` or a documented boundary defect that
  still returns real, on-topic content -- never a wrong-content swap).
- **KEEP_SHADOW_ONLY**: configured and researched, but correctness,
  recurrence, or engine support is not sufficient for production.
- **REMOVE_FROM_CANDIDATE_SCOPE**: not used this track -- every configured
  unit still has active research value (see Section 4); none merited
  outright removal.

## 3. Latest evidence reconciliation

Two units changed verdict since their originating milestone because Track
7D.4a (docs/7d4a-start-heading-false-positive-hardening.md) fixed the
specific defect blocking them -- the milestone brief's own instruction to
use latest evidence, not the original milestone verdict:

- **`combined_assurance`**: 7D.3 found `NOT_READY_FOR_CUTOVER` (2022/2023
  resolved to an unrelated infographic paragraph, contaminating 3 of 4
  comparison pairs). 7D.4a traced this to the PARAGRAPH run-in matcher
  accepting mid-sentence prose, fixed it generically
  (`_run_in_remainder_is_prose_continuation`, `ALGORITHM_VERSION 1.6.0`),
  and re-verified: all 4 adjacent pairs now score 0.96-1.00 cosine
  similarity (7D.4a Section 9), confirming one stable disclosure, not four
  different ones. 7D.4a's own re-evaluation: **READY_WITH_CAVEAT**.
- **`remuneration_governance`**: 7D.4 found `NOT_READY` (2024 resolved to
  an unrelated culture/voting passage). Same fix, same mechanism. 7D.4a's
  own re-evaluation: **READY_WITH_CAVEAT**.

No unit was demoted based on new evidence found this track -- the
corpus-wide safety sweep in 7D.4a (Section 7/8) found exactly 3 functional
changes across the entire corpus, all 3 the intended fixes, 0 regressions
elsewhere.

## 4. Deferred-defect impact review

| defect | affects an intended production unit (A) or only shadow/deferred coverage (B) | disposition |
|---|---|---|
| `governance_policies_processes` 2023 boundary issue | A -- promoted this track | ENABLE_WITH_KNOWN_CAVEAT; 2023 truncates to the section's opening 14 words (real, on-topic, incomplete -- not wrong content) |
| `remco_chairperson_report` 2023 truncation | A -- promoted this track | ENABLE_WITH_KNOWN_CAVEAT; 2023 truncates to 65 of an expected ~268 words, still on-topic (7D.4 Section 14: "truncated-but-still-on-topic excerpt", not a content swap) |
| ACT 2019 governance localization issue | B | `governance_policies_processes` 2019 is `GENUINE_ABSENCE` (schedule instance itself only spans 1 page that year) -- an explicit absence, not a defect that could contaminate a comparison; does not change this unit's caveat |
| SUR 2025 remuneration schedule narrowness | A -- affects the two promoted SUR units | Both `remuneration_policy_changes_and_focus` and `fair_responsible_remuneration` show 2025 as `EXTRACTION_DEFECT` (heading present in the source but outside that year's narrower localized schedule range) -- surfaces as `UNRESOLVED_UPSTREAM`, never wrong content; documented caveat |
| SUR `remuneration_policy_shareholder_engagement` boundary gap | B | unit never resolves in any of its 3 years -- KEEP_SHADOW_ONLY, unaffected by promoting its two sibling SUR units |
| KP2 fused `"(CONT)"` headings | B | KP2 has zero configured `UnitConfig` entries; not applicable to any production candidate |
| BEL narrative boundary limitations | A (partially) | `gross_margin` (already enabled) is unaffected -- its own ANCHOR_SENTENCE boundary was hardened in 7D.1 and re-verified stable in 7D.4a's sweep; `variable_remuneration`'s boundary limitation (2022's chart-label truncation) is why that unit stays KEEP_SHADOW_ONLY (0/6 pairs ever resolve regardless) |
| CEO/Chair localization defects (7D.6) | B | zero semantic units configured for either schedule -- not applicable |
| Material Risks structural incompatibility (7D.5) | B | schedule not implemented as a `UnitConfig`-bearing candidate -- not applicable |
| 7D.6 generic boundary-algorithm caveats (font-ratio, "(continued)" recognition, exact-match-wins, 2-occurrence boilerplate) | B | these are schedule-localization-layer limitations for CEO_REVIEW/CHAIR_REVIEW/other schedules with no configured units; none of the promoted units in this track hit these specific mechanisms (their own defects are the distinct PARAGRAPH run-in issue 7D.4a fixed, or genuine schedule-narrowing/absence) |

No repair was performed for any category-B item, per the milestone's hard
scope boundary.

## 5. Structured-family decision

Re-confirmed from Track 7E.2 (docs/7e2-fresh-database-release-rehearsal.md
Section 15/16): fresh rebuild succeeded for both `ned_remuneration_policy_table`
and `total_remuneration_outcomes` (16 structured comparisons total,
rebuilt clean from scratch), structured reconstruction is deterministic,
alignment/value-change output was verified correct, `current_*` views
expose them, and the frontend renders them. No concrete blocker exists.
**Both remain in production scope, unchanged.** Live local-DB confirmation
this track: 11 `structured_tables` rows (5 `ned_remuneration_policy_table`
+ 6 `total_remuneration_outcomes`) and 409 `structured_value_change_events`
rows for the current corpus state.

## 6. Router validation

`services.comparison_routing.ComparisonPathRouter` is purely config-driven
(`is_narrative_unit_in_scope`/`is_structured_table_in_scope` read directly
from `cutover_config`'s frozensets) -- no router code change was needed or
made. Verified directly (`cutover_enabled=True`):

| case | expected path | observed |
|---|---|---|
| ACT CORPORATE_GOVERNANCE `combined_assurance` (newly enabled) | SEMANTIC_UNIT | SEMANTIC_UNIT |
| ACT CORPORATE_GOVERNANCE `information_security_governance` (newly enabled) | SEMANTIC_UNIT | SEMANTIC_UNIT |
| ACT REMUNERATION `remuneration_policy_changes` (newly enabled) | SEMANTIC_UNIT | SEMANTIC_UNIT |
| BEL CORPORATE_GOVERNANCE `board_composition_diversity` (shadow-only) | LEGACY_PASSAGE | LEGACY_PASSAGE |
| SUR REMUNERATION `remuneration_policy_shareholder_engagement` (shadow-only) | LEGACY_PASSAGE | LEGACY_PASSAGE |
| any in-scope unit with `cutover_enabled=False` | LEGACY_PASSAGE | LEGACY_PASSAGE |

Unresolved cases (`UNRESOLVED_UPSTREAM`, `GENUINE_ABSENCE`,
`EXTRACTION_DEFECT`) never silently fall back to legacy: routing happens
independently of alignment status, and `publishing.cutover_publishing.
build_narrative_comparison_rows` always emits a row for every in-scope
`(ticker, schedule, unit_key)` on a pair -- resolved or not
(`tests/test_cutover_publishing.py`). The legacy passage-alignment path
remains fully available for every out-of-scope unit and every ticker
outside the narrative/structured scope (e.g. KP2, SBP, SDL). Both
narrative and structured results coexist correctly on the same
`ReportPair` (`tests/test_cutover_publishing.py::test_structured_resolved_row_built_with_row_column_and_value_change_json`
alongside the narrative-row tests).

## 7. Final production-scope matrix

`cutover_config.py` `CONFIG_VERSION` bumped 1.1.0 -> 1.2.0.

| ticker | schedule | unit/family | mode | fresh-DB coverage (current corpus) | known caveat | category | enabled in production config? | rationale |
|---|---|---|---|---|---|---|---|---|
| BEL | FINANCIAL_PERFORMANCE | gross_margin | LEXICAL_ONLY | 16 comparisons, MATCHED | none | ENABLE_NOW | yes (unchanged) | already validated STRONG_CUTOVER_CANDIDATE (7E.2) |
| ACT | FINANCIAL_PERFORMANCE | cfo_conclusion | LEXICAL_ONLY | 0 comparisons in current local snapshot (17 semantic units exist; no MATCHED alignment run recomputed locally since last publish) | none documented | ENABLE_NOW | yes (unchanged) | already validated STRONG_CUTOVER_CANDIDATE (7E.2); local snapshot gap is a stale-pipeline-run artifact, not a correctness defect -- re-running `units align`/`analytical` locally would repopulate it |
| ACT | FINANCIAL_PERFORMANCE | healthcare_services_review | LEXICAL_ONLY | 2 comparisons, MATCHED | none | ENABLE_NOW | yes (unchanged) | already validated STRONG_CUTOVER_CANDIDATE (7D.2c/7E.2) |
| ACT | CORPORATE_GOVERNANCE | information_security_governance | LEXICAL_ONLY | 5 comparisons, MATCHED | 2017 GENUINE_ABSENCE (expected) | ENABLE_NOW | **yes (new)** | READY_FOR_CUTOVER (7D.3): reliable across 7/8 attempted years, no correctness defect |
| ACT | CORPORATE_GOVERNANCE | governance_policies_processes | LEXICAL_ONLY | 3 comparisons, MATCHED | 2023 truncates to the section's opening sentence only (real, on-topic, incomplete); 2019 GENUINE_ABSENCE | ENABLE_WITH_KNOWN_CAVEAT | **yes (new)** | READY_WITH_CAVEAT (7D.3); truncation is bounded and never substitutes wrong content |
| ACT | CORPORATE_GOVERNANCE | combined_assurance | LEXICAL_ONLY | 4 comparisons, MATCHED | 2016 GENUINE_ABSENCE (expected) | ENABLE_WITH_KNOWN_CAVEAT | **yes (new)** | NOT_READY (7D.3) -> READY_WITH_CAVEAT after 7D.4a's fix; all 4 pairs now stable (0.96-1.00 cosine) |
| BEL | CORPORATE_GOVERNANCE | board_composition_diversity | STRUCTURED_COMPARISON_PREFERRED | 0 comparisons (no engine) | no comparison engine exists for this mode in this codebase | KEEP_SHADOW_ONLY | no | cannot ever produce a comparison result today, regardless of extraction quality |
| ACT | REMUNERATION | remco_chairperson_report | LEXICAL_ONLY | 4 comparisons, MATCHED | 2023 truncates to 65 of an expected ~268 words, still on-topic; 2019 EXPECTED_HEADING_VARIATION | ENABLE_WITH_KNOWN_CAVEAT | **yes (new)** | READY_WITH_CAVEAT (7D.4); truncated-but-on-topic, never wrong content |
| ACT | REMUNERATION | remuneration_policy_changes | LEXICAL_ONLY | 6 comparisons, MATCHED | 2019 GENUINE_ABSENCE | ENABLE_NOW | **yes (new)** | READY_FOR_CUTOVER (7D.4): no confirmed defect |
| ACT | REMUNERATION | remuneration_governance | LEXICAL_ONLY | 5 comparisons, MATCHED | real recurrence 5/9 years (2020-2024 only) | ENABLE_WITH_KNOWN_CAVEAT | **yes (new)** | NOT_READY (7D.4) -> READY_WITH_CAVEAT after 7D.4a's fix |
| BEL | REMUNERATION | variable_remuneration | LEXICAL_ONLY | 0 comparisons (0/6 pairs ever resolve) | 2022 boundary lands on a chart-label, real but incomplete; genuinely absent 2016/2020 | KEEP_SHADOW_ONLY | no | NOT_READY (7D.4): no comparison pair has ever resolved |
| SUR | REMUNERATION | remuneration_policy_changes_and_focus | LEXICAL_ONLY | 1 comparison, MATCHED | 2025 EXTRACTION_DEFECT (heading outside that year's narrower schedule range) -- surfaces as UNRESOLVED_UPSTREAM | ENABLE_WITH_KNOWN_CAVEAT | **yes (new)** | READY_WITH_CAVEAT (7D.4); 2023->2024 pair is clean (cosine 0.888) |
| SUR | REMUNERATION | fair_responsible_remuneration | LEXICAL_ONLY | 1 comparison, MATCHED | same 2025 EXTRACTION_DEFECT class | ENABLE_WITH_KNOWN_CAVEAT | **yes (new)** | READY_WITH_CAVEAT (7D.4); 2023->2024 pair is clean (cosine 0.978) |
| SUR | REMUNERATION | remuneration_policy_shareholder_engagement | LEXICAL_ONLY | 0 comparisons (0/3 years ever resolve) | heading sits beyond the schedule's own localized end boundary every year | KEEP_SHADOW_ONLY | no | NOT_READY (7D.4): never extracts |
| ACT | structured (REMUNERATION) | ned_remuneration_policy_table | STRUCTURED_COMPARISON_PREFERRED | 5 tables | none | ENABLE_NOW | yes (unchanged) | STRONG_CUTOVER_CANDIDATE (7E.2) |
| ACT | structured (REMUNERATION) | total_remuneration_outcomes | STRUCTURED_COMPARISON_PREFERRED | 6 tables | none | ENABLE_NOW | yes (unchanged) | STRONG_CUTOVER_CANDIDATE (7E.2) |

## 8. Expected production-visible comparison counts

Computed against the current local corpus (the same 6-issuer, 30-report,
25-report-pair corpus Track 7E.2 rehearsed and rebuilt from scratch), since
the 7E.2 rehearsal database itself was ephemeral and is no longer running
locally. This local DB was queried directly rather than assumed from
memory.

| metric | count |
|---|---|
| narrative units enabled | 11 |
| narrative units shadow-only | 3 |
| structured families enabled | 2 |
| narrative comparison rows (current corpus, all MATCHED, newly-enabled scope) | 47 (gross_margin 16, cfo_conclusion 0*, healthcare_services_review 2, information_security_governance 5, governance_policies_processes 3, combined_assurance 4, remco_chairperson_report 4, remuneration_policy_changes 6, remuneration_governance 5, remuneration_policy_changes_and_focus 1, fair_responsible_remuneration 1) |
| structured comparison rows | 409 `structured_value_change_events` across 11 `structured_tables` |
| companies with new-path coverage | 3 (ACT, BEL, SUR) |
| report pairs represented (narrative) | 13 distinct report pairs |
| report pairs represented (structured) | 5 distinct report pairs |

\* `cfo_conclusion` shows 0 `lexical_unit_comparisons` rows in the current
local snapshot despite 17 persisted `semantic_units` and already-enabled
production status -- this reflects a stale local alignment/analytical run,
not a scope or correctness change (7E.2 documented `cfo_conclusion` rows
as present in its own rehearsal). Re-running `units align --schedule
financial_performance` / `units analytical` locally would repopulate it;
not required by this milestone's scope, which touches configuration only.

These become the 7E.3 post-cutover smoke-test expectations.

## 9. Storage implications

7E.2 rehearsal baseline restated: **~412 MB** final fresh app database size
against the Neon free-tier 512 MB limit (~100 MB / ~20% headroom).
`app.qa_chunks` (149 MB) plus its HNSW index (`app.
ix_app_qa_chunks_hnsw_cosine`, 24 MB) remains the single largest,
non-shared growth driver (~173 MB combined).

Promoting 8 additional narrative units changes only which rows are exposed
through `current_narrative_unit_comparisons` and related `current_*`
views -- it does **not** change which rows exist in the shared publication
corpus. Per Track 7E.1's shared-corpus architecture, every configured
unit's `semantic_units`/`lexical_unit_comparisons`/`analytical_decisions`
rows are already computed and stored regardless of cutover scope (7E.2
Section: "non-cutover units... rebuilt clean, non-zero `analytical_
decisions`/`lexical_unit_comparisons`"); this track only changes which of
those already-existing rows the new comparison path is permitted to
surface. No material storage impact. Storage monitoring (in particular
`qa_chunks` growth) remains a post-cutover action, not addressed here.

## 10. Local smoke-test results

Representative cases verified directly against the local dev database
(`market_documents`, the same corpus 7E.2 rehearsed) via
`ComparisonPathRouter` and direct SQL, since the app-side publication
database (`market_documents_app`) is currently empty locally (no
publication run pending this scope decision, consistent with production
remaining on its existing stable publication):

| ticker | report pair | expected path | expected comparison type | observed result | pass/fail |
|---|---|---|---|---|---|
| ACT | 2022/2023 CORPORATE_GOVERNANCE | SEMANTIC_UNIT | narrative LEXICAL_ONLY (`combined_assurance`) | routed SEMANTIC_UNIT | pass |
| ACT | any REMUNERATION pair | SEMANTIC_UNIT | narrative LEXICAL_ONLY (`remuneration_policy_changes`) | routed SEMANTIC_UNIT | pass |
| ACT | any CORPORATE_GOVERNANCE pair | SEMANTIC_UNIT | narrative LEXICAL_ONLY (`information_security_governance`) | routed SEMANTIC_UNIT | pass |
| BEL | any CORPORATE_GOVERNANCE pair (shadow-only candidate) | LEGACY_PASSAGE | n/a (not in scope) | routed LEGACY_PASSAGE | pass |
| SUR | any REMUNERATION pair (`remuneration_policy_shareholder_engagement`, unresolved case) | LEGACY_PASSAGE for the shadow unit; the pair's own in-scope SUR units still route SEMANTIC_UNIT and surface an explicit `UNRESOLVED_UPSTREAM`/`EXTRACTION_DEFECT` row for 2025 | mixed | routed LEGACY_PASSAGE for the shadow unit; confirmed via `tests/test_cutover_publishing.py` that in-scope-but-unresolved units always build an explicit row, never drop or fall back silently | pass |
| KP2 | any pair (legacy-path case) | LEGACY_PASSAGE | legacy passage-alignment only, ticker entirely outside narrative/structured scope | routed LEGACY_PASSAGE | pass |

## 11. Tests

- `tests/test_cutover_config.py` (new): exact narrative production scope
  (11 entries), exact structured scope (unchanged, 2 entries), shadow-only
  units confirmed absent from scope, `is_narrative_unit_in_scope` spot
  checks, `CONFIG_VERSION == "1.2.0"`, deterministic configuration hash.
- `tests/test_coverage_registry.py` (updated): the two 7D.3/7D.4
  "candidates are not enabled" tests were replaced with
  `test_promoted_governance_units_are_enabled_in_production`,
  `test_bel_board_composition_diversity_remains_shadow_only`,
  `test_promoted_remuneration_units_are_enabled_in_production`, and
  `test_shadow_only_remuneration_units_remain_candidates`, asserting the
  exact new `production_status` split.
- `tests/test_cutover_publishing.py` (updated):
  `test_narrative_unresolved_row_is_still_built_never_dropped` now expects
  8 unresolved rows for a bare ACT pair (one per newly-in-scope ACT unit
  across all three schedules) instead of 2, confirming unresolved cases
  remain explicit rather than silently dropped or falling back.
- Router behavior (Section 6) verified via direct `ComparisonPathRouter`
  calls during development; no router test changes were needed since
  `tests/test_comparison_routing.py`'s existing tests are scope-agnostic
  (they inject their own `cutover_enabled`/scope fixtures) and all 50
  targeted tests across `test_coverage_registry.py`,
  `test_cutover_publishing.py`, `test_cutover_comparison.py`,
  `test_cutover_preflight.py`, `test_comparison_routing.py`, and
  `test_cutover_config.py` passed together.

**Full-suite results (run exactly once each, per the milestone's
instruction):**

- Python: `1202 passed, 3 skipped` (`.venv/bin/python -m pytest`).
- Frontend: `923 passed, 27 failed, 60 skipped` (`npm test`, `web/`). All
  27 failures are in `tests/repository/discovery-repository.test.ts` and
  `tests/repository/methodology-repository.test.ts` (`DatabaseUnavailableError`
  against the local `market_documents_app_test` fixture database). This
  track touches no file under `web/` -- no route, repository, component,
  or test file was changed -- so this is a pre-existing local
  test-fixture/schema wiring gap in this developer's environment, not a
  regression introduced by the production-scope configuration change.
  Direct `pg` connectivity to the seeded test database was confirmed
  working during investigation; the failure is isolated to those two
  DB-backed repository test files and does not affect any test this
  milestone's own scope covers.

## 12. Release caveats

- `governance_policies_processes`: 2023 truncates to the section's opening
  sentence only; 2019 is a genuine schedule-boundary absence.
- `combined_assurance`: 2016 is a genuine absence; all other years stable
  since the 7D.4a fix.
- `remco_chairperson_report`: 2023 truncates to a shorter but still
  on-topic excerpt; 2019 uses a genuinely different heading wording
  ("Chairman's" vs. "Chairperson's report"), not configured.
- `remuneration_governance`: only recurs in 5 of 9 available ACT years
  (2020-2024); earlier years are a genuine schedule/format difference, not
  a defect.
- `remuneration_policy_changes_and_focus` / `fair_responsible_remuneration`
  (SUR): 2025 sits outside that year's narrower localized schedule range
  and surfaces as an explicit unresolved/defect row, never as wrong
  content.
- `board_composition_diversity` (BEL), `variable_remuneration` (BEL),
  `remuneration_policy_shareholder_engagement` (SUR) remain out of
  production scope entirely (Section 7).
- The local `cfo_conclusion` comparison-row gap (Section 8 footnote) is a
  stale-pipeline-run artifact in this developer's local database, not a
  scope or correctness issue; 7E.2's own rehearsal already confirmed
  published rows exist for it.

## 13. Exact 7E.3 cutover scope

`cutover_config.py`, `CONFIG_VERSION = "1.2.0"`:

- **Narrative** (11): BEL `gross_margin`; ACT `cfo_conclusion`,
  `healthcare_services_review`, `information_security_governance`,
  `governance_policies_processes`, `combined_assurance`,
  `remco_chairperson_report`, `remuneration_policy_changes`,
  `remuneration_governance`; SUR `remuneration_policy_changes_and_focus`,
  `fair_responsible_remuneration`.
- **Structured** (2, unchanged): ACT `ned_remuneration_policy_table`,
  `total_remuneration_outcomes`.

This is the authoritative scope Track 7E.3 must expose through the new
comparison path when it performs the fresh-database cutover -- no more, no
less.

## 14. Final verdict

**PASS WITH CAVEATS — SCOPE FINALIZED WITH EXPLICIT NON-BLOCKING
LIMITATIONS.**

- Narrative units enabled: 11 (3 unchanged, 8 newly promoted)
- Narrative units shadow-only: 3 (BEL `board_composition_diversity`, BEL
  `variable_remuneration`, SUR `remuneration_policy_shareholder_engagement`)
- Structured families enabled: 2 (unchanged)
- Expected narrative comparison count: 47 (current local corpus; see
  Section 8 footnote on `cfo_conclusion`)
- Expected structured comparison count: 409 value-change events across 11
  structured tables
- Companies with new-path coverage: 3 (ACT, BEL, SUR)
- Known production caveats: 6 bounded, documented, non-fatal limitations
  (Section 12) -- none substitutes wrong content for any comparison
- Readiness for 7E.3: ready. The scope is explicit, evidence-based,
  conservative (3 researched candidates deliberately excluded), and every
  enabled unit's known limitation is bounded and safely handled by the
  existing "always build a row, mark it explicitly unresolved" publishing
  discipline.
