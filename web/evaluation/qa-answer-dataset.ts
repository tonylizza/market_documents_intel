/**
 * Milestone 7B.2 practical evaluation dataset for the standard-RAG `/ask`
 * pipeline (`qa-chunk-retrieval-service.ts` + `qa-answer-service.ts` +
 * `question-router.ts`). Distinct from `qa-dataset.ts` (the 7B.1b/c
 * evidence-*selection*-pipeline dataset, unchanged, still used by
 * `/evidence-review`): this dataset exercises the NEW chunk-retrieval +
 * generation stack end to end, against the real, live corpus and the real
 * 6-company vocabulary (ACT, BEL, KP2, SBP, SDL, SUR).
 *
 * Per the milestone brief, this dataset characterizes quality -- it is not
 * a pass/fail gate, and cases deliberately do NOT carry hand-verified
 * ground-truth passage sets the way `qa-dataset.ts` does (that dataset's
 * rigor took a dedicated live-corpus verification pass documented in its
 * own module docstring; reproducing that same rigor for a second,
 * additive dataset was out of scope for this implementation milestone).
 * What IS honestly checkable without that verification pass:
 *   - whether retrieval returns any evidence at all for a plausible,
 *     answerable question (a retrieval-miss/no-miss proxy);
 *   - whether a genuinely absent topic correctly yields no evidence or an
 *     INSUFFICIENT_EVIDENCE-shaped result (an abstention proxy);
 *   - the answer status distribution, citation completeness (citations
 *     always resolve to real evidence by construction -- see
 *     `qa-answer-service.ts`), and provider fallback behavior;
 *   - latency.
 * See the 7B.2 final report for the honest characterization of what this
 * dataset can and cannot conclude.
 */

export type QaAnswerCaseType =
  | "straightforward"
  | "broad_descriptive"
  | "numeric"
  | "surrounding_context"
  | "no_answer"
  | "comparison"
  | "chronology"
  | "restatement"
  | "conflicting_evidence"
  | "multi_report";

export interface QaAnswerEvaluationCase {
  id: string;
  question: string;
  caseType: QaAnswerCaseType;
  companyTicker: string | null;
  /** Whether real evidence is expected to exist for this question at all --
   * `false` only for genuinely absent-topic `no_answer` cases (verified by
   * the question itself referencing a topic with no plausible presence in
   * a JSE annual-report corpus, e.g. consumer esports revenue). */
  expectEvidence: boolean;
  notes: string;
}

