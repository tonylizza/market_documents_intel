import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";

/**
 * Milestone 7B.2 evidence-only prompt policy. The single place the
 * generation prompt is assembled, so every provider implementation (Gemini
 * today, any future provider) sends an identical policy -- no vectors, no
 * outside knowledge, every material claim cited, explicit abstention.
 */

export const QA_GENERATION_SYSTEM_INSTRUCTION = `You are a grounded question-answering assistant for a JSE (Johannesburg Stock Exchange) annual-report disclosure intelligence application. You answer questions strictly from report excerpts the user's system retrieved -- you never use outside knowledge, training data, or general world knowledge to fill gaps.

Rules, none of which may be broken:
1. Answer only from the supplied report excerpts. Never introduce a fact, figure, or claim that is not stated in an excerpt.
2. Cite every material claim by its excerpt id (e.g. "[E1]"). A claim with no excerpt id backing it must not appear in the answer.
3. If the excerpts do not contain enough information to answer the question, say so explicitly and set status to INSUFFICIENT_EVIDENCE -- do not guess or approximate.
4. Never combine two unrelated excerpts into a causal or comparative claim neither excerpt supports on its own (e.g. excerpt A mentions revenue, excerpt B mentions headcount -- do not imply one caused the other unless an excerpt says so directly).
5. Never state that a number went up, down, or changed unless the excerpts make both the value and the direction unambiguous. If a number appears without clear context or comparison, describe it neutrally rather than asserting direction.
6. Never claim a year-over-year or period-over-period change unless excerpts from both the earlier and later period are present and clearly labeled with their periods. A single period's excerpt is never sufficient for a change claim.
7. Distinguish what a report explicitly states from anything you infer. If you must infer, say so explicitly (e.g. "the excerpt does not state X directly, but Y implies it").
8. A partial answer is allowed only when you explicitly separate what is supported from what is not -- set status to PARTIALLY_ANSWERED and fill unsupportedPortion with a clear statement of the gap. Never present a partial answer as if it were complete.
9. If the excerpts conflict with each other on a material point, do not silently pick one -- set status to AMBIGUOUS_OR_CONFLICTING and describe the conflict.
10. Respond with the required JSON structure only.`;

function formatExcerpt(evidence: QaEvidenceChunk, index: number): string {
  const label = evidence.citation.label;
  const heading = evidence.citation.sectionHeading ? ` | Section: ${evidence.citation.sectionHeading}` : "";
  return `[E${index + 1}] (${label}${heading})\n${evidence.text}`;
}

export interface QaGenerationPrompt {
  systemInstruction: string;
  userContent: string;
  /** Maps the "[E1]", "[E2]", ... labels used in the prompt back to real
   * chunk ids -- the caller uses this to translate the model's
   * `citedChunkIds` (which the model expresses as excerpt numbers) back
   * into verifiable chunk ids. */
  excerptChunkIds: string[];
}

export interface QaGenerationPromptOptions {
  /** Set by the caller when `question-router.ts` classified this question
   * as `COMPARISON_QA` and could not confirm evidence from two distinct
   * report periods (`bothSidesPresent` returned false) -- adds an explicit,
   * question-specific instruction on top of rule 6's general caution,
   * rather than relying on the model to infer it from the excerpts alone. */
  singleSidedComparisonWarning?: boolean;
}

export function buildQaGenerationPrompt(
  questionText: string,
  evidence: readonly QaEvidenceChunk[],
  options: QaGenerationPromptOptions = {},
): QaGenerationPrompt {
  const excerptChunkIds = evidence.map((e) => e.chunkId);
  const excerptsText = evidence.map((e, i) => formatExcerpt(e, i)).join("\n\n");

  const comparisonWarning = options.singleSidedComparisonWarning
    ? "\n\nNote: this question asks about change over time, but the retrieved excerpts only clearly cover a single report period for the relevant company. Do not assert or imply any year-over-year change. Answer only what the single period's excerpts support, and state explicitly that a comparison cannot be confirmed from the available evidence."
    : "";

  const userContent = `Question: ${questionText}

Retrieved excerpts:
${excerptsText || "(no excerpts were retrieved for this question)"}

Answer the question using only the excerpts above. List every excerpt number you cited (as plain integers, e.g. 1 for [E1]) in citedExcerptNumbers.${comparisonWarning}`;

  return { systemInstruction: QA_GENERATION_SYSTEM_INSTRUCTION, userContent, excerptChunkIds };
}

/** Translates the model's excerpt-number citations (1-based, matching
 * `[E#]` labels) back into real chunk ids, silently dropping any number
 * outside the actual excerpt range -- a model-invented excerpt number must
 * never resolve to an unrelated real chunk. */
export function resolveCitedChunkIds(citedExcerptNumbers: readonly number[], excerptChunkIds: readonly string[]): string[] {
  const resolved: string[] = [];
  for (const n of citedExcerptNumbers) {
    const index = n - 1;
    if (index >= 0 && index < excerptChunkIds.length) {
      resolved.push(excerptChunkIds[index]);
    }
  }
  return Array.from(new Set(resolved));
}
