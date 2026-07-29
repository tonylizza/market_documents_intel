# Milestone 7A.2/7A.3: Next.js Frontend

## Local setup

```bash
cd web
pnpm install
cp .env.example .env.local   # fill in APP_READONLY_DATABASE_URL
pnpm dev
```

Requires the application schema (Milestone 7A.1) already migrated and
activated, and the `app_readonly` role provisioned (`scripts/sql/app_roles.sql`
from the repo root, or `market-documents publish app-init-roles`), **plus**
the Milestone 7A.2 grant addition described below.

## Package manager

**pnpm** — no other JavaScript package manager or lockfile existed in the
repository before this milestone. Only `pnpm-lock.yaml` is committed.

## Required environment variables

| Variable | Purpose |
|---|---|
| `APP_READONLY_DATABASE_URL` | Server-only. The `app_readonly` role's connection string. Never `DATABASE_URL`/`APP_DATABASE_URL`/publisher credentials. Never read from a Client Component. |
| `TEST_APP_READONLY_DATABASE_URL` | Used only by the Vitest repository test suite, against a dedicated application test database (`market_documents_app_test`), never the research DB. |

`POSTGRES_PORT` is also honored (defaults to `5434`, this repo's local
Postgres port) so tests can never silently connect to an unrelated project's
Postgres on port 5433.

## Pre-existing gap found and fixed: `app_readonly` grant on metric tables

`app.metric_definitions`/`app.metric_label_thresholds` had **no** grant to
`app_readonly` at all after Milestone 7A.1 (confirmed: `permission denied for
table metric_definitions`). This is not a schema/Alembic issue — no table,
column, or view changed. `scripts/sql/app_roles.sql` (already a non-Alembic,
re-runnable role-management script by design) now also grants `SELECT` on
those two tables. Re-run `market-documents publish app-init-roles` (or
`psql "$APP_DATABASE_URL" -f scripts/sql/app_roles.sql` with the usual
`-v publisher_pw=... -v readonly_pw=...`) to apply it to an existing database.

Both tables remain **publication-scoped** (no `current_*` view wraps them).
`PostgresMethodologyRepository` resolves the active `publication_id` first
(`SELECT publication_id FROM app.current_companies LIMIT 1`) and filters
explicitly — it never scans them unfiltered, which would mix in stale/
historical publications' metric catalogs.

## Development command

```bash
pnpm dev          # next dev, Turbopack, http://localhost:3000
```

## Test commands

```bash
pnpm test         # vitest run -- unit, repository, and component tests
pnpm test:watch   # vitest (watch mode)
pnpm test:seed    # (re)seed the frontend test application database
pnpm typecheck    # tsc --noEmit
pnpm lint         # eslint
```

Repository tests require the frontend test application database to exist
and be migrated to head (it's the same `migrations_app` Alembic environment
from Milestone 7A.1 — `alembic -c alembic_app.ini upgrade head` against
`market_documents_app_test`) and the `app_readonly`/`app_publisher` roles
provisioned on it. `pnpm test` runs `seedAppDatabase()` automatically via
each repository test file's `beforeAll` — no manual seeding step required
once the database and roles exist.

## Production build / local production start

```bash
pnpm build        # next build (Node runtime, Turbopack)
pnpm start        # next start
```

Both were verified against the real local `market_documents_app` database
via the `app_readonly` role during this milestone's implementation (see
final report for counts/timings).

## Vercel deployment notes

- Set `APP_READONLY_DATABASE_URL` as a server-only (never `NEXT_PUBLIC_*`)
  environment variable in the Vercel project.
- No Vercel-specific configuration exists in this codebase (no `vercel.json`,
  no Vercel KV/Blob/Edge Config, no edge middleware).
- Database access uses the ordinary Node runtime everywhere (no route or
  layout in this app sets `export const runtime = "edge"`), since `pg`
  requires a real TCP socket, not available on edge runtimes.

## Portable Node deployment notes

The app runs identically outside Vercel:

```bash
pnpm build
pnpm start   # or: node .next/standalone/server.js if `output: "standalone"` is enabled later
```

Any conventional Node 20+ container/host works — `pg` connects with an
ordinary `postgresql://` URL to any conventional Postgres (local, Neon,
Supabase, RDS, etc.), with SSL controlled by the URL's own `sslmode` query
parameter (`lib/db/pool.ts` maps `sslmode=require`/`no-verify` to
`{rejectUnauthorized: false}`, `verify-full`/`verify-ca` to strict
verification, and no `sslmode` to no SSL at all — matching local Postgres).

## Caching behavior

`export const revalidate = 60` on `/` and `/methodology` (time-based
revalidation, Next.js's standard, non-platform-specific ISR mechanism — no
Vercel-only cache tags or KV). This means:

- A newly activated publication appears within 60 seconds without a
  redeploy.
- The database is not queried on every single request under normal traffic
  (a public, low-traffic research site) — Next.js serves the prerendered/
  revalidated HTML in between.
- `/companies/[ticker]`, `/comparisons/[comparisonId]`, and `/discover` all
  also set `export const revalidate = 60` (dynamic routes, rendered on
  first request then cached per distinct ticker/comparison id/query-string
  combination).

