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
  it("getNarrativeUnitComparison returns the seeded resolved cfo_conclusion row for ACT's latest comparison", async () => {
    const narrative = await repository.getNarrativeUnitComparison(actLatestComparisonId);
    expect(narrative).not.toBeNull();
    expect(narrative?.comparisonBackend).toBe("SEMANTIC_UNIT");
    expect(narrative?.status).toBe("RESOLVED");
    expect(narrative?.unitKey).toBe("cfo_conclusion");
    expect(narrative?.lexicalMetrics?.tfidfCosine).toBeCloseTo(0.75, 2);
    expect(narrative?.earlierProvenance?.startPage).toBe(10);
  });

  it("getNarrativeUnitComparison returns null (never throws) for a comparison outside the cutover scope", async () => {
    const narrative = await repository.getNarrativeUnitComparison(belComparisonId);
    expect(narrative).toBeNull();
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
    const narrativeIdx = source.indexOf("getNarrativeUnitComparison");
    const structuredIdx = source.indexOf("getStructuredTableComparisons");
    expect(source.slice(narrativeIdx, narrativeIdx + 400)).toContain("report_comparison_id = $1");
    expect(source.slice(structuredIdx, structuredIdx + 400)).toContain("report_comparison_id = $1");
  });
});
