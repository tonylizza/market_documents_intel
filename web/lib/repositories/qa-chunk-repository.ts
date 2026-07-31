import type { QaChunkCandidate, QaChunkCitation } from "@/lib/domain/qa-chunk";

/**
 * Production Q&A retrieval-chunk repository interface -- reads
 * `app.current_qa_chunks` / `app.current_qa_chunk_passages` (Milestone
 * 7B.2), the real, published, `app_readonly`-servable corpus. Deliberately
 * a different file and interface from the 7B.1d experimental
 * `QaChunkRetrievalRepository` (`lib/repositories/qa-chunk-retrieval-
 * repository.ts`), which reads the disposable `qa_experiment` schema
 * through a separate, higher-privileged pool and is never used outside
 * evaluation scripts. This one uses the same `app_readonly`-bound pool
 * (`lib/db/pool.ts`) and HNSW-aware query wrapper (`lib/db/vector-
 * query.ts`) every other production route already uses. Implemented by
 * `PostgresQaChunkRepository`.
 */
export interface QaChunkRepository {
  /** Top-`limit` chunk candidates by cosine similarity. Bounded top-K only
   * (brief: "initially 20-30 semantic candidates") -- never an unbounded
   * scan. `companyTicker`, when given, is applied in the SQL `WHERE`
   * clause -- a company's chunks are scoped to the top-K search itself,
   * never filtered out of an already-fetched, company-agnostic top-K after
   * the fact (a company whose chunks don't happen to rank in the
   * unfiltered top-K would otherwise be wrongly zeroed out for a
   * DOCUMENT_QA/COMPARISON_QA question that named it explicitly). */
  searchSemanticCandidates(
    vector: number[],
    limit: number,
    mode: "exact" | "hnsw",
    companyTicker?: string | null,
  ): Promise<QaChunkCandidate[]>;

  /** Optional lexical retrieval over chunk text (`qa_chunks.search_vector`),
   * for deterministic RRF fusion with the semantic ranking. Returns an
   * empty array for an empty query. Same SQL-level `companyTicker`
   * scoping as `searchSemanticCandidates`. */
  searchLexicalCandidates(queryText: string, limit: number, companyTicker?: string | null): Promise<QaChunkCandidate[]>;

  /** Resolves a set of chunk ids to their citation context (company/report/
   * page/section) in one batched round trip. */
  resolveCitations(chunkIds: readonly string[]): Promise<Map<string, QaChunkCitation>>;

  /** Every canonical passage id a chunk's character span overlaps, keyed by
   * chunk id -- the parent-resolution mapping citations and comparison
   * links resolve through. */
  resolveMemberPassageIds(chunkIds: readonly string[]): Promise<Map<string, string[]>>;
}