## Database-access architecture

```
React page/component (Server Component)
  -> lib/services/*        (view-model assembly, e.g. grouping discovery items into sections)
  -> lib/repositories/*-repository.ts   (interfaces)
  -> lib/repositories/postgres-*-repository.ts  (parameterized SQL against app.current_* views)
  -> lib/db/pool.ts         (single shared pg.Pool, max 5 connections, 10s statement_timeout)
  -> app.current_* views / app.metric_definitions,app.metric_label_thresholds (publication_id-filtered)
```

- `lib/db/pool.ts`, `lib/db/config.ts` are marked with the `server-only`
  package -- importing them from a Client Component fails the build.
  `tests/unit/no-client-db-imports.test.ts` additionally statically scans
  every `"use client"` file to confirm none imports `@/lib/db`.
- Rows are validated with Zod (`lib/schemas/*.ts`) before being mapped into
  typed domain view models (`lib/domain/*.ts`) -- a malformed row throws a
  `MalformedRowError` server-side rather than reaching a component with an
  unexpected shape.
- No generic/arbitrary-query repository method exists. Every method is
  named and purpose-built: `listCompanies`, `getCompanyCardSummaries`,
  `getLatestComparisonSummaries`, `getMetricDefinitions`,
  `getMethodologyContentData`, `getApplicationDataSummary`.

## Repository/service pattern

- **Repository interfaces** (`company-repository.ts`,
  `methodology-repository.ts`) define the contract; **Postgres
  implementations** (`postgres-company-repository.ts`,
  `postgres-methodology-repository.ts`) are the only files that contain SQL.
- **Services** (`company-service.ts`, `methodology-service.ts`) orchestrate
  repository calls and apply presentation-shaping rules that are not SQL
  concerns -- e.g. `buildLatestSignalSections` groups discovery items into
  titled sections and *omits* any section with zero qualifying items,
  rather than rendering an empty ranking.
- Pages construct a `Postgres*Repository` and pass it to the corresponding
  service function -- straightforward dependency injection that lets unit
  tests substitute an in-memory fake repository (see
  `tests/unit/company-service.test.ts`) without touching Postgres at all.

## Quality-label semantics

Three independent quality dimensions, each with its own vocabulary
(persisted directly on `app.report_comparisons` by the Python publisher --
the frontend never recomputes text labels, only visual styling):

| Dimension | GOOD | USABLE | NEEDS_REVIEW | FAILED |
|---|---|---|---|---|
| Report-side | Analysis ready | Ready with caution | Review recommended | Unavailable |
| Alignment-change | Strong attribution | Usable attribution | Attribution uncertain | Attribution unavailable |
| Disclosure-change | Analysis ready | Ready with caution | Review recommended | Unavailable |

`QualityBadge` requires an explicit `dimension` prop and never collapses
these into one lookup. `lib/formatting/labels.ts` keeps a matching,
dimension-keyed fallback vocabulary used only when a row's own
`*_quality_label` is missing but its raw tier is present.

### Disclosure-change review-qualified display (current corpus)

All 25 current comparisons have `disclosure_change_quality = NEEDS_REVIEW`
(`disclosure_change_primary_eligible = false`) -- an upstream Milestone 3/6
characteristic, not a frontend defect (see the Milestone 7A.1 follow-up).
The frontend:

- Always displays `disclosure_change_score`/`disclosure_change_label` when
  published, **regardless** of primary eligibility.
- Always displays `disclosure_change_quality_label` alongside the magnitude
  -- never one without the other (`DisclosureChangeSummary`).
- Never implies primary eligibility: no ranking, badge, or copy claims a
  review-qualified value is a confirmed headline finding.
- Never renders a `largest_overall_change`/`largest_new_disclosure_share`
  discovery ranking -- both are correctly absent from the underlying data
  while review-qualified, and the frontend does not synthesize a
  replacement ranking.
- A `Tooltip` next to "Overall disclosure change" explains the magnitude is
  corpus-relative and review-qualified.

## Accessibility

- Skip-to-content link (`AppShell`), semantic landmarks (`<header>`,
  `<nav aria-label="Primary">`, `<main id="main-content">`, `<footer>`).
- Every quality/status indicator renders **text**, not color alone
  (`QualityBadge` always renders a label string; `role="status"` +
  `aria-label` combine dimension + label for assistive technology).
- `Tooltip` opens on focus as well as hover, is dismissible with Escape, and
  its content is always linked via `aria-describedby` regardless of visual
  open state -- never hover-only.
- Visible focus rings everywhere (`:focus-visible` in `styles/base.css`),
  never suppressed.
- `prefers-reduced-motion: reduce` disables the loading-skeleton shimmer and
  all transitions.
- Mobile navigation is a real, keyboard-operable disclosure (`aria-expanded`
  button), not a hover-only menu.
- Meaningful, per-route page titles via the App Router `metadata` API.

## Security headers

Set in `next.config.ts` for every route: `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`,
a same-origin `Content-Security-Policy` (no third-party scripts/fonts/CDNs
anywhere in this app), and a restrictive `Permissions-Policy`. Verified live
against `next start` (see final report).

