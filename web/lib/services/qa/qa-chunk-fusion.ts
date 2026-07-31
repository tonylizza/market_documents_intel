import type { ChunkHit } from "@/lib/repositories/qa-chunk-retrieval-repository";

/**
 * Milestone 7B.1d (experimental): maps child chunk hits back to canonical
 * parent passages. Only `ANCHOR`/`EARLIER_SIDE`/`LATER_SIDE` roles count as
 * a parent -- `PREVIOUS`/`NEXT`/`HEADING_CONTEXT` members are supporting
 * context the chunk's text includes, not passages the chunk is *evidence
 * for*; treating them as parents would let neighboring content silently
 * inherit relevance it was never independently ranked for.
 *
 * Multiple child hits (same or different strategy) mapping to the same
 * parent collapse into one `ChunkParentCandidate` -- `hitCount` records how
 * many independently ranked chunks supported this passage (a diagnostic
 * signal only; it must never inflate the evidence set itself, which is
 * still deduplicated by `passageId` downstream in `evidence-set-builder.ts`
 * exactly as before this milestone).
 */

const PARENT_ROLES = new Set(["ANCHOR", "EARLIER_SIDE", "LATER_SIDE"]);

export interface ChunkParentCandidate {
  passageId: string;
  bestSimilarity: number;
  bestRawRank: number;
  bestStrategy: string;
  hitCount: number;
}

export function mapChunkHitsToParents(hits: readonly ChunkHit[]): Map<string, ChunkParentCandidate> {
  const parents = new Map<string, ChunkParentCandidate>();
  hits.forEach((hit, index) => {
    const rawRank = index + 1;
    for (const member of hit.members) {
      if (!PARENT_ROLES.has(member.role)) continue;
      const existing = parents.get(member.passageId);
      if (!existing) {
        parents.set(member.passageId, {
          passageId: member.passageId,
          bestSimilarity: hit.similarity,
          bestRawRank: rawRank,
          bestStrategy: hit.strategy,
          hitCount: 1,
        });
        continue;
      }
      existing.hitCount += 1;
      if (hit.similarity > existing.bestSimilarity) {
        existing.bestSimilarity = hit.similarity;
        existing.bestRawRank = rawRank;
        existing.bestStrategy = hit.strategy;
      }
    }
  });
  return parents;
}
