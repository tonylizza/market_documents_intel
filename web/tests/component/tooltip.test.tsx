/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tooltip } from "@/components/Tooltip";

describe("Tooltip", () => {
  it("is reachable and openable by keyboard focus alone, not only hover", async () => {
    const user = userEvent.setup();
    render(<Tooltip content="Helper text" triggerLabel="More information" />);

    const trigger = screen.getByRole("button", { name: "More information" });
    const tooltip = screen.getByRole("tooltip", { hidden: true });
    expect(tooltip.className).not.toContain("open");

    await user.tab();
    expect(trigger).toHaveFocus();
    expect(tooltip.className).toContain("open");
  });

  it("the content is always linked via aria-describedby regardless of open state", () => {
    render(<Tooltip content="Helper text" triggerLabel="More information" />);
    const trigger = screen.getByRole("button", { name: "More information" });
    const describedBy = trigger.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent("Helper text");
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    render(<Tooltip content="Helper text" triggerLabel="More information" />);
    const trigger = screen.getByRole("button", { name: "More information" });
    const tooltip = screen.getByRole("tooltip", { hidden: true });

    await user.tab();
    expect(tooltip.className).toContain("open");

    await user.keyboard("{Escape}");
    expect(trigger).toBeInTheDocument();
    expect(tooltip.className).not.toContain("open");
  });
});