## Milestone 7A.3: company history, comparison detail, discovery

Adds three real routes on top of 7A.2's foundation, replacing the
`/companies/[ticker]` placeholder shell.

### Routes

| Route | Purpose |
|---|---|
| `/companies/[ticker]?comparison=<id>&metric=<key>` | Company header, full-history chart (bounded metric selector), adaptive comparison navigator, compact preview of the selected comparison. |
| `/comparisons/[comparisonId]` | Primary analytical page: quality summary (3 dimensions), 6 headline metric cards, up to 3 deterministic findings, report-side and alignment-change language tables/charts, passage-composition summary, collapsed technical details. |
| `/discover?type=<type>&scope=<scope>&company=<ticker>&minQuality=<tier>&periodStart=<date>&periodEnd=<date>` | Corpus-wide, category-specific discovery rankings. |

### Data-access additions

Two new purposeful queries on `CompanyRepository` (`getCompanyByTicker`,
`getCompanyHistory`) and a new `ComparisonRepository`/`DiscoveryRepository`
pair -- see `lib/repositories/*-repository.ts` for interfaces and
`lib/repositories/postgres-*-repository.ts` for the parameterized SQL.
Deliberately *not* separate repository methods: headline metrics,
deterministic findings, and technical details are all pure functions over
an already-fetched comparison row (`lib/services/headline-metrics.ts`,
`lib/content/finding-copy.ts`, `comparison-service.ts::buildTechnicalDetails`)
-- re-querying for each would be N+1 for no reason, since every field they
need is already present on the one `app.current_report_comparisons` row.

Per-route query counts (verified against the real local `market_documents_app`
database, `psql`/repository-test-confirmed):

- `/companies/[ticker]`: 2 queries (`getCompanyByTicker` + one
  `getCompanyHistory` comparison list, `ORDER BY chronological_index`,
  never one query per comparison card).
- `/comparisons/[comparisonId]`: 3 queries, run as `Promise.all` after the
  first (`getComparisonById` + `getComparisonLanguageMetrics` +
  `getComparisonPassageComposition`).
- `/discover`: up to 3 queries (`listAvailableDiscoveryTypes`,
  `getDiscoveryItems`, plus `CompanyRepository.listCompanies`/
  `getApplicationDataSummary` reused for filter options -- never a
  duplicate query for data already available elsewhere).

Passage composition is read directly from
`app.current_passage_comparisons.alignment_status` (`GROUP BY`), which
includes a real, directly queryable `UNCHANGED` value -- confirmed via the
Python publisher source and live data (3,266 `UNCHANGED` rows in the
current corpus). No derivation/arithmetic against `report_comparisons`'
summary count columns was needed or used.

### Finding-key vocabulary

`finding_key` and `discovery_type` share one 8-value vocabulary (see
`market_documents.publishing.findings.CANDIDATE_KEY_ORDER`).
`lib/config/discovery.ts` (`DISCOVERY_TYPES`) and
`lib/content/finding-copy.ts` (`FINDING_COPY`, exhaustive, with a safe
fallback for an unrecognized key) are both built against the full 8, even
though only 6 are populated in the current corpus (the two
feature-quality-gated types are empty while `disclosure_change_quality` is
`NEEDS_REVIEW` corpus-wide). `finding_payload` is `{ "<key>": {value,
magnitude}, ..., "_disclosure_change_diagnostics": {...} }` --
`extractFindingPayloadEntry` validates and extracts one key's entry; the
raw JSONB is never passed into a component.

### Adaptive comparison navigator

`components/AdaptiveComparisonNavigator.tsx` implements three modes, chosen
purely by comparison count (`lib/config/comparison.ts::selectNavigatorMode`,
never viewport width):

- **Compact** (≤10 comparisons): all cards in a wrapping grid.
- **Scrollable** (11–20): horizontal `overflow-x` strip with scroll-snap,
  prev/next buttons, `Home`/`End` keyboard support, an `IntersectionObserver`-
  driven "Showing X–Y of N" range indicator, and the selected card
  auto-scrolled into view.
- **Range-filtered** (>20): a "Latest 10 / All N" toggle, an explicit range
  summary, shortcut links (latest / historical peak / largest eligible
  uncertainty increase / largest eligible risk introduction --
  `getCompanyHistoricalHighlights`, `null` when no comparison qualifies),
  and the filtered card list. The full-history chart above the navigator
  (section B) remains visible in every mode, including range-filtered.

Tested with synthetic histories at 0, 1, 5, 10, 11, 20, 21, and 35
comparisons (`tests/component/adaptive-comparison-navigator.test.tsx`,
`tests/fixtures/comparison-fixtures.ts::makeComparisonHistory`).

### Charting

**Recharts** (new dependency; none existed before 7A.3) -- smallest
practical React-native charting library with built-in `ResponsiveContainer`,
keyboard-accessible tooltips via a controlled `<Tooltip content={...}>`, and
no dependency on a platform-specific rendering service. Chart animations are
disabled (`isAnimationActive={false}`) everywhere, which both satisfies
"avoid excessive animation"/reduced-motion and avoids animation-timing
flakiness in tests.

