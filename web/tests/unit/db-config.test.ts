import { describe, expect, it } from "vitest";
import { loadDatabaseConfig, redactDatabaseUrl } from "@/lib/db/config";
import { DatabaseConfigError } from "@/lib/db/errors";

describe("loadDatabaseConfig", () => {
  it("throws DatabaseConfigError when the value is missing", () => {
    // An explicit empty override, not `undefined` -- the test setup file
    // sets a real `APP_READONLY_DATABASE_URL` for repository tests, and
    // `undefined` legitimately falls back to that ambient value by design
    // (mirrors how the real app reads `process.env` in production).
    expect(() => loadDatabaseConfig("")).toThrow(DatabaseConfigError);
  });

  it("throws DatabaseConfigError when the value is an empty string", () => {
    expect(() => loadDatabaseConfig("   ")).toThrow(DatabaseConfigError);
  });

  it("throws DatabaseConfigError when the value is not a valid URL", () => {
    expect(() => loadDatabaseConfig("not-a-url")).toThrow(DatabaseConfigError);
  });

  it("throws DatabaseConfigError for an unsupported scheme", () => {
    expect(() => loadDatabaseConfig("mysql://user:pw@localhost:3306/db")).toThrow(DatabaseConfigError);
  });

  it("accepts a valid postgresql:// URL", () => {
    const config = loadDatabaseConfig("postgresql://app_readonly:secret@localhost:5434/market_documents_app");
    expect(config.connectionString).toBe("postgresql://app_readonly:secret@localhost:5434/market_documents_app");
  });

  it("accepts a valid postgres:// URL", () => {
    const config = loadDatabaseConfig("postgres://app_readonly:secret@localhost:5434/market_documents_app");
    expect(config.sslMode).toBeNull();
  });

  it("extracts sslmode from the query string", () => {
    const config = loadDatabaseConfig("postgresql://user:pw@host:5432/db?sslmode=require");
    expect(config.sslMode).toBe("require");
  });
});

describe("redactDatabaseUrl", () => {
  it("never includes the username or password", () => {
    const redacted = redactDatabaseUrl("postgresql://app_readonly:super-secret-password@localhost:5434/market_documents_app");
    expect(redacted).not.toContain("super-secret-password");
    expect(redacted).not.toContain("app_readonly");
  });

  it("never includes query string parameters", () => {
    const redacted = redactDatabaseUrl("postgresql://user:pw@host:5432/db?sslmode=require&password=leak");
    expect(redacted).not.toContain("leak");
    expect(redacted).not.toContain("sslmode");
  });

  it("keeps only scheme, host, port, and database name", () => {
    const redacted = redactDatabaseUrl("postgresql://user:pw@example.com:5434/market_documents_app");
    expect(redacted).toBe("postgresql://example.com:5434/market_documents_app");
  });

  it("falls back to a fixed placeholder for an unparseable value", () => {
    const redacted = redactDatabaseUrl("not a url at all");
    expect(redacted).toBe("postgresql://<redacted>");
  });
});
