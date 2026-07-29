"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { ComparisonSummary } from "@/lib/domain/comparison";
import type { CompanyHistoricalHighlights } from "@/lib/domain/company";
import { NAVIGATOR_THRESHOLDS, selectNavigatorMode } from "@/lib/config/comparison";
import { ComparisonNavigatorCard } from "./ComparisonNavigatorCard";
import styles from "./AdaptiveComparisonNavigator.module.css";

export interface AdaptiveComparisonNavigatorProps {
  comparisons: readonly ComparisonSummary[];
  companyTicker: string;
  selectedComparisonId: string | null;
  highlights: CompanyHistoricalHighlights;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Implements the three approved navigator modes (see `NAVIGATOR_THRESHOLDS`)
 * -- mode is a pure function of `comparisons.length`, never inferred from
 * viewport width. Every mode renders real `Link`s
 * (`?comparison=<id>`), so the navigator works with JavaScript disabled and
 * every selection is a genuine, shareable URL.
 */
export function AdaptiveComparisonNavigator({
  comparisons,
  companyTicker,
  selectedComparisonId,
  highlights,
}: AdaptiveComparisonNavigatorProps) {
  const mode = selectNavigatorMode(comparisons.length);

  if (comparisons.length === 0) {
    return <p className={styles.empty}>No comparisons are available for this company yet.</p>;
  }

  if (mode === "compact") {
    return (
      <div className={styles.compactGrid} data-testid="navigator-compact">
        {comparisons.map((comparison) => (
          <ComparisonNavigatorCard
            key={comparison.id}
            comparison={comparison}
            companyTicker={companyTicker}
            selected={comparison.id === selectedComparisonId}
          />
        ))}
      </div>
    );
  }

  if (mode === "scrollable") {
    return (
      <ScrollableNavigator
        comparisons={comparisons}
        companyTicker={companyTicker}
        selectedComparisonId={selectedComparisonId}
      />
    );
  }

  return (
    <RangeFilteredNavigator
      comparisons={comparisons}
      companyTicker={companyTicker}
      selectedComparisonId={selectedComparisonId}
      highlights={highlights}
    />
  );
}

function ScrollableNavigator({
  comparisons,
  companyTicker,
  selectedComparisonId,
}: {
  comparisons: readonly ComparisonSummary[];
  companyTicker: string;
  selectedComparisonId: string | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<Map<string, HTMLElement>>(new Map());
  const [visibleIndices, setVisibleIndices] = useState<Set<number>>(new Set());

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        setVisibleIndices((prev) => {
          const next = new Set(prev);
          for (const entry of entries) {
            const index = Number((entry.target as HTMLElement).dataset.index);
            if (entry.isIntersecting) next.add(index);
            else next.delete(index);
          }
          return next;
        });
      },
      { root: container, threshold: 0.6 },
    );