Chart color: the app's existing `--chart-1..6` brand tokens were run
through the dataviz skill's `validate_palette.js` categorical-palette
validator and **failed** (lightness band, chroma floor, and normal-vision
floor all failed -- navy/teal read too close together for 6-way identity
encoding). `styles/tokens.css` now also defines `--viz-cat-1..6`, the
validated default categorical palette (6 of its 8 slots), used for the
6-status passage-composition chart (fixed category→slot order, never
reassigned by value/rank) and as the single series color for single-series
charts (full-history line, language-metric bars). The brand `--chart-*`
tokens are kept only as a historical/UI-accent reference, documented as
failing that validation.

Every chart has a **table alternative reading the exact same data** (never
a second, drifting copy), a visually-hidden accessible summary paragraph,
and explicit empty/one-point/null-value handling
(`tests/component/full-history-chart.test.tsx`).

Directional/value-judgment color rule: the language-metrics chart encodes
increase/decrease by **bar position** (left/right of a zero reference
line), not by red/green color -- satisfies "do not automatically style all
increases as bad or all decreases as good" without needing a second
palette.

### Quality/discovery semantics (7A.3 additions)

- Headline metrics: `HeadlineMetric.reviewQualifiedExploratory` is derived
  from `primaryEligible` (never a hardcoded "always true" for the current
  corpus), so a future publication with a primary-eligible
  `disclosure_change_score` renders correctly without a code change.
- Discovery minimum-quality filter: type-specific, resolved against the
  *selected ranking's own* quality dimension
  (`DISCOVERY_TYPE_CONFIG[type].qualityDimension`) via a reverse
  label→tier lookup (`rawQualityFromLabel`) -- never a generic
  cross-dimension quality scale. An unresolvable label is excluded, not
  assumed to pass.
- `listAvailableDiscoveryTypes()` derives the tab set from actual
  `app.current_discovery_items` rows -- confirmed live: 6 of 8 types
  populated, `largest_overall_change`/`largest_new_disclosure_share`
  absent (49 total discovery items, matching the milestone's expected
  corpus state exactly).
- Discovery results are never re-sorted client-side; row order is exactly
  the repository's `ORDER BY rank` (the database's deterministic tie-break).

### URL state

`/companies/[ticker]?comparison=<uuid>&metric=<key>` and
`/discover?type=&scope=&company=&minQuality=&periodStart=&periodEnd=` are
both fully shareable/back-button-friendly. Every parameter is validated
against a bounded allowlist before use
(`resolveComparisonMetricKey`, `resolveSelectedComparison`,
`resolveSelectedDiscoveryType`, `resolveRankScope`, `resolveMinQualityParam`,
`resolvePeriodDateParam`) -- an invalid/unknown value falls back safely
(latest comparison, default metric, first available discovery type, no
filter) and never throws or crashes the page.

## Known limitations

- `app.current_report_comparisons` (and every other `current_*` view)
  exposes no `publication_version`/`activated_at` -- both live only in
  `app_internal.publications`, unreachable by `app_readonly`. The
  Methodology/home pages use a static "Data reflects the currently active
  publication" note instead. Exposing real publication metadata safely
  would need a new, deliberately narrow view or column grant -- flagged as
  a candidate for a future milestone's schema change, not implemented here
  per this milestone's "no schema migration without approval" constraint.
- No live browser/visual screenshot verification was performed (no browser
  automation tool was available in this environment); verification instead
  used `next build`/`next start` + `curl` against the real local
  application database, plus 317 automated unit/repository/component/page
  tests. Responsive behavior (640px breakpoints) was verified at the CSS
  level, not via a rendered screenshot at multiple viewport widths.
- Playwright/end-to-end tests were not added (marked optional in the brief)
  given the scope already covered by component- and page-level tests
  against real rendered output.
- `notFound()` (invalid ticker/comparison id) renders the correct
  not-found UI and `NEXT_HTTP_ERROR_FALLBACK;404` digest (verified via
  `curl`, response body inspection), but the *raw* initial HTTP status code
  observed via `curl` is `200`, not `404` -- a pre-existing characteristic
  of this app's root-level `app/loading.tsx` Suspense boundary streaming
  the initial shell before the nested `notFound()` resolves, not a defect
  introduced in 7A.3 (the 7A.2 placeholder page had the same call pattern
  and boundary). Worth a follow-up if strict-404-status crawlers/monitoring
  matter for this app; not addressed here since fixing it would mean
  removing or restructuring the shared root Suspense boundary used by every
  route.
- Range-filtered mode's "visible range" indicator in scrollable mode is
  `IntersectionObserver`-driven and reflects real DOM intersection; the
  range-filtered mode's "Latest N / All" toggle is local component state,
  not URL-persisted (only `comparison=`/`metric=` are, per the milestone's
  URL-state requirement).

## Milestone 7A.4: passage search, evidence exploration, and the 404 fix

Adds three real routes on top of 7A.3's foundation and fixes a pre-existing
HTTP-status defect.

### Routes

