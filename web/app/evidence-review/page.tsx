import type { Metadata } from "next";
import { runEvidencePipeline } from "@/lib/services/qa/qa-pipeline";
import { PageHeader } from "@/components/PageHeader";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { GateStatusBanner } from "@/components/GateStatusBanner";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Evidence review (experimental)" };

/** Highly parameterized, per-question pipeline output -- never cached
 * across the unbounded question space (mirrors `/passages`' caching
 * discipline). */
export const dynamic = "force-dynamic";

interface EvidenceReviewPageProps {
  searchParams: Promise<{ q?: string }>;
}

const EXPLANATION_LABELS: Record<string, string> = {
  DUPLICATE: "Duplicate of another selected passage",
  BELOW_RELEVANCE_FLOOR: "Below the corpus's weak-match relevance floor",
  OUT_OF_SCOPE: "Outside the question's required company, category, or report side",
  REDUNDANT_NO_NEW_COVERAGE: "Redundant -- added no new topic coverage beyond what was already selected",
  NOT_DIRECTLY_RESPONSIVE: "In scope, but not judged specifically responsive to the question's topic",
};

export default async function EvidenceReviewPage({ searchParams }: EvidenceReviewPageProps) {
  const { q } = await searchParams;
  const question = q?.trim() ?? "";

  let result: Awaited<ReturnType<typeof runEvidencePipeline>> | null = null;
  let failed = false;
  if (question !== "") {
    try {
      result = await runEvidencePipeline(question);
    } catch (error) {
      failed = true;
      console.error("Failed to run evidence-review pipeline:", (error as Error).message);
    }
  }

  return (
    <>
      <PageHeader
        title="Evidence review"
        subtitle="Experimental -- Milestone 7B.1b"
        description="Shows how the system selects and grades supporting evidence for a question. This is not a finished Q&A feature: it never generates an answer, a summary, or any model-written text -- only real, published passages with citations, and an explicit judgment of whether the evidence is sufficient."
      />
      <form className={styles.form} action="/evidence-review" method="get">
        <label htmlFor="evidence-review-question" className={styles.label}>
          Question
        </label>
        <input
          id="evidence-review-question"
          name="q"
          type="text"
          defaultValue={question}
          className={styles.input}
          placeholder="e.g. What did the company disclose about liquidity risk?"
        />
        <button type="submit" className={styles.submit}>
          Review evidence
        </button>
      </form>

      {question === "" ? (
        <EmptyState
          title="Enter a question to review its evidence"
          description="Nothing is submitted to any external service -- the question stays within this application."
        />
      ) : failed || !result ? (
        <ErrorState title="Evidence review is temporarily unavailable" />
      ) : (
        (() => {
          const { evidencePackage, candidates } = result;
          return (
            <div className={styles.results}>
              <section aria-labelledby="query-analysis-heading" className={styles.section}>
                <h2 id="query-analysis-heading">Query analysis</h2>
                <dl className={styles.analysisGrid}>
                  <div>
                    <dt>Question type</dt>
                    <dd>{evidencePackage.queryAnalysis.questionType}</dd>
                  </div>
                  <div>
                    <dt>Scope</dt>
                    <dd>{evidencePackage.queryAnalysis.requestedScope}</dd>
                  </div>
                  {evidencePackage.queryAnalysis.tickers.length > 0 && (
                    <div>
                      <dt>Companies mentioned</dt>
                      <dd>{evidencePackage.queryAnalysis.tickers.join(", ")}</dd>
                    </div>
                  )}
                  {evidencePackage.queryAnalysis.comparisonDirection && (
                    <div>
                      <dt>Comparison direction (from wording only, not verified)</dt>
                      <dd>{evidencePackage.queryAnalysis.comparisonDirection}</dd>
                    </div>
                  )}
                  <div>
                    <dt>Required concepts</dt>
                    <dd>{evidencePackage.queryAnalysis.requiredConceptFamilies.length > 0 ? evidencePackage.queryAnalysis.requiredConceptFamilies.join(", ") : "(none detected)"}</dd>
                  </div>
                  {evidencePackage.queryAnalysis.optionalConceptFamilies.length > 0 && (
                    <div>
                      <dt>Optional/supporting concepts</dt>
                      <dd>{evidencePackage.queryAnalysis.optionalConceptFamilies.join(", ")}</dd>
                    </div>
                  )}
                  {evidencePackage.queryAnalysis.materialElements.length > 1 && (
                    <div>
                      <dt>Material elements (separable parts of the question)</dt>
                      <dd>{evidencePackage.queryAnalysis.materialElements.map((e) => e.text).join(" | ")}</dd>
                    </div>
                  )}
                </dl>
                {(evidencePackage.queryAnalysis.warnings.length > 0 || evidencePackage.queryAnalysis.unresolvedRequiredConcepts.length > 0) && (
                  <ul className={styles.warnings}>
                    {evidencePackage.queryAnalysis.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                    {evidencePackage.queryAnalysis.unresolvedRequiredConcepts.map((concept) => (
                      <li key={concept}>Looks like a distinct topic, but matched no known concept family: &ldquo;{concept}&rdquo;</li>
                    ))}
                  </ul>
                )}
              </section>

              <section aria-labelledby="gate-status-heading" className={styles.section}>
                <h2 id="gate-status-heading">Groundedness assessment</h2>
                <GateStatusBanner status={evidencePackage.gateStatus} reasonCodes={evidencePackage.gateReasonCodes} />
                {evidencePackage.queryAnalysis.materialElements.length > 1 && (
                  <div className={styles.analysisGrid}>
                    <div>
                      <dt>Supported subquestions</dt>
                      <dd>{evidencePackage.supportedSubquestions.length > 0 ? evidencePackage.supportedSubquestions.join(" | ") : "(none)"}</dd>
                    </div>
                    <div>
                      <dt>Unsupported subquestions</dt>
                      <dd>{evidencePackage.unsupportedSubquestions.length > 0 ? evidencePackage.unsupportedSubquestions.join(" | ") : "(none)"}</dd>
                    </div>
                  </div>
                )}
                <p className={styles.muted}>{evidencePackage.partialSupportRationale}</p>
                {evidencePackage.coherence.restatementAmbiguityDetected && (
                  <p className={styles.warnings}>Restatement/correction ambiguity: chronology between original and restated values is not clear.</p>
                )}
                {evidencePackage.coherence.comparisonContextSatisfied === false && (
                  <p className={styles.warnings}>Comparison context is incomplete or topically mismatched between the requested report sides.</p>
                )}
                {evidencePackage.coherence.dateRangeCovered === false && <p className={styles.warnings}>No selected evidence falls within the requested date range.</p>}
              </section>

              <section aria-labelledby="selected-evidence-heading" className={styles.section}>
                <h2 id="selected-evidence-heading">Selected evidence ({evidencePackage.selectedEvidence.length})</h2>
                {evidencePackage.selectedEvidence.length === 0 ? (
                  <p className={styles.muted}>No passage was selected as sufficient evidence for this question.</p>
                ) : (
                  <ul className={styles.evidenceList}>
                    {evidencePackage.selectedEvidence.map((item) => (
                      <li key={item.candidateId} className={styles.evidenceItem}>
                        <p className={styles.evidenceHeading}>{item.context.heading ?? "(No heading)"}</p>
                        <p className={styles.evidenceExcerpt}>{item.context.text.slice(0, 280)}</p>
                        <p className={styles.citation}>{item.citation.label}</p>
                        <p className={styles.muted}>
                          Direct-responsiveness: {item.directResponsivenessScore.toFixed(2)} ({item.evidenceEligible ? "eligible" : "not eligible"})
                          {item.ineligibilityReasons.length > 0 ? ` -- ${item.ineligibilityReasons.join(", ")}` : ""}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section aria-labelledby="rejected-evidence-heading" className={styles.section}>
                <h2 id="rejected-evidence-heading">
                  Rejected candidates ({evidencePackage.rejectedEvidenceSummary.reduce((sum, r) => sum + r.count, 0)})
                </h2>
                {evidencePackage.rejectedEvidenceSummary.length === 0 ? (
                  <p className={styles.muted}>No candidates were rejected.</p>
                ) : (
                  <ul className={styles.rejectedList}>
                    {evidencePackage.rejectedEvidenceSummary.map((r) => (
                      <li key={r.reason}>
                        {r.count} × {EXPLANATION_LABELS[r.reason] ?? r.reason}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section aria-labelledby="candidate-sources-heading" className={styles.section}>
                <h2 id="candidate-sources-heading">Candidate sources</h2>
                <p className={styles.muted}>
                  {evidencePackage.retrievalDiagnostics.candidateCount} candidates from{" "}
                  {evidencePackage.retrievalDiagnostics.sources.join(" + ") || "no sources"}, reranked with{" "}
                  {evidencePackage.rerankerMethod.replace(/_/g, " ")}.
                </p>
              </section>

              <section aria-labelledby="latency-heading" className={styles.section}>
                <h2 id="latency-heading">Latency</h2>
                <p className={styles.muted}>{evidencePackage.latencyMs.total}ms total</p>
              </section>

              <p className={styles.candidateCount}>{candidates.length} total reranked candidates considered.</p>
            </div>
          );
        })()
      )}
    </>
  );
}
