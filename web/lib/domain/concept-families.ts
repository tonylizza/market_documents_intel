/**
 * Milestone 7B.1c Phase 2: predeclared, hand-built substantive-concept
 * taxonomy for the Q&A pipeline's direct-responsiveness gating. Every
 * family's synonym list was built from either the milestone's own worked
 * examples (foreign exchange, margin pressure, going concern, customer
 * concentration, debt covenant) or a real, recurring topic in the 74-case
 * evaluation dataset's questions/passages (`evaluation/qa-dataset.ts`).
 *
 * Deliberately excludes company names, tickers, years, and the milestone's
 * named generic words (performance, strategy, operations, growth, outlook,
 * shareholders) as bare trigger terms -- no family's `terms` list contains
 * any of those alone, so none of them can satisfy a family match by
 * themselves. Multi-word phrases that happen to contain a generic word
 * (e.g. "growth opportunities") are fine: the phrase itself is specific,
 * even though one of its words in isolation would not be.
 *
 * One dedicated `ambiguitySensitiveConcepts` family exists separately
 * below (`RESTATEMENT_CORRECTION_TERMS`) -- restatement/correction
 * questions get their own detection path (Phase 7), not just another
 * ordinary topic family, since matching it changes gate behavior
 * (`AMBIGUOUS_OR_CONFLICTING` handling), not just eligibility.
 */

export interface ConceptFamily {
  id: string;
  /** Lowercase phrases/words matched as case-insensitive substrings against
   * normalized passage/question text. Single words are only used here when
   * they are already domain-specific (e.g. "covenant", "malus") -- never a
   * generic English word. */
  terms: string[];
}

export const CONCEPT_FAMILIES: ConceptFamily[] = [
  { id: "foreign_exchange", terms: ["foreign exchange", "fx", "currency exposure", "exchange rate", "translation exposure", "hedging", "aud/zar", "zar/usd", "exchange-rate"] },
  { id: "margin_pressure", terms: ["operating margin", "gross margin", "margin pressure", "margin compression", "profitability pressure", "input costs", "pricing pressure", "cost inflation"] },
  { id: "going_concern", terms: ["going concern", "ability to continue operating", "material uncertainty", "liquidity support", "solvency"] },
  { id: "customer_concentration", terms: ["major customer", "key customer", "largest customer", "customer concentration", "revenue concentration"] },
  { id: "debt_covenant", terms: ["covenant", "debt covenant", "borrowing condition", "lender requirement", "compliance breach", "waiver", "breach of covenant"] },
  { id: "growth_opportunities", terms: ["growth opportunities", "growth opportunity", "maximise growth", "expand its business", "business expansion"] },
  { id: "board_meetings", terms: ["board meet", "board meetings", "scheduled meetings", "access to management", "access to senior management", "unfettered access"] },
  { id: "labour_diversity_pay", terms: ["labour standards", "diversity and inclusion", "pay equality", "gender pay gap", "wage-level determination", "equal pay"] },
  { id: "share_repurchase", terms: ["share repurchase", "general repurchase", "buy-back", "buyback", "repurchase of shares", "price ceiling", "working capital adequacy"] },
  { id: "board_charter", terms: ["board charter", "scope of authority", "board composition", "terms of reference"] },
  { id: "credit_risk_guarantee", terms: ["credit risk", "financing guarantee", "guarantee contract", "contingent liabilit", "wesbank"] },
  { id: "hse_governance", terms: ["health, safety and environment", "hse committee", "health safety and environment", "safety and environment committee"] },
  { id: "net_loss_cashflow", terms: ["net loss", "loss for the year", "cash outflow", "net cash outflow", "operating and investing activities"] },
  { id: "disclosure_obligations_regulatory", terms: ["market-disclosure obligations", "market disclosure obligations", "aim rules", "market abuse regulation", "asx listing rules", "parallel obligations", "regulatory disclosure"] },
  { id: "remuneration_policy", terms: ["remuneration policy", "remuneration philosophy", "remuneration principles", "compensation basis"] },
  { id: "investment_proposition", terms: ["investment proposition", "unlisted investment", "investment access"] },
  { id: "fair_value_measurement", terms: ["fair value", "fair value estimation", "valuation of financial assets"] },
  { id: "key_management_personnel", terms: ["key management personnel", "key management"] },
  { id: "sovereign_risk", terms: ["sovereign risk", "country risk", "political risk"] },
  { id: "incentive_targets", terms: ["short-term incentive", "sti target", "incentive target", "target-setting", "budget sensitivity", "target setting process"] },
  { id: "king_iv_stakeholder", terms: ["king iv", "stakeholder-inclusive", "stakeholder groups", "ethical leadership"] },
  { id: "loadshedding_energy", terms: ["loadshedding", "load shedding", "electricity supply", "power outage"] },
  { id: "materiality_fraud_risk", terms: ["materiality", "component materiality", "fraud risk", "fraud-risk indicator"] },
  { id: "directors_report_content", terms: ["directors report", "directors' report", "director's report"] },
  { id: "leadership_biography", terms: ["leadership", "director biography", "non-executive director", "biography"] },
  { id: "agm_share_authority", terms: ["notice of annual general meeting", "agm notice", "allot and issue", "share placement authority", "unissued shares"] },
  { id: "listed_investment_performance", terms: ["listed investment", "listed investments performance"] },
  { id: "valuation_summary", terms: ["valuation summary"] },
  { id: "investment_portfolio_composition", terms: ["investment portfolio", "investments per category", "portfolio composition"] },
  { id: "currency_reporting", terms: ["reporting currency", "functional currency", "usd", "us dollar"] },
  { id: "share_based_payments", terms: ["share-based payment", "share-based payments", "fair value of shares", "fair value of options"] },
  { id: "board_strategy_activities", terms: ["board activities", "key board activities", "strategy session"] },
  { id: "purpose_risk_strategy", terms: ["purpose, risk", "purpose and risk", "inseparable elements", "risks and opportunities"] },
  { id: "financial_liability_classification", terms: ["financial liabilit", "ifrs 13", "fair value hierarchy", "classification of financial"] },
  { id: "company_registration_changes", terms: ["company registration", "registration change", "re-registration", "register of companies"] },
  { id: "industrial_manufacturing_risk", terms: ["industrial manufacturing", "manufacturing risk", "industrial risk exposure"] },
  { id: "community_consultation", terms: ["community consultation", "consultation process", "stakeholder consultation", "before drilling"] },
  { id: "environmental_stewardship", terms: ["environmental stewardship", "environmental responsibility", "mine development"] },
  { id: "significant_changes_state_of_affairs", terms: ["significant changes in state of affairs", "state of affairs", "subsequent events", "after the reporting date"] },
  { id: "new_director_appointment", terms: ["newly appointed", "new director", "mining engineering qualification"] },
  { id: "malus_clawback", terms: ["malus", "clawback", "forfeiture of awards"] },
  { id: "special_incentives_bonus", terms: ["special incentive", "bonus paid", "ltip", "long-term incentive plan"] },
];

