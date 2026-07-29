import type { ReactNode } from "react";
import styles from "./SectionHeader.module.css";

export interface SectionHeaderProps {
  title: string;
  description?: string;
  children?: ReactNode;
  id?: string;
}

export function SectionHeader({ title, description, children, id }: SectionHeaderProps) {
  return (
    <div className={styles.wrapper}>
      <div>
        <h2 className={styles.title} id={id}>
          {title}
        </h2>
        {description && <p className={styles.description}>{description}</p>}
      </div>
      {children}
    </div>
  );
}
