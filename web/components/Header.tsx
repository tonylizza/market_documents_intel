import Link from "next/link";
import { PRODUCT_NAME } from "@/lib/config/product";
import { PrimaryNavigation } from "./PrimaryNavigation";
import styles from "./Header.module.css";

export function Header() {
  return (
    <header className={styles.header}>
      <div className={`container ${styles.inner}`}>
        <Link href="/" className={styles.brand}>
          {PRODUCT_NAME}
        </Link>
        <PrimaryNavigation />
      </div>
    </header>
  );
}
