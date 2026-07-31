import { describe, expect, it } from "vitest";
import { reciprocalRankFusion } from "@/lib/services/rrf";

describe("reciprocalRankFusion", () => {
  it("scores a passage present in both rankings higher than one present in only one", () => {
    const lexical = [
      { id: "a", rankPosition: 1 },
      { id: "b", rankPosition: 2 },
    ];
    const semantic = [
      { id: "a", rankPosition: 3 },
      { id: "c", rankPosition: 1 },
    ];
    const fused = reciprocalRankFusion(lexical, semantic, 60);
    expect(fused[0].id).toBe("a");
    expect(fused[0].lexicalRankPosition).toBe(1);
    expect(fused[0].semanticRankPosition).toBe(3);
  });

  it("computes the standard RRF formula: 1/(k+rank) summed across rankings", () => {
    const lexical = [{ id: "a", rankPosition: 1 }];
    const semantic = [{ id: "a", rankPosition: 1 }];
    const fused = reciprocalRankFusion(lexical, semantic, 60);
    expect(fused[0].fusedScore).toBeCloseTo(2 * (1 / 61), 10);
  });

  it("includes passages present in only one ranking", () => {
    const lexical = [{ id: "only-lexical", rankPosition: 1 }];
    const semantic: { id: string; rankPosition: number }[] = [];
    const fused = reciprocalRankFusion(lexical, semantic, 60);
    expect(fused).toHaveLength(1);
    expect(fused[0].semanticRankPosition).toBeNull();
  });

  it("breaks ties deterministically by ascending id", () => {
    const lexical = [
      { id: "z", rankPosition: 1 },
      { id: "a", rankPosition: 1 },
    ];
    const fused = reciprocalRankFusion(lexical, [], 60);
    expect(fused.map((f) => f.id)).toEqual(["a", "z"]);
  });

  it("is deterministic across repeated calls with the same input", () => {
    const lexical = [
      { id: "a", rankPosition: 2 },
      { id: "b", rankPosition: 1 },
    ];
    const semantic = [{ id: "b", rankPosition: 3 }];
    const first = reciprocalRankFusion(lexical, semantic, 60);
    const second = reciprocalRankFusion(lexical, semantic, 60);
    expect(first).toEqual(second);
  });

  it("returns an empty array when both rankings are empty", () => {
    expect(reciprocalRankFusion([], [], 60)).toEqual([]);
  });
});
