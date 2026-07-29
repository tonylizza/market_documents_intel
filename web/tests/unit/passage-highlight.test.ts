import { describe, expect, it } from "vitest";
import { buildExcerpt, buildHighlightSpans, extractHighlightTerms } from "@/lib/services/passage-highlight";
import { MAX_EXCERPT_LENGTH } from "@/lib/domain/passage";

describe("extractHighlightTerms", () => {
  it("splits on whitespace and strips quotes", () => {
    expect(extractHighlightTerms('"going concern"')).toEqual(["going", "concern"]);
  });

  it("lowercases and de-duplicates", () => {
    expect(extractHighlightTerms("Liquidity liquidity LIQUIDITY")).toEqual(["liquidity"]);
  });

  it("drops single-character tokens", () => {
    expect(extractHighlightTerms("a liquidity")).toEqual(["liquidity"]);
  });
});

describe("buildHighlightSpans", () => {
  it("produces a single unmatched span when there are no terms", () => {
    expect(buildHighlightSpans("hello world", [])).toEqual([{ text: "hello world", matched: false }]);
  });

  it("marks a whole-word case-insensitive match", () => {
    const spans = buildHighlightSpans("The Liquidity position is strong.", ["liquidity"]);
    expect(spans).toContainEqual({ text: "Liquidity", matched: true });
    expect(spans.some((s) => !s.matched && s.text.includes("The "))).toBe(true);
  });

  it("does not match a substring inside an unrelated word", () => {
    // "liquid" should not match inside "liquidity" partially-highlight the
    // rest -- whole regex-alternation match is fine, but a shorter term
    // like "cash" must not match "cashier".
    const spans = buildHighlightSpans("cashier duties", ["cash"]);
    expect(spans.every((s) => !s.matched)).toBe(true);
  });

  it("reconstructs the exact original text from the returned spans", () => {
    const original = "Governance and remuneration oversight increased this year.";
    const spans = buildHighlightSpans(original, ["governance", "remuneration"]);
    expect(spans.map((s) => s.text).join("")).toBe(original);
  });

  it("keeps HTML-like input as inert text spans, never interpreted markup", () => {
    const original = "<script>alert(1)</script> liquidity risk";
    const spans = buildHighlightSpans(original, ["liquidity"]);
    expect(spans.map((s) => s.text).join("")).toBe(original);
    // Every span is plain text data -- there is no span whose `text`
    // was stripped of the tag, proving no HTML parsing occurred here.
    expect(spans.some((s) => s.text.includes("<script>"))).toBe(true);
  });

  it("returns an empty array for empty text", () => {
    expect(buildHighlightSpans("", ["liquidity"])).toEqual([]);
  });
});

describe("buildExcerpt", () => {
  it("returns the full text (highlighted) when already under the max length", () => {
    const spans = buildExcerpt("short passage about liquidity", ["liquidity"]);
    expect(spans.map((s) => s.text).join("")).toBe("short passage about liquidity");
  });

  it("windows a long passage around the first match, bounded by MAX_EXCERPT_LENGTH", () => {
    const filler = "word ".repeat(500);
    const text = `${filler}liquidity risk is discussed here ${filler}`;
    const spans = buildExcerpt(text, ["liquidity"]);
    const joined = spans.map((s) => s.text).join("");
    expect(joined.length).toBeLessThanOrEqual(MAX_EXCERPT_LENGTH + 2);
    expect(joined).toContain("liquidity");
    expect(spans.some((s) => s.matched && s.text.toLowerCase() === "liquidity")).toBe(true);
  });

  it("falls back to the leading text when there is no match", () => {
    const filler = "word ".repeat(500);
    const spans = buildExcerpt(filler, ["nonexistentterm"]);
    const joined = spans.map((s) => s.text).join("");
    expect(joined.length).toBeLessThanOrEqual(MAX_EXCERPT_LENGTH + 1);
  });
});
