# Track 7F.7a.4a — Shared-Artifact Migration Bootstrap Correction

**Status: architecture/design only. No migrations, no schema changes, no
production actions, no governance deployment were performed.** This track
re-uses the measurements already taken by `docs/production-storage-audit-7f7a3.md`
(production `polished-dawn-80694996`, 432MB, per-table sizes) and
`docs/versioned-shared-publication-artifacts-design-7f7a4.md` (family
classification, local content-stability tests) and the executed precedent
in `docs/7e3-fresh-neon-production-cutover.md`. No new database was queried
to produce this document — every number below is drawn from those three
already-completed, already-cited measurements. This document's job is
narrower than 7F.7a.4's: verify one specific claim (does the *migration
itself* fit under 512MB, not just the *end state*) and pick a vehicle.

## 0. Scope discipline

Every section below is analysis. No `INSERT`/`UPDATE`/`DELETE`/DDL, no
`publish build`/`promote`/`cleanup`, no Neon project creation, no Vercel
deploy. Where a number is not directly measured, it is explicitly marked
as an estimate and derived from a measured figure with the arithmetic
shown, not asserted.

## 1. Verifying the bootstrap problem

7F.7a.4's Phase 2 ("backfill from the ACTIVE publication") was specified
as: create the `app_artifacts` rows for the four shareable families from
the currently-`ACTIVE` publication's existing data, **while that
publication's own inline copies remain in place** (Phase 3's compatibility
views are what let old rows keep working without a backfill of *their own*
FK, and Phase 4 is what stops writing inline copies going forward — neither
removes today's inline data). That ordering is deliberate and correct on
its own terms (it is exactly 7E.1's own additive-first discipline), but it
means Phase 2 is, by construction, a **coexistence** step, not a
**replacement** step.

Modeled phase by phase, using `docs/production-storage-audit-7f7a3.md`'s
measured production baseline (432MB total: `app` 304MB, `app_corpus`
119MB, `app_internal` 0.2MB, unattributed ~8.6MB) and its per-table
breakdown for the four shareable families (retrieval_contexts 58MB +
retrieval_context_language_categories 34MB + retrieval_context_risk_subcategories
~2.4MB combined-bucket share + passage_comparisons 33MB + qa_chunks 75MB +
qa_chunk_passages 14MB + passage_language_signals 66MB ≈ **280MB**, per
audit §10):

| phase | starting size | new heap+index added | removed | transient peak | headroom (512MB cap) | fits? |
|---|---|---|---|---|---|---|
| 1. schema only | 432MB | ~5 empty tables + indexes, <1MB | none | ~432MB | ~80MB | Yes |
| 2. backfill `app_artifacts` while inline data remains | 432MB | **~280MB** (one full copy of the four families' current content, table+index, since production today holds exactly one publication — no dedup benefit exists yet at backfill time) | none (inline data explicitly retained per Phase 3's design) | **~712MB** | **−200MB** | **No** |
| 3. compatibility views | ~712MB (inherits Phase 2's state) | ~0 (view `CREATE OR REPLACE`, no data) | none | ~712MB | −200MB | No (already broken by Phase 2) |
| 4. publisher writes shared artifacts | ~712MB | ~0 for the existing publication; future builds benefit, this one doesn't | none yet | ~712MB | −200MB | No |
| 5. validate | ~712MB | 0 (read-only checks) | none | ~712MB | −200MB | No |
| 6. stop duplicate writes | ~712MB | 0 (behavior change for *future* builds only) | none | ~712MB | −200MB | No |
| 7. remove legacy inline columns | ~712MB → ~432MB after this runs | 0 | **−280MB** (the inline copies finally dropped) | drops back to ~432MB only *after* Phase 7 | 80MB, restored | Yes, but only once Phase 7 completes |

**Confirmed: Phase 2 cannot fit under the 512MB cap in place.** The
pasted brief's ~712MB estimate is correct to within the precision the
audit's own per-table figures support (432 + 280 = 712). This is not
close to the cap — it overshoots by ~200MB, more than double the current
~80MB headroom. Critically, Phase 7 (the step that would bring storage
back down) is scheduled *last*, and every phase before it depends on
Phase 2 having succeeded. **7F.7a.4's own final-state estimate (~456MB,
+56MB headroom, §12 scenario F of that document) describes the state
after all seven phases complete — it says nothing about whether the
database can survive getting there, and it cannot, as specified.** This
confirms the pasted brief's framing: do not assume the destination being
reachable means the road there is.

## 2. Evaluating a fresh-Neon cutover as the migration vehicle

`docs/7e3-fresh-neon-production-cutover.md` already executed this pattern
once, for a different problem (moving off a near-capacity, pre-`app_corpus`-sharing
database), and it is directly reusable here. Its shape: build the *final*
schema fresh, on an empty branch, run the full corpus-load and
`publish build` pipeline once against it, validate, smoke-test, then cut
the application's `APP_READONLY_DATABASE_URL` over — no in-place
transformation of the live database ever happens, so there is no
inline-data-plus-new-data coexistence step to blow a storage cap on.

Applied to this problem: create a fresh Neon project, apply migrations
including the new `app_artifacts` schema from 7F.7a.4 §7, run the
corpus-load + `publish build` pipeline (now writing `app_artifacts` rows
directly and thin `app.*` rows with FK-only content — never constructing
the old inline-content columns at all, since there is no pre-existing
publication on this project to stay compatible with), validate, smoke-test,
cut over Vercel's env var, redeploy. `polished-dawn-80694996` (current
production) remains untouched throughout and is the rollback target,
exactly as `young-waterfall-72587754` was retained through 7E.3.

