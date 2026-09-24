# Track 7F.7a.4: Versioned Shared Publication Artifact Design

**Status: architecture/design only. No production access, no schema changes, no migrations, no publish/promote/deploy actions were taken. All measurements in this document are read-only queries against the local research/app databases (`market_documents_app` on `localhost:5434`), plus citations of `docs/production-storage-audit-7f7a3.md` for production numbers. Production Neon was not queried.**

## 0. Scope discipline (§1 of the brief)

This track is analysis and design only, per explicit instruction. Every
query below is a `SELECT`; no `INSERT`/`UPDATE`/`DELETE`/DDL was run against
any database, local or remote, and no migration, publish, promote, or
cleanup command was executed. All local evidence comes from four
publications that already existed in the local `market_documents_app`
database before this track started (see §5) — no new publication was
built to gather this evidence.

## 1. Background: what 7E.1 already solved and explicitly declined

`docs/7e1-publication-storage-lifecycle-hardening.md` moved `passages` and
`passage_embeddings` into a non-publication-scoped `app_corpus` schema,
keyed by `labels.derive_corpus_id(table, *parts)` — `derive_id` with
`publication_version` pinned to the sentinel `labels.CORPUS_SCOPE =
"__corpus__"` (`src/market_documents/publishing/labels.py:22-60`). It
redefined `app.current_passages`/`app.current_passage_embeddings`
(`src/market_documents/publishing/schema.py`) to resolve through the
corpus tables, added `gc_orphaned_corpus_rows` (reference-counted, not
cascade-based — `src/market_documents/publishing/publisher.py:1529-1583`),
and benchmarked the web hot path unaffected (1.24ms → 1.29ms).

It explicitly declined to extend this to `retrieval_contexts`,
`passage_comparisons`, `qa_chunks`, `passage_language_signals`, reasoning
that these are "genuinely outputs of code that changes between releases"
and that a single code/config change bumps `source_configuration_hash`
for an entire publish run, not per family — so sharing them would need
"its own design and benchmarking." `docs/production-storage-audit-7f7a3.md`
(Track 7F.7a.3, completed immediately before this track) measured
production at 432MB/512MB cap, one single `ACTIVE` publication, ~280MB of
the 304MB `app` schema attributable to exactly these four families plus
their two child tables, and a projected second-build transient peak of
~730MB — concluding `ARCHITECTURAL_CHANGE_REQUIRED` and handing this
track the open question.

## 2. Inventory of each large artifact family

Traced via `src/market_documents/publishing/publisher.py` (1,583 lines,
single `PublicationBuilder._build_rows` method), `src/market_documents/publishing/schema.py`
(`current_*` view definitions), and `web/lib/repositories/*.ts`.

### A/B/C. `retrieval_contexts` / `retrieval_context_language_categories` / `retrieval_context_risk_subcategories`

- **Research/source inputs:** `PassageComparison` (this publication's own
  alignment output, itself derived from `PassageAlignment` research rows),
  `Passage` publication-eligibility/classification flags
  (`primary_narrative_eligible`, `feature_eligible`,
  `structured_content_category`), `LanguageSignalTag`s accumulated per
  `(passage_comparison_id, report_side)` in the passage-language-signals
  pass.
- **Builder:** `publisher.py:1174-1305` (`# --- Retrieval contexts
  (Milestone 7B.1) ---`), building one `RetrievalContext` per non-null
  side of every `PassageComparison` (`COMPARISON_LINKED`), plus one per
  passage never referenced by any comparison (`REPORT_ONLY`,
  `publisher.py:1261-1305`).
- **Config dependencies:** passage-exclusion policy
  (`labels.PUBLICATION_EXCLUDED_CATEGORIES`), alignment status/type/
  confidence vocabulary (no independent version constant today).
- **Algorithm/version dependencies:** the alignment engine that produced
  the source `PassageAlignment` rows, and the extraction/classification
  code that produced `primary_narrative_eligible`/`feature_eligible`/
  `structured_content_category` — neither has an explicit version
  constant surfaced to the publisher.
- **Publication writer:** `RetrievalContext`/`RetrievalContextLanguageCategory`/
  `RetrievalContextRiskSubcategory` ORM rows, ids via `labels.derive_id(pv,
  "retrieval_contexts", str(app_pc.id), side_value)` (`publisher.py:1205`,
  `:1238`, `:1251`).
- **App tables:** `app.retrieval_contexts`, `app.retrieval_context_language_categories`,
  `app.retrieval_context_risk_subcategories`.
- **`current_*` views:** `app.current_retrieval_contexts`,
  `app.current_retrieval_context_language_categories`,
  `app.current_retrieval_context_risk_subcategories`
  (`src/market_documents/publishing/schema.py`).
- **Web consumers:** `web/lib/repositories/postgres-semantic-retrieval-repository.ts`
  — every retrieval/search/filter query in the file goes through
  `app.current_retrieval_contexts` (and its two category child views),
  confirmed at lines 59, 126, 204-212, 314-316, 449-459.

### D. `passage_comparisons`

- **Research/source inputs:** `PassageAlignment` (source alignment engine
  output), filtered by the same category-exclusion/one-sided-match rules
  applied to `passages`.
- **Builder:** `publisher.py:823-892` (`# --- Passage comparisons and
  passage-language signals ---`).
- **Config/algorithm dependencies:** the alignment engine version only —
  no dependency on language-signal, governance, or financial-condition
  code at all (confirmed empirically, §5).
- **Publication writer:** id via `labels.derive_id(pv, "passage_comparisons",
  str(alignment.id))` (`publisher.py:864`); natural/source key is
  `source_alignment_id` (unique per publication via
  `uq_app_passage_comparisons_pub_source`).
- **App table:** `app.passage_comparisons`.
- **`current_*` view:** `app.current_passage_comparisons`.
- **Web consumers:** `postgres-semantic-retrieval-repository.ts:316`
  (`LEFT JOIN app.current_passage_comparisons`).

### E/F. `qa_chunks` / `qa_chunk_passages`

- **Research/source inputs:** `app_passages`' already-published rows for
  one report (text from the shared `app_corpus.passages` row, per 7E.1),
  chunked and re-embedded independently of the canonical passage
  embeddings — see the module docstring the builder references.
- **Builder:** `publisher.py:1309-1424` (`# --- Q&A retrieval chunks
  (Milestone 7B.2) ---`), calling `build_qa_chunks(report_passage_rows,
  embedding_model.count_tokens)` then `embedding_model.encode_batch(...)`.
