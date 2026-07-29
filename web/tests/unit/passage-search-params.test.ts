import { describe, expect, it } from "vitest";
import {
  buildPassageSearchQueryString,
  hasSearchableInput,
  parsePassageSearchParams,
  resetPage,
} from "@/lib/services/passage-search-params";
import { MAX_PASSAGE_PAGE_SIZE, MAX_PASSAGE_QUERY_LENGTH } from "@/lib/domain/passage";

describe("parsePassageSearchParams", () => {
  it("parses a plain query", () => {
    const params = parsePassageSearchParams({ q: "liquidity" });
    expect(params.query).toBe("liquidity");
  });

  it("truncates an overlong query to MAX_PASSAGE_QUERY_LENGTH", () => {
    const long = "a".repeat(MAX_PASSAGE_QUERY_LENGTH + 50);
    const params = parsePassageSearchParams({ q: long });
    expect(params.query).toHaveLength(MAX_PASSAGE_QUERY_LENGTH);
  });

  it("treats an empty/whitespace-only query as no query", () => {
    expect(parsePassageSearchParams({ q: "" }).query).toBeNull();
    expect(parsePassageSearchParams({ q: "   " }).query).toBeNull();
  });

  it("validates alignment status against the controlled vocabulary, dropping unknown values", () => {
    expect(parsePassageSearchParams({ status: "NEW" }).alignmentStatus).toBe("NEW");
    expect(parsePassageSearchParams({ status: "not-a-real-status" }).alignmentStatus).toBeNull();
    expect(parsePassageSearchParams({ status: "DROP TABLE passages;" }).alignmentStatus).toBeNull();
  });

  it("validates confidence, passage type, and report side against controlled vocabularies", () => {
    expect(parsePassageSearchParams({ confidence: "HIGH" }).confidence).toBe("HIGH");
    expect(parsePassageSearchParams({ confidence: "bogus" }).confidence).toBeNull();
    expect(parsePassageSearchParams({ type: "LIST" }).passageType).toBe("LIST");
    expect(parsePassageSearchParams({ type: "bogus" }).passageType).toBeNull();
    expect(parsePassageSearchParams({ side: "EARLIER" }).reportSide).toBe("EARLIER");
    expect(parsePassageSearchParams({ side: "sideways" }).reportSide).toBeNull();
  });

  it("falls back to the allowed sort-key default for an invalid sort value", () => {
    expect(parsePassageSearchParams({ sort: "relevance", q: "x" }).sort).toBe("relevance");
    expect(parsePassageSearchParams({ sort: "not-a-sort" }).sort).toBe("newest_report");
  });

  it("falls back relevance -> newest_report when no query is present (relevance is meaningless without a query)", () => {
    expect(parsePassageSearchParams({ sort: "relevance" }).sort).toBe("newest_report");
    expect(parsePassageSearchParams({ sort: "relevance", q: "liquidity" }).sort).toBe("relevance");
  });

  it("normalizes pagination: invalid/negative page falls back to 1, page size is bounded", () => {
    expect(parsePassageSearchParams({ page: "0" }).page).toBe(1);
    expect(parsePassageSearchParams({ page: "-5" }).page).toBe(1);
    expect(parsePassageSearchParams({ page: "not-a-number" }).page).toBe(1);
    expect(parsePassageSearchParams({ page: "3" }).page).toBe(3);
    expect(parsePassageSearchParams({ pageSize: "9999" }).pageSize).toBe(MAX_PASSAGE_PAGE_SIZE);
    expect(parsePassageSearchParams({ pageSize: "0" }).pageSize).toBeGreaterThanOrEqual(1);
  });

  it("normalizes a duplicate query-string value (array) by taking the first entry", () => {
    const params = parsePassageSearchParams({ company: ["ACT", "BEL"] });
    expect(params.company).toBe("ACT");
  });

  it("rejects a comparison id that isn't a UUID shape", () => {
    expect(parsePassageSearchParams({ comparison: "not-a-uuid" }).comparisonId).toBeNull();
    expect(parsePassageSearchParams({ comparison: "11111111-1111-1111-1111-111111111111" }).comparisonId).toBe(
      "11111111-1111-1111-1111-111111111111",
    );
  });

  it("rejects a malformed period date", () => {
    expect(parsePassageSearchParams({ periodStart: "2024-01-01" }).periodStart).toBe("2024-01-01");
    expect(parsePassageSearchParams({ periodStart: "not-a-date" }).periodStart).toBeNull();
    expect(parsePassageSearchParams({ periodStart: "'; DROP TABLE passages; --" }).periodStart).toBeNull();
  });

  it("only accepts a subcategory when a category is also present", () => {
    expect(parsePassageSearchParams({ subcategory: "climate_environmental" }).subcategory).toBeNull();
    expect(parsePassageSearchParams({ category: "risk", subcategory: "climate_environmental" }).subcategory).toBe(
      "climate_environmental",
    );
  });

  it("parses tri-state boolean filters", () => {
    expect(parsePassageSearchParams({ collision: "1" }).collisionFlag).toBe(true);
    expect(parsePassageSearchParams({ collision: "0" }).collisionFlag).toBe(false);
    expect(parsePassageSearchParams({}).collisionFlag).toBeNull();
    expect(parsePassageSearchParams({ collision: "garbage" }).collisionFlag).toBeNull();
  });

  it("never throws on a garbage/malformed input object", () => {
    expect(() =>
      parsePassageSearchParams({ page: "💥", pageSize: "-1", status: "<script>", sort: undefined }),
    ).not.toThrow();
  });
});

