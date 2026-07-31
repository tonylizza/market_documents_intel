/**
 * Milestone 7B.2: standard-RAG Q&A retrieval-chunk domain types. A `QaChunk`
 * is a retrieval artifact only -- it is never presented as though it were
 * the original source document, and it is never a citation object on its
 * own. Every chunk resolves back to real `app.passages` rows (via
 * `memberPassageIds`) and a real `app.reports` row, which remain the
 * authoritative evidence identity (see `docs/qa-retrieval-chunks.md`'s
 * "parent-child" discipline, carried forward from the 7B.1d spike into this
 * production corpus).
 */

/** One nearest-neighbor chunk candidate, before dedup. */
export interface QaChunkCandidate {
  chunkId: string;
  reportId: string;
  companyId: string;
  chunkIndex: number;
  similarity: number | null;
  text: string;
  sectionHeading: string | null;
  pageStart: number;
  pageEnd: number;
  tokenCount: number;
  memberPassageIds: string[];
  /** 1-based position in the semantic ranking -- what RRF fuses on, never
   * the raw cosine value (mirrors `LexicalCandidate.rankPosition`). */
  semanticRankPosition: number | null;
  /** 1-based position in the lexical (`ts_rank`) ranking, when lexical
   * fusion is enabled; `null` for a semantic-only candidate. */
  lexicalRankPosition: number | null;
  fusedScore: number | null;
}

/** A chunk citation, resolved with enough report/company context to render
 * without a second round-trip. `memberPassageIds` and `reportId` are what
 * `/ask` uses to link to the mapped `/passages` and `/comparisons` pages --
 * this is not itself a citation identity independent of those. */
export interface QaChunkCitation {
  chunkId: string;
  companyId: string;
  companyTicker: string;
  companyName: string;
  reportId: string;
  reportTitle: string;
  reportPeriodEnd: string | null;
  pageStart: number;
  pageEnd: number;
  sectionHeading: string | null;
  memberPassageIds: string[];
  /** Server-formatted, e.g. "KP2, 2024 report, pp. 12-14". */
  label: string;
}

/** One deduplicated, citation-ready piece of Q&A evidence -- the unit
 * `/ask`'s answer-generation prompt and evidence list are both built from. */
export interface QaEvidenceChunk {
  chunkId: string;
  text: string;
  citation: QaChunkCitation;
  similarity: number | null;
  fusedScore: number | null;
  /** How many raw candidates (pre-dedup) this evidence chunk represents --
   * a diagnostic only, never used to inflate evidence-set size or imply
   * independent corroboration (overlapping chunks are not independent
   * evidence -- see `qa-chunk-dedup.ts`). */
  mergedCandidateCount: number;
}
