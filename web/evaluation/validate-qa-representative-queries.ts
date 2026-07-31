/**
 * Milestone 7B.1b real-data validation: representative answerable,
 * partially-answerable, no-answer, and ambiguous/conflicting questions run
 * against the live corpus with the shipped default configuration
 * (quality_aware reranker, evidence-set size 3). Prints query analysis,
 * candidate counts, selected/rejected evidence, and gate status/reasons for
 * each -- an ad hoc reporting script, not a test. Reports every case,
 * including failures, with no cherry-picking.
 *
 * Run: `npx tsx --tsconfig evaluation/tsconfig.json evaluation/validate-qa-representative-queries.ts`
 */
import { PostgresSemanticRetrievalRepository } from "../lib/repositories/postgres-semantic-retrieval-repository";
import { PostgresCompanyRepository } from "../lib/repositories/postgres-company-repository";
import { HttpQueryEmbeddingProvider, loadHttpQueryEmbeddingProviderConfig } from "../lib/services/query-embedding-provider";
import { analyzeQuestion } from "../lib/services/qa/query-analysis";
import { generateCandidates } from "../lib/services/qa/candidate-generation";
import { createQaReranker } from "../lib/services/qa/qa-reranker";
import { buildEvidenceSet } from "../lib/services/qa/evidence-set-builder";
import { checkCoherence } from "../lib/services/qa/coherence-checker";
import { evaluateGroundedness } from "../lib/services/qa/groundedness-gate";
import { getQaConfig } from "../lib/config/qa-config";
import { parsePassageSearchParams } from "../lib/services/passage-search-params";
import { closePool } from "../lib/db/pool";

interface RepresentativeQuery {
  label: string;
  question: string;
}

const QUERIES: RepresentativeQuery[] = [
  // Answerable -- 7B.1 report's representative queries, reused with real
  // company names substituted where the original was generic.
  { label: "answerable", question: "What did ACT say about its ability to continue operating?" },
  { label: "answerable", question: "What new liquidity risks did Kore Potash introduce?" },
  { label: "answerable", question: "How did Bell Equipment's board oversight disclosures change?" },
  { label: "answerable", question: "What did Sabvest Capital report about customer concentration?" },
  { label: "answerable", question: "What evidence discusses Southern Palladium's foreign-exchange exposure?" },
  { label: "answerable", question: "What changed in Bell Equipment's debt covenant language?" },
  { label: "answerable", question: "What did Spur's most recent report say about margin pressure?" },
  { label: "answerable", question: "What future expansion plans did ACT disclose?" },
  // Partially answerable
  { label: "partially_answerable", question: "What is Kore Potash's remuneration philosophy and executive succession plan?" },
  { label: "partially_answerable", question: "How do ACT and Kore Potash's climate risk disclosures compare?" },
  { label: "partially_answerable", question: "What quantitative and qualitative evidence exists for Spur's franchise growth strategy?" },
  // No-answer
  { label: "no_answer", question: "What does the company disclose about cryptocurrency mining operations?" },
  { label: "no_answer", question: "What autonomous vehicle technology has the company developed?" },
  { label: "no_answer", question: "What space launch contracts has the company signed?" },
  { label: "no_answer", question: "What did Titan Global Resources disclose about its risk exposure?" },
  // Ambiguous/conflicting
  { label: "ambiguous", question: "Did Sabvest Capital's subsidiaries satisfy IFRS 10 consolidation requirements?" },
  { label: "ambiguous", question: "What does Southern Palladium's directors' report say about company registration?" },
];

async function main() {
  const companyRepo = new PostgresCompanyRepository();
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const companies = await companyRepo.listCompanies();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);
  const config = getQaConfig();

  for (const { label, question } of QUERIES) {
    console.log(`\n${"=".repeat(100)}\n[${label}] "${question}"\n${"=".repeat(100)}`);
    const analysis = analyzeQuestion(question, companies);
    console.log(
      `  analysis: tickers=${JSON.stringify(analysis.tickers)} scope=${analysis.requestedScope} questionType=${analysis.questionType} ` +
        `direction=${analysis.comparisonDirection}(${analysis.directionConfidence}) unresolved=${JSON.stringify(analysis.unresolvedTerms)}`,
    );

    const params = parsePassageSearchParams({
      q: analysis.normalizedQuestion,
      company: analysis.requiredTicker ?? undefined,
      periodStart: analysis.dateRange?.start ?? undefined,
      periodEnd: analysis.dateRange?.end ?? undefined,
      category: analysis.requiredCategory ?? undefined,
    });

    let embedding = null;
    try {
      embedding = await provider.embedQuery(question);
    } catch (error) {
      console.error(`  [embed-query failed] ${(error as Error).message}`);
    }

    const candidates = await generateCandidates(semanticRepo, question, embedding, params, config, null);
    const reranked = createQaReranker(config.secondStageReranker).rerank(question, candidates, analysis);
    const evidenceSet = buildEvidenceSet(reranked, analysis, config);
    const coherence = checkCoherence(evidenceSet.selected, evidenceSet.rejected, analysis);
    const gate = evaluateGroundedness(evidenceSet, analysis, coherence, config);

    console.log(`  candidates=${candidates.length} selected=${evidenceSet.selected.length} rejected=${evidenceSet.rejected.length}`);
    console.log(`  GATE STATUS: ${gate.status} -- reasons: ${gate.reasonCodes.join(", ")}`);
    for (const item of evidenceSet.selected) {
      console.log(
        `    SELECTED [${item.context.companyTicker}] "${(item.context.heading ?? "(no heading)").slice(0, 60)}" -- ${item.context.text.slice(0, 100).replace(/\s+/g, " ")}...`,
      );
    }
    if (evidenceSet.selected.length === 0) {
      console.log("    (no evidence selected)");
    }
  }

  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
