import { describe, expect, it } from "vitest";
import { appendRetrievalModeParam, parseRetrievalMode } from "@/lib/services/retrieval-search-params";

describe("parseRetrievalMode", () => {
  it("returns the fallback when mode is absent", () => {
    expect(parseRetrievalMode({}, "keyword")).toBe("keyword");
  });

  it("parses a valid mode", () => {
    expect(parseRetrievalMode({ mode: "semantic" }, "keyword")).toBe("semantic");
    expect(parseRetrievalMode({ mode: "hybrid" }, "keyword")).toBe("hybrid");
  });

  it("falls back to the default on an invalid mode value", () => {
    expect(parseRetrievalMode({ mode: "not-a-mode" }, "keyword")).toBe("keyword");
    expect(parseRetrievalMode({ mode: "DROP TABLE" }, "keyword")).toBe("keyword");
  });

  it("takes the first value when mode is provided multiple times", () => {
    expect(parseRetrievalMode({ mode: ["hybrid", "semantic"] }, "keyword")).toBe("hybrid");
  });
});

describe("appendRetrievalModeParam", () => {
  it("omits mode entirely when it matches the default", () => {
    expect(appendRetrievalModeParam("q=liquidity", "keyword", "keyword")).toBe("q=liquidity");
  });

  it("appends mode when it differs from the default", () => {
    const result = appendRetrievalModeParam("q=liquidity", "hybrid", "keyword");
    expect(new URLSearchParams(result).get("mode")).toBe("hybrid");
    expect(new URLSearchParams(result).get("q")).toBe("liquidity");
  });
});