export const QA_ANSWER_EVALUATION_DATASET: QaAnswerEvaluationCase[] = [
  // --- straightforward ---
  {
    id: "straightforward-act-liquidity",
    question: "What did ACT disclose about liquidity risk?",
    caseType: "straightforward",
    companyTicker: "ACT",
    expectEvidence: true,
    notes: "Single company, single well-covered topic -- the same topic real 7B.1 cases confirm has corpus coverage.",
  },
  {
    id: "straightforward-bel-governance",
    question: "What is Bell Equipment Limited's governance structure?",
    caseType: "straightforward",
    companyTicker: "BEL",
    expectEvidence: true,
    notes: "Governance disclosure is a standard annual-report section for every company in this corpus.",
  },
  {
    id: "straightforward-kp2-remuneration",
    question: "What did Kore Potash plc disclose about executive remuneration?",
    caseType: "straightforward",
    companyTicker: "KP2",
    expectEvidence: true,
    notes: "Remuneration is a known-populated subcategory in the corpus's custom taxonomy.",
  },

  // --- broad descriptive ---
  {
    id: "broad-corpus-governance-practices",
    question: "What governance practices are commonly disclosed across the companies in this corpus?",
    caseType: "broad_descriptive",
    companyTicker: null,
    expectEvidence: true,
    notes: "Corpus-wide, no single company named -- exercises the CORPUS_QA route and grouped-citation display.",
  },
  {
    id: "broad-sur-strategy",
    question: "What is Spur Corporation Limited's overall business strategy?",
    caseType: "broad_descriptive",
    companyTicker: "SUR",
    expectEvidence: true,
    notes: "Broad, open-ended single-company question -- strategy sections are standard content.",
  },

  // --- numeric ---
  {
    id: "numeric-sbp-financial-condition",
    question: "What figures did Sabvest Capital Limited report about its financial condition?",
    caseType: "numeric",
    companyTicker: "SBP",
    expectEvidence: true,
    notes: "Exercises rule 5 (no direction claim without clear values/labels) -- financial_condition category is populated for this company.",
  },
  {
    id: "numeric-sdl-risk-figures",
    question: "How many risk factors did Southern Palladium Limited disclose?",
    caseType: "numeric",
    companyTicker: "SDL",
    expectEvidence: true,
    notes: "A count-style numeric question with no stored ground-truth count -- must not be answered with a fabricated number.",
  },

  // --- surrounding context ---
  {
    id: "context-act-climate",
    question: "What context did ACT provide around its climate and environmental disclosures?",
    caseType: "surrounding_context",
    companyTicker: "ACT",
    expectEvidence: true,
    notes: "climate_environmental is a known-populated subcategory -- tests whether the ~70-token chunk overlap surfaces surrounding narrative, not just a bare mention.",
  },

  // --- no answer ---
  {
    id: "no-answer-esports",
    question: "What did the company disclose about consumer esports tournament revenue?",
    caseType: "no_answer",
    companyTicker: null,
    expectEvidence: false,
    notes: "Genuinely absent topic -- none of these six JSE-listed companies (financial services, equipment, mining, investment holding, consumer retail) discloses esports tournament revenue. Reused verification logic from qa-dataset.ts's no-answer cases (same corpus).",
  },
  {
    id: "no-answer-cryptocurrency-mining",
    question: "What did the company disclose about cryptocurrency mining operations?",
    caseType: "no_answer",
    companyTicker: null,
    expectEvidence: false,
    notes: "Genuinely absent topic for this corpus -- none of the six companies operates in cryptocurrency mining.",
  },

  // --- comparison ---
  {
    id: "comparison-act-risk-change",
    question: "Did ACT's risk disclosures increase or decrease between its earlier and later reports?",
    caseType: "comparison",
    companyTicker: "ACT",
    expectEvidence: true,
    notes: "Exercises the COMPARISON_QA route and bothSidesPresent/singleSidedComparisonWarning caution -- ACT has multiple published reports.",
  },
  {
    id: "comparison-bel-governance-change",
    question: "How did Bell Equipment Limited's governance disclosures change compared to its previous report?",
    caseType: "comparison",
    companyTicker: "BEL",
    expectEvidence: true,
    notes: "Requires evidence from two distinct report periods before any change claim is asserted.",
  },

  // --- chronology ---
  {
    id: "chronology-kp2-strategy-over-time",
    question: "How has Kore Potash plc's strategy evolved over time across its reports?",
    caseType: "chronology",
    companyTicker: "KP2",
    expectEvidence: true,
    notes: "Chronological question type -- routes to COMPARISON_QA; KP2 has several published reports spanning multiple years.",
  },

  // --- restatements ---
  {
    id: "restatement-sbp-corrected-figures",
    question: "Did Sabvest Capital Limited restate or correct any previously disclosed figures?",
    caseType: "restatement",
    companyTicker: "SBP",
    expectEvidence: true,
    notes: "Restatement vocabulary question -- tests whether the answer distinguishes an explicit restatement from an ordinary period-over-period change (rule 6/7).",
  },

  // --- conflicting evidence ---
  {
    id: "conflicting-sdl-risk-assessment",
    question: "Is Southern Palladium Limited's overall risk profile improving or worsening?",
    caseType: "conflicting_evidence",
    companyTicker: "SDL",
    expectEvidence: true,
    notes: "Open-ended judgment question likely to retrieve excerpts describing both improving and worsening individual risk factors -- tests rule 9 (do not silently pick one side of a conflict).",
  },

  // --- multi-report ---
  {
    id: "multi-report-kp2-all-years",
    question: "Across all of Kore Potash plc's annual reports, what strategic themes recur?",
    caseType: "multi_report",
    companyTicker: "KP2",
    expectEvidence: true,
    notes: "Explicitly asks across every report for one company -- KP2 has 4 published reports in the corpus, exercising multi-report evidence aggregation within DOCUMENT_QA/COMPARISON_QA scoping.",
  },
  {
    id: "multi-report-corpus-risk-themes",
    question: "What risk themes appear across multiple companies' most recent reports?",
    caseType: "multi_report",
    companyTicker: null,
    expectEvidence: true,
    notes: "Cross-company, cross-report -- exercises CORPUS_QA's group-by-company-then-report citation structure with more than one company/report actually represented.",
  },
];
