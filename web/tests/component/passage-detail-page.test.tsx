/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { PassageComparisonDetail, PassageSideDetail } from "@/lib/domain/passage";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

function makeSide(overrides: Partial<PassageSideDetail> = {}): PassageSideDetail {
  return {
    passageId: "p1",
    heading: "Liquidity",
    text: "The group maintains adequate liquidity.",
    wordCount: 6,
    firstPageNumber: 10,
    lastPageNumber: 10,
    passageType: "HEADING_WITH_BODY",
    structuredContentCategory: null,
    primaryNarrativeEligible: true,
    featureEligible: true,
    ...overrides,
  };
}

function makeDetail(overrides: Partial<PassageComparisonDetail> = {}): PassageComparisonDetail {
  return {
    passageComparisonId: "pc1",
    reportComparisonId: "rc1",
    companyId: "c1",
    companyTicker: "ACT",
    companyName: "Acme Corp",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    confidenceLabel: "High confidence",
    contentScore: 0.9,
    semanticSimilarity: 0.95,
    lexicalSimilarity: 0.9,
    headingSimilarity: 1,
    positionDifference: 0.01,
    collisionFlag: false,
    splitMergeFlag: false,
    reviewReason: null,
    earlier: makeSide(),
    later: makeSide({ passageId: "p2", text: "The group maintains adequate liquidity headroom." }),
    ...overrides,
  };
}

let mockDetail: PassageComparisonDetail | null = makeDetail();
let shouldThrow = false;

vi.mock("@/lib/repositories/postgres-passage-repository", () => ({
  PostgresPassageRepository: class {
    async getPassageComparisonById() {
      if (shouldThrow) throw new Error("connection refused");
      return mockDetail;
    }
    async getPassageLanguageSignals() {
      if (shouldThrow) throw new Error("connection refused");
      return [];
    }
  },
}));

const { default: PassageDetailPage } = await import("@/app/passages/[passageComparisonId]/page");

describe("/passages/[passageComparisonId] page", () => {
  it("renders a matched two-sided passage with both disclosures", async () => {
    mockDetail = makeDetail();
    shouldThrow = false;
    const jsx = await PassageDetailPage({ params: Promise.resolve({ passageComparisonId: "pc1" }) });
    render(jsx);
    expect(screen.getByText("Earlier disclosure")).toBeInTheDocument();
    expect(screen.getByText("Later disclosure")).toBeInTheDocument();
  });

  it("renders the NEW layout: later side primary, earlier side explained as absent", async () => {
    mockDetail = makeDetail({ alignmentStatus: "NEW", earlier: null });
    const jsx = await PassageDetailPage({ params: Promise.resolve({ passageComparisonId: "pc1" }) });
    render(jsx);
    expect(screen.getByText("No aligned earlier passage")).toBeInTheDocument();
    expect(screen.getByText("Later disclosure (primary)")).toBeInTheDocument();
  });

  it("renders the REMOVED layout: earlier side primary, later side explained as absent", async () => {
    mockDetail = makeDetail({ alignmentStatus: "REMOVED", later: null });
    const jsx = await PassageDetailPage({ params: Promise.resolve({ passageComparisonId: "pc1" }) });
    render(jsx);
    expect(screen.getByText("No aligned later passage")).toBeInTheDocument();
    expect(screen.getByText("Earlier disclosure (primary)")).toBeInTheDocument();
  });

  it("renders the one-sided AMBIGUOUS layout with an uncertain-attribution explanation", async () => {
    mockDetail = makeDetail({ alignmentStatus: "AMBIGUOUS", later: null });
    const jsx = await PassageDetailPage({ params: Promise.resolve({ passageComparisonId: "pc1" }) });
    render(jsx);
    expect(screen.getByText(/attribution across reports is uncertain/i)).toBeInTheDocument();
  });

  it("calls notFound() for an unknown passage comparison id", async () => {
    mockDetail = null;
    await expect(PassageDetailPage({ params: Promise.resolve({ passageComparisonId: "missing" }) })).rejects.toThrow(
      "NEXT_NOT_FOUND",
    );
  });

  it("renders a safe error state when the database is unavailable", async () => {
    mockDetail = makeDetail();
    shouldThrow = true;
    const jsx = await PassageDetailPage({ params: Promise.resolve({ passageComparisonId: "pc1" }) });
    render(jsx);
    expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument();
    shouldThrow = false;
  });

  it("shows the review reason when present", async () => {
    mockDetail = makeDetail({ reviewReason: "Attribution uncertain -- only one side available" });
    const jsx = await PassageDetailPage({ params: Promise.resolve({ passageComparisonId: "pc1" }) });
    render(jsx);
    expect(screen.getAllByText(/Attribution uncertain -- only one side available/).length).toBeGreaterThan(0);
  });
});
