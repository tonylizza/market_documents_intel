import { describe, expect, it } from "vitest";
import { CONCEPT_FAMILIES, matchFamilies, matchesFamily, matchesRestatementTerms, getConceptFamily } from "@/lib/domain/concept-families";

describe("concept-families -- generic/company/ticker exclusion", () => {
  it("never treats a bare company ticker as a concept-family trigger", () => {
    const matches = matchFamilies(CONCEPT_FAMILIES, "ACT");
    expect(matches).toEqual([]);
  });

  it("never treats the milestone's named generic words alone as a trigger", () => {
    for (const word of ["performance", "strategy", "operations", "growth", "outlook", "shareholders"]) {
      expect(matchFamilies(CONCEPT_FAMILIES, word)).toEqual([]);
    }
  });

  it("does match a specific multi-word phrase that happens to contain a generic word", () => {
    expect(matchFamilies(CONCEPT_FAMILIES, "What growth opportunities has ACT identified?")).toContain("growth_opportunities");
  });
});

describe("concept-families -- worked examples from the milestone plan", () => {
  it("matches the foreign-exchange family on its synonym set", () => {
    const family = getConceptFamily("foreign_exchange")!;
    for (const term of ["foreign exchange exposure", "FX risk", "currency exposure", "hedging policy"]) {
      expect(matchesFamily(family, term)).toBe(true);
    }
  });

  it("matches the margin-pressure family on its synonym set", () => {
    const family = getConceptFamily("margin_pressure")!;
    expect(matchesFamily(family, "operating margin declined due to cost inflation")).toBe(true);
  });

  it("matches the debt-covenant family without over-matching on unrelated text", () => {
    const family = getConceptFamily("debt_covenant")!;
    expect(matchesFamily(family, "the lender required a covenant waiver")).toBe(true);
    expect(matchesFamily(family, "the board reviewed strategy")).toBe(false);
  });
});

describe("matchesRestatementTerms", () => {
  it("matches restatement/correction vocabulary", () => {
    expect(matchesRestatementTerms("the prior period was restated")).toBe(true);
    expect(matchesRestatementTerms("as restated, the figure increased")).toBe(true);
    expect(matchesRestatementTerms("ordinary unrelated prose")).toBe(false);
  });
});
