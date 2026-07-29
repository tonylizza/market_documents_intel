import path from "node:path";
import { defineConfig } from "vitest/config";

/** Separate config for `pnpm test:production` -- only
 * `tests/production/**`, a much longer default timeout (real `next
 * build`/`next start` involved), and no jsdom/React plugin (these tests
 * only issue real `fetch` requests against a running server). */
export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "node",
    globals: true,
    include: ["tests/production/**/*.test.ts"],
    testTimeout: 60_000,
    hookTimeout: 300_000,
    fileParallelism: false,
  },
});
