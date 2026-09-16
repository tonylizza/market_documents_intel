import "server-only";

/**
 * Track 7A.3/7A.4: the live caller's own copy of
 * `SEMANTIC_COMPARISON_CUTOVER_ENABLED` -- deliberately the *same* env var
 * name as the Python publishing side
 * (`market_documents.config.Settings.semantic_comparison_cutover_enabled`),
 * not an independent flag (per the 7A.3/7A.4 task's "do not introduce
 * another independent cutover flag" rule).
 *
 * Publishing always computes and persists Track 7C.6 narrative/structured
 * comparison rows for in-scope report comparisons, regardless of this
 * flag's value at publish time (see `cutover_publishing.py`). This flag is
 * what makes the *live caller* prefer those persisted rows over the legacy
 * `app.report_comparisons` fields -- flipping it is a Vercel/`.env` change
 * only, requires no republish and no database change, and is read fresh on
 * every request (no caching), so rollback is immediate.
 */
export function isCutoverEnabled(): boolean {
  return process.env.SEMANTIC_COMPARISON_CUTOVER_ENABLED === "true";
}
