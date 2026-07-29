import type { TextDiffResult, TextDiffSegment } from "@/lib/domain/passage";
import { MAX_DIFF_INPUT_LENGTH } from "@/lib/domain/passage";

/** LCS table cells beyond this are refused -- guards wall-clock/memory even
 * for two inputs that are each individually under `MAX_DIFF_INPUT_LENGTH`
 * but produce a large token cross-product (e.g. very short, very repetitive
 * words). `next()`'s caller falls back to unhighlighted original text. */
const MAX_DIFF_TABLE_CELLS = 4_000_000;

/** Splits text into alternating word/whitespace tokens (never
 * character-level) -- reconstructing `tokens.join("")` always recovers the
 * exact original text, so diffing never loses or alters a single
 * character, only classifies each token as equal/inserted/deleted. */
function tokenize(text: string): string[] {
  return text.match(/\S+|\s+/g) ?? [];
}

function computeLcsDiff(a: string[], b: string[]): { earlier: TextDiffSegment[]; later: TextDiffSegment[] } {
  const n = a.length;
  const m = b.length;
  const table: Uint32Array[] = new Array(n + 1);
  for (let i = 0; i <= n; i += 1) table[i] = new Uint32Array(m + 1);

  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      table[i][j] = a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }

  const earlierOps: { op: TextDiffSegment["op"]; text: string }[] = [];
  const laterOps: { op: TextDiffSegment["op"]; text: string }[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      earlierOps.push({ op: "equal", text: a[i] });
      laterOps.push({ op: "equal", text: b[j] });
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      earlierOps.push({ op: "delete", text: a[i] });
      i += 1;
    } else {
      laterOps.push({ op: "insert", text: b[j] });
      j += 1;
    }
  }
  while (i < n) {
    earlierOps.push({ op: "delete", text: a[i] });
    i += 1;
  }
  while (j < m) {
    laterOps.push({ op: "insert", text: b[j] });
    j += 1;
  }

  return { earlier: mergeConsecutive(earlierOps), later: mergeConsecutive(laterOps) };
}

function mergeConsecutive(ops: { op: TextDiffSegment["op"]; text: string }[]): TextDiffSegment[] {
  const merged: TextDiffSegment[] = [];
  for (const segment of ops) {
    const last = merged[merged.length - 1];
    if (last && last.op === segment.op) {
      last.text += segment.text;
    } else {
      merged.push({ op: segment.op, text: segment.text });
    }
  }
  return merged;
}

/**
 * Deterministic, presentation-only word-level diff between an earlier and
 * later passage text -- never mutates or reinterprets the analytical
 * alignment result, only decorates the two already-published strings for
 * display. Falls back to `diffed: false` (unhighlighted original text, both
 * sides as single `equal` segments) for exceptionally large passages,
 * rather than freezing the browser/server on an oversized diff.
 */
export function buildTextDiff(earlierText: string, laterText: string): TextDiffResult {
  if (earlierText.length > MAX_DIFF_INPUT_LENGTH || laterText.length > MAX_DIFF_INPUT_LENGTH) {
    return {
      earlier: [{ op: "equal", text: earlierText }],
      later: [{ op: "equal", text: laterText }],
      diffed: false,
    };
  }

  const earlierTokens = tokenize(earlierText);
  const laterTokens = tokenize(laterText);

  if (earlierTokens.length * laterTokens.length > MAX_DIFF_TABLE_CELLS) {
    return {
      earlier: [{ op: "equal", text: earlierText }],
      later: [{ op: "equal", text: laterText }],
      diffed: false,
    };
  }

  const { earlier, later } = computeLcsDiff(earlierTokens, laterTokens);
  return { earlier, later, diffed: true };
}
