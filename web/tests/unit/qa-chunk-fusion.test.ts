import { describe, expect, it } from "vitest";
import { mapChunkHitsToParents } from "@/lib/services/qa/qa-chunk-fusion";
import type { ChunkHit } from "@/lib/repositories/qa-chunk-retrieval-repository";

describe("mapChunkHitsToParents", () => {
  it("maps a single ANCHOR hit to its parent passage", () => {
    const hits: ChunkHit[] = [
      { chunkId: "c1", strategy: "HEADING_PLUS_PASSAGE", similarity: 0.9, members: [{ passageId: "p1", role: "ANCHOR" }] },
    ];
    const parents = mapChunkHitsToParents(hits);
    expect(parents.get("p1")).toEqual({ passageId: "p1", bestSimilarity: 0.9, bestRawRank: 1, bestStrategy: "HEADING_PLUS_PASSAGE", hitCount: 1 });
  });

  it("ignores PREVIOUS/NEXT/HEADING_CONTEXT members -- they are not parents", () => {
    const hits: ChunkHit[] = [
      {
        chunkId: "c1",
        strategy: "LOCAL_WINDOW",
        similarity: 0.8,
        members: [
          { passageId: "prev", role: "PREVIOUS" },
          { passageId: "anchor", role: "ANCHOR" },
          { passageId: "next", role: "NEXT" },
          { passageId: "head", role: "HEADING_CONTEXT" },
        ],
      },
    ];
    const parents = mapChunkHitsToParents(hits);
    expect([...parents.keys()]).toEqual(["anchor"]);
  });

  it("maps a COMPARISON_PAIR hit to both EARLIER_SIDE and LATER_SIDE parents", () => {
    const hits: ChunkHit[] = [
      {
        chunkId: "c1",
        strategy: "COMPARISON_PAIR",
        similarity: 0.85,
        members: [
          { passageId: "earlier", role: "EARLIER_SIDE" },
          { passageId: "later", role: "LATER_SIDE" },
        ],
      },
    ];
    const parents = mapChunkHitsToParents(hits);
    expect(new Set(parents.keys())).toEqual(new Set(["earlier", "later"]));
  });

  it("collapses multiple child hits for the same parent into one entry, tracking hitCount and best similarity", () => {
    const hits: ChunkHit[] = [
      { chunkId: "c1", strategy: "HEADING_PLUS_PASSAGE", similarity: 0.7, members: [{ passageId: "p1", role: "ANCHOR" }] },
      { chunkId: "c2", strategy: "LOCAL_WINDOW", similarity: 0.95, members: [{ passageId: "p1", role: "ANCHOR" }] },
      { chunkId: "c3", strategy: "CURRENT_PLUS_NEXT", similarity: 0.6, members: [{ passageId: "p1", role: "ANCHOR" }] },
    ];
    const parents = mapChunkHitsToParents(hits);
    const p1 = parents.get("p1");
    expect(p1?.hitCount).toBe(3);
    expect(p1?.bestSimilarity).toBe(0.95);
    expect(p1?.bestStrategy).toBe("LOCAL_WINDOW");
  });

  it("returns an empty map for no hits", () => {
    expect(mapChunkHitsToParents([]).size).toBe(0);
  });
});