**Does this avoid the ~280MB backfill duplication?** Yes, and precisely
because there is no *backfill* step in this vehicle at all — there is
only a *first build*. A first build populates each `app_artifacts` row
exactly once (there is nothing to copy from and nothing to keep
compatible with), so the ~280MB of family content is written **once**,
not written-once-while-a-second-copy-of-the-same-content-also-exists.
This is the same reason 7E.3 itself never had to reason about a
432MB-plus-300MB peak: its "old" and "new" databases were always two
independent Neon projects, never two copies inside one project's storage
budget.

## 3. Modeling fresh-project storage

Component-by-component, reusing 7F.7a.3's measured per-table figures and
7F.7a.4's own classification (§6/§7 of that document) for which family
lands where:

| component | measured/derived basis | estimate |
|---|---|---|
| `app_corpus` (shared passages + embeddings) | 7F.7a.3 §2, measured directly: 119MB | **119MB** — unchanged; same corpus, same dedup design, nothing about this track touches it |
| `app_artifacts` (four families, one generation each) | sum of the same four families' current `app` schema footprint (7F.7a.3 §3): 92 (retrieval_contexts+children) + 33 (passage_comparisons) + 66 (passage_language_signals) + 89 (qa_chunks+qa_chunk_passages) | **~280MB** — same raw content as today, just relocated from `app.*` inline columns into `app_artifacts.*`; moving where it's stored doesn't shrink it on a first build |
| thin `app.*` publication layer (genuinely per-publication: `companies`, `reports`, `report_comparisons`, `language_metrics`, `discovery_items`, `metric_definitions`, `metric_label_thresholds`, narrative/structured comparison tables, plus the now-FK-only rows for the four families) | 7F.7a.3's "everything else" bucket (~2.4MB) + 7F.7a.4's own accounting of the residual `app` layer once the four families are subtracted (304 − 280 = 24MB) | **~24MB** |
| `app_internal` | 7F.7a.3 §2, measured: 0.2MB | **~0.2MB** |
| system/catalog overhead | 7F.7a.3 §2, measured: ~8.6MB (this project would carry its own fresh version of this, plausibly similar since it's driven by extension/catalog metadata, not application row count) | **~8–10MB** |
| **expected total** | sum | **~431–433MB** |

**Conservative upper bound:** add back the transient index-build overhead
Neon/Postgres carries during large index creation (HNSW indexes in
particular build a working set alongside the final structure before the
old one is dropped — 7E.3 §13's first `qa_chunks` attempt timed out
precisely because of sustained load during a large batched insert, not
because of a size overshoot, but the *risk profile* is the same
class of event) and a first-build corpus that may have grown slightly
since the 7f7a3 audit (two production rollouts occurred after the
`7e3` corpus was fixed): **~460–480MB** as a conservative ceiling,
still comfortably under 512MB, with the same order of headroom 7E.3
itself measured (218MB, ~43%) if the expected case holds, or closer to
the 7F.7a.3-audited ~80MB if the ceiling case holds.

**Correction to a possible misreading:** the fresh project's first-build
size is **not** 7F.7a.4's post-migration ~456MB estimate re-derived from
scratch — that number already assumed the shared-artifact design was in
place and only ~24MB of genuinely-new content was being added on top of
an already-existing 432MB. Here, the fresh project starts at **zero**,
so its first build has to write the *entire* ~280MB of family content
plus the ~119MB corpus plus the ~24MB thin layer — there is no "reuse an
existing generation" benefit to draw on for a project's very first
build. The number lands in the same ~432MB neighborhood as today's
production by coincidence of arithmetic (119+280+24+8.6 ≈ 432, and
that's also today's actual total), not because sharing has already paid
off. The payoff is deferred to the *second* build (§4 below).

## 4. Modeling first-build and future-build peaks

**Fresh-project first build:** per §3, the maximum transient size while
constructing the first publication is bounded by the final size itself
(~432–480MB) plus ordinary in-flight index-build working space —
there is no second copy of anything, because nothing existed before it.
This is qualitatively the same shape 7E.3 actually measured (pre-promotion
peak 293MB was *higher* than post-promotion 294MB only trivially, because
its build never carried a duplicate-content problem either). No scenario
here approaches 512MB on the first build.

**Future builds, once the fresh project is live and using per-family
version axes (7F.7a.4 §7):** steady state after the fresh cutover and one
"quiet" rebuild (an unchanged-content republish, matching what
`docs/versioned-shared-publication-artifacts-design-7f7a4.md` §12
scenario F modeled) settles at ≈ 432MB (one artifact generation per
family) + a second thin layer retained for rollback (~24MB) ≈ **~456MB**,
which matches 7F.7a.4's own number and is the correct baseline for the
scenarios below. Call this **S = 456MB**, headroom **56MB**.

| scenario | families whose artifact version changes | new content duplicated | transient peak | headroom (512MB cap) | fits? |
|---|---|---|---|---|---|
| A. no artifact family changes | none | ~24MB (new thin layer only, all four families reused) | S + 24MB ≈ **480MB** | 32MB | Yes |
| B. governance/report-level metric-only change | none (governance metrics live in `app.language_metrics`/`app.report_comparisons`, inside the ~24MB thin layer per 7F.7a.4 §16 — confirmed empirically that the underlying `passage_language_signals` rows do not change for this kind of release) | ~24MB (same as A) | S + 24MB ≈ **480MB** | 32MB | Yes |
| C. language-signal artifact version bump | `passage_language_signals` (66MB) | 66 + 24 = 90MB | S + 90MB ≈ **546MB** | **−34MB** | **No** |
| D. alignment artifact version bump | `passage_comparisons` (33MB) + `retrieval_contexts`+children (92MB), since both key off the alignment version per 7F.7a.4 §7 | 125 + 24 = 149MB | S + 149MB ≈ **605MB** | **−93MB** | **No** |
| E. QA-chunk artifact version bump | `qa_chunks`+`qa_chunk_passages` (89MB) | 89 + 24 = 113MB | S + 113MB ≈ **569MB** | **−57MB** | **No** |
| F. all four families change simultaneously | all four | 280 + 24 = 304MB | S + 304MB ≈ **760MB** | **−248MB** | **No** |

**This is the finding the pasted brief specifically asked to be
quantified, and it matters:** four of six realistic future-release
shapes — including the single-family bumps C, D, and E individually, not
just the all-at-once case F — already exceed the 512MB cap on their own,
using the *post-migration, fully-shared* architecture's own steady state
as the starting point. The versioned-artifact design does not make the
512MB constraint go away; it only changes which releases are safe
(metric-only changes, scenario B, which is what 7F.7a.1/governance
actually was) from which are not (any release that legitimately bumps
one of the four content-bearing families, scenarios C/D/E/F). Given
7F.7a.4 §5's own measurement — 0% divergence in any of the four families
across three real releases including two that shipped — scenario B has
been the common case so far, but nothing in the design guarantees it
stays that way, and §16 of that same document already flags governance
as the one place a family-content change was plausible before being
empirically ruled out for *this specific pair of releases*.

## 5. Version-generation retention and repeated bumps

Walking the pasted brief's exact sequence, using the same per-family
sizes and the rule that a generation is retained as long as *any*
retained publication's thin rows still FK to it (7F.7a.4 §10):

- **P1** built: `alignment_v1` (92+33=125MB), `signals_v1` (66MB),
  `qa_v1` (89MB). One generation of each. Artifact-layer total: 280MB.
  Plus corpus 119MB, plus P1's own thin layer ~24MB. **Total ≈ 423MB.**
- **P2** built, reusing all v1 generations (no code changed). No new
  artifact-layer content. P1 is retained as the rollback target, so its
  thin layer (~24MB) stays alongside P2's own (~24MB). **Total ≈
  423 + 24 = 447MB.** (Matches §4's "S ≈ 456MB" scenario to within
  rounding — the small difference is which publication's thin-layer
  size is used as the marginal add.)
- **P3** built, `signals_v2` (new content, 66MB) while `signals_v1` is
  still referenced by P1 (if P1 is still retained) and/or P2 (if P2 is
  the retained rollback target instead of P1). Assuming standard
  "keep active + one rollback" policy, P1 can now be GC'd (nothing newer
  than P2 needs to roll back further than one step) — but only *after*
  `cleanup_publications` removes P1's thin rows, which must happen before
  `gc_orphaned_corpus_rows`'s extended reference-count check (7F.7a.4
  §10) can see `signals_v1` as unreferenced. If that cleanup runs
  promptly: artifact layer = 125 (alignment_v1, unchanged) + 66
  (signals_v2, new) + 89 (qa_v1, unchanged) = 280MB, same total as
  before — old `signals_v1` freed. **Total ≈ 423MB again.** If cleanup
  lags (P1 retained "just in case" past the point P2 is superseded):
  artifact layer briefly carries both `signals_v1` and `signals_v2`
  (280 + 66 = 346MB), plus three thin layers (~72MB), plus corpus
  119MB ≈ **537MB — already over the cap**, before P4 or P5 are even
  considered.
