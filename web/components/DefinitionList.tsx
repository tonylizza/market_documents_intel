import styles from "./DefinitionList.module.css";

export interface Definition {
  term: string;
  description: string;
}

export interface DefinitionListProps {
  items: readonly Definition[];
}

export function DefinitionList({ items }: DefinitionListProps) {
  return (
    <dl className={styles.list}>
      {items.map((item) => (
        <div className={styles.row} key={item.term}>
          <dt className={styles.term}>{item.term}</dt>
          <dd className={styles.description}>{item.description}</dd>
        </div>
      ))}
    </dl>
  );
}