describe("hasSearchableInput", () => {
  it("is false for completely empty params (bounded empty-search rule)", () => {
    expect(hasSearchableInput(parsePassageSearchParams({}))).toBe(false);
  });

  it("is false when only page/pageSize/sort/exactPhrase are set", () => {
    expect(hasSearchableInput(parsePassageSearchParams({ page: "2", sort: "company", phrase: "1" }))).toBe(false);
  });

  it("is true with a query", () => {
    expect(hasSearchableInput(parsePassageSearchParams({ q: "liquidity" }))).toBe(true);
  });

  it("is true with only a structured filter and no query", () => {
    expect(hasSearchableInput(parsePassageSearchParams({ company: "ACT" }))).toBe(true);
    expect(hasSearchableInput(parsePassageSearchParams({ collision: "1" }))).toBe(true);
  });
});

describe("buildPassageSearchQueryString / parsePassageSearchParams round-trip", () => {
  it("round-trips every settable field", () => {
    const original = parsePassageSearchParams({
      q: "going concern",
      phrase: "1",
      company: "ACT",
      periodStart: "2022-01-01",
      periodEnd: "2023-01-01",
      status: "SUBSTANTIALLY_MODIFIED",
      confidence: "HIGH",
      type: "LIST",
      category: "risk",
      subcategory: "climate_environmental",
      collision: "1",
      sort: "company",
      page: "2",
      pageSize: "10",
    });
    const serialized = buildPassageSearchQueryString(original);
    const roundTripped = parsePassageSearchParams(Object.fromEntries(new URLSearchParams(serialized)));
    expect(roundTripped).toEqual(original);
  });

  it("omits default values from the serialized query string", () => {
    const params = parsePassageSearchParams({ q: "liquidity" });
    const serialized = buildPassageSearchQueryString(params);
    expect(serialized).toBe("q=liquidity");
  });
});

describe("resetPage", () => {
  it("resets page to 1 without touching other fields", () => {
    const params = parsePassageSearchParams({ q: "x", page: "5", company: "ACT" });
    const reset = resetPage(params);
    expect(reset.page).toBe(1);
    expect(reset.company).toBe("ACT");
    expect(reset.query).toBe("x");
  });
});
