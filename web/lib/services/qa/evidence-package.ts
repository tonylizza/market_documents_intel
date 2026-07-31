import type {
  EvidenceCandidateSource,
  EvidenceCoherence,
  EvidencePackage,
  EvidenceSet,
  GateDecision,
  QaRerankerMethod,
  QueryAnalysis,
} from "@/lib/domain/qa-evidence";
import type { RetrievalMode } from "@/lib/domain/retrieval";

/**
 * Milestone 7B.1b: the stable, versioned evidence-package contract Milestone
 * 7B.2 (grounded Q&A) is meant to consume. Bump `EVIDENCE_SELECTION_VERSION`
 * whenever the selection/gate logic changes in a way a downstream consumer
 * should be able to detect. Never includes raw vectors or database
 * credentials -- only citation-ready, already-published fields.
 */
export const EVIDENCE_SELECTION_VERSION = "7b.1b.1";

export interface BuildEvidencePackageInput {
  publicationId: string | null;
  question: string;
  analysis: QueryAnalysis;
  gateDecision: GateDecision;
  evidenceSet: EvidenceSet;
  coherence: EvidenceCoherence;
  candidateCount: number;
  candidateSources: EvidenceCandidateSource[];
  retrievalMode: RetrievalMode | null;
  rerankerMethod: QaRerankerMethod;
  latencyMs: EvidencePackage["latencyMs"];
}

export function buildEvidencePackage(input: BuildEvidencePackageInput): EvidencePackage {
  const rejectedCounts = new Map<string, number>();
  for (const rejection of input.evidenceSet.rejected) {
    rejectedCounts.set(rejection.reason, (rejectedCounts.get(rejection.reason) ?? 0) + 1);
  }

  return {
    evidenceSelectionVersion: EVIDENCE_SELECTION_VERSION,
    publicationId: input.publicationId ?? "",
    question: input.question,
    normalizedQuestion: input.analysis.normalizedQuestion,
    queryAnalysis: input.analysis,
    gateStatus: input.gateDecision.status,
    gateReasonCodes: input.gateDecision.reasonCodes,
    selectedEvidence: input.evidenceSet.selected,
    rejectedEvidenceSummary: [...rejectedCounts.entries()].map(([reason, count]) => ({
      reason: reason as EvidencePackage["rejectedEvidenceSummary"][number]["reason"],
      count,
    })),
    coverage: input.evidenceSet.coverage,
    coherence: input.coherence,
    supportedSubquestions: input.gateDecision.supportedSubquestions,
    unsupportedSubquestions: input.gateDecision.unsupportedSubquestions,
    partialSupportRationale: input.gateDecision.partialSupportRationale,
    retrievalDiagnostics: {
      candidateCount: input.candidateCount,
      sources: input.candidateSources,
      retrievalMode: input.retrievalMode,
    },
    rerankerMethod: input.rerankerMethod,
    generatedAt: new Date().toISOString(),
    latencyMs: input.latencyMs,
  };
}
