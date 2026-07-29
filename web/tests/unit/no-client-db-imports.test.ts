import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "../..");
const SCAN_DIRS = ["app", "components"];

function collectSourceFiles(dir: string): string[] {
  const entries = readdirSync(dir);
  const files: string[] = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      files.push(...collectSourceFiles(fullPath));
    } else if (/\.(ts|tsx)$/.test(entry)) {
      files.push(fullPath);
    }
  }
  return files;
}

describe("no Client Component imports a server-only database module", () => {
  const files = SCAN_DIRS.flatMap((dir) => collectSourceFiles(path.join(ROOT, dir)));

  it("scanned at least one file (sanity check the scan itself works)", () => {
    expect(files.length).toBeGreaterThan(0);
  });

  for (const file of files) {
    const relative = path.relative(ROOT, file);
    const content = readFileSync(file, "utf-8");
    const isClientComponent = /^["']use client["'];?\s*$/m.test(content);

    if (isClientComponent) {
      it(`${relative} (a Client Component) does not import lib/db`, () => {
        expect(content).not.toMatch(/from ["']@\/lib\/db/);
      });
    }
  }
});
