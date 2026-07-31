"use client";

import { useState } from "react";
import Link from "next/link";
import type { GroupedRetrievalResult, RetrievalContext } from "@/lib/domain/retrieval";
import { HighlightedText } from "@/components/HighlightedText";
import {
  formatAlignmentStatusLabel,
  formatConfidenceLabel,
  formatPassageTypeLabel,
  formatReportSideLabel,
} from "@/lib/config/passage-vocabulary";
import { formatComparisonPeriod, formatPeriodEnd } from "@/lib/formatting/dates";
import { formatCount } from "@/lib/formatting/numbers";
import type { QualityExplanationCode } from "@/lib/services/passage-quality";
import styles from "./RetrievalResultCard.module.css";

export interface RetrievalResultCardProps {
  result: GroupedRetrievalResult;
}

/** Plain-language translation of the reranker's explanation code -- the
 * raw code (e.g. `HEADING_ONLY_FRAGMENT`) is a diagnostics/audit value,
 * never shown verbatim in the UI (milestone: "Do not expose raw internal
 * codes prominently in the UI. Technical details may show plain-language
 * explanations."). `null`/`NO_QUALITY_ADJUSTMENT` renders nothing. */
const EXPLANATION_LABELS: Partial<Record<QualityExplanationCode, string>> = {
  RETAINED_SHORT_FINANCIAL_SENTENCE: "Short passage retained: contains a real financial-language signal",
  LOW_SUBSTANTIVE_TOKEN_COUNT: "Mildly de-emphasized: short passage without a complete sentence",
  HEADING_ONLY_FRAGMENT: "De-emphasized: this passage is only a heading with no body text",
  SHORT_GENERIC_HEADING_PENALTY: "De-emphasized: a short, generic, or repeated section heading",
};

function pageRangeLabel(first: number, last: number): string {
  return first === last ? `Page ${first}` : `Pages ${first}–${last}`;
}

function contextSummary(context: RetrievalContext): string {
  if (context.contextType === "REPORT_ONLY" || !context.reportSide) {
    return formatPeriodEnd(context.reportPeriodEnd) ?? "Period unknown";
  }
  const period =
    context.earlierPeriodEnd && context.laterPeriodEnd
      ? formatComparisonPeriod(context.earlierPeriodEnd, context.laterPeriodEnd)
      : "Comparison";
  return `${period} · ${formatReportSideLabel(context.reportSide)}`;
}

/**
 * One semantic/hybrid `/passages` result. Extends `PassageResultCard`'s
 * shape with retrieval-specific presentation: a weak-match label (never a
 * numeric probability/confidence score shown to the user), a grouped
 * "also appears in" expander for a passage occupying more than one valid
 * comparison context (Option C -- one deduplicated vector, multiple
 * contexts), and a collapsed technical-details panel. Never renders a raw
 * vector or embedding value anywhere.
 */
