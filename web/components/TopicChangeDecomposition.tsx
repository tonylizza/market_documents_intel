import Link from "next/link";
import {
  TOPIC_CATEGORIES,
  type TopicCategory,
  type TopicChangeDetail,
  type TopicEvidencePassage,
} from "@/lib/domain/comparison";
import { formatCount, formatMetricValue } from "@/lib/formatting/numbers";
import {
  NET_TONE_DECLINE_THRESHOLD,
  TOPIC_LABELS,
  TOPIC_THRESHOLDS,
  describeNetToneDriver,
  describeTopicChange,
  meetsTopicThreshold,
  relativeLengthChange,
} from "@/lib/services/topic-change";
import { DefinitionList } from "./DefinitionList";
import { EmptyState } from "./EmptyState";
import styles from "./TopicChangeDecomposition.module.css";

export interface TopicChangeDecompositionProps {
  comparisonId: string;
  topicChange: TopicChangeDetail | null;
  netToneChange: number | null;
  evidence: readonly TopicEvidencePassage[];
}

function formatShare(value: number | null): string {
  return value === null ? "Not available" : `${(value * 100).toFixed(0)}%`;
}

function formatSigned(value: number | null): string {
  return formatMetricValue(value, "rate_per_1000_words") ?? "Not available";
}

function EvidenceList({ passages, side }: { passages: readonly TopicEvidencePassage[]; side: "EARLIER" | "LATER" }) {
  const rows = passages.filter((p) => p.reportSide === side);
  if (rows.length === 0) return <p className={styles.muted}>No category words in this report&apos;s eligible narrative.</p>;
  return (
    <ol className={styles.evidence}>
      {rows.map((p) => (
        <li key={`${p.passageComparisonId}-${p.reportSide}`}>
          <p className={styles.evidenceMeta}>
            {formatCount(p.hits)} hits{p.firstPageNumber !== null ? ` · page ${p.firstPageNumber}` : ""}
            {p.heading ? ` · ${p.heading}` : ""}
          </p>
          <p className={styles.excerpt}>{p.excerpt}</p>
          {p.alignmentCaveat && <p className={styles.caution}>{p.alignmentCaveat}</p>}
          <Link href={`/passages/${p.passageComparisonId}`}>View passage →</Link>
        </li>
      ))}
    </ol>
  );
}

