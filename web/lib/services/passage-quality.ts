/**
 * Milestone 7B.1a: deterministic, explainable passage-quality features used
 * to remediate "short-passage similarity inflation" -- very short,
 * heading-like, or generic fragments (e.g. a 2-word passage whose entire
 * text is literally its own heading, "Operations (continued)") that rank
 * highly by raw cosine similarity despite carrying little substantive
 * meaning.
 *
 * Every feature here is computed purely from fields already published to
 * `app.passages`/`app.retrieval_contexts` (heading, text, word_count,
 * passage_type, language-signal presence) plus one corpus-wide heading-
 * frequency aggregate -- no new schema, no LLM classifier, no learned
 * weights. Real-corpus inspection (Milestone 7B.1a report) found this
 * pattern affects roughly half the corpus: 42.7% of passages are 1-5 words
 * and 95.2% of those are exact heading-duplicates; 14.0% are 6-15 words
 * with a 56.1% duplicate rate; bands of 16+ words have zero exact
 * heading-duplicates. These thresholds are chosen from that real
 * distribution, not guessed.
 */

/** Below this word count, a passage is never adjusted regardless of any
 * other feature -- real-corpus inspection found zero heading-duplicate
 * fragments at or above this length. */
export const SUBSTANTIVE_WORD_COUNT_THRESHOLD = 16;

/** A heading appearing more than this many times across the current
 * publication is treated as a generic/structural label (running header,
 * navigation link, section boilerplate) rather than a distinguishing
 * title. Real corpus: "BACK" (80x), "OVERVIEW" (92x), "USD" (429x). */
export const REPEATED_HEADING_FREQUENCY_THRESHOLD = 6;

/** A passage whose alphabetic-token ratio falls below this is dominated by
 * numbers/symbols (a table/statistics dump), not prose. */
export const MIN_ALPHABETIC_TOKEN_RATIO = 0.5;

/** `text` within this many characters of `heading`'s own length is treated
 * as a heading-only fragment (allows for trivial trailing punctuation/
 * whitespace without requiring byte-exact equality). */
const HEADING_ONLY_SLACK_CHARS = 5;

