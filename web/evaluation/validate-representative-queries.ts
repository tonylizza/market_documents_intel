/**
 * Milestone 7B.1a real-data validation: the 11 representative failure
 * queries named in the Milestone 7B.1 final report, run against the real
 * corpus with no filters, comparing baseline (no remediation) vs.
 * remediated (shipped `QualityAdjustedSemanticReranker`) top-10 semantic
 * results side by side. Ad hoc reporting script, not a test -- prints
 * every query's full top-10 for manual inspection, including failures.
 *
 * Run: `npx tsx --tsconfig evaluation/tsconfig.json evaluation/validate-representative-queries.ts`
 */
import { PostgresSemanticRetrievalRepository } from "../lib/repositories/postgres-semantic-retrieval-repository";
import { HttpQueryEmbeddingProvider, loadHttpQueryEmbeddingProviderConfig } from "../lib/services/query-embedding-provider";
import { parsePassageSearchParams } from "../lib/services/passage-search-params";
import { IdentitySemanticReranker, QualityAdjustedSemanticReranker } from "../lib/services/semantic-reranker";
import { closePool } from "../lib/db/pool";

const QUERIES = [
  "ability to continue operating",
  "difficulty meeting financial obligations",
  "changes in board oversight",
  "exposure to currency movements",
  "plans for future expansion",
  "pressure on operating margins",
  "reliance on major customers",
  "uncertainty about economic conditions",
  "newly introduced liquidity risk",
  "removed governance disclosure",
  "modified debt covenant language",
];

function snippet(text: string, n = 80): string {
  const t = text.trim().replace(/\s+/g, " ");
  return t.length > n ? t.slice(0, n) + "..." : t;
}

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);
  const baseline = new IdentitySemanticReranker();
  const remediated = new QualityAdjustedSemanticReranker();
  const params = parsePassageSearchParams({ q: "placeholder" });

  for (const query of QUERIES) {
    console.log(`\n${"=".repeat(100)}\nQUERY: "${query}"\n${"=".repeat(100)}`);
    const embedding = await provider.embedQuery(query);
    const candidates = await semanticRepo.searchSemanticCandidates(embedding.vector, params, 50, "exact");

    const baselineRanked = baseline.rerank(query, candidates).slice(0, 10);
    const remediatedRanked = remediated.rerank(query, candidates).slice(0, 10);

    console.log("\n-- BASELINE (raw cosine, no remediation) top 10 --");
    for (const c of baselineRanked) {
      const cand = candidates.find((x) => x.passageId === c.passageId)!;
      console.log(`  [${c.rawSimilarity.toFixed(3)}] wc=${cand.wordCount} "${snippet(cand.heading ?? "(no heading)")}" -- ${snippet(cand.text)}`);
    }

    console.log("\n-- REMEDIATED (quality-adjusted) top 10 --");
    for (const c of remediatedRanked) {
      const cand = candidates.find((x) => x.passageId === c.passageId)!;
      const adjustedNote = c.qualityFactor < 1 ? ` [adjusted x${c.qualityFactor.toFixed(2)}, ${c.explanationCode}, was rank ${c.originalRank + 1}]` : "";
      console.log(`  [raw=${c.rawSimilarity.toFixed(3)} adj=${c.adjustedScore.toFixed(3)}] wc=${cand.wordCount} "${snippet(cand.heading ?? "(no heading)")}" -- ${snippet(cand.text)}${adjustedNote}`);
    }
  }

  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
