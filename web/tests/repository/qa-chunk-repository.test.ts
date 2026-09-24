import { randomUUID } from "node:crypto";
import { Client } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { closePool, query } from "@/lib/db/pool";
import { PostgresQaChunkRepository } from "@/lib/repositories/postgres-qa-chunk-repository";
import { seedAppDatabase } from "../fixtures/seed-app-database";
import { SEED_APP_DATABASE_URL } from "../fixtures/env";

/**
 * Track 7F.10: `searchSemanticCandidates` in "hnsw" mode reads
 * `app.current_qa_chunk_vectors` (an index-usable view over the shared
 * `app_artifacts.qa_chunks` generation), through the real `app_readonly`
 * pool. These tests pin that it returns exactly what the exact
 * `app.current_qa_chunks` path returns. Two traps are seeded on purpose:
 * artifact rows the active publication does not reference (a different
 * generation, nearest to the query), and a legacy publication whose
 * embeddings are inline on the thin rows (the fallback path).
 */

const DIM = 384;
const TEST_VERSION = "qa_chunk_repo_test_7f10";
const repository = new PostgresQaChunkRepository();

function basis(i: number, j: number, mix: number): string {
  const v = new Array<number>(DIM).fill(0);
  v[i] = 1;
  v[j] = mix;
  const norm = Math.sqrt(1 + mix * mix);
  return `[${v.map((x) => x / norm).join(",")}]`;
}

function queryVector(): number[] {
  const v = new Array<number>(DIM).fill(0);
  v[0] = 1;
  v[1] = 0.3;
  return v;
}

let client: Client;
let publicationId: string;
let reports: { id: string; companyId: string; sourceReportId: string; ticker: string }[];
const sharedChunkIds: string[] = [];

async function insertArtifact(sourceReportId: string, chunkIndex: number, embedding: string): Promise<string> {
  const id = randomUUID();
  await client.query(
    `INSERT INTO app_artifacts.qa_chunks
       (id, source_report_id, chunk_index, qa_chunking_artifact_version, text, section_heading, page_start,
        page_end, token_count, truncation_policy, embedding_model, embedding_model_revision, dimensions,
        embedding_text_hash, embedding, vector_norm, content_hash)
     VALUES ($1, $2, $3, $4, $5, 'Heading', 1, 1, 10, 'none', 'test-model', 'r1', ${DIM}, $6, $7::vector, 1, 'h')`,
    [id, sourceReportId, chunkIndex, TEST_VERSION, `artifact chunk ${chunkIndex}`, `hash-${id}`, embedding],
  );
  return id;
}

