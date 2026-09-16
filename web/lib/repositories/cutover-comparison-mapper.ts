import type {
  LexicalMetrics,
  NarrativeUnitComparison,
  ProvenanceRef,
  StructuredTableComparison,
} from "@/lib/domain/cutover-comparison";
import type { NarrativeUnitComparisonRow, StructuredTableComparisonRow } from "@/lib/schemas/cutover-comparison";

function mapProvenance(
  data:
    | {
        report_id: string;
        directory_year: number;
        start_page: number;
        end_page: number | null;
        source_block_ids: string[];
        source_excerpt: string | null;
      }
    | null,
): ProvenanceRef | null {
  if (data === null) return null;
  return {
    reportId: data.report_id,
    directoryYear: data.directory_year,
    startPage: data.start_page,
    endPage: data.end_page,
    sourceBlockIds: data.source_block_ids,
    sourceExcerpt: data.source_excerpt,
  };
}

function mapLexicalMetrics(
  data:
    | {
        tfidf_cosine: number | null;
        unigram_jaccard: number | null;
        bigram_jaccard: number | null;
        edit_similarity: number | null;
        sequence_similarity: number | null;
        word_count_change: number | null;
        word_count_change_pct: number | null;
      }
    | null,
): LexicalMetrics | null {
  if (data === null) return null;
  return {
    tfidfCosine: data.tfidf_cosine,
    unigramJaccard: data.unigram_jaccard,
    bigramJaccard: data.bigram_jaccard,
    editSimilarity: data.edit_similarity,
    sequenceSimilarity: data.sequence_similarity,
    wordCountChange: data.word_count_change,
    wordCountChangePct: data.word_count_change_pct,
  };
}

export function mapNarrativeUnitComparisonRow(data: NarrativeUnitComparisonRow): NarrativeUnitComparison {
  return {
    comparisonBackend: data.comparison_backend,
    status: data.status,
    schedule: data.schedule,
    unitKey: data.unit_key,
    alignmentStatus: data.alignment_status,
    alignmentConfidence: data.alignment_confidence,
    analyticalMode: data.analytical_mode,
    lexicalMetrics: mapLexicalMetrics(data.lexical_metrics),
    earlierWordCount: data.earlier_word_count,
    laterWordCount: data.later_word_count,
    earlierProvenance: mapProvenance(data.earlier_provenance),
    laterProvenance: mapProvenance(data.later_provenance),
    reviewReason: data.review_reason,
  } satisfies NarrativeUnitComparison;
}

export function mapStructuredTableComparisonRow(data: StructuredTableComparisonRow): StructuredTableComparison {
  return {
    comparisonBackend: data.comparison_backend,
    status: data.status,
    tableFamilyKey: data.table_family_key,
    rowAlignments: data.row_alignments.map((ra) => ({
      earlierRowIdentity: ra.earlier_row_identity,
      laterRowIdentity: ra.later_row_identity,
      status: ra.status,
      confidence: ra.confidence,
      evidence: ra.evidence,
    })),
    columnAlignments: data.column_alignments.map((ca) => ({
      normalizedKey: ca.normalized_key,
      isRestated: ca.is_restated,
      status: ca.status,
      comparabilityStatus: ca.comparability_status,
    })),
    valueChangeEvents: data.value_change_events.map((ev) => ({
      rowIdentity: ev.row_identity,
      columnNormalizedKey: ev.column_normalized_key,
      eventType: ev.event_type,
      earlierRawValue: ev.earlier_raw_value,
      laterRawValue: ev.later_raw_value,
      earlierNumeric: ev.earlier_numeric,
      laterNumeric: ev.later_numeric,
      absoluteChange: ev.absolute_change,
      pctChange: ev.pct_change,
    })),
    footnotes: data.footnotes,
    earlierProvenance: mapProvenance(data.earlier_provenance),
    laterProvenance: mapProvenance(data.later_provenance),
    reviewReason: data.review_reason,
  } satisfies StructuredTableComparison;
}
