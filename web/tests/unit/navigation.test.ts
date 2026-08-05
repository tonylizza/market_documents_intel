import { describe, expect, it } from "vitest";
import { PRIMARY_NAVIGATION, RESERVED_NAVIGATION_LABELS } from "@/lib/config/navigation";

const IMPLEMENTED_ROUTES = new Set(["/", "/discover", "/passages", "/ask", "/methodology"]);

describe("PRIMARY_NAVIGATION", () => {
  it("only includes routes implemented so far", () => {
    for (const item of PRIMARY_NAVIGATION) {
      expect(IMPLEMENTED_ROUTES.has(item.href)).toBe(true);
    }
  });

  it("does not include any reserved (future-milestone) label", () => {
    const labels = PRIMARY_NAVIGATION.map((item) => item.label);
    for (const reserved of RESERVED_NAVIGATION_LABELS) {
      expect(labels).not.toContain(reserved);
    }
  });

  it("includes exactly Companies, Discover, Passages, Ask the Reports, and Methodology", () => {
    expect(PRIMARY_NAVIGATION.map((item) => item.label)).toEqual([
      "Companies",
      "Discover",
      "Passages",
      "Ask the Reports",
      "Methodology",
    ]);
  });

  it("does not link /evidence-review (Milestone 7B.1b's experimental analyst-review route)", () => {
    const hrefs = PRIMARY_NAVIGATION.map((item) => item.href);
    expect(hrefs).not.toContain("/evidence-review");
  });
});
