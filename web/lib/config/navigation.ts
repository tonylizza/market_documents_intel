export interface NavigationItem {
  label: string;
  href: string;
}

/** Only routes that actually exist -- see `navigation.test.ts`. */
export const PRIMARY_NAVIGATION: readonly NavigationItem[] = [
  { label: "Companies", href: "/" },
  { label: "Discover", href: "/discover" },
  { label: "Passages", href: "/passages" },
  { label: "Ask the Reports", href: "/ask" },
  { label: "Methodology", href: "/methodology" },
];

/** Documented, not rendered -- reserved for a future milestone. */
export const RESERVED_NAVIGATION_LABELS: readonly string[] = [];
