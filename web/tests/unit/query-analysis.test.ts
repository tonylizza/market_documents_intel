import { describe, expect, it } from "vitest";
import { analyzeQuestion, type CompanyNameLookup } from "@/lib/services/qa/query-analysis";

const COMPANIES: CompanyNameLookup[] = [
  { ticker: "ACT", name: "AfroCentric Investment Corporation Limited" },
  { ticker: "BEL", name: "Bell Equipment Limited" },
  { ticker: "KP2", name: "Kore Potash plc" },
  { ticker: "SBP", name: "Sabvest Capital Limited" },
  { ticker: "SDL", name: "Southern Palladium Limited" },
  { ticker: "SUR", name: "Spur Corporation Limited" },
];

describe("analyzeQuestion -- company extraction", () => {
  it("matches an explicit ticker mentioned in caps", () => {
    expect(analyzeQuestion("What did ACT disclose about liquidity risk?", COMPANIES).tickers).toEqual(["ACT"]);
  });

  it("matches a derived company alias (full name minus corporate suffixes)", () => {
    expect(analyzeQuestion("How did AfroCentric describe its remuneration model?", COMPANIES).tickers).toEqual(["ACT"]);
  });

  it("matches the full registered company name", () => {
    expect(analyzeQuestion("What did Bell Equipment Limited say about margins?", COMPANIES).tickers).toEqual(["BEL"]);
  });

  it("does not false-positive-match a ticker embedded inside an unrelated word", () => {
    // "ACT" as a ticker must not match inside "react" or "impact".
    expect(analyzeQuestion("How did the company react to market impact?", COMPANIES).tickers).toEqual([]);
  });

  it("returns no tickers for a corpus-wide question", () => {
    expect(analyzeQuestion("What risks are commonly disclosed across companies?", COMPANIES).tickers).toEqual([]);
  });
});

describe("analyzeQuestion -- date range extraction", () => {
  it("extracts a single year as a same-year range", () => {
    const analysis = analyzeQuestion("What did SUR report in 2023?", COMPANIES);
    expect(analysis.dateRange).toEqual({ start: "2023-01-01", end: "2023-12-31" });
  });

  it("extracts a two-year range from the min/max years mentioned", () => {
    const analysis = analyzeQuestion("How did debt levels change between 2021 and 2023?", COMPANIES);
    expect(analysis.dateRange).toEqual({ start: "2021-01-01", end: "2023-12-31" });
  });

  it("returns null when no year is mentioned", () => {
    expect(analyzeQuestion("What is the company's strategy?", COMPANIES).dateRange).toBeNull();
  });
});

describe("analyzeQuestion -- comparison language extraction", () => {
  it.each([
    ["What increased in operating margin?", "increased"],
    ["Did revenue decrease this year?", "decreased"],
    ["What new risks were added?", "added"],
    ["What disclosures were removed?", "removed"],
    ["What language changed in the governance section?", "changed"],
  ] as const)("detects comparison direction for %s -> %s", (question, expected) => {
    expect(analyzeQuestion(question, COMPANIES).comparisonDirection).toBe(expected);
  });

  it("labels direction confidence LEXICAL_ONLY whenever a direction is detected -- never a stronger claim", () => {
    const analysis = analyzeQuestion("Did risk disclosures increase?", COMPANIES);
    expect(analysis.comparisonDirection).not.toBeNull();
    expect(analysis.directionConfidence).toBe("LEXICAL_ONLY");
  });

  it("leaves direction confidence null when no direction language is present", () => {
    const analysis = analyzeQuestion("What is the company's governance structure?", COMPANIES);
    expect(analysis.comparisonDirection).toBeNull();
    expect(analysis.directionConfidence).toBeNull();
  });

  it("warns that direction was extracted from wording only, not verified", () => {
    const analysis = analyzeQuestion("Did costs increase?", COMPANIES);
    expect(analysis.warnings.some((w) => w.includes("no stored signal exists to verify"))).toBe(true);
  });
});