- **P4** built, `alignment_v2` (125MB new) while `alignment_v1` may still
  be referenced by whichever publication is the current rollback target.
  Same conditional as P3: prompt GC keeps the artifact layer at 280MB
  (one generation per family); lagging GC stacks another 125MB.
- **P5** built, `qa_v2` (89MB new), same pattern again.

**When can GC safely delete an old generation?** Only when zero retained
publications reference it — mechanically, after `cleanup_publications`
has removed every publication's thin rows for every publication outside
the retention window, run in that order (7F.7a.4 §10, extending the
already-shipped `gc_orphaned_corpus_rows` ordering). This is a policy
question as much as a mechanical one: **the number of publications kept
retained at once is what actually bounds storage, not the sharing design
itself.** With a strict "active + 1 rollback" policy and prompt cleanup
after every promote, at most 2 generations per family can ever be alive
simultaneously — worst case (every family bumps between the active and
its one retained rollback) is 2× the 280MB artifact layer = 560MB,
**still over the cap on its own**, before even the thin layers and
corpus are added. **Repeated legitimate version bumps absolutely can
reapproach or exceed 512MB even under this design** — the pasted brief's
suspicion here is correct, and it is a materially larger risk than the
single-family bump scenarios in §4, since it depends on retention policy
discipline (how promptly cleanup+GC run) rather than only on release
content.

