import { describe, expect, it } from "vitest";
import { generateCandidates } from "@/lib/services/qa/candidate-generation";
import { getQaConfig } from "@/lib/config/qa-config";
import { parsePassageSearchParams } from "@/lib/services/passage-search-params";
import type { SemanticRetrievalRepository } from "@/lib/repositories/semantic-retrieval-repository";
import type { LexicalCandidate, RetrievalContext, SemanticCandidate } from "@/lib/domain/retrieval";
import type { QaChunkRetrievalRepository, ChunkHit } from "@/lib/repositories/qa-chunk-retrieval-repository";

function context(overrides: Partial<RetrievalContext> = {}): RetrievalContext {
  return {
    contextId: "ctx-1",
    passageId: "passage-1",
    contextType: "COMPARISON_LINKED",
    passageComparisonId: "pc-1",
    reportComparisonId: "rc-1",
    reportId: "report-1",
    companyId: "company-1",
    companyTicker: "ACT",
    companyName: "AfroCentric Investment Corporation Limited",
    reportSide: "LATER",
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    reportPeriodEnd: "2024-12-31",
    earlierPeriodEnd: "2023-12-31",
    laterPeriodEnd: "2024-12-31",
    heading: "Liquidity risk",
    passageType: "PARAGRAPH",
    structuredContentCategory: null,
    primaryNarrativeEligible: true,
    featureEligible: true,
    reportSideQuality: "GOOD",
    alignmentChangeQuality: "GOOD",
    collisionFlag: false,
    splitMergeFlag: false,
    irregularGapFlag: false,
    firstPageNumber: 10,
    lastPageNumber: 10,
    wordCount: 40,
    text: "The group maintains adequate liquidity headroom and there is no material uncertainty.",
    categories: ["financial_condition"],
    riskSubcategories: [],
    ...overrides,
  };
}

function semanticCandidate(overrides: Partial<SemanticCandidate> = {}): SemanticCandidate {
  return {
    passageId: "passage-1",
    similarity: 0.8,
    heading: "Liquidity risk",
    text: "The group maintains adequate liquidity headroom and there is no material uncertainty.",
    wordCount: 40,
    hasLanguageSignal: true,
    headingFrequency: 1,
    ...overrides,
  };
}

function lexicalCandidate(overrides: Partial<LexicalCandidate> = {}): LexicalCandidate {
  return {
    passageId: "passage-1",
    passageComparisonId: "pc-1",
    rank: 0.5,
    rankPosition: 1,
    ...overrides,
  };
}

interface FakeRepoConfig {
  lexical?: LexicalCandidate[];
  semantic?: SemanticCandidate[];
  contexts?: RetrievalContext[];
}

function fakeRepo(cfg: FakeRepoConfig): SemanticRetrievalRepository & { calls: Record<string, unknown[]> } {
  const calls: Record<string, unknown[]> = { searchLexicalCandidates: [], searchSemanticCandidates: [], expandRetrievalContexts: [] };
  return {
    calls,
    async searchLexicalCandidates(params, limit) {
      calls.searchLexicalCandidates.push({ params, limit });
      return cfg.lexical ?? [];
    },
    async searchSemanticCandidates(vector, params, limit, mode) {
      calls.searchSemanticCandidates.push({ vector, params, limit, mode });
      return cfg.semantic ?? [];
    },
    async expandRetrievalContexts(passageIds, params) {
      calls.expandRetrievalContexts.push({ passageIds, params });
      return cfg.contexts ?? [];
    },
    async resolveVectorSearchMode() {
      return "hnsw";
    },
  };
}

const params = parsePassageSearchParams({ q: "liquidity risk" });
const embedding = { vector: [0.1, 0.2], model: "test", modelRevision: "1", dimensions: 2, normalizedQueryText: "liquidity risk", latencyMs: 5, tokenCount: 2, provider: "test" };

