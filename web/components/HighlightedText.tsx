import type { HighlightSpan } from "@/lib/domain/passage";
import styles from "./HighlightedText.module.css";

export interface HighlightedTextProps {
  spans: readonly HighlightSpan[];
}

/**
 * Renders lexical-highlight spans as real `<mark>` elements -- a structured
 * alternative to `dangerouslySetInnerHTML`. `spans` are produced by
 * `buildHighlightSpans`/`buildExcerpt` (TypeScript-side, never raw database
 * HTML), so this component can safely render plain text nodes throughout.
 */
export function HighlightedText({ spans }: HighlightedTextProps) {
  return (
    <>
      {spans.map((span, index) =>
        span.matched ? (
          <mark className={styles.mark} key={index}>
            {span.text}
          </mark>
        ) : (
          <span key={index}>{span.text}</span>
        ),
      )}
    </>
  );
}