- **Config dependencies:** chunk-window target/overlap-token
  configuration consumed by `build_qa_chunks` (see
  `tests/publishing/test_qa_chunking.py`), the embedding model/revision
  (`MODEL_NAME`/`MODEL_REVISION`, `publisher.py:1401-1402`).
- **Algorithm/version dependencies:** the chunk-window algorithm itself.
  `tests/publishing/test_qa_chunking.py:216`
  (`test_same_input_yields_identical_output`) confirms the builder is a
  pure, deterministic function of its input passage rows and
  configuration — no dependency on governance/financial-condition/
  language-signal code anywhere in `publisher.py:1309-1424`.
- **Publication writer:** chunk id via `labels.derive_id(pv, "qa_chunks",
  str(candidate.report_id), str(candidate.chunk_index))`
  (`publisher.py:1384-1386`); member-mapping id via `labels.derive_id(pv,
  "qa_chunk_passages", str(chunk_id), str(member_passage_id))`
  (`publisher.py:1413-1415`).
- **CLI flag:** `market-documents publish build --include-qa-chunks/--skip-qa-chunks`
  (`src/market_documents/cli/publish.py:155-169`), threaded into
  `PublicationBuilder(include_qa_chunks=...)`.
- **App tables:** `app.qa_chunks`, `app.qa_chunk_passages`.
- **`current_*` views:** `app.current_qa_chunks`, `app.current_qa_chunk_passages`.
- **Web consumers:** `web/lib/repositories/postgres-qa-chunk-repository.ts`
  — every Q&A retrieval query reads `app.current_qa_chunks`/
  `app.current_qa_chunk_passages` (lines 51, 86, 137, 175).

### G. `passage_language_signals`

- **Research/source inputs:** `cd.passage_language_signals` (per-passage
  category-hit signal rows from the research language-signal pipeline),
  `cd.category_hits_by_signal_id` (subcategory-level hits, including
  `financial_condition` and `governance` subcategories).
- **Builder:** `publisher.py:1000-1170` (`# --- passage_language_signals
  ---`, two passes: core categories at `:1013-1042`, taxonomy-category
  hits including financial_condition/governance at `:1044-1170`).
- **Config/algorithm dependencies:** `CORE_CATEGORIES`,
  `CUSTOM_TAXONOMY_CATEGORIES` (imported constants, not versioned), the
  research-side language-signal extraction/dictionary-matching pipeline
  that produced `cd.passage_language_signals`/`category_hits_by_signal_id`
  in the first place.
- **Publication writer:** ids via `labels.derive_id(pv,
  "passage_language_signals", str(signal.id), category, "")`
  (`publisher.py:1020-1022`, core categories) and `..., hit.category,
  hit.subcategory` (`:1057-1059`, taxonomy hits, including
  financial_condition/governance).
- **App table:** `app.passage_language_signals`.
- **`current_*` view:** `app.current_passage_language_signals`.
- **Web consumers:** not read directly by the semantic-retrieval
  repository's SQL grepped above; consumed via `app.language_metrics`/
  `app.report_comparisons` aggregation, which is a *separate*,
  genuinely-per-publication downstream table (percentile bands computed
  over `snapshot.comparisons`, `publisher.py:395-458`) — important for
  §16 below: the raw per-passage signal rows and the aggregated,
  publication-population-relative bands are architecturally distinct
  layers, and only the latter is legitimately release-specific.

## 3. Artifact identity per family

| family | source/content-determining inputs | NOT part of identity (confirmed) |
|---|---|---|
| `passage_comparisons` | `source_alignment_id` (`PassageAlignment.id`) + alignment-algorithm version | governance/financial-condition config, language-signal taxonomy, QA chunking config |
| `retrieval_contexts` | `source_alignment_id` (or `source_passage_id` for `REPORT_ONLY`) + `report_side` + `context_type` + alignment-algorithm version + passage-eligibility/classification version | governance/financial-condition config, QA chunking config, metric percentile bands |
| `retrieval_context_language_categories`/`_risk_subcategories` | parent retrieval-context identity + the language-signal-tag category/subcategory set observed for that side | metric percentile bands, disclosure-change scoring |
| `qa_chunks`/`qa_chunk_passages` | `source_report_id` + `chunk_index` + chunking-window config version + embedding model/revision | alignment output, language-signal output, governance/financial-condition config entirely |
| `passage_language_signals` | `source_signal_id` (research `LanguageSignalTag`/hit row id) + `category` + `subcategory` + language-signal-extraction/taxonomy version | metric percentile bands, disclosure-change scoring, which categories are currently *displayed* as report-level metrics |

No single global hash fits all five identities — `passage_comparisons`
and `retrieval_contexts` share an alignment-version axis but
`retrieval_contexts` additionally depends on passage-classification
version; `qa_chunks` depends on an entirely disjoint axis (chunking
config + embedding model) with **zero** dependency on alignment or
language-signal code; `passage_language_signals` depends on the
language-signal extraction version, independent of alignment identity
beyond needing the same alignment row to exist. This matches the brief's
instruction not to invent one hash — each family gets its own version
axis (§7).

## 4. Current versioning analysis

Every `app`/`app_internal` row's id comes from exactly one function,
`labels.derive_id(publication_version, table, *parts)`
(`labels.py:22-34`), and `publication_version` is a **free-form,
caller-supplied string** passed to `PublicationBuilder.__init__`
(`publisher.py:260-266`) and to `market-documents publish build
<publication_version>` (`cli/publish.py`). There is exactly one other
version-shaped identifier in the codebase:

- `Publication.source_configuration_hash` — computed by
  `_source_configuration_hash(research_schema_version)`
  (`publisher.py:207-215`), hashing `research_schema_version` +
  `labels.METRIC_THRESHOLD_VERSION` ("percentile_v1") +
  `labels.PUBLICATION_EXCLUDED_CATEGORIES`. This is stored once per
  `Publication` as metadata (visible in `market-documents publish audit`
  output), **never used to key any row's id or to gate reuse of any
  table's content** — it answers "was this publication built against
  compatible research schema/config," not "which of these five artifact
  families actually changed."

