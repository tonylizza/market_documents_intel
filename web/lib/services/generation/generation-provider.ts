import type { GeneratedAnswer } from "@/lib/domain/qa-answer";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";
import type { QaGenerationPromptOptions } from "@/lib/services/generation/prompt";

/**
 * Server-side provider boundary for grounded answer generation (Milestone
 * 7B.2). Implementations must never invent an answer when they cannot
 * reach the model -- `GenerationProviderError` is the only failure path,
 * always translated by the caller into `PROVIDER_UNAVAILABLE` plus the
 * already-retrieved evidence, never a fabricated answer.
 */
export interface GenerationProvider {
  generateAnswer(
    questionText: string,
    evidence: readonly QaEvidenceChunk[],
    options?: QaGenerationPromptOptions,
  ): Promise<GeneratedAnswer>;
}

export class GenerationProviderError extends Error {
  constructor(
    message: string,
    readonly cause_?: unknown,
  ) {
    super(message);
    this.name = "GenerationProviderError";
  }
}

export class GenerationProviderNotConfiguredError extends GenerationProviderError {
  constructor(message = "No generation provider API key is configured.") {
    super(message);
    this.name = "GenerationProviderNotConfiguredError";
  }
}

export class GenerationProviderTimeoutError extends GenerationProviderError {
  constructor(message = "The generation provider timed out.") {
    super(message);
    this.name = "GenerationProviderTimeoutError";
  }
}

export class GenerationProviderResponseError extends GenerationProviderError {
  constructor(message: string, cause_?: unknown) {
    super(message, cause_);
    this.name = "GenerationProviderResponseError";
  }
}
