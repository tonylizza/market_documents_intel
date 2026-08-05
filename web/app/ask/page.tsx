import type { Metadata } from "next";
import Link from "next/link";
import { cookies } from "next/headers";
import { PageHeader } from "@/components/PageHeader";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { AnswerStatusBanner } from "@/components/AnswerStatusBanner";
import { QaEvidenceList } from "@/components/QaEvidenceList";
import { AskForm } from "@/components/AskForm";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";
import { MAX_QUESTION_LENGTH_CHARS, QaQuestionTooLongError, runQaPipeline } from "@/lib/services/qa/qa-orchestrator";
import { hashClientId } from "@/lib/services/qa/quota-service";
import styles from "./page.module.css";

const CLIENT_ID_COOKIE = "mdi_cid";

export const metadata: Metadata = { title: "Ask" };

/** Highly parameterized, per-question pipeline output -- never cached
 * across the unbounded question space (mirrors `/passages` and
 * `/evidence-review`'s caching discipline). */
export const dynamic = "force-dynamic";

interface AskPageProps {
  searchParams: Promise<{ q?: string; company?: string; year?: string }>;
}

const ROUTE_LABELS: Record<string, string> = {
  DOCUMENT_QA: "Single-report question",
  COMPARISON_QA: "Comparison / change-over-time question",
  CORPUS_QA: "Corpus-wide question",
};

function yearsInRange(start: string | null, end: string | null): string[] {
  if (!start || !end) return [];
  const startYear = Number.parseInt(start.slice(0, 4), 10);
  const endYear = Number.parseInt(end.slice(0, 4), 10);
  if (!Number.isFinite(startYear) || !Number.isFinite(endYear)) return [];
  const years: string[] = [];
  for (let y = startYear; y <= endYear; y += 1) years.push(String(y));
  return years;
}

export default async function AskPage({ searchParams }: AskPageProps) {
  const { q, company, year } = await searchParams;
  const question = q?.trim() ?? "";
  const companyFilter = company?.trim().toUpperCase() || null;
  const yearFilter = year?.trim() || null;

  let companies: { ticker: string; name: string }[] = [];
  let reportYears: string[] = [];
  let filterLoadFailed = false;
  try {
    const companyRepository = new PostgresCompanyRepository();
    const allCompanies = await companyRepository.listCompanies();
    companies = allCompanies.map((c) => ({ ticker: c.ticker, name: c.name })).sort((a, b) => a.ticker.localeCompare(b.ticker));
    const years = new Set<string>();
    for (const c of allCompanies) {
      for (const y of yearsInRange(c.firstReportPeriodEnd, c.latestReportPeriodEnd)) years.add(y);
    }
    reportYears = [...years].sort((a, b) => Number(b) - Number(a));
  } catch (error) {
    filterLoadFailed = true;
    console.error("Failed to load company/year filters for /ask:", (error as Error).message);
  }

  let result: Awaited<ReturnType<typeof runQaPipeline>> | null = null;
  let pipelineFailed = false;
  let questionTooLong = false;
  if (question !== "") {
    if (question.length > MAX_QUESTION_LENGTH_CHARS) {
      // Server-side request validation (brief: "maximum question length:
      // approximately 500 characters") -- rejected before any retrieval or
      // generation work happens, never a silent truncation.
      questionTooLong = true;
    } else {
      try {
        const cookieStore = await cookies();
        const rawClientId = cookieStore.get(CLIENT_ID_COOKIE)?.value ?? null;
        const clientIdHash = rawClientId ? hashClientId(rawClientId) : null;
        result = await runQaPipeline(question, { companyTicker: companyFilter, reportYear: yearFilter }, clientIdHash);
      } catch (error) {
        if (error instanceof QaQuestionTooLongError) {
          questionTooLong = true;
        } else {
          pipelineFailed = true;
          console.error("Failed to run Q&A pipeline:", (error as Error).message);
        }
      }
    }
  }

  return (
    <>
      <PageHeader
        title="Ask"
        description="Ask a question about the report corpus. Answers are generated only from retrieved report excerpts, with citations to the original report, page, and section -- never from outside knowledge. When evidence is insufficient, the system says so explicitly rather than guessing."
      />

      <AskForm
        initialQuestion={question}
        initialCompany={companyFilter ?? ""}
        initialReportYear={yearFilter ?? ""}
        companies={companies}
        reportYears={reportYears}
      />

      {filterLoadFailed && question === "" && (
        <p className={styles.warnings}>Company and year filters could not be loaded, but you can still ask a question.</p>
      )}

      {question === "" ? (
        <EmptyState
          title="Enter a question to get a grounded answer"
          description="Nothing is submitted to any external service other than the configured answer-generation provider, and only retrieved report excerpts (never raw vectors) are ever sent to it."
        />
      ) : questionTooLong ? (
        <ErrorState title={`Question is too long (maximum ${MAX_QUESTION_LENGTH_CHARS} characters).`} />
      ) : pipelineFailed || !result ? (
        <ErrorState title="Ask is temporarily unavailable" />
      ) : (
        (() => {
          const { route, answer, comparisonLinkTicker, grouped, analysis } = result;
          const citedChunkIds = new Set(answer.citedEvidence.map((e) => e.chunkId));
          return (
            <div className={styles.results}>
              <section aria-labelledby="answer-heading" className={styles.section}>
                <span className={styles.routeBadge}>{ROUTE_LABELS[route] ?? route}</span>
                <h2 id="answer-heading">Answer</h2>
                <AnswerStatusBanner
                  status={answer.status}
                  unsupportedPortion={answer.unsupportedPortion}
                  errorDetail={answer.errorDetail}
                />
                {answer.answerText && <p className={styles.answerText}>{answer.answerText}</p>}
                {route === "COMPARISON_QA" && comparisonLinkTicker && (
                  <p className={styles.comparisonLink}>
                    <Link href={`/companies/${comparisonLinkTicker}`}>
                      View {comparisonLinkTicker}&apos;s full comparison timeline
                    </Link>
                  </p>
                )}
                {analysis.warnings.length > 0 && (
                  <ul className={styles.warnings}>
                    {analysis.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                )}
              </section>

              {route === "CORPUS_QA" && grouped.length > 0 ? (
                <section aria-labelledby="evidence-heading" className={`${styles.section} ${styles.groupedSection}`}>
                  <h2 id="evidence-heading">Supporting excerpts, by company and report</h2>
                  {grouped.map((group) => (
                    <div key={group.companyTicker}>
                      <h3>
                        {group.companyTicker} -- {group.companyName}
                      </h3>
                      {group.reports.map((report) => (
                        <div key={report.reportId}>
                          <h4>{report.reportTitle}</h4>
                          <QaEvidenceList allEvidence={report.chunks} citedChunkIds={citedChunkIds} />
                        </div>
                      ))}
                    </div>
                  ))}
                </section>
              ) : (
                <section aria-labelledby="evidence-heading" className={styles.section}>
                  <h2 id="evidence-heading">Supporting excerpts</h2>
                  {answer.allEvidence.length === 0 ? (
                    <EmptyState title="No supporting excerpts were retrieved for this question." />
                  ) : (
                    <QaEvidenceList allEvidence={answer.allEvidence} citedChunkIds={citedChunkIds} />
                  )}
                </section>
              )}
            </div>
          );
        })()
      )}
    </>
  );
}
