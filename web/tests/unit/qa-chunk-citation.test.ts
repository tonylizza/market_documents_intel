import { describe, expect, it } from "vitest";
import { formatQaChunkCitationLabel } from "@/lib/services/qa/qa-chunk-citation";
import type { QaChunkCitation } from "@/lib/domain/qa-chunk";

function citation(overrides: Partial<QaChunkCitation> = {}): QaChunkCitation {
  return {
    chunkId: "chunk-1",
    companyId: "company-1",
    companyTicker: "ACT",
    companyName: "Acme Corp",
    reportId: "report-1",
    reportTitle: "2024 Annual Report",
    reportPeriodEnd: "2024-12-31",
    pageStart: 12,
    pageEnd: 14,
    sectionHeading: "Strategic Overview",
    memberPassageIds: ["p1"],
    label: "",
    ...overrides,
  };
}

describe("formatQaChunkCitationLabel", () => {
  it("formats a multi-page citation with the report year", () => {
    expect(formatQaChunkCitationLabel(citation())).toBe("ACT, 2024 report, pp. 12-14");
  });

  it("formats a single-page citation", () => {
    expect(formatQaChunkCitationLabel(citation({ pageStart: 5, pageEnd: 5 }))).toBe("ACT, 2024 report, p. 5");
  });

  it("omits the year when the period end is missing", () => {
    expect(formatQaChunkCitationLabel(citation({ reportPeriodEnd: null }))).toBe("ACT, pp. 12-14");
  });

  it("omits the year when the period end is malformed", () => {
    expect(formatQaChunkCitationLabel(citation({ reportPeriodEnd: "not-a-date" }))).toBe("ACT, pp. 12-14");
  });
});
