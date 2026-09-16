# Track 7C.6 — Scoped Production Cutover

Makes the semantic-unit/structured-table pipeline (7C.1–7C.4) the primary
comparison path for exactly the scope 7C.5's shadow evaluation validated as
ready, with an explicit rollback and no silent legacy fallback. The legacy
passage-alignment pipeline is unmodified and remains authoritative for
everything else.

## 1. Exact supported scope

`src/market_documents/services/cutover_config.py`:

| Type | Ticker | Schedule | Unit / table family |
|---|---|---|---|
| Narrative | BEL | FINANCIAL_PERFORMANCE | `gross_margin` |
| Narrative | ACT | FINANCIAL_PERFORMANCE | `cfo_conclusion` |
| Structured | ACT | REMUNERATION | `ned_remuneration_policy_table` |
| Structured | ACT | REMUNERATION | `total_remuneration_outcomes` |

Every other (ticker, schedule, unit/table) combination — including every
other ticker in the corpus (KP2, SBP, SDL, SUR) and every other narrative
subsection of BEL/ACT — is out of scope and stays on the legacy pipeline
unconditionally. The scope is a frozen, explicit registry
(`NEW_PIPELINE_NARRATIVE_SCOPE`/`NEW_PIPELINE_STRUCTURED_SCOPE`), never
inferred from whether rows happen to exist in the database.

## 2. Routing rules

`src/market_documents/services/comparison_routing.py`:
`ComparisonPathRouter.route_narrative(ticker, schedule, unit_key)` and
`.route_structured(ticker, table_family_key)` return one of
`ComparisonBackend.SEMANTIC_UNIT` / `STRUCTURED_TABLE` / `LEGACY_PASSAGE`,
deterministically:

```
if not cutover_enabled:
    LEGACY_PASSAGE
elif (ticker, schedule, unit_key) in NEW_PIPELINE_NARRATIVE_SCOPE:
    SEMANTIC_UNIT
elif (ticker, table_family_key) in NEW_PIPELINE_STRUCTURED_SCOPE:
    STRUCTURED_TABLE
else:
    LEGACY_PASSAGE
```

Routing reads no database state — it is a pure function of the request and
the two frozen registries.

## 3. Feature flag / rollback

`SEMANTIC_COMPARISON_CUTOVER_ENABLED` (env var; `Settings.semantic_comparison_cutover_enabled`,
default `false`).

- `false` (default): every request routes `LEGACY_PASSAGE`, unconditionally
  — byte-for-byte the pre-7C.6 behavior.
- `true`: additionally routes the scoped entries above to the new pipeline.

**To disable the cutover in any environment: set
`SEMANTIC_COMPARISON_CUTOVER_ENABLED=false` (or unset it) and restart the
process.** No code change, migration, or deployment is required — this is
the entire rollback procedure. There is deliberately no per-ticker or
per-schedule flag matrix; the scope registry itself is the only
finer-grained control, and changing it is a code change, not a runtime
toggle.

## 4. Unresolved behavior — no silent legacy fallback

`src/market_documents/services/cutover_comparison.py` returns one of three
response types. For in-scope requests where the new pipeline has not
produced a trustworthy result, the response's `status` is explicit —
`UNRESOLVED_UPSTREAM`, `AMBIGUOUS`, or `REVIEW_REQUIRED` — and
`comparison_backend` stays `SEMANTIC_UNIT`/`STRUCTURED_TABLE`. The response
never silently substitutes a legacy result and presents it as the new
pipeline's own. Legacy is not read or attached at all in this path (no
dual-read audit mode was built in 7C.6 — Section 11 of the milestone brief
marks it optional and it was not needed to meet the acceptance criteria).

For out-of-scope requests, the response is `LegacyComparisonResponse`
(`comparison_backend=LEGACY_PASSAGE`, `status=NOT_AVAILABLE`) — a signal
that the legacy pipeline (unchanged) remains authoritative, never a
computed payload.

## 5. API / service integration

Research confirmed **no HTTP/FastAPI layer sits between the Next.js web
app and these Python services** — the web app reads the `app` schema
directly over Postgres, populated by `publishing/publisher.py`. The only
current "assemble a comparison for a report pair" call site is
`publishing/source_dataset.py::_resolve_comparison`, which reads legacy
`Passage`/`PassageAlignment`/`FeatureRun` lineage exclusively and is
**unmodified by 7C.6**.

`services.cutover_comparison` is the new, freestanding normalized-response
layer 7C.6 adds — the "smallest adapter necessary" the milestone calls
for. It is exercised today through:

- `market-documents units compare-cutover <ticker> (--unit-key | --table-family)`
  — prints the routed response for every adjacent-year pair (diagnostic).
- `market-documents units cutover-check` — preflight (Section 9 below).
- Direct calls from tests/future callers: `get_narrative_comparison(session, pair, schedule, unit_key)`,
  `get_structured_comparison(session, pair, table_family_key)`.

