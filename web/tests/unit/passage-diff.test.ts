import { describe, expect, it } from "vitest";
import { buildTextDiff } from "@/lib/services/passage-diff";
import { MAX_DIFF_INPUT_LENGTH } from "@/lib/domain/passage";

describe("buildTextDiff", () => {
  it("marks fully identical text as entirely equal on both sides", () => {
    const result = buildTextDiff("the group maintains liquidity", "the group maintains liquidity");
    expect(result.diffed).toBe(true);
    expect(result.earlier.every((s) => s.op === "equal")).toBe(true);
    expect(result.later.every((s) => s.op === "equal")).toBe(true);
  });

  it("detects an insertion (later has extra words the earlier does not)", () => {
    const result = buildTextDiff("the group maintains liquidity", "the group maintains adequate liquidity");
    expect(result.later.some((s) => s.op === "insert" && s.text.includes("adequate"))).toBe(true);
    expect(result.earlier.some((s) => s.op === "insert")).toBe(false);
  });

  it("detects a deletion (earlier has words the later does not)", () => {
    const result = buildTextDiff("the group maintains adequate liquidity", "the group maintains liquidity");
    expect(result.earlier.some((s) => s.op === "delete" && s.text.includes("adequate"))).toBe(true);
    expect(result.later.some((s) => s.op === "delete")).toBe(false);
  });

  it("keeps unchanged tokens as equal segments on both sides", () => {
    const result = buildTextDiff("liquidity risk is stable", "liquidity risk is elevated");
    const earlierEqual = result.earlier.filter((s) => s.op === "equal").map((s) => s.text).join("");
    const laterEqual = result.later.filter((s) => s.op === "equal").map((s) => s.text).join("");
    expect(earlierEqual).toContain("liquidity risk is");
    expect(laterEqual).toContain("liquidity risk is");
  });

  it("reconstructs the exact original text from the diff segments", () => {
    const earlierText = "The board governance framework was updated during the year.";
    const laterText = "The board governance framework and remuneration policy were both updated this year.";
    const result = buildTextDiff(earlierText, laterText);
    expect(result.earlier.map((s) => s.text).join("")).toBe(earlierText);
    expect(result.later.map((s) => s.text).join("")).toBe(laterText);
  });

  it("falls back to undiffed (diffed: false) for input beyond MAX_DIFF_INPUT_LENGTH", () => {
    const huge = "word ".repeat(Math.ceil(MAX_DIFF_INPUT_LENGTH / 5) + 10);
    const result = buildTextDiff(huge, "short");
    expect(result.diffed).toBe(false);
    expect(result.earlier).toEqual([{ op: "equal", text: huge }]);
    expect(result.later).toEqual([{ op: "equal", text: "short" }]);
  });

  it("handles empty strings without throwing", () => {
    expect(() => buildTextDiff("", "")).not.toThrow();
    expect(buildTextDiff("", "new text").later.some((s) => s.op === "insert")).toBe(true);
  });
});
