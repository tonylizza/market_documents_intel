/**
 * Track 7A.3/7A.4: domain types for the Track 7C.6 cutover comparison
 * results published into `app.current_narrative_unit_comparisons` /
 * `app.current_structured_table_comparisons`. Read verbatim from the
 * database -- never recomputed -- mirroring `domain/comparison.ts`'s own
 * convention. See docs/7a3-7a4-live-comparison-integration.md.
 */

export type ComparisonResponseStatus =
  | "RESOLVED"
  | "UNRESOLVED_UPSTREAM"
  | "AMBIGUOUS"
  | "REVIEW_REQUIRED"
  | "NOT_AVAILABLE";

export interface ProvenanceRef {
  reportId: string;
  directoryYear: number;
  startPage: number;
  endPage: number | null;
  sourceBlockIds: string[];
  sourceExcerpt: string | null;
}

export interface LexicalMetrics {
  tfidfCosine: number | null;
  unigramJaccard: number | null;
  bigramJaccard: number | null;
  editSimilarity: number | null;
  sequenceSimilarity: number | null;
  wordCountChange: number | null;
  wordCountChangePct: number | null;
}

export interface NarrativeUnitComparison {
  comparisonBackend: "SEMANTIC_UNIT";
  status: ComparisonResponseStatus;
  schedule: string;
  unitKey: string;
  alignmentStatus: string | null;
  alignmentConfidence: string | null;
  analyticalMode: string | null;
  lexicalMetrics: LexicalMetrics | null;
  earlierWordCount: number | null;
  laterWordCount: number | null;
  earlierProvenance: ProvenanceRef | null;
  laterProvenance: ProvenanceRef | null;
  reviewReason: string | null;
}

export interface StructuredRowAlignment {
  earlierRowIdentity: string | null;
  laterRowIdentity: string | null;
  status: string;
  confidence: string;
  evidence: string;
}

export interface StructuredColumnAlignment {
  normalizedKey: string | null;
  isRestated: boolean;
  status: string;
  comparabilityStatus: string;
}

export interface StructuredValueChangeEvent {
  rowIdentity: string | null;
  columnNormalizedKey: string | null;
  eventType: string;
  earlierRawValue: string | null;
  laterRawValue: string | null;
  earlierNumeric: number | null;
  laterNumeric: number | null;
  absoluteChange: number | null;
  pctChange: number | null;
}

export interface StructuredTableComparison {
  comparisonBackend: "STRUCTURED_TABLE";
  status: ComparisonResponseStatus;
  tableFamilyKey: string;
  rowAlignments: StructuredRowAlignment[];
  columnAlignments: StructuredColumnAlignment[];
  valueChangeEvents: StructuredValueChangeEvent[];
  footnotes: string[];
  earlierProvenance: ProvenanceRef | null;
  laterProvenance: ProvenanceRef | null;
  reviewReason: string | null;
}
