import { describe, expect, it } from "vitest";
import { bothSidesPresent, groupEvidenceByCompanyAndReport, routeQuestion } from "@/lib/services/qa/question-router";
import type { CompanyNameLookup } from "@/lib/services/qa/query-analysis";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";

const COMPANIES: CompanyNameLookup[] = [
  { ticker: "ACT", name: "AfroCentric Investment Corporation Limited" },
  { ticker: "BEL", name: "Bell Equipment Limited" },
];

function evidence(overrides: Partial<QaEvidenceChunk["citation"]> = {}): QaEvidenceChunk {
  const citation = {
    chunkId: "chunk-1",
    companyId: "company-act",
    companyTicker: "ACT",
    companyName: "AfroCentric Investment Corporation Limited",
    reportId: "report-1",
    reportTitle: "2024 Annual Report",
    reportPeriodEnd: "2024-12-31",
    pageStart: 1,
    pageEnd: 2,
    sectionHeading: null,
    memberPassageIds: ["p1"],
    label: "ACT, 2024 report, pp. 1-2",
    ...overrides,
  };
  return {
    chunkId: citation.chunkId,
    text: "evidence text",
    citation,
    similarity: 0.9,
    fusedScore: null,
    mergedCandidateCount: 1,
  };
}

describe("routeQuestion", () => {
  it("routes a comparative question to COMPARISON_QA", () => {
    const decision = routeQuestion("Did ACT's risk disclosures increase between 2022 and 2024?", COMPANIES);
    expect(decision.route).toBe("COMPARISON_QA");
    expect(decision.comparisonLinkTicker).toBe("ACT");
  });

  it("routes a chronological question to COMPARISON_QA", () => {
    const decision = routeQuestion("How has ACT's governance structure evolved over time?", COMPANIES);
    expect(decision.route).toBe("COMPARISON_QA");
  });

  it("routes a question naming an alignment status to COMPARISON_QA", () => {
    const decision = routeQuestion("What disclosures were newly introduced by ACT?", COMPANIES);
    expect(decision.route).toBe("COMPARISON_QA");
  });

  it("routes a single-company descriptive question to DOCUMENT_QA", () => {
    const decision = routeQuestion("What is ACT's strategy?", COMPANIES);
    expect(decision.route).toBe("DOCUMENT_QA");
  });

  it("routes a question naming no company to CORPUS_QA", () => {
    const decision = routeQuestion("What risks are commonly disclosed across companies?", COMPANIES);
    expect(decision.route).toBe("CORPUS_QA");
  });

  it("does not set comparisonLinkTicker for a multi-company comparison question", () => {
    const decision = routeQuestion("Compare ACT and Bell Equipment Limited's governance disclosures.", COMPANIES);
    expect(decision.route).toBe("COMPARISON_QA");
    expect(decision.comparisonLinkTicker).toBeNull();
  });
});

describe("bothSidesPresent", () => {
  it("is true when cited evidence spans two distinct report periods for the same company", () => {
    const e1 = evidence({ reportPeriodEnd: "2023-12-31" });
    const e2 = evidence({ reportPeriodEnd: "2024-12-31" });
    expect(bothSidesPresent([e1, e2])).toBe(true);
  });

  it("is false when all cited evidence is from a single report period", () => {
    const e1 = evidence({ reportPeriodEnd: "2024-12-31", chunkId: "a" });
    const e2 = evidence({ reportPeriodEnd: "2024-12-31", chunkId: "b" });
    expect(bothSidesPresent([e1, e2])).toBe(false);
  });

  it("is false for empty evidence", () => {
    expect(bothSidesPresent([])).toBe(false);
  });

  it("does not count distinct periods across different companies as both sides", () => {
    const e1 = evidence({ reportPeriodEnd: "2024-12-31", companyId: "company-act" });
    const e2 = evidence({ reportPeriodEnd: "2023-12-31", companyId: "company-bel", companyTicker: "BEL" });
    expect(bothSidesPresent([e1, e2])).toBe(false);
  });
});

describe("groupEvidenceByCompanyAndReport", () => {
  it("groups evidence by company then report, in first-seen order", () => {
    const actReport1 = evidence({ companyTicker: "ACT", reportId: "r1", chunkId: "a" });
    const belReport1 = evidence({ companyTicker: "BEL", companyId: "company-bel", reportId: "r2", chunkId: "b" });
    const actReport2 = evidence({ companyTicker: "ACT", reportId: "r3", chunkId: "c" });

    const grouped = groupEvidenceByCompanyAndReport([actReport1, belReport1, actReport2]);
    expect(grouped.map((g) => g.companyTicker)).toEqual(["ACT", "BEL"]);
    expect(grouped[0].reports.map((r) => r.reportId)).toEqual(["r1", "r3"]);
  });

  it("returns an empty array for no evidence", () => {
    expect(groupEvidenceByCompanyAndReport([])).toEqual([]);
  });
});