describe("analyzeQuestion -- earlier/later side extraction", () => {
  it("detects the earlier side", () => {
    expect(analyzeQuestion("What did the prior report say about risk?", COMPANIES).requestedReportSides).toEqual(["EARLIER"]);
  });

  it("detects the later side", () => {
    expect(analyzeQuestion("What does the most recent report say about risk?", COMPANIES).requestedReportSides).toEqual(["LATER"]);
  });

  it("detects both sides for an explicit before/after question", () => {
    const sides = analyzeQuestion("How did language change between the previous and most recent report?", COMPANIES).requestedReportSides;
    expect(sides).toContain("EARLIER");
    expect(sides).toContain("LATER");
  });
});

describe("analyzeQuestion -- alignment-status extraction", () => {
  it("detects NEW disclosure language", () => {
    expect(analyzeQuestion("What risks were newly introduced?", COMPANIES).alignmentStatuses).toContain("NEW");
  });

  it("detects REMOVED disclosure language", () => {
    expect(analyzeQuestion("What is no longer disclosed?", COMPANIES).alignmentStatuses).toContain("REMOVED");
  });
});

describe("analyzeQuestion -- category extraction", () => {
  it("detects a known category mentioned by name", () => {
    expect(analyzeQuestion("What governance changes were disclosed?", COMPANIES).categories).toContain("governance");
  });

  it("detects a known subcategory mentioned by name", () => {
    expect(analyzeQuestion("What did they say about climate environmental risk?", COMPANIES).subcategories).toContain(
      "climate_environmental",
    );
  });
});

describe("analyzeQuestion -- scope classification", () => {
  it("classifies a single-company question with no comparison language as single_company", () => {
    expect(analyzeQuestion("What is ACT's governance structure?", COMPANIES).requestedScope).toBe("single_company");
  });

  it("classifies a single-company question with comparison language as single_comparison", () => {
    expect(analyzeQuestion("Did ACT's risk disclosures increase?", COMPANIES).requestedScope).toBe("single_comparison");
  });

  it("classifies a no-company question as corpus_wide", () => {
    expect(analyzeQuestion("What risks are commonly disclosed?", COMPANIES).requestedScope).toBe("corpus_wide");
  });

  it("sets requiredTicker only when exactly one company is referenced", () => {
    expect(analyzeQuestion("What is ACT's strategy?", COMPANIES).requiredTicker).toBe("ACT");
    expect(analyzeQuestion("What is the corpus-wide strategy?", COMPANIES).requiredTicker).toBeNull();
  });
});

describe("analyzeQuestion -- question-type classification", () => {
  it.each([
    ["Why did operating margins decline?", "causal"],
    ["Does the company disclose climate risk?", "existence_based"],
    ["How much debt does the company carry?", "quantitative"],
    ["Did risk disclosures increase compared to last year?", "comparative"],
    ["What is the company's strategy?", "descriptive"],
  ] as const)("classifies %s as %s", (question, expected) => {
    expect(analyzeQuestion(question, COMPANIES).questionType).toBe(expected);
  });
});

describe("analyzeQuestion -- unresolved terms and no silent over-narrowing", () => {
  it("surfaces an unrecognized all-caps token as unresolved rather than silently ignoring it", () => {
    const analysis = analyzeQuestion("What did XYZ disclose about risk?", COMPANIES);
    expect(analysis.unresolvedTerms).toContain("XYZ");
    expect(analysis.warnings.some((w) => w.includes("XYZ"))).toBe(true);
  });

  it("does not flag known non-ticker acronyms as unresolved", () => {
    const analysis = analyzeQuestion("What did the CEO say about JSE disclosure requirements?", COMPANIES);
    expect(analysis.unresolvedTerms).toEqual([]);
  });

  it("does not silently narrow scope when a term is ambiguous -- ambiguous questions still return a full analysis", () => {
    const analysis = analyzeQuestion("What did XYZ say?", COMPANIES);
    expect(analysis.requiredTicker).toBeNull();
    expect(analysis.tickers).toEqual([]);
  });
});
