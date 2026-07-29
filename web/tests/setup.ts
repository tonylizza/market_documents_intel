import "@testing-library/jest-dom/vitest";
import { TEST_APP_READONLY_DATABASE_URL } from "./fixtures/env";

// jsdom implements neither ResizeObserver (needed by Recharts'
// ResponsiveContainer) nor IntersectionObserver (needed by
// AdaptiveComparisonNavigator's scrollable-mode visible-range tracking).
// No-op stubs are sufficient for component tests, which assert on rendered
// markup/accessible text, not on real layout/intersection geometry.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
if (typeof globalThis.IntersectionObserver === "undefined") {
  // @ts-expect-error -- minimal stub, not a full IntersectionObserver implementation
  globalThis.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// jsdom doesn't implement `Element.prototype.scrollIntoView` or
// `Element.prototype.scrollBy` (used by AdaptiveComparisonNavigator's
// scrollable mode) -- no-op stubs, since tests assert on markup/state, not
// real scroll geometry.
if (typeof Element !== "undefined") {
  if (typeof Element.prototype.scrollIntoView !== "function") {
    Element.prototype.scrollIntoView = () => {};
  }
  if (typeof Element.prototype.scrollBy !== "function") {
    Element.prototype.scrollBy = () => {};
  }
}

// jsdom doesn't implement `window.matchMedia` -- stub it to "no preference"
// so `prefers-reduced-motion` checks (AdaptiveComparisonNavigator's
// scroll-into-view behavior) don't throw in tests.
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

// Repository tests must connect to the dedicated frontend test database,
// never the developer's real local `market_documents_app` and never the
// research database. `pool.ts` reads `APP_READONLY_DATABASE_URL` lazily
// (only when a query actually runs), so setting it here -- before any test
// body executes -- is sufficient regardless of import order. Unit/component
// tests never call into `lib/db`, so this has no effect on them.
process.env.APP_READONLY_DATABASE_URL = TEST_APP_READONLY_DATABASE_URL;