export function RetrievalResultCard({ result }: RetrievalResultCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { context, additionalContexts, diagnostics } = result;

  return (
    <article className={styles.card} aria-labelledby={`retrieval-heading-${context.contextId}`}>
      <div className={styles.meta}>
        <span className={styles.company}>
          {context.companyName} ({context.companyTicker})
        </span>
        <span aria-hidden="true">·</span>
        <span>{contextSummary(context)}</span>
        <span aria-hidden="true">·</span>
        <span>{pageRangeLabel(context.firstPageNumber, context.lastPageNumber)}</span>
        {diagnostics.strength === "weak" && <span className={styles.weakBadge}>Weak match</span>}
      </div>

      <h3 id={`retrieval-heading-${context.contextId}`} className={styles.heading}>
        {result.headingHighlight ? <HighlightedText spans={result.headingHighlight} /> : (context.heading ?? "(No heading)")}
      </h3>

      <p className={styles.excerpt}>
        <HighlightedText spans={result.excerpt} />
      </p>

      <div className={styles.badges}>
        {context.alignmentStatus && <span className={styles.badge}>{formatAlignmentStatusLabel(context.alignmentStatus)}</span>}
        {context.confidence && <span className={styles.badge}>{formatConfidenceLabel(context.confidence)}</span>}
        <span className={styles.badge}>{formatPassageTypeLabel(context.passageType)}</span>
        {context.contextType === "REPORT_ONLY" && <span className={styles.badge}>No published alignment</span>}
      </div>

      {result.hasAdditionalContexts && (
        <div className={styles.additionalContexts}>
          <button
            type="button"
            className={styles.expanderButton}
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? "Hide" : "Also appears in"} {additionalContexts.length} other comparison
            {additionalContexts.length === 1 ? "" : "s"}
          </button>
          {expanded && (
            <ul className={styles.additionalList}>
              {additionalContexts.map((additional) => (
                <li key={additional.contextId}>
                  <span>{contextSummary(additional)}</span>
                  {additional.alignmentStatus && <span> · {formatAlignmentStatusLabel(additional.alignmentStatus)}</span>}
                  {additional.passageComparisonId && (
                    <Link href={`/passages/${additional.passageComparisonId}`}>View evidence →</Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <details className={styles.technicalDetails}>
        <summary>Technical details</summary>
        <dl>
          <div>
            <dt>Mode</dt>
            <dd>{diagnostics.mode}</dd>
          </div>
          {diagnostics.semanticSimilarity !== null && (
            <div>
              <dt>Semantic similarity (raw)</dt>
              <dd>{diagnostics.semanticSimilarity.toFixed(3)}</dd>
            </div>
          )}
          {diagnostics.adjustedSemanticScore !== null && diagnostics.qualityFactor !== null && diagnostics.qualityFactor < 1 && (
            <div>
              <dt>Adjusted semantic score</dt>
              <dd>{diagnostics.adjustedSemanticScore.toFixed(3)} (retrieval-quality adjustment: {diagnostics.qualityFactor.toFixed(2)}×)</dd>
            </div>
          )}
          {diagnostics.qualityExplanationCode && EXPLANATION_LABELS[diagnostics.qualityExplanationCode] && (
            <div>
              <dt>Ranking note</dt>
              <dd>{EXPLANATION_LABELS[diagnostics.qualityExplanationCode]}</dd>
            </div>
          )}
          {diagnostics.semanticRawRank !== null && diagnostics.semanticAdjustedRank !== null && diagnostics.semanticRawRank !== diagnostics.semanticAdjustedRank && (
            <div>
              <dt>Semantic rank</dt>
              <dd>
                adjusted #{diagnostics.semanticAdjustedRank} (raw cosine rank #{diagnostics.semanticRawRank})
              </dd>
            </div>
          )}
          {diagnostics.lexicalRankPosition !== null && (
            <div>
              <dt>Lexical rank</dt>
              <dd>{diagnostics.lexicalRankPosition}</dd>
            </div>
          )}
          {diagnostics.fusedScore !== null && (
            <div>
              <dt>Fused score</dt>
              <dd>{diagnostics.fusedScore.toFixed(4)}</dd>
            </div>
          )}
          {diagnostics.vectorSearchMode && (
            <div>
              <dt>Vector search mode</dt>
              <dd>{diagnostics.vectorSearchMode}</dd>
            </div>
          )}
          {diagnostics.model && (
            <div>
              <dt>Model</dt>
              <dd>
                {diagnostics.model}
                {diagnostics.modelRevision ? ` @ ${diagnostics.modelRevision.slice(0, 8)}` : ""}
              </dd>
            </div>
          )}
        </dl>
      </details>

      <p className={styles.footer}>
        <span>{formatCount(context.wordCount)} words</span>
        <span className={styles.citation}>{result.citation.label}</span>
        <Link href={result.evidenceUrl}>View evidence →</Link>
      </p>
    </article>
  );
}
