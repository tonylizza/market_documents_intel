/**
 * Milestone 7B.1a retrieval-evaluation runner. Executes the real (83-case)
 * dataset against the real, live corpus and the real query-embedding
 * service -- a script (`tsx --tsconfig evaluation/tsconfig.json
 * evaluation/run-evaluation.ts`), not a unit test: it requires
 * `APP_READONLY_DATABASE_URL` and `QUERY_EMBEDDING_SERVICE_URL` pointed at
 * a running Postgres + embedding service.
 *
 * Runs every case through BOTH the "no remediation" baseline
 * (`IdentitySemanticReranker`) and the shipped remediation
 * (`QualityAdjustedSemanticReranker`) using the *same* raw candidates and
 * *same* query embedding for both (one DB/embedding round trip per
 * case/mode, not two) -- so the before/after comparison is exact, not
 * approximated by re-querying.
 *
 * Writes `evaluation/results/publication_retrieval_evaluation.csv`
 * (per-case, per-mode, per-reranker-variant metrics) and prints an
 * aggregate summary, per-category breakdown, short-fragment/weak-match
 * analysis, and a default-search-mode recommendation to stdout.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { PostgresPassageRepository } from "../lib/repositories/postgres-passage-repository";
import { PostgresSemanticRetrievalRepository } from "../lib/repositories/postgres-semantic-retrieval-repository";
import { HttpQueryEmbeddingProvider, loadHttpQueryEmbeddingProviderConfig } from "../lib/services/query-embedding-provider";
import { parsePassageSearchParams } from "../lib/services/passage-search-params";
import { reciprocalRankFusion } from "../lib/services/rrf";
import { closePool } from "../lib/db/pool";
import { IdentitySemanticReranker, QualityAdjustedSemanticReranker, type SemanticReranker } from "../lib/services/semantic-reranker";
import { computePassageQualityFeatures, SUBSTANTIVE_WORD_COUNT_THRESHOLD } from "../lib/services/passage-quality";
import { decideDefaultSearchMode } from "./default-mode-rule";
import { RETRIEVAL_EVALUATION_DATASET, type RetrievalEvaluationCase } from "./dataset";
import {
  aggregateMetrics,
  computeCaseMetrics,
  irrelevantShortFragmentRateAtK,
  meanOf,
  rateAtOrAboveThreshold,
  rateBelowThreshold,
  shortFragmentRateAtK,
  substantivePrecisionAtK,
  type CaseMetrics,
  type RelevanceGrade,
} from "./metrics";

const VARIANTS = ["baseline", "remediated"] as const;
type Variant = (typeof VARIANTS)[number];
const VECTOR_MODES = ["exact", "hnsw"] as const;

const RERANKERS: Record<Variant, SemanticReranker> = {
  baseline: new IdentitySemanticReranker(),
  remediated: new QualityAdjustedSemanticReranker(),
};

function gradedMap(testCase: RetrievalEvaluationCase): Map<string, RelevanceGrade> | undefined {
  if (!testCase.gradedRelevance) return undefined;
  return new Map(Object.entries(testCase.gradedRelevance));
}

function buildParams(testCase: RetrievalEvaluationCase) {
  return parsePassageSearchParams({
    q: testCase.query,
    phrase: testCase.exactPhrase ? "1" : undefined,
    company: testCase.filters?.company ?? undefined,
    periodStart: testCase.filters?.periodStart ?? undefined,
    periodEnd: testCase.filters?.periodEnd ?? undefined,
    status: testCase.filters?.alignmentStatus ?? undefined,
    category: testCase.filters?.category ?? undefined,
    subcategory: testCase.filters?.subcategory ?? undefined,
    rsQuality: testCase.filters?.reportSideQuality ?? undefined,
  });
}

interface CaseRow {
  caseId: string;
  category: string;
  variant: Variant;
  mode: string;
  recallAt5: number;
  recallAt10: number;
  precisionAt5: number;
  substantivePrecisionAt5: number;
  mrr: number;
  ndcgAt10: number | null;
  shortFragmentRateAt5: number | null;
  shortFragmentRateAt10: number | null;
  irrelevantShortFragmentRateAt5: number | null;
  topSimilarity: number | null;
  filterAccurate: boolean | null;
}

async function main() {
  const passageRepo = new PostgresPassageRepository();
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);

  const rows: CaseRow[] = [];
  // keyed by variant -> similarity list
  const noAnswerSimilarities: Record<Variant, number[]> = { baseline: [], remediated: [] };
  const answerableSimilarities: Record<Variant, number[]> = { baseline: [], remediated: [] };
  let duplicateContextCases = 0;
  let groupedContextCompleteCases = 0;
  let groupedContextCasesTotal = 0;
  let providerFailures = 0;
  let citationIncomplete = 0;
  let citationChecked = 0;

  for (const testCase of RETRIEVAL_EVALUATION_DATASET) {
    const params = buildParams(testCase);
    const graded = gradedMap(testCase);
    const relevantSet = new Set(testCase.relevantPassageIds);

    // --- keyword (reranker-independent, computed once) ---
    const lexicalResults = await passageRepo.searchPassages({ ...params, pageSize: 20, page: 1 });
    const lexicalIds = lexicalResults.map((r) => r.passageId);
    const keywordMetrics = computeCaseMetrics(lexicalIds, testCase.relevantPassageIds, graded);
    let filterAccurate: boolean | null = null;
    if (testCase.expectedCompanyTicker) {
      filterAccurate = lexicalResults.every((r) => r.companyTicker === testCase.expectedCompanyTicker);
    } else if (testCase.expectedAlignmentStatus) {
      filterAccurate = lexicalResults.every((r) => r.alignmentStatus === testCase.expectedAlignmentStatus);
    }
    for (const variant of VARIANTS) {
      rows.push({
        caseId: testCase.id,
        category: testCase.category,
        variant,
        mode: "keyword",
        ...keywordMetrics,
        substantivePrecisionAt5: keywordMetrics.precisionAt5,
        shortFragmentRateAt5: null,
        shortFragmentRateAt10: null,
        irrelevantShortFragmentRateAt5: null,
        topSimilarity: null,
        filterAccurate,
      });
    }

    if (testCase.category === "repeated_passage") {
      groupedContextCasesTotal += 1;
      const contexts = await semanticRepo.expandRetrievalContexts(testCase.relevantPassageIds, params);
      if (contexts.length >= 2) groupedContextCompleteCases += 1;
      const seen = new Set<string>();
      for (const c of contexts) {
        const key = `${c.passageId}:${c.passageComparisonId}:${c.reportSide}:${c.contextType}`;
        if (seen.has(key)) duplicateContextCases += 1;
        seen.add(key);
        citationChecked += 1;
        if (!c.passageId || !c.reportId || !c.companyId || c.firstPageNumber == null || c.lastPageNumber == null) {
          citationIncomplete += 1;
        }
      }
    }

    let embedding;
    try {
      embedding = await provider.embedQuery(testCase.query);
    } catch (error) {
      providerFailures += 1;
      console.error(`[embed-query failed] ${testCase.id}: ${(error as Error).message}`);
      continue;
    }

    for (const vectorMode of VECTOR_MODES) {
      const semanticCandidates = await semanticRepo.searchSemanticCandidates(embedding.vector, params, 50, vectorMode);

      // Fragment classification computed once per candidate (reranker-
      // independent structural fact), reused for the short-fragment metrics
      // under both variants.
      const isFragment = new Set(
        semanticCandidates
          .filter((c) => {
            const features = computePassageQualityFeatures({
              heading: c.heading,
              text: c.text,
              wordCount: c.wordCount,
              hasLanguageSignal: c.hasLanguageSignal,
              headingFrequency: c.headingFrequency,
            });
            return (
              features.wordCount < SUBSTANTIVE_WORD_COUNT_THRESHOLD &&
              (features.isHeadingOnlyFragment || features.isRepeatedGenericHeading || features.containsContinued)
            );
          })
          .map((c) => c.passageId),
      );

      const lexicalCandidates = await semanticRepo.searchLexicalCandidates(params, 50);

      for (const variant of VARIANTS) {
        const reranked = RERANKERS[variant].rerank(testCase.query, semanticCandidates);
        const semanticIds = reranked.map((c) => c.passageId);
        const semanticMetrics = computeCaseMetrics(semanticIds, testCase.relevantPassageIds, graded);
        const topSimilarity = semanticCandidates[0]?.similarity ?? null;
        const fragFlags5 = semanticIds.slice(0, 5).map((id) => isFragment.has(id));
        const fragFlags10 = semanticIds.slice(0, 10).map((id) => isFragment.has(id));

        if (vectorMode === "exact" && topSimilarity !== null) {
          if (testCase.category === "no_answer") noAnswerSimilarities[variant].push(topSimilarity);
          if (testCase.relevantPassageIds.length > 0) answerableSimilarities[variant].push(topSimilarity);
        }

        rows.push({
          caseId: testCase.id,
          category: testCase.category,
          variant,
          mode: vectorMode === "exact" ? "semantic_exact" : "semantic_hnsw",
          ...semanticMetrics,
          substantivePrecisionAt5: substantivePrecisionAtK(semanticIds, relevantSet, isFragment, 5),
          shortFragmentRateAt5: shortFragmentRateAtK(fragFlags5, 5),
          shortFragmentRateAt10: shortFragmentRateAtK(fragFlags10, 10),
          irrelevantShortFragmentRateAt5: irrelevantShortFragmentRateAtK(semanticIds, isFragment, relevantSet, 5),
          topSimilarity,
          filterAccurate: null,
        });

        const lexicalRanking = lexicalCandidates.map((c) => ({ id: c.passageId, rankPosition: c.rankPosition }));
        const semanticRanking = reranked.map((c) => ({ id: c.passageId, rankPosition: c.finalRank }));
        const fused = reciprocalRankFusion(lexicalRanking, semanticRanking, 60);
        const hybridIds = fused.map((f) => f.id);
        const hybridMetrics = computeCaseMetrics(hybridIds, testCase.relevantPassageIds, graded);
        const hybridFragFlags5 = hybridIds.slice(0, 5).map((id) => isFragment.has(id));
        const hybridFragFlags10 = hybridIds.slice(0, 10).map((id) => isFragment.has(id));
        rows.push({
          caseId: testCase.id,
          category: testCase.category,
          variant,
          mode: vectorMode === "exact" ? "hybrid_exact" : "hybrid_hnsw",
          ...hybridMetrics,
          substantivePrecisionAt5: substantivePrecisionAtK(hybridIds, relevantSet, isFragment, 5),
          shortFragmentRateAt5: shortFragmentRateAtK(hybridFragFlags5, 5),
          shortFragmentRateAt10: shortFragmentRateAtK(hybridFragFlags10, 10),
          irrelevantShortFragmentRateAt5: irrelevantShortFragmentRateAtK(hybridIds, isFragment, relevantSet, 5),
          topSimilarity: null,
          filterAccurate: null,
        });
      }
    }
  }

  const outDir = path.resolve(__dirname, "results");
  mkdirSync(outDir, { recursive: true });
  const csvHeader =
    "case_id,category,variant,mode,recall_at_5,recall_at_10,precision_at_5,substantive_precision_at_5,mrr,ndcg_at_10,short_fragment_rate_at_5,short_fragment_rate_at_10,irrelevant_short_fragment_rate_at_5,top_similarity,filter_accurate\n";
  const csvBody = rows
    .map((r) =>
      [
        r.caseId,
        r.category,
        r.variant,
        r.mode,
        r.recallAt5.toFixed(4),
        r.recallAt10.toFixed(4),
        r.precisionAt5.toFixed(4),
        r.substantivePrecisionAt5.toFixed(4),
        r.mrr.toFixed(4),
        r.ndcgAt10 !== null ? r.ndcgAt10.toFixed(4) : "",
        r.shortFragmentRateAt5 !== null ? r.shortFragmentRateAt5.toFixed(4) : "",
        r.shortFragmentRateAt10 !== null ? r.shortFragmentRateAt10.toFixed(4) : "",
        r.irrelevantShortFragmentRateAt5 !== null ? r.irrelevantShortFragmentRateAt5.toFixed(4) : "",
        r.topSimilarity !== null ? r.topSimilarity.toFixed(4) : "",
        r.filterAccurate !== null ? String(r.filterAccurate) : "",
      ].join(","),
    )
    .join("\n");
  writeFileSync(path.join(outDir, "publication_retrieval_evaluation.csv"), csvHeader + csvBody + "\n");

  function printAggregate(label: string, subset: CaseRow[]) {
    const aggregate = aggregateMetrics(
      subset.map(
        (r): CaseMetrics => ({
          recallAt5: r.recallAt5,
          recallAt10: r.recallAt10,
          precisionAt5: r.precisionAt5,
          mrr: r.mrr,
          ndcgAt10: r.ndcgAt10,
        }),
      ),
    );
    const fragRates5 = subset.map((r) => r.shortFragmentRateAt5).filter((v): v is number => v !== null);
    const irrelevantFragRates5 = subset.map((r) => r.irrelevantShortFragmentRateAt5).filter((v): v is number => v !== null);
    const subPrecision5 = meanOf(subset.map((r) => r.substantivePrecisionAt5));
    console.log(
      `${label.padEnd(28)} n=${aggregate.caseCount} recall@5=${aggregate.meanRecallAt5.toFixed(3)} ` +
        `recall@10=${aggregate.meanRecallAt10.toFixed(3)} precision@5=${aggregate.meanPrecisionAt5.toFixed(3)} ` +
        `subst.precision@5=${subPrecision5.toFixed(3)} MRR=${aggregate.meanMrr.toFixed(3)} ` +
        `nDCG@10=${aggregate.meanNdcgAt10?.toFixed(3) ?? "n/a"}` +
        (fragRates5.length > 0 ? ` fragRate@5=${meanOf(fragRates5).toFixed(3)} irrelevantFragRate@5=${meanOf(irrelevantFragRates5).toFixed(3)}` : ""),
    );
  }

  console.log("\n=== Baseline (no remediation) vs Remediated -- by mode ===");
  for (const variant of VARIANTS) {
    for (const mode of ["keyword", "semantic_exact", "semantic_hnsw", "hybrid_exact", "hybrid_hnsw"]) {
      printAggregate(`${variant}/${mode}`, rows.filter((r) => r.variant === variant && r.mode === mode));
    }
  }

  console.log("\n=== By query category (remediated, semantic_exact) ===");
  const categories = [...new Set(RETRIEVAL_EVALUATION_DATASET.map((c) => c.category))].sort();
  for (const category of categories) {
    printAggregate(category, rows.filter((r) => r.variant === "remediated" && r.mode === "semantic_exact" && r.category === category));
  }

  console.log("\n=== Semantic-paraphrase subset: keyword vs baseline-semantic vs remediated-semantic (recall@10) ===");
  const paraphraseIds = new Set(
    RETRIEVAL_EVALUATION_DATASET.filter((c) => c.category === "semantic_paraphrase" || c.expectedBehavior === "semantic_favored").map((c) => c.id),
  );
  const kwParaphrase = rows.filter((r) => paraphraseIds.has(r.caseId) && r.mode === "keyword" && r.variant === "baseline");
  const baseSemParaphrase = rows.filter((r) => paraphraseIds.has(r.caseId) && r.mode === "semantic_exact" && r.variant === "baseline");
  const remSemParaphrase = rows.filter((r) => paraphraseIds.has(r.caseId) && r.mode === "semantic_exact" && r.variant === "remediated");
  console.log(
    `keyword recall@10=${aggregateMetrics(kwParaphrase).meanRecallAt10.toFixed(3)} MRR=${aggregateMetrics(kwParaphrase).meanMrr.toFixed(3)} | ` +
      `baseline-semantic recall@10=${aggregateMetrics(baseSemParaphrase).meanRecallAt10.toFixed(3)} MRR=${aggregateMetrics(baseSemParaphrase).meanMrr.toFixed(3)} | ` +
      `remediated-semantic recall@10=${aggregateMetrics(remSemParaphrase).meanRecallAt10.toFixed(3)} MRR=${aggregateMetrics(remSemParaphrase).meanMrr.toFixed(3)}`,
  );

  console.log("\n=== Default search-mode decision (remediated variant) ===");
  const kwAgg = aggregateMetrics(
    rows.filter((r) => r.variant === "remediated" && r.mode === "keyword").map((r): CaseMetrics => r),
  );
  const hybridAgg = aggregateMetrics(
    rows.filter((r) => r.variant === "remediated" && r.mode === "hybrid_exact").map((r): CaseMetrics => r),
  );
  const decision = decideDefaultSearchMode({ keyword: kwAgg, hybrid: hybridAgg });
  console.log(`decision: ${decision.mode} -- ${decision.reason}`);

  console.log("\n=== Filter accuracy (deterministic cases) ===");
  const filterRows = rows.filter((r) => r.filterAccurate !== null && r.variant === "baseline");
  const filterAccurateCount = filterRows.filter((r) => r.filterAccurate).length;
  console.log(`${filterAccurateCount}/${filterRows.length} deterministic filter checks passed`);

  console.log("\n=== Grouped-context completeness / citation completeness ===");
  console.log(`${groupedContextCompleteCases}/${groupedContextCasesTotal} repeated-passage cases showed >=2 contexts`);
  console.log(`duplicate context rows observed: ${duplicateContextCases}`);
  console.log(`citation completeness: ${citationChecked - citationIncomplete}/${citationChecked} contexts had complete citation fields`);

  console.log("\n=== No-answer / weak-match similarity distribution (semantic-exact, top-1) ===");
  for (const variant of VARIANTS) {
    const noAns = noAnswerSimilarities[variant];
    const ans = answerableSimilarities[variant];
    console.log(`[${variant}] no-answer top-1: n=${noAns.length} mean=${meanOf(noAns).toFixed(3)} max=${noAns.length ? Math.max(...noAns).toFixed(3) : "n/a"}`);
    console.log(`[${variant}] answerable top-1: n=${ans.length} mean=${meanOf(ans).toFixed(3)} min=${ans.length ? Math.min(...ans).toFixed(3) : "n/a"}`);
    for (const threshold of [0.6, 0.65, 0.7, 0.71, 0.72, 0.75, 0.78, 0.8]) {
      console.log(
        `  [${variant}] threshold=${threshold}: no-answer false-strong-match rate=${rateAtOrAboveThreshold(noAns, threshold).toFixed(3)}, ` +
          `answerable suppression rate=${rateBelowThreshold(ans, threshold).toFixed(3)}`,
      );
    }
  }

  console.log(`\nquery-embedding provider failures: ${providerFailures}/${RETRIEVAL_EVALUATION_DATASET.length}`);
  console.log(`\nCSV written to ${path.join(outDir, "publication_retrieval_evaluation.csv")}`);

  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
