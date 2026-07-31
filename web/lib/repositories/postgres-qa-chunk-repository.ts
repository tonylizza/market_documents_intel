import "server-only";
import { query } from "@/lib/db/pool";
import { queryVector } from "@/lib/db/vector-query";
import { MalformedRowError } from "@/lib/db/errors";
import type { QaChunkCandidate, QaChunkCitation } from "@/lib/domain/qa-chunk";
import {
  qaChunkCandidateRowSchema,
  qaChunkCitationContextRowSchema,
  qaChunkLexicalCandidateRowSchema,
  qaChunkMemberPassageRowSchema,
} from "@/lib/schemas/qa-chunk";
import { formatQaChunkCitationLabel } from "@/lib/services/qa/qa-chunk-citation";
import type { QaChunkRepository } from "@/lib/repositories/qa-chunk-repository";

function vectorLiteral(vector: readonly number[]): string {
  return `[${vector.join(",")}]`;
}

/**
 * Production repository for `app.current_qa_chunks` /
 * `app.current_qa_chunk_passages` (Milestone 7B.2) -- the real, published,
 * `app_readonly`-servable corpus. Uses the same production pool
 * (`lib/db/pool.ts`) and HNSW-aware query wrapper (`lib/db/vector-query.ts`)
 * every other production route already uses -- never the disposable
 * `qa_experiment` schema's dedicated higher-privileged pool.
 */
export class PostgresQaChunkRepository implements QaChunkRepository {
  async searchSemanticCandidates(
    vector: number[],
    limit: number,
    mode: "exact" | "hnsw",
    companyTicker: string | null = null,
  ): Promise<QaChunkCandidate[]> {
    const companyJoin = companyTicker ? "JOIN app.current_companies c ON c.id = qc.company_id" : "";
    const companyFilter = companyTicker ? "WHERE c.ticker = $3" : "";
    const params: unknown[] = [vectorLiteral(vector), limit];
    if (companyTicker) params.push(companyTicker);

    const sql = `
      SELECT
        qc.id AS chunk_id,
        qc.report_id AS report_id,
        qc.company_id AS company_id,
        qc.chunk_index AS chunk_index,
        (1 - (qc.embedding <=> $1::vector)) AS similarity,
        qc.text AS text,
        qc.section_heading AS section_heading,
        qc.page_start AS page_start,
        qc.page_end AS page_end,
        qc.token_count AS token_count
      FROM app.current_qa_chunks qc
      ${companyJoin}
      ${companyFilter}
      ORDER BY qc.embedding <=> $1::vector
      LIMIT $2
    `;
    const rows = await queryVector(sql, params, mode);
    return this.parseCandidateRows(rows, /* semantic */ true);
  }

  async searchLexicalCandidates(
    queryText: string,
    limit: number,
    companyTicker: string | null = null,
  ): Promise<QaChunkCandidate[]> {
    if (!queryText) return [];
    const companyJoin = companyTicker ? "JOIN app.current_companies c ON c.id = qc.company_id" : "";
    const companyFilter = companyTicker ? "AND c.ticker = $2" : "";
    const params: unknown[] = [queryText];
    if (companyTicker) params.push(companyTicker);
    params.push(limit);
    const limitIdx = params.length;

    const sql = `
      SELECT
        qc.id AS chunk_id,
        qc.report_id AS report_id,
        qc.company_id AS company_id,
        qc.chunk_index AS chunk_index,
        ts_rank(qc.search_vector, websearch_to_tsquery('english', $1)) AS rank,
        qc.text AS text,
        qc.section_heading AS section_heading,
        qc.page_start AS page_start,
        qc.page_end AS page_end,
        qc.token_count AS token_count
      FROM app.current_qa_chunks qc
      ${companyJoin}
      WHERE qc.search_vector @@ websearch_to_tsquery('english', $1)
      ${companyFilter}
      ORDER BY rank DESC, qc.id ASC
      LIMIT $${limitIdx}
    `;
    const rows = await query(sql, params);
    const parsed = rows.map((row, index) => {
      const parsedRank = qaChunkLexicalCandidateRowSchema.safeParse({ chunk_id: row.chunk_id, rank: row.rank });
      if (!parsedRank.success) {
        throw new MalformedRowError(`qa-chunk-lexical-candidate[${index}]`, parsedRank.error.message);
      }
      const parsedRow = qaChunkCandidateRowSchema.safeParse({ ...row, similarity: 0 });
      if (!parsedRow.success) {
        throw new MalformedRowError(`qa-chunk-lexical-candidate[${index}]`, parsedRow.error.message);
      }
      return { data: parsedRow.data, rankPosition: index + 1 };
    });
    return parsed.map(({ data, rankPosition }) => ({
      chunkId: data.chunk_id,
      reportId: data.report_id,
      companyId: data.company_id,
      chunkIndex: data.chunk_index,
      similarity: null,
      text: data.text,
      sectionHeading: data.section_heading,
      pageStart: data.page_start,
      pageEnd: data.page_end,
      tokenCount: data.token_count,
      memberPassageIds: [],
      semanticRankPosition: null,
      lexicalRankPosition: rankPosition,
      fusedScore: null,
    }));
  }

