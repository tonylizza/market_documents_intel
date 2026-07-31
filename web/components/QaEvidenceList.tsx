import Link from "next/link";
import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";
import styles from "./QaEvidenceList.module.css";

export interface QaEvidenceListProps {
  allEvidence: readonly QaEvidenceChunk[];
  citedChunkIds: ReadonlySet<string>;
}

/**
 * Expandable supporting excerpts (brief: "expandable supporting excerpts",
 * "page ranges and section headings", "links to mapped passages/
 * comparisons"). Numbered E1..EN in the same order the generation prompt
 * used, so a reader can match an answer's "[E2]"-style citation marker back
 * to the excerpt here. Native `<details>`/`<summary>` -- expandable and
 * keyboard/screen-reader accessible with no client JS.
 */
export function QaEvidenceList({ allEvidence, citedChunkIds }: QaEvidenceListProps) {
  if (allEvidence.length === 0) return null;

  return (
    <ul className={styles.list}>
      {allEvidence.map((evidence, index) => {
        const isCited = citedChunkIds.has(evidence.chunkId);
        return (
          <li key={evidence.chunkId} className={`${styles.item} ${isCited ? styles.itemCited : ""}`}>
            <details>
              <summary className={styles.summary}>
                <span className={styles.excerptLabel}>[E{index + 1}]</span>
                <span>{evidence.citation.label}</span>
                {isCited && <span className={styles.citedBadge}>Cited in answer</span>}
              </summary>
              <div className={styles.body}>
                <p className={styles.text}>{evidence.text}</p>
                <div className={styles.meta}>
                  {evidence.citation.sectionHeading && <span>Section: {evidence.citation.sectionHeading}</span>}
                  <span>
                    Pages {evidence.citation.pageStart}
                    {evidence.citation.pageEnd !== evidence.citation.pageStart ? `-${evidence.citation.pageEnd}` : ""}
                  </span>
                  {evidence.mergedCandidateCount > 1 && (
                    <span>Represents {evidence.mergedCandidateCount} overlapping matches</span>
                  )}
                  {evidence.citation.memberPassageIds.length > 0 && (
                    <Link
                      href={`/passages?q=&company=${evidence.citation.companyTicker}`}
                      className={styles.link}
                    >
                      View mapped passages
                    </Link>
                  )}
                </div>
              </div>
            </details>
          </li>
        );
      })}
    </ul>
  );
}