## 6. QA confirmation gate — retained, not skipped

7F.7a.4 §5's stability claim for `qa_chunks`/`qa_chunk_passages` is
explicitly **not** measured — every local publication used
`--skip-qa-chunks`, so zero rows exist to compare (7F.7a.4 §14). This
track does not relax that gap. Before `qa_chunks` sharing (under either
migration vehicle) is treated as production-ready, run two local
`--include-qa-chunks` builds from unchanged source data and compare
`embedding_text_hash` per `(report_id, chunk_index)` across them — the
exact test 7F.7a.4 §14/§19 already specified. This gate blocks Phase 4
(or, under the fresh-cutover vehicle, blocks the first build from writing
`qa_chunks` as a shared artifact) specifically for this one family; the
other three families already have the measured evidence (7F.7a.4 §5) to
proceed without it. No such build was run in this track — it remains an
open prerequisite, not newly satisfied.

## 7. Comparing migration options

| | A. in-place additive migration | B. fresh Neon cutover | C. lifecycle weakening (in-place publication mutation) |
|---|---|---|---|
| **storage feasibility** | **No.** Phase 2 requires ~712MB against a 512MB cap (§1) — provably does not fit, not a matter of optimization | **Yes.** First build peaks at ~432–480MB (§3/§4); no coexistence step exists in this vehicle by construction | Frees ~304MB before a build by retiring the active publication first, but only by taking production to zero publications for the build's duration — "feasible" in a narrow storage sense at the cost of an outage (7F.7a.4 §18) |
| **downtime** | N/A — migration cannot complete to test this | **None required** — proven by 7E.3 itself: build in parallel, cut over via env var + redeploy, old project serves traffic throughout | **Full outage** for the build duration (7F.7a.4 §18 already rejected this on this basis) |
| **rollback safety** | Undermined by construction: a Phase-2 failure that hits the storage cap mid-backfill leaves `app_artifacts` partially populated in the *same* database the live publication depends on | **Strongest of the three** — old project (`polished-dawn-80694996`) untouched throughout, exact 7E.3 precedent; rollback is an env-var revert, already exercised operationally | Destroys the rollback publication's own frozen-copy guarantee the moment in-place mutation starts (7F.7a.4 §18) |
| **implementation complexity** | Moderate on paper (7 additive phases) but the plan is unexecutable past Phase 2 as specified, so its real complexity is understated | Higher raw effort (full corpus-load + extraction + publish pipeline, matching 7E.3's 170-step runbook) but it is a **proven, already-executed pattern** with known failure modes and known fixes (QA-chunk insert timeout, background-process races — both already resolved once in 7E.3 §13) | Deceptively simple to describe, harder to implement safely (transactional partial-update semantics across 7 FK-linked tables) — already assessed and rejected in 7F.7a.4 §18 |
| **operational risk** | High — the failure mode is discovered mid-migration against a live database, not in review | Low-moderate — same risk categories 7E.3 already surfaced and mitigated; no new risk category introduced | High — partial-build failure leaves an existing publication in an inconsistent state with no clean recovery path (7F.7a.4 §18) |

## 8. Final recommendation

**FRESH_NEON_CUTOVER_REQUIRED**

The in-place migration specified in 7F.7a.4 is not executable as written:
Phase 2 alone requires ~712MB against a 512MB cap, a ~200MB overshoot with
no smaller phase ordering available (Phase 7, the only phase that shrinks
storage, is necessarily last and depends on every earlier phase having
already succeeded). Lifecycle weakening was already correctly rejected in
7F.7a.4 §18 on rollback-safety and partial-failure grounds, and nothing
in this track's analysis changes that. A fresh-Neon cutover, structurally
identical to the already-executed `docs/7e3-fresh-neon-production-cutover.md`,
avoids the bootstrap problem entirely because it has no coexistence step:
a first build into an empty project writes each family's content exactly
once, landing at an expected ~432MB (§3), comfortably under the cap, with
zero required downtime and the strongest rollback guarantee of the three
options (§7).

**This is not a permanent escape from the 512MB constraint**, and §4/§5
of this document quantify why: once live on the shared-artifact
architecture, a release that bumps any single family's artifact version
(language-signal, alignment, or QA-chunk) already exceeds the cap on its
own steady-state math (§4, scenarios C/D/E), and repeated legitimate
version bumps under even a disciplined "active + 1 rollback" retention
policy can reach ~560MB in the artifact layer alone before corpus and
thin-layer costs are added (§5). The fresh cutover fixes the *migration*
problem the pasted brief raised; it does not fix the *architecture's*
long-run storage ceiling, which remains genuinely tight against 512MB.

**Bounded implementation sequence (not executed):**

1. Finalize the `app_artifacts` schema and the three version constants
   from 7F.7a.4 §7 in code, targeted at being written natively by a fresh
   build — no Phase-3-style compatibility views are needed under this
   vehicle, since there is no pre-existing publication to stay compatible
   with.
2. Add the existence-check-before-insert pattern (7F.7a.4 §11) to the
   five construction sites in `_build_rows`, writing directly into the
   new shape.
3. Run the §6 QA-chunk confirmatory gate locally (two `--include-qa-chunks`
   builds, compare `embedding_text_hash`) — required before step 5
   includes QA chunks as a shared artifact; the other three families
   already have the measured evidence (7F.7a.4 §5) to proceed.
4. Create a fresh Neon project (7E.3 §3's pattern: verify Postgres
   version, avoid credential leakage into any transcript, rotate on any
   accidental exposure), apply migrations to head including the new
   schema.
5. Run the full corpus-load + extraction + `publish build` pipeline
   against the fresh project (7E.3 §6-13's proven runbook), building
   directly into the shared-artifact shape.
6. `publish validate`; local smoke test against the fresh database
   (7E.3 §14/§18 pattern); full backend + frontend test gates (7E.3 §19).
7. Cut over `APP_READONLY_DATABASE_URL` and redeploy (7E.3 §20 pattern);
   retain `polished-dawn-80694996` untouched as the rollback target.
8. **Before any future version bump**, establish and document a
   retention/GC policy bound to at most 2 concurrently-retained
   publications with cleanup run promptly after every promote — §5 shows
   this is what actually keeps storage under the cap going forward, not
   the sharing design alone.

## 9. Documentation

This file covers all 9 sections of the correction brief. A correction
note has been added to
`docs/versioned-shared-publication-artifacts-design-7f7a4.md` pointing
here. No migrations, schema changes, or production actions were taken.
