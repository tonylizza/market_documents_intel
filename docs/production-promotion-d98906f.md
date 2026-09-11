# Production Promotion Report — `d98906f`

## 1. Source commit

- HEAD at start and end of this deployment: `d98906f339d89e03f3e037c640b0f287fd8137bf`
  ("Finalize passage alignment research checkpoint")
- Working tree was clean at the start. It is **not** clean at the end: this
  deployment required one small, additive code change (see §16).

## 2. Target environment

- Provider: Neon Postgres (project already in use for the Milestone 7B.3
  Preview deployment; promoted to serve Production for this deployment).
- Vercel project: `tonylizzas-projects/market-documents-intel`.
- Prior to this deployment, Vercel **Production** had no populated database
  credentials (env vars existed as empty placeholders). Production now
  points at the same Neon database Preview already used.

## 3. Pre-deployment DB state

- Migration revision: `app_0008` (already at head — no migrations were
  outstanding).
- Active publication: `2026-08-05.1` (id `443457ec-51b4-535a-b69d-bcf795ec98ad`),
  30 reports / 25 comparisons / 22,169 passages / 26,473 passage comparisons /
  53,793 passage-language signals.
- DB size: 460 MB (out of a 512 MB free-tier project cap).

## 4. Post-migration revision

No migrations were applied — the Neon database was already at `app_0008`,
matching the local `migrations_app` head. Confirmed via
`market-documents publish app-status`.

## 5. Backup / rollback state

- The prior `ACTIVE` publication (`2026-08-05.1` / `443457ec…`) was never
  deleted. After promotion it is `SUPERSEDED` and remains fully queryable.
- Rollback command:
  ```
  market-documents publish promote --publication-id 443457ec-51b4-535a-b69d-bcf795ec98ad
  ```
- No separate Neon branch/snapshot was taken beyond retaining the superseded
  publication row, since the app's own publication-versioning mechanism is
  the project's supported recovery path.

## 6. Rebuild stages performed

The research pipeline itself did not need re-extraction, re-segmentation, or
re-embedding — all 30 reports were already `COMPLETED`/`COMPLETED_WITH_WARNINGS`
with 0 failures across extraction, segmentation, and embedding, reflecting the
frozen `d98906f` checkpoint.

However, verification uncovered a **stale current-run lineage defect**: the
existing `alignment_runs` / `feature_runs` / `language_signal_runs` for all 25
report pairs referenced passage IDs from a segmentation run that predated the
Milestone 6 rebuild (oversized-block handling). The "current" segmentation for
every report had moved on, but alignment/features/language signals had not
been recomputed against it — `_resolve_comparison`'s alignment_run/
language_run lineage guard catches a feature-run vs. language-run mismatch,
but there was no equivalent guard for segmentation vs. alignment staleness.
Net effect: a first publish attempt (`2026-09-11.1`, since deleted) produced
0 passage comparisons and 0 passage-language signals, despite full report/
passage/embedding data.

Fix applied — re-running the same frozen algorithm (no parameter, threshold,
or config changes) against current segmentation:

```
market-documents pairs align-all --force
market-documents pairs features-build-all --force
market-documents pairs language-build-all --force
```

All three completed 25/25 pairs, 0 failures. Verified afterward that all
23,967 alignment rows now resolve against current passage IDs for every pair
(previously 0/23,967 for some pairs sampled, confirmed corpus-wide).

## 7. Corpus counts

| Metric | Count |
|---|---|
| Companies | 6 |
| Reports | 30 |
| Report pairs / comparisons | 25 |
| Canonical passages | 20,677 |
| Passage comparisons (alignment records) | 23,279 |
| Language metrics | 450 |
| Passage-language signals | 54,003 |
| Discovery items | 45 |
| QA retrieval chunks | 0 (excluded — see §9) |

## 8. Embedding / retrieval coverage

- Eligible passages (corpus-wide): 21,153
- Directly embedded: 21,091 (99.7%)
- Remainder (62 passages) represented via retrieval subchunks (oversized
  passages split per "chunking v1" policy) — 0 passages with neither a
  canonical embedding nor retrieval-subchunk representation.
- Effective candidate-retrieval coverage: 100%.

## 9. Alignment metrics

Corpus-wide totals across all 25 pairs (post-fix, current-segmentation-
consistent run):

| Status | Count |
|---|---|
| Matched (unchanged + lightly + substantially modified) | 11,149 |
| — unchanged | 3,094 |
| — lightly modified | 4,456 |
| — substantially modified | 3,599 |
| New | 4,503 |
| Removed | 4,389 |
| Ambiguous | 3,926 |

No gross anomalies found (no company with near-total NEW/REMOVED, no pair
with zero matches). Proportions are consistent with the already-accepted
research-round behavior.

## 10. Publication validation

- Publication built: `2026-09-11.4` (id `4a461cff-0d4c-5de2-9803-1705f8cee5f4`).
- `market-documents publish validate`: **458,592 checks run, all passed.**
- Comparison against prior `ACTIVE` (`2026-08-05.1`):

