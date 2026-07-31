import { PostgresSemanticRetrievalRepository } from "./lib/repositories/postgres-semantic-retrieval-repository";
import { parsePassageSearchParams } from "./lib/services/passage-search-params";
import { closePool } from "./lib/db/pool";

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const targetPassageId = "688cd61c-5d1a-5748-88c7-7659ef214b93";
  const terms = ["growth", "opportunities", "identified", "healthcare", "administration", "business"];
  const orQuery = terms.join(" OR ");
  const params = parsePassageSearchParams({ q: orQuery, company: "ACT" });
  const lexical = await semanticRepo.searchLexicalCandidates(params, 200);
  console.log("lexical count:", lexical.length, "has target:", lexical.some(c=>c.passageId===targetPassageId));
  const idx = lexical.findIndex(c=>c.passageId===targetPassageId);
  console.log("rank position (of 200):", idx >= 0 ? lexical[idx].rankPosition : "not found in 200");

  // try AND on just "growth opportunities" phrase
  const params2 = parsePassageSearchParams({ q: "growth opportunities", company: "ACT" });
  const lexical2 = await semanticRepo.searchLexicalCandidates(params2, 40);
  console.log("phrase-only count:", lexical2.length, "has target:", lexical2.some(c=>c.passageId===targetPassageId), "rank:", lexical2.findIndex(c=>c.passageId===targetPassageId));

  await closePool();
}
main().catch(e=>{console.error(e); process.exit(1);});
