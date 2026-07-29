import styles from "./LoadingSkeleton.module.css";

export interface LoadingSkeletonProps {
  /** Number of skeleton blocks to render (e.g. one per expected card). */
  count?: number;
  label?: string;
}

export function LoadingSkeleton({ count = 3, label = "Loading" }: LoadingSkeletonProps) {
  return (
    <div className={styles.wrapper} role="status" aria-label={label}>
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className={styles.block} aria-hidden="true" />
      ))}
      <span className="visually-hidden">{label}</span>
    </div>
  );
}
