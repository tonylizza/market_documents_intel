import { z } from "zod";

export const qaChunkCandidateRowSchema = z.object({
  chunk_id: z.string(),
  report_id: z.string(),
  company_id: z.string(),
  chunk_index: z.number().int(),
  similarity: z.number(),
  text: z.string(),
  section_heading: z.string().nullable(),
  page_start: z.number().int(),
  page_end: z.number().int(),
  token_count: z.number().int(),
});

export type QaChunkCandidateRow = z.infer<typeof qaChunkCandidateRowSchema>;

export const qaChunkLexicalCandidateRowSchema = z.object({
  chunk_id: z.string(),
  rank: z.number().nullable(),
});

export type QaChunkLexicalCandidateRow = z.infer<typeof qaChunkLexicalCandidateRowSchema>;

export const qaChunkMemberPassageRowSchema = z.object({
  qa_chunk_id: z.string(),
  passage_id: z.string(),
});

export type QaChunkMemberPassageRow = z.infer<typeof qaChunkMemberPassageRowSchema>;

export const qaChunkCitationContextRowSchema = z.object({
  chunk_id: z.string(),
  company_id: z.string(),
  company_ticker: z.string(),
  company_name: z.string(),
  report_id: z.string(),
  report_title: z.string(),
  report_period_end: z.string().nullable(),
  page_start: z.number().int(),
  page_end: z.number().int(),
  section_heading: z.string().nullable(),
});

export type QaChunkCitationContextRow = z.infer<typeof qaChunkCitationContextRowSchema>;
