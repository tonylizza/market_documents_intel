/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { GateStatusBanner } from "@/components/GateStatusBanner";

describe("GateStatusBanner", () => {
  it("renders a plain-language label for SUPPORTED", () => {
    render(<GateStatusBanner status="SUPPORTED" reasonCodes={["SUPPORTED_BY_SINGLE_PASSAGE"]} />);
    expect(screen.getByText("Supported by the evidence below")).toBeInTheDocument();
    expect(screen.getByText("Supported by a single passage.")).toBeInTheDocument();
  });

  it("renders a plain-language label for INSUFFICIENT_EVIDENCE", () => {
    render(<GateStatusBanner status="INSUFFICIENT_EVIDENCE" reasonCodes={["NO_DIRECT_EVIDENCE"]} />);
    expect(screen.getByText("Not enough evidence to answer")).toBeInTheDocument();
  });

  it("renders a plain-language label for AMBIGUOUS_OR_CONFLICTING", () => {
    render(<GateStatusBanner status="AMBIGUOUS_OR_CONFLICTING" reasonCodes={["CONFLICTING_EVIDENCE"]} />);
    expect(screen.getByText("Evidence is ambiguous or conflicting")).toBeInTheDocument();
  });

  it("renders a plain-language label for PARTIALLY_SUPPORTED", () => {
    render(<GateStatusBanner status="PARTIALLY_SUPPORTED" reasonCodes={["INSUFFICIENT_TOPIC_COVERAGE"]} />);
    expect(screen.getByText("Only partially supported")).toBeInTheDocument();
  });

  it("never renders a raw gate reason code verbatim", () => {
    render(<GateStatusBanner status="INSUFFICIENT_EVIDENCE" reasonCodes={["NO_DIRECT_EVIDENCE", "ONLY_WEAK_INDIRECT_EVIDENCE"]} />);
    expect(screen.queryByText("NO_DIRECT_EVIDENCE")).not.toBeInTheDocument();
    expect(screen.queryByText("ONLY_WEAK_INDIRECT_EVIDENCE")).not.toBeInTheDocument();
  });

  it("renders every supplied reason code's plain-language explanation", () => {
    render(<GateStatusBanner status="PARTIALLY_SUPPORTED" reasonCodes={["INSUFFICIENT_TOPIC_COVERAGE", "LOW_RELEVANCE_MARGIN"]} />);
    expect(screen.getByText(/only covers part of what the question asked/)).toBeInTheDocument();
    expect(screen.getByText(/barely above the threshold/)).toBeInTheDocument();
  });

  it("renders no reason list when no reason codes are supplied", () => {
    render(<GateStatusBanner status="SUPPORTED" reasonCodes={[]} />);
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });

  it("exposes an accessible status role for the banner", () => {
    render(<GateStatusBanner status="SUPPORTED" reasonCodes={[]} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
