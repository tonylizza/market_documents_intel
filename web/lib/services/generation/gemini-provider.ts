import "server-only";
import type { GeneratedAnswer } from "@/lib/domain/qa-answer";
import { ANSWER_STATUSES } from "@/lib/domain/qa-answer";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";
import type { GenerationConfig } from "@/lib/config/generation-config";
import { getGenerationConfig } from "@/lib/config/generation-config";
import { buildQaGenerationPrompt, resolveCitedChunkIds, type QaGenerationPromptOptions } from "@/lib/services/generation/prompt";
import {
  GenerationProviderNotConfiguredError,
  GenerationProviderResponseError,
  GenerationProviderTimeoutError,
  type GenerationProvider,
} from "@/lib/services/generation/generation-provider";

const GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models";

const RESPONSE_SCHEMA = {
  type: "OBJECT",
  properties: {
    status: {
      type: "STRING",
      enum: ANSWER_STATUSES.filter((s) => s !== "PROVIDER_UNAVAILABLE"),
    },
    answerText: { type: "STRING" },
    citedExcerptNumbers: { type: "ARRAY", items: { type: "INTEGER" } },
    unsupportedPortion: { type: "STRING", nullable: true },
  },
  required: ["status", "answerText", "citedExcerptNumbers"],
} as const;

interface GeminiResponseBody {
  status: string;
  answerText: string;
  citedExcerptNumbers: number[];
  unsupportedPortion: string | null;
}

async function callGeminiOnce(
  systemInstruction: string,
  userContent: string,
  config: GenerationConfig,
): Promise<GeminiResponseBody> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${GEMINI_BASE_URL}/${config.model}:generateContent?key=${config.apiKey}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        system_instruction: { parts: [{ text: systemInstruction }] },
        contents: [{ role: "user", parts: [{ text: userContent }] }],
        generationConfig: {
          responseMimeType: "application/json",
          responseSchema: RESPONSE_SCHEMA,
          temperature: 0,
        },
      }),
      signal: controller.signal,
      // Next.js's server-runtime `fetch` patch caches/dedupes requests by
      // default -- confirmed live to cause this exact POST to hang until
      // AbortController fired, even though the identical request completes
      // in <1s outside the Next.js process. `no-store` opts this call out
      // of that layer entirely, which is also simply correct for a
      // non-idempotent generation call that must never be cached anyway.
      cache: "no-store",
    });
  } catch (error) {
    if ((error as { name?: string })?.name === "AbortError") {
      throw new GenerationProviderTimeoutError();
    }
    throw new GenerationProviderResponseError("Gemini request failed.", error);
  } finally {
    clearTimeout(timeout);
  }

  if (!response.ok) {
    // Never surface the raw response body (may echo the API key back in an
    // error message on some failure modes) -- status code + a generic
    // detail only.
    throw new GenerationProviderResponseError(`Gemini returned HTTP ${response.status}.`);
  }

  const body = (await response.json()) as {
    candidates?: { content?: { parts?: { text?: string }[] } }[];
  };
  const text = body.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) {
    throw new GenerationProviderResponseError("Gemini response had no content.");
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new GenerationProviderResponseError("Gemini response was not valid JSON.", error);
  }

  const candidate = parsed as Partial<GeminiResponseBody>;
  if (
    typeof candidate.status !== "string" ||
    typeof candidate.answerText !== "string" ||
    !Array.isArray(candidate.citedExcerptNumbers)
  ) {
    throw new GenerationProviderResponseError("Gemini response did not match the required structure.");
  }

  return {
    status: candidate.status,
    answerText: candidate.answerText,
    citedExcerptNumbers: candidate.citedExcerptNumbers.filter((n): n is number => typeof n === "number"),
    unsupportedPortion: typeof candidate.unsupportedPortion === "string" ? candidate.unsupportedPortion : null,
  };
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Google Gemini implementation of `GenerationProvider` -- free-tier,
 * Vercel-serverless-friendly, no self-hosted infrastructure. Timeouts and a
 * single bounded retry (configurable) are enforced here; any failure past
 * that surfaces as a typed `GenerationProviderError`, which the caller
 * (`generateQaAnswer`) always maps to `PROVIDER_UNAVAILABLE` -- this class
 * never invents an answer on failure.
 */
export class GeminiGenerationProvider implements GenerationProvider {
  constructor(private readonly config: GenerationConfig = getGenerationConfig()) {}

  async generateAnswer(
    questionText: string,
    evidence: readonly QaEvidenceChunk[],
    options: QaGenerationPromptOptions = {},
  ): Promise<GeneratedAnswer> {
    if (!this.config.apiKey) {
      throw new GenerationProviderNotConfiguredError();
    }

    const prompt = buildQaGenerationPrompt(questionText, evidence, options);

    let lastError: unknown;
    for (let attempt = 0; attempt <= this.config.maxRetries; attempt += 1) {
      try {
        const raw = await callGeminiOnce(prompt.systemInstruction, prompt.userContent, this.config);
        const status = raw.status as GeneratedAnswer["status"];
        return {
          status,
          answerText: raw.answerText,
          citedChunkIds: resolveCitedChunkIds(raw.citedExcerptNumbers, prompt.excerptChunkIds),
          unsupportedPortion: raw.unsupportedPortion,
        };
      } catch (error) {
        lastError = error;
        if (attempt < this.config.maxRetries) {
          await sleep(this.config.retryBackoffMs * (attempt + 1));
        }
      }
    }
    throw lastError;
  }
}
