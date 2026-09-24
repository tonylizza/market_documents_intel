import type { TopicCategory, TopicCategoryChange } from "@/lib/domain/comparison";

/**
 * Track 7F.9 -- pure presentation helpers for the unified topic-change
 * decomposition (docs/discover-metrics-unified-implementation-7f9.md).
 * Thresholds mirror `findings.CandidateSpec.epsilon`; they are shown to
 * the user, never used to re-rank.
 */
export const TOPIC_THRESHOLDS: Record<TopicCategory, { threshold: number; direction: "both" | "increase" }> = {
  financial_condition: { threshold: 0.25, direction: "both" },
  governance: { threshold: 0.25, direction: "both" },
  uncertainty: { threshold: 0.75, direction: "increase" },
};

export const NET_TONE_DECLINE_THRESHOLD = -2.25;

export const TOPIC_LABELS: Record<TopicCategory, { title: string; doesNotMean: string }> = {
  financial_condition: {
    title: "Financial-condition language change",
    doesNotMean: "It describes wording only -- not financial health, financial performance, or financial risk.",
  },
  governance: {
    title: "Governance language change",
    doesNotMean: "It describes wording only -- not whether governance quality improved or worsened.",
  },
  uncertainty: {
    title: "Uncertainty-language change",
    doesNotMean: "It describes wording only -- not whether the business actually became more or less uncertain.",
  },
};

export function meetsTopicThreshold(category: TopicCategory, value: number | null): boolean {
  if (value === null) return false;
  const { threshold, direction } = TOPIC_THRESHOLDS[category];
  if (direction === "increase" && value <= 0) return false;
  return Math.abs(value) >= threshold;
}

/** Plain statement of why the topic change is (or is not) nonzero -- the
 * two legs are reported as observed, never interpreted. */
export function describeTopicChange(change: TopicCategoryChange): string | null {
  const { hitsEarlier, hitsLater, countChangePer1000, densityChange, topicChange } = change;
  if (hitsEarlier === null || hitsLater === null || countChangePer1000 === null || densityChange === null || topicChange === null) {
    return null;
  }
  if (hitsEarlier === hitsLater) {
    return "The category's word count did not change, so there is no topic change; any density movement came from the report getting longer or shorter.";
  }
  if (topicChange === 0) {
    return "The word count and the word density moved in opposite directions, so the change is attributed to report length rather than to the category itself; the topic change is 0.";
  }
  const direction = topicChange > 0 ? "rose" : "fell";
  return `Both the word count and the word density ${direction}; the topic change is the smaller of the two movements.`;
}

export function relativeLengthChange(wordsEarlier: number | null, wordsLater: number | null): number | null {
  if (wordsEarlier === null || wordsLater === null) return null;
  const mean = (wordsEarlier + wordsLater) / 2;
  return mean > 0 ? (wordsLater - wordsEarlier) / mean : null;
}

/** Which component mainly drove a net-tone movement: each component's signed
 * contribution to `netToneChange = positiveRateChange - negativeRateChange`
 * is compared in the direction of the overall change. */
export function describeNetToneDriver(
  netToneChange: number | null,
  positiveRateChange: number | null,
  negativeRateChange: number | null,
): string | null {
  if (netToneChange === null || positiveRateChange === null || negativeRateChange === null || netToneChange === 0) {
    return null;
  }
  const sign = Math.sign(netToneChange);
  const positiveContribution = Math.max(0, sign * positiveRateChange);
  const negativeContribution = Math.max(0, sign * -negativeRateChange);
  if (sign < 0) {
    return positiveContribution >= negativeContribution
      ? "Driven mainly by fewer positive words."
      : "Driven mainly by more negative words.";
  }
  return positiveContribution >= negativeContribution
    ? "Driven mainly by more positive words."
    : "Driven mainly by fewer negative words.";
}
