/**
 * Milestone 7B.1a: deterministic semantic reranker. Operates only on the
 * bounded candidate set already returned from Postgres (never a full-corpus
 * in-memory cosine scan, never a second unbounded query) -- takes raw
 * semantic candidates (ranked by cosine similarity) and produces a
 * quality-adjusted ranking that demotes short-passage similarity inflation
 * while preserving the raw similarity, the original rank, and a plain
 * explanation code for every candidate.
 */
import type { RerankedSemanticCandidate, SemanticCandidate } from "@/lib/domain/retrieval";
import {
  computePassageQualityFeatures,
  computeQualityAdjustment,
  type QualityAdjustmentConfig,
} from "@/lib/services/passage-quality";

export interface SemanticReranker {
  rerank(query: string, candidates: SemanticCandidate[]): RerankedSemanticCandidate[];
}

/**
 * The shipped reranker: a single deterministic quality-multiplier applied
 * to raw cosine similarity, then a stable re-sort. This expresses several
 * of the milestone's named remediation strategies as special cases of one
 * mechanism (see `evaluation/rerank-experiments.ts` for how each is
 * exercised): a `null`/identity config is "No remediation"; setting a
 * factor near 0 approximates a hard exclusion; the classification itself
 * implements "conditional short-passage exclusion" and "generic-heading
 * exclusion"; the continuous word-count/heading-frequency inputs implement
 * "length-aware score penalty"; the whole mechanism is the "passage-quality
 * multiplier" and "post-retrieval reranking" strategies at once.
 *
 * `query` is accepted (per the milestone's specified interface) but unused
 * by this deterministic strategy -- reserved for a future lexical-support
 * feature (milestone strategy 8), not implemented in this pass (see final
 * report "known limitations").
 */
export class QualityAdjustedSemanticReranker implements SemanticReranker {
  constructor(private readonly config?: QualityAdjustmentConfig) {}

  rerank(_query: string, candidates: SemanticCandidate[]): RerankedSemanticCandidate[] {
    const withOriginalRank = candidates.map((candidate, index) => ({ candidate, originalRank: index + 1 }));

    const adjusted = withOriginalRank.map(({ candidate, originalRank }) => {
      const features = computePassageQualityFeatures({
        heading: candidate.heading,
        text: candidate.text,
        wordCount: candidate.wordCount,
        hasLanguageSignal: candidate.hasLanguageSignal,
        headingFrequency: candidate.headingFrequency,
      });
      const { factor, explanationCode } = computeQualityAdjustment(features, this.config);
      return {
        passageId: candidate.passageId,
        rawSimilarity: candidate.similarity,
        qualityFactor: factor,
        adjustedScore: candidate.similarity * factor,
        explanationCode,
        originalRank,
        finalRank: 0, // assigned below after sort
      } satisfies RerankedSemanticCandidate;
    });

    adjusted.sort((a, b) => {
      if (b.adjustedScore !== a.adjustedScore) return b.adjustedScore - a.adjustedScore;
      // Deterministic tie-break: prefer the better original (raw-similarity)
      // rank, then stable id ordering -- never insertion order alone.
      if (a.originalRank !== b.originalRank) return a.originalRank - b.originalRank;
      return a.passageId.localeCompare(b.passageId);
    });

    return adjusted.map((candidate, index) => ({ ...candidate, finalRank: index + 1 }));
  }
}

/** No-op reranker -- the "No remediation" baseline strategy, used by the
 * experiment harness and available as a configuration for comparison. Ranks
 * are preserved unchanged; `adjustedScore` equals `rawSimilarity`. */
export class IdentitySemanticReranker implements SemanticReranker {
  rerank(_query: string, candidates: SemanticCandidate[]): RerankedSemanticCandidate[] {
    return candidates.map((candidate, index) => ({
      passageId: candidate.passageId,
      rawSimilarity: candidate.similarity,
      qualityFactor: 1,
      adjustedScore: candidate.similarity,
      explanationCode: "NO_QUALITY_ADJUSTMENT",
      originalRank: index + 1,
      finalRank: index + 1,
    }));
  }
}
