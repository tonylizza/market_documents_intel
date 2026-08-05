import type { AlignmentStatus, ReportSide } from "@/lib/domain/passage";
import type { ComparisonDirection, QueryAnalysis, QuestionType, RequestedScope } from "@/lib/domain/qa-evidence";
import { CONCEPT_FAMILIES, matchFamilies, matchesRestatementTerms } from "@/lib/domain/concept-families";

/** Only the fields query analysis actually needs -- deliberately not the
 * full `domain/company.ts` `Company` (report counts, sector, etc. are
 * irrelevant here and would couple this pure function to an unrelated,
 * heavier domain shape). */
export interface CompanyNameLookup {
  ticker: string;
  name: string;
}

/**
 * Milestone 7B.1b: deterministic, rule-based query analysis. No LLM call --
 * the milestone requires this baseline be tried first, and with only 6
 * companies and a small controlled vocabulary (alignment statuses,
 * financial-language categories), closed-vocabulary matching is sufficient
 * and fully explainable. Every extraction is either a controlled-vocabulary
 * match or an explicit regex rule -- nothing is guessed, and anything that
 * looks relevant but doesn't resolve is surfaced in `unresolvedTerms`/
 * `warnings` rather than silently dropped (milestone requirement: "must not
 * silently narrow scope incorrectly").
 */

const KNOWN_CATEGORIES = ["risk", "financial_condition", "governance", "strategy"] as const;

/** Subcategory vocabulary observed in the real published taxonomy (see
 * `evaluation/dataset.ts`'s existing filter usage) -- not exhaustive of the
 * full custom taxonomy, but the deterministic baseline only needs to match
 * what a question could plausibly name explicitly. */
const KNOWN_SUBCATEGORIES = ["climate_environmental", "debt", "remuneration"] as const;

const ALIGNMENT_KEYWORDS: { pattern: RegExp; status: AlignmentStatus }[] = [
  { pattern: /\bnewly (introduced|disclosed|added)\b|\bnew disclosure\b/i, status: "NEW" },
  { pattern: /\bno longer (disclosed|reported|mentioned)\b|\bremoved disclosure\b/i, status: "REMOVED" },
  { pattern: /\bunchanged\b|\bstayed the same\b/i, status: "UNCHANGED" },
  { pattern: /\bslightly (modified|changed|updated)\b/i, status: "LIGHTLY_MODIFIED" },
  { pattern: /\b(substantially|materially|significantly) (modified|changed|revised)\b/i, status: "SUBSTANTIALLY_MODIFIED" },
  { pattern: /\bambiguous\b|\bunclear (change|status)\b/i, status: "AMBIGUOUS" },
];

