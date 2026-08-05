import { beforeEach, describe, expect, it, vi } from "vitest";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";

const listCompaniesMock = vi.fn();
const retrieveQaEvidenceMock = vi.fn();
const generateAnswerMock = vi.fn();
const checkAndIncrementQuotaMock = vi.fn();

vi.mock("@/lib/repositories/postgres-company-repository", () => ({
  PostgresCompanyRepository: vi.fn().mockImplementation(() => ({ listCompanies: listCompaniesMock })),
}));

vi.mock("@/lib/repositories/postgres-qa-chunk-repository", () => ({
  PostgresQaChunkRepository: vi.fn().mockImplementation(() => ({})),
}));

vi.mock("@/lib/services/qa/qa-chunk-retrieval-service", () => ({
  retrieveQaEvidence: retrieveQaEvidenceMock,
}));

vi.mock("@/lib/services/query-embedding-provider", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/services/query-embedding-provider")>();
  return {
    ...actual,
    createQueryEmbeddingProvider: vi.fn().mockReturnValue({ embedQuery: vi.fn() }),
  };
});

vi.mock("@/lib/services/generation/gemini-provider", () => ({
  GeminiGenerationProvider: vi.fn().mockImplementation(() => ({ generateAnswer: generateAnswerMock })),
}));

vi.mock("@/lib/config/generation-config", () => ({
  getGenerationConfig: vi.fn().mockReturnValue({ apiKey: "test-key", model: "gemini-flash-lite-latest", timeoutMs: 1000, maxRetries: 0, retryBackoffMs: 0 }),
}));

vi.mock("@/lib/services/qa/quota-service", () => ({
  checkAndIncrementQuota: checkAndIncrementQuotaMock,
  loadQuotaLimits: vi.fn().mockReturnValue({ perClientLimit: 10, globalLimit: 100 }),
}));

const { runQaPipeline } = await import("@/lib/services/qa/qa-orchestrator");

function evidenceChunk(chunkId: string): QaEvidenceChunk {
  return {
    chunkId,
    text: "Liquidity risk disclosure text.",
    citation: {
      chunkId,
      companyId: "c1",
      companyTicker: "KP2",
      companyName: "Kelp Co",
      reportId: "r1",
      reportTitle: "2024 Annual Report",
      reportPeriodEnd: "2024-12-31",
      pageStart: 12,
      pageEnd: 14,
      sectionHeading: "Liquidity",
      memberPassageIds: ["p1"],
      label: "KP2, 2024 report, pp. 12-14",
    },
    similarity: 0.9,
    fusedScore: 0.9,
    mergedCandidateCount: 1,
  };
}

describe("runQaPipeline quota gating", () => {
  beforeEach(() => {
    listCompaniesMock.mockReset().mockResolvedValue([]);
    retrieveQaEvidenceMock.mockReset().mockResolvedValue({ evidence: [evidenceChunk("chunk-1")] });
    generateAnswerMock.mockReset().mockResolvedValue({
      status: "ANSWERED",
      answerText: "Liquidity risk is disclosed on pp. 12-14.",
      citedChunkIds: ["chunk-1"],
      unsupportedPortion: null,
    });
    checkAndIncrementQuotaMock.mockReset();
  });

  it("calls Gemini and answers when quota allows", async () => {
    checkAndIncrementQuotaMock.mockResolvedValue({ allowed: true, reason: "within_limit" });
    const result = await runQaPipeline("What is the liquidity risk?", { companyTicker: null, reportYear: null }, "hash-1");
    expect(generateAnswerMock).toHaveBeenCalledTimes(1);
    expect(result.answer.status).toBe("ANSWERED");
  });

  it("no Gemini call in closed failure mode: quota_service_unavailable + allowed=false skips generation entirely", async () => {
    checkAndIncrementQuotaMock.mockResolvedValue({ allowed: false, reason: "quota_service_unavailable" });
    const result = await runQaPipeline("What is the liquidity risk?", { companyTicker: null, reportYear: null }, "hash-1");
    expect(generateAnswerMock).not.toHaveBeenCalled();
    expect(result.answer.status).toBe("PROVIDER_UNAVAILABLE");
  });

  it("evidence preserved in closed failure mode: retrieved evidence/citations are still returned", async () => {
    checkAndIncrementQuotaMock.mockResolvedValue({ allowed: false, reason: "quota_service_unavailable" });
    const result = await runQaPipeline("What is the liquidity risk?", { companyTicker: null, reportYear: null }, "hash-1");
    expect(result.answer.allEvidence).toHaveLength(1);
    expect(result.answer.allEvidence[0].chunkId).toBe("chunk-1");
    expect(result.answer.citedEvidence).toEqual([]);
  });

  it("redacted error response: the client-facing errorDetail never mentions the database or a raw error", async () => {
    checkAndIncrementQuotaMock.mockResolvedValue({ allowed: false, reason: "quota_service_unavailable" });
    const result = await runQaPipeline("What is the liquidity risk?", { companyTicker: null, reportYear: null }, "hash-1");
    expect(result.answer.errorDetail).toBe("Generated answers are temporarily unavailable right now. Supporting excerpts are still shown below.");
    expect(result.answer.errorDetail).not.toMatch(/database|ETIMEDOUT|postgres|neon/i);
  });

  it("client quota exceeded still blocks generation with the per-client message", async () => {
    checkAndIncrementQuotaMock.mockResolvedValue({ allowed: false, reason: "per_client_limit" });
    const result = await runQaPipeline("What is the liquidity risk?", { companyTicker: null, reportYear: null }, "hash-1");
    expect(generateAnswerMock).not.toHaveBeenCalled();
    expect(result.answer.errorDetail).toContain("this browser");
  });

  it("global quota exceeded still blocks generation with the global message", async () => {
    checkAndIncrementQuotaMock.mockResolvedValue({ allowed: false, reason: "global_limit" });
    const result = await runQaPipeline("What is the liquidity risk?", { companyTicker: null, reportYear: null }, "hash-1");
    expect(generateAnswerMock).not.toHaveBeenCalled();
    expect(result.answer.errorDetail).toContain("application has been reached");
  });
});
