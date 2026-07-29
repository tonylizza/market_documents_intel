import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PostgresPassageRepository } from "@/lib/repositories/postgres-passage-repository";
import { getPassageDetailViewModel } from "@/lib/services/passage-detail-service";
import { PageHeader } from "@/components/PageHeader";
import { SectionHeader } from "@/components/SectionHeader";
import { ErrorState } from "@/components/ErrorState";
import { PassageSideView } from "@/components/PassageSideView";
import { PassageDiffView } from "@/components/PassageDiffView";
import { PassageLanguageSignalsSection } from "@/components/PassageLanguageSignalsSection";
import { TechnicalDetails } from "@/components/TechnicalDetails";
import { DefinitionList } from "@/components/DefinitionList";
import { EmptyState } from "@/components/EmptyState";
import { formatAlignmentStatusLabel, formatAlignmentTypeLabel } from "@/lib/config/passage-vocabulary";
import { formatComparisonPeriod } from "@/lib/formatting/dates";
import { formatMetricValue } from "@/lib/formatting/numbers";
import styles from "./page.module.css";

interface PassageDetailPageProps {
  params: Promise<{ passageComparisonId: string }>;
}

export async function generateMetadata({ params }: PassageDetailPageProps): Promise<Metadata> {
  const { passageComparisonId } = await params;
  const repository = new PostgresPassageRepository();
  try {
    const detail = await repository.getPassageComparisonById(passageComparisonId);
    if (!detail) return { title: "Passage not found" };
    return { title: `${detail.companyTicker} passage evidence` };
  } catch {
    return { title: "Passage evidence" };
  }
}

/**
 * Full evidence detail for one passage comparison (Milestone 7A.4).
 * Two queries total (`getPassageDetailViewModel` -- `getPassageComparisonById`
 * + `getPassageLanguageSignals`, run as `Promise.all`); the text diff is a
 * pure, presentation-only function over the already-fetched two texts, not
 * a third query.
 */
export default async function PassageDetailPage({ params }: PassageDetailPageProps) {
  const { passageComparisonId } = await params;
  const repository = new PostgresPassageRepository();

  let viewModel: Awaited<ReturnType<typeof getPassageDetailViewModel>> = null;
  let failed = false;
  try {
    viewModel = await getPassageDetailViewModel(repository, passageComparisonId);
  } catch (error) {
    failed = true;
    console.error("Failed to load passage detail:", (error as Error).message);
  }

  if (failed) {
    return <ErrorState title="This passage evidence is temporarily unavailable" />;
  }
  if (!viewModel) {
    notFound();
  }

  const { detail, languageSignals, diff } = viewModel;
  const isNew = detail.alignmentStatus === "NEW";
  const isRemoved = detail.alignmentStatus === "REMOVED";
  const isMatchedBothSides = detail.earlier !== null && detail.later !== null;

  return (
    <>
      <p className={styles.backlink}>
        <Link href={`/comparisons/${detail.reportComparisonId}/evidence`}>← Back to comparison evidence</Link>
        {" · "}
        <Link href={`/comparisons/${detail.reportComparisonId}`}>Comparison summary</Link>
      </p>

      <PageHeader
        title={formatComparisonPeriod(detail.earlierPeriodEnd, detail.laterPeriodEnd) ?? "Unknown period"}
        subtitle={`${detail.companyName} (${detail.companyTicker}) -- passage evidence`}
        description={`${formatAlignmentStatusLabel(detail.alignmentStatus)} -- ${formatAlignmentTypeLabel(detail.alignmentType)}`}
      >
        <div className={styles.qualityRow}>
          <span className={styles.confidenceBadge}>{detail.confidenceLabel}</span>
        </div>
      </PageHeader>

      {detail.reviewReason && (
        <p className={styles.reviewReason} role="note">
          Review reason: {detail.reviewReason}
        </p>
      )}

      <section aria-labelledby="passage-evidence-heading" className={styles.section}>
        <SectionHeader id="passage-evidence-heading" title="Passage text" />

        {isMatchedBothSides && detail.earlier && detail.later && diff ? (
          <PassageDiffView earlier={detail.earlier} later={detail.later} diff={diff} />
        ) : isNew ? (
          <div className={styles.oneSided}>
            <EmptyState title="No aligned earlier passage" description="This passage is new in the later report." />
            {detail.later && <PassageSideView label="Later disclosure (primary)" side={detail.later} />}
          </div>
        ) : isRemoved ? (
          <div className={styles.oneSided}>
            {detail.earlier && <PassageSideView label="Earlier disclosure (primary)" side={detail.earlier} />}
            <EmptyState title="No aligned later passage" description="This passage was removed in the later report." />
          </div>
        ) : (
          <div className={styles.oneSided}>
            <p className={styles.ambiguousNote} role="note">
              This passage&rsquo;s attribution across reports is uncertain (AMBIGUOUS) -- only one side is available, and
              it is not confirmed as either newly added or removed.
            </p>
            {detail.earlier && <PassageSideView label="Earlier disclosure (uncertain attribution)" side={detail.earlier} />}
            {detail.later && <PassageSideView label="Later disclosure (uncertain attribution)" side={detail.later} />}
          </div>
        )}
      </section>

      <section aria-labelledby="passage-signals-heading" className={styles.section}>
        <SectionHeader id="passage-signals-heading" title="Passage-level language signals" />
        <PassageLanguageSignalsSection signals={languageSignals} />
      </section>

      <section aria-labelledby="passage-technical-heading" className={styles.section}>
        <SectionHeader id="passage-technical-heading" title="Technical details" />
        <TechnicalDetails summary="Show technical alignment values">
          <DefinitionList
            items={[
              { term: "Content score", description: formatMetricValue(detail.contentScore, "score_0_1") ?? "Not available" },
              { term: "Semantic similarity", description: formatMetricValue(detail.semanticSimilarity, "score_0_1") ?? "Not available" },
              { term: "Lexical similarity", description: formatMetricValue(detail.lexicalSimilarity, "score_0_1") ?? "Not available" },
              { term: "Heading similarity", description: formatMetricValue(detail.headingSimilarity, "score_0_1") ?? "Not available" },
              { term: "Position difference", description: detail.positionDifference !== null ? detail.positionDifference.toFixed(3) : "Not available" },
              { term: "Collision flagged", description: detail.collisionFlag ? "Yes" : "No" },
              { term: "Split/merge flagged", description: detail.splitMergeFlag ? "Yes" : "No" },
              { term: "Review reason", description: detail.reviewReason ?? "None" },
            ]}
          />
        </TechnicalDetails>
      </section>
    </>
  );
}