There is **no** `ALIGNMENT_ALGORITHM_VERSION`, `LANGUAGE_SIGNAL_VERSION`,
`QA_CHUNKING_VERSION`, or `RETRIEVAL_CONTEXT_VERSION` constant anywhere
in the codebase (confirmed by grep across `publisher.py`, `labels.py`,
and the `market_documents.language_features`/`market_documents.alignment`
packages referenced from `publisher.py`'s imports). `METRIC_THRESHOLD_VERSION`
exists but versions only the percentile-banding scheme applied to
*displayed* metrics — a downstream, genuinely-per-publication concern,
not any of the five families in scope here.

**Does a single code/config change currently invalidate an entire
publish run even when most artifact families are unchanged? Yes, by
construction and confirmed empirically.** `publication_version` is a
single string chosen once per `publish build` invocation and threaded
into every `derive_id` call in `_build_rows` — there is no per-table or
per-family opt-out. §5 shows three real production code changes
(healthcare-review promotion → financial-condition metrics [7F.5] →
governance metrics [7F.7a.1]) each produced a **new `publication_version`
and therefore entirely new ids for every row in all five families**, even
though the content of all five families was **100% identical** across
all three releases (only `app.language_metrics`/`app.report_comparisons`
— the genuinely release-specific aggregation layer — actually changed).

## 5. Content-stability test (measured against real local publications)

Four real publications exist in the local `market_documents_app`
database (queried directly, `app_internal.publications`):

| `publication_version` | status | built for |
|---|---|---|
| `2026-09-17-7d2c-healthcare-services-review-promotion.1` | SUPERSEDED | pre-financial-condition baseline |
| `7f4-local-validation-1` | SUPERSEDED | Track 7F.5 financial-condition metrics |
| `7f7a1-local-1` | SUPERSEDED | Track 7F.7a.1 governance metrics |
| `7f7a1a-local-1` | ACTIVE | governance metrics, rebuilt |

Row counts for all four candidate families are **identical across all
four publications** (`34099` retrieval_contexts, `51369`
retrieval_context_language_categories, `533`
retrieval_context_risk_subcategories, `23279` passage_comparisons,
`54003` passage_language_signals; `qa_chunks`/`qa_chunk_passages` are `0`
in all four — every local build used `--skip-qa-chunks`, see the
qa_chunks caveat below).

Content-equality was tested by joining each family through its stable
source key (`source_alignment_id` for `passage_comparisons`, joined
through to `retrieval_contexts`/`passage_language_signals`; direct
`source_passage_id` for `REPORT_ONLY` contexts), hashing every non-id
content column per row, and comparing hash sets between publication
pairs (`md5` over pipe-joined column values, real SQL run against the
local database, not estimated):

| family | pre-fincond → fincond (`healthcare-review` → `7f4`) | fincond → governance (`7f4` → `7f7a1`) | governance rebuild (`7f7a1` → `7f7a1a`) |
|---|---|---|---|
| `passage_comparisons` | 23,279/23,279 matched, 0 changed, 0 missing | 23,279/23,279 matched, 0 changed, 0 missing | 23,279/23,279 matched, 0 changed, 0 missing |
| `retrieval_contexts` | — (see below) | 34,099/34,099 matched, 0 changed, 0 missing | 34,099/34,099 matched, 0 changed, 0 missing |
| `passage_language_signals` | 54,003/54,003 matched, 0 changed, 0 missing | 54,003/54,003 matched, 0 changed, 0 missing | 54,003/54,003 matched, 0 changed, 0 missing |

(`retrieval_contexts`' pre-fincond→fincond pair was not separately run —
the fincond→governance and rebuild pairs were prioritized as the higher-
value comparisons since they bracket both production releases in
`docs/production-storage-audit-7f7a3.md`; the two pairs actually run
already span both real code changes production went through.)

**Result: 100% of rows, 100% of content, byte-identical across every
family tested, across all three real code changes including the two that
actually shipped to production (7F.5, 7F.7a.1).** Estimated MB reusable
if these three families were shared: effectively their entire measured
footprint (§12).

**qa_chunks/qa_chunk_passages — evidence gap, explicitly flagged, not
filled with assumption.** All four local publications were built with
`--skip-qa-chunks` (`publisher.py:1321-1322`: `include_qa_chunks=False`
makes the per-report loop iterate zero times), so **no local row-level
content comparison could be run** for this family — this is a genuine
blocker, not a byte-measured result. The architectural case for stability
is strong (§2's trace of `publisher.py:1309-1424` shows the chunk builder
touches only corpus passage text/heading/pages and the embedding model,
with zero code path through governance/financial-condition/language-
signal logic, and `test_same_input_yields_identical_output` proves the
chunk-window function itself is deterministic), but it is **reasoned, not
measured**. §14 and §19 both flag a confirmatory local build (with
`--include-qa-chunks`, comparing chunk `embedding_text_hash` across two
publications) as a required Phase-1 validation step before relying on
this family's stability in production.

## 6. Classification per family

| family | classification | why |
|---|---|---|
| `passage_comparisons` | **SHAREABLE_WITH_VERSION_KEY** | Identity = `source_alignment_id` + alignment-algorithm version. Measured 100% stable across 3 real releases including both that shipped to production. No dependency on governance/financial-condition/language-signal code (confirmed by trace, `publisher.py:823-892`). |
| `retrieval_contexts` | **SHAREABLE_WITH_VERSION_KEY** | Identity = `source_alignment_id`/`source_passage_id` + side + alignment version + passage-classification version. Measured 100% stable across the same 3 releases. |
| `retrieval_context_language_categories` / `_risk_subcategories` | **SHAREABLE_WITH_VERSION_KEY** | Pure children of `retrieval_contexts`' identity; same measured stability (matched via the parent context's content hash, which embeds the same signal-tag-derived category set). |
| `passage_language_signals` | **SHAREABLE_WITH_VERSION_KEY** | Identity = source signal/hit id + category/subcategory + language-signal-extraction version. Measured 100% stable across 3 releases, **including the governance and financial-condition releases themselves** — the raw per-passage category hit rows did not change; only the downstream `app.language_metrics`/`app.report_comparisons` aggregation (a different, correctly-still-publication-scoped layer) changed. This directly contradicts the brief's stated premise for §16 ("Governance changes did require new language signal outputs") for *this specific local dataset and these specific two releases* — flagged explicitly, not silently overridden (see §16). |
| `qa_chunks` / `qa_chunk_passages` | **SHAREABLE_WITH_VERSION_KEY, pending one confirmatory build** | Strong architectural case (deterministic builder, zero dependency on the three other families' inputs, identity = report + chunk index + chunking config + embedding model/revision) but **not locally measured at the row/content level** — every local publication was built with `--skip-qa-chunks`. Downgrade to `MORE_EVIDENCE_NEEDED` would be defensible; classified here as `SHAREABLE_WITH_VERSION_KEY` because the code-path evidence is unusually strong (a determinism unit test plus a full trace showing zero coupling to the other three families), but §14/§19 require the confirmatory build before this family is relied upon in the migration. |

None of the seven qualify as `SAFE_TO_SHARE_NOW` in the unconditional
7E.1 sense (that classification was reserved for `passages`/
`passage_embeddings`, which are pure copies of upstream data with no
release-specific code in their path at all) — every family here is a
**code output**, so a real version axis is required even though it
happened to be stable across every release tested. None require
`SHAREABLE_WITH_CONTENT_HASH` as the *primary* mechanism (a version key
is sufficient and cheaper to reason about, since each family's content is
a deterministic function of its stated version inputs) — but a content
hash is still recommended as a **defensive equality check at build time**
(§7), catching the case where a version bump was forgotten even though
code actually changed, rather than as the identity mechanism itself.

## 7. Proposed storage model

New schema `app_artifacts` (parallel to `app_corpus`), one table per
family, keyed by `labels.derive_id(<version-sentinel>, table, *parts)` —
the same `derive_id` function 7E.1 already repurposed, but with a
**real, per-family, bumpable version string** in the `publication_version`
slot instead of a fixed sentinel like `CORPUS_SCOPE`. This is the
concrete form of the "second versioning axis" 7E.1 flagged as missing.

New version constants (proposed, none exist today — see §4):

```python
ALIGNMENT_ARTIFACT_VERSION = "alignment_v1"       # passage_comparisons, retrieval_contexts identity component
LANGUAGE_SIGNAL_ARTIFACT_VERSION = "signals_v1"   # passage_language_signals
QA_CHUNKING_ARTIFACT_VERSION = "qa_chunk_v1"      # qa_chunks/qa_chunk_passages, combined with embedding_model/revision (already tracked per-row)
```

| table | primary key | stable/source key | version/hash key | publication reference strategy | notable FKs | uniqueness |
|---|---|---|---|---|---|---|
| `app_artifacts.passage_comparisons` | `id` (`derive_id(ALIGNMENT_ARTIFACT_VERSION, "passage_comparisons", source_alignment_id)`) | `source_alignment_id` | `alignment_artifact_version` column | none (shared) | `earlier_passage_id`/`later_passage_id` → `app_corpus.passages` (source-keyed, not publication-keyed) | `(source_alignment_id, alignment_artifact_version)` |
| `app_artifacts.retrieval_contexts` | `id` (`derive_id(ALIGNMENT_ARTIFACT_VERSION, "retrieval_contexts", source_alignment_id_or_passage_id, side, context_type)`) | `source_alignment_id`/`source_passage_id` + `report_side` + `context_type` | `alignment_artifact_version` | none (shared) | `passage_embedding_id` → `app_corpus.passage_embeddings`; `passage_comparison_artifact_id` → `app_artifacts.passage_comparisons` | `(source_key, report_side, context_type, alignment_artifact_version)` |
| `app_artifacts.retrieval_context_language_categories` / `_risk_subcategories` | same pattern, child of the row above | parent key + category/subcategory | inherits parent's version | none (shared) | → `app_artifacts.retrieval_contexts` | `(retrieval_context_artifact_id, category)` / `(..., subcategory)` |
| `app_artifacts.passage_language_signals` | `id` (`derive_id(LANGUAGE_SIGNAL_ARTIFACT_VERSION, "passage_language_signals", source_signal_id, category, subcategory)`) | `source_signal_id` (research row id) + category/subcategory | `language_signal_artifact_version` | none (shared) | `passage_comparison_artifact_id` → `app_artifacts.passage_comparisons` | `(source_signal_id, category, subcategory, language_signal_artifact_version)` |
| `app_artifacts.qa_chunks` / `qa_chunk_passages` | `id` (`derive_id(QA_CHUNKING_ARTIFACT_VERSION, "qa_chunks", source_report_id, chunk_index, embedding_model, embedding_model_revision)`) | `source_report_id` + `chunk_index` | `qa_chunking_artifact_version` + `embedding_model`/`embedding_model_revision` (already-tracked columns) | none (shared) | member rows → `app_corpus.passages` | `(source_report_id, chunk_index, qa_chunking_artifact_version, embedding_model, embedding_model_revision)` |

Thin per-publication membership layer, mirroring 7E.1's treatment of
`app.passages` (kept as a real per-publication row for genuinely
per-publication columns, with `text` nullable and resolved via
`app_corpus`): `app.passage_comparisons`, `app.retrieval_contexts`,
`app.passage_language_signals`, `app.qa_chunks`/`app.qa_chunk_passages`
**keep their existing `id` scheme** (`derive_id(publication_version,
...)`) so every existing FK in the `app` schema (e.g.
`app.passage_language_signals.passage_comparison_id →
app.passage_comparisons.id`) is untouched, but their bulk content
columns are dropped/left nullable and replaced by one FK column pointing
at the matching `app_artifacts.*` row. `app.current_*` views are
redefined (`CREATE OR REPLACE VIEW`, same output shape) to join through
that FK, exactly the same technique already proven for
`app.current_passages`/`app.current_passage_embeddings`.

`Publication` gains three new columns recording which artifact version
each family was built against (`alignment_artifact_version`,
`language_signal_artifact_version`, `qa_chunking_artifact_version`) —
the per-family analogue of today's monolithic `source_configuration_hash`,
so a rollback or audit can answer "which artifact generation does this
publication actually use" without inspecting individual rows.

## 8. Immutability / reproducibility

Each `app_artifacts.*` row's id is a pure function of (source content
key, family version) — never of `publication_version` — so it is
immutable in exactly the sense `app_corpus.*` rows already are.
Publication P1, built while `alignment_artifact_version = "alignment_v1"`,
writes thin `app.passage_comparisons` rows whose FK points at
`app_artifacts.passage_comparisons` rows keyed under `"alignment_v1"`.
If a later alignment-algorithm change bumps the constant to
`"alignment_v2"`, a new build computes a **new** family of
`app_artifacts.passage_comparisons` ids (different `derive_id` input) —
it can never overwrite or reuse P1's rows, because the version string is
baked into the id itself, the same guarantee `derive_id` already gives
`publication_version`-keyed rows today. P1's thin rows and their FK
pointers are never touched by a later build; P1 continues to resolve to
exactly the `"alignment_v1"` generation forever, through `current_*`
views scoped by `publication_id`, unless P1 itself is deleted (§9/§10).