    itemRefs.current.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [comparisons.length]);

  useEffect(() => {
    if (!selectedComparisonId) return;
    const element = itemRefs.current.get(selectedComparisonId);
    element?.scrollIntoView({ block: "nearest", inline: "center", behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }, [selectedComparisonId]);

  function scrollByCard(direction: 1 | -1) {
    const container = containerRef.current;
    if (!container) return;
    const cardWidth = container.querySelector<HTMLElement>("[data-comparison-id]")?.offsetWidth ?? 240;
    container.scrollBy({ left: direction * (cardWidth + 16), behavior: prefersReducedMotion() ? "auto" : "smooth" });
  }

  function handleKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Home") {
      event.preventDefault();
      itemRefs.current.get(comparisons[0].id)?.scrollIntoView({ inline: "start", block: "nearest" });
    } else if (event.key === "End") {
      event.preventDefault();
      itemRefs.current.get(comparisons[comparisons.length - 1].id)?.scrollIntoView({ inline: "end", block: "nearest" });
    }
  }

  const visibleCount = visibleIndices.size;
  const minVisible = visibleCount > 0 ? Math.min(...visibleIndices) + 1 : 1;
  const maxVisible = visibleCount > 0 ? Math.max(...visibleIndices) + 1 : 1;

  return (
    <div className={styles.scrollableWrapper} data-testid="navigator-scrollable">
      <div className={styles.scrollableControls}>
        <button type="button" onClick={() => scrollByCard(-1)} aria-label="Scroll to earlier comparisons">
          ← Earlier
        </button>
        <span className={styles.rangeIndicator} role="status">
          Showing {minVisible}–{maxVisible} of {comparisons.length} comparisons
        </span>
        <button type="button" onClick={() => scrollByCard(1)} aria-label="Scroll to later comparisons">
          Later →
        </button>
      </div>
      <div
        ref={containerRef}
        className={styles.scrollableRow}
        role="group"
        aria-label="Comparison history, scrollable"
        tabIndex={0}
        onKeyDown={handleKeyDown}
      >
        {comparisons.map((comparison, index) => (
          <div
            key={comparison.id}
            data-index={index}
            ref={(element) => {
              if (element) itemRefs.current.set(comparison.id, element);
              else itemRefs.current.delete(comparison.id);
            }}
          >
            <ComparisonNavigatorCard
              comparison={comparison}
              companyTicker={companyTicker}
              selected={comparison.id === selectedComparisonId}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function RangeFilteredNavigator({
  comparisons,
  companyTicker,
  selectedComparisonId,
  highlights,
}: {
  comparisons: readonly ComparisonSummary[];
  companyTicker: string;
  selectedComparisonId: string | null;
  highlights: CompanyHistoricalHighlights;
}) {
  const [showAll, setShowAll] = useState(false);
  const windowSize = NAVIGATOR_THRESHOLDS.longHistoryWindow;

  const visible = useMemo(() => {
    return showAll ? comparisons : comparisons.slice(Math.max(0, comparisons.length - windowSize));
  }, [comparisons, showAll, windowSize]);

  const firstVisible = visible[0];
  const lastVisible = visible[visible.length - 1];

  const shortcuts: { label: string; comparisonId: string | null }[] = [
    { label: "Latest comparison", comparisonId: highlights.latestComparisonId },
    { label: "Historical peak change", comparisonId: highlights.historicalPeakChangeComparisonId },
    { label: "Largest eligible uncertainty increase", comparisonId: highlights.largestEligibleUncertaintyIncreaseComparisonId },
    { label: "Largest eligible risk introduction", comparisonId: highlights.largestEligibleRiskIntroductionComparisonId },
  ];

  return (
    <div className={styles.rangeFilteredWrapper} data-testid="navigator-range-filtered">
      <div className={styles.rangeControls}>
        <div role="group" aria-label="Comparison range">
          <button type="button" aria-pressed={!showAll} onClick={() => setShowAll(false)} className={!showAll ? styles.rangeButtonActive : styles.rangeButton}>
            Latest {windowSize}
          </button>
          <button type="button" aria-pressed={showAll} onClick={() => setShowAll(true)} className={showAll ? styles.rangeButtonActive : styles.rangeButton}>
            All {comparisons.length}
          </button>
        </div>
        <p className={styles.rangeSummary} role="status">
          Showing {visible.length} of {comparisons.length} comparisons
          {firstVisible && lastVisible ? ` (${firstVisible.earlierPeriodEnd ?? "?"} – ${lastVisible.laterPeriodEnd ?? "?"})` : ""}
        </p>
      </div>

      <div className={styles.shortcuts}>
        {shortcuts
          .filter((shortcut) => shortcut.comparisonId !== null)
          .map((shortcut) => (
            <Link key={shortcut.label} href={`/companies/${companyTicker}?comparison=${shortcut.comparisonId}`} className={styles.shortcutLink}>
              {shortcut.label}
            </Link>
          ))}
      </div>

      <div className={styles.compactGrid}>
        {visible.map((comparison) => (
          <ComparisonNavigatorCard
            key={comparison.id}
            comparison={comparison}
            companyTicker={companyTicker}
            selected={comparison.id === selectedComparisonId}
          />
        ))}
      </div>
    </div>
  );
}
