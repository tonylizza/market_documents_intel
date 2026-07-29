import { describe, expect, it } from "vitest";
import { extractFindingPayloadEntry } from "@/lib/schemas/comparison";

describe("extractFindingPayloadEntry", () => {
  it("extracts a well-formed entry", () => {
    const payload = { largest_risk_introduction: { value: 2.4, magnitude: 2.4 } };
    expect(extractFindingPayloadEntry(payload, "largest_risk_introduction")).toEqual({ value: 2.4, magnitude: 2.4 });
  });

  it("returns null for a missing key rather than throwing -- a payload legitimately omits ineligible candidates", () => {
    expect(extractFindingPayloadEntry({}, "largest_risk_introduction")).toBeNull();
  });

  it("returns null for a null payload", () => {
    expect(extractFindingPayloadEntry(null, "largest_risk_introduction")).toBeNull();
  });

  it("returns null for a malformed entry (wrong shape), never a raw unvalidated value", () => {
    expect(extractFindingPayloadEntry({ largest_risk_introduction: "not-an-object" }, "largest_risk_introduction")).toBeNull();
    expect(extractFindingPayloadEntry({ largest_risk_introduction: { value: "bad" } }, "largest_risk_introduction")).toBeNull();
  });

  it("ignores the diagnostics key when looking up an ordinary finding key", () => {
    const payload = { _disclosure_change_diagnostics: { score_available: true } };
    expect(extractFindingPayloadEntry(payload, "largest_overall_change")).toBeNull();
  });
});
