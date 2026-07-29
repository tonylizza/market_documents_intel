import type { ReactNode } from "react";
import styles from "./TechnicalDetails.module.css";

export interface TechnicalDetailsProps {
  summary: string;
  children: ReactNode;
}

/** Native `<details>`-based expandable section -- no JavaScript required,
 * keyboard-operable and screen-reader-friendly by default. */
export function TechnicalDetails({ summary, children }: TechnicalDetailsProps) {
  return (
    <details className={styles.details}>
      <summary className={styles.summary}>{summary}</summary>
      <div className={styles.content}>{children}</div>
    </details>
  );
}
