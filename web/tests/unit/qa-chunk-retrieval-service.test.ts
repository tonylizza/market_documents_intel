import { describe, expect, it, vi } from "vitest";
import { retrieveQaEvidence } from "@/lib/services/qa/qa-chunk-retrieval-service";
import type { QaChunkCandidate, QaChunkCitation } from "@/lib/domain/qa-chunk";
import type { QaChunkRepository } from "@/lib/repositories/qa-chunk-repository";
import type { QueryEmbeddingProvider } from "@/lib/services/query-embedding-provider";
import type { QaChunkConfig } from "@/lib/config/qa-chunk-config";

function candidate(overrides: Partial<QaChunkCandidate> = {}): QaChunkCandidate {
  return {
    chunkId: "chunk-1",
    reportId: "report-1",
    companyId: "company-1",
    chunkIndex: 0,
    similarity: 0.9,
    text: "chunk text",
    sectionHeading: null,
    pageStart: 1,
    pageEnd: 2,
    tokenCount: 300,
    memberPassageIds: [],
    semanticRankPosition: 1,
    lexicalRankPosition: null,
    fusedScore: null,
    ...overrides,
  };
}

function citation(chunkId: string): QaChunkCitation {
  return {
    chunkId,
    companyId: "company-1",
    companyTicker: "ACT",
    companyName: "Acme Corp",
    reportId: "report-1",
    reportTitle: "2024 Annual Report",
    reportPeriodEnd: "2024-12-31",
    pageStart: 1,
    pageEnd: 2,
    sectionHeading: null,
    memberPassageIds: ["p1"],
    label: "ACT, 2024 report, pp. 1-2",
  };
}

function fakeEmbeddingProvider(): QueryEmbeddingProvider {
  return {
    embedQuery: vi.fn().mockResolvedValue({
      vector: [0.1, 0.2],
      model: "test-model",
      modelRevision: "rev",
      dimensions: 2,
      normalizedQueryText: "question",
      latencyMs: 1,
      tokenCount: 2,
      provider: "test",
    }),
  };
}

function baseConfig(overrides: Partial<QaChunkConfig> = {}): QaChunkConfig {
  return {
    semanticCandidateLimit: 25,
    lexicalCandidateLimit: 25,
    lexicalFusionEnabled: false,
    rrfK: 60,
    maxEvidenceChunks: 5,
    vectorSearchMode: "hnsw",
    minimumSemanticSimilarity: 0.71,
    ...overrides,
  };
}

