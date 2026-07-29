"use client";

import { useId, useState, type ReactNode } from "react";
import styles from "./Tooltip.module.css";

export interface TooltipProps {
  content: string;
  children?: ReactNode;
  /** Accessible label for the trigger when no children are supplied. */
  triggerLabel?: string;
}

/**
 * Keyboard- and screen-reader-accessible helper text -- opens on hover
 * *and* focus (never hover-only), dismissible with Escape, and always
 * linked via `aria-describedby` so the content is available to assistive
 * technology regardless of the trigger's current visual open/closed state.
 */
export function Tooltip({ content, children, triggerLabel = "More information" }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const tooltipId = useId();

  return (
    <span className={styles.wrapper}>
      <button
        type="button"
        className={styles.trigger}
        aria-describedby={tooltipId}
        aria-label={children ? undefined : triggerLabel}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
      >
        {children ?? "?"}
      </button>
      <span role="tooltip" id={tooltipId} className={`${styles.bubble} ${open ? styles.open : ""}`}>
        {content}
      </span>
    </span>
  );
}
