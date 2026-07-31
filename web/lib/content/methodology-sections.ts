export interface MethodologySectionContent {
  id: string;
  title: string;
  paragraphs: string[];
  /** Optional, more technical detail rendered inside a collapsed
   * `<details>` (`TechnicalDetails`) rather than inline prose. */
  technicalDetails?: string[];
}

/**
 * Stable, version-controlled explanatory prose -- the "static" half of the
 * hybrid methodology page. Metric names/units/short definitions come from
 * `app.metric_definitions` instead (see `methodology-service.ts`); corpus
 * counts come from `app.current_*` views. Nothing here should duplicate
 * data the database already owns.
 */
export const METHODOLOGY_SECTIONS: MethodologySectionContent[] = [
  {
    id: "what-the-tool-analyzes",
    title: "What the tool analyzes",
    paragraphs: [
      "This tool analyzes consecutive pairs of integrated annual reports filed by JSE-listed companies, " +
        "measuring how the language and structure of disclosures change from one report to the next.",
      "It surfaces document-level change scores, passage-level additions and removals, and financial-language " +
        "signals such as tone, uncertainty, and risk-language shifts -- always with an explicit statement of how " +
        "confident the underlying analysis is.",
    ],
  },
  {
    id: "corpus-and-report-pairing",
    title: "Corpus and report pairing",
    paragraphs: [
      "Reports are identified by company and fiscal period end, not by fiscal-year label alone, since the same " +
        "label can refer to different periods across companies or years.",
      "Only consecutive, validated reports for the same company are paired for comparison. Irregular reporting " +
        "gaps and transition periods are flagged explicitly rather than silently absorbed into the comparison.",
      "Company history and comparison charts always use each report's actual period-end date, never an assumed " +
        "one-report-per-year cadence or an evenly spaced index -- two companies with the same nominal fiscal year " +
        "can have different actual period-end dates, and a gap between two reports is never assumed to be exactly " +
        "12 months.",
    ],
  },
  {
    id: "text-extraction-and-narrative-construction",
    title: "Text extraction and narrative construction",
    paragraphs: [
      "Each report's native PDF text is extracted page by page, with repeated headers/footers and page-number " +
        "artifacts identified and excluded from the narrative text used for analysis.",
      "Extraction quality is assessed per report and factors into every downstream confidence assessment -- a " +
        "poorly-extracted report never silently produces a confident-looking result.",
    ],
  },
  {
    id: "document-level-change-measurement",
    title: "Document-level change measurement",
    paragraphs: [
      "Before passages are individually compared, whole-document lexical and structural similarity is measured " +
        "between the earlier and later report, giving a coarse baseline for how much the document changed overall.",
    ],
  },
  {
    id: "passage-alignment",
    title: "Passage alignment",
    paragraphs: [
      "Each report is segmented into passages, and passages are aligned between the earlier and later report using " +
        "a combination of semantic embedding similarity, lexical similarity, and position -- classifying each " +
        "passage as unchanged, lightly modified, substantially modified, new, removed, or ambiguous.",
      "A passage that cannot be matched with adequate confidence is marked ambiguous rather than forced into an " +
        "uncertain match -- alignment confidence is tracked and published alongside every comparison.",
    ],
  },
  {
    id: "financial-language-characterization",
    title: "Financial-language characterization",
    paragraphs: [
      "Passage text is scored against the Loughran-McDonald financial-language dictionary (positive, negative, " +
        "uncertainty, litigious, constraining, and modal-strength categories) plus a custom taxonomy covering risk, " +
        "financial condition, governance, and strategy language.",
      "Category rates are computed per 1,000 analyzed words, and changes are measured both by simple earlier-vs-" +
        "later rate comparison and by attributing specific introduced/removed language to specific passages.",
    ],
  },
  {
    id: "report-side-versus-alignment-change-analysis",
    title: "Report-side versus alignment-change analysis",
    paragraphs: [
      "Two independent questions are asked of every comparison: how did the report's language read on its own " +
        "terms in each period (report-side), and how confidently can a specific change be attributed to a specific " +
        "passage correspondence (alignment-change)? These are scored, labeled, and published separately, and one " +
        "can be usable while the other is not.",
    ],
  },
  {
    id: "quality-labels",
    title: "Quality labels",
    paragraphs: [
      "Every analytical output carries an explicit, plain-language quality label rather than being presented as " +
        "uniformly reliable. Three independent quality dimensions exist, each with its own vocabulary:",
    ],
    technicalDetails: [
      "Report-side quality -- how reliable the report's own language measurement is: Analysis ready, Ready with " +
        "caution, Review recommended, or Unavailable.",
      "Alignment-change quality -- how reliable the passage-to-passage attribution is: Strong attribution, Usable " +
        "attribution, Attribution uncertain, or Attribution unavailable.",
      "Disclosure-change quality -- the same four-tier vocabulary as report-side quality, applied to the overall " +
        "disclosure-change score specifically. A review-qualified score is still shown, with its quality label " +
        "displayed alongside it, but is excluded from primary discovery rankings and never presented as a headline " +
        "finding until it clears a stricter, independently-tracked eligibility bar.",
    ],
  },
  {
    id: "discovery-rankings",
    title: "Discovery rankings",
    paragraphs: [
      "The Discover page ranks comparisons within one category at a time -- largest uncertainty increase, " +
        "negative-tone shift, risk introduced, risk removed, governance shift, or financial-condition shift -- " +
        "never a single opaque score blending unrelated signals together.",
      "Each ranking is gated on the one quality dimension that actually governs it (report-side or " +
        "alignment-change), and ties are broken deterministically rather than arbitrarily. A category with zero " +
        "currently eligible items is omitted from the page entirely rather than shown empty; the two feature-" +
        "quality-gated rankings (largest overall disclosure change, largest new-disclosure share) are absent for " +
        "this reason in the current corpus.",
    ],
  },
  {
    id: "structured-content-handling",
    title: "Structured-content handling",
    paragraphs: [
      "Passages that are tables, lists, captions, or extraction artifacts are classified separately from ordinary " +
        "narrative prose. Only passages that are unreadable extraction artifacts are excluded from publication " +
        "entirely -- tables, lists, and similar structured content are still published as real, searchable " +
        "passages, with eligibility flags carrying the analytical nuance rather than the passage being hidden.",
    ],
  },
  {
    id: "publication-model",
    title: "Publication model",
    paragraphs: [
      "Analytical results are computed in a separate research pipeline and published into this application's own " +
        "read-only database as an atomic, versioned snapshot. The application always reads the single currently " +
        "active publication -- never a mix of old and new results, and never a partially-built one.",
    ],
  },
  {
    id: "passage-search",
    title: "Passage search",
    paragraphs: [
      "The Passages page supports three search modes: Keyword, Semantic, and Hybrid. Keyword search uses " +
        "PostgreSQL's conventional full-text search -- it does not understand meaning or synonyms beyond ordinary " +
        "English stemming (e.g. \"disclosed\" matching \"disclosure\"). Semantic search finds passages with similar " +
        "meaning even when the wording differs, using a sentence-embedding model. Hybrid search combines both " +
        "using reciprocal rank fusion. Keyword is the default mode; Semantic and Hybrid are available but did not " +
        "outperform Keyword on this corpus in evaluation (see below), so they are offered as clearly labeled " +
        "additional modes rather than the default.",
      "A passage's heading is weighted above its body text in Keyword search, so a keyword appearing in a heading " +
        "ranks a result higher than the same keyword appearing only in body text. Structured filters (company, " +
        "report period, alignment status, confidence, financial-language category, and others) apply identically " +
        "across all three modes and are all based on the same published, controlled classifications used elsewhere " +
        "in this application -- never an invented or free-text value.",
      "An empty search with no filters is never used to dump the entire corpus at once; a search or at least one " +
        "filter is required before results are shown (Semantic and Hybrid additionally require an actual search " +
        "term -- structured filters alone cannot be ranked by meaning).",
    ],
  },
  {
    id: "semantic-and-hybrid-retrieval",
    title: "Semantic and hybrid retrieval",
    paragraphs: [
      "Semantic search uses BAAI/bge-small-en-v1.5, a compact, locally-run sentence-embedding model, to turn each " +
        "published passage and each search query into a 384-dimensional vector, then ranks passages by vector " +
        "similarity (cosine distance) rather than shared literal words.",
      "Exactly one vector is stored per published passage, never one per report comparison. Roughly two-thirds of " +
        "passages in this corpus are the later side of one comparison and the earlier side of the next, so the " +
        "same passage can be a valid search result in more than one comparison context. Rather than duplicate the " +
        "vector, each valid comparison-side interpretation is expanded at search time into its own \"retrieval " +
        "context\" -- the highest-ranked context for a passage is shown first, and any other valid comparison " +
        "contexts for the same passage are available through an \"also appears in\" expander rather than being " +
        "silently dropped or duplicated as separate results.",
      "Both exact (mathematically precise) and HNSW (approximate, indexed) vector search are implemented. Exact " +
        "search is the correctness baseline. Measured against the real corpus (see the Milestone 7B.1 report), " +
        "HNSW matched exact search's recall exactly while running noticeably faster, so HNSW is the current " +
        "default -- exact search remains available as a diagnostic/benchmark reference.",
      "Semantic similarity is a relative ranking signal, not a probability, confidence percentage, or proof of a " +
        "factual relationship between the query and the result. A weak-match notice is shown when no result clears " +
        "a similarity floor calibrated from real evaluation data (the gap between queries with a known good answer " +
        "and queries about topics genuinely absent from this corpus) -- results are still shown below that floor, " +
        "just without an implied confident match.",
      "Roughly half of this corpus is very short (heading fragments, running headers, table labels), and raw " +
        "cosine similarity alone tends to rank these highly despite carrying little substantive meaning. Semantic " +
        "results are re-ranked using deterministic, corpus-derived passage-quality signals -- word count, whether " +
        "the passage's text is essentially just its own heading, whether the heading repeats across the corpus as " +
        "a structural label rather than a distinguishing title, and whether the passage carries a published " +
        "financial-language signal -- to bound down (never zero out) the ranking of low-substance fragments. A " +
        "genuinely short but financially dense passage is never penalized for its length: the underlying raw " +
        "similarity score is always preserved and shown separately from this adjustment, and the technical " +
        "details for any result show a plain-language reason whenever an adjustment was applied.",
      "No large-language-model calls, generated answers, or generated summaries are involved anywhere in this " +
        "retrieval process -- every result is a real, published passage excerpt, never model-generated text. " +
        "Query text is sent only to a locally-hosted embedding service under this application's own control, never " +
        "to an external or third-party AI provider.",
    ],
    technicalDetails: [
      "Retrieval evaluation: an 83-case, version-controlled evaluation dataset spanning direct keyword, phrase, " +
        "semantic-paraphrase, filter-sensitive, comparison-status, repeated-passage, weak-match, no-answer, and " +
        "short-passage (both genuinely substantive and known heading-fragment traps) query types was run against " +
        "the real corpus across five configurations (keyword, semantic-exact, semantic-HNSW, hybrid-exact, " +
        "hybrid-HNSW), each compared before and after the passage-quality re-ranking described above. Keyword " +
        "search had the strongest overall recall and nDCG@10 both before and after re-ranking, so it remains the " +
        "default; Hybrid and Semantic are retained as explicitly labeled alternative modes. Re-ranking measurably " +
        "reduced the rate of irrelevant short fragments occupying top-5 semantic results without regressing " +
        "recall on any evaluated query type; it did not change which mode is the default.",
      "Weak-match threshold: recalibrated from a 50-case real-similarity sample (10 no-answer, 40 answerable " +
        "queries). The two distributions overlap substantially at this corpus's short-fragment density, so no " +
        "similarity threshold cleanly separates them -- the shipped floor is set to never wrongly suppress a " +
        "genuinely answerable query, which means a minority of no-answer queries can still appear as a weak but " +
        "present match rather than being reliably flagged as unanswerable.",
    ],
  },
  {
    id: "comparison-evidence-and-passage-detail",
    title: "Comparison evidence and passage detail",
    paragraphs: [
      "Each report-comparison page links to a full evidence list of every passage alignment behind that " +
        "comparison's language and disclosure-change measurements, organized by alignment status and filterable " +
        "by confidence and category.",
      "Every passage comparison also has its own detail page showing the complete published text on each " +
        "available side. New and removed passages show only the one side that exists, clearly labeled; a passage " +
        "whose attribution is ambiguous shows whichever side is available with an explicit note that attribution " +
        "is uncertain -- text is never fabricated for a side that has no published passage.",
    ],
  },
  {
    id: "text-difference-highlighting",
    title: "Text-difference highlighting",
    paragraphs: [
      "When both an earlier and later passage are available, the detail page shows a word-level highlighted " +
        "difference between the two texts, as a reading aid only. This highlighting is generated entirely in the " +
        "browser/server presentation layer by comparing the two already-published strings -- it never changes, " +
        "recomputes, or feeds back into the underlying alignment status, confidence, or similarity scores, and no " +
        "passage text is ever sent to an external service to produce it.",
      "An unhighlighted \"Show original text\" view is always available, and an exceptionally long passage falls " +
        "back to unhighlighted text automatically rather than risk freezing the page.",
    ],
  },
  {
    id: "passage-language-signals",
    title: "Passage-level language signals",
    paragraphs: [
      "The same financial-language categories described above are also published at the individual passage level, " +
        "grouped by report side and by category/subcategory, with raw, adjusted, and negated counts. Where a " +
        "passage participates in an alignment, each category is also flagged as introduced, removed, or retained " +
        "relative to its aligned counterpart.",
      "Only the signal rows for the passage being viewed are ever loaded -- never the full corpus-wide signal " +
        "table -- and a category with no published rate for a given passage is shown as not available rather than " +
        "assumed to be zero.",
    ],
  },
  {
    id: "future-grounded-qa",
    title: "Future grounded question-answering",
    paragraphs: [
      "Grounded question-answering (asking a natural-language question and receiving a generated answer with " +
        "citations) is planned for a later milestone and is not available yet -- this application never generates " +
        "answers, summaries, or findings today. This application also does not provide a PDF viewer or document " +
        "downloads -- all evidence is shown as extracted, published passage text.",
    ],
  },
  {
    id: "limitations",
    title: "Limitations",
    paragraphs: [
      "This corpus currently covers a small number of companies and reporting periods, and coverage varies by " +
        "company. Some comparisons span irregular reporting gaps or transition periods, which are flagged but " +
        "still shown. Overall disclosure-change scores in the current corpus are all review-qualified: real values " +
        "are shown, but with an explicit recommendation to treat them as provisional rather than a primary ranking " +
        "signal, until a future recalibration clears them for primary use.",
    ],
  },
];

export const NON_INVESTMENT_ADVICE_STATEMENT =
  "This tool is a research and disclosure-analysis aid. It does not provide investment advice or " +
  "recommendations, and none of its outputs -- including quality labels, magnitude labels, or discovery " +
  "rankings -- should be interpreted as predictive of future financial performance.";