beforeAll(async () => {
  ({ publicationId } = await seedAppDatabase());
  client = new Client({ connectionString: SEED_APP_DATABASE_URL });
  await client.connect();
  await client.query(`DELETE FROM app_artifacts.qa_chunks WHERE qa_chunking_artifact_version = $1`, [TEST_VERSION]);

  const rows = await client.query(
    `SELECT r.id, r.company_id, r.source_report_id, c.ticker
       FROM app.reports r JOIN app.companies c ON c.id = r.company_id
      WHERE r.publication_id = $1 ORDER BY c.ticker, r.period_end LIMIT 4`,
    [publicationId],
  );
  reports = rows.rows.map((r) => ({
    id: r.id,
    companyId: r.company_id,
    sourceReportId: r.source_report_id,
    ticker: r.ticker,
  }));

  // 12 chunks of the active publication, at graded distances from the query.
  for (let i = 0; i < 12; i += 1) {
    const report = reports[i % reports.length];
    const artifactId = await insertArtifact(report.sourceReportId, i, basis(0, 2 + i, 0.2 + i * 0.25));
    const thinId = randomUUID();
    await client.query(
      `INSERT INTO app.qa_chunks (id, publication_id, report_id, company_id, chunk_index, qa_chunking_artifact_id)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [thinId, publicationId, report.id, report.companyId, i, artifactId],
    );
    sharedChunkIds.push(thinId);
  }
  // Trap: artifact rows nearest to the query that NO active thin row references.
  for (let i = 0; i < 5; i += 1) {
    await insertArtifact(reports[0].sourceReportId, 100 + i, basis(0, 1, 0.3));
  }
});

afterAll(async () => {
  await client.query(`DELETE FROM app.qa_chunks WHERE publication_id = $1`, [publicationId]);
  await client.query(`DELETE FROM app_artifacts.qa_chunks WHERE qa_chunking_artifact_version = $1`, [TEST_VERSION]);
  await client.end();
  await closePool();
});

describe("PostgresQaChunkRepository.searchSemanticCandidates (Track 7F.10 vector view)", () => {
  it("app_readonly can read app.current_qa_chunk_vectors, which holds exactly the active shared chunks", async () => {
    // Guards against the hnsw path silently falling back to the exact query:
    // the view must be granted and populated, not merely equivalent.
    const rows = await query<{ id: string }>(`SELECT id FROM app.current_qa_chunk_vectors`);
    expect(rows.map((r) => r.id).sort()).toEqual([...sharedChunkIds].sort());
  });

  it("hnsw mode returns exactly the exact-mode top-k, excluding unreferenced artifact rows", async () => {
    const exact = await repository.searchSemanticCandidates(queryVector(), 8, "exact");
    const hnsw = await repository.searchSemanticCandidates(queryVector(), 8, "hnsw");

    expect(exact).toHaveLength(8);
    expect(hnsw.map((c) => c.chunkId)).toEqual(exact.map((c) => c.chunkId));
    hnsw.forEach((c, i) => {
      expect(c.similarity).toBeCloseTo(exact[i].similarity ?? NaN, 6);
      expect(c.semanticRankPosition).toBe(i + 1);
      expect(sharedChunkIds).toContain(c.chunkId);
    });
    // Strictly non-increasing similarity after the exact re-sort.
    for (let i = 1; i < hnsw.length; i += 1) {
      expect(hnsw[i].similarity!).toBeLessThanOrEqual(hnsw[i - 1].similarity!);
    }
    expect(hnsw[0].text).toMatch(/^artifact chunk /);
  });

  it("company-scoped search stays on the exact path and is scoped", async () => {
    const ticker = reports[0].ticker;
    const scoped = await repository.searchSemanticCandidates(queryVector(), 20, "hnsw", ticker);
    expect(scoped.length).toBeGreaterThan(0);
    const companyIds = new Set(reports.filter((r) => r.ticker === ticker).map((r) => r.companyId));
    scoped.forEach((c) => expect(companyIds.has(c.companyId)).toBe(true));
  });

  it("falls back to the exact view when the active publication stores embeddings inline", async () => {
    const legacyPublicationId = randomUUID();
    await client.query(
      `INSERT INTO app_internal.publications
         (id, publication_version, source_database_identifier, source_schema_version,
          source_configuration_hash, status, started_at, completed_at, company_count, report_count, comparison_count)
       VALUES ($1, 'legacy-inline-7f10', 'postgresql://localhost/test', 'test', 'test-hash',
               'READY', now(), now(), 0, 0, 0)`,
      [legacyPublicationId],
    );
    const legacyIds: string[] = [];
    for (let i = 0; i < 3; i += 1) {
      const id = randomUUID();
      await client.query(
        `INSERT INTO app.qa_chunks (id, publication_id, report_id, company_id, chunk_index, text, section_heading,
           page_start, page_end, token_count, truncation_policy, embedding_model, embedding_model_revision,
           dimensions, embedding_text_hash, embedding, vector_norm)
         VALUES ($1, $2, $3, $4, $5, 'inline chunk', NULL, 1, 1, 10, 'none', 'test-model', 'r1', ${DIM}, 'h',
                 $6::vector, 1)`,
        [id, legacyPublicationId, reports[0].id, reports[0].companyId, i, basis(0, 50 + i, 0.5)],
      );
      legacyIds.push(id);
    }
    await client.query(`UPDATE app_internal.application_state SET active_publication_id = $1`, [legacyPublicationId]);
    try {
      const hnsw = await repository.searchSemanticCandidates(queryVector(), 8, "hnsw");
      expect(hnsw.map((c) => c.chunkId).sort()).toEqual([...legacyIds].sort());
    } finally {
      await client.query(`UPDATE app_internal.application_state SET active_publication_id = $1`, [publicationId]);
      await client.query(`DELETE FROM app_internal.publications WHERE id = $1`, [legacyPublicationId]);
    }
  });
});