const EARLIER_SIDE_PATTERN = /\b(earlier|prior|previous|last year'?s?|preceding)\b/i;
const LATER_SIDE_PATTERN = /\b(later|latest|current|most recent|this year'?s?|new(est)? report)\b/i;

const DIRECTION_PATTERNS: { pattern: RegExp; direction: ComparisonDirection }[] = [
  { pattern: /\b(increased?|rose|grew|higher|rising|up from|growth in)\b/i, direction: "increased" },
  { pattern: /\b(decreased?|fell|declined?|lower|falling|down from|reduction in)\b/i, direction: "decreased" },
  { pattern: /\b(added|newly introduced|introduced for the first time)\b/i, direction: "added" },
  { pattern: /\b(removed|dropped|discontinued|eliminated|no longer)\b/i, direction: "removed" },
  { pattern: /\b(changed|modified|updated|revised)\b/i, direction: "changed" },
];

/** Common finance/domain acronyms that legitimately appear in questions and
 * are not company-ticker references -- excluded from `unresolvedTerms` so
 * routine questions don't generate spurious warnings. */
const KNOWN_NON_TICKER_ACRONYMS = new Set([
  "JSE", "ESG", "CEO", "CFO", "COO", "IPO", "GRI", "USD", "ZAR", "EUR", "GBP", "IFRS", "AGM", "KPI",
]);

/** Derives a deterministic short alias from a full registered company name
 * by stripping common corporate-suffix tokens -- e.g. "AfroCentric
 * Investment Corporation Limited" -> "AfroCentric". Falls back to the first
 * word if stripping would otherwise remove everything. */
function deriveCompanyAlias(name: string): string {
  const suffixTokens = /\b(Limited|Ltd|plc|PLC|Corporation|Investment|Capital|Group|Holdings)\b/g;
  const stripped = name.replace(suffixTokens, "").replace(/\s+/g, " ").trim();
  return stripped.length > 0 ? stripped : name.split(/\s+/)[0];
}

function extractTickers(question: string, companies: readonly CompanyNameLookup[]): string[] {
  const matched = new Set<string>();
  for (const company of companies) {
    const tickerPattern = new RegExp(`\\b${company.ticker}\\b`);
    const alias = deriveCompanyAlias(company.name);
    const aliasPattern = new RegExp(`\\b${alias.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
    if (tickerPattern.test(question) || aliasPattern.test(question) || question.toLowerCase().includes(company.name.toLowerCase())) {
      matched.add(company.ticker);
    }
  }
  return [...matched];
}

function extractYears(question: string): number[] {
  return [...question.matchAll(/\b(19\d{2}|20\d{2})\b/g)].map((m) => Number.parseInt(m[1], 10));
}

function extractDateRange(question: string): { start: string | null; end: string | null } | null {
  const years = extractYears(question);
  if (years.length === 0) return null;
  const min = Math.min(...years);
  const max = Math.max(...years);
  return { start: `${min}-01-01`, end: `${max}-12-31` };
}

/** Whether the question names more than one distinct year -- the actual
 * signal for "this spans multiple report periods". A single year mentioned
 * (e.g. "in its 2025 financial statements") still produces a full Jan-Dec
 * `dateRange` (a legitimate one-year filter window), but `start !== end` on
 * that range is true for every single-year question too, so it must never
 * be used as the multi-year test -- doing so misroutes single-report
 * questions naming one year into COMPARISON_QA. */
function spansMultipleYears(question: string): boolean {
  return new Set(extractYears(question)).size > 1;
}

function extractComparisonDirection(question: string): ComparisonDirection {
  for (const { pattern, direction } of DIRECTION_PATTERNS) {
    if (pattern.test(question)) return direction;
  }
  return null;
}

function extractAlignmentStatuses(question: string): AlignmentStatus[] {
  const statuses = new Set<AlignmentStatus>();
  for (const { pattern, status } of ALIGNMENT_KEYWORDS) {
    if (pattern.test(question)) statuses.add(status);
  }
  return [...statuses];
}

function extractReportSides(question: string): ReportSide[] {
  const sides: ReportSide[] = [];
  if (EARLIER_SIDE_PATTERN.test(question)) sides.push("EARLIER");
  if (LATER_SIDE_PATTERN.test(question)) sides.push("LATER");
  return sides;
}

function extractCategories(question: string): string[] {
  const lower = question.toLowerCase();
  return KNOWN_CATEGORIES.filter((category) => lower.includes(category.replace(/_/g, " ")) || lower.includes(category));
}

function extractSubcategories(question: string): string[] {
  const lower = question.toLowerCase();
  return KNOWN_SUBCATEGORIES.filter((sub) => lower.includes(sub.replace(/_/g, " ")) || lower.includes(sub));
}

function classifyQuestionType(question: string, direction: ComparisonDirection, isMultiYear: boolean): QuestionType {
  if (/\bwhy\b|\bwhat (caused|led to|is the reason)\b|\breason for\b/i.test(question)) return "causal";
  if (/\bhow much\b|\bhow many\b|\bwhat (percentage|amount|proportion)\b/i.test(question)) return "quantitative";
  if (direction !== null || /\bcompar(e|ison|ed)\b|\bversus\b|\bvs\.?\b|\bdifference between\b/i.test(question)) return "comparative";
  if (/\bdoes\b|\bdid\b|\bis there\b|\bwas there\b|\bhas the company\b|\bhave they\b/i.test(question)) return "existence_based";
  if (isMultiYear || /\bover time\b|\btrend\b|\bhistory\b|\btimeline\b/i.test(question)) {
    return "chronological";
  }
  return "descriptive";
}

function classifyScope(tickers: string[], direction: ComparisonDirection, isMultiYear: boolean): RequestedScope {
  if (tickers.length === 0) return "corpus_wide";
  if (tickers.length === 1 && (direction !== null || isMultiYear)) return "single_comparison";
  if (tickers.length === 1) return "single_company";
  return "corpus_wide";
}

function extractUnresolvedTerms(question: string, tickers: string[]): string[] {
  const matchedTickers = new Set(tickers);
  const candidates = [...question.matchAll(/\b[A-Z]{2,5}\b/g)].map((m) => m[0]);
  return [...new Set(candidates)].filter((token) => !matchedTickers.has(token) && !KNOWN_NON_TICKER_ACRONYMS.has(token));
}

/** Milestone 7B.1c Phase 2: splits a question into separable material
 * elements at an "and <interrogative>" boundary -- e.g. "...and how does
 * it handle succession planning?" or "...and what were the exact 2026
 * budget figures?". Covers every `partially_answerable` case in the real
 * 74-case evaluation dataset (`evaluation/qa-dataset.ts`); questions
 * without this pattern are always a single element, never force-split. */
const MATERIAL_CLAUSE_SPLIT_PATTERN = /\band\s+(?:at\s+)?(?=how\b|what\b|why\b|who\b|which\b|when\b|where\b)/i;

function splitMaterialElements(question: string): string[] {
  const parts = question
    .split(MATERIAL_CLAUSE_SPLIT_PATTERN)
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  return parts.length > 1 ? parts : [question];
}

/** A material element "looks substantive" (worth flagging in
 * `unresolvedRequiredConcepts` when it matches no concept family) when it's
 * long enough to plausibly carry its own topic, not just a trailing
 * fragment like "or when?". Deliberately conservative -- under-flagging
 * (missing a genuinely unresolved concept) is preferred over noisy
 * false-positive warnings on every short clause. */
const MIN_SUBSTANTIVE_ELEMENT_WORDS = 4;

export function extractConceptAnalysis(
  normalizedQuestion: string,
  questionType: QuestionType,
  comparisonDirection: ComparisonDirection,
): Pick<
  QueryAnalysis,
  | "materialElements"
  | "requiredConceptFamilies"
  | "directionalConcepts"
  | "quantitativeConcepts"
  | "causalConcepts"
  | "ambiguitySensitiveConcepts"
  | "unresolvedRequiredConcepts"
> {
  const elementTexts = splitMaterialElements(normalizedQuestion);
  const materialElements = elementTexts.map((text) => ({ text, requiredFamilies: matchFamilies(CONCEPT_FAMILIES, text) }));
  const requiredConceptFamilies = [...new Set(materialElements.flatMap((element) => element.requiredFamilies))];

  const unresolvedRequiredConcepts =
    materialElements.length > 1
      ? materialElements.filter((element) => element.requiredFamilies.length === 0 && element.text.split(/\s+/).length >= MIN_SUBSTANTIVE_ELEMENT_WORDS).map((element) => element.text)
      : [];

  return {
    materialElements,
    requiredConceptFamilies,
    directionalConcepts: comparisonDirection !== null ? [comparisonDirection] : [],
    quantitativeConcepts: questionType === "quantitative" ? ["quantitative"] : [],
    causalConcepts: questionType === "causal" ? ["causal"] : [],
    ambiguitySensitiveConcepts: matchesRestatementTerms(normalizedQuestion) ? ["restatement_correction"] : [],
    unresolvedRequiredConcepts,
  };
}

export function analyzeQuestion(question: string, companies: readonly CompanyNameLookup[]): QueryAnalysis {
  const normalizedQuestion = question.trim().replace(/\s+/g, " ");
  const tickers = extractTickers(normalizedQuestion, companies);
  const dateRange = extractDateRange(normalizedQuestion);
  const isMultiYear = spansMultipleYears(normalizedQuestion);
  const comparisonDirection = extractComparisonDirection(normalizedQuestion);
  const alignmentStatuses = extractAlignmentStatuses(normalizedQuestion);
  const requestedReportSides = extractReportSides(normalizedQuestion);
  const categories = extractCategories(normalizedQuestion);
  const subcategories = extractSubcategories(normalizedQuestion);
  const questionType = classifyQuestionType(normalizedQuestion, comparisonDirection, isMultiYear);
  const requestedScope = classifyScope(tickers, comparisonDirection, isMultiYear);
  const unresolvedTerms = extractUnresolvedTerms(normalizedQuestion, tickers);
  const conceptAnalysis = extractConceptAnalysis(normalizedQuestion, questionType, comparisonDirection);
  // Milestone-6's existing *subcategory* taxonomy (climate_environmental,
  // debt, remuneration -- genuinely specific sub-topics) doubles as the
  // optional/corroborating-concept signal. The four broad top-level
  // `categories` (risk/financial_condition/governance/strategy) are
  // deliberately excluded here -- they already function as a *scope*
  // constraint (`requiredCategory`/`OUT_OF_SCOPE` filtering), and the
  // milestone is explicit that "scope matches alone provide zero
  // substantive support"; conflating a bare category match with genuine
  // topical coverage would let `companyOnlyIndicator`/`genericOnlyIndicator`
  // (Phase 3) be defeated by scope alone.
  const optionalConceptFamilies = [...new Set(subcategories)];

  const warnings: string[] = [];
  if (unresolvedTerms.length > 0) {
    warnings.push(`Possible company/entity reference not recognized: ${unresolvedTerms.join(", ")}`);
  }
  if (comparisonDirection !== null) {
    warnings.push(
      "Comparison direction was extracted from question wording only -- no stored signal exists to verify whether a financial figure actually increased or decreased.",
    );
  }

  return {
    question,
    normalizedQuestion,
    tickers,
    dateRange,
    comparisonDirection,
    directionConfidence: comparisonDirection !== null ? "LEXICAL_ONLY" : null,
    alignmentStatuses,
    requestedReportSides,
    categories,
    subcategories,
    questionType,
    requestedScope,
    requiredTicker: tickers.length === 1 ? tickers[0] : null,
    requiredReportSide: requestedReportSides.length === 1 ? requestedReportSides[0] : null,
    requiredCategory: categories.length === 1 ? categories[0] : null,
    unresolvedTerms,
    warnings,
    materialElements: conceptAnalysis.materialElements,
    requiredConceptFamilies: conceptAnalysis.requiredConceptFamilies,
    optionalConceptFamilies,
    directionalConcepts: conceptAnalysis.directionalConcepts,
    quantitativeConcepts: conceptAnalysis.quantitativeConcepts,
    causalConcepts: conceptAnalysis.causalConcepts,
    ambiguitySensitiveConcepts: conceptAnalysis.ambiguitySensitiveConcepts,
    unresolvedRequiredConcepts: conceptAnalysis.unresolvedRequiredConcepts,
  };
}
