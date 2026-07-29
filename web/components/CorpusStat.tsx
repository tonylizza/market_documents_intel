import styles from "./CorpusStat.module.css";

export interface CorpusStatProps {
  label: string;
  value: string;
}

export function CorpusStat({ label, value }: CorpusStatProps) {
  return (
    <div className={styles.stat}>
      <span className={styles.value}>{value}</span>
      <span className={styles.label}>{label}</span>
    </div>
  );
}