## 9. Rollback safety

Rollback (`activate_publication`, `publisher.py:1486-1509`) flips
`ApplicationState.active_publication_id` back to an older, still-`READY`/
`SUPERSEDED` publication — it touches no content rows at all today, and
this design changes nothing about that. The rolled-back-to publication's
thin `app.retrieval_contexts`/`app.passage_comparisons`/`app.qa_chunks`/
`app.passage_language_signals` rows still exist (cleanup only removes
rows belonging to publications outside the `keep` window, never the one
being rolled back to, by definition), and each still points at its
original `app_artifacts.*` generation via the FK from §7 — the same
generation it always pointed at, since that FK is never rewritten after
a row is created. `app.current_*` views re-resolve immediately through
`application_state.active_publication_id`, joining each publication's
thin rows to their own artifact generation — a newer artifact generation
created for a subsequent publication is a separate row set under a
different version-keyed id and is never read by the rolled-back
publication's views. This is the direct analogue of 7E.1's own §8
functional-parity check (rollback tested there against
`passages`/`passage_embeddings`; the same join shape applies here).

## 10. Garbage collection

Extends `gc_orphaned_corpus_rows`'s reference-counting pattern
(`publisher.py:1529-1583`) rather than replacing it. For each
`app_artifacts.*` table, a generation (identified by its version-keyed
`id`) is deletable only when `NOT EXISTS` any `app.<family>` row (across
**every** publication currently retained, not just the active one) whose
FK points at it — the same `NOT EXISTS` correlated-subquery shape
already used for `orphaned_embeddings`/`orphaned_passages`
(`publisher.py:1556-1574`), extended to four more FK columns. This must
run **after** `cleanup_publications` (which removes old publications'
thin rows first, the same ordering 7E.1 already documents as a runbook
step, `publisher.py:1512-1526`) so the reference count reflects only
publications actually still retained — never a time-based or
generation-age-based deletion rule, matching the brief's explicit
instruction.