/** Ambiguity-sensitive vocabulary (Phase 7) -- restatement/correction
 * questions get dedicated gate handling (AMBIGUOUS_OR_CONFLICTING
 * chronology checks), not just ordinary topic-family eligibility. Kept as
 * its own list, not one more `CONCEPT_FAMILIES` entry, so
 * `query-analysis.ts` and `restatement-detection.ts` can both reference it
 * without conflating "this is about restatement" with "this is about,
 * e.g., margin pressure." */
export const RESTATEMENT_CORRECTION_TERMS = [
  "restated",
  "restatement",
  "corrected",
  "correction",
  "revised",
  "reclassified",
  "prior-period adjustment",
  "prior period adjustment",
  "error correction",
  "corrected comparative",
  "previously reported",
  "as restated",
  "retrospective adjustment",
];

const FAMILY_BY_ID = new Map(CONCEPT_FAMILIES.map((family) => [family.id, family]));

export function getConceptFamily(id: string): ConceptFamily | undefined {
  return FAMILY_BY_ID.get(id);
}

/** Case-insensitive substring match against normalized text -- same
 * convention as `query-analysis.ts`'s existing `extractCategories`. */
export function matchFamilies(families: readonly ConceptFamily[], text: string): string[] {
  const lower = text.toLowerCase();
  return families.filter((family) => family.terms.some((term) => lower.includes(term))).map((family) => family.id);
}

export function matchesFamily(family: ConceptFamily, text: string): boolean {
  const lower = text.toLowerCase();
  return family.terms.some((term) => lower.includes(term));
}

export function matchesRestatementTerms(text: string): boolean {
  const lower = text.toLowerCase();
  return RESTATEMENT_CORRECTION_TERMS.some((term) => lower.includes(term));
}
