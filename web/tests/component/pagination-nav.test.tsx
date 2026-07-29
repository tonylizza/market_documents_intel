/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PaginationNav } from "@/components/PaginationNav";
import type { PaginationState } from "@/lib/domain/passage";

function makePagination(overrides: Partial<PaginationState> = {}): PaginationState {
  return {
    page: 2,
    pageSize: 25,
    totalCount: 100,
    totalIsCapped: false,
    totalPages: 4,
    hasNextPage: true,
    hasPreviousPage: true,
    ...overrides,
  };
}

describe("PaginationNav", () => {
  it("renders nothing for a single-page result set", () => {
    const { container } = render(
      <PaginationNav pagination={makePagination({ totalPages: 1, hasNextPage: false, hasPreviousPage: false })} buildHref={(p) => `/x?page=${p}`} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("marks the current page with aria-current", () => {
    render(<PaginationNav pagination={makePagination()} buildHref={(p) => `/x?page=${p}`} />);
    expect(screen.getByRole("link", { name: "Page 2" })).toHaveAttribute("aria-current", "page");
  });

  it("disables Previous on the first page and Next on the last page", () => {
    render(<PaginationNav pagination={makePagination({ page: 1, hasPreviousPage: false })} buildHref={(p) => `/x?page=${p}`} />);
    expect(screen.getByRole("link", { name: "Previous page" })).toHaveAttribute("aria-disabled", "true");
  });

  it("provides an accessible label for the navigation landmark", () => {
    render(<PaginationNav pagination={makePagination()} buildHref={(p) => `/x?page=${p}`} label="My results" />);
    expect(screen.getByRole("navigation", { name: "My results" })).toBeInTheDocument();
  });

  it("builds hrefs via the caller-supplied function", () => {
    render(<PaginationNav pagination={makePagination()} buildHref={(p) => `/passages?page=${p}`} />);
    expect(screen.getByRole("link", { name: "Page 3" })).toHaveAttribute("href", "/passages?page=3");
  });
});
