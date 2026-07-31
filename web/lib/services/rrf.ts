/**
 * Reciprocal Rank Fusion -- deterministic fusion of a lexical ranking and a
 * semantic ranking into one fused score, per the milestone's explicit
 * instruction: "Prefer reciprocal rank fusion ... lexical rank and cosine
 * similarity are not naturally on the same scale" and "Do not add raw
 * ts_rank and cosine similarity directly without normalization."
 *
 * score(passage) = sum over rankings containing the passage of 1 / (k + rank)
 *
 * `rank` is always the 1-based position in that ranking, never the raw
 * `ts_rank`/cosine value -- this is what makes the two rankings
 * commensurable at all.
 */

export interface RankedItem {
  id: string;
  rankPosition: number;
}

export interface FusedItem {
  id: string;
  fusedScore: number;
  lexicalRankPosition: number | null;
  semanticRankPosition: number | null;
}

/** Deterministic tie-break: equal fused scores sort by ascending `id`
 * (stable, reproducible across re-runs -- never insertion order, which
 * depends on which candidate list happened to be iterated first). */
export function reciprocalRankFusion(
  lexicalRanking: readonly RankedItem[],
  semanticRanking: readonly RankedItem[],
  k: number,
): FusedItem[] {
  const lexicalByPassage = new Map(lexicalRanking.map((item) => [item.id, item.rankPosition]));
  const semanticByPassage = new Map(semanticRanking.map((item) => [item.id, item.rankPosition]));

  const allIds = new Set<string>([...lexicalByPassage.keys(), ...semanticByPassage.keys()]);

  const fused: FusedItem[] = [];
  for (const id of allIds) {
    const lexicalRank = lexicalByPassage.get(id) ?? null;
    const semanticRank = semanticByPassage.get(id) ?? null;
    const lexicalScore = lexicalRank !== null ? 1 / (k + lexicalRank) : 0;
    const semanticScore = semanticRank !== null ? 1 / (k + semanticRank) : 0;
    fused.push({
      id,
      fusedScore: lexicalScore + semanticScore,
      lexicalRankPosition: lexicalRank,
      semanticRankPosition: semanticRank,
    });
  }

  fused.sort((a, b) => {
    if (b.fusedScore !== a.fusedScore) return b.fusedScore - a.fusedScore;
    return a.id.localeCompare(b.id);
  });
  return fused;
}
