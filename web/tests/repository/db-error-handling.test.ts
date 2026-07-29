import { afterEach, describe, expect, it } from "vitest";
import { closePool } from "@/lib/db/pool";
import { DatabaseUnavailableError } from "@/lib/db/errors";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";

const ORIGINAL_URL = process.env.APP_READONLY_DATABASE_URL;

afterEach(async () => {
  await closePool();
  process.env.APP_READONLY_DATABASE_URL = ORIGINAL_URL;
});

describe("database error translation", () => {
  it("translates a connection failure into DatabaseUnavailableError, never a raw driver error", async () => {
    // An unreachable port on localhost -- fails fast with ECONNREFUSED.
    process.env.APP_READONLY_DATABASE_URL = "postgresql://app_readonly:wrong@localhost:1/nonexistent_db";
    const repository = new PostgresCompanyRepository();

    await expect(repository.listCompanies()).rejects.toBeInstanceOf(DatabaseUnavailableError);
  });

  it("the translated error never includes the connection string", async () => {
    process.env.APP_READONLY_DATABASE_URL = "postgresql://app_readonly:wrong@localhost:1/nonexistent_db";
    const repository = new PostgresCompanyRepository();

    try {
      await repository.listCompanies();
      expect.unreachable("expected listCompanies to throw");
    } catch (error) {
      expect((error as Error).message).not.toContain("wrong");
      expect((error as Error).message).not.toContain("app_readonly");
    }
  });
});
