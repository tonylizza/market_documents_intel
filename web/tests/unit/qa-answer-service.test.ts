import { describe, expect, it, vi } from "vitest";
import { generateQaAnswer } from "@/lib/services/qa/qa-answer-service";
import { GenerationProviderTimeoutError } from "@/lib/services/generation/generation-provider";
import type { GenerationProvider } from "@/lib/services/generation/generation-provider";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";

function evidence(chunkId: string): QaEvidenceChunk {
  return {
    chunkId,
    text: "some evidence text",
    citation: {
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
    },
    similarity: 0.9,
    fusedScore: null,
    mergedCandidateCount: 1,
  };
}

describe("generateQaAnswer", () => {
  it("returns INSUFFICIENT_EVIDENCE without calling the provider when there is no evidence", async () => {
    const provider: GenerationProvider = { generateAnswer: vi.fn() };
    const result = await generateQaAnswer("q", [], provider);
    expect(result.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(provider.generateAnswer).not.toHaveBeenCalled();
  });

  it("returns the generated answer with only real, resolved cited evidence", async () => {
    const e1 = evidence("a");
    const e2 = evidence("b");
    const provider: GenerationProvider = {
      generateAnswer: vi.fn().mockResolvedValue({
        status: "ANSWERED",
        answerText: "the answer [E1]",
        citedChunkIds: ["a"],
        unsupportedPortion: null,
      }),
    };
    const result = await generateQaAnswer("q", [e1, e2], provider);
    expect(result.status).toBe("ANSWERED");
    expect(result.citedEvidence.map((e) => e.chunkId)).toEqual(["a"]);
    expect(result.allEvidence.map((e) => e.chunkId)).toEqual(["a", "b"]);
  });

  it("drops a cited chunk id that does not match any real evidence item", async () => {
    const provider: GenerationProvider = {
      generateAnswer: vi.fn().mockResolvedValue({
        status: "ANSWERED",
        answerText: "answer",
        citedChunkIds: ["nonexistent-chunk"],
        unsupportedPortion: null,
      }),
    };
    const result = await generateQaAnswer("q", [evidence("a")], provider);
    expect(result.citedEvidence).toEqual([]);
  });

  it("falls back to PROVIDER_UNAVAILABLE with all evidence intact when the provider fails", async () => {
    const provider: GenerationProvider = {
      generateAnswer: vi.fn().mockRejectedValue(new GenerationProviderTimeoutError()),
    };
    const evidenceList = [evidence("a")];
    const result = await generateQaAnswer("q", evidenceList, provider);
    expect(result.status).toBe("PROVIDER_UNAVAILABLE");
    expect(result.answerText).toBeNull();
    expect(result.allEvidence.map((e) => e.chunkId)).toEqual(["a"]);
    expect(result.errorDetail).not.toBeNull();
  });

  it("never invents an answer on provider failure", async () => {
    const provider: GenerationProvider = {
      generateAnswer: vi.fn().mockRejectedValue(new Error("boom")),
    };
    const result = await generateQaAnswer("q", [evidence("a")], provider);
    expect(result.answerText).toBeNull();
    expect(result.citedEvidence).toEqual([]);
  });

  it("carries the partial-answer unsupportedPortion through unchanged", async () => {
    const provider: GenerationProvider = {
      generateAnswer: vi.fn().mockResolvedValue({
        status: "PARTIALLY_ANSWERED",
        answerText: "partial answer",
        citedChunkIds: ["a"],
        unsupportedPortion: "the excerpts do not cover the second half of the question",
      }),
    };
    const result = await generateQaAnswer("q", [evidence("a")], provider);
    expect(result.status).toBe("PARTIALLY_ANSWERED");
    expect(result.unsupportedPortion).toBe("the excerpts do not cover the second half of the question");
  });
});