**Publishing/`app.report_comparisons` integration is deliberately not
wired in this milestone.** That table's columns are shaped for legacy
metrics (`disclosure_change_score`, tone/uncertainty deltas, etc.); the new
pipeline's narrative/structured payloads are structurally different and
the milestone brief explicitly forbids "flattening structured output into
prose" or fabricating legacy-shaped numbers from the new pipeline's data.
Building that bridge is real 7A.3/7A.4 (frontend build-out) scope — a
schema/design decision, not a routing integration — and is out of 7C.6's
own stated bounds ("do not create a full replacement publishing model").
The router and normalized-response layer are the complete, correctly-scoped
"service/API integration" 7C.6 delivers; wiring them into the publish
pipeline's DB writes is deferred to that future milestone.

## 6. Response shape

Discriminated by type, matching the milestone's "don't pretend lexical and
structured outputs have identical payloads" instruction:

- `NarrativeComparisonResponse` — `alignment_status`, `analytical_mode`,
  `lexical_metrics` (tfidf/jaccard/edit/sequence similarity, word counts),
  `earlier_provenance`/`later_provenance`, `review_reason`.
- `StructuredComparisonResponse` — `row_alignments`, `column_alignments`,
  `value_change_events` (raw + numeric values, event type), `footnotes`,
  provenance, `review_reason`.
- `LegacyComparisonResponse` — `note` only; never a computed payload.

No materiality score or composite score was added, per the milestone's
explicit instruction.

## 7. Provenance behavior

Every `NarrativeComparisonResponse`/`StructuredComparisonResponse` with a
resolvable unit/table carries a `ProvenanceRef`: `report_id`,
`directory_year`, `start_page`/`end_page`, `source_block_ids` (persisted
`SemanticUnitSourceBlock.text_block_id` / `StructuredTableRow.source_block_id`),
and a `source_excerpt` (the unit's `source_text`, or the table's
`source_heading`). Verified in `tests/test_cutover_comparison.py`'s
provenance assertions. No response drops provenance at the API boundary.

## 8. Legacy preservation

