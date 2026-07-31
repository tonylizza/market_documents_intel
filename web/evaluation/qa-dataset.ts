import type { GateReasonCode } from "@/lib/domain/qa-evidence";
import type { ReportSide } from "@/lib/domain/passage";

/**
 * Milestone 7B.1b: answer-oriented evaluation dataset for the Q&A evidence-
 * selection and groundedness-gating pipeline. Every passage id referenced
 * here was read directly from the live corpus (real SQL queries against
 * `market_documents_app`, documented in the Milestone 7B.1b final report) --
 * never derived from this pipeline's own retrieval output, and never
 * guessed. Ground truth for the `no_answer`/`insufficient_evidence` cases
 * reuses the same genuinely-absent-topic verification methodology as the
 * Milestone 7B.1a retrieval-evaluation dataset (same corpus, unchanged).
 *
 * Distinct from `evaluation/dataset.ts` (the Milestone 7B.1/7B.1a retrieval
 * dataset): that dataset grades passage *retrieval* relevance; this one
 * grades whether the Q&A pipeline can assemble a coherent *evidence set*
 * and correctly classify answerability. A few passage ids are intentionally
 * reused (e.g. known short-fragment traps) where a genuinely different,
 * answer-oriented question legitimately needs the same real, already-
 * verified passage as ground truth -- never the same case wholesale.
 *
 * Corpus is only 6 companies (ACT, BEL, KP2, SBP, SDL, SUR) / ~25 report
 * comparisons -- breadth here comes from question variety across that real
 * set, not from a larger corpus.
 *
 * Correction applied during real-evaluation verification: the initial
 * dataset-construction query selected `retrieval_contexts.id` (the
 * comparison-context identity) under a comment implying it was the passage
 * id, which silently made every `minimumSufficientEvidenceSets`/trap
 * reference an unreachable id (`EvidenceCandidate.passageId` is the
 * underlying passage's own id, never a context id -- a passage that
 * expands into multiple contexts, e.g. its `EARLIER` and `LATER`
 * comparison-side interpretations, has one passage id shared across
 * several distinct context ids). Caught by a real 0% minimum-sufficient-
 * set-recovery rate across every case on the first live evaluation run --
 * every affected context id was re-resolved to its real passage id via
 * `SELECT id, passage_id FROM app.current_retrieval_contexts WHERE id IN
 * (...)` before any metric was reported. A few cases' two "alternate"
 * evidence sets collapsed to the same passage id as a result (both
 * comparison sides of one repeated passage) -- left as harmless literal
 * duplication rather than restructured, since it doesn't change recovery
 * semantics.
 */

export type QaAnswerabilityClass = "SUPPORTED" | "PARTIALLY_SUPPORTED" | "INSUFFICIENT_EVIDENCE" | "AMBIGUOUS_OR_CONFLICTING";

export interface QaEvaluationCase {
  id: string;
  question: string;
  /** Which of the milestone's required case types this exercises -- not a
   * pipeline input, purely for reporting metrics by group. */
  caseType: string;
  expectedAnswerability: QaAnswerabilityClass;
  companyTicker?: string;
  /** One or more alternate sets of passage ids, any one of which fully
   * counts as "the minimum sufficient evidence was recovered." Empty for
   * INSUFFICIENT_EVIDENCE cases (nothing should be selected as sufficient). */
  minimumSufficientEvidenceSets: string[][];
  /** Corroborating but not required -- selecting these is fine, but they
   * don't count toward minimum-sufficient-set recovery on their own. */
  acceptableAdditionalPassageIds?: string[];
  /** Plausible-looking passages that must NOT be treated as sufficient
   * evidence for this specific question (wrong company/topic/scope). */
  unsupportedTrapPassageIds?: string[];
  /** Real, verified bare numeric/table fragments that should not, alone,
   * satisfy the gate. */
  numericFragmentTrapPassageIds?: string[];
  /** Real, verified single/near-single-word heading fragments that should
   * not, alone, satisfy the gate. */
  shortHeadingTrapPassageIds?: string[];
  /** At least one of these is expected to appear in the gate's reasonCodes
   * when expectedAnswerability !== "SUPPORTED". */
  expectedGateReasonCodes?: GateReasonCode[];
  expectedRequiredScope?: { ticker?: string; periodStart?: string; periodEnd?: string; reportSide?: ReportSide };
  /** Human judgment rationale -- why this is graded the way it is, and
   * (for no-answer cases) how absence was verified. */
  notes: string;
}

