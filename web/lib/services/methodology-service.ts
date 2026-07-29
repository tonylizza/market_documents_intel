import type { MethodologyRepository } from "@/lib/repositories/methodology-repository";
import type { MetricDefinition } from "@/lib/domain/metric";
import type { ApplicationDataSummary } from "@/lib/domain/metric";
import { METHODOLOGY_SECTIONS, NON_INVESTMENT_ADVICE_STATEMENT, type MethodologySectionContent } from "@/lib/content/methodology-sections";

export interface MethodologyPageViewModel {
  sections: MethodologySectionContent[];
  metrics: MetricDefinition[];
  summary: ApplicationDataSummary;
  nonInvestmentAdviceStatement: string;
}

export async function getMethodologyPageViewModel(repository: MethodologyRepository): Promise<MethodologyPageViewModel> {
  const { metrics, summary } = await repository.getMethodologyContentData();
  return {
    sections: METHODOLOGY_SECTIONS,
    metrics,
    summary,
    nonInvestmentAdviceStatement: NON_INVESTMENT_ADVICE_STATEMENT,
  };
}