`services.cutover_comparison`/`comparison_routing`/`cutover_config`/
`cutover_preflight` import **only** 7C.1–7C.5 models
(`SemanticUnit*`, `AnalyticalDecision*`, `StructuredTable*`) — none of them
import or touch `Passage`, `PassageAlignment`, `AlignmentRun`, or any
publishing model. No migration was added. No legacy service, CLI command,
or publishing behavior was changed. The full pre-existing test suite
(1039 passed, 3 skipped before this milestone's tests were added) remains
green with 7C.6's tests added on top.

## 9. Deployment prerequisites / cutover preflight

`market-documents units cutover-check [--ticker TICKER]`
(`services/cutover_preflight.py`) reports one of `READY` / `MISSING_DATA` /
`UNRESOLVED` / `UNSUPPORTED` per configured scope entry, by calling the
same `get_narrative_comparison`/`get_structured_comparison` functions a
real caller would use (with the cutover flag forced on for the check only)
and counting how many report pairs actually resolve. It never
auto-backfills — a `MISSING_DATA`/`UNRESOLVED` verdict means "run the
relevant `units localize`/`extract`/`align`/`classify`/`structure`/
`compare-structured` stage first."

**Backfill performed for this milestone** (Section 13 of the brief: only
what supported scope requires): `units classify BEL` and `units classify
ACT` were run to persist the `AnalyticalDecisionRun`/`LexicalUnitComparison`
rows 7C.3 already computes but had not yet materialized in this database
for the two configured narrative units. No new schedule, unit, table
family, or extraction/alignment logic was touched.

## 10. Tests

- `tests/test_comparison_routing.py` — routing table (A), feature flag (B),
  rollback toggle.
- `tests/test_cutover_comparison.py` — unresolved/ambiguous/review-required
  behavior with no silent fallback (C), narrative MATCHED response with
  lexical metrics (D), structured row/column/value-change response (E),
  provenance (F), legacy preservation for out-of-scope tickers/units (G).
- `tests/test_cutover_preflight.py` — READY/MISSING_DATA/UNRESOLVED
  verdicts.
- Full existing suite (7C.1–7C.5, legacy passage/publishing) reruns green
  unchanged (H): 1039 passed, 3 skipped, 0 failed as of 7C.5's commit;
  see Section 12.

## 11. Real-corpus cutover smoke results

Run via `units compare-cutover`/`units cutover-check` against the real dev
database, cutover flag forced on for the check:

| Case | Result |
|---|---|
| BEL 2018→2019 `gross_margin` | `SEMANTIC_UNIT` / `RESOLVED` / MATCHED, tfidf=0.7469, words 64→47, provenance present |
| BEL 2021→2022 `gross_margin` | `SEMANTIC_UNIT` / `RESOLVED` / MATCHED, tfidf=0.7450, words 139→101, provenance present |
| BEL 2019→2020 `gross_margin` | `SEMANTIC_UNIT` / `UNRESOLVED_UPSTREAM`, explicit reason, **no legacy fallback** |
| ACT `ned_remuneration_policy_table`, e.g. 2022→2023 | `STRUCTURED_TABLE` / `RESOLVED`, 18 rows / 3 columns / 51 value-change events |
| BEL `net_debt` (unsupported unit) | `LEGACY_PASSAGE` / `NOT_AVAILABLE` for every pair |
| SBP `gross_margin` (unsupported ticker) | `LEGACY_PASSAGE` / `NOT_AVAILABLE` for every pair |
| Cutover flag off, BEL `gross_margin` | `LEGACY_PASSAGE` / `NOT_AVAILABLE` — confirms rollback default |

`units cutover-check` (flag forced on) verdicts: `BEL FINANCIAL_PERFORMANCE
gross_margin: READY` (2/6 pairs resolve — the other 4 are BEL's own
documented 7C.5 recall-defect years, correctly UNRESOLVED_UPSTREAM, not
fixed here per the milestone's hard stop), `ACT FINANCIAL_PERFORMANCE
cfo_conclusion: UNRESOLVED` (0/9 — matches 7C.5's own documented finding
that no real ACT `cfo_conclusion` pair has ever resolved MATCHED in this
corpus; not a 7C.6 regression), `ACT ned_remuneration_policy_table: READY`
(4/9), `ACT total_remuneration_outcomes: READY` (5/9).

ACT `cfo_conclusion` being `UNRESOLVED` at the ticker level (rather than
`READY`) is expected and consistent with 7C.5's own finding — it is not a
7C.6 defect, and per the milestone's hard stop, fixing the underlying
recall gap is explicitly out of scope. The cutover flag should not be
relied on to make ACT `cfo_conclusion` comparisons in production today;
BEL `gross_margin` and both ACT structured-table families are.

## 12. Deployment / preview result

No staging/preview deployment step exists for this milestone: 7C.6 adds no
migration, no publishing-pipeline change, and no frontend change — nothing
in the deployed application's request path changes when the flag is
flipped, because nothing in the application's request path (the `app`
schema / Next.js web app) reads from `services.cutover_comparison` yet
(Section 5). The flag and router are live in this codebase; enabling them
in production has no observable effect until a future milestone wires the
publishing pipeline or an API layer to call `services.cutover_comparison`.

**CUTOVER NOT YET ENABLED IN PRODUCTION.**

## 13. Rollback procedure

1. Set `SEMANTIC_COMPARISON_CUTOVER_ENABLED=false` (or leave/return it
   unset — this is the default).
2. Restart the process reading `Settings` (no other service currently
   reads it, since nothing is wired to call `services.cutover_comparison`
   in production yet — see Section 12).
3. No data migration, backfill reversal, or code rollback is needed: no
   schema changed, and legacy `Passage`/`PassageAlignment`/publishing data
   was never touched.

## 14. Remaining unsupported scope

Everything not listed in Section 1: every ticker other than BEL/ACT; every
BEL/ACT narrative subsection other than `gross_margin`/`cfo_conclusion`;
every ACT table family other than the two REMUNERATION ones listed; every
non-FINANCIAL_PERFORMANCE/REMUNERATION schedule. All of it stays on the
unmodified legacy pipeline. Widening this scope, fixing the three known
7C.5 recall defects (BEL 2017/2020 `gross_margin`, ACT 2019 schedule
mislocalization), adding materiality scoring, and wiring the publishing
pipeline/frontend to the new responses are all explicitly future,
separate-milestone work per the brief's hard stop.

## 15. Final verdict

**PASS WITH NON-BLOCKING CAVEATS — SCOPED CUTOVER READY**

All Section 15 test categories (A–H) pass; the real-corpus smoke test in
Section 11 matches the exact expected outcomes the milestone specified,
including the required "no silent fallback" behavior for BEL 2019→2020.
The one caveat: ACT `cfo_conclusion` currently has zero resolving pairs in
this corpus, which is a pre-existing, already-documented 7C.5 finding
(not a 7C.6-introduced defect) — the cutover is ready to enable for BEL
`gross_margin` and both ACT structured-table families today; ACT
`cfo_conclusion` will correctly report `UNRESOLVED_UPSTREAM`/no result
until a future milestone addresses the underlying recall gap, which this
module surfaces honestly rather than masking.

**CUTOVER NOT YET ENABLED IN PRODUCTION** (Section 12).

---

**Hard stop.** No schedule, unit, or table family was added or expanded.
No BEL/ACT recall defect was fixed. No materiality scoring was added. The
legacy passage pipeline was not modified or deleted. The application/UI
was not redesigned. Wiring `services.cutover_comparison` into the
publishing pipeline or an API layer is separate, future work.
