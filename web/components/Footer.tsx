import Link from "next/link";
import { NON_ADVICE_NOTICE, PRODUCT_NAME } from "@/lib/config/product";
import styles from "./Footer.module.css";

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={`container ${styles.inner}`}>
        <p className={styles.project}>{PRODUCT_NAME}</p>
        <p className={styles.notice}>{NON_ADVICE_NOTICE}</p>
        <p className={styles.links}>
          <Link href="/methodology">Methodology</Link>
        </p>
        <p className={styles.attribution}>A portfolio research project. Not affiliated with the JSE.</p>
      </div>
    </footer>
  );
}