| Route | Purpose |
|---|---|
| `/passages?q=&phrase=&company=&periodStart=&periodEnd=&comparison=&side=&status=&confidence=&type=&category=&subcategory=&rsQuality=&acQuality=&primary=&feature=&irregularGap=&collision=&splitMerge=&sort=&page=&pageSize=` | Corpus-wide lexical passage search + structured filters, server-side paginated. |
| `/comparisons/[comparisonId]/evidence?status=&confidence=&category=&subcategory=&collision=&splitMerge=&heading=&pageStart=&pageEnd=&page=&pageSize=` | Comparison-specific, status-tabbed, filtered, paginated passage evidence. |
| `/passages/[passageComparisonId]` | Full evidence detail for one passage comparison -- side-by-side text, word-level diff, language signals. |

### The 404 fix

Root cause (already diagnosed as a known limitation in 7A.3): a blanket
`app/loading.tsx` sat above every route, so Next.js had to flush the
Suspense fallback shell (HTTP 200) before a nested `notFound()` could
resolve, regardless of which page eventually called it. The App Router
applies a segment's `loading.tsx` to that segment **and everything nested
under it** -- there is no way to keep a route's own loading state while
excluding a not-found-capable descendant from the same boundary.

Fix (smallest correct change, not a full restructure):

- Deleted the root `app/loading.tsx`.
- `app/(home)/page.tsx` (moved from `app/page.tsx` into a route group --
  same URL, `/`) and `app/(home)/loading.tsx` give the home page back its
  own scoped loading state without that boundary reaching any dynamic
  route.
- `app/discover/loading.tsx` and `app/methodology/loading.tsx` are new,
  scoped loading states -- neither route has a nested dynamic child, so a
  loading boundary there is safe.
- `app/companies/[ticker]/`, `app/comparisons/[comparisonId]/`,
  `app/comparisons/[comparisonId]/evidence/`, and
  `app/passages/[passageComparisonId]/` deliberately have **no**
  `loading.tsx` anywhere in their ancestor chain, so `notFound()`/normal
  resolution happens before any byte is flushed and the real HTTP status
  is correct.
- `app/passages/page.tsx` (the search page) does **not** have its own
  `loading.tsx` either -- a `loading.tsx` at `app/passages/` would also
  wrap the nested `app/passages/[passageComparisonId]/` segment (same
  cascading-boundary rule), which would silently reintroduce the bug one
  level down. This was caught by the new production-status test suite
  itself (see below) on the first run, before the fix.

Verified with real `next build` + `next start` + real HTTP requests (never
just checking for the not-found digest in a 200 body) -- see
`tests/production/http-status.test.ts` and `pnpm test:production`.

### Full-text search design

`app.current_passages.search_vector` is a Postgres generated column:
`setweight(to_tsvector('english', heading), 'A') || setweight(to_tsvector('english', text), 'B')`,
GIN-indexed (`ix_app_passages_search_vector`). Confirmed via `EXPLAIN
ANALYZE` that the GIN index is actually used (`Bitmap Index Scan on
ix_app_passages_search_vector`), not a sequential scan.

- Query parsing: `websearch_to_tsquery('english', $1)` -- forgiving of
  malformed/adversarial input (never throws, unlike `to_tsquery`), which is
  exactly why it was chosen over building a custom parser. Exact-phrase
  mode simply wraps the (quote-stripped) query in a single quoted phrase
  before passing it to the same function -- `websearch_to_tsquery` already
  treats a quoted substring as a phrase search, so no second `tsquery`
  function/code path was needed.
- Ranking: `ts_rank(search_vector, tsquery)`, which naturally favors
  heading (weight A) matches over body (weight B) matches. Sort keys are a
  fixed, bounded map (`PASSAGE_SORT_SQL`) from a 5-value enum
  (`relevance`, `newest_report`, `oldest_report`, `company`, `page_order`)
  to a literal `ORDER BY` fragment -- never a user-supplied order-by
  string. Every sort key ends with the same deterministic tie-break
  (company, report period, passage index, passage id).
- Safe excerpts/highlighting are built in TypeScript
  (`lib/services/passage-highlight.ts`), not `ts_headline` -- the milestone
  brief's own suggested fallback when `ts_headline` would need unsafe HTML
  handling. Highlight spans (`{text, matched}`) are rendered via
  `<HighlightedText>` as real `<mark>`/`<span>` elements, never
  `dangerouslySetInnerHTML`. Term matching uses `\b` word-boundary regexes
  (case-insensitive) so `cash` never matches inside `cashier`.
- A completely empty search (no query, no filter) never queries the
  corpus: `hasSearchableInput()` gates the query in both the page and the
  service layer, showing an orientation empty-state instead. When a search
  *is* active, three queries run in parallel (`searchPassages`,
  `countPassageSearchResults`, `getPassageFilterOptions`).
- Count is capped (`MAX_COUNTED_PASSAGE_RESULTS = 1000`): the count query
  wraps its `WHERE`-filtered rows in `SELECT ... LIMIT 1001`, so a very
  broad query never pays for an expensive exact count beyond that -- the
  UI shows "the first 1,000+ results" instead of an exact number past the
  cap. Pagination itself is always `LIMIT`/`OFFSET` in SQL, never a
  client-side slice.