| Metric | Prior ACTIVE | New | Delta | Explanation |
|---|---|---|---|---|
| Companies | 6 | 6 | 0 | — |
| Reports | 30 | 30 | 0 | — |
| Comparisons | 25 | 25 | 0 | — |
| Passages | 22,169 | 20,677 | −6.7% | Milestone 6 oversized-block segmentation change |
| Passage comparisons | 26,473 | 23,279 | −12.1% | Follows from fewer passages |
| Language metrics | 450 | 450 | 0 | — |
| Passage-language signals | 53,793 | 54,003 | +0.4% | In line |
| Discovery items | 49 | 45 | −8.2% | Follows from comparison-metric shifts |
| QA chunks | present | 0 | — | Deliberately excluded, see §9 below |

## 11. New publication ID

`2026-09-11.4` / `4a461cff-0d4c-5de2-9803-1705f8cee5f4`

## 12. Promotion result

**Promoted successfully.**

```
market-documents publish promote --publication-id 4a461cff-0d4c-5de2-9803-1705f8cee5f4
[OK]   publication 4a461cff-0d4c-5de2-9803-1705f8cee5f4 is now ACTIVE
```

Prior publication `2026-08-05.1` is now `SUPERSEDED` (retained, queryable,
rollback path intact).

## 13. Deployed-app smoke tests

Vercel Production (`market-documents-intel.vercel.app`, deployment
`dpl_3TGQRV9D5T6fpR5G85iZ6xKzKoV4`) — all checks against the **live public
URL**, not the database directly:

| Check | Result |
|---|---|
| `/` (homepage) | 200, all 6 companies (ACT, BEL, KP2, SBP, SDL, SUR) render |
| `/discover` | 200, no error markup |
| `/passages` | 200 |
| `/companies/ACT` | 200 |
| `/ask` | 200, no crash/error text (degrades gracefully with 0 QA chunks) |
| `/methodology` | 200 |

## 14. Warnings / known limitations

1. **QA retrieval chunks were deliberately excluded from this publication**
   (a new `--skip-qa-chunks` build flag, added this session — see §16) due to
   the Neon free-tier project's 512 MB storage cap: a full publication
   including `qa_chunks`/`qa_chunk_passages` could not coexist with the
   retained prior `ACTIVE` publication within that limit, even after
   `VACUUM FULL` reclaimed dead space from a discarded defective draft build.
   **The `/ask` Q&A feature currently has zero passage coverage in
   Production** — it will not error, but it cannot answer anything until a
   future publication includes QA chunks (which will require either a larger
   Neon plan or a smaller per-publication footprint elsewhere).
2. Correspondingly, Vercel Production's `CLOUDFLARE_*`, `GEMINI_*`, and
   `QA_QUOTA_*` env vars were left as empty placeholders — only
   `APP_READONLY_DATABASE_URL` was populated. Wiring up the Q&A stack in
   Production should wait until a publication with QA chunks exists.
3. Passage/comparison/discovery-item count deltas vs. the prior publication
   (§10) are attributable to the Milestone 6 segmentation change, not to any
   defect in this deployment.
4. The stale current-run lineage gap found in §6 (segmentation vs. alignment
   currency not cross-checked) is a real gap in `_resolve_comparison`'s
   lineage guards and should be considered for the next research round —
   it was worked around here (forced recomputation), not fixed at the root.
5. This session's code change (§16) is uncommitted. `git status` also shows
   an unrelated modified `.DS_Store`, not part of this work.

## 15. Rollback instructions

Database:
```
market-documents publish promote --publication-id 443457ec-51b4-535a-b69d-bcf795ec98ad
```
This re-activates `2026-08-05.1` atomically; `2026-09-11.4` becomes
`SUPERSEDED` (not deleted).

Vercel:
```
vercel env rm APP_READONLY_DATABASE_URL production --yes
```
(There is no separate "prior Production" app deployment to roll back to,
since Production had no working database configuration before this
deployment — rollback here means returning Production to its pre-deployment,
unconfigured state, or re-running `vercel env add` with the same value if
only the publication needs to roll back, not the app's DB wiring.)

## 16. Code change made during this deployment

To fit a publication within the Neon free-tier storage cap, added an
additive, backward-compatible `--include-qa-chunks/--skip-qa-chunks` flag
(default: include) to `market-documents publish build`:

- `src/market_documents/publishing/publisher.py`: `PublicationBuilder.__init__`
  gained `include_qa_chunks: bool = True`; the QA-chunk-building block is
  skipped when `False`.
- `src/market_documents/cli/publish.py`: `publish build` gained the CLI flag,
  threaded through to the builder.

This does not touch extraction, segmentation, embedding, alignment,
features, or language-signal logic — no thresholds, weights, or matching
behavior changed. Full publishing test suite (107 passed, 3 skipped) re-run
after the change with no regressions. **Not yet committed** — pending your
review.
