import { describe, expect, it } from "vitest";
import { buildQaGenerationPrompt, resolveCitedChunkIds } from "@/lib/services/generation/prompt";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";

function evidence(chunkId: string, text = "some evidence text"): QaEvidenceChunk {
  return {
    chunkId,
    text,
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
      sectionHeading: "Strategic Overview",
      memberPassageIds: ["p1"],
      label: "ACT, 2024 report, pp. 1-2",
    },
    similarity: 0.9,
    fusedScore: null,
    mergedCandidateCount: 1,
  };
}

describe("buildQaGenerationPrompt", () => {
  it("numbers excerpts sequentially and includes their citation labels", () => {
    const prompt = buildQaGenerationPrompt("What is the strategy?", [evidence("a"), evidence("b")]);
    expect(prompt.userContent).toContain("[E1] (ACT, 2024 report, pp. 1-2");
    expect(prompt.userContent).toContain("[E2] (ACT, 2024 report, pp. 1-2");
    expect(prompt.excerptChunkIds).toEqual(["a", "b"]);
  });

  it("includes the question text", () => {
    const prompt = buildQaGenerationPrompt("What is the strategy?", [evidence("a")]);
    expect(prompt.userContent).toContain("What is the strategy?");
  });

  it("states explicitly when no excerpts were retrieved", () => {
    const prompt = buildQaGenerationPrompt("What is the strategy?", []);
    expect(prompt.userContent).toContain("no excerpts were retrieved");
    expect(prompt.excerptChunkIds).toEqual([]);
  });

  it("system instruction requires citation of every material claim and forbids outside knowledge", () => {
    const prompt = buildQaGenerationPrompt("q", []);
    expect(prompt.systemInstruction).toMatch(/cite every material claim/i);
    expect(prompt.systemInstruction).toMatch(/never use outside knowledge/i);
  });

  it("adds an explicit single-sided-comparison warning when requested", () => {
    const withWarning = buildQaGenerationPrompt("Did risk increase?", [evidence("a")], {
      singleSidedComparisonWarning: true,
    });
    expect(withWarning.userContent).toMatch(/do not assert or imply any year-over-year change/i);

    const withoutWarning = buildQaGenerationPrompt("Did risk increase?", [evidence("a")]);
    expect(withoutWarning.userContent).not.toMatch(/do not assert or imply any year-over-year change/i);
  });
});

describe("resolveCitedChunkIds", () => {
  it("maps 1-based excerpt numbers back to their chunk ids", () => {
    const resolved = resolveCitedChunkIds([1, 2], ["chunk-a", "chunk-b"]);
    expect(resolved).toEqual(["chunk-a", "chunk-b"]);
  });

  it("drops excerpt numbers outside the real range rather than fabricating a chunk id", () => {
    const resolved = resolveCitedChunkIds([1, 5, 0, -1], ["chunk-a"]);
    expect(resolved).toEqual(["chunk-a"]);
  });

  it("deduplicates repeated citations of the same excerpt", () => {
    const resolved = resolveCitedChunkIds([1, 1, 1], ["chunk-a"]);
    expect(resolved).toEqual(["chunk-a"]);
  });

  it("returns an empty array for no citations", () => {
    expect(resolveCitedChunkIds([], ["chunk-a"])).toEqual([]);
  });
});
