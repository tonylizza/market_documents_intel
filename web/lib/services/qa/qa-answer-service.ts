import type { QaAnswer } from "@/lib/domain/qa-answer";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";
import type { GenerationProvider } from "@/lib/services/generation/generation-provider";
import { GenerationProviderError } from "@/lib/services/generation/generation-provider";
import type { QaGenerationPromptOptions } from "@/lib/services/generation/prompt";

/**
 * Milestone 7B.2 provider-fallback contract: if the generation provider is
 * unavailable (not configured, times out, or returns an unusable response),
 * return the retrieved excerpts and citations with status
 * `PROVIDER_UNAVAILABLE` -- never invent an answer. This is the ONE place
 * that contract is enforced, so `/ask` never has to special-case a
 * provider failure itself.
 */
export async function generateQaAnswer(
  questionText: string,
  evidence: readonly QaEvidenceChunk[],
  provider: GenerationProvider,
  options: QaGenerationPromptOptions = {},
): Promise<QaAnswer> {
  if (evidence.length === 0) {
    return {
      status: "INSUFFICIENT_EVIDENCE",
      answerText: null,
      unsupportedPortion: null,
      citedEvidence: [],
      allEvidence: [],
      providerLatencyMs: null,
      errorDetail: null,
    };
  }

  const startedAt = Date.now();
  try {
    const generated = await provider.generateAnswer(questionText, evidence, options);
    const evidenceById = new Map(evidence.map((e) => [e.chunkId, e]));
    // Only chunk ids that resolved to a real, currently-retrieved evidence
    // item are ever attached as "cited" -- `resolveCitedChunkIds` (prompt.ts)
    // already filters out-of-range excerpt numbers, this is the second,
    // independent guard against a fabricated/mismatched citation.
    const citedEvidence = generated.citedChunkIds
      .map((id) => evidenceById.get(id))
      .filter((e): e is QaEvidenceChunk => e !== undefined);

    return {
      status: generated.status,
      answerText: generated.answerText,
      unsupportedPortion: generated.unsupportedPortion,
      citedEvidence,
      allEvidence: [...evidence],
      providerLatencyMs: Date.now() - startedAt,
      errorDetail: null,
    };
  } catch (error) {
    const detail = error instanceof GenerationProviderError ? error.message : "Generation provider failed.";
    return {
      status: "PROVIDER_UNAVAILABLE",
      answerText: null,
      unsupportedPortion: null,
      citedEvidence: [],
      allEvidence: [...evidence],
      providerLatencyMs: Date.now() - startedAt,
      errorDetail: detail,
    };
  }
}
