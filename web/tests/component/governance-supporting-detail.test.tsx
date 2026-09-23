/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { GovernanceSupportingDetail } from "@/components/GovernanceSupportingDetail";
import type { GovernanceSubcategoryMover } from "@/lib/services/comparison-service";

function makeMover(overrides: Partial<GovernanceSubcategoryMover> = {}): GovernanceSubcategoryMover {
  return {
    id: "gov-board",
    subcategory: "board",
    earlierCount: 10,
    laterCount: 20,
    change: 10,
    earlierShareContribution: 0.4,
    laterShareContribution: 0.5,
    lowVolume: false,
    ...overrides,
  };
}

describe("GovernanceSupportingDetail", () => {
  it("renders M1-G density and M6-G topic-mix change as supporting, non-ranking detail", () => {
    render(
      <GovernanceSupportingDetail
        languageDensityChange={1.736}
        shareChange={0.0865}
        topicMixChange={0.0193}
        subcategoryMovers={[]}
      />,
    );
    expect(screen.getByText(/Governance language density change/)).toBeInTheDocument();
    expect(screen.getByText(/Topic-mix change \(M6-G\)/)).toBeInTheDocument();
    expect(screen.getByText(/Supporting detail only; no positive\/negative direction/)).toBeInTheDocument();
  });

  it("renders an empty state when there are no subcategory movers", () => {
    render(<GovernanceSupportingDetail languageDensityChange={null} shareChange={null} topicMixChange={null} subcategoryMovers={[]} />);
    expect(screen.getByText(/No subcategory detail available/)).toBeInTheDocument();
  });

  it("renders subcategory movers with hit counts, change, and share contributions", () => {
    render(
      <GovernanceSupportingDetail
        languageDensityChange={1.736}
        shareChange={0.0865}
        topicMixChange={0.0193}
        subcategoryMovers={[makeMover()]}
      />,
    );
    const row = screen.getByText("Board").closest("tr")!;
    expect(row.textContent).toContain("10");
    expect(row.textContent).toContain("20");
    expect(row.textContent).toContain("+10");
  });

  it("flags a low-volume subcategory (litigation/shareholder_rights) with a cautionary note", () => {
    render(
      <GovernanceSupportingDetail
        languageDensityChange={0.1}
        shareChange={0.06}
        topicMixChange={0.02}
        subcategoryMovers={[makeMover({ id: "gov-litigation", subcategory: "litigation", lowVolume: true })]}
      />,
    );
    expect(screen.getByText(/low corpus-wide volume/)).toBeInTheDocument();
  });

  it("Track 7F.7a.1 item 9: shows the share-relative interpretation when M3-G is material but M1-G is small (share-relative movement)", () => {
    render(
      <GovernanceSupportingDetail languageDensityChange={0.1} shareChange={-0.09} topicMixChange={0.03} subcategoryMovers={[]} />,
    );
    expect(
      screen.getByText(/Governance language itself changed little, but its share of classified disclosure moved/),
    ).toBeInTheDocument();
  });

  it("Track 7F.7a.1 item 9: shows the own-volume interpretation when M1-G is large and consistent with M3-G", () => {
    render(
      <GovernanceSupportingDetail languageDensityChange={1.7} shareChange={0.09} topicMixChange={0.03} subcategoryMovers={[]} />,
    );
    expect(screen.getByText(/own volume moved in a direction consistent with its share change/)).toBeInTheDocument();
  });

  it("shows no interpretation text when M3-G is below materiality", () => {
    render(
      <GovernanceSupportingDetail languageDensityChange={0.1} shareChange={0.02} topicMixChange={0.03} subcategoryMovers={[]} />,
    );
    expect(screen.queryByText(/Governance language itself changed little/)).not.toBeInTheDocument();
    expect(screen.queryByText(/own volume moved in a direction consistent/)).not.toBeInTheDocument();
  });
});