  async resolveCitations(chunkIds: readonly string[]): Promise<Map<string, QaChunkCitation>> {
    if (chunkIds.length === 0) return new Map();
    const sql = `
      SELECT
        qc.id AS chunk_id,
        c.id AS company_id,
        c.ticker AS company_ticker,
        c.name AS company_name,
        r.id AS report_id,
        r.title AS report_title,
        r.period_end AS report_period_end,
        qc.page_start AS page_start,
        qc.page_end AS page_end,
        qc.section_heading AS section_heading
      FROM app.current_qa_chunks qc
      JOIN app.current_reports r ON r.id = qc.report_id
      JOIN app.current_companies c ON c.id = qc.company_id
      WHERE qc.id = ANY($1::uuid[])
    `;
    const rows = await query(sql, [chunkIds as string[]]);
    const memberIds = await this.resolveMemberPassageIds(chunkIds);

    const result = new Map<string, QaChunkCitation>();
    rows.forEach((row, index) => {
      const parsed = qaChunkCitationContextRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`qa-chunk-citation[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      const citation: QaChunkCitation = {
        chunkId: data.chunk_id,
        companyId: data.company_id,
        companyTicker: data.company_ticker,
        companyName: data.company_name,
        reportId: data.report_id,
        reportTitle: data.report_title,
        reportPeriodEnd: data.report_period_end,
        pageStart: data.page_start,
        pageEnd: data.page_end,
        sectionHeading: data.section_heading,
        memberPassageIds: memberIds.get(data.chunk_id) ?? [],
        label: "",
      };
      citation.label = formatQaChunkCitationLabel(citation);
      result.set(data.chunk_id, citation);
    });
    return result;
  }

  async resolveMemberPassageIds(chunkIds: readonly string[]): Promise<Map<string, string[]>> {
    if (chunkIds.length === 0) return new Map();
    const rows = await query(
      `SELECT qa_chunk_id, passage_id FROM app.current_qa_chunk_passages
       WHERE qa_chunk_id = ANY($1::uuid[]) ORDER BY qa_chunk_id, member_order`,
      [chunkIds as string[]],
    );
    const result = new Map<string, string[]>();
    rows.forEach((row, index) => {
      const parsed = qaChunkMemberPassageRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`qa-chunk-member-passage[${index}]`, parsed.error.message);
      }
      const arr = result.get(parsed.data.qa_chunk_id) ?? [];
      arr.push(parsed.data.passage_id);
      result.set(parsed.data.qa_chunk_id, arr);
    });
    return result;
  }

  private parseCandidateRows(rows: unknown[], semantic: boolean): QaChunkCandidate[] {
    return rows.map((row, index) => {
      const parsed = qaChunkCandidateRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`qa-chunk-candidate[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      return {
        chunkId: data.chunk_id,
        reportId: data.report_id,
        companyId: data.company_id,
        chunkIndex: data.chunk_index,
        similarity: data.similarity,
        text: data.text,
        sectionHeading: data.section_heading,
        pageStart: data.page_start,
        pageEnd: data.page_end,
        tokenCount: data.token_count,
        memberPassageIds: [],
        semanticRankPosition: semantic ? index + 1 : null,
        lexicalRankPosition: null,
        fusedScore: null,
      } satisfies QaChunkCandidate;
    });
  }
}