### Search-result grain: a passage can produce zero, one, or two rows

A real, load-bearing discovery from inspecting the actual corpus: **most**
aligned passages (14,752 of 22,148 in the live corpus) participate in
*two* `passage_comparisons` rows -- once as the `LATER` side of the
comparison with the company's prior report, and again as the `EARLIER`
side of the comparison with its next report. `primary_alignment` is `true`
on every row in the live data, so it cannot be used to pick a single
canonical alignment per passage.

Given that, `searchPassages` is deliberately built as `app.current_passages
p LEFT JOIN app.current_passage_comparisons pc ON pc.earlier_passage_id =
p.id OR pc.later_passage_id = p.id`: a passage with two alignments
legitimately produces two distinct result rows (different comparison
periods, possibly different alignment status/confidence -- each is
genuine, separate evidence), a passage with one alignment produces one
row, and a passage with zero alignments (21 in the live corpus) produces
one "report-only" row with every alignment-scoped field `null`. `report
side` is computed per-row via a `CASE` expression comparing `pc
.earlier_passage_id`/`later_passage_id` to `p.id` -- it is not a stored,
single-valued column on the passage.

### Filter vocabulary (real, inspected values)

Every filter enum was pulled from the live `market_documents_app`
database, not invented: 6 alignment statuses, 3 alignment types, 4
confidence tiers, 5 passage types, 2 report sides, 9 non-null
structured-content categories (plus null = ordinary narrative, the
overwhelming majority), and the financial-language taxonomy (7 core
LM-style categories with no subcategory --
constraining/litigious/negative/positive/strong_modal/uncertainty/weak_modal
-- plus `financial_condition`/`governance`/`risk`/`strategy`, each with
real subcategories, 48 category/subcategory pairs total). Raw values are
preserved internally; `lib/config/passage-vocabulary.ts` is the only place
that maps them to display labels (`SUBSTANTIALLY_MODIFIED` never reaches
rendered text).

The "financial-language category" filter is corpus-wide (any category);
"subcategory" narrows within the selected category (financial_condition,
governance, risk, and strategy all have real subcategories -- not risk
alone, despite the milestone brief using risk subcategories as its
running example). Both are implemented as a single `EXISTS` against
`app.current_passage_language_signals` scoped to the row's own
`passage_comparison_id`, requiring `raw_count > 0` (a signal row exists
for essentially every passage/side/core-category combination regardless
of count -- `raw_count > 0` is what "actually present" means).

"Report side" (`EARLIER`/`LATER`), "irregular-gap comparison", "report-side
quality", and "alignment-change quality" are all resolved via plain joins
to the already-joined `pc`/`rc` rows -- no `EXISTS` subqueries were needed
once the per-row alignment grain above was settled.

### Comparison evidence page

`getComparisonEvidenceSummary` deliberately adds **no new SQL** --
it composes two existing `ComparisonRepository` queries
(`getComparisonById` + `getComparisonPassageComposition`, both from
7A.3), the same "derive, don't re-query" rule `comparison-service.ts`
already used for headline metrics. The filtered/paginated evidence rows
(`getComparisonEvidence`/`countComparisonEvidence`) and passage-comparison
detail (`getPassageComparisonById`) share one SQL column list/join
(`passage-mapper.ts`'s `PASSAGE_COMPARISON_DETAIL_ROW_COLUMNS_SQL`/
`_JOIN_SQL`) so the two routes can never drift on which fields are
available. The status tabs are real server-rendered links (not an ARIA
`tab`/`tabpanel` pair with client-side roving tabindex) -- each is a full
navigation to a new, shareable URL with `status=` set and `page` reset to
`1`, which keeps ordinary `Tab`/`Enter` keyboard navigation and screen
readers working without any custom JS.

### Passage detail page

NEW/REMOVED render only the one real side, clearly labeled "(primary)";
the absent side shows an explicit `EmptyState`, never fabricated text. A
one-sided AMBIGUOUS passage (all AMBIGUOUS rows in the live corpus are
currently one-sided -- 0 two-sided) shows the available side with an
explicit uncertain-attribution note rather than guessing NEW vs. REMOVED.
A matched two-sided passage renders `PassageDiffView`, a client component
with a "Show original text" toggle (`aria-pressed`), defaulting to the
highlighted diff.

The diff (`lib/services/passage-diff.ts`) is a deterministic, word-level
LCS diff over `\S+`/`\s+` tokens (never character-level) computed
entirely in the presentation layer from the two already-published texts
-- it never touches or recomputes `alignmentStatus`/`confidence`/any
analytical field, and no passage text is ever sent to an external
service. Two safety caps, independent of each other: `MAX_DIFF_INPUT_LENGTH`
(20,000 characters per side) and a token-count-product cap
(4,000,000 cells) on the LCS table itself, guarding against a pathological
short-token-heavy input that's under the character cap but would still
blow up the `O(n*m)` table. Either cap falls back to `diffed: false` --
both original texts shown unhighlighted, with a visible explanation, never
a frozen page.

### Passage-level language signals

