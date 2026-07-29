"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { PRIMARY_NAVIGATION } from "@/lib/config/navigation";
import styles from "./PrimaryNavigation.module.css";

export function PrimaryNavigation() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <nav className={styles.nav} aria-label="Primary">
      <button
        type="button"
        className={styles.toggle}
        aria-expanded={open}
        aria-controls="primary-navigation-list"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="visually-hidden">{open ? "Close menu" : "Open menu"}</span>
        <span aria-hidden="true">{open ? "✕" : "☰"}</span>
      </button>
      <ul id="primary-navigation-list" className={`${styles.list} ${open ? styles.listOpen : ""}`}>
        {PRIMARY_NAVIGATION.map((item) => {
          const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link href={item.href} aria-current={isActive ? "page" : undefined} onClick={() => setOpen(false)}>
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
