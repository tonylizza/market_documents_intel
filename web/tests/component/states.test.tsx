/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { LoadingSkeleton } from "@/components/LoadingSkeleton";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";

describe("LoadingSkeleton", () => {
  it("renders a status role for assistive technology", () => {
    render(<LoadingSkeleton label="Loading companies" />);
    expect(screen.getByRole("status", { name: "Loading companies" })).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("renders an alert role with a plain-language message, never a stack trace", () => {
    render(<ErrorState />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).not.toMatch(/at\s+\S+\.(ts|tsx|js):\d+/);
    expect(alert.textContent).toContain("temporarily unavailable");
  });
});

describe("EmptyState", () => {
  it("renders a status role with title and description", () => {
    render(<EmptyState title="No companies" description="Check back later." />);
    expect(screen.getByRole("status")).toHaveTextContent("No companies");
    expect(screen.getByRole("status")).toHaveTextContent("Check back later.");
  });
});
