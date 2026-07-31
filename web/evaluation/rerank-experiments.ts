/**
 * Milestone 7B.1a: compares >=8 named, deterministic remediation strategies
 * for the short-passage similarity-inflation problem against the real
 * evaluation dataset and the real corpus -- run once, before the shipped
 * default (`QualityAdjustedSemanticReranker`, named `quality_multiplier`
 * here) is selected, so the selection is evidence-based rather than
 * assumed. Each strategy is a pure function from raw candidates (plus the
 * lexical id set, for the one strategy that uses lexical support) to an
 * ordered passage-id list -- deliberately simpler than the full
 * `SemanticReranker` interface, since this script only needs ranked ids to
 * score metrics, not the diagnostics fields the shipped reranker carries.
 *
 * Run: `npx tsx --tsconfig evaluation/tsconfig.json evaluation/rerank-experiments.ts`
 * (requires APP_READONLY_DATABASE_URL, QUERY_EMBEDDING_SERVICE_URL).
 */
import { PostgresSemanticRetrievalRepository } from "../lib/repositories/postgres-semantic-retrieval-repository";
import { HttpQueryEmbeddingProvider, loadHttpQueryEmbeddingProviderConfig } from "../lib/services/query-embedding-provider";
import { parsePassageSearchParams } from "../lib/services/passage-search-params";
import { closePool } from "../lib/db/pool";
import { computePassageQualityFeatures, computeQualityAdjustment, SUBSTANTIVE_WORD_COUNT_THRESHOLD } from "../lib/services/passage-quality";
import type { SemanticCandidate } from "../lib/domain/retrieval";
import { RETRIEVAL_EVALUATION_DATASET, type RetrievalEvaluationCase } from "./dataset";
import {
  aggregateMetrics,
  computeCaseMetrics,
  irrelevantShortFragmentRateAtK,
  meanOf,
  substantivePrecisionAtK,
  type CaseMetrics,
  type RelevanceGrade,
} from "./metrics";

type Strategy = (candidates: readonly SemanticCandidate[], lexicalIds: ReadonlySet<string>) => string[];

function isFragmentFlag(c: SemanticCandidate): boolean {
  const f = computePassageQualityFeatures(c);
  return f.wordCount < SUBSTANTIVE_WORD_COUNT_THRESHOLD && (f.isHeadingOnlyFragment || f.isRepeatedGenericHeading || f.containsContinued);
}

/** Stable demotion helper: keeps every candidate (never deletes), moves
 * flagged ones after unflagged ones, preserving each group's relative
 * (raw-similarity) order -- so a hard "exclusion" strategy still produces a
 * full ranked list comparable to the others (excluded items just rank
 * beyond the ones kept). */
function demote(candidates: readonly SemanticCandidate[], shouldDemote: (c: SemanticCandidate) => boolean): string[] {
  const kept = candidates.filter((c) => !shouldDemote(c));
  const demoted = candidates.filter((c) => shouldDemote(c));
  return [...kept, ...demoted].map((c) => c.passageId);
}

const STRATEGIES: Record<string, Strategy> = {
  no_op: (candidates) => candidates.map((c) => c.passageId),

  hard_cutoff_10: (candidates) => demote(candidates, (c) => c.wordCount < 10),

  hard_cutoff_16: (candidates) => demote(candidates, (c) => c.wordCount < 16),

  hard_cutoff_30: (candidates) => demote(candidates, (c) => c.wordCount < 30),

  generic_heading_exclusion: (candidates) =>
    demote(candidates, (c) => {
      const f = computePassageQualityFeatures(c);
      return f.isRepeatedGenericHeading || f.containsContinued || f.isHeadingOnlyFragment;
    }),

  length_aware_linear_penalty: (candidates) => {
    const scored = candidates.map((c) => {
      const f = computePassageQualityFeatures(c);
      const factor = f.hasLanguageSignal ? 1 : Math.min(1, c.wordCount / SUBSTANTIVE_WORD_COUNT_THRESHOLD);
      return { id: c.passageId, score: c.similarity * factor };
    });
    scored.sort((a, b) => b.score - a.score);
    return scored.map((s) => s.id);
  },

  quality_multiplier: (candidates) => {
    const scored = candidates.map((c) => {
      const f = computePassageQualityFeatures(c);
      const { factor } = computeQualityAdjustment(f);
      return { id: c.passageId, score: c.similarity * factor };
    });
    scored.sort((a, b) => b.score - a.score);
    return scored.map((s) => s.id);
  },

  lexical_support_boost: (candidates, lexicalIds) => {
    const scored = candidates.map((c) => ({
      id: c.passageId,
      score: c.similarity * (lexicalIds.has(c.passageId) ? 1.15 : 1),
    }));
    scored.sort((a, b) => b.score - a.score);
    return scored.map((s) => s.id);
  },
};