`getPassageLanguageSignals` is scoped to one `passage_comparison_id`
(indexed: `ix_app_passage_language_signals_passage_comparison_id`) --
never a read across the 269,819-row table. Grouped by report side, then
category/subcategory; a `subcategory === null` row is a real core-category
signal, not a missing value. Rows with `raw_count === 0` are filtered out
client-side before display (most core-category rows are legitimately
zero) rather than fetched selectively, since the per-passage row count is
already small (≤ 48).

### Repository/service additions

- `PassageRepository`/`PostgresPassageRepository`: `searchPassages`,
  `countPassageSearchResults`, `getPassageFilterOptions`,
  `getPassageComparisonById`, `getPassageLanguageSignals`.
- `ComparisonRepository` gained `getComparisonEvidence`,
  `countComparisonEvidence`, `getComparisonEvidenceFilterOptions`.
- Services: `passage-search-service.ts`, `passage-search-params.ts`
  (parse/validate/canonicalize/serialize URL state, never throws on
  garbage input), `comparison-evidence-service.ts`,
  `comparison-evidence-params.ts`, `passage-detail-service.ts`,
  `passage-highlight.ts`, `passage-diff.ts`, `pagination.ts` (shared
  pagination-state builder).
- Every dynamic SQL fragment is built via string concatenation (`+`), not
  a `${}` interpolation inside a `query(\`...\`)` template literal --
  matches the existing `postgres-comparison-repository.ts` convention
  (`"SELECT " + COLUMNS_SQL + \`...\``) and is asserted by a static
  regex check in the repository test suites. Every actual value (query
  text, filter values, ids) is still a `$1`/`$2`/... bind parameter; only
  already-safe, internally-built SQL fragments and bind-parameter index
  numbers are concatenated.

### URL state

Both `/passages` and `/comparisons/[id]/evidence` are fully
shareable/back-button-friendly: every parameter is validated against a
controlled allowlist (`parsePassageSearchParams`/
`parseComparisonEvidenceFilters`), an invalid/unknown value is dropped
rather than crashing the page, duplicate query-string values take the
first entry, and any filter/query/sort change resets `page` to `1`
(`resetPage`/`resetEvidencePage`). `buildPassageSearchQueryString`/
`buildComparisonEvidenceQueryString` omit default values, so a copy-pasted
URL round-trips to an equivalent parsed state.

### Caching

`/passages` sets `export const dynamic = "force-dynamic"` (always
server-rendered, never cached across the effectively unbounded
query/filter combination space). `/comparisons/[id]/evidence` and
`/passages/[passageComparisonId]` have no `revalidate` export (dynamic by
default, since neither reads a bounded/enumerable-caching-friendly key
space the way `/discover` does) -- both are fast (single-digit-to-low-
double-digit-millisecond real queries against the live database, see
Performance below), so per-request rendering is not a measured problem.

### Security

Same posture as 7A.2/7A.3, extended: every new SQL string is parameterized
(verified by static source checks in the repository test suites, plus the
`$1`/no-`${}` convention above); no new client-accessible database code
(`PostgresPassageRepository`/its SQL never imported from a `"use client"`
file, covered by the existing `no-client-db-imports` static test);
`PassageDiffView` is the only new client component with any interactivity
(a toggle button), and it never fetches data itself -- it only renders
props computed server-side. No new CSP exception was needed (no new
third-party script/style/font origin).

### Performance (measured against the real local `market_documents_app` database)

- `/passages?q=<term>`: 3 queries (search + count + filter options, run in
  parallel). Representative searches (liquidity, "going concern" exact
  phrase, governance, uncertainty, debt, impairment, climate,
  remuneration) all returned in 70-115ms end-to-end (`curl -w
  %{time_total}` against a real `next start` production server), including
  the GIN-indexed full-text search itself (confirmed via `EXPLAIN ANALYZE`
  earlier: `Bitmap Index Scan on ix_app_passages_search_vector`, ~44ms
  including planning for "liquidity", 340 index hits before joins).
- `/comparisons/[id]/evidence`: up to 4 queries (summary: 2 existing
  reused queries; evidence: 2 new, comparison-scoped queries), verified
  200 against a real comparison id.
- `/passages/[passageComparisonId]`: 2 queries in parallel
  (`getPassageComparisonById` + `getPassageLanguageSignals`); the diff is
  computed in-process, not a third query.
- No route queries `app.current_passage_language_signals` without a
  `passage_comparison_id`/`report_comparison_id` scope (asserted
  statically in both repository test suites).
- Guardrails in place: `MAX_PASSAGE_QUERY_LENGTH` (200 chars),
  `MAX_PASSAGE_PAGE_SIZE`/evidence page size cap (50), `MAX_EXCERPT_LENGTH`
  (320 chars), `MAX_COUNTED_PASSAGE_RESULTS` (1,000), `MAX_DIFF_INPUT_LENGTH`
  (20,000 chars) + the LCS-table cell cap, and the existing shared pool's
  10s `statement_timeout`.

### Testing