describe("generateCandidates", () => {
  it("merges a passage found by both keyword and semantic sources into one candidate with both sources recorded", async () => {
    const repo = fakeRepo({
      lexical: [lexicalCandidate()],
      semantic: [semanticCandidate()],
      contexts: [context()],
    });
    const candidates = await generateCandidates(repo, "liquidity risk", embedding, params, getQaConfig(), "pub-1");
    expect(candidates).toHaveLength(1);
    expect(candidates[0].sources).toEqual(expect.arrayContaining(["keyword", "semantic"]));
  });

  it("preserves raw lexical rank, raw/adjusted semantic rank, quality factor, and explanation code", async () => {
    const repo = fakeRepo({
      lexical: [lexicalCandidate({ rankPosition: 3 })],
      semantic: [semanticCandidate({ wordCount: 40, hasLanguageSignal: true })],
      contexts: [context()],
    });
    const candidates = await generateCandidates(repo, "liquidity risk", embedding, params, getQaConfig(), "pub-1");
    const candidate = candidates[0];
    expect(candidate.lexicalRankPosition).toBe(3);
    expect(candidate.semanticRawRank).not.toBeNull();
    expect(candidate.semanticAdjustedRank).not.toBeNull();
    expect(candidate.semanticRawSimilarity).toBe(0.8);
    expect(candidate.qualityFactor).not.toBeNull();
    expect(candidate.qualityExplanationCode).not.toBeNull();
    expect(candidate.rrfRank).not.toBeNull();
  });

  it("produces one candidate per retrieval context, not per passage, when a passage expands into multiple contexts", async () => {
    const repo = fakeRepo({
      lexical: [lexicalCandidate()],
      semantic: [],
      contexts: [
        context({ contextId: "ctx-1", contextType: "COMPARISON_LINKED" }),
        context({ contextId: "ctx-2", contextType: "REPORT_ONLY", passageComparisonId: null, reportComparisonId: null, reportSide: null }),
      ],
    });
    const candidates = await generateCandidates(repo, "liquidity risk", null, params, getQaConfig(), "pub-1");
    expect(candidates).toHaveLength(2);
    expect(candidates.map((c) => c.retrievalContextId).sort()).toEqual(["ctx-1", "ctx-2"]);
  });

  it("uses retrievalContextId, not passageId, as the citation identity", async () => {
    const repo = fakeRepo({ lexical: [lexicalCandidate()], contexts: [context({ contextId: "ctx-distinct", passageId: "passage-1" })] });
    const candidates = await generateCandidates(repo, "liquidity risk", null, params, getQaConfig(), "pub-1");
    expect(candidates[0].citation.retrievalContextId).toBe("ctx-distinct");
    expect(candidates[0].candidateId).toBe("ctx-distinct");
  });

  it("degrades to keyword-only when no query embedding is available", async () => {
    const repo = fakeRepo({ lexical: [lexicalCandidate()], contexts: [context()] });
    const candidates = await generateCandidates(repo, "liquidity risk", null, params, getQaConfig(), "pub-1");
    expect(repo.calls.searchSemanticCandidates).toHaveLength(0);
    expect(candidates[0].sources).toEqual(["keyword"]);
    expect(candidates[0].semanticRawSimilarity).toBeNull();
  });

  it("returns an empty array when neither source produces any candidates", async () => {
    const repo = fakeRepo({});
    const candidates = await generateCandidates(repo, "an unrelated topic", null, params, getQaConfig(), "pub-1");
    expect(candidates).toEqual([]);
    expect(repo.calls.expandRetrievalContexts).toHaveLength(0);
  });

  it("passes the configured candidate limit through to both repository sources", async () => {
    const repo = fakeRepo({ lexical: [lexicalCandidate()], semantic: [semanticCandidate()], contexts: [context()] });
    const config = getQaConfig();
    await generateCandidates(repo, "liquidity risk", embedding, params, config, "pub-1");
    // Milestone 7B.1c Phase 1: the lexical request is multiplied by
    // `LEXICAL_FANOUT_LIMIT_MULTIPLIER` to absorb `searchLexicalCandidates`'
    // pre-dedup report-comparison join fan-out (see `candidate-generation.ts`);
    // the semantic request is unaffected, since `searchSemanticCandidates`
    // has no equivalent join.
    expect((repo.calls.searchLexicalCandidates[0] as { limit: number }).limit).toBe(config.candidateLimitPerSource * 4);
    expect((repo.calls.searchSemanticCandidates[0] as { limit: number }).limit).toBe(config.candidateLimitPerSource);
  });

  it("propagates the same structured filter params to every repository call unchanged", async () => {
    const scopedParams = parsePassageSearchParams({ q: "liquidity risk", company: "ACT" });
    const repo = fakeRepo({ lexical: [lexicalCandidate()], contexts: [context()] });
    await generateCandidates(repo, "liquidity risk", null, scopedParams, getQaConfig(), "pub-1");
    expect((repo.calls.searchLexicalCandidates[0] as { params: typeof scopedParams }).params.company).toBe("ACT");
    expect((repo.calls.expandRetrievalContexts[0] as { params: typeof scopedParams }).params.company).toBe("ACT");
  });

  it("carries the active publication id into every candidate's citation", async () => {
    const repo = fakeRepo({ lexical: [lexicalCandidate()], contexts: [context()] });
    const candidates = await generateCandidates(repo, "liquidity risk", null, params, getQaConfig(), "pub-42");
    expect(candidates[0].citation.publicationId).toBe("pub-42");
  });

  it("produces a deterministic, stable candidate order across repeated calls with the same input", async () => {
    const repo = fakeRepo({
      lexical: [lexicalCandidate()],
      semantic: [semanticCandidate()],
      contexts: [context()],
    });
    const first = await generateCandidates(repo, "liquidity risk", embedding, params, getQaConfig(), "pub-1");
    const second = await generateCandidates(repo, "liquidity risk", embedding, params, getQaConfig(), "pub-1");
    expect(first.map((c) => c.candidateId)).toEqual(second.map((c) => c.candidateId));
  });
});

