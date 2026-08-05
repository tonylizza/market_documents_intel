import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const queryMock = vi.fn();

vi.mock("pg", () => ({
  Pool: vi.fn().mockImplementation(() => ({ query: queryMock })),
}));

const { checkAndIncrementQuota, hashClientId, loadQuotaFailureMode } = await import("@/lib/services/qa/quota-service");

function allowedRow(allowed: boolean, current_count = 1) {
  return { rows: [{ allowed, current_count }] };
}

function resetPoolSingleton() {
  delete (globalThis as unknown as { __qaQuotaPool?: unknown }).__qaQuotaPool;
}

describe("quota-service", () => {
  const originalUrl = process.env.QA_QUOTA_DATABASE_URL;
  const originalMode = process.env.QA_QUOTA_FAILURE_MODE;
  const originalVercelEnv = process.env.VERCEL_ENV;

  beforeEach(() => {
    queryMock.mockReset();
    resetPoolSingleton();
  });

  afterEach(() => {
    if (originalUrl === undefined) delete process.env.QA_QUOTA_DATABASE_URL;
    else process.env.QA_QUOTA_DATABASE_URL = originalUrl;
    if (originalMode === undefined) delete process.env.QA_QUOTA_FAILURE_MODE;
    else process.env.QA_QUOTA_FAILURE_MODE = originalMode;
    if (originalVercelEnv === undefined) delete process.env.VERCEL_ENV;
    else process.env.VERCEL_ENV = originalVercelEnv;
    resetPoolSingleton();
    // Deliberately not `vi.restoreAllMocks()` -- that also tears down the
    // hoisted `vi.mock("pg", ...)` factory's `Pool` implementation (any
    // `vi.fn()`, not just `vi.spyOn` spies), which would silently break
    // every `checkAndIncrementQuota` test running after the first one that
    // spies on `console.error`. Individual `console.error` spies restore
    // themselves via their own `mockRestore()` inline instead.
  });

  describe("hashClientId", () => {
    it("is deterministic for the same input", () => {
      expect(hashClientId("abc-123")).toBe(hashClientId("abc-123"));
    });

    it("differs for different inputs", () => {
      expect(hashClientId("abc-123")).not.toBe(hashClientId("abc-124"));
    });

    it("never returns the raw input (always a hex digest)", () => {
      const hash = hashClientId("abc-123");
      expect(hash).not.toBe("abc-123");
      expect(hash).toMatch(/^[0-9a-f]{64}$/);
    });
  });

  describe("loadQuotaFailureMode", () => {
    it("defaults to closed in Production when unset", () => {
      delete process.env.QA_QUOTA_FAILURE_MODE;
      process.env.VERCEL_ENV = "production";
      expect(loadQuotaFailureMode()).toBe("closed");
    });

    it("defaults to open outside Production when unset", () => {
      delete process.env.QA_QUOTA_FAILURE_MODE;
      delete process.env.VERCEL_ENV;
      expect(loadQuotaFailureMode()).toBe("open");
    });

    it("respects an explicit valid value", () => {
      process.env.QA_QUOTA_FAILURE_MODE = "closed";
      delete process.env.VERCEL_ENV;
      expect(loadQuotaFailureMode()).toBe("closed");
    });

    it("invalid configuration: unknown value falls back to the safe per-environment default and logs, never throws", () => {
      process.env.QA_QUOTA_FAILURE_MODE = "sideways";
      process.env.VERCEL_ENV = "production";
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      expect(loadQuotaFailureMode()).toBe("closed");
      expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining("invalid QA_QUOTA_FAILURE_MODE"));
      errorSpy.mockRestore();
    });
  });

  describe("checkAndIncrementQuota", () => {
    it("database success: within limit increments both counters and allows", async () => {
      process.env.QA_QUOTA_DATABASE_URL = "postgresql://app_quota_writer:pw@localhost:5434/db";
      queryMock.mockResolvedValueOnce(allowedRow(true, 3)).mockResolvedValueOnce(allowedRow(true, 12));
      const result = await checkAndIncrementQuota("some-hash");
      expect(result).toEqual({ allowed: true, reason: "within_limit" });
      expect(queryMock).toHaveBeenCalledTimes(2);
    });

    it("client quota exceeded: per-client limit blocks before the global check", async () => {
      process.env.QA_QUOTA_DATABASE_URL = "postgresql://app_quota_writer:pw@localhost:5434/db";
      queryMock.mockResolvedValueOnce(allowedRow(false, 11));
      const result = await checkAndIncrementQuota("some-hash");
      expect(result).toEqual({ allowed: false, reason: "per_client_limit" });
      expect(queryMock).toHaveBeenCalledTimes(1);
    });

    it("global quota exceeded: allowed under per-client but blocked by the global limit", async () => {
      process.env.QA_QUOTA_DATABASE_URL = "postgresql://app_quota_writer:pw@localhost:5434/db";
      queryMock.mockResolvedValueOnce(allowedRow(true, 4)).mockResolvedValueOnce(allowedRow(false, 101));
      const result = await checkAndIncrementQuota("some-hash");
      expect(result).toEqual({ allowed: false, reason: "global_limit" });
    });

    it("fails open (allowed=true) when QA_QUOTA_DATABASE_URL is not configured and mode is open", async () => {
      delete process.env.QA_QUOTA_DATABASE_URL;
      process.env.QA_QUOTA_FAILURE_MODE = "open";
      const result = await checkAndIncrementQuota("some-hash");
      expect(result).toEqual({ allowed: true, reason: "quota_service_unavailable" });
    });

    it("database unavailable in closed mode: unconfigured database blocks generation", async () => {
      delete process.env.QA_QUOTA_DATABASE_URL;
      process.env.QA_QUOTA_FAILURE_MODE = "closed";
      const result = await checkAndIncrementQuota("some-hash");
      expect(result).toEqual({ allowed: false, reason: "quota_service_unavailable" });
    });

    it("database unavailable in closed mode: a query error (configured but unreachable) blocks generation", async () => {
      process.env.QA_QUOTA_DATABASE_URL = "postgresql://app_quota_writer:pw@localhost:5434/db";
      process.env.QA_QUOTA_FAILURE_MODE = "closed";
      queryMock.mockRejectedValueOnce(new Error("connect ETIMEDOUT 10.0.0.5:5432"));
      const result = await checkAndIncrementQuota("some-hash");
      expect(result).toEqual({ allowed: false, reason: "quota_service_unavailable" });
    });

    it("database unavailable in open mode: a query error still allows generation (legacy/Preview behavior)", async () => {
      process.env.QA_QUOTA_DATABASE_URL = "postgresql://app_quota_writer:pw@localhost:5434/db";
      process.env.QA_QUOTA_FAILURE_MODE = "open";
      queryMock.mockRejectedValueOnce(new Error("connect ETIMEDOUT 10.0.0.5:5432"));
      const result = await checkAndIncrementQuota("some-hash");
      expect(result).toEqual({ allowed: true, reason: "quota_service_unavailable" });
    });

    it("redacted error response: logs only the error message, never the query args or a raw connection string", async () => {
      process.env.QA_QUOTA_DATABASE_URL = "postgresql://app_quota_writer:s3cret@localhost:5434/db";
      process.env.QA_QUOTA_FAILURE_MODE = "closed";
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      queryMock.mockRejectedValueOnce(new Error("connect ETIMEDOUT 10.0.0.5:5432"));
      await checkAndIncrementQuota("some-hash");
      expect(errorSpy).toHaveBeenCalledTimes(1);
      const loggedArgs = errorSpy.mock.calls[0];
      expect(loggedArgs.join(" ")).not.toContain("s3cret");
      expect(loggedArgs.join(" ")).not.toContain("some-hash");
      errorSpy.mockRestore();
    });
  });
});