`tests/unit/passage-*`, `comparison-evidence-*` (parsing, canonicalization,
URL round-trip, label mapping, highlighting, diffing, malformed-row
rejection via direct Zod schema tests); `tests/repository/passage-repository
.test.ts` + additions to `tests/repository/comparison-repository.test.ts`
(real queries against the seeded `market_documents_app_test` database,
including static source-shape checks); `tests/component/passage-*`,
`comparison-evidence-*` (rendering, accessibility, empty/error states);
`tests/component/passages-page.test.tsx`,
`comparison-evidence-page.test.tsx`, `passage-detail-page.test.tsx`
(page-level integration tests with a mocked repository, following the
existing `companies-page.test.tsx` pattern); `tests/production/http-status
.test.ts` (real `next build` + `next start`, real HTTP status assertions
-- this is the suite that caught the `/passages/[id]` nested-loading
regression described above).

`pnpm test` runs the full unit/repository/component/page suite (502 tests,
including everything from 7A.1-7A.3) against the seeded test database.
`pnpm test:production` is separate (`vitest.production.config.ts`,
excluded from `pnpm test` via `vitest.config.ts`'s `exclude`) because it
spawns a real production build + server (~15s once built) -- kept out of
the fast default loop.

The test fixture (`tests/fixtures/seed-app-database.ts`) was extended with
real, distinct, searchable passage text (reusing several of this
milestone's representative search terms) and passage-language-signal rows
for ACT's latest seeded comparison, plus one deliberately unaligned
"Directors' report" passage so report-only-result handling has real
fixture data to test against.

### Deployment checklist (Milestone 7A.4 additions)

- [ ] `alembic -c alembic_app.ini upgrade head` on the target database (no
      schema change was introduced this milestone -- this just confirms
      the existing 7A.1 migrations are current; nothing new to apply).
- [ ] An active publication exists (`app_internal.application_state`
      resolves to a real `app_internal.publications` row).
- [ ] `app_readonly` role provisioned with `SELECT` on every `app.current_*`
      view used above (no new grants were needed this milestone -- the
      views already existed and were already granted).
- [ ] `APP_READONLY_DATABASE_URL` set (server-only; never `DATABASE_URL`/
      `APP_DATABASE_URL`/publisher credentials in the web environment).
- [ ] `sslmode` set appropriately for the target Postgres (see
      `lib/db/pool.ts`'s mapping).
- [ ] `pnpm build` succeeds.
- [ ] `app_readonly` cannot write (`INSERT`/`UPDATE`/`DELETE` denied) --
      unchanged from 7A.1/7A.2, re-verify after any role change.
- [ ] Only `app.current_*` views are reachable -- no `app_internal`, no
      raw `app.passages`/`app.passage_comparisons`/
      `app.passage_language_signals`/`app.report_comparisons` access from
      the web tier (asserted statically in the repository test suites).
- [ ] Health check: `GET /` returns 200.
- [ ] Invalid-route 404 check: `GET /companies/<bogus>`,
      `GET /comparisons/<bogus-uuid>`,
      `GET /comparisons/<bogus-uuid>/evidence`, and
      `GET /passages/<bogus-uuid>` all return actual HTTP 404 (not just a
      not-found UI inside a 200) -- run `pnpm test:production` or
      equivalent `curl -o /dev/null -w '%{http_code}'` checks against the
      deployed environment.
- [ ] No publisher/elevated database credentials present in the web
      deployment's environment variables.

### Known limitations (Milestone 7A.4)

- Search-result cards do not show financial-language category/subcategory
  badges (the passage-detail page does, in full, via
  `PassageLanguageSignalsSection`). Adding this to every search-result row
  would require an additional per-row aggregation join
  (`array_agg(DISTINCT category)` over `current_passage_language_signals`)
  on top of an already-filtered, already-joined search query; deferred as
  a scope/performance trade-off rather than added speculatively. The
  category/subcategory *filters* on `/passages` work correctly regardless
  (they use their own `EXISTS` predicate, not the display badge).
- The "Comparison ID" filter on `/passages` is a plain advanced text input
  (paste a UUID), not a dependent company -> comparison dropdown --
  building a friendly picker would need an additional per-company
  comparison-list query and was judged disproportionate to this filter's
  likely usage (mostly reached via a link from elsewhere, e.g. a future
  "search within this comparison" entry point, not manual typing).
- No live browser/visual screenshot verification was performed (same
  constraint as 7A.2/7A.3 -- no browser automation tool available in this
  environment). Verification used `next build`/`next start` +
  `curl`/`fetch`-based real HTTP checks, plus the automated test suite.
  Responsive/mobile behavior (filter disclosure, stacked passage sides)
  was verified at the CSS level, not via a rendered screenshot at multiple
  viewport widths.
- All current AMBIGUOUS rows in the live corpus are one-sided (0 two-sided
  AMBIGUOUS rows exist today); the matched-two-sided-AMBIGUOUS code path
  is implemented and exercised by unit/component tests with synthetic
  data, but not by a real-corpus row.

## Next milestone boundaries (not implemented here)

Semantic/embedding-based search, grounded Q&A, a PDF viewer, exports,
authentication, saved searches, annotations, and web-triggered publishing
are all out of scope for 7A.4 and were not started (Milestone 7B).
