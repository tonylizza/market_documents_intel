import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { getRetrievalConfig } from "@/lib/config/retrieval-config";

const ENV_KEYS = [
  "SEMANTIC_CANDIDATE_LIMIT",
  "LEXICAL_CANDIDATE_LIMIT",
  "RETRIEVAL_CONTEXT_EXPANSION_MULTIPLIER",
  "RETRIEVAL_CONTEXTS_PER_PASSAGE",
  "RETRIEVAL_RRF_K",
  "RETRIEVAL_MIN_SIMILARITY",
  "SEMANTIC_RETRIEVAL_MODE",
  "PASSAGE_SEARCH_DEFAULT_MODE",
] as const;

describe("getRetrievalConfig", () => {
  const originalEnv: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const key of ENV_KEYS) {
      originalEnv[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    for (const key of ENV_KEYS) {
      if (originalEnv[key] === undefined) delete process.env[key];
      else process.env[key] = originalEnv[key];
    }
  });

  it("defaults to keyword as the search mode when unset", () => {
    expect(getRetrievalConfig().defaultSearchMode).toBe("keyword");
  });

  it("defaults to hnsw as the vector search mode (per the Milestone 7B.1 benchmark)", () => {
    expect(getRetrievalConfig().vectorSearchMode).toBe("hnsw");
  });

  it("falls back to the default mode when PASSAGE_SEARCH_DEFAULT_MODE is invalid", () => {
    process.env.PASSAGE_SEARCH_DEFAULT_MODE = "not-a-real-mode";
    expect(getRetrievalConfig().defaultSearchMode).toBe("keyword");
  });

  it("accepts a valid override for PASSAGE_SEARCH_DEFAULT_MODE", () => {
    process.env.PASSAGE_SEARCH_DEFAULT_MODE = "hybrid";
    expect(getRetrievalConfig().defaultSearchMode).toBe("hybrid");
  });

  it("falls back to a documented default when SEMANTIC_RETRIEVAL_MODE is invalid", () => {
    process.env.SEMANTIC_RETRIEVAL_MODE = "bogus";
    expect(getRetrievalConfig().vectorSearchMode).toBe("hnsw");
  });

  it("accepts exact/auto overrides for SEMANTIC_RETRIEVAL_MODE", () => {
    process.env.SEMANTIC_RETRIEVAL_MODE = "exact";
    expect(getRetrievalConfig().vectorSearchMode).toBe("exact");
    process.env.SEMANTIC_RETRIEVAL_MODE = "auto";
    expect(getRetrievalConfig().vectorSearchMode).toBe("auto");
  });

  it("parses numeric overrides and ignores invalid ones", () => {
    process.env.RETRIEVAL_RRF_K = "30";
    expect(getRetrievalConfig().rrfK).toBe(30);
    process.env.RETRIEVAL_RRF_K = "not-a-number";
    expect(getRetrievalConfig().rrfK).toBe(60);
  });

  it("parses a float override for the minimum similarity threshold", () => {
    process.env.RETRIEVAL_MIN_SIMILARITY = "0.6";
    expect(getRetrievalConfig().minimumSemanticSimilarity).toBe(0.6);
  });
});
