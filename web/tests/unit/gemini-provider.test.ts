import { afterEach, describe, expect, it, vi } from "vitest";
import { GeminiGenerationProvider } from "@/lib/services/generation/gemini-provider";
import {
  GenerationProviderNotConfiguredError,
  GenerationProviderResponseError,
  GenerationProviderTimeoutError,
} from "@/lib/services/generation/generation-provider";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";

const CONFIG = {
  apiKey: "test-key",
  model: "gemini-2.5-flash-lite",
  timeoutMs: 1000,
  maxRetries: 1,
  retryBackoffMs: 1,
};

function evidence(chunkId = "chunk-a"): QaEvidenceChunk[] {
  return [
    {
      chunkId,
      text: "Revenue grew 12% in the period.",
      citation: {
        chunkId,
        companyId: "company-1",
        companyTicker: "ACT",
        companyName: "Acme Corp",
        reportId: "report-1",
        reportTitle: "2024 Annual Report",
        reportPeriodEnd: "2024-12-31",
        pageStart: 1,
        pageEnd: 2,
        sectionHeading: null,
        memberPassageIds: ["p1"],
        label: "ACT, 2024 report, pp. 1-2",
      },
      similarity: 0.9,
      fusedScore: null,
      mergedCandidateCount: 1,
    },
  ];
}

function mockGeminiResponse(body: Record<string, unknown>, ok = true, status = 200) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => ({
      candidates: [{ content: { parts: [{ text: JSON.stringify(body) }] } }],
    }),
  }) as unknown as typeof fetch;
}

describe("GeminiGenerationProvider", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws GenerationProviderNotConfiguredError when no API key is set", async () => {
    const provider = new GeminiGenerationProvider({ ...CONFIG, apiKey: null });
    await expect(provider.generateAnswer("q", evidence())).rejects.toBeInstanceOf(
      GenerationProviderNotConfiguredError,
    );
  });

  it("returns a parsed answer with resolved chunk ids on success", async () => {
    mockGeminiResponse({
      status: "ANSWERED",
      answerText: "Revenue grew 12% [E1].",
      citedExcerptNumbers: [1],
      unsupportedPortion: null,
    });
    const provider = new GeminiGenerationProvider(CONFIG);
    const result = await provider.generateAnswer("What happened to revenue?", evidence("chunk-a"));
    expect(result.status).toBe("ANSWERED");
    expect(result.citedChunkIds).toEqual(["chunk-a"]);
  });

  it("throws GenerationProviderResponseError on a non-OK HTTP response", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 }) as unknown as typeof fetch;
    const provider = new GeminiGenerationProvider({ ...CONFIG, maxRetries: 0 });
    await expect(provider.generateAnswer("q", evidence())).rejects.toBeInstanceOf(GenerationProviderResponseError);
  });

  it("throws GenerationProviderResponseError when the response is not valid JSON", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ candidates: [{ content: { parts: [{ text: "not json" }] } }] }),
    }) as unknown as typeof fetch;
    const provider = new GeminiGenerationProvider({ ...CONFIG, maxRetries: 0 });
    await expect(provider.generateAnswer("q", evidence())).rejects.toBeInstanceOf(GenerationProviderResponseError);
  });

  it("throws GenerationProviderResponseError when required fields are missing", async () => {
    mockGeminiResponse({ answerText: "missing status and citations" });
    const provider = new GeminiGenerationProvider({ ...CONFIG, maxRetries: 0 });
    await expect(provider.generateAnswer("q", evidence())).rejects.toBeInstanceOf(GenerationProviderResponseError);
  });

  it("times out via AbortController and throws GenerationProviderTimeoutError", async () => {
    global.fetch = vi.fn().mockImplementation(
      (_url: string, init?: RequestInit) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            const err = new Error("aborted");
            err.name = "AbortError";
            reject(err);
          });
        }),
    ) as unknown as typeof fetch;
    const provider = new GeminiGenerationProvider({ ...CONFIG, timeoutMs: 5, maxRetries: 0 });
    await expect(provider.generateAnswer("q", evidence())).rejects.toBeInstanceOf(GenerationProviderTimeoutError);
  });

  it("retries up to maxRetries then surfaces the last error", async () => {
    let callCount = 0;
    global.fetch = vi.fn().mockImplementation(() => {
      callCount += 1;
      return Promise.resolve({ ok: false, status: 503 });
    }) as unknown as typeof fetch;
    const provider = new GeminiGenerationProvider({ ...CONFIG, maxRetries: 2, retryBackoffMs: 1 });
    await expect(provider.generateAnswer("q", evidence())).rejects.toBeInstanceOf(GenerationProviderResponseError);
    expect(callCount).toBe(3); // 1 initial attempt + 2 retries, never unbounded
  });

  it("succeeds on a retry after an initial failure", async () => {
    let callCount = 0;
    global.fetch = vi.fn().mockImplementation(() => {
      callCount += 1;
      if (callCount === 1) return Promise.resolve({ ok: false, status: 503 });
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          candidates: [
            {
              content: {
                parts: [
                  {
                    text: JSON.stringify({
                      status: "INSUFFICIENT_EVIDENCE",
                      answerText: "",
                      citedExcerptNumbers: [],
                      unsupportedPortion: null,
                    }),
                  },
                ],
              },
            },
          ],
        }),
      });
    }) as unknown as typeof fetch;
    const provider = new GeminiGenerationProvider({ ...CONFIG, maxRetries: 1, retryBackoffMs: 1 });
    const result = await provider.generateAnswer("q", evidence());
    expect(result.status).toBe("INSUFFICIENT_EVIDENCE");
    expect(callCount).toBe(2);
  });

  it("never sends vectors in the request body", async () => {
    mockGeminiResponse({
      status: "ANSWERED",
      answerText: "ok [E1]",
      citedExcerptNumbers: [1],
      unsupportedPortion: null,
    });
    const provider = new GeminiGenerationProvider(CONFIG);
    await provider.generateAnswer("q", evidence());
    const fetchMock = global.fetch as unknown as { mock: { calls: unknown[][] } };
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const bodyText = String(init.body);
    expect(bodyText).not.toMatch(/embedding/i);
    expect(bodyText).not.toMatch(/\[\s*-?\d+\.\d+\s*,\s*-?\d+\.\d+/); // no raw float-array vector literal
  });
});