function CategoryPanel({
  category,
  detail,
  comparisonId,
  evidence,
}: {
  category: TopicCategory;
  detail: TopicChangeDetail;
  comparisonId: string;
  evidence: readonly TopicEvidencePassage[];
}) {
  const change = detail.categories[category];
  const { threshold, direction } = TOPIC_THRESHOLDS[category];
  const eligible = meetsTopicThreshold(category, change.topicChange);
  const lengthChange = relativeLengthChange(detail.wordsEarlier, detail.wordsLater);
  const categoryEvidence = evidence.filter((p) => p.category === category);

  return (
    <article className={styles.panel} aria-labelledby={`topic-${category}`}>
      <h3 id={`topic-${category}`} className={styles.title}>
        {TOPIC_LABELS[category].title}: {formatSigned(change.topicChange)}
      </h3>
      <p className={styles.status}>
        {eligible
          ? `Clears the Discover threshold (${direction === "increase" ? "increase of at least" : "at least ±"}${threshold.toFixed(2)} per 1,000 words).`
          : `Below the Discover threshold (${direction === "increase" ? "increase of at least" : "at least ±"}${threshold.toFixed(2)} per 1,000 words).`}{" "}
        {TOPIC_LABELS[category].doesNotMean}
      </p>
      {describeTopicChange(change) && <p>{describeTopicChange(change)}</p>}
      <DefinitionList
        items={[
          {
            term: "Category word hits (earlier → later)",
            description:
              change.hitsEarlier === null || change.hitsLater === null
                ? "Not available"
                : `${formatCount(change.hitsEarlier)} → ${formatCount(change.hitsLater)}`,
          },
          { term: "Count change per 1,000 average words", description: formatSigned(change.countChangePer1000) },
          { term: "Density change per 1,000 words", description: formatSigned(change.densityChange) },
          {
            term: "Narrative words analysed (earlier → later)",
            description:
              detail.wordsEarlier === null || detail.wordsLater === null
                ? "Not available"
                : `${formatCount(detail.wordsEarlier)} → ${formatCount(detail.wordsLater)}${
                    lengthChange === null ? "" : ` (${lengthChange >= 0 ? "+" : ""}${(lengthChange * 100).toFixed(0)}% length change)`
                  }`,
          },
          {
            term: "Passages moving with / against the net change",
            description:
              change.supportingHits === null || change.opposingHits === null
                ? "Not available"
                : `${formatCount(change.supportingHits)} hits with, ${formatCount(change.opposingHits)} hits against`,
          },
          {
            term: "Change consistency",
            description: `${change.changeConsistencyRatio === null ? "Not available" : change.changeConsistencyRatio.toFixed(2)} -- net change divided by total passage-level churn (±1 = every changed passage moved the same way).`,
          },
          {
            term: "Largest single-passage share",
            description: `${formatShare(change.largestPassageShare)} of all passage-level churn came from one passage.`,
          },
        ]}
      />
      <p className={styles.muted}>
        Passage-level figures group passages by their alignment between the two reports. They are supporting context
        only: they never decide whether a change is published, and weakly aligned passages may have moved rather than
        been added or removed.
      </p>
      <div className={styles.sides}>
        <div>
          <h4 className={styles.sideTitle}>Highest-hit passages, earlier report</h4>
          <EvidenceList passages={categoryEvidence} side="EARLIER" />
        </div>
        <div>
          <h4 className={styles.sideTitle}>Highest-hit passages, later report</h4>
          <EvidenceList passages={categoryEvidence} side="LATER" />
        </div>
      </div>
      <p>
        <Link href={`/comparisons/${comparisonId}/evidence?category=${category}`}>
          Explore all passages with {TOPIC_LABELS[category].title.toLowerCase().replace(" change", "")} words →
        </Link>
      </p>
    </article>
  );
}

/**
 * Track 7F.9 -- decomposition panel for the unified topic-change metric
 * (financial-condition, governance, uncertainty) plus the net-tone
 * positive/negative components. Report-side highest-hit passages are shown
 * as evidence instead of earlier->later passage pairs, so a weak alignment
 * can never be presented as the cause of a change.
 */
export function TopicChangeDecomposition({ comparisonId, topicChange, netToneChange, evidence }: TopicChangeDecompositionProps) {
  if (!topicChange) {
    return (
      <EmptyState
        title="No topic-change detail available"
        description="This comparison has no published language features, or was published before topic-change detail was available."
      />
    );
  }
  const driver = describeNetToneDriver(netToneChange, topicChange.positiveRateChange, topicChange.negativeRateChange);
  return (
    <div className={styles.wrapper}>
      {TOPIC_CATEGORIES.map((category) => (
        <CategoryPanel key={category} category={category} detail={topicChange} comparisonId={comparisonId} evidence={evidence} />
      ))}
      <article className={styles.panel} aria-labelledby="topic-net-tone">
        <h3 id="topic-net-tone" className={styles.title}>
          Net tone change: {formatSigned(netToneChange)}
        </h3>
        <p className={styles.status}>
          {netToneChange !== null && netToneChange <= NET_TONE_DECLINE_THRESHOLD
            ? `Clears the Discover net tone decline threshold (${NET_TONE_DECLINE_THRESHOLD.toFixed(2)} per 1,000 words).`
            : `Discover lists net tone declines of ${NET_TONE_DECLINE_THRESHOLD.toFixed(2)} per 1,000 words or more.`}{" "}
          A dictionary word-count measure -- not management sentiment, outlook, or performance.
        </p>
        <DefinitionList
          items={[
            { term: "Positive-word density change", description: formatSigned(topicChange.positiveRateChange) },
            { term: "Negative-word density change", description: formatSigned(topicChange.negativeRateChange) },
          ]}
        />
        {driver && <p>{driver}</p>}
      </article>
    </div>
  );
}
