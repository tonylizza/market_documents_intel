import "server-only";
import { qaExperimentQuery, qaExperimentQueryVector } from "@/lib/db/qa-experiment-pool";

/**
 * Milestone 7B.1d (experimental): reads the disposable
 * `qa_experiment.retrieval_chunks` / `retrieval_chunk_passages` tables built
 * by `market_documents.qa_experiment.build_chunks` -- entirely separate from
 * `app.passage_embeddings`/`app.current_passage_embeddings`, never part of
 * the publication lifecycle, never exposed as a public search mode. Used
 * only by evaluation scripts and (optionally, behind `candidate-generation.
 * ts`'s `chunkOptions` parameter) the Q&A evidence pipeline's experimental
 * candidate mix -- never by `/passages` or any public route.
 */

export interface ChunkMemberPassage {
  passageId: string;
  role: string;
}

export interface ChunkHit {
  chunkId: string;
  strategy: string;
  similarity: number;
  members: ChunkMemberPassage[];
}

function vectorLiteral(vector: readonly number[]): string {
  return `[${vector.join(",")}]`;
}

export class QaChunkRetrievalRepository {
  /** Top-`limit` child chunks by cosine similarity, optionally restricted
   * to a strategy subset (query-type routing experiments pass a narrower
   * list; omit/empty to search every built strategy). Each hit carries its
   * full member-passage/role list so callers can map straight back to
   * canonical parent passages without a second round-trip. */
  async searchChunkCandidates(
    vector: number[],
    limit: number,
    strategies: readonly string[] | null = null,
    mode: "exact" | "hnsw" = "hnsw",
  ): Promise<ChunkHit[]> {
    const values: unknown[] = [];
    let strategyFilter = "";
    if (strategies && strategies.length > 0) {
      values.push(strategies as string[]);
      strategyFilter = `WHERE rc.chunk_strategy = ANY($${values.length}::text[])`;
    }
    const vectorIdx = values.length + 1;
    const limitIdx = values.length + 2;

    const sql = `
      SELECT rc.id AS chunk_id, rc.chunk_strategy AS strategy,
             (1 - (rc.embedding <=> $${vectorIdx}::vector)) AS similarity
      FROM qa_experiment.retrieval_chunks rc
      ${strategyFilter}
      ORDER BY rc.embedding <=> $${vectorIdx}::vector
      LIMIT $${limitIdx}
    `;

    const rows = await qaExperimentQueryVector<{ chunk_id: string; strategy: string; similarity: number }>(
      sql,
      [...values, vectorLiteral(vector), limit],
      mode,
    );
    if (rows.length === 0) return [];

    const chunkIds = rows.map((r) => r.chunk_id);
    const memberRows = await qaExperimentQuery<{ chunk_id: string; passage_id: string; role: string }>(
      `SELECT chunk_id, passage_id, role FROM qa_experiment.retrieval_chunk_passages WHERE chunk_id = ANY($1::uuid[])`,
      [chunkIds],
    );
    const membersByChunk = new Map<string, ChunkMemberPassage[]>();
    for (const m of memberRows) {
      const arr = membersByChunk.get(m.chunk_id) ?? [];
      arr.push({ passageId: m.passage_id, role: m.role });
      membersByChunk.set(m.chunk_id, arr);
    }

    return rows.map((r) => ({
      chunkId: r.chunk_id,
      strategy: r.strategy,
      similarity: r.similarity,
      members: membersByChunk.get(r.chunk_id) ?? [],
    }));
  }
}
