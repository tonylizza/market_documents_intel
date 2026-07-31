import type { CompanyNameLookup } from "@/lib/services/qa/query-analysis";
import { analyzeQuestion } from "@/lib/services/qa/query-analysis";
import type { QueryAnalysis } from "@/lib/domain/qa-evidence";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";

/**
 * Milestone 7B.2 deterministic question router. Reuses `analyzeQuestion`
 * (7B.1b, unchanged) for the underlying facet extraction -- this module
 * only adds a routing decision on top, never re-derives ticker/date/
 * direction extraction.
 *
 * Limitation (documented, not silently dropped): `app.qa_chunk_comparison_
 * contexts` (the chunk-to-comparison-side mapping the brief lists as
 * optional) was deferred in this milestone -- see the 7B.2 final report.
 * Without it, `COMPARISON_QA` cannot resolve an exact `report_comparison_id`
 * per chunk, so `bothSidesPresent` is approximated from cited evidence's
 * report periods (distinct `reportPeriodEnd` values for the same company)
 * rather than verified comparison-side membership, and the comparison link
 * points at the company's timeline (`/companies/[ticker]`) rather than one
 * specific `/comparisons/[id]`. This is honest, bounded degradation, not a
 * silent gap: the prompt is told explicitly to withhold a change claim
 * whenever `bothSidesPresent` is false.
 */
export type QaRoute = "DOCUMENT_QA" | "COMPARISON_QA" | "CORPUS_QA";

export interface QaRoutingDecision {
  route: QaRoute;
  analysis: QueryAnalysis;
  /** Server-computed link target for "link to the comparison interface"
   * (brief, COMPARISON_QA) -- `null` for non-comparison routes or when no
   * single company could be resolved. */
  comparisonLinkTicker: string | null;
}

export function routeQuestion(question: string, companies: readonly CompanyNameLookup[]): QaRoutingDecision {
  const analysis = analyzeQuestion(question, companies);

  const isComparisonShaped =
    analysis.questionType === "comparative" ||
    analysis.questionType === "chronological" ||
    analysis.requestedScope === "single_comparison" ||
    analysis.comparisonDirection !== null ||
    analysis.alignmentStatuses.length > 0;

  if (isComparisonShaped) {
    return {
      route: "COMPARISON_QA",
      analysis,
      comparisonLinkTicker: analysis.tickers.length === 1 ? analysis.tickers[0] : null,
    };
  }

  if (analysis.tickers.length === 0 || analysis.requestedScope === "corpus_wide") {
    return { route: "CORPUS_QA", analysis, comparisonLinkTicker: null };
  }

  return { route: "DOCUMENT_QA", analysis, comparisonLinkTicker: null };
}

/**
 * COMPARISON_QA safeguard (brief: "require evidence from the relevant
 * earlier/later sides before asserting change ... do not infer direction
 * from unlabeled numbers"). Bounded approximation given the deferred
 * comparison-context mapping (see module docstring): true only when the
 * cited evidence includes at least two distinct report period-ends for the
 * same company -- i.e. genuinely spans more than one report, not just more
 * than one chunk of the same report.
 */
export function bothSidesPresent(evidence: readonly QaEvidenceChunk[]): boolean {
  const periodsByCompany = new Map<string, Set<string>>();
  for (const e of evidence) {
    if (!e.citation.reportPeriodEnd) continue;
    const set = periodsByCompany.get(e.citation.companyId) ?? new Set<string>();
    set.add(e.citation.reportPeriodEnd);
    periodsByCompany.set(e.citation.companyId, set);
  }
  return [...periodsByCompany.values()].some((periods) => periods.size >= 2);
}

/** CORPUS_QA citation grouping (brief: "group citations by company and
 * report"). Deterministic: companies in first-seen order, reports within a
 * company in first-seen order -- never re-sorted by score, so grouping is
 * stable across identical evidence sets. */
export function groupEvidenceByCompanyAndReport(
  evidence: readonly QaEvidenceChunk[],
): { companyTicker: string; companyName: string; reports: { reportId: string; reportTitle: string; chunks: QaEvidenceChunk[] }[] }[] {
  const companyOrder: string[] = [];
  const byCompany = new Map<string, QaEvidenceChunk[]>();
  for (const e of evidence) {
    const key = e.citation.companyTicker;
    if (!byCompany.has(key)) {
      byCompany.set(key, []);
      companyOrder.push(key);
    }
    byCompany.get(key)!.push(e);
  }

  return companyOrder.map((ticker) => {
    const companyEvidence = byCompany.get(ticker)!;
    const reportOrder: string[] = [];
    const byReport = new Map<string, QaEvidenceChunk[]>();
    for (const e of companyEvidence) {
      if (!byReport.has(e.citation.reportId)) {
        byReport.set(e.citation.reportId, []);
        reportOrder.push(e.citation.reportId);
      }
      byReport.get(e.citation.reportId)!.push(e);
    }
    return {
      companyTicker: ticker,
      companyName: companyEvidence[0].citation.companyName,
      reports: reportOrder.map((reportId) => ({
        reportId,
        reportTitle: byReport.get(reportId)![0].citation.reportTitle,
        chunks: byReport.get(reportId)!,
      })),
    };
  });
}
