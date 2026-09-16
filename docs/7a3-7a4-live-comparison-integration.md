# Track 7A.3/7A.4 — Live Comparison Integration

Wires the Track 7C.6 cutover comparison layer (`comparison_routing.py`,
`cutover_comparison.py`) into the application path end users actually hit,
verifies it locally, and prepares (but does not execute) controlled staging
and production enablement.

## 1. Original production call graph

Audited by reading the real code, not assumed from naming. Before this
milestone:

```
Browser
  -> Next.js Server Component (no API route exists for comparisons)
       web/app/comparisons/[comparisonId]/page.tsx
  -> comparison-service.ts::getComparisonPageViewModel
  -> PostgresComparisonRepository (web/lib/repositories/postgres-comparison-repository.ts)
  -> app.current_report_comparisons / app.current_language_metrics /
     app.current_passage_comparisons  (Postgres views, filtered to the
     active publication_id)
  -> app.report_comparisons / app.language_metrics / app.passage_comparisons
     (real tables -- written ONLY by an offline batch job)
       <- market_documents.publishing.publisher.PublicationBuilder.build()
       <- invoked via `market-documents publish build/validate/promote`
       <- reads the LEGACY passage-alignment/dictionary-metrics pipeline's
          already-computed research-schema output
          (services/feature_extraction.py, services/financial_language_signals.py)
```

Key finding: **the web app has no API route and never calls Python at
request time.** Every comparison page is a Server Component reading
Postgres views directly. The `app.current_*` views are thin
`WHERE publication_id = active_publication_id` filters over tables that
only an offline publish job ever writes. The Track 7C.6 cutover layer
(`comparison_routing.py`/`cutover_comparison.py`) was, before this
milestone, called **only** from two CLI diagnostic commands
(`units cutover-check`, `units compare-cutover`) — its output was computed
fresh per invocation and never persisted anywhere.

## 2. New production call graph

```
Browser
  -> web/app/comparisons/[comparisonId]/page.tsx
  -> comparison-facade.ts::getComparisonView   <-- the one facade (Section 4)
       |-> comparison-service.ts::getComparisonPageViewModel   (unchanged; "legacy")
       |-> config/cutover.ts::isCutoverEnabled()                (reads SEMANTIC_COMPARISON_CUTOVER_ENABLED)
       |-> PostgresComparisonRepository.getNarrativeUnitComparison       (new)
       |-> PostgresComparisonRepository.getStructuredTableComparisons   (new)
  -> app.current_narrative_unit_comparisons / app.current_structured_table_comparisons
     (new Postgres views, same active-publication-filter pattern)
  -> app.narrative_unit_comparisons / app.structured_table_comparisons
     (new real tables -- written ONLY by the offline publish job)
       <- PublicationBuilder._build_rows()'s new cutover pass
       <- publishing/cutover_publishing.py::build_narrative_comparison_rows /
          build_structured_comparison_rows
       <- services/cutover_comparison.py::get_narrative_comparison /
          get_structured_comparison  (UNCHANGED -- Track 7C.6, not touched)
       <- ComparisonPathRouter(cutover_enabled=True)  (always force-enabled
          at publish time, mirroring `compare-cutover --force-enabled`)
```

## 3. Integration point selected, and why

The task's own framing offered two options for a publish-time-materialized
architecture:

- **A.** publishing invokes `cutover_comparison` and persists a normalized
  published result.
- **B.** the API invokes `cutover_comparison` against persisted 7C outputs
  directly.

Option B does not fit this application at all: there is no API layer, and
the web app (TypeScript, Vercel serverless/Node) cannot call Python
(`cutover_comparison.py`) at request time — there is no live HTTP boundary
between the two runtimes anywhere in this repo. **Option A is the only
architecturally viable choice**, and it is also "the architecture already
closest to current production conventions" per the task's own
instruction — every other piece of comparison data (`report_comparisons`,
`passage_comparisons`, `language_metrics`) already reaches the web app this
exact way.

