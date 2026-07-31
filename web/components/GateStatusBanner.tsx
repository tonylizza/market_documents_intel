import type { GateReasonCode, GateStatus } from "@/lib/domain/qa-evidence";
import styles from "./GateStatusBanner.module.css";

export interface GateStatusBannerProps {
  status: GateStatus;
  reasonCodes: readonly GateReasonCode[];
}

/** Plain-language labels for the four gate outcomes -- the raw enum value
 * is never shown to an ordinary user (mirrors `RetrievalResultCard`'s
 * `EXPLANATION_LABELS` pattern: technical/internal codes stay in developer-
 * facing surfaces only). */
const STATUS_LABELS: Record<GateStatus, string> = {
  SUPPORTED: "Supported by the evidence below",
  PARTIALLY_SUPPORTED: "Only partially supported",
  INSUFFICIENT_EVIDENCE: "Not enough evidence to answer",
  AMBIGUOUS_OR_CONFLICTING: "Evidence is ambiguous or conflicting",
};

const STATUS_TONE: Record<GateStatus, "supported" | "partial" | "insufficient" | "ambiguous"> = {
  SUPPORTED: "supported",
  PARTIALLY_SUPPORTED: "partial",
  INSUFFICIENT_EVIDENCE: "insufficient",
  AMBIGUOUS_OR_CONFLICTING: "ambiguous",
};

/** Plain-language explanation for every reason code -- never the raw code
 * itself (milestone: "Do not expose internal enum names directly to
 * ordinary users"). */
const REASON_LABELS: Record<GateReasonCode, string> = {
  NO_DIRECT_EVIDENCE: "No passage in the corpus directly addresses this question.",
  ONLY_WEAK_INDIRECT_EVIDENCE: "Only weak or indirect matches were found -- nothing strong enough to rely on.",
  REQUIRED_SCOPE_NOT_COVERED: "Nothing was found for the specific company or category the question asked about.",
  MISSING_COMPARISON_SIDE: "Nothing was found for the specific report side (earlier/later) the question asked about.",
  NUMERIC_FRAGMENT_WITHOUT_CONTEXT: "The only matching content is a bare number or table figure with no explanatory text nearby.",
  CONFLICTING_EVIDENCE: "The matching passages disagree with each other or cannot be reconciled.",
  INSUFFICIENT_TOPIC_COVERAGE: "The evidence only covers part of what the question asked.",
  LOW_RELEVANCE_MARGIN: "The best match is only barely above the threshold for a confident answer.",
  CITATION_METADATA_INCOMPLETE: "A citation could not be fully resolved for one of the matching passages.",
  EVIDENCE_REDUNDANT: "Most of the matching passages repeat the same content rather than adding new information.",
  SUPPORTED_BY_SINGLE_PASSAGE: "Supported by a single passage.",
  SUPPORTED_BY_MULTIPLE_PASSAGES: "Supported by multiple independent passages.",
  REQUIRED_CONCEPT_MISSING: "The question named a specific topic that no candidate evidence could be matched against.",
  GENERIC_ONLY_MATCH: "The matching passages are generic prose, not specifically about what was asked.",
  COMPANY_ONLY_MATCH: "Matches are from the right company, but not about the topic asked.",
  SCOPE_ONLY_MATCH: "Matches are in the right scope (company, side, or category), but not about the topic asked.",
  BODY_SUPPORT_MISSING: "The topic only appears in a heading, not in the passage's own text.",
  DIRECT_RESPONSIVENESS_BELOW_FLOOR: "No matching passage was judged specifically responsive to this question.",
  PARTIAL_SUPPORT_NOT_SEPARABLE: "This question doesn't split into separately-checkable parts, so partial support isn't reported.",
  WRONG_TOPIC_RIGHT_COMPANY: "The right company was found, but not evidence about the specific topic asked.",
  RESTATEMENT_AMBIGUITY: "The evidence includes a restated or corrected figure whose chronology isn't clear.",
  CHRONOLOGY_INCOMPLETE: "Only part of the requested time period is covered by the evidence.",
  RESTATEMENT_DETECTED: "The evidence includes a restatement or correction.",
  ORIGINAL_AND_RESTATED_VALUES_PRESENT: "Both an original and a restated value are present in the evidence.",
  SUPERSEDED_EVIDENCE: "One selected passage has been superseded by a later, corrected passage.",
  CORRECTION_CONTEXT_REQUIRED: "Both the original and restated context are needed to answer this question.",
  RESTATEMENT_CHRONOLOGY_CLEAR: "The order of the original and restated values is clear.",
  RESTATEMENT_CHRONOLOGY_AMBIGUOUS: "The order of the original and restated values is not clear.",
  COMPARISON_CONTEXT_MISSING: "Evidence for one side of the requested comparison is missing.",
  REPORT_SIDE_MISMATCH: "The evidence doesn't match the requested report side.",
  DIRECTION_NOT_VERIFIED: "Whether the figure increased or decreased could not be verified from stored data.",
  DATE_RANGE_NOT_COVERED: "No evidence falls within the requested date range.",
  CHRONOLOGY_CONFLICT: "Evidence from different periods conflicts without a clear explanation.",
  COMPARISON_TOPIC_MISMATCH: "The two sides of the comparison are not about the same topic.",
};

export function GateStatusBanner({ status, reasonCodes }: GateStatusBannerProps) {
  const tone = STATUS_TONE[status];
  return (
    <div className={`${styles.banner} ${styles[tone]}`} role="status">
      <p className={styles.statusLabel}>{STATUS_LABELS[status]}</p>
      {reasonCodes.length > 0 && (
        <ul className={styles.reasonList}>
          {reasonCodes.map((code) => (
            <li key={code}>{REASON_LABELS[code]}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