## 11. Build lifecycle feasibility

Feasible with the current `PublicationBuilder` architecture with no
change to its overall shape. The exact pattern this design needs already
exists for `passage_embeddings`: `publisher.py:790-819` looks up
`existing_corpus_embeddings` by a source-derived key
(`(passage.id, embedding_run.model_name, embedding_run.model_revision)`),
reuses the row if found, and only constructs+inserts a new
`CorpusPassageEmbedding` if not. The proposed build step for each of the
five families is the identical shape: before constructing an
`app_artifacts.*` row, look up by its `derive_id`-computed key in a
per-build dict (or a single `SELECT ... WHERE id = ANY(...)` batch
lookup, cheaper than the embedding case's per-row dict since these keys
are computed, not queried, up front); reuse if the row already exists,
skip construction entirely; otherwise build and insert once. Every
`_build_rows` loop that constructs these five families
(`publisher.py:823-892`, `:1000-1170`, `:1174-1305`, `:1309-1424`)
already iterates in the right order and already has every source id it
needs in scope — the change is additive (existence-check before insert,
FK-instead-of-inline-content on the thin row), not a restructuring of the
method's control flow. Steps 5-7 of the brief's lifecycle (validate,
promote, GC unreferenced generations later) require zero change:
`validate_persisted`, `activate_publication`, and the extended
`gc_orphaned_corpus_rows` from §10 all already operate at the level of
"does a row exist / is it referenced," which is unaffected by whether the
row's content lives inline or behind an artifact FK.

## 12. Storage modeling (production numbers, from `docs/production-storage-audit-7f7a3.md`)

