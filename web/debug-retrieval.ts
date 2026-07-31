import { PostgresSemanticRetrievalRepository } from "./lib/repositories/postgres-semantic-retrieval-repository";
import { PostgresCompanyRepository } from "./lib/repositories/postgres-company-repository";
import { HttpQueryEmbeddingProvider, loadHttpQueryEmbeddingProviderConfig } from "./lib/services/query-embedding-provider";
import { analyzeQuestion } from "./lib/services/qa/query-analysis";
import { parsePassageSearchParams } from "./lib/services/passage-search-params";
import { getQaConfig } from "./lib/config/qa-config";
import { closePool } from "./lib/db/pool";

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const companyRepo = new PostgresCompanyRepository();
  const companies = await companyRepo.listCompanies();
  const question = "What growth opportunities has ACT identified in its healthcare administration business?";
  const targetPassageId = "688cd61c-5d1a-5748-88c7-7659ef214b93";

  const analysis = analyzeQuestion(question, companies);
  console.log("analysis:", JSON.stringify(analysis, null, 2));

  const params = parsePassageSearchParams({
    q: analysis.normalizedQuestion,
    company: analysis.requiredTicker ?? undefined,
    periodStart: analysis.dateRange?.start ?? undefined,
    periodEnd: analysis.dateRange?.end ?? undefined,
    category: analysis.requiredCategory ?? undefined,
  });
  console.log("params:", JSON.stringify(params, null, 2));

  const config = getQaConfig();
  const lexical = await semanticRepo.searchLexicalCandidates(params, config.candidateLimitPerSource);
  console.log("lexical count:", lexical.length, "has target:", lexical.some(c=>c.passageId===targetPassageId));

  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);
  const embedding = await provider.embedQuery(question);
  const semantic = await semanticRepo.searchSemanticCandidates(embedding.vector, params, config.candidateLimitPerSource, "auto");
  console.log("semantic count:", semantic.length, "has target:", semantic.some(c=>c.passageId===targetPassageId));

  await closePool();
}
main().catch(e=>{console.error(e); process.exit(1);});
