import Link from "next/link";
import type { CompanyCardSummary } from "@/lib/domain/comparison";
import { formatReportRange, formatComparisonPeriod } from "@/lib/formatting/dates";
import { formatCount } from "@/lib/formatting/numbers";
import { DisclosureChangeSummary } from "./DisclosureChangeSummary";
import { QualityBadge } from "./QualityBadge";
import styles from "./CompanyCard.module.css";

export interface CompanyCardProps {
  company: CompanyCardSummary;
}

/**
 * Only the company name is an interactive link (to the Milestone 7A.3
 * placeholder shell at `/companies/[ticker]`) -- the card intentionally
 * does not wrap its entire content in one anchor, since `Tooltip` renders
 * an interactive `<button>` further down and nested interactive elements
 * (`<a><button/></a>`) are invalid HTML and break keyboard/AT navigation.
 */
export function CompanyCard({ company }: CompanyCardProps) {
  const comparison = company.latestComparison;
  const reportRange = formatReportRange(company.firstReportPeriodEnd, company.latestReportPeriodEnd);
  const comparisonPeriod = comparison
    ? formatComparisonPeriod(comparison.earlierPeriodEnd, comparison.laterPeriodEnd)
    : null;

  return (
    <article className={styles.card} aria-labelledby={`company-${company.ticker}-name`}>
      <header className={styles.header}>
        <div>
          <h3 className={styles.name} id={`company-${company.ticker}-name`}>
            <Link href={`/companies/${company.ticker}`}>{company.name}</Link>
          </h3>
          <span className={styles.ticker}>{company.ticker}</span>
        </div>
        {company.isHistoricalPeak && <span className={styles.peakBadge}>Historical peak change</span>}
      </header>

      <dl className={styles.metaGrid}>
        <div>
          <dt>Report range</dt>
          <dd>{reportRange ?? "—"}</dd>
        </div>
        <div>
          <dt>Reports</dt>
          <dd>{formatCount(company.reportCount)}</dd>
        </div>
        <div>
          <dt>Comparisons</dt>
          <dd>{formatCount(company.comparisonCount)}</dd>
        </div>
        {comparisonPeriod && (
          <div>
            <dt>Latest comparison</dt>
            <dd>{comparisonPeriod}</dd>
          </div>
        )}
      </dl>

      {comparison ? (
        <>
          <DisclosureChangeSummary
            score={comparison.disclosureChangeScore}
            label={comparison.disclosureChangeLabel}
            quality={comparison.disclosureChangeQuality}
            qualityLabel={comparison.disclosureChangeQualityLabel}
          />

          {(comparison.uncertaintyChangeLabel || comparison.riskIntroductionLabel) && (
            <ul className={styles.signals}>
              {comparison.uncertaintyChangeLabel && (
                <li className={styles.signal}>
                  <span className={styles.signalLabel}>Uncertainty direction</span>
                  <span>{comparison.uncertaintyChangeLabel}</span>
                </li>
              )}
              {comparison.riskIntroductionLabel && (
                <li className={styles.signal}>
                  <span className={styles.signalLabel}>Risk introduction</span>
                  <span>{comparison.riskIntroductionLabel}</span>
                </li>
              )}
            </ul>
          )}

          <div className={styles.badges}>
            <QualityBadge
              dimension="report-side"
              quality={comparison.reportSideQuality}
              label={comparison.reportSideQualityLabel}
              compact
            />
          </div>
        </>
      ) : (
        <p className={styles.noComparison}>No comparison available yet for this company.</p>
      )}
    </article>
  );
}
