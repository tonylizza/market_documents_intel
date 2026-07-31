import { describe, expect, it } from "vitest";
import { buildQaEvidenceChunks, deduplicateQaChunkCandidates } from "@/lib/services/qa/qa-chunk-dedup";
import type { QaChunkCandidate, QaChunkCitation } from "@/lib/domain/qa-chunk";

function candidate(overrides: Partial<QaChunkCandidate> = {}): QaChunkCandidate {
  return {
    chunkId: "chunk-1",
    reportId: "report-1",
    companyId: "company-1",
    chunkIndex: 0,
    similarity: 0.9,
    text: "some chunk text",
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

describe("deduplicateQaChunkCandidates", () => {
  it("collapses candidates sharing a member passage id into one group", () => {
    const a = candidate({ chunkId: "a", memberPassageIds: ["p1", "p2"] });
    const b = candidate({ chunkId: "b", chunkIndex: 5, pageStart: 10, pageEnd: 11, memberPassageIds: ["p2", "p3"] });
    const groups = deduplicateQaChunkCandidates([a, b], 5);
    expect(groups).toHaveLength(1);
    expect(groups[0].representative.chunkId).toBe("a");
    expect(groups[0].mergedCandidateCount).toBe(2);
  });

  it("collapses adjacent chunk indices in the same report", () => {
    const a = candidate({ chunkId: "a", chunkIndex: 3 });
    const b = candidate({ chunkId: "b", chunkIndex: 4, pageStart: 20, pageEnd: 21 });
    const groups = deduplicateQaChunkCandidates([a, b], 5);
    expect(groups).toHaveLength(1);
  });

  it("collapses overlapping or near-adjacent page ranges", () => {
    const a = candidate({ chunkId: "a", chunkIndex: 0, pageStart: 5, pageEnd: 6 });
    const b = candidate({ chunkId: "b", chunkIndex: 40, pageStart: 6, pageEnd: 7 });
    const groups = deduplicateQaChunkCandidates([a, b], 5);
    expect(groups).toHaveLength(1);
  });

  it("keeps distinct candidates from different reports separate", () => {
    const a = candidate({ chunkId: "a", reportId: "report-1" });
    const b = candidate({ chunkId: "b", reportId: "report-2" });
    const groups = deduplicateQaChunkCandidates([a, b], 5);
    expect(groups).toHaveLength(2);
  });

  it("keeps distinct candidates in the same report with no overlap separate", () => {
    const a = candidate({ chunkId: "a", chunkIndex: 0, pageStart: 1, pageEnd: 2 });
    const b = candidate({ chunkId: "b", chunkIndex: 50, pageStart: 100, pageEnd: 101 });
    const groups = deduplicateQaChunkCandidates([a, b], 5);
    expect(groups).toHaveLength(2);
  });

  it("preserves rank order -- the first (best-ranked) candidate in a group is the representative", () => {
    const best = candidate({ chunkId: "best", chunkIndex: 0 });
    const worse = candidate({ chunkId: "worse", chunkIndex: 1 });
    const groups = deduplicateQaChunkCandidates([best, worse], 5);
    expect(groups[0].representative.chunkId).toBe("best");
  });

  it("never exceeds maxGroups distinct groups", () => {
    const candidates = Array.from({ length: 10 }, (_, i) =>
      candidate({ chunkId: `c${i}`, chunkIndex: i * 10, pageStart: i * 100, pageEnd: i * 100 + 1 }),
    );
    const groups = deduplicateQaChunkCandidates(candidates, 3);
    expect(groups).toHaveLength(3);
  });

  it("does not inflate mergedCandidateCount beyond actual duplicate count", () => {
    const a = candidate({ chunkId: "a", memberPassageIds: ["p1"] });
    const groups = deduplicateQaChunkCandidates([a], 5);
    expect(groups[0].mergedCandidateCount).toBe(1);
  });
});

describe("buildQaEvidenceChunks", () => {
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

  it("attaches resolved citations and carries mergedCandidateCount through", () => {
    const groups = deduplicateQaChunkCandidates([candidate({ chunkId: "a" })], 5);
    const evidence = buildQaEvidenceChunks(groups, new Map([["a", citation("a")]]));
    expect(evidence).toHaveLength(1);
    expect(evidence[0].citation.label).toBe("ACT, 2024 report, pp. 1-2");
    expect(evidence[0].mergedCandidateCount).toBe(1);
  });

  it("drops a group with no resolvable citation rather than crashing", () => {
    const groups = deduplicateQaChunkCandidates([candidate({ chunkId: "a" })], 5);
    const evidence = buildQaEvidenceChunks(groups, new Map());
    expect(evidence).toHaveLength(0);
  });
});
