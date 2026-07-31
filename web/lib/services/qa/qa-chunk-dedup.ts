import type { QaChunkCandidate, QaChunkCitation, QaEvidenceChunk } from "@/lib/domain/qa-chunk";

/**
 * Overlap-aware evidence-set deduplication (Milestone 7B.2 brief:
 * "Overlapping chunks are not independent corroboration"). Two candidates
 * are treated as the same evidence when, within the same report, they:
 *   - share at least one canonical member passage id, OR
 *   - have adjacent/overlapping chunk indices (the standard chunker's
 *     ~70-token overlap means index N and N+1 routinely quote the same
 *     sentences), OR
 *   - have overlapping or near-adjacent page ranges (within
 *     `PAGE_ADJACENCY_TOLERANCE`).
 *
 * Greedy, deterministic: candidates are processed in caller-supplied rank
 * order (already fused/sorted); the first (highest-ranked) representative
 * of an overlap group is kept, later duplicates are merged into it
 * (`mergedCandidateCount` increments, citation metadata is not widened
 * beyond what the kept chunk already carries -- merging never inflates the
 * evidence count).
 */

const PAGE_ADJACENCY_TOLERANCE = 1;

function pagesOverlapOrAdjacent(aStart: number, aEnd: number, bStart: number, bEnd: number): boolean {
  return aStart - PAGE_ADJACENCY_TOLERANCE <= bEnd && bStart - PAGE_ADJACENCY_TOLERANCE <= aEnd;
}

function sharesMemberPassage(a: readonly string[], b: readonly string[]): boolean {
  if (a.length === 0 || b.length === 0) return false;
  const bSet = new Set(b);
  return a.some((id) => bSet.has(id));
}

function isDuplicateOf(candidate: QaChunkCandidate, kept: QaChunkCandidate): boolean {
  if (candidate.reportId !== kept.reportId) return false;
  if (sharesMemberPassage(candidate.memberPassageIds, kept.memberPassageIds)) return true;
  if (Math.abs(candidate.chunkIndex - kept.chunkIndex) <= 1) return true;
  if (pagesOverlapOrAdjacent(candidate.pageStart, candidate.pageEnd, kept.pageStart, kept.pageEnd)) return true;
  return false;
}

export interface DedupedEvidenceGroup {
  representative: QaChunkCandidate;
  mergedCandidateCount: number;
}

/** Groups overlapping candidates, keeping the highest-ranked representative
 * of each group -- input order IS rank order (best first); this function
 * does no scoring or sorting of its own. */
export function deduplicateQaChunkCandidates(
  rankedCandidates: readonly QaChunkCandidate[],
  maxGroups: number,
): DedupedEvidenceGroup[] {
  const groups: DedupedEvidenceGroup[] = [];

  for (const candidate of rankedCandidates) {
    const existingGroup = groups.find((g) => isDuplicateOf(candidate, g.representative));
    if (existingGroup) {
      existingGroup.mergedCandidateCount += 1;
      continue;
    }
    if (groups.length >= maxGroups) continue;
    groups.push({ representative: candidate, mergedCandidateCount: 1 });
  }

  return groups;
}

/** Attaches resolved citations to deduped groups, producing the final
 * evidence-chunk list `/ask`'s prompt and UI are both built from. Groups
 * with no resolvable citation (should not happen for a chunk that passed
 * validation, but defensively excluded rather than crashing the request)
 * are dropped. */
export function buildQaEvidenceChunks(
  groups: readonly DedupedEvidenceGroup[],
  citationsByChunkId: ReadonlyMap<string, QaChunkCitation>,
): QaEvidenceChunk[] {
  const evidence: QaEvidenceChunk[] = [];
  for (const group of groups) {
    const citation = citationsByChunkId.get(group.representative.chunkId);
    if (!citation) continue;
    evidence.push({
      chunkId: group.representative.chunkId,
      text: group.representative.text,
      citation,
      similarity: group.representative.similarity,
      fusedScore: group.representative.fusedScore,
      mergedCandidateCount: group.mergedCandidateCount,
    });
  }
  return evidence;
}