function fakeChunkRepo(hits: ChunkHit[]): QaChunkRetrievalRepository & { calls: unknown[] } {
  const calls: unknown[] = [];
  return {
    calls,
    async searchChunkCandidates(vector, limit, strategies) {
      calls.push({ vector, limit, strategies });
      return hits;
    },
  } as QaChunkRetrievalRepository & { calls: unknown[] };
}

describe("generateCandidates -- Milestone 7B.1d chunkOptions (experimental, opt-in)", () => {
  it("omitting chunkOptions never queries the chunk repository (default behavior unchanged)", async () => {
    const repo = fakeRepo({ lexical: [lexicalCandidate()], contexts: [context()] });
    const candidates = await generateCandidates(repo, "liquidity risk", embedding, params, getQaConfig(), "pub-1");
    expect(candidates[0].sources).not.toContain("chunk");
    expect(candidates[0].chunkStrategy ?? null).toBeNull();
  });

  it("a passage surfaced only via a chunk hit still resolves through expandRetrievalContexts and carries chunk provenance", async () => {
    const chunkRepo = fakeChunkRepo([
      { chunkId: "chunk-1", strategy: "LOCAL_WINDOW", similarity: 0.77, members: [{ passageId: "passage-1", role: "ANCHOR" }] },
    ]);
    const repo = fakeRepo({ contexts: [context()] }); // no lexical/semantic hits at all
    const candidates = await generateCandidates(repo, "liquidity risk", embedding, params, getQaConfig(), "pub-1", {
      repo: chunkRepo,
      childLimit: 10,
    });
    expect(candidates).toHaveLength(1);
    expect(candidates[0].sources).toEqual(["chunk"]);
    expect(candidates[0].chunkStrategy).toBe("LOCAL_WINDOW");
    expect(candidates[0].chunkSimilarity).toBe(0.77);
    expect(candidates[0].chunkHitCount).toBe(1);
  });

  it("merges chunk provenance onto a passage already found by keyword/semantic, without dropping those sources", async () => {
    const chunkRepo = fakeChunkRepo([
      { chunkId: "chunk-1", strategy: "HEADING_PLUS_PASSAGE", similarity: 0.9, members: [{ passageId: "passage-1", role: "ANCHOR" }] },
    ]);
    const repo = fakeRepo({ lexical: [lexicalCandidate()], semantic: [semanticCandidate()], contexts: [context()] });
    const candidates = await generateCandidates(repo, "liquidity risk", embedding, params, getQaConfig(), "pub-1", {
      repo: chunkRepo,
      childLimit: 10,
    });
    expect(candidates).toHaveLength(1);
    expect(candidates[0].sources.sort()).toEqual(["chunk", "keyword", "semantic"]);
  });

  it("PREVIOUS/NEXT/HEADING_CONTEXT-only chunk members never introduce a candidate passage on their own", async () => {
    const chunkRepo = fakeChunkRepo([
      { chunkId: "chunk-1", strategy: "LOCAL_WINDOW", similarity: 0.9, members: [{ passageId: "neighbor-passage", role: "PREVIOUS" }] },
    ]);
    const repo = fakeRepo({ contexts: [] });
    const candidates = await generateCandidates(repo, "liquidity risk", embedding, params, getQaConfig(), "pub-1", {
      repo: chunkRepo,
      childLimit: 10,
    });
    expect(candidates).toEqual([]);
    expect(repo.calls.expandRetrievalContexts).toHaveLength(0);
  });

  it("skips the chunk repository entirely when no query embedding is available", async () => {
    const chunkRepo = fakeChunkRepo([]);
    const repo = fakeRepo({ lexical: [lexicalCandidate()], contexts: [context()] });
    await generateCandidates(repo, "liquidity risk", null, params, getQaConfig(), "pub-1", { repo: chunkRepo, childLimit: 10 });
    expect(chunkRepo.calls).toHaveLength(0);
  });
});