describe("retrieveQaEvidence", () => {
  it("returns empty evidence with zero candidates when semantic search finds nothing", async () => {
    const repository: QaChunkRepository = {
      searchSemanticCandidates: vi.fn().mockResolvedValue([]),
      searchLexicalCandidates: vi.fn().mockResolvedValue([]),
      resolveCitations: vi.fn().mockResolvedValue(new Map()),
      resolveMemberPassageIds: vi.fn().mockResolvedValue(new Map()),
    };
    const result = await retrieveQaEvidence("a question", fakeEmbeddingProvider(), repository, baseConfig());
    expect(result.evidence).toEqual([]);
    expect(result.candidateCount).toBe(0);
  });

  it("uses semantic-only ranking when lexical fusion is disabled", async () => {
    const c1 = candidate({ chunkId: "a", semanticRankPosition: 1 });
    const c2 = candidate({ chunkId: "b", semanticRankPosition: 2, chunkIndex: 50, pageStart: 50, pageEnd: 51 });
    const repository: QaChunkRepository = {
      searchSemanticCandidates: vi.fn().mockResolvedValue([c1, c2]),
      searchLexicalCandidates: vi.fn(),
      resolveCitations: vi.fn().mockResolvedValue(new Map([["a", citation("a")], ["b", citation("b")]])),
      resolveMemberPassageIds: vi.fn().mockResolvedValue(new Map()),
    };
    const result = await retrieveQaEvidence("a question", fakeEmbeddingProvider(), repository, baseConfig());
    expect(repository.searchLexicalCandidates).not.toHaveBeenCalled();
    expect(result.evidence.map((e) => e.chunkId)).toEqual(["a", "b"]);
    expect(result.lexicalFusionUsed).toBe(false);
  });

  it("fuses lexical and semantic rankings when lexical fusion is enabled", async () => {
    const semantic = [candidate({ chunkId: "a", semanticRankPosition: 2 }), candidate({ chunkId: "b", semanticRankPosition: 1, chunkIndex: 50, pageStart: 50, pageEnd: 51 })];
    const lexical = [candidate({ chunkId: "a", semanticRankPosition: null, lexicalRankPosition: 1 })];
    const repository: QaChunkRepository = {
      searchSemanticCandidates: vi.fn().mockResolvedValue(semantic),
      searchLexicalCandidates: vi.fn().mockResolvedValue(lexical),
      resolveCitations: vi.fn().mockResolvedValue(new Map([["a", citation("a")], ["b", citation("b")]])),
      resolveMemberPassageIds: vi.fn().mockResolvedValue(new Map()),
    };
    const result = await retrieveQaEvidence(
      "a question",
      fakeEmbeddingProvider(),
      repository,
      baseConfig({ lexicalFusionEnabled: true }),
    );
    expect(repository.searchLexicalCandidates).toHaveBeenCalledWith("a question", 25, null);
    expect(result.lexicalFusionUsed).toBe(true);
    // "a" appears in both rankings so it must fuse to the top.
    expect(result.evidence[0].chunkId).toBe("a");
  });

  it("drops semantic candidates below the minimum similarity floor", async () => {
    const strong = candidate({ chunkId: "strong", similarity: 0.9, semanticRankPosition: 1 });
    const weak = candidate({ chunkId: "weak", similarity: 0.3, semanticRankPosition: 2 });
    const repository: QaChunkRepository = {
      searchSemanticCandidates: vi.fn().mockResolvedValue([strong, weak]),
      searchLexicalCandidates: vi.fn(),
      resolveCitations: vi.fn().mockResolvedValue(new Map([["strong", citation("strong")], ["weak", citation("weak")]])),
      resolveMemberPassageIds: vi.fn().mockResolvedValue(new Map()),
    };
    const result = await retrieveQaEvidence(
      "q",
      fakeEmbeddingProvider(),
      repository,
      baseConfig({ minimumSemanticSimilarity: 0.71 }),
    );
    expect(result.evidence.map((e) => e.chunkId)).toEqual(["strong"]);
  });

  it("does NOT apply the similarity floor when the search is scoped to a company", async () => {
    // Company-scoped search shrinks the candidate pool and lowers the
    // achievable max similarity for a genuinely relevant match -- the
    // floor must not reject an on-topic, company-scoped result just
    // because it scores below the unscoped-calibrated threshold.
    const belowUnscopedFloor = candidate({ chunkId: "act-chunk", similarity: 0.6, semanticRankPosition: 1 });
    const repository: QaChunkRepository = {
      searchSemanticCandidates: vi.fn().mockResolvedValue([belowUnscopedFloor]),
      searchLexicalCandidates: vi.fn(),
      resolveCitations: vi.fn().mockResolvedValue(new Map([["act-chunk", citation("act-chunk")]])),
      resolveMemberPassageIds: vi.fn().mockResolvedValue(new Map()),
    };
    const result = await retrieveQaEvidence(
      "q",
      fakeEmbeddingProvider(),
      repository,
      baseConfig({ minimumSemanticSimilarity: 0.71 }),
      "ACT",
    );
    expect(result.evidence.map((e) => e.chunkId)).toEqual(["act-chunk"]);
  });

  it("returns INSUFFICIENT_EVIDENCE-shaped empty result when every candidate is below the floor", async () => {
    const weak = candidate({ chunkId: "weak", similarity: 0.2, semanticRankPosition: 1 });
    const repository: QaChunkRepository = {
      searchSemanticCandidates: vi.fn().mockResolvedValue([weak]),
      searchLexicalCandidates: vi.fn(),
      resolveCitations: vi.fn(),
      resolveMemberPassageIds: vi.fn(),
    };
    const result = await retrieveQaEvidence(
      "q",
      fakeEmbeddingProvider(),
      repository,
      baseConfig({ minimumSemanticSimilarity: 0.71 }),
    );
    expect(result.evidence).toEqual([]);
    expect(result.candidateCount).toBe(0);
  });

  it("scopes semantic and lexical search to the given company at the SQL level, not post-hoc", async () => {
    const repository: QaChunkRepository = {
      searchSemanticCandidates: vi.fn().mockResolvedValue([]),
      searchLexicalCandidates: vi.fn().mockResolvedValue([]),
      resolveCitations: vi.fn().mockResolvedValue(new Map()),
      resolveMemberPassageIds: vi.fn().mockResolvedValue(new Map()),
    };
    await retrieveQaEvidence(
      "q",
      fakeEmbeddingProvider(),
      repository,
      baseConfig({ lexicalFusionEnabled: true }),
      "ACT",
    );
    expect(repository.searchSemanticCandidates).toHaveBeenCalledWith(expect.any(Array), 25, "hnsw", "ACT");
    expect(repository.searchLexicalCandidates).toHaveBeenCalledWith("q", 25, "ACT");
  });

  it("passes the bounded candidate limit through to the repository", async () => {
    const repository: QaChunkRepository = {
      searchSemanticCandidates: vi.fn().mockResolvedValue([]),
      searchLexicalCandidates: vi.fn().mockResolvedValue([]),
      resolveCitations: vi.fn().mockResolvedValue(new Map()),
      resolveMemberPassageIds: vi.fn().mockResolvedValue(new Map()),
    };
    await retrieveQaEvidence("q", fakeEmbeddingProvider(), repository, baseConfig({ semanticCandidateLimit: 30 }));
    expect(repository.searchSemanticCandidates).toHaveBeenCalledWith(expect.any(Array), 30, "hnsw", null);
  });

  it("applies overlap-aware dedup and never exceeds maxEvidenceChunks", async () => {
    const overlapping = Array.from({ length: 10 }, (_, i) =>
      candidate({ chunkId: `c${i}`, chunkIndex: i, semanticRankPosition: i + 1 }),
    );
    const citations = new Map(overlapping.map((c) => [c.chunkId, citation(c.chunkId)]));
    const repository: QaChunkRepository = {
      searchSemanticCandidates: vi.fn().mockResolvedValue(overlapping),
      searchLexicalCandidates: vi.fn(),
      resolveCitations: vi.fn().mockResolvedValue(citations),
      resolveMemberPassageIds: vi.fn().mockResolvedValue(new Map()),
    };
    const result = await retrieveQaEvidence(
      "q",
      fakeEmbeddingProvider(),
      repository,
      baseConfig({ maxEvidenceChunks: 3 }),
    );
    // All 10 candidates share adjacent chunk indices in the same report --
    // overlap-aware dedup must collapse them to one group, well under the
    // maxEvidenceChunks cap.
    expect(result.evidence.length).toBeLessThanOrEqual(3);
  });
});
