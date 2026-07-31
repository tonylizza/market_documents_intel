import { PostgresSemanticRetrievalRepository } from "./lib/repositories/postgres-semantic-retrieval-repository";
import { parsePassageSearchParams } from "./lib/services/passage-search-params";
import { closePool } from "./lib/db/pool";

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const targetPassageId = "688cd61c-5d1a-5748-88c7-7659ef214b93";
  const STOPWORDS = new Set(["the","a","an","and","or","but","of","to","in","on","for","is","are","was","were","did","does","what","how","why","who","which","with","about","that","this","these","those","it","its","as","at","by","from","be","has","have","had","will","would","could","should","than","then","there","their"]);
  const question = "What growth opportunities has ACT identified in its healthcare administration business?";
  const terms = question.toLowerCase().split(/[^a-z0-9]+/).filter(t => t.length >= 3 && !STOPWORDS.has(t));
  const orQuery = terms.join(" OR ");
  console.log("orQuery:", orQuery);

  const params = parsePassageSearchParams({ q: orQuery, company: "ACT" });
  const lexical = await semanticRepo.searchLexicalCandidates(params, 40);
  console.log("lexical count:", lexical.length, "has target:", lexical.some(c=>c.passageId===targetPassageId));
  const idx = lexical.findIndex(c=>c.passageId===targetPassageId);
  console.log("rank position:", idx >= 0 ? lexical[idx].rankPosition : "not found");

  await closePool();
}
main().catch(e=>{console.error(e); process.exit(1);});