export const QA_EVALUATION_DATASET: QaEvaluationCase[] = [
  // ---------------------------------------------------------------------
  // SUPPORTED -- directly answerable by one passage, one company/category
  // each. All passage ids below were read via:
  //   SELECT c.ticker, rc.id, rc.heading, rc.report_side, rc.alignment_status,
  //          cat.category, p.word_count, p.text
  //   FROM app.current_retrieval_contexts rc
  //   JOIN app.current_companies c ON c.id = rc.company_id
  //   JOIN app.current_passages p ON p.id = rc.passage_id
  //   JOIN app.current_retrieval_context_language_categories cat
  //     ON cat.retrieval_context_id = rc.id
  //   WHERE p.word_count >= 20 AND rc.primary_narrative_eligible = true
  //     AND cat.category IN ('risk','financial_condition','governance','strategy')
  //   ORDER BY c.ticker, cat.category, p.word_count DESC;
  // (real query, real corpus, Milestone 7B.1b pre-coding investigation).
  // ---------------------------------------------------------------------
  {
    id: "sup-act-financial-growth",
    question: "What growth opportunities has ACT identified in its healthcare administration business?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["688cd61c-5d1a-5748-88c7-7659ef214b93"], ["688cd61c-5d1a-5748-88c7-7659ef214b93"]],
    expectedRequiredScope: { ticker: "ACT" },
    notes:
      'Real passage (LATER side, NEW/LIGHTLY_MODIFIED counterparts) headed "MAXIMISE GROWTH OPPORTUNITIES", discussing the Bonitas/LMS Medical Fund amalgamation and POLMED contract -- directly answers the question. Either side alone is sufficient.',
  },
  {
    id: "sup-act-governance-board-meetings",
    question: "How often did ACT's board meet during the year and what access do non-executive directors have to management?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["d128c408-9100-5150-8615-eb8fed857010"]],
    expectedRequiredScope: { ticker: "ACT" },
    notes: 'Real "Board meetings" passage: four scheduled meetings plus AGM/strategy session; non-executive directors have unfettered access to senior executives.',
  },
  {
    id: "sup-act-risk-labour-standards",
    question: "What did ACT disclose about labour standards, including diversity and pay equality?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["f8ff34f3-e750-5913-abea-5803cd2788c9"], ["f8ff34f3-e750-5913-abea-5803cd2788c9"]],
    expectedRequiredScope: { ticker: "ACT" },
    notes: 'Real "Labour standards" passage discussing diversity/inclusion, pay equality and wage-level determination in progress.',
  },
  {
    id: "sup-bel-financial-repurchase",
    question: "What must Bell Equipment confirm about working capital before a general share repurchase?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "BEL",
    minimumSufficientEvidenceSets: [["8e1d3ea3-b95b-5ad0-a298-4ef4f32b0241"], ["8e1d3ea3-b95b-5ad0-a298-4ef4f32b0241"]],
    expectedRequiredScope: { ticker: "BEL" },
    notes: "Real passage on share capital/reserves and working capital adequacy conditions for a general repurchase.",
  },
  {
    id: "sup-bel-governance-board-charter",
    question: "What governs the scope of authority and composition of Bell Equipment's board?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "BEL",
    minimumSufficientEvidenceSets: [["444943af-7bb7-5c9a-857c-a40fb54b5dae"]],
    expectedRequiredScope: { ticker: "BEL" },
    notes: 'Real "Board charter" passage: scope of authority/responsibility/composition contained in a formal charter, reviewed annually.',
  },
  {
    id: "sup-bel-risk-credit-guarantee",
    question: "What credit risk does Bell Equipment carry through WesBank financing guarantees?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "BEL",
    minimumSufficientEvidenceSets: [["ca3bf939-ebca-51e2-ab94-6750fac9f135"], ["ca3bf939-ebca-51e2-ab94-6750fac9f135"]],
    expectedRequiredScope: { ticker: "BEL" },
    notes: "Real contingent-liabilities passage on WesBank credit-risk financial guarantee contracts for customer equipment financing.",
  },
  {
    id: "sup-kp2-governance-hse-committee",
    question: "Why did Kore Potash not hold separate Health, Safety and Environment committee meetings?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["e7231e0f-37d5-589f-8f8c-5a004e526fa4"], ["e7231e0f-37d5-589f-8f8c-5a004e526fa4"]],
    expectedRequiredScope: { ticker: "KP2" },
    notes: "Real passage: limited operational activity during feasibility-study phases created a low-risk environment, so no separate HSE committee meetings were held.",
  },
  {
    id: "sup-kp2-financial-loss",
    question: "What loss did Kore Potash incur and what were its net cash outflows for the year?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["699d81dd-8c7d-59ae-9708-21e255cdccfb"]],
    expectedRequiredScope: { ticker: "KP2" },
    notes: "Real passage stating a USD 3,144,172 loss (prior year USD 4,202,752) and net cash outflows of USD 9,277,027 from operating/investing activities.",
  },
  {
    id: "sup-kp2-strategy-disclosure-obligations",
    question: "What parallel market-disclosure obligations does Kore Potash operate under?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["477cc143-1c8a-5264-abc2-2894fc66a97d"], ["866788f8-cc91-5bb6-8dd9-6e4011202b0e"], ["477cc143-1c8a-5264-abc2-2894fc66a97d"]],
    expectedRequiredScope: { ticker: "KP2" },
    notes: "Real corporate-governance passage: subject to parallel obligations under the AIM Rules and Market Abuse Regulation, plus ASX Listing Rules.",
  },
  {
    id: "sup-sbp-governance-remuneration-policy",
    question: "What principles does Sabvest Capital apply to its remuneration policy?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [["f3d98e55-2f34-572b-b8c7-220c4311add4"]],
    expectedRequiredScope: { ticker: "SBP" },
    notes: 'Real "11.2 Remuneration philosophy and policy" passage: approved by Remuneration Committee and Board, no differential compensation basis stated.',
  },
  {
    id: "sup-sbp-strategy-investment-proposition",
    question: "What unlisted investment access does Sabvest Capital offer investors?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [["e94d0c0b-cc95-5546-90f5-24503eed5e91"], ["e94d0c0b-cc95-5546-90f5-24503eed5e91"]],
    expectedRequiredScope: { ticker: "SBP" },
    notes: 'Real "2.3 Investment proposition" passage listing thirteen unlisted groups (Amicus, Altify, Apex Partners, ARB Holdings, etc.).',
  },
  {
    id: "sup-sdl-financial-fair-value",
    question: "How does Southern Palladium estimate the fair value of its financial assets and liabilities?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["80551cc4-b7bf-52cd-8d55-8235273a2714"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: '"d) Fair value estimation" passage: nominal value less estimated credit adjustments used for recognition/measurement/disclosure purposes.',
  },
  {
    id: "sup-sdl-governance-key-management",
    question: "Who were Southern Palladium's key management personnel and directors during the year?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["83a8694d-7a25-50a8-b2da-1733ea4dbb6a"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: '"b) Key management personnel" passage naming the non-executive chairman and managing director with appointment dates.',
  },
  {
    id: "sup-sdl-strategy-sovereign-risk",
    question: "How does Southern Palladium mitigate sovereign risk in South Africa?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["02b401a2-bca1-5c12-8705-ccedd141a895"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: '"Sovereign risk" passage: strong partnership with local community members and a productive relationship as mitigation.',
  },
  {
    id: "sup-sur-financial-target-setting",
    question: "What is Spur's approach to setting short-term incentive targets given sensitivity around budgets?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SUR",
    minimumSufficientEvidenceSets: [["53eaa2e3-e3a5-5e35-8de2-34661615d7a2"]],
    expectedRequiredScope: { ticker: "SUR" },
    notes: '"Target-setting process for 2026 STI" passage: commercially sensitive budgets, so an overview of the target-setting rationale is disclosed instead.',
  },
  {
    id: "sup-sur-risk-stakeholder-governance",
    question: "How does Spur's governance framework align with King IV principles across stakeholder groups?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SUR",
    minimumSufficientEvidenceSets: [["0e3839b8-cf5c-5c40-bce9-fd3732cec4e2"]],
    expectedRequiredScope: { ticker: "SUR" },
    notes: '"OUR STAKEHOLDER" passage: governance framework aligns with King IV, ensuring ethical leadership/accountability/oversight across employee/customer/investor/franchisee experience.',
  },
  {
    id: "sup-sur-strategy-loadshedding",
    question: "How has electricity loadshedding affected Spur's ongoing reinvention strategy?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SUR",
    minimumSufficientEvidenceSets: [["d69e2966-1cea-59a3-a259-9c593f2e86f9"]],
    expectedRequiredScope: { ticker: "SUR" },
    notes: '"ONGOING REINVENTION" passage: loadshedding continued to worsen, negatively affecting consumer confidence per PwC\'s Global Consumer Insights Survey.',
  },

  // ---------------------------------------------------------------------
  // SUPPORTED -- multi-passage / chronology / report-side-specific
  // ---------------------------------------------------------------------
  {
    id: "sup-multi-act-growth-both-sides",
    question: "How did ACT describe its growth-opportunity strategy across its two most recent reports?",
    caseType: "answerable_only_by_multiple_passages",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["688cd61c-5d1a-5748-88c7-7659ef214b93", "688cd61c-5d1a-5748-88c7-7659ef214b93"]],
    expectedRequiredScope: { ticker: "ACT" },
    notes: "Both EARLIER and LATER sides carry the same real growth-opportunity content (Bonitas/LMS/POLMED) -- a chronology question naturally wants both sides, not just one.",
  },
  {
    id: "sup-earlier-side-act-labour",
    question: "What did ACT's earlier report say about labour standards?",
    caseType: "answerable_only_from_earlier_side",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["f8ff34f3-e750-5913-abea-5803cd2788c9"]],
    expectedRequiredScope: { ticker: "ACT", reportSide: "EARLIER" },
    notes: "Real EARLIER-side labour-standards passage exists distinctly from the LATER-side counterpart -- side-specific scope must be honored.",
  },
  {
    id: "sup-later-side-kp2-hse",
    question: "What does Kore Potash's most recent report say about Health, Safety and Environment committee meetings?",
    caseType: "answerable_only_from_later_side",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["e7231e0f-37d5-589f-8f8c-5a004e526fa4"]],
    expectedRequiredScope: { ticker: "KP2", reportSide: "LATER" },
    notes: "Real LATER-side HSE-committee passage, distinct context id from the EARLIER-side counterpart.",
  },
  {
    id: "sup-new-sdl-directors-report",
    question: "What newly introduced content appeared in Southern Palladium's directors' report?",
    caseType: "answerable_from_new_disclosure",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["300b005e-d11c-5907-b85b-8044e39c4382"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: 'Real passage with alignment_status=NEW under heading "DIRECTORS REPORT".',
  },
  {
    id: "sup-removed-act-leadership-bio",
    question: "What biography for Grace Khoza was removed from ACT's leadership section?",
    caseType: "answerable_from_removed_disclosure",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["e7a3b82a-8f51-596b-8a28-68535c39c54b"], ["e7a3b82a-8f51-596b-8a28-68535c39c54b"]],
    expectedRequiredScope: { ticker: "ACT" },
    notes: 'Real alignment_status=REMOVED passage ("Our Leadership 6. Grace Khoza...") -- a genuinely removed director biography.',
  },
  {
    id: "sup-modified-bel-agm-notice",
    question: "What changed in Bell Equipment's notice of annual general meeting regarding share placement authority?",
    caseType: "answerable_from_modified_disclosure",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "BEL",
    minimumSufficientEvidenceSets: [["2e51fd22-bb9b-5b68-b286-d69b6740ecc5"]],
    expectedRequiredScope: { ticker: "BEL" },
    notes: "Real alignment_status=LIGHTLY_MODIFIED passage on director authorization to allot/issue unissued shares.",
  },
  {
    id: "sup-period-kp2-2024",
    question: "What did Kore Potash disclose about its 2024 governance committee meeting activity?",
    caseType: "answerable_only_within_one_report_period",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["e7231e0f-37d5-589f-8f8c-5a004e526fa4"]],
    expectedRequiredScope: { ticker: "KP2", periodStart: "2024-01-01", periodEnd: "2024-12-31" },
    notes: "KP2's latest report period end is 2024-12-31 (verified via corpus period range query) -- the LATER-side passage is the one within that period.",
  },

  // ---------------------------------------------------------------------
  // PARTIALLY_SUPPORTED
  // ---------------------------------------------------------------------
  {
    id: "partial-sbp-remuneration-and-succession",
    question: "What is Sabvest Capital's remuneration philosophy and how does it handle executive succession planning?",
    caseType: "partially_answerable",
    expectedAnswerability: "PARTIALLY_SUPPORTED",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [["f3d98e55-2f34-572b-b8c7-220c4311add4"]],
    expectedGateReasonCodes: ["INSUFFICIENT_TOPIC_COVERAGE"],
    notes: "Remuneration philosophy is real and answerable (same passage as sup-sbp-governance-remuneration-policy); no succession-planning passage was found for SBP in this inspection -- the question's second half is unsupported.",
  },
  {
    id: "partial-bel-repurchase-and-buyback-pricing",
    question: "What conditions govern Bell Equipment's share repurchases, and at what specific price ceiling are repurchases permitted?",
    caseType: "partially_answerable",
    expectedAnswerability: "PARTIALLY_SUPPORTED",
    companyTicker: "BEL",
    minimumSufficientEvidenceSets: [["8e1d3ea3-b95b-5ad0-a298-4ef4f32b0241"]],
    expectedGateReasonCodes: ["INSUFFICIENT_TOPIC_COVERAGE"],
    notes: "Working-capital/reserves adequacy conditions are covered; the specific price-ceiling mechanics (a distinct, more detailed sub-topic) were not separately verified in this inspection.",
  },
  {
    id: "partial-kp2-materiality-and-fraud-risk",
    question: "How does Kore Potash's auditor apply materiality, and what specific fraud-risk indicators were identified?",
    caseType: "partially_answerable",
    expectedAnswerability: "PARTIALLY_SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["02c3244d-fd2d-535c-8f7d-dce9ec706429"]],
    expectedGateReasonCodes: ["INSUFFICIENT_TOPIC_COVERAGE"],
    notes: "Component materiality methodology is real and covered; specific fraud-risk indicators are a distinct sub-topic not verified as separately disclosed in this passage.",
  },
  {
    id: "partial-act-diversity-and-gender-pay-gap",
    question: "What diversity commitments has ACT made, and what is the exact gender pay gap figure?",
    caseType: "partially_answerable",
    expectedAnswerability: "PARTIALLY_SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["f8ff34f3-e750-5913-abea-5803cd2788c9"]],
    expectedGateReasonCodes: ["INSUFFICIENT_TOPIC_COVERAGE"],
    notes: "The labour-standards passage explicitly states pay equality/wage-level determination is still in progress (not yet reported) -- the diversity half is supported, the exact-figure half is explicitly not yet available.",
  },

  // ---------------------------------------------------------------------
  // AMBIGUOUS_OR_CONFLICTING
  // ---------------------------------------------------------------------
  {
    id: "ambiguous-sbp-restatement",
    question: "Did Sabvest Capital's subsidiaries satisfy IFRS 10 investment-entity consolidation requirements?",
    caseType: "conflicting_or_apparently_inconsistent",
    expectedAnswerability: "AMBIGUOUS_OR_CONFLICTING",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [],
    unsupportedTrapPassageIds: ["57db39f3-b2e9-5e48-919d-82a84a3ebe20"],
    expectedGateReasonCodes: ["CONFLICTING_EVIDENCE"],
    notes:
      'Real "6.2 Restatement" passage: management reassessed investment-entity status and concluded subsidiaries were *incorrectly* consolidated in the prior period under IFRS 10 -- the passage itself documents a correction of an earlier inconsistent position, exactly the kind of apparent self-contradiction the gate should flag rather than present as a clean single answer.',
  },
  {
    id: "ambiguous-sdl-directors-report-new-removed",
    question: "What does Southern Palladium's directors' report say, and has it changed between reports?",
    caseType: "conflicting_or_apparently_inconsistent",
    expectedAnswerability: "AMBIGUOUS_OR_CONFLICTING",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [],
    unsupportedTrapPassageIds: ["300b005e-d11c-5907-b85b-8044e39c4382", "cbb880e9-28ef-543b-86bd-3cb2337328b9"],
    expectedGateReasonCodes: ["CONFLICTING_EVIDENCE"],
    notes:
      'Real corpus finding: a "DIRECTORS REPORT" passage exists with alignment_status=NEW (300b005e...) and a same-heading passage with alignment_status=REMOVED (cbb880e9...) for the same company, with no verified explanatory link between them -- mixed NEW+REMOVED evidence without explanation, exactly the coherence check this milestone requires.',
  },
  {
    id: "ambiguous-sbp-listed-investment-performance",
    question: "How did Sabvest Capital's listed investments perform?",
    caseType: "ambiguous",
    expectedAnswerability: "AMBIGUOUS_OR_CONFLICTING",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [],
    unsupportedTrapPassageIds: ["8efd7e8e-ac28-54f1-9b14-564fcb53f143"],
    expectedGateReasonCodes: ["CONFLICTING_EVIDENCE", "INSUFFICIENT_TOPIC_COVERAGE"],
    notes:
      'Real passage "6.12 Performance of listed investments" has alignment_status=AMBIGUOUS -- the alignment pipeline could not confidently classify how this passage relates across report versions, so its content should not be presented as a settled, coherent answer.',
  },
  {
    id: "ambiguous-sbp-non-executive-directors",
    question: "Who are Sabvest Capital's non-executive directors?",
    caseType: "ambiguous",
    expectedAnswerability: "AMBIGUOUS_OR_CONFLICTING",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [],
    unsupportedTrapPassageIds: ["621c9af8-bc94-5e3b-9951-02614e9a4975"],
    expectedGateReasonCodes: ["CONFLICTING_EVIDENCE", "INSUFFICIENT_TOPIC_COVERAGE"],
    notes:
      'Real "Non-executive directors" passage has alignment_status=AMBIGUOUS -- board composition is a topic where an unresolved alignment classification is a genuine risk of presenting stale or superseded director information as current.',
  },
  {
    id: "ambiguous-sbp-valuation-summary",
    question: "What was Sabvest Capital's unlisted-investment valuation for 2022 versus 2023?",
    caseType: "conflicting_or_apparently_inconsistent",
    expectedAnswerability: "AMBIGUOUS_OR_CONFLICTING",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [],
    unsupportedTrapPassageIds: ["68248b1b-0ae4-53ae-943b-4a329d833b1c"],
    expectedGateReasonCodes: ["CONFLICTING_EVIDENCE", "INSUFFICIENT_TOPIC_COVERAGE"],
    notes: 'Real passage with alignment_status=AMBIGUOUS headed "Valuation summary: 2023 2022" -- the alignment pipeline itself could not confidently classify this passage, a genuine corpus-level ambiguity signal.',
  },

  // ---------------------------------------------------------------------
  // INSUFFICIENT_EVIDENCE -- no answer in corpus. Reuses the same
  // genuinely-verified-absent topics from the Milestone 7B.1a retrieval
  // evaluation dataset (same corpus, unchanged since) -- absence was
  // verified there by direct corpus inspection, not by this pipeline's own
  // retrieval output.
  // ---------------------------------------------------------------------
  {
    id: "noanswer-airline-loyalty",
    question: "What does the company disclose about its airline loyalty rewards partnership?",
    caseType: "no_answer_in_corpus",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE", "ONLY_WEAK_INDIRECT_EVIDENCE"],
    notes: "None of the 6 companies (a healthcare group, an equipment manufacturer, a mining explorer, an investment holding company, a mining explorer, and a restaurant franchisor) operate an airline loyalty program -- verified absent in the 7B.1a dataset and unchanged.",
  },
  {
    id: "noanswer-esports",
    question: "What esports sponsorship deals has the company entered into?",
    caseType: "no_answer_in_corpus",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE", "ONLY_WEAK_INDIRECT_EVIDENCE"],
    notes: "No esports-related content in this corpus.",
  },
  {
    id: "noanswer-agriculture-subsidy",
    question: "What agricultural subsidy programs does the company benefit from?",
    caseType: "no_answer_in_corpus",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE", "ONLY_WEAK_INDIRECT_EVIDENCE"],
    notes: "No agricultural-subsidy content -- none of the 6 companies operate in agriculture.",
  },
  {
    id: "noanswer-deep-sea-mining",
    question: "What deep-sea mining exploration activity has the company undertaken?",
    caseType: "no_answer_in_corpus",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE", "ONLY_WEAK_INDIRECT_EVIDENCE"],
    notes: "The two mining explorers (KP2 potash, SDL palladium) operate on land, not deep-sea -- verified absent.",
  },
  {
    id: "noanswer-social-media-influencer",
    question: "What social media influencer marketing campaigns has the company run?",
    caseType: "no_answer_in_corpus",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE", "ONLY_WEAK_INDIRECT_EVIDENCE"],
    notes: "No influencer-marketing content verified in the corpus.",
  },
  {
    id: "noanswer-patent-litigation",
    question: "What patent infringement litigation is the company currently defending?",
    caseType: "no_answer_in_corpus",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE", "ONLY_WEAK_INDIRECT_EVIDENCE"],
    notes: "No patent-litigation content verified.",
  },
  {
    id: "noanswer-nonexistent-company",
    question: "What did Acme Global Holdings disclose about its risk exposure?",
    caseType: "no_answer_in_corpus",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE"],
    notes: "\"Acme Global Holdings\" is not one of the 6 real companies in this corpus -- a nonexistent-company question.",
  },
  {
    id: "noanswer-unsupported-acquisition",
    question: "What details did the company disclose about its acquisition of a competing national retail chain?",
    caseType: "no_answer_in_corpus",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE", "ONLY_WEAK_INDIRECT_EVIDENCE"],
    notes: "No verified acquisition of a national retail chain by any of the 6 companies in this corpus.",
  },
  {
    id: "noanswer-nonexistent-regulatory-event",
    question: "How did the company respond to the 2024 Global Carbon Trading Directive?",
    caseType: "no_answer_in_corpus",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE"],
    notes: "\"2024 Global Carbon Trading Directive\" is a fabricated regulatory event with no real-world or corpus basis.",
  },
  {
    id: "noanswer-unsupported-numeric-claim",
    question: "Why did the company report exactly 47.3% growth in cryptocurrency-denominated assets?",
    caseType: "unsupported_exact_numeric_claim",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE"],
    notes: "No cryptocurrency-denominated-asset content exists in this corpus -- an unsupported, fabricated exact numeric claim.",
  },

  // ---------------------------------------------------------------------
  // Numeric-fragment traps -- real, verified bare numeric/table passages
  // that must not, alone, satisfy the gate.
  // ---------------------------------------------------------------------
  {
    id: "numeric-trap-act-operating-margin",
    question: "What was ACT's operating margin and what drove the change?",
    caseType: "numerical_table_fragment_without_explanatory_prose",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [],
    numericFragmentTrapPassageIds: ["a8730771-a5f9-523d-8252-d20fd3d5b77a", "f23fb083-846a-5cf4-85e3-0854843cddce", "15f47fb0-d528-5943-bbcc-a514b80a57ab"],
    expectedGateReasonCodes: ["NUMERIC_FRAGMENT_WITHOUT_CONTEXT"],
    notes:
      'Real corpus passages: "Operating margin" heading paired with bare figures like "(0.9%) (0.2%) (13.9%)", "-1.6%", "-9%" -- no explanatory prose about *why* the margin changed. The question asks for a driver/reason, which these bare figures cannot support alone.',
  },
  {
    id: "numeric-trap-sbp-investments-per-category",
    question: "How has Sabvest Capital's investment portfolio composition changed by category?",
    caseType: "numerical_table_fragment_without_explanatory_prose",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [],
    numericFragmentTrapPassageIds: ["97d62691-d676-5de1-a201-53c7f92a6026", "c595f63b-3d8e-5e9b-9153-0715947f3d05"],
    expectedGateReasonCodes: ["NUMERIC_FRAGMENT_WITHOUT_CONTEXT"],
    notes:
      'Real corpus finding: "Investments per category at 31 December (R\'000)" is a bare table-header fragment (7 words, no explanatory prose about what changed or why) -- a real passage, but not itself sufficient to answer a question about composition change.',
  },
  {
    id: "numeric-trap-short-heading-operations",
    question: "What is disclosed about ongoing healthcare operations?",
    caseType: "short_heading_trap",
    expectedAnswerability: "PARTIALLY_SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["003006b0-5d3e-51ba-99a1-702112625371"]],
    shortHeadingTrapPassageIds: ["505894d7-7db1-5487-a09a-8749f4ef6577"],
    expectedGateReasonCodes: ["LOW_RELEVANCE_MARGIN", "INSUFFICIENT_TOPIC_COVERAGE"],
    notes:
      'The real 2-word passage "Operations (continued)" (verified in the Milestone 7B.1a report as a genuine segmentation artifact, heading with no attached body) must not be selected as sufficient evidence; the real substantive "HEALTHCARE ADMINISTRATION" passage is the legitimate answer.',
  },
  {
    id: "short-heading-trap-usd-currency",
    question: "What currency does Kore Potash report its financial results in?",
    caseType: "short_heading_trap",
    expectedAnswerability: "PARTIALLY_SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["9dd921c5-fd16-565c-82c6-eed67f67bad0"]],
    shortHeadingTrapPassageIds: ["24e91fc9-437c-5859-966b-798b28147c7d", "681b4a5f-8161-55ee-8b63-771e7e1a1f98"],
    expectedGateReasonCodes: ["LOW_RELEVANCE_MARGIN"],
    notes: 'Real single-word "USD" heading fragments (verified in the 7B.1a report) are a real currency signal but not, alone, a substantive answer to how/why USD is used -- the financial-liabilities passage provides real context.',
  },
  {
    id: "short-heading-trap-back-navigation",
    question: "What operational overview information does Spur provide?",
    caseType: "short_heading_trap",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    companyTicker: "SUR",
    minimumSufficientEvidenceSets: [],
    shortHeadingTrapPassageIds: ["915a07f1-7880-5eb1-8150-a993170ca056"],
    expectedGateReasonCodes: ["ONLY_WEAK_INDIRECT_EVIDENCE", "NO_DIRECT_EVIDENCE"],
    notes: 'Real single-word "BACK" heading (verified in the 7B.1a report as a running-header/navigation-link artifact, 80+ corpus-wide repeats of similar labels) carries no substantive content on its own.',
  },

  // ---------------------------------------------------------------------
  // Broad / corpus-wide / multi-company / weak-indirect / quality-aware /
  // comparison-direction / chronology cases.
  // ---------------------------------------------------------------------
  {
    id: "broad-corpus-governance-practices",
    question: "What governance practices are commonly disclosed across companies in this corpus?",
    caseType: "broad_corpus_wide",
    expectedAnswerability: "SUPPORTED",
    minimumSufficientEvidenceSets: [
      ["d128c408-9100-5150-8615-eb8fed857010"],
      ["444943af-7bb7-5c9a-857c-a40fb54b5dae"],
      ["f3d98e55-2f34-572b-b8c7-220c4311add4"],
    ],
    acceptableAdditionalPassageIds: ["83a8694d-7a25-50a8-b2da-1733ea4dbb6a", "0e3839b8-cf5c-5c40-bce9-fd3732cec4e2"],
    notes: "A deliberately unscoped (no ticker) question -- any real governance passage from any company legitimately answers it; recall/diversity matter more than one specific passage.",
  },
  {
    id: "multi-company-remuneration-comparison",
    question: "How do ACT and Sabvest Capital's remuneration policies compare?",
    caseType: "multi_company",
    expectedAnswerability: "SUPPORTED",
    minimumSufficientEvidenceSets: [["d128c408-9100-5150-8615-eb8fed857010", "f3d98e55-2f34-572b-b8c7-220c4311add4"]],
    notes: "Explicitly names two companies (ACT, SBP) -- the required-scope check should not force a single ticker; both companies' governance passages are legitimately relevant.",
  },
  {
    id: "weak-indirect-sbp-industrial-diversification",
    question: "What is Sabvest Capital's exposure to heavy industrial manufacturing risk?",
    caseType: "weak_indirect_evidence",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [],
    unsupportedTrapPassageIds: ["aa26105b-ba80-5a50-815b-1b259ad0f3df"],
    expectedGateReasonCodes: ["ONLY_WEAK_INDIRECT_EVIDENCE", "NO_DIRECT_EVIDENCE"],
    notes: 'A real passage mentions "SA BIAS INDUSTRIES", an industrial group among Sabvest\'s unlisted investments, but that passage discusses investment performance, not manufacturing risk exposure specifically -- related terminology, no direct support for the actual question asked.',
  },
  {
    id: "related-terminology-no-support-kp2-community",
    question: "What community consultation process did Kore Potash follow before beginning drilling operations?",
    caseType: "related_terminology_no_direct_support",
    expectedAnswerability: "INSUFFICIENT_EVIDENCE",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [],
    expectedGateReasonCodes: ["NO_DIRECT_EVIDENCE", "ONLY_WEAK_INDIRECT_EVIDENCE"],
    notes: "KP2 discusses feasibility-study-phase HSE governance, but no specific community-consultation-before-drilling process was verified in this inspection -- related domain, no direct support.",
  },
  {
    id: "quality-aware-act-remuneration-short",
    question: "What does ACT's remuneration model balance?",
    caseType: "requires_quality_aware_interpretation",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["688cd61c-5d1a-5748-88c7-7659ef214b93"]],
    numericFragmentTrapPassageIds: ["f23fb083-846a-5cf4-85e3-0854843cddce"],
    expectedGateReasonCodes: ["SUPPORTED_BY_SINGLE_PASSAGE"],
    notes:
      "A shorter, substantive passage should outrank a longer but low-substance numeric fragment purely on cosine similarity -- requires the quality-aware reranker's demotion of table-like content, not raw similarity ranking alone.",
  },
  {
    id: "direction-lexical-act-growth-increase",
    question: "Did ACT's healthcare administration client base increase between reports?",
    caseType: "requires_comparison_direction",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "ACT",
    minimumSufficientEvidenceSets: [["688cd61c-5d1a-5748-88c7-7659ef214b93"], ["688cd61c-5d1a-5748-88c7-7659ef214b93"]],
    expectedRequiredScope: { ticker: "ACT" },
    notes:
      '"Increase" is lexical comparison language with no stored ground-truth direction signal in the schema (verified: no comparison-direction field exists anywhere) -- the real passage narrates 3.6 million lives reached after the Bonitas/LMS amalgamation, which the system can surface as evidence, but any claimed "direction" must be labeled directionConfidence=LEXICAL_ONLY, never asserted as verified.',
  },
  {
    id: "direction-lexical-bel-repurchase-removed",
    question: "Were any share repurchase authorizations removed from Bell Equipment's disclosures?",
    caseType: "requires_comparison_direction",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "BEL",
    minimumSufficientEvidenceSets: [["2e51fd22-bb9b-5b68-b286-d69b6740ecc5"]],
    expectedRequiredScope: { ticker: "BEL" },
    notes: '"Removed" comparison language maps to alignment-status filtering (a well-supported signal, unlike numeric increase/decrease) -- distinguishes reliable alignment-status-based direction from unverifiable numeric-value direction.',
  },
  {
    id: "chronology-kp2-hse-governance-timeline",
    question: "How has Kore Potash's approach to Health, Safety and Environment governance evolved over time?",
    caseType: "requires_chronology",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["e7231e0f-37d5-589f-8f8c-5a004e526fa4", "e7231e0f-37d5-589f-8f8c-5a004e526fa4"]],
    expectedRequiredScope: { ticker: "KP2" },
    notes: "A chronology question naturally requires both the EARLIER and LATER report-side passages (real, both present) rather than a single side.",
  },
  // ---------------------------------------------------------------------
  // Additional SUPPORTED cases -- remaining real, verified passages from
  // the same top-3-per-ticker/category query, rounding out coverage across
  // companies/categories not yet used above.
  // ---------------------------------------------------------------------
  {
    id: "sup-sbp-financial-incentives",
    question: "How are Sabvest Capital's executive directors' qualitative incentives structured?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [["a61b9075-4e1d-52e4-b729-956f33d416a7"], ["a61b9075-4e1d-52e4-b729-956f33d416a7"]],
    expectedRequiredScope: { ticker: "SBP" },
    notes: "Real passage: executive directors (other than CEO) may receive qualitative incentives up to 25% of CTC, based on pre-set KPIs at CEO/Remcom discretion.",
  },
  {
    id: "sup-sbp-governance-special-incentives",
    question: "Were any special incentives or bonuses paid to Sabvest Capital staff during the period?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [["09852a22-dac2-55d2-b62e-ab6dfefa389e"]],
    expectedRequiredScope: { ticker: "SBP" },
    notes: "Real passage: no special incentives or bonuses paid other than the one referred to above; LTIP awards were formula-based on NAV-per-share growth over four years.",
  },
  {
    id: "sup-sbp-shareholder-inclusive-approach",
    question: "What stakeholder-inclusive approach does Sabvest Capital's governing body follow?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SBP",
    minimumSufficientEvidenceSets: [["5c2bfa94-6fca-5cac-8564-0a43b2a793b4"]],
    expectedRequiredScope: { ticker: "SBP" },
    notes: '"Principle 16" passage: the governing body should adopt a shareholder-inclusive approach balancing material stakeholders\' needs/interests/expectations.',
  },
  {
    id: "sup-sdl-financial-environmental-stewardship",
    question: "How does Southern Palladium approach environmental stewardship in mine development?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["837d6679-703e-573c-b220-d37422d33ed8"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: '"Environmental Responsibility and Stewardship" passage: environmental-stewardship principles entrenched throughout mine development and production planning.',
  },
  {
    id: "sup-sdl-financial-directors-report-governance",
    question: "What accountability foundations does Southern Palladium's directors' report describe?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["85b8f3ef-d5eb-568b-9dae-43e327b9e981"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: '"DIRECTORS REPORT" passage: governance foundations promoting accountability/collaboration adopted throughout operations, achieved via vigilant planning.',
  },
  {
    id: "sup-sdl-governance-new-director-bio",
    question: "What mining engineering qualifications does Southern Palladium's newly appointed non-executive director hold?",
    caseType: "answerable_from_new_disclosure",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["50bc341c-b3c8-5cfb-9c78-b89063adc759"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: "Real NEW-status passage: Daniel Van Heerden, non-independent non-executive director, holds an M.Com, B.Eng Mining Engineering, and a Government Mining Engineer competence certificate.",
  },
  {
    id: "sup-sdl-governance-no-significant-changes",
    question: "Were there any significant changes to Southern Palladium's state of affairs after the reporting date?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["d12e620d-18bd-54c4-bc47-2eb9ff948d3d"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: '"SIGNIFICANT CHANGES IN STATE OF AFFAIRS" passage: no other significant changes occurred; no matters arose since reporting-period end.',
  },
  {
    id: "sup-sdl-risk-currency-sensitivity",
    question: "How sensitive is Southern Palladium's profit or loss to AUD/ZAR exchange-rate movements?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["cc3d6df5-1aef-5bc8-b725-958ddcd39bdb"], ["ecbb4d53-482f-5172-92d5-f46694a3ffd7"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: "Real passage: sensitivity of profit/loss to exchange-rate changes arises mainly from ZAR dollar-denominated instruments, quantified for a 10% AUD/ZAR movement.",
  },
  {
    id: "sup-sdl-strategy-share-based-payments",
    question: "How does Southern Palladium account for share-based payments to directors and employees?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SDL",
    minimumSufficientEvidenceSets: [["02bcfd0d-09e1-54ea-a243-5b4680d781c9"], ["bd3eb51e-33f1-552b-99b2-c704ee244107"]],
    expectedRequiredScope: { ticker: "SDL" },
    notes: '"l) Share-based payments" passage: fair value of shares/options recognised as an expense on a pro-rata basis under AASB 2.',
  },
  {
    id: "sup-sur-financial-remuneration-weightings",
    question: "How are Spur's SAR and bonus award weightings determined for its CEO, CFO and COO?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SUR",
    minimumSufficientEvidenceSets: [["3dd68926-38e3-520a-9cc6-280e5a1f6080"], ["3dd68926-38e3-520a-9cc6-280e5a1f6080"]],
    expectedRequiredScope: { ticker: "SUR" },
    notes: 'Real "Remuneration policy continued 1" passage: SARs/bonus award weightings for CEO/CFO/COO, with a minimum "meets expectations" personal-performance rating required.',
  },
  {
    id: "sup-sur-governance-malus-clawback",
    question: "Does Spur have a malus and clawback policy for its SAR allocations?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SUR",
    minimumSufficientEvidenceSets: [["857d98bd-03d1-5fe7-90f8-bc669e6ece79"]],
    expectedRequiredScope: { ticker: "SUR" },
    notes: '"SAR allocation" passage: the group\'s malus and clawback policy applies to the 2025 financial-year short-term incentive.',
  },
  {
    id: "sup-sur-risk-board-activities-2023",
    question: "What strategy-related activities did Spur's board undertake in 2023?",
    caseType: "answerable_only_within_one_report_period",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SUR",
    minimumSufficientEvidenceSets: [["802d819f-a609-5037-bfbd-95963020b7cd"]],
    expectedRequiredScope: { ticker: "SUR", periodStart: "2023-01-01", periodEnd: "2023-12-31" },
    notes: '"Key board activities in 2023" passage: considered/approved new strategy, regular leadership-team engagement to support implementation.',
  },
  {
    id: "sup-sur-risk-governing-body-inseparable-elements",
    question: "How does Spur's governing body view the relationship between purpose, risk, and strategy?",
    caseType: "answerable_by_one_passage",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "SUR",
    minimumSufficientEvidenceSets: [["d93fa48c-786a-5f0d-9aa7-32c47ea7b5d5"]],
    expectedRequiredScope: { ticker: "SUR" },
    notes: '"Principle Application" passage: the governing body should appreciate that purpose, risks/opportunities, strategy, business model and performance are inseparable elements.',
  },
  {
    id: "partial-sur-target-setting-and-exact-budget",
    question: "What is Spur's target-setting rationale for STI, and what were the exact 2026 budget figures used?",
    caseType: "partially_answerable",
    expectedAnswerability: "PARTIALLY_SUPPORTED",
    companyTicker: "SUR",
    minimumSufficientEvidenceSets: [["53eaa2e3-e3a5-5e35-8de2-34661615d7a2"]],
    expectedGateReasonCodes: ["INSUFFICIENT_TOPIC_COVERAGE"],
    notes: "The passage explicitly states budget figures are commercially sensitive and not disclosed -- the rationale is answerable, the exact-figures half is explicitly unsupported by design, not a retrieval failure.",
  },
  {
    id: "partial-kp2-liability-classification-and-fair-value-hierarchy",
    question: "How does Kore Potash classify financial liabilities, and where do they fall in the IFRS 13 fair-value hierarchy?",
    caseType: "partially_answerable",
    expectedAnswerability: "PARTIALLY_SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["9dd921c5-fd16-565c-82c6-eed67f67bad0"]],
    expectedGateReasonCodes: ["INSUFFICIENT_TOPIC_COVERAGE"],
    notes: "Classification methodology is covered; the specific IFRS 13 fair-value-hierarchy level was not separately verified as disclosed for this passage.",
  },
  {
    id: "repeated-passage-kp2-materiality-audit",
    question: "How does Kore Potash's independent auditor describe its application of materiality?",
    caseType: "repeated_passage_across_comparisons",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["02c3244d-fd2d-535c-8f7d-dce9ec706429"], ["02c3244d-fd2d-535c-8f7d-dce9ec706429"]],
    notes:
      "Real corpus finding: the identical auditor's-report materiality passage is tagged under both 'governance' and 'risk' categories across different retrieval contexts for the same underlying disclosure -- tests that category-driven candidate generation doesn't inflate this into multiple independent sources.",
  },
  {
    id: "repeated-passage-kp2-transitions-both-modification",
    question: "What did Kore Potash's directors report about company registration changes?",
    caseType: "repeated_passage_across_comparisons",
    expectedAnswerability: "PARTIALLY_SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [["02c3244d-fd2d-535c-8f7d-dce9ec706429"]],
    expectedGateReasonCodes: ["INSUFFICIENT_TOPIC_COVERAGE"],
    notes: "The materiality-application passage is real and relevant to the audit context but does not itself discuss company-registration changes -- deliberately included as a partial/weak-match boundary case, not a clean answer.",
  },
  {
    id: "repeated-passage-kp2-financial-liabilities",
    question: "How does Kore Potash classify financial liabilities and equity instruments?",
    caseType: "repeated_passage_across_comparisons",
    expectedAnswerability: "SUPPORTED",
    companyTicker: "KP2",
    minimumSufficientEvidenceSets: [
      ["9dd921c5-fd16-565c-82c6-eed67f67bad0"],
      ["e19bb59d-10fd-5d37-8416-fa27364f54aa"],
      ["e19bb59d-10fd-5d37-8416-fa27364f54aa"],
    ],
    notes:
      "Real corpus finding: the identical financial-liabilities-classification passage appears across three different retrieval contexts (UNCHANGED/UNCHANGED/LIGHTLY_MODIFIED) -- the evidence-set builder's dedup pass should treat these as one underlying disclosure, not three independent corroborating sources.",
  },
];
