import { readFileSync } from "node:fs";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { closePool } from "@/lib/db/pool";
import { PostgresComparisonRepository } from "@/lib/repositories/postgres-comparison-repository";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";
import { seedAppDatabase } from "../fixtures/seed-app-database";

const repository = new PostgresComparisonRepository();
const companyRepository = new PostgresCompanyRepository();

let actLatestComparisonId: string;
let belComparisonId: string;

beforeAll(async () => {
  await seedAppDatabase();
  const actHistory = await companyRepository.getCompanyHistory("ACT");
  actLatestComparisonId = actHistory!.comparisons[actHistory!.comparisons.length - 1].id;
  const belHistory = await companyRepository.getCompanyHistory("BEL");
  belComparisonId = belHistory!.comparisons[0].id;
});

afterAll(async () => {
  await closePool();
});

describe("PostgresComparisonRepository cutover-comparison reads against the seeded test database", () => {
  it("getNarrativeUnitComparisons returns both seeded ACT rows -- cfo_conclusion resolved, healthcare_services_review unresolved -- not silently dropping either", async () => {
    const narrative = await repository.getNarrativeUnitComparisons(actLatestComparisonId);
    expect(narrative).toHaveLength(2);

    const byUnitKey = new Map(narrative.map((n) => [n.unitKey, n]));
    const cfoConclusion = byUnitKey.get("cfo_conclusion");
    expect(cfoConclusion?.comparisonBackend).toBe("SEMANTIC_UNIT");
    expect(cfoConclusion?.status).toBe("RESOLVED");
    expect(cfoConclusion?.lexicalMetrics?.tfidfCosine).toBeCloseTo(0.75, 2);
    expect(cfoConclusion?.earlierProvenance?.startPage).toBe(10);

    const healthcareServicesReview = byUnitKey.get("healthcare_services_review");
    expect(healthcareServicesReview?.comparisonBackend).toBe("SEMANTIC_UNIT");
    expect(healthcareServicesReview?.status).toBe("UNRESOLVED_UPSTREAM");
    expect(healthcareServicesReview?.reviewReason).not.toBeNull();
  });

  it("getNarrativeUnitComparisons returns an empty array (never an error) for a comparison outside the cutover scope", async () => {
    const narrative = await repository.getNarrativeUnitComparisons(belComparisonId);
    expect(narrative).toEqual([]);
  });

  it("getStructuredTableComparisons returns both ACT table families -- one resolved, one unresolved -- not mutually exclusive", async () => {
    const structured = await repository.getStructuredTableComparisons(actLatestComparisonId);
    expect(structured).toHaveLength(2);

    const byFamily = new Map(structured.map((s) => [s.tableFamilyKey, s]));
    const resolved = byFamily.get("total_remuneration_outcomes");
    expect(resolved?.status).toBe("RESOLVED");
    expect(resolved?.rowAlignments).toHaveLength(1);
    expect(resolved?.rowAlignments[0].earlierRowIdentity).toBe("a banderker");
    expect(resolved?.valueChangeEvents[0].eventType).toBe("VALUE_INCREASED");
    expect(resolved?.footnotes).toContain("Restated for prior-year comparatives.");

    const unresolved = byFamily.get("ned_remuneration_policy_table");
    expect(unresolved?.status).toBe("UNRESOLVED_UPSTREAM");
    expect(unresolved?.rowAlignments).toEqual([]);
    expect(unresolved?.reviewReason).not.toBeNull();
  });

  it("getStructuredTableComparisons returns an empty array (never an error) for a comparison outside the cutover scope", async () => {
    const structured = await repository.getStructuredTableComparisons(belComparisonId);
    expect(structured).toEqual([]);
  });
});

describe("PostgresComparisonRepository cutover-comparison source -- static query-shape checks", () => {
  const source = readFileSync(path.resolve(__dirname, "../../lib/repositories/postgres-comparison-repository.ts"), "utf-8");

  it("only queries app.current_narrative_unit_comparisons / app.current_structured_table_comparisons, never the raw app tables", () => {
    expect(source).toContain("app.current_narrative_unit_comparisons");
    expect(source).toContain("app.current_structured_table_comparisons");
    expect(source).not.toMatch(/FROM\s+app\.narrative_unit_comparisons\b/);
    expect(source).not.toMatch(/FROM\s+app\.structured_table_comparisons\b/);
  });

  it("scopes both cutover reads by report_comparison_id = $1", () => {
    const narrativeIdx = source.indexOf("getNarrativeUnitComparisons");
    const structuredIdx = source.indexOf("getStructuredTableComparisons");
    expect(source.slice(narrativeIdx, narrativeIdx + 400)).toContain("report_comparison_id = $1");
    expect(source.slice(structuredIdx, structuredIdx + 400)).toContain("report_comparison_id = $1");
  });
});
