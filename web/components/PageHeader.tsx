import type { ReactNode } from "react";
import styles from "./PageHeader.module.css";

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  description?: string;
  children?: ReactNode;
}

export function PageHeader({ title, subtitle, description, children }: PageHeaderProps) {
  return (
    <div className={styles.wrapper}>
      <div className={styles.text}>
        {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
        <h1 className={styles.title}>{title}</h1>
        {description && <p className={styles.description}>{description}</p>}
      </div>
      {children && <div className={styles.extra}>{children}</div>}
    </div>
  );
}
