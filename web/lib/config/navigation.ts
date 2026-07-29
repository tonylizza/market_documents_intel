export interface NavigationItem {
  label: string;
  href: string;
}

/**
 * Only routes that actually exist. `Ask the Reports` is reserved for
 * Milestone 7B but must never appear here as a nonfunctional link -- see
 * `navigation.test.ts::navigation only includes implemented routes`.
 */
export const PRIMARY_NAVIGATION: readonly NavigationItem[] = [
  { label: "Companies", href: "/" },
  { label: "Discover", href: "/discover" },
  { label: "Passages", href: "/passages" },
  { label: "Methodology", href: "/methodology" },
];

/** Documented, not rendered -- reserved for a future milestone. */
export const RESERVED_NAVIGATION_LABELS: readonly string[] = ["Ask the Reports"];