**Where the feature flag actually lives at runtime.** Because publishing is
a periodic batch job, baking `SEMANTIC_COMPARISON_CUTOVER_ENABLED` into the
*publish-time* routing decision would mean the only way to roll back is to
republish — which directly conflicts with the task's requirement that
toggling the flag require no data migration or republish. So the flag's
enforcement point moved to the *read side*:

- **At publish time**, for every report pair whose `(ticker, schedule,
  unit_key)` / `(ticker, table_family_key)` is in the fixed 7C.6 scope
  config, the publish job *always* computes and persists the new-backend
  candidate result, using `ComparisonPathRouter(cutover_enabled=True)`.
  Because every call is for a combination drawn directly from the scope
  frozensets, the router can only ever select the new backend for it —
  never `LEGACY_PASSAGE` — so every persisted row is genuinely
  `RESOLVED`/`UNRESOLVED_UPSTREAM`/`AMBIGUOUS`/`REVIEW_REQUIRED`.
- **At read time**, the web app reads its own copy of
  `SEMANTIC_COMPARISON_CUTOVER_ENABLED` (same env var name, new to the web
  app — not an independent flag) to decide whether to *prefer* a persisted
  new-backend row over the legacy fields, when one exists for that
  comparison.
- Legacy data is published exactly as before, unconditionally, so
  flag-OFF behavior is byte-for-byte identical to pre-milestone production.

## 4. Schema / API changes

**New Postgres tables** (`migrations_app/versions/app_0009_cutover_comparisons.py`),
following every existing `app` schema convention (`AppUUIDPkMixin`,
`publication_id` FK+index, enums stored as plain strings, `UniqueConstraint`
on `(publication_id, report_comparison_id, ...)` for idempotent republish):

- `app.narrative_unit_comparisons` — one row per (report comparison, unit).
  `comparison_backend`, `status`, `schedule`, `unit_key`, `alignment_status`,
  `alignment_confidence`, `analytical_mode`, `lexical_metrics` (JSONB),
  earlier/later word counts, earlier/later `provenance` (JSONB),
  `review_reason`.
- `app.structured_table_comparisons` — one row per (report comparison, table
  family) — genuinely one-to-many: ACT has two in-scope families at once.
  `comparison_backend`, `status`, `table_family_key`, `row_alignments` /
  `column_alignments` / `value_change_events` / `footnotes` (JSONB arrays),
  earlier/later `provenance`, `review_reason`.

JSONB arrays rather than fully normalized child tables: only two table
families are in scope for this milestone, volumes are small, and a fully
normalized row/column/event schema would be sprawl this integration
milestone does not need. `app.current_narrative_unit_comparisons` /
`app.current_structured_table_comparisons` views follow the exact
`_ACTIVE_PUBLICATION_JOIN` pattern every other `current_*` view uses, in
their own `CUTOVER_COMPARISON_CURRENT_VIEWS` tuple (never appended to an
earlier milestone's tuple, per `schema.py`'s documented migration-replay
rule). `app_readonly` was granted `SELECT` on both new views
(`scripts/sql/app_roles.sql`).

**No new API route** — there still isn't one; the facade is a plain
TypeScript module the Server Component calls directly, matching the
existing architecture.

**Response shape**: not a single flat schema (would lose meaning across
three structurally different payloads). `web/lib/services/comparison-facade.ts`:

```ts
export type ComparisonView =
  | { backend: "LEGACY_PASSAGE"; legacy: ComparisonPageViewModel }
  | {
      backend: "CUTOVER";
      narrative: NarrativeUnitComparison | null;
      structured: StructuredTableComparison[];
      legacy: ComparisonPageViewModel;
    };
```

