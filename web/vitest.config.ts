import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
      // `server-only`'s real package unconditionally throws unless resolved
      // through Next.js's bundler-specific server/client aliasing, which
      // Vitest has no equivalent of. Neutralized to a no-op for tests only
      // -- the real guard still applies in the actual Next.js build.
      "server-only": path.resolve(__dirname, "tests/mocks/server-only-noop.ts"),
    },
  },
  test: {
    // Default environment is Node (repository tests need a real `pg`
    // connection); component test files opt into jsdom individually via a
    // `// @vitest-environment jsdom` docblock at the top of the file.
    environment: "node",
    setupFiles: ["./tests/setup.ts"],
    globals: true,
    include: ["tests/**/*.test.{ts,tsx}"],
    // Production HTTP-status tests spawn a real `next build` + `next
    // start` (60-90s+) -- excluded from the default `pnpm test` run so the
    // ordinary unit/repository/component suite stays fast; run explicitly
    // via `pnpm test:production`.
    exclude: ["node_modules/**", "tests/production/**"],
    // Repository test files each call `seedAppDatabase()` (TRUNCATE +
    // re-INSERT) against the one shared `market_documents_app_test`
    // database in their own `beforeAll` -- running test *files* in
    // parallel lets two files' seed transactions interleave (one file's
    // TRUNCATE firing mid-read of another), which is a real correctness
    // bug, not a flaky test. Files run sequentially; tests within a file
    // still run in whatever order Vitest normally uses.
    fileParallelism: false,
  },
});