const STRATEGY_NAMES = Object.keys(STRATEGIES);

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

interface StrategyRow {
  strategy: string;
  caseId: string;
  category: string;
  metrics: CaseMetrics;
  substantivePrecisionAt5: number;
  irrelevantFragRateAt5: number;
}

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);

  const rows: StrategyRow[] = [];
  let providerFailures = 0;

  for (const testCase of RETRIEVAL_EVALUATION_DATASET) {
    const params = buildParams(testCase);
    const graded = gradedMap(testCase);
    const relevantSet = new Set(testCase.relevantPassageIds);

    let embedding;
    try {
      embedding = await provider.embedQuery(testCase.query);
    } catch (error) {
      providerFailures += 1;
      console.error(`[embed-query failed] ${testCase.id}: ${(error as Error).message}`);
      continue;
    }

    const candidates = await semanticRepo.searchSemanticCandidates(embedding.vector, params, 50, "exact");
    const lexicalCandidates = await semanticRepo.searchLexicalCandidates(params, 50);
    const lexicalIds = new Set(lexicalCandidates.map((c) => c.passageId));
    const isFragment = new Set(candidates.filter(isFragmentFlag).map((c) => c.passageId));

    for (const name of STRATEGY_NAMES) {
      const rankedIds = STRATEGIES[name](candidates, lexicalIds);
      const metrics = computeCaseMetrics(rankedIds, testCase.relevantPassageIds, graded);
      rows.push({
        strategy: name,
        caseId: testCase.id,
        category: testCase.category,
        metrics,
        substantivePrecisionAt5: substantivePrecisionAtK(rankedIds, relevantSet, isFragment, 5),
        irrelevantFragRateAt5: irrelevantShortFragmentRateAtK(rankedIds, isFragment, relevantSet, 5),
      });
    }
  }

  console.log(`\nquery-embedding provider failures: ${providerFailures}/${RETRIEVAL_EVALUATION_DATASET.length}`);
  console.log(`\n=== >=8 remediation strategies -- aggregate over n=${RETRIEVAL_EVALUATION_DATASET.length - providerFailures} cases (semantic_exact) ===`);

  const paraphraseIds = new Set(
    RETRIEVAL_EVALUATION_DATASET.filter((c) => c.category === "semantic_paraphrase" || c.expectedBehavior === "semantic_favored").map((c) => c.id),
  );

  interface Summary {
    strategy: string;
    recallAt5: number;
    recallAt10: number;
    precisionAt5: number;
    substPrecisionAt5: number;
    mrr: number;
    ndcgAt10: number | null;
    irrelevantFragRateAt5: number;
    paraphraseRecallAt10: number;
    paraphraseMrr: number;
  }
  const summaries: Summary[] = [];

  for (const name of STRATEGY_NAMES) {
    const subset = rows.filter((r) => r.strategy === name);
    const agg = aggregateMetrics(subset.map((r) => r.metrics));
    const paraphraseSubset = subset.filter((r) => paraphraseIds.has(r.caseId));
    const paraphraseAgg = aggregateMetrics(paraphraseSubset.map((r) => r.metrics));
    const summary: Summary = {
      strategy: name,
      recallAt5: agg.meanRecallAt5,
      recallAt10: agg.meanRecallAt10,
      precisionAt5: agg.meanPrecisionAt5,
      substPrecisionAt5: meanOf(subset.map((r) => r.substantivePrecisionAt5)),
      mrr: agg.meanMrr,
      ndcgAt10: agg.meanNdcgAt10,
      irrelevantFragRateAt5: meanOf(subset.map((r) => r.irrelevantFragRateAt5)),
      paraphraseRecallAt10: paraphraseAgg.meanRecallAt10,
      paraphraseMrr: paraphraseAgg.meanMrr,
    };
    summaries.push(summary);
    console.log(
      `${name.padEnd(28)} recall@5=${summary.recallAt5.toFixed(3)} recall@10=${summary.recallAt10.toFixed(3)} ` +
        `precision@5=${summary.precisionAt5.toFixed(3)} subst.precision@5=${summary.substPrecisionAt5.toFixed(3)} ` +
        `MRR=${summary.mrr.toFixed(3)} nDCG@10=${summary.ndcgAt10?.toFixed(3) ?? "n/a"} ` +
        `irrelevantFragRate@5=${summary.irrelevantFragRateAt5.toFixed(3)} ` +
        `paraphrase.recall@10=${summary.paraphraseRecallAt10.toFixed(3)} paraphrase.MRR=${summary.paraphraseMrr.toFixed(3)}`,
    );
  }

  console.log("\n=== short_substantive_passage category (does the strategy wrongly suppress genuinely short, financially-dense passages?) ===");
  for (const name of STRATEGY_NAMES) {
    const subset = rows.filter((r) => r.strategy === name && r.category === "short_substantive_passage");
    const agg = aggregateMetrics(subset.map((r) => r.metrics));
    console.log(`${name.padEnd(28)} n=${agg.caseCount} recall@5=${agg.meanRecallAt5.toFixed(3)} recall@10=${agg.meanRecallAt10.toFixed(3)} MRR=${agg.meanMrr.toFixed(3)}`);
  }

  // --- predeclared eligibility filter (from the milestone spec itself, not
  // derived from these results): the shipped reranker must be a *bounded,
  // non-zero, explainable* adjustment -- "demotion, not deletion" -- because
  // it has to plug into the existing `SemanticReranker` interface
  // (`RerankedSemanticCandidate.qualityFactor`/`explanationCode`) used by
  // the retrieval service, RRF, and the UI's raw-vs-adjusted diagnostics.
  // `hard_cutoff_*` and `generic_heading_exclusion` are full demotions-to-
  // bottom (see `demote()`) -- useful as a comparison point, but not
  // eligible to ship regardless of how they score. Only `quality_multiplier`
  // and `length_aware_linear_penalty` are bounded multiplicative strategies;
  // `lexical_support_boost` is a boost (not a length-based penalty at all)
  // and is scored for reference only.
  const ARCHITECTURALLY_ELIGIBLE = new Set(["quality_multiplier", "length_aware_linear_penalty"]);

  // --- predeclared selection gate (defined before viewing final numbers):
  // among architecturally-eligible strategies, a candidate winner must not
  // regress recall@5/recall@10/paraphrase-recall@10 vs no_op and must
  // materially reduce irrelevantFragRate@5 (>=15% relative reduction); the
  // winner is the eligible candidate with the highest nDCG@10 (MRR as
  // tiebreak).
  const baseline = summaries.find((s) => s.strategy === "no_op")!;
  const candidates = summaries.filter((s) => {
    if (!ARCHITECTURALLY_ELIGIBLE.has(s.strategy)) return false;
    const noRegression =
      s.recallAt5 >= baseline.recallAt5 - 1e-9 &&
      s.recallAt10 >= baseline.recallAt10 - 1e-9 &&
      s.paraphraseRecallAt10 >= baseline.paraphraseRecallAt10 - 1e-9;
    const fragRateReduction = baseline.irrelevantFragRateAt5 > 0 ? 1 - s.irrelevantFragRateAt5 / baseline.irrelevantFragRateAt5 : 0;
    return noRegression && fragRateReduction >= 0.15;
  });
  candidates.sort(
    (a, b) => (b.ndcgAt10 ?? 0) - (a.ndcgAt10 ?? 0) || b.mrr - a.mrr || a.irrelevantFragRateAt5 - b.irrelevantFragRateAt5,
  );

  const allNonEligible = summaries.filter((s) => s.strategy !== "no_op" && !ARCHITECTURALLY_ELIGIBLE.has(s.strategy));
  const bestNonEligibleByFragRate = [...allNonEligible].sort((a, b) => a.irrelevantFragRateAt5 - b.irrelevantFragRateAt5)[0];

  console.log(
    "\n=== Selection gate: eligibility (bounded/non-zero/explainable, from the spec's architecture requirement, not from these numbers) " +
      "then no recall/paraphrase-recall regression vs no_op, then >=15% relative irrelevantFragRate@5 reduction ===",
  );
  console.log(`architecturally eligible for shipping: ${[...ARCHITECTURALLY_ELIGIBLE].join(", ")}`);
  console.log(
    `demonstrative-only (excluded regardless of score -- full demotion-to-bottom, not a bounded factor): ` +
      `${allNonEligible.map((s) => s.strategy).join(", ")} -- best of these by irrelevantFragRate@5 was ` +
      `${bestNonEligibleByFragRate.strategy} (${bestNonEligibleByFragRate.irrelevantFragRateAt5.toFixed(3)}), for reference only`,
  );
  if (candidates.length === 0) {
    console.log("no eligible strategy satisfied the gate -- falling back to no_op (no remediation)");
  } else {
    console.log(`qualifying eligible strategies (best first): ${candidates.map((c) => c.strategy).join(", ")}`);
    console.log(`selected: ${candidates[0].strategy}`);
  }

  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
