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
        topicMixChange={0.0193}
        shareEarlier={0.29}
        shareLater={0.38}
        hitsEarlier={40}
        hitsLater={53}
        customTaxonomyHitsEarlier={138}
        customTaxonomyHitsLater={139}
        subcategoryMovers={[]}
      />,
    );
    expect(screen.getByText(/Governance language density change/)).toBeInTheDocument();
    expect(screen.getByText(/Topic-mix change \(M6-G\)/)).toBeInTheDocument();
    expect(screen.getByText(/Supporting detail only; no positive\/negative direction/)).toBeInTheDocument();
  });

  it("renders an empty state when there are no subcategory movers", () => {
    render(
      <GovernanceSupportingDetail
        languageDensityChange={null}
        topicMixChange={null}
        shareEarlier={null}
        shareLater={null}
        hitsEarlier={null}
        hitsLater={null}
        customTaxonomyHitsEarlier={null}
        customTaxonomyHitsLater={null}
        subcategoryMovers={[]}
      />,
    );
    expect(screen.getByText(/No subcategory detail available/)).toBeInTheDocument();
  });

  it("renders subcategory movers with hit counts, change, and share contributions", () => {
    render(
      <GovernanceSupportingDetail
        languageDensityChange={1.736}
        topicMixChange={0.0193}
        shareEarlier={0.29}
        shareLater={0.38}
        hitsEarlier={40}
        hitsLater={53}
        customTaxonomyHitsEarlier={138}
        customTaxonomyHitsLater={139}
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
        topicMixChange={0.02}
        shareEarlier={0.3}
        shareLater={0.36}
        hitsEarlier={30}
        hitsLater={36}
        customTaxonomyHitsEarlier={100}
        customTaxonomyHitsLater={100}
        subcategoryMovers={[makeMover({ id: "gov-litigation", subcategory: "litigation", lowVolume: true })]}
      />,
    );
    expect(screen.getByText(/low corpus-wide volume/)).toBeInTheDocument();
  });

  it("Track 7F.7a.1a: states the factual share/count decomposition (no 'changed little'/'own-volume' classification)", () => {
    render(
      <GovernanceSupportingDetail
        languageDensityChange={0.1}
        topicMixChange={0.03}
        shareEarlier={0.4037940379403794}
        shareLater={0.29444444444444445}
        hitsEarlier={131}
        hitsLater={106}
        customTaxonomyHitsEarlier={324}
        customTaxonomyHitsLater={360}
        subcategoryMovers={[]}
      />,
    );
    expect(
      screen.getByText(
        /Governance language represented 40\.4% of classified disclosure in the earlier report and 29\.4% in the later report\. Governance hits changed from 131 to 106, while total classified-language hits changed from 324 to 360\./,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/changed little/)).not.toBeInTheDocument();
    expect(screen.queryByText(/own-volume/)).not.toBeInTheDocument();
    expect(screen.queryByText(/share-relative/)).not.toBeInTheDocument();
  });

  it("Track 7F.7a.1a: when governance hits are exactly unchanged, attributes the share movement to other classified categories factually", () => {
    render(
      <GovernanceSupportingDetail
        languageDensityChange={0}
        topicMixChange={0.01}
        shareEarlier={0.4141791044776119}
        shareLater={0.5135135135135135}
        hitsEarlier={56}
        hitsLater={56}
        customTaxonomyHitsEarlier={135}
        customTaxonomyHitsLater={109}
        subcategoryMovers={[]}
      />,
    );
    expect(
      screen.getByText(/Governance hits did not change, so the share movement came from changes in other classified categories\./),
    ).toBeInTheDocument();
  });

  it("renders no decomposition text when share/hit-count data is unavailable", () => {
    render(
      <GovernanceSupportingDetail
        languageDensityChange={0.1}
        topicMixChange={0.03}
        shareEarlier={null}
        shareLater={null}
        hitsEarlier={null}
        hitsLater={null}
        customTaxonomyHitsEarlier={null}
        customTaxonomyHitsLater={null}
        subcategoryMovers={[]}
      />,
    );
    expect(screen.queryByText(/Governance language represented/)).not.toBeInTheDocument();
  });
});
