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
      "The Passages page searches every published passage using PostgreSQL's conventional, keyword-based full-text " +
        "search -- it is not semantic or AI-generated retrieval, and it does not understand meaning or synonyms " +
        "beyond ordinary English stemming (e.g. \"disclosed\" matching \"disclosure\").",
      "A passage's heading is weighted above its body text, so a keyword appearing in a heading ranks a result " +
        "higher than the same keyword appearing only in body text. Structured filters (company, report period, " +
        "alignment status, confidence, financial-language category, and others) are all based on the same " +
        "published, controlled classifications used elsewhere in this application -- never an invented or " +
        "free-text value.",
      "An empty search with no filters is never used to dump the entire corpus at once; a search or at least one " +
        "filter is required before results are shown.",
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
    id: "future-semantic-retrieval",
    title: "Future semantic retrieval",
    paragraphs: [
      "Semantic, meaning-based retrieval and grounded question-answering over the corpus are planned for a later " +
        "milestone and are not available yet. This application also does not provide a PDF viewer or document " +
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