**Deviation from the originally anticipated three-way discriminated union**
(`SEMANTIC_UNIT` / `STRUCTURED_TABLE` / `LEGACY_PASSAGE`, each mutually
exclusive): local end-to-end testing against the real dataset revealed that
narrative and structured coverage are **not mutually exclusive** — ACT is in
scope for both a narrative unit (`cfo_conclusion`) and two structured table
families simultaneously, so a single ACT report comparison legitimately
carries both a narrative row and multiple structured rows at once. An
earlier version of this facade picked exactly one and silently dropped
ACT's structured tables; this was caught before shipping (Section 10) and
fixed by collapsing to a `CUTOVER` backend that carries both payloads
independently (`narrative: T | null`, `structured: T[]`), still with
`legacy` always present as diagnostic/audit context. `legacy` must never be
read as the primary result once `backend !== "LEGACY_PASSAGE"` — enforced
by construction in the facade (the backend decision depends only on whether
a cutover row *exists*, never on that row's `status`), not by page code
remembering to check `status`.

`ComparisonRepository` gained two additive, named methods (no generic query
method, matching the interface's existing documented convention):
`getNarrativeUnitComparison(comparisonId): Promise<NarrativeUnitComparison | null>`
and `getStructuredTableComparisons(comparisonId): Promise<StructuredTableComparison[]>`.

## 5. Frontend / publishing changes

**Frontend**: `web/app/comparisons/[comparisonId]/page.tsx` now calls
`getComparisonView` instead of `getComparisonPageViewModel` directly. The
`LEGACY_PASSAGE` branch renders the exact same JSX as before (byte-identical
output, verified in Section 8). Two new, additive sections render only when
`backend === "CUTOVER"`:

- `components/NarrativeUnitComparisonSection.tsx` — resolved: unit label,
  lexical metrics (TF-IDF cosine, unigram/bigram Jaccard, edit/sequence
  similarity), word counts, alignment status/confidence. Unresolved: neutral
  copy ("Comparison unavailable for this report pair", "Review required",
  etc.) in the existing product voice — the raw status
  (`UNRESOLVED_UPSTREAM` etc.) never appears in user-facing text, only in a
  `data-status` attribute for admin/debug inspection.
- `components/StructuredTableComparisonSection.tsx` — one real `<table>`
  per table family (row alignment, then value-change events, then
  footnotes) — never flattened into prose. Same unresolved-copy convention.

No changes to `web/app/comparisons/[comparisonId]/evidence/page.tsx`,
`passages/**`, or `companies/[ticker]/**` — out of scope; only the
comparison detail page's data source changed.

**Publishing**: new module `src/market_documents/publishing/cutover_publishing.py`
(`build_narrative_comparison_rows`, `build_structured_comparison_rows`),
called from `PublicationBuilder._build_rows()` in a dedicated pass
immediately after `ReportComparison` rows are flushed (not the same flush
window — `NarrativeUnitComparison`/`StructuredTableComparison` have no ORM
`relationship()` back to `ReportComparison`, only a raw FK column, so
inserting both in one unit-of-work flush produced a real FK-violation
insert-ordering bug during local testing, fixed by flushing
`ReportComparison` rows first). Two new `Publication` counters
(`narrative_comparison_count`, `structured_comparison_count`).
No changes to `comparison_routing.py`, `cutover_comparison.py`,
`cutover_config.py`, or any Track 7C.1–7C.6 algorithm.

## 6. Feature-flag behavior

- **OFF** (default, both sides): the web app never even queries the two new
  tables/views for narrative/structured data — `isCutoverEnabled()` short-circuits
  before either repository call. Production behavior is functionally (and
  in local testing, literally byte-)identical to pre-milestone legacy
  behavior.
- **ON**: for a comparison with a persisted narrative and/or structured row,
  `backend` becomes `CUTOVER` and the new section(s) render — resolved or
  explicitly unresolved. For a comparison with no persisted row (out of
  the fixed scope), `backend` stays `LEGACY_PASSAGE` regardless of the flag.
- One flag, one name, shared between the Python publish-time force-enabled
  router and the web app's read-time gate — no second independent flag was
  introduced, per the task's explicit instruction.

## 7. Unresolved-state behavior

Verified end to end (Section 9) that an `UNRESOLVED_UPSTREAM` /
`AMBIGUOUS` / `REVIEW_REQUIRED` cutover row is published and rendered
exactly like a resolved one structurally — `backend` still reports
`CUTOVER`, and the page shows a neutral unresolved state. At no point does
the facade or the page fall back to displaying `legacy` as the primary
result for a unit/table the new pipeline covers. `legacy` remains available
in the `ComparisonView` object as diagnostic/audit context only (not
currently rendered as a labeled "legacy comparison" panel in the UI — the
existing legacy sections on the same page already serve that role for
every field the new pipeline doesn't cover).

## 8. Provenance behavior

`ProvenanceRef` (`report_id`, `directory_year`, `start_page`, `end_page`,
`source_block_ids`, `source_excerpt`) survives Python dataclass -> JSONB ->
Postgres -> Zod-validated TypeScript row -> camelCase domain object
unchanged, for both narrative (`earlierProvenance`/`laterProvenance`) and
structured (same, per table). Verified present and correctly shaped in the
local end-to-end run (Section 9, case 1: `earlierProvenance.startPage ===
10`). The current UI does not yet render page numbers/source excerpts
directly in the new sections (out of scope for this integration milestone,
matching the "minimum UI changes necessary" instruction) — the API-level
object still carries full provenance for later use, satisfying the
fallback requirement ("ensure the API response still carries sufficient
provenance for later use").

## 9. Tests

**Python** (`tests/test_cutover_publishing.py`, new, 6 tests): resolved
narrative row built with correct fields; unresolved narrative row still
built (never dropped); out-of-scope ticker returns no rows; resolved
structured row built with row/column/value-change JSON + footnotes (and
ACT's second, data-less table family still published unresolved);
out-of-scope ticker returns no structured rows; row ids are deterministic
across repeated calls (idempotent-republish contract).

`tests/publishing/test_publishing_lifecycle.py` gained two integration
tests exercising the real `PublicationBuilder.build()` against a live test
database: an in-scope BEL pair produces exactly one `RESOLVED` narrative
row and zero structured rows; an ACT pair with no upstream Track 7C data
produces one narrative row and two structured rows, all `UNRESOLVED_UPSTREAM`
— demonstrating the "never silently omit" guarantee at the publishing layer.

**Web**: `tests/repository/cutover-comparison-repository.test.ts` (6 tests,
real seeded test database) — resolved narrative/structured reads, `null`/`[]`
for an out-of-scope comparison, both ACT table families returned together
(one resolved, one unresolved), plus the same static source-shape
assertions (`app.current_*` only, parameterized `$1`) the existing
comparison-repository test file uses. `tests/unit/comparison-facade.test.ts`
(7 tests, fake repository) — flag off, flag on with no row, resolved
narrative, unresolved narrative (no legacy substitution), structured-only,
**both narrative and structured simultaneously** (the ACT case that caught
the discriminated-union bug), and unknown comparison id. Existing
`comparison-service.test.ts`/`comparison-evidence-service.test.ts` fake
repositories extended with the two new no-op stub methods; no existing
assertions changed.

## 10. Local end-to-end results

Run against the real local dev database (`market-documents units
cutover-check` confirmed real 7C data beforehand: BEL `gross_margin` 2/6
pairs resolve, ACT `cfo_conclusion` 0/9 resolve, ACT
`ned_remuneration_policy_table` 4/9 resolve, ACT
`total_remuneration_outcomes` 5/9 resolve).

1. Ran `alembic -c alembic_app.ini upgrade head` against the local `app`
   database — `app_0009` applied cleanly. Re-ran `market-documents publish
   app-init-roles` so `app_readonly` could select the two new views.
2. `market-documents publish build --publication-version 2026-09-16-cutover-test.1`
   → `status=READY`. Verified directly in Postgres:
   `narrative_comparison_count=15`, `structured_comparison_count=18`,
   matching the preflight check's resolved/unresolved counts exactly.
   `market-documents publish promote` activated it.
3. `pnpm dev`, flag OFF: comparison pages for both an in-scope (BEL) and
   out-of-scope (KP2) id returned HTTP 200 with **zero** occurrences of the
   new section headings — confirmed byte-identical-to-legacy behavior.
4. Flag ON, five cases:
   - **BEL 2018→2019 gross_margin**: `backend=CUTOVER`, narrative
     `status=RESOLVED`, `tfidf_cosine=0.747`, word counts 64→47 shown.
   - **BEL 2019→2020 gross_margin**: `backend=CUTOVER`, narrative
     `status=UNRESOLVED_UPSTREAM`, page shows "Comparison unavailable for
     this report pair" — no legacy substitution, raw status only in
     `data-status`.
   - **ACT 2019→2020, `total_remuneration_outcomes`**: `backend=CUTOVER`,
     structured table rendered with real row alignments (e.g. "a
     banderker" matched HIGH confidence) and value-change events (e.g.
     Base Pay +316.2%) — **and**, on the same page, the narrative section
     for `cfo_conclusion` (unresolved) and the second structured family
     `ned_remuneration_policy_table` (unresolved) all rendered together.
     This is the case that caught and fixed the discriminated-union bug in
     Section 4.
   - **A different ticker (KP2)**: `backend=LEGACY_PASSAGE`, no new
     sections — confirmed with the flag ON.
   - (See Section 14 for why a fifth, distinct "unsupported BEL/ACT
     section" case does not exist as its own comparison id at this
     application's actual per-report-pair page granularity, and how that
     requirement is satisfied structurally instead.)
5. Flag flipped back to OFF, dev server restarted (no DB change): all
   three previously-`CUTOVER` comparison ids re-rendered with zero
   occurrences of the new section headings — rollback confirmed (Section
   12).

## 11. Staging/preview results

**Not executed in this session.** This repo's Vercel Preview environment
(`web/.env.preview.local`) exists and has been used for a prior
milestone's Preview-only deploy (7B.3 Q&A), but triggering a real deploy is
an external, shared-environment action — per this task's own §16 ("do not
enable production automatically... normally requires user approval") and
this repo's established practice, a real Preview deploy is deferred to an
explicit follow-up authorized by you. Section 13 below is the exact
procedure to run it.

## 12. Rollback verification

Verified locally (Section 10, step 5): flag ON → `CUTOVER` behavior for
BEL/ACT comparisons; flag OFF (env var change + process restart only, **no
database rollback, no data deletion, no republish**) → all three
previously-`CUTOVER` comparisons revert to `LEGACY_PASSAGE` rendering. This
matches the task's required rollback contract exactly, and is a direct
consequence of the Section 3 design decision to keep the flag a read-time
concern.

## 13. Production/staging enable procedure (prepared, not executed)

**Staging/Preview:**
1. Ensure the target app database has `app_0009` applied and
   `app_readonly` granted on the two new views (`market-documents publish
   app-init-roles` against that database).
2. Run/confirm a `publish build → validate → promote` cycle against that
   database has produced an ACTIVE publication with non-null
   `narrative_comparison_count`/`structured_comparison_count`.
3. Deploy the web app to Preview with `SEMANTIC_COMPARISON_CUTOVER_ENABLED`
   unset/`false` first. Verify deployment succeeds and spot-check a BEL/ACT
   comparison page renders unchanged.
4. Set `SEMANTIC_COMPARISON_CUTOVER_ENABLED=true` on the Preview
   environment (Vercel env var), redeploy/restart. Re-run the five cases
   from Section 10 against the Preview URL; capture actual responses.
5. Set it back to `false` to confirm rollback in that environment too.

**Production (only after Preview passes, and only with your explicit
go-ahead):**
1. Confirm the production app database is on `app_0009` with the grant
   applied, and the active production publication was built after this
   milestone's publisher change (so it actually has cutover rows).
2. Set `SEMANTIC_COMPARISON_CUTOVER_ENABLED=true` in the production Vercel
   environment.
3. If this repo's Vercel project redeploys on env var change, that
   redeploy is itself the "deploy" step; otherwise trigger one.
4. Smoke-check: load one known-in-scope comparison (BEL gross_margin) and
   confirm `CUTOVER` rendering; load one known out-of-scope comparison and
   confirm unchanged legacy rendering.
5. Monitor logs (Section 15) for `CUTOVER`/`LEGACY_PASSAGE` and
   resolved/unresolved counts over the first requests.
6. Rollback if needed: set the flag back to `false`, redeploy/restart. No
   database action required.

## 14. Unsupported scope

Scope is exactly the four entries in `cutover_config.py`: BEL
`gross_margin`, ACT `cfo_conclusion` (both `FINANCIAL_PERFORMANCE`), ACT
`ned_remuneration_policy_table`, ACT `total_remuneration_outcomes`. Nothing
was added to this scope, and no new company/schedule/unit/table family was
introduced, per the task's hard-stop instruction.

One structural note discovered during integration: the application's real
page granularity is **one comparison id per report pair** (the whole
document), not per-schedule/unit. Because BEL and ACT each have every one
of their report pairs attempted against their one/two in-scope entries
(every BEL comparison gets a `gross_margin` attempt; every ACT comparison
gets a `cfo_conclusion` attempt and both structured-table attempts), there
is no BEL/ACT comparison id that has literally zero cutover coverage — an
"unsupported section within an in-scope company" is therefore demonstrated
structurally rather than as its own distinct comparison id: on every
BEL/ACT comparison page, the new `CUTOVER` section(s) cover only the exact
in-scope unit/table(s), while everything else on that same page (headline
metrics, deterministic findings, other language-metric sections, passage
evidence) continues to render from the unmodified legacy pipeline,
regardless of the flag. A genuinely different ticker (KP2/SBP/SDL/SUR) is
the clean "fully out of scope" case, verified in Section 10.

## 15. Observability

The web app logs nothing new beyond `console.error` on a facade/query
failure (matching the existing `ErrorState` fallback path — unchanged).
`backend` (`LEGACY_PASSAGE`/`CUTOVER`) and, when `CUTOVER`, each payload's
`status` are ordinary fields on the returned `ComparisonView`/domain
objects — available to add to structured request logs if/when this
application adopts them, without any additional plumbing. On the
publishing side, `Publication.narrative_comparison_count`/
`structured_comparison_count` are persisted per publish and visible via
`market-documents publish show`, giving an audit trail of how much cutover
coverage each publication actually produced. Nothing here logs full source
document text — only counts, statuses, and the same short
`source_excerpt` (already length-capped in `cutover_comparison.py`) that
was already part of the 7C.6 response shape.

## 16. Remaining caveats

- Staging/Preview and production have **not** been touched (Section 11).
- The new sections do not yet render provenance (page numbers/excerpts) in
  the UI, though the API-level data carries it (Section 8) — deferred as
  out of the "minimum UI changes necessary" scope.
- `legacy` is carried in `ComparisonView` for diagnostic purposes but is
  not currently exposed as a labeled "legacy comparison" toggle/panel in
  the UI when `backend === "CUTOVER"` — only the always-present, unmodified
  legacy sections elsewhere on the same page serve that role today.
- This work does not address any recall/coverage gap in the underlying
  Track 7C.1–7C.5 pipelines (e.g. ACT `cfo_conclusion` resolving 0/9 pairs
  locally) — per the task's explicit instruction, that is a separate,
  out-of-scope concern to document elsewhere, not fix here.

## 17. Final verdict

**PASS — READY TO ENABLE SCOPED CUTOVER IN PRODUCTION** (pending the
Preview verification pass in Section 13, which has not yet been run).

**PRODUCTION CUTOVER NOT ENABLED.**
