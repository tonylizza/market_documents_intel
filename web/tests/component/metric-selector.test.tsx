/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/companies/ACT",
  useSearchParams: () => new URLSearchParams("comparison=cmp-1"),
}));

const { MetricSelector } = await import("@/components/MetricSelector");

describe("MetricSelector", () => {
  it("renders exactly the seven approved metric keys as tabs", () => {
    render(<MetricSelector selected="disclosure_change" />);
    expect(screen.getAllByRole("tab")).toHaveLength(7);
  });

  it("marks the selected metric with aria-selected", () => {
    render(<MetricSelector selected="uncertainty_change" />);
    expect(screen.getByRole("tab", { name: /Uncertainty change/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Disclosure change/ })).toHaveAttribute("aria-selected", "false");
  });

  it("preserves the existing comparison= query parameter while changing metric=", () => {
    render(<MetricSelector selected="disclosure_change" />);
    const tab = screen.getByRole("tab", { name: /Net tone change/ });
    expect(tab).toHaveAttribute("href", "/companies/ACT?comparison=cmp-1&metric=net_tone_change");
  });

  it("flags the exploratory (review-qualified) metric", () => {
    render(<MetricSelector selected="disclosure_change" />);
    expect(screen.getByText("Exploratory")).toBeInTheDocument();
  });
});
