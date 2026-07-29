import styles from "./ErrorState.module.css";

export interface ErrorStateProps {
  title?: string;
  description?: string;
}

/** Polished service-unavailable state -- never a stack trace, never a raw
 * driver error message. */
export function ErrorState({
  title = "This section is temporarily unavailable",
  description = "We couldn't reach the application database. Please try again shortly.",
}: ErrorStateProps) {
  return (
    <div className={styles.wrapper} role="alert">
      <p className={styles.title}>{title}</p>
      <p className={styles.description}>{description}</p>
    </div>
  );
}
