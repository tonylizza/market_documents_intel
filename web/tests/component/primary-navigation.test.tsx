/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

const { PrimaryNavigation } = await import("@/components/PrimaryNavigation");

describe("PrimaryNavigation", () => {
  it("renders only the implemented routes", () => {
    render(<PrimaryNavigation />);
    expect(screen.getByRole("link", { name: "Companies" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Discover" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Passages" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Methodology" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Ask the Reports" })).not.toBeInTheDocument();
  });

  it("marks the active route with aria-current", () => {
    render(<PrimaryNavigation />);
    expect(screen.getByRole("link", { name: "Companies" })).toHaveAttribute("aria-current", "page");
  });

  it("the mobile menu toggle expands and collapses the link list", async () => {
    const user = userEvent.setup();
    render(<PrimaryNavigation />);

    const toggle = screen.getByRole("button", { name: /open menu/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    await user.click(screen.getByRole("button", { name: /close menu/i }));
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
});