Baseline: 432MB steady state, 80MB headroom, single `ACTIVE` publication.
Per-family production sizes (table+index): `retrieval_contexts` 58MB +
`retrieval_context_language_categories` 34MB +
`retrieval_context_risk_subcategories` (folded into the audit's "~2.4MB
combined" bucket, immaterial) ≈ **92MB**; `passage_comparisons` **33MB**;
`qa_chunks` 75MB + `qa_chunk_passages` 14MB ≈ **89MB**;
`passage_language_signals` **66MB**. Sum of these four families ≈
**280MB** of the ~304MB `app` schema (matches the audit's own §10
figure). The remaining ~24MB (`companies`, `reports`,
`report_comparisons`, `language_metrics`, `discovery_items`,
`metric_definitions`, `metric_label_thresholds`, narrative/structured
comparison tables) is genuinely, unavoidably per-publication — small, and
out of scope for sharing (correctly so: it encodes this publication's own
percentile bands and aggregation, not a stable source-derived output).

| scenario | families shared | steady-state size (unchanged, 1 pub already active) | new build's duplicated layer | transient peak | headroom at peak (512MB cap) | fits? |
|---|---|---|---|---|---|---|
| A. current architecture | none | 432MB | ~300MB | **~732MB** | **−220MB** | No |
| B. share QA only | qa_chunks+qa_chunk_passages (−89MB) | 432MB | 211MB | 643MB | −131MB | No |
| C. share retrieval contexts only | retrieval_contexts+children (−92MB) | 432MB | 208MB | 640MB | −128MB | No |
| D. share language signals only | passage_language_signals (−66MB) | 432MB | 234MB | 666MB | −154MB | No |
| E. share passage_comparisons only | passage_comparisons (−33MB) | 432MB | 267MB | 699MB | −187MB | No |
| F. share all four safe families | all of A-D combined (−280MB) | 432MB | **~24MB** | **456MB** | **+56MB** | **Yes** |

No single-family scenario closes the gap — even sharing the single
largest family (retrieval contexts, 92MB) still leaves a ~208MB
duplicated layer against only 80MB of headroom. §13 works out the
minimal *combination* short of all four.

## 13. ROI / risk prioritization and the minimal viable combination

| family | current MB (prod) | measured reusable % | engineering complexity | migration risk | rollback risk | MB saved if shared |
|---|---|---|---|---|---|---|
| `retrieval_contexts` (+children) | 92 | 100% (measured, 3 releases) | moderate — 3 tables, 2 FK redirections (`passage_embedding_id` already indirect per 7E.1, `passage_comparison_id` needs the same treatment) | low — same proven `derive_id`+view-redirect pattern as 7E.1 | low — same rollback argument as §9 | 92 |
| `qa_chunks` (+`qa_chunk_passages`) | 89 | reasoned, not measured (§5 gap) | low — fully decoupled builder already, no cross-family dependency to redirect | low, **pending** the confirmatory build (§14/§19) | low | 89 |
| `passage_language_signals` | 66 | 100% (measured, 3 releases, including governance) | moderate — highest row count (54,003 locally / 32,823 in prod), one extra FK hop through `passage_comparisons` artifact id | low | low | 66 |
| `passage_comparisons` | 33 | 100% (measured, 3 releases) | low — smallest of the four, and a dependency every other family already needs redirected anyway (`retrieval_contexts`/`passage_language_signals` both FK to it) | low | low | 33 |

Per §12, no subset smaller than three families reaches a positive
transient-peak headroom: sharing `retrieval_contexts` + `qa_chunks` +
`passage_language_signals` (92+89+66 = 247MB reused) leaves a duplicated
layer of `300 − 247 = 53MB`, peak `432 + 53 = 485MB`, headroom **+27MB**
— the smallest architectural change that gets the build under the 512MB
cap at all. Adding `passage_comparisons` (the cheapest, smallest, and a
dependency the other three already need redirected) brings the duplicated
layer down to ~24MB, peak 456MB, headroom **+56MB** — for materially more
margin at low incremental engineering cost, since its FK redirection is
already required work for the other three families' migration either way.

**Neither combination reaches the brief's stated ≥100MB target.** That
target is unreachable purely through artifact sharing given production's
own already-tight 80MB baseline headroom (§12/§20) — see §21 for the
explicit reconciliation.

## 14. QA chunks special review

- **Did QA chunk content actually change in 7F.5/7F.7a?** Not measurable
  locally — every local publication used `--skip-qa-chunks` (§5 gap).
  Architecturally, no: `publisher.py:1309-1424` never reads
  `cd.language_features`, `cd.category_hits_by_signal_id`, or any
  governance/financial-condition-related field; it reads only
  `snapshot.passages_by_report`, corpus passage text/heading, and page
  numbers.
- **Should governance/financial-condition changes have required QA chunk
  regeneration at all?** No — there is no code path connecting them.
  Regeneration happened only because `publication_version` is global
  (§4), not because QA chunk content depends on those changes.
- **Can QA chunk identity be independently versioned?** Yes — proposed in
  §7 (`QA_CHUNKING_ARTIFACT_VERSION` + existing `embedding_model`/
  `embedding_model_revision` columns, which already carry the only two
  things that can legitimately change chunk content).
- **Does `publish --skip-qa-chunks` avoid storage allocation or only
  regeneration?** **Storage allocation.** `publisher.py:1321-1322`: when
  `include_qa_chunks=False`, the `for report_source_id, passage_datasets
  in ... if self.include_qa_chunks else ()` loop iterates zero times —
  no `AppQaChunk`/`AppQaChunkPassage` ORM objects are ever constructed,
  so zero rows are written for this family at all (confirmed: all four
  local publications show `0` rows for both tables, §5). This means
  `--skip-qa-chunks` is **not** evidence of a stable, reusable chunk
  layer — it is evidence of an *empty* one; the family's storage cost
  only shows up when a build actually includes chunks, which is why
  production (built without `--skip-qa-chunks`) carries the full 89MB
  and local test builds do not.
- **Easiest high-value decoupling?** Yes, in engineering-complexity terms
  (§13: lowest complexity of the three non-trivial families, no
  cross-family FK dependency to redirect) — but it is also the one family
  this track cannot certify as measured-stable. Recommended treatment:
  build the migration for all four together per §19, but run the
  confirmatory build (two `--include-qa-chunks` local publications,
  compare `embedding_text_hash` per `(report_id, chunk_index)`) as an
  explicit Phase-1 gate specifically for this family before Phase 4
  (publisher starts writing shared QA-chunk artifacts) is enabled for it.

## 15. Retrieval context special review

- **What actually invalidates them?** Per §2's trace, their content is a
  function of the alignment output (`PassageComparison`/
  `PassageAlignment`) and passage-classification flags — not of
  governance/financial-condition config, and not of the percentile-band/
  metric-label layer.
- **Do governance metric changes affect them?** No — measured 100%
  identical across the `7f4-local-validation-1` (financial-condition) →
  `7f7a1-local-1` (governance) transition, real local data (§5).
- **Byte-identical across recent releases?** Yes, confirmed via
  content-hash comparison keyed by `source_alignment_id`/
  `source_passage_id` + `report_side` + `context_type` (§5) — 34,099/34,099
  matched, 0 changed, 0 missing, across both the fincond→governance
  transition and the governance rebuild.
- **Can they be independently versioned/reused?** Yes — §7's design.

## 16. Language signal special review

- **"Governance changes did require new language signal outputs" —
  checked against local evidence, and contradicted for the specific
  releases available locally.** `passage_language_signals` rows,
  including `category = 'governance'` rows, were measured **100%
  byte-identical** between `7f4-local-validation-1` (pre-governance) and
  `7f7a1-local-1` (post-governance), 54,003/54,003 matched (§5). Tracing
  why: the governance *category hits* (`cd.category_hits_by_signal_id`
  with `hit.category == 'governance'`) come from the research-side
  language-signal pipeline, which had presumably already computed
  governance hits before Track 7F.7a.1 shipped — what Track 7F.7a.1
  actually added was the **downstream aggregation**:
  `app.language_metrics` rows with `population="governance_subcategory"`
  (`publisher.py:1148-1170`) and the `governance_*` fields on
  `app.report_comparisons` (`publisher.py:561-576`). Those two are
  correctly *not* part of this track's shareable-family list — they are
  genuinely a function of this publication's own eligible population
  (percentile bands recomputed per build, `publisher.py:395-458`) and
  remain publication-scoped by design, matching 7E.1's own reasoning.
- **Must the entire table regenerate when only one derived metric family
  changes?** With the current architecture, yes (single global
  `publication_version`). With §7's design, no — `passage_language_signals`
  as a raw-signal family is fully decoupled from which metric families
  are currently displayed.
- **Can signals be versioned at signal-family/category level?** The
  proposed `language_signal_artifact_version` is a single version string
  for the whole family, not per-category, deliberately — per-category
  versioning was considered and rejected as overengineering: the
  measured evidence (§5, 3 releases, 0% divergence) gives no signal that
  categories change independently of each other in practice, and a
  single version string is far simpler to reason about for GC/rollback
  (§9/§10). If real evidence later shows one category's extraction logic
  changing independently, category-level versioning is a incremental,
  backward-compatible follow-up (the id already includes `category`/
  `subcategory` as parts, so per-category version bumps are mechanically
  possible without a schema change).
- **Can existing rows be reused for unchanged signal families?** Yes,
  automatically, under the build-lifecycle reuse-check in §11.

## 17. Passage comparison special review

- **Did recent financial-condition/governance releases actually change
  them?** No — measured 100% identical across all three real local
  transitions tested (§5): 23,279/23,279 matched, 0 changed, in every
  pair, including both releases that shipped to production.
- **Exact version key permitting reuse:** `source_alignment_id` +
  `alignment_artifact_version` (§7) — passage comparisons depend only on
  the alignment engine's output, which financial-condition/governance
  work never touches.

## 18. Alternative: lifecycle change instead of shared artifacts

Considered, not implemented, per the brief.

**Option: mutate/rebuild the inactive publication layer in place.**
Instead of always creating a brand-new `Publication` row and a full new
set of publication-scoped rows, a new build could `UPDATE` an existing
non-`ACTIVE` publication's rows in place (or truncate-and-rebuild just
that publication's own row set) before promoting it.

- **Downtime risk:** low if done to a non-`ACTIVE` publication (readers
  are unaffected, since `current_*` views resolve through
  `application_state.active_publication_id`, and the in-place-mutated
  publication isn't active yet) — but requires holding that publication
  in a non-terminal status for the duration of the rebuild, during which
  it cannot be used as a rollback target either (its rows are mid-mutation).
- **Rollback loss:** real. Today, a `SUPERSEDED` publication is a
  complete, byte-for-byte-frozen rollback target
  (`activate_publication` just flips the pointer). In-place mutation of
  an inactive publication **destroys** its own rollback value the moment
  the rebuild starts — there is no longer a second, independent frozen
  copy to fall back to if the *new* build's own data turns out to be bad,
  only the currently-`ACTIVE` one. This directly weakens the guarantee
  Track 7E.3/7E.4's blue/green cutover design and this project's
  "publication immutability" goal (stated explicitly in this track's own
  brief) were built around.
- **Validation safety:** compromised in the same way — `validate_persisted`
  currently runs against a freshly-built, fully-isolated `Publication`;
  running it against a row set that's being mutated in place introduces
  a window where the publication is neither the old, known-good state nor
  the new, validated state.
- **Partial-build failure risk:** materially worse. Today, a failed build
  simply marks a *new* `Publication` row `FAILED` and leaves every other
  publication untouched (`publisher.py:285-292`). In-place mutation of an
  existing publication's rows means a failed rebuild leaves that
  publication in an **inconsistent, partially-mutated state** with no
  clean "this publication's data is exactly what it was before" recovery
  path — a strictly worse failure mode than today's.
- **Complexity:** deceptively simple to describe, substantially harder to
  implement correctly (transactional partial-update semantics across
  seven tables with FK dependencies, versus today's insert-only build).

**Option: temporarily retire the current publication before building.**
Would free ~304MB before the build starts, fitting comfortably under the
cap — but leaves production with **zero** active publication (a hard
outage, not a rollback risk) for the duration of the build, which for a
~300MB publication with QA-chunk re-embedding is not a short window. This
directly contradicts the project's stated blue/green goal (`docs/7e3-fresh-neon-production-cutover.md`'s
own reason for existing) and is a strictly worse choice than the shared-
artifact design for any of the metrics the brief cares about (downtime,
rollback safety, partial-build-failure blast radius).

**Conclusion: do not recommend lifecycle weakening.** Both lifecycle
variants trade a well-understood, already-tested storage problem for a
newly-introduced availability/rollback-safety problem, for a project
whose CLAUDE.md domain rules and this track's own brief explicitly
prioritize reproducibility and publication immutability. The versioned
shared-artifact design (§7) achieves the same storage reduction (§12)
without touching either guarantee.

## 19. Migration strategy

Mirrors 7E.1's own phased, additive-only approach
(`docs/7e1-publication-storage-lifecycle-hardening.md` §5), extended to
four families instead of two:

1. **Phase 1 — create shared tables/version identities.** New
   `app_artifacts` schema + five tables (§7) + the three new version
   constants (§7) + three new `Publication` columns recording which
   artifact version each publication used. Additive migration, no
   existing table touched. **Gate:** run the qa_chunks confirmatory build
   from §14 before enabling Phase 4 for that family specifically — the
   other three families already have the measured evidence (§5) to
   proceed without an extra gate.
2. **Phase 2 — backfill from the ACTIVE publication.** Same
   Postgres-to-Postgres, payload-never-touches-Python discipline 7E.1
   used for `passages`/`passage_embeddings` (`docs/7e1...md` §5 step 4):
   one server-side `INSERT ... SELECT` per new table, computing each
   row's deterministic `app_artifacts` id from the active publication's
   existing source keys.
3. **Phase 3 — dual-read/compatibility views.** Redefine
   `app.current_retrieval_contexts`/`app.current_passage_comparisons`/
   `app.current_qa_chunks`/`app.current_passage_language_signals` (and
   the two retrieval-context child views) to `COALESCE` between the thin
   row's own (pre-migration) inline content and the new
   `app_artifacts`-joined content, exactly the pattern
   `app.current_passages` already uses for `text`
   (`COALESCE(t.text, cp.text)`) — so a pre-migration publication that
   still has its own fully-populated content columns needs no backfill
   to keep working.
4. **Phase 4 — publisher writes shared artifacts.** `_build_rows`'
   construction sites for these five families gain the existence-check-
   before-insert pattern already proven for `passage_embeddings`
   (§11), and thin `app.*` rows drop their bulk content columns going
   forward (nullable, never backfilled for old rows — matches 7E.1's
   "leaves `NULL` from this migration onward" choice for `app.passages.text`).
5. **Phase 5 — verify.** Repeat this track's own §5/§8-style checks
   against a real new build: row counts, content-hash equality between
   the shared-artifact reads and the pre-migration inline reads for the
   still-active old-format publication, `build → validate → promote →
   rollback` end-to-end (the exact sequence 7E.1 §8 already exercised),
   and a retrieval-performance benchmark for the new join shape
   (`postgres-semantic-retrieval-repository.ts`'s existing queries,
   unmodified, per 7E.1's own §9 methodology) — this design adds one more
   join hop per family (`app.retrieval_contexts` → its artifact row) on
   top of 7E.1's already-benchmarked `app.current_passages` →
   `app_corpus.passages` hop; re-benchmarking rather than assuming safety
   is the same discipline 7E.1 applied.
6. **Phase 6 — stop writing duplicate publication-scoped copies.** Once
   verified, `_build_rows` no longer constructs the (now-unused) inline
   content columns at all for new builds.
7. **Phase 7 — remove legacy inline columns, later.** Drop the
   now-permanently-`NULL`/unused inline content columns from the five
   thin `app.*` tables in a subsequent, separate migration, once no
   pre-migration publication that relies on them remains retained
   (`cleanup_publications` will eventually retire them naturally under
   normal `keep` policy) — no destructive migration in the same release,
   per the brief.

## 20. Production deployment blocker: minimum change to unblock governance

Per §12/§13, the minimum architecture change that gets a new build's
transient peak under the 512MB cap **at all**, given production's
measured 432MB steady state and 80MB headroom, is sharing at least three
of the four families — specifically `retrieval_contexts` + `qa_chunks` +
`passage_language_signals` (the three largest; §13's 247MB-of-280MB
combination), yielding a peak of ~485MB and **+27MB** headroom.
`passage_comparisons` alone, or any other single family, is insufficient
(§12, scenarios B-E all remain negative). Given `passage_comparisons`'s
low incremental engineering cost (§13 — its FK redirection is required
work for the other three regardless, since both `retrieval_contexts` and
`passage_language_signals` FK to it), including it in the same phase 1
(all four families, §12 scenario F: ~456MB peak, +56MB headroom) is
recommended over the bare three-family minimum, for materially more
safety margin at negligible extra scope. Neither combination reaches the
brief's own ≥100MB target — see §21's explicit reconciliation of that
gap.

## 21. Final recommendation

**SHARE_MULTIPLE_ARTIFACT_FAMILIES**

- **Exact families, phase 1:** all four — `retrieval_contexts` (+
  `retrieval_context_language_categories`/`_risk_subcategories`),
  `qa_chunks` (+ `qa_chunk_passages`), `passage_language_signals`,
  `passage_comparisons` — per §7's design, migrated together via §19's
  seven phases, with the qa_chunks-specific confirmatory-build gate from
  §14 applied before Phase 4 is enabled for that one family.
- **Estimated storage saved:** the current architecture's per-build
  duplicated layer drops from ~300MB to ~24MB (§12, scenario F) — a
  ~276MB reduction in what every future build must duplicate before
  promotion, permanently, for as long as these families' content remains
  stable under their own version axes (not merely a one-time cleanup).
- **Expected new transient peak:** ~456MB (432MB current steady state +
  ~24MB genuinely-per-publication layer), **+56MB headroom** under the
  512MB cap — down from the current architecture's projected ~732MB
  peak (**−220MB** headroom, i.e. does not fit at all).
- **Engineering scope:** one new schema (5 tables), 3 new version
  constants + 3 new `Publication` columns, existence-check-before-insert
  added to 5 already-identified construction sites in
  `_build_rows` (mirroring a pattern already proven for
  `passage_embeddings`), `current_*` view redefinitions for 6 views
  (retrieval_contexts + 2 children, passage_comparisons, qa_chunks +
  qa_chunk_passages, passage_language_signals), extended
  `gc_orphaned_corpus_rows`, and one confirmatory local build+comparison
  specifically for `qa_chunks` before relying on it. Comparable in shape
  and size to Track 7E.1's own shipped scope (2 tables there vs 5 here,
  same techniques throughout).
- **Rollout risk:** low, by the same reasoning 7E.1 used and this track
  re-verified: every family's stability was measured (not assumed) across
  real production code changes for three of the four; the fourth
  (`qa_chunks`) has a required, cheap, explicit verification gate rather
  than being taken on faith. The design changes zero web-facing queries
  (§2's consumer trace confirms every read goes through `current_*`
  views only) and preserves every immutability/rollback guarantee (§8/§9),
  unlike the rejected lifecycle-weakening alternative (§18).
- **Is it enough to resume governance production deployment?** **Yes, to
  get a new build under the 512MB cap at all (§20)** — but explicitly
  **not** to the brief's own stated ≥100MB comfort margin. Production's
  baseline headroom (80MB) is simply too tight for any purely-artifact-
  sharing fix to clear that bar on its own: even sharing all four
  families and reducing the duplicated layer to its practical floor
  (~24MB, the genuinely-per-publication layer that can never be shared)
  yields only +56MB. Reaching the brief's ≥100MB target requires pairing
  this architectural change with **one** of: (a) a temporary Neon
  storage-cap increase for the duration of future build/promote/cleanup
  cycles (removes the constraint without weakening any guarantee — the
  cleanest complement), or (b) further shrinking the ~24MB
  genuinely-per-publication layer itself (e.g., dropping the confirmed-
  dead `app.passage_embeddings` table, §8 of the production audit — 56KB,
  immaterial on its own, but indicative that this layer has not yet been
  audited as tightly as the four shared families now have been). Recommend
  (a) as the pragmatic unblock for the pending governance deployment,
  with this track's design as the durable, permanent fix for every build
  after that.

## 22. Documentation

This file (`docs/versioned-shared-publication-artifacts-design-7f7a4.md`)
covers all 22 sections of the brief. No production code, schema, or data
was modified in the course of producing it.

## Correction (Track 7F.7a.4a)

**This document's §12/§20/§21 ~456MB post-migration estimate describes
the destination architecture's steady state — it does not establish that
the proposed Phase 2 in-place backfill (§19) itself fits under the 512MB
cap.** Phase 2 requires the ~280MB of shareable-family content to be
written into `app_artifacts` **while** the existing publication's inline
copies of the same content remain in place (by this document's own
additive-migration discipline, §19 Phase 3/4/6/7 don't remove the old
inline data until *after* Phase 2 has already completed). Modeled against
the current 432MB production baseline, that is a ~712MB transient peak —
about 200MB over the cap, not close to fitting. See
`docs/shared-artifact-migration-bootstrap-7f7a4a.md` §1 for the
phase-by-phase model and §8 for the resulting recommendation
(`FRESH_NEON_CUTOVER_REQUIRED`, analogous to `docs/7e3-fresh-neon-production-cutover.md`,
rather than the in-place migration this document's §19 originally
proposed). That document also quantifies a second, independent finding
not covered here: even after a successful cutover to the shared-artifact
architecture, a future release that bumps any single family's artifact
version (language-signal, alignment, or QA-chunk — not just all four at
once) can already exceed 512MB on steady-state math alone, so this
design's long-run safety depends on disciplined retention/GC policy, not
on artifact-sharing by itself.