const CONTINUED_PATTERN = /\bcontinued\b|\(cont\.?\)/i;
const TERMINAL_PUNCTUATION_PATTERN = /[.!?]["')\]]?\s*$/;

/** Milestone 7B.1b: verbs/phrases that indicate a numeric figure is being
 * explained rather than just listed -- used only by
 * `computeNumericFragmentSeverity`, never by `computeQualityAdjustment`
 * (the existing `/passages` reranker's contract is unchanged). */
const EXPLANATORY_VERB_PATTERN =
  /\b(increased?|decreased?|rose|fell|grew|declined?|totaled|totalled|amounted to|reported|represents?|compared to|driven by|primarily due to)\b/i;

/** A passage is "table-row-like" when numeric tokens dominate and
 * alphabetic/prose tokens are sparse -- e.g. "EUR (5% movement) (1,450)
 * 1,450 4 (4)", a real corpus example with almost no explanatory prose. */
const TABLE_ROW_NUMERIC_RATIO_THRESHOLD = 0.4;
const TABLE_ROW_ALPHABETIC_RATIO_THRESHOLD = 0.3;

/** A short fragment that is nearly all percentage/numeric figures with no
 * surrounding prose (e.g. "Operating margin (0.9%) (0.2%) (13.9%)" -- the
 * heading/label itself contributes a couple of alphabetic tokens, so this
 * is deliberately more permissive than `TABLE_ROW_ALPHABETIC_RATIO_THRESHOLD`). */
const PERCENTAGE_FRAGMENT_MAX_ALPHABETIC_RATIO = 0.5;
const PERCENTAGE_FRAGMENT_MAX_WORD_COUNT = 15;

/** Real corpus text frequently attaches punctuation directly to a numeric
 * or alphabetic token with no space (e.g. "(1,450)", "(5%", "movement)") --
 * stripped here so numeric-fragment detection isn't defeated by adjacent
 * parentheses. Deliberately a *separate* classification from
 * `isAlphabeticToken`/`isNumericToken` above, which back the existing
 * shipped `/passages` quality-adjustment thresholds and must not change. */
function stripSurroundingPunctuation(token: string): string {
  return token.replace(/^[^\w%]+|[^\w%]+$/g, "");
}

function isNumericFragmentToken(token: string): boolean {
  const stripped = stripSurroundingPunctuation(token);
  return stripped.length > 0 && /^[-+]?[\d.,%$£€]+$/.test(stripped) && /\d/.test(stripped);
}

function isAlphabeticFragmentToken(token: string): boolean {
  const stripped = stripSurroundingPunctuation(token);
  return /^[A-Za-z][A-Za-z'-]*$/.test(stripped);
}

export type QualityExplanationCode =
  | "NO_QUALITY_ADJUSTMENT"
  | "RETAINED_SHORT_FINANCIAL_SENTENCE"
  | "LOW_SUBSTANTIVE_TOKEN_COUNT"
  | "HEADING_ONLY_FRAGMENT"
  | "SHORT_GENERIC_HEADING_PENALTY";

export interface PassageQualityInput {
  heading: string | null;
  text: string;
  wordCount: number;
  /** Whether any published language-signal category was ever detected for
   * this passage in any of its retrieval contexts -- an explicit override
   * so a short but financially-dense passage is never penalized purely for
   * its length (milestone requirement: "passages with high financial-
   * language density despite short length"). */
  hasLanguageSignal: boolean;
  /** How many times this exact heading text appears across the current
   * publication's passages (0 when the passage has no heading). */
  headingFrequency: number;
  /** Milestone 7B.1b: whether another passage covering the same page range
   * was also retrieved alongside this one -- supplied only by the Q&A
   * candidate-generation layer (the existing `/passages` reranker has no
   * such input and never needs one). `undefined`/omitted means the caller
   * didn't evaluate this (treated the same as not-available, never assumed
   * true). */
  hasNearbyContext?: boolean;
}

export interface PassageQualityFeatures {
  wordCount: number;
  alphabeticTokenRatio: number;
  uppercaseTokenRatio: number;
  numericTokenRatio: number;
  headingWordCount: number;
  headingToTotalRatio: number;
  isHeadingOnlyFragment: boolean;
  endsWithTerminalPunctuation: boolean;
  hasCompleteSentenceHeuristic: boolean;
  containsContinued: boolean;
  isRepeatedGenericHeading: boolean;
  hasLanguageSignal: boolean;
  /** Milestone 7B.1b numeric-fragment features -- additive, never consulted
   * by `computeQualityAdjustment` (the shipped `/passages` reranker). */
  proseToNumberRatio: number;
  hasExplanatoryVerb: boolean;
  looksLikeTableRow: boolean;
  isPercentageOnlyFragment: boolean;
  hasNearbyContext: boolean | null;
}

function tokenize(text: string): string[] {
  return text.split(/\s+/).filter((token) => token.length > 0);
}

function isAlphabeticToken(token: string): boolean {
  return /^[A-Za-z][A-Za-z'-]*$/.test(token);
}

function isUppercaseToken(token: string): boolean {
  return isAlphabeticToken(token) && token === token.toUpperCase() && token.length > 1;
}

function isNumericToken(token: string): boolean {
  return /^[-+]?[\d.,%$£€]+$/.test(token) && /\d/.test(token);
}

export function computePassageQualityFeatures(input: PassageQualityInput): PassageQualityFeatures {
  const trimmedText = input.text.trim();
  const trimmedHeading = input.heading?.trim() ?? null;
  const tokens = tokenize(trimmedText);
  const wordCount = input.wordCount;

  const alphabeticCount = tokens.filter(isAlphabeticToken).length;
  const uppercaseCount = tokens.filter(isUppercaseToken).length;
  const numericCount = tokens.filter(isNumericToken).length;

  const headingWordCount = trimmedHeading ? tokenize(trimmedHeading).length : 0;
  const headingToTotalRatio = wordCount > 0 ? Math.min(1, headingWordCount / wordCount) : 0;

  const isHeadingOnlyFragment =
    trimmedHeading !== null &&
    trimmedHeading.length > 0 &&
    trimmedText.length <= trimmedHeading.length + HEADING_ONLY_SLACK_CHARS &&
    trimmedText.toLowerCase().startsWith(trimmedHeading.toLowerCase().slice(0, Math.min(trimmedHeading.length, 12)));

  const endsWithTerminalPunctuation = TERMINAL_PUNCTUATION_PATTERN.test(trimmedText);
  // A deliberately narrow heuristic (not a real parser): "looks like a
  // sentence" if it has enough words to plausibly contain a
  // subject/verb/object and ends the way real prose usually does. Never
  // used alone to *penalize* -- only to avoid over-crediting punctuation-
  // free table/label text as substantive.
  const hasCompleteSentenceHeuristic = wordCount >= 6 && endsWithTerminalPunctuation;

  const containsContinued = trimmedHeading !== null && CONTINUED_PATTERN.test(trimmedHeading);
  const isRepeatedGenericHeading = input.headingFrequency > REPEATED_HEADING_FREQUENCY_THRESHOLD;

  const alphabeticTokenRatio = tokens.length > 0 ? alphabeticCount / tokens.length : 0;
  const numericTokenRatio = tokens.length > 0 ? numericCount / tokens.length : 0;

  // Numeric-fragment detection uses punctuation-stripped token
  // classification (see `stripSurroundingPunctuation`) rather than the
  // ratios above, since real corpus numeric fragments frequently attach
  // parentheses/percent signs directly to a token with no space.
  const fragmentAlphabeticCount = tokens.filter(isAlphabeticFragmentToken).length;
  const fragmentNumericCount = tokens.filter(isNumericFragmentToken).length;
  const fragmentAlphabeticRatio = tokens.length > 0 ? fragmentAlphabeticCount / tokens.length : 0;
  const fragmentNumericRatio = tokens.length > 0 ? fragmentNumericCount / tokens.length : 0;

  const proseToNumberRatio = fragmentAlphabeticCount / Math.max(1, fragmentNumericCount);
  const hasExplanatoryVerb = EXPLANATORY_VERB_PATTERN.test(trimmedText);
  const looksLikeTableRow =
    fragmentNumericRatio > TABLE_ROW_NUMERIC_RATIO_THRESHOLD && fragmentAlphabeticRatio < TABLE_ROW_ALPHABETIC_RATIO_THRESHOLD;
  const isPercentageOnlyFragment =
    /%/.test(trimmedText) &&
    fragmentAlphabeticRatio <= PERCENTAGE_FRAGMENT_MAX_ALPHABETIC_RATIO &&
    wordCount <= PERCENTAGE_FRAGMENT_MAX_WORD_COUNT;

  return {
    wordCount,
    alphabeticTokenRatio,
    uppercaseTokenRatio: tokens.length > 0 ? uppercaseCount / tokens.length : 0,
    numericTokenRatio,
    headingWordCount,
    headingToTotalRatio,
    isHeadingOnlyFragment,
    endsWithTerminalPunctuation,
    hasCompleteSentenceHeuristic,
    containsContinued,
    isRepeatedGenericHeading,
    hasLanguageSignal: input.hasLanguageSignal,
    proseToNumberRatio,
    hasExplanatoryVerb,
    looksLikeTableRow,
    isPercentageOnlyFragment,
    hasNearbyContext: input.hasNearbyContext ?? null,
  };
}

export type NumericFragmentSeverity = "none" | "fragment_with_context" | "fragment_without_context";

/**
 * Milestone 7B.1b: classifies whether a passage is a "bare" numeric/table
 * fragment that should not, by itself, be treated as sufficient Q&A
 * evidence -- distinct from `computeQualityAdjustment`, which governs the
 * existing `/passages` semantic ranking and is never modified by this
 * function. Numeric fragments remain searchable (this never removes or
 * excludes a passage) -- it only informs the Q&A groundedness gate that a
 * passage is a number/table dump, and whether an adjacent context was found
 * that explains it. A fragment with `hasExplanatoryVerb` present in its own
 * text is not penalized even if it also looks table-like (the milestone
 * requires "numeric evidence may be retained when paired with explanatory
 * prose" -- explanatory prose in the *same* passage counts, not only a
 * neighboring one).
 */
export function computeNumericFragmentSeverity(features: PassageQualityFeatures): NumericFragmentSeverity {
  const isBareNumericFragment = (features.looksLikeTableRow || features.isPercentageOnlyFragment) && !features.hasExplanatoryVerb;
  if (!isBareNumericFragment) return "none";
  return features.hasNearbyContext === true ? "fragment_with_context" : "fragment_without_context";
}

export interface QualityAdjustmentConfig {
  /** Bounded multiplier for an exact/near-exact heading-only fragment. */
  headingOnlyFragmentFactor: number;
  /** Bounded multiplier for a short passage with a generic/repeated or
   * "(continued)" heading, but not an exact heading-only duplicate. */
  genericHeadingFactor: number;
  /** Mild bounded multiplier for a passage below the substantive-length
   * threshold that isn't classified as a fragment or generic heading. */
  lowSubstantiveFactor: number;
}

export const DEFAULT_QUALITY_ADJUSTMENT_CONFIG: QualityAdjustmentConfig = {
  headingOnlyFragmentFactor: 0.5,
  genericHeadingFactor: 0.6,
  lowSubstantiveFactor: 0.85,
};

export interface QualityAdjustment {
  factor: number;
  explanationCode: QualityExplanationCode;
}

/**
 * Deterministic quality-adjustment rule. Never returns a factor of 0 (a
 * bounded demotion, not deletion -- see milestone: "no arbitrary large
 * penalty", "preserve useful short substantive passages"). A real
 * financial-language signal always wins over any length-based penalty.
 */
export function computeQualityAdjustment(
  features: PassageQualityFeatures,
  config: QualityAdjustmentConfig = DEFAULT_QUALITY_ADJUSTMENT_CONFIG,
): QualityAdjustment {
  if (features.wordCount >= SUBSTANTIVE_WORD_COUNT_THRESHOLD) {
    return { factor: 1, explanationCode: "NO_QUALITY_ADJUSTMENT" };
  }

  const wouldBePenalized =
    features.isHeadingOnlyFragment ||
    features.isRepeatedGenericHeading ||
    features.containsContinued ||
    features.alphabeticTokenRatio < MIN_ALPHABETIC_TOKEN_RATIO;

  if (features.hasLanguageSignal) {
    return wouldBePenalized
      ? { factor: 1, explanationCode: "RETAINED_SHORT_FINANCIAL_SENTENCE" }
      : { factor: 1, explanationCode: "NO_QUALITY_ADJUSTMENT" };
  }

  if (features.isHeadingOnlyFragment) {
    return { factor: config.headingOnlyFragmentFactor, explanationCode: "HEADING_ONLY_FRAGMENT" };
  }
  if (features.isRepeatedGenericHeading || features.containsContinued) {
    return { factor: config.genericHeadingFactor, explanationCode: "SHORT_GENERIC_HEADING_PENALTY" };
  }
  if (wouldBePenalized || !features.hasCompleteSentenceHeuristic) {
    return { factor: config.lowSubstantiveFactor, explanationCode: "LOW_SUBSTANTIVE_TOKEN_COUNT" };
  }
  return { factor: 1, explanationCode: "NO_QUALITY_ADJUSTMENT" };
}
