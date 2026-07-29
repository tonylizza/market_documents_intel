import { CorpusStat } from "./CorpusStat";
import { formatCount } from "@/lib/formatting/numbers";
import { formatReportRange } from "@/lib/formatting/dates";
import type { ApplicationDataSummary } from "@/lib/domain/metric";
import styles from "./DataCoverageSummary.module.css";

export interface DataCoverageSummaryProps {
  summary: ApplicationDataSummary;
}

/** Corpus-wide summary strip -- company/report/comparison counts and the
 * available period range. Deliberately does not surface any technical
 * database identifier (publication UUID, schema version) prominently. */
export function DataCoverageSummary({ summary }: DataCoverageSummaryProps) {
  const range = formatReportRange(summary.earliestPeriodEnd, summary.latestPeriodEnd);

  return (
    <section className={styles.wrapper} aria-label="Corpus summary">
      <div className={styles.stats}>
        <CorpusStat label="Companies" value={formatCount(summary.companyCount)} />
        <CorpusStat label="Reports" value={formatCount(summary.reportCount)} />
        <CorpusStat label="Comparisons" value={formatCount(summary.comparisonCount)} />
        {range && <CorpusStat label="Period range" value={range} />}
      </div>
      <p className={styles.note}>{summary.publicationNote}</p>
    </section>
  );
}
