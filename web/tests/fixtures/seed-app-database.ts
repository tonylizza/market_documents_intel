import { randomUUID } from "node:crypto";
import { Client } from "pg";
import { SEED_APP_DATABASE_URL } from "./env";

export interface SeededCompany {
  ticker: string;
  name: string;
  reportCount: number;
}

/** Matches the real corpus's report counts (see docs/frontend.md /
 * real-data validation) -- comparison_count is a clean N-1 here rather
 * than reproducing the real corpus's one known irregular-pairing case
 * (ACT), which is an upstream research-data fact, not something a test
 * fixture needs to replicate. */
export const SEEDED_COMPANIES: SeededCompany[] = [
  { ticker: "ACT", name: "Acme Test Holdings", reportCount: 9 },
  { ticker: "BEL", name: "Bellwether Test Ltd", reportCount: 7 },
  { ticker: "KP2", name: "Kappa Two Test Group", reportCount: 6 },
  { ticker: "SBP", name: "Sable Point Test Plc", reportCount: 3 },
  { ticker: "SDL", name: "Sundial Test Resources", reportCount: 2 },
  { ticker: "SUR", name: "Surrey Test Industries", reportCount: 3 },
];

const METRIC_CATALOG = [
  {
    metric_key: "disclosure_change_score",
    display_name: "Overall disclosure change",
    short_description: "How much a report's disclosures changed compared to the prior report.",
    technical_description: "Composite score over lexical/structural passage-alignment change classes.",
    unit: "score_0_1",
    direction_interpretation: "Higher means more change.",
    methodology_anchor: "Milestone 3/6",
  },
  {
    metric_key: "net_tone_change",
    display_name: "Net tone change",
    short_description: "Whether overall language tone became more positive or negative.",
    technical_description: "Change in (positive_rate - negative_rate) per 1,000 analyzed words.",
    unit: "rate_per_1000_words",
    direction_interpretation: "Positive means more positive tone.",
    methodology_anchor: "Milestone 6",
  },
  {
    metric_key: "uncertainty_intensity_change",
    display_name: "Uncertainty language change",
    short_description: "Whether uncertainty-related language increased or decreased.",
    technical_description: "Change in uncertainty-category dictionary hit rate per 1,000 words.",
    unit: "rate_per_1000_words",
    direction_interpretation: "Positive means more uncertainty language.",
    methodology_anchor: "Milestone 6",
  },
  {
    metric_key: "risk_language_introduction",
    display_name: "Risk language introduced",
    short_description: "How much new risk-related language was introduced.",
    technical_description: "Risk-category hits attributable to new/modified passage content.",
    unit: "rate_per_1000_words",
    direction_interpretation: "Higher means more newly introduced risk language.",
    methodology_anchor: "Milestone 6",
  },
  {
    metric_key: "risk_language_removal",
    display_name: "Risk language removed",
    short_description: "How much previously-present risk-related language was removed.",
    technical_description: "Risk-category hits attributable to removed passage content.",
    unit: "rate_per_1000_words",
    direction_interpretation: "Higher means more risk language removed.",
    methodology_anchor: "Milestone 6",
  },
  {
    metric_key: "governance_language_change",
    display_name: "Governance language change",
    short_description: "Change in governance-related language.",
    technical_description: "Change in custom-taxonomy governance-category rate per 1,000 words.",
    unit: "rate_per_1000_words",
    direction_interpretation: "Positive means more governance language.",
    methodology_anchor: "Milestone 6",
  },
  {
    metric_key: "financial_condition_language_change",
    display_name: "Financial condition language change",
    short_description: "Change in language describing financial condition.",
    technical_description: "Change in custom-taxonomy financial-condition rate per 1,000 words.",
    unit: "rate_per_1000_words",
    direction_interpretation: "Positive means more financial-condition language.",
    methodology_anchor: "Milestone 6",
  },
  {
    metric_key: "new_rate_words",
    display_name: "New disclosure share",
    short_description: "Share of the report that is entirely new disclosure content.",
    technical_description: "new_words / feature-eligible word totals.",
    unit: "share",
    direction_interpretation: "Higher means more new content.",
    methodology_anchor: "Milestone 3",
  },
];

function periodEnd(yearsAgoFromLatest: number): string {
  const latestYear = 2025;
  const year = latestYear - yearsAgoFromLatest;
  return `${year}-06-30`;
}

/**
 * Seeds `app.language_metrics` (report-side + alignment-change categories)
 * and a full six-status `app.passage_comparisons` set (including a real
 * `UNCHANGED` row -- never derived) for one comparison, so
 * `PostgresComparisonRepository` tests have real rows to read against.
 * Only called for ACT's latest comparison to keep seed time bounded.
 */
async function seedLanguageMetricsAndPassageComposition(
  client: Client,
  publicationId: string,
  companyId: string,
  comparisonId: string,
  earlierReportId: string,
  laterReportId: string,
): Promise<void> {
  const languageMetrics = [
    { scope: "report_side", population: "primary_narrative", category: "positive", earlier: 5.0, later: 6.5, change: 1.5 },
    { scope: "report_side", population: "primary_narrative", category: "negative", earlier: 4.0, later: 3.0, change: -1.0 },
    { scope: "report_side", population: "custom_taxonomy", category: "governance", earlier: 2.0, later: 2.4, change: 0.4 },
    { scope: "alignment_change", population: "primary_narrative_excl_ambiguous", category: "risk", earlier: null, later: null, change: null },
  ];
  for (const metric of languageMetrics) {
    await client.query(
      `INSERT INTO app.language_metrics
         (id, publication_id, report_comparison_id, metric_scope, population, category, subcategory,
          earlier_count, later_count, earlier_rate_per_1000, later_rate_per_1000, rate_change, absolute_rate_change,
          introduced_count, introduced_rate_per_1000, removed_count, removed_rate_per_1000, retained_count,
          negated_count, quality, primary_eligible)
       VALUES ($1, $2, $3, $4, $5, $6, NULL,
               10, 12, $7, $8, $9, $9,
               $10, $11, $12, $13, $14,
               0, 'GOOD', true)`,
      [
        randomUUID(),
        publicationId,
        comparisonId,
        metric.scope,
        metric.population,
        metric.category,
        metric.earlier,
        metric.later,
        metric.change,
        metric.scope === "alignment_change" ? 3 : null,
        metric.scope === "alignment_change" ? 1.2 : null,
        metric.scope === "alignment_change" ? 1 : null,
        metric.scope === "alignment_change" ? 0.4 : null,
        metric.scope === "alignment_change" ? 5 : null,
      ],
    );
  }

  interface PassageFixture {
    heading: string | null;
    text: string;
    passageType?: string;
    structuredContentCategory?: string | null;
    firstPage?: number;
    lastPage?: number;
  }

  async function insertPassage(reportId: string, index: number, fixture: PassageFixture): Promise<string> {
    const id = randomUUID();
    const wordCount = fixture.text.split(/\s+/).filter(Boolean).length;
    await client.query(
      `INSERT INTO app.passages
         (id, publication_id, source_passage_id, company_id, report_id, report_period_end,
          passage_index, first_page_number, last_page_number, heading, passage_type, text,
          word_count, structured_content_category, primary_narrative_eligible, feature_eligible)
       VALUES ($1, $2, $3, $4, $5, NULL, $6, $7, $8, $9, $10, $11,
               $12, $13, true, true)`,
      [
        id,
        publicationId,
        randomUUID(),
        companyId,
        reportId,
        index,
        fixture.firstPage ?? 1,
        fixture.lastPage ?? fixture.firstPage ?? 1,
        fixture.heading,
        fixture.passageType ?? "HEADING_WITH_BODY",
        fixture.text,
        wordCount,
        fixture.structuredContentCategory ?? null,
      ],
    );
    return id;
  }

  async function insertLanguageSignal(
    passageId: string,
    passageComparisonId: string,
    reportSide: "EARLIER" | "LATER",
    category: string,
    subcategory: string | null,
    rawCount: number,
    options: { introduced?: boolean; removed?: boolean; retained?: boolean } = {},
  ): Promise<void> {
    await client.query(
      `INSERT INTO app.passage_language_signals
         (id, publication_id, passage_id, passage_comparison_id, report_comparison_id, report_side,
          category, subcategory, raw_count, negated_count, adjusted_count, rate_per_1000,
          is_introduced, is_removed, is_retained)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 0, $9, $10, $11, $12, $13)`,
      [
        randomUUID(),
        publicationId,
        passageId,
        passageComparisonId,
        comparisonId,
        reportSide,
        category,
        subcategory,
        rawCount,
        rawCount > 0 ? rawCount * 4.0 : 0,
        options.introduced ?? false,
        options.removed ?? false,
        options.retained ?? false,
      ],
    );
  }

  // Real, distinct, searchable text -- deliberately reuses several of the
  // milestone's representative search terms (liquidity, going concern,
  // governance, remuneration, impairment, uncertainty, debt, climate) so
  // repository/lexical-search tests exercise `search_vector` against real
  // rows rather than a generic placeholder string repeated for every row.
  const earlierFixtures: PassageFixture[] = [
    {
      heading: "Liquidity and going concern",
      text: "The group maintains adequate liquidity headroom and there is no material uncertainty regarding going concern.",
    },
    {
      heading: "Governance framework",
      text: "The board governance framework was updated during the year to strengthen oversight of remuneration policy.",
    },
    {
      heading: "Impairment of assets",
      text: "An impairment charge was recognised following a detailed review of asset carrying values amid market uncertainty.",
    },
    {
      heading: "Debt covenant compliance",
      text: "The company remained in compliance with all debt covenants throughout the reporting period.",
    },
    {
      heading: null,
      text: "Climate related risks are considered as part of the enterprise risk assessment process.",
    },
  ];
  const laterFixtures: PassageFixture[] = [
    {
      heading: "Liquidity and going concern",
      text: "The group maintains adequate liquidity headroom and there is no material uncertainty regarding going concern outlook.",
    },
    {
      heading: "Governance framework and remuneration",
      text: "The board governance framework and remuneration committee mandate were both updated during the year to strengthen oversight.",
    },
    {
      heading: "Impairment and asset review",
      text: "A significant impairment charge was recognised after a comprehensive review of asset carrying values reflecting heightened market uncertainty and climate transition risk.",
      firstPage: 40,
      lastPage: 41,
    },
    {
      heading: "New disclosure on climate risk",
      text: "This year the group introduces expanded disclosure on climate related transition risk and physical risk exposure.",
    },
    {
      // Deliberately never referenced by any `alignments` entry below --
      // a real, published, report-only passage with no alignment at all
      // (see `PassageRepository.searchPassages`'s handling of a null
      // `passage_comparison_id`).
      heading: "Directors' report",
      text: "This section lists the standalone directors' report content for the current reporting period.",
    },
  ];

  // Sequential (not Promise.all) -- a single `pg.Client` connection can't
  // run concurrent queries.
  const earlierPassages: string[] = [];
  for (let index = 0; index < earlierFixtures.length; index += 1) {
    earlierPassages.push(await insertPassage(earlierReportId, index, earlierFixtures[index]));
  }
  const laterPassages: string[] = [];
  for (let index = 0; index < laterFixtures.length; index += 1) {
    laterPassages.push(await insertPassage(laterReportId, index, laterFixtures[index]));
  }

  const alignments: { status: string; earlier: string | null; later: string | null; collisionFlag?: boolean }[] = [
    { status: "UNCHANGED", earlier: earlierPassages[0], later: laterPassages[0] },
    { status: "LIGHTLY_MODIFIED", earlier: earlierPassages[1], later: laterPassages[1] },
    { status: "SUBSTANTIALLY_MODIFIED", earlier: earlierPassages[2], later: laterPassages[2], collisionFlag: true },
    { status: "NEW", earlier: null, later: laterPassages[3] },
    { status: "REMOVED", earlier: earlierPassages[3], later: null },
    { status: "AMBIGUOUS", earlier: earlierPassages[4], later: null },
  ];
  for (const alignment of alignments) {
    const passageComparisonId = randomUUID();
    await client.query(
      `INSERT INTO app.passage_comparisons
         (id, publication_id, source_alignment_id, report_comparison_id, earlier_passage_id, later_passage_id,
          alignment_status, alignment_type, confidence, confidence_label, collision_flag, split_merge_flag,
          primary_alignment, review_reason)
       VALUES ($1, $2, $3, $4, $5, $6, $7,
               'ONE_TO_ONE', 'HIGH', 'Strong attribution', $8, false, true, $9)`,
      [
        passageComparisonId,
        publicationId,
        randomUUID(),
        comparisonId,
        alignment.earlier,
        alignment.later,
        alignment.status,
        alignment.collisionFlag ?? false,
        alignment.status === "AMBIGUOUS" ? "Attribution uncertain -- only one side available" : null,
      ],
    );

    if (alignment.status === "UNCHANGED") {
      await insertLanguageSignal(alignment.earlier!, passageComparisonId, "EARLIER", "risk", "liquidity", 2, { retained: true });
      await insertLanguageSignal(alignment.later!, passageComparisonId, "LATER", "risk", "liquidity", 2, { retained: true });
      await insertLanguageSignal(alignment.earlier!, passageComparisonId, "EARLIER", "uncertainty", null, 1, { retained: true });
      await insertLanguageSignal(alignment.later!, passageComparisonId, "LATER", "uncertainty", null, 1, { retained: true });
    }
    if (alignment.status === "LIGHTLY_MODIFIED") {
      await insertLanguageSignal(alignment.earlier!, passageComparisonId, "EARLIER", "governance", "remuneration", 1, { retained: true });
      await insertLanguageSignal(alignment.later!, passageComparisonId, "LATER", "governance", "remuneration", 2, { introduced: true });
    }
    if (alignment.status === "SUBSTANTIALLY_MODIFIED") {
      await insertLanguageSignal(alignment.earlier!, passageComparisonId, "EARLIER", "uncertainty", null, 1, { retained: true });
      await insertLanguageSignal(alignment.later!, passageComparisonId, "LATER", "uncertainty", null, 2, { retained: true });
      await insertLanguageSignal(alignment.later!, passageComparisonId, "LATER", "risk", "climate_environmental", 1, { introduced: true });
    }
    if (alignment.status === "NEW") {
      await insertLanguageSignal(alignment.later!, passageComparisonId, "LATER", "risk", "climate_environmental", 2, { introduced: true });
    }
    if (alignment.status === "REMOVED") {
      await insertLanguageSignal(alignment.earlier!, passageComparisonId, "EARLIER", "financial_condition", "debt", 1, { removed: true });
    }
  }
}

/**
 * Truncates and repopulates the application schema in the dedicated
 * frontend test database (`market_documents_app_test`) with a small,
 * realistic-shaped fixture: 6 companies matching the real corpus's report
 * counts, consecutive comparisons (half GOOD-quality/primary-eligible, half
 * NEEDS_REVIEW/review-qualified -- both disclosure-change states this
 * milestone must render correctly), a metric catalog, and language-based
 * (never feature-gated) discovery items. Never touches the research
 * database or `market_documents_app` (the real local publication).
 */
export async function seedAppDatabase(): Promise<{ publicationId: string }> {
  const client = new Client({ connectionString: SEED_APP_DATABASE_URL });
  await client.connect();

  try {
    await client.query("BEGIN");

    await client.query(
      `TRUNCATE TABLE
         app.discovery_items,
         app.passage_language_signals,
         app.passage_comparisons,
         app.language_metrics,
         app.passages,
         app.report_comparisons,
         app.reports,
         app.companies,
         app.metric_label_thresholds,
         app.metric_definitions,
         app_internal.application_state,
         app_internal.publications
       RESTART IDENTITY CASCADE`,
    );

    const publicationId = randomUUID();
    await client.query(
      `INSERT INTO app_internal.publications
         (id, publication_version, source_database_identifier, source_schema_version,
          source_configuration_hash, status, started_at, completed_at, activated_at,
          company_count, report_count, comparison_count)
       VALUES ($1, 'test-fixture', 'postgresql://localhost/test', 'test', 'test-hash',
               'ACTIVE', now(), now(), now(), $2, $3, $4)`,
      [publicationId, SEEDED_COMPANIES.length, SEEDED_COMPANIES.reduce((n, c) => n + c.reportCount, 0), SEEDED_COMPANIES.reduce((n, c) => n + c.reportCount - 1, 0)],
    );

    await client.query(
      `INSERT INTO app_internal.application_state (singleton_key, active_publication_id, updated_at)
       VALUES ('active', $1, now())`,
      [publicationId],
    );

    for (const metric of METRIC_CATALOG) {
      await client.query(
        `INSERT INTO app.metric_definitions
           (id, publication_id, metric_key, display_name, short_description, technical_description,
            unit, direction_interpretation, methodology_anchor)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
        [
          randomUUID(),
          publicationId,
          metric.metric_key,
          metric.display_name,
          metric.short_description,
          metric.technical_description,
          metric.unit,
          metric.direction_interpretation,
          metric.methodology_anchor,
        ],
      );
    }

    let displayOrder = 0;
    for (const company of SEEDED_COMPANIES) {
      const companyId = randomUUID();
      const reportIds: string[] = [];

      // Inserted before reports/comparisons (both FK-reference company_id);
      // latest_comparison_id is backfilled via UPDATE once comparisons exist.
      await client.query(
        `INSERT INTO app.companies
           (id, publication_id, source_company_id, ticker, name, sector, description,
            first_report_period_end, latest_report_period_end, report_count, comparison_count,
            latest_comparison_id, historical_peak_comparison_id, display_order, has_current_data)
         VALUES ($1, $2, $3, $4, $5, NULL, NULL, $6, $7, $8, $9, NULL, NULL, $10, true)`,
        [
          companyId,
          publicationId,
          randomUUID(),
          company.ticker,
          company.name,
          periodEnd(company.reportCount - 1),
          periodEnd(0),
          company.reportCount,
          company.reportCount - 1,
          displayOrder,
        ],
      );

      for (let i = 0; i < company.reportCount; i += 1) {
        const reportId = randomUUID();
        reportIds.push(reportId);
        const yearsAgo = company.reportCount - 1 - i;
        await client.query(
          `INSERT INTO app.reports
             (id, publication_id, source_report_id, company_id, title, filename, directory_year,
              period_start, period_end, page_count, narrative_word_count,
              extraction_quality, extraction_quality_label, chronological_index)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'GOOD', 'Analysis ready', $12)`,
          [
            reportId,
            publicationId,
            randomUUID(),
            companyId,
            `${company.name} integrated annual report`,
            `${company.ticker.toLowerCase()}-${i}.pdf`,
            2025 - yearsAgo,
            null,
            periodEnd(yearsAgo),
            120,
            45000,
            i,
          ],
        );
      }

      let latestComparisonId: string | null = null;
      const comparisonCount = company.reportCount - 1;
      for (let i = 0; i < comparisonCount; i += 1) {
        const comparisonId = randomUUID();
        const isLatest = i === comparisonCount - 1;
        if (isLatest) latestComparisonId = comparisonId;
        // Alternate GOOD/primary-eligible vs NEEDS_REVIEW/review-qualified
        // comparisons -- both disclosure-change states must render.
        const reviewQualified = i % 2 === 0;
        const quality = reviewQualified ? "NEEDS_REVIEW" : "GOOD";
        const qualityLabel = reviewQualified ? "Review recommended" : "Analysis ready";
        const primaryEligible = !reviewQualified;
        const score = 0.2 + i * 0.05;
        const primaryFindingKey = primaryEligible ? "largest_uncertainty_increase" : null;
        // Mirrors the real publisher's `finding_payload` shape (see
        // `market_documents.publishing.publisher`): one `{value, magnitude}`
        // entry per eligible candidate, keyed by finding key, plus the
        // fixed diagnostics key -- never a bare/empty object when a finding
        // key is set, so `extractFindingPayloadEntry` has a real row to read.
        const findingPayload = JSON.stringify({
          ...(primaryFindingKey ? { [primaryFindingKey]: { value: 1.5, magnitude: 1.5 } } : {}),
          _disclosure_change_diagnostics: { score_available: true },
        });

        await client.query(
          `INSERT INTO app.report_comparisons
             (id, publication_id, source_report_pair_id, company_id, earlier_report_id, later_report_id,
              earlier_period_end, later_period_end, gap_months, chronological_index,
              is_transition, is_irregular_gap, is_latest_for_company, is_historical_peak_change,
              disclosure_change_score, disclosure_change_label, disclosure_change_percentile,
              disclosure_change_quality, disclosure_change_quality_label, disclosure_change_primary_eligible,
              disclosure_change_warning,
              net_tone_change, net_tone_change_label,
              uncertainty_change, uncertainty_change_label,
              risk_introduction_rate, risk_introduction_label,
              risk_removal_rate, risk_removal_label,
              governance_change, governance_change_label,
              financial_condition_change, financial_condition_change_label,
              report_side_quality, report_side_quality_label, report_side_primary_eligible, report_side_warning,
              alignment_change_quality, alignment_change_quality_label, alignment_change_primary_eligible, alignment_change_warning,
              dictionary_match_rate_earlier, dictionary_match_rate_later,
              ambiguous_word_share, collision_flagged_word_share, unmatched_word_share, structured_content_exclusion_share,
              primary_finding_key, secondary_finding_key, tertiary_finding_key, finding_payload)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 12, $9, false, false, $10, false,
                   $11, $12, $13, $14, $15, $16, $17,
                   -1.2, 'Moderate decrease',
                   1.5, 'Moderate increase',
                   2.1, 'Notable increase',
                   0.3, 'Minimal increase',
                   0.4, 'Minimal increase',
                   0.2, 'Minimal increase',
                   'GOOD', 'Analysis ready', true, NULL,
                   'USABLE', 'Usable attribution', true, NULL,
                   0.92, 0.93,
                   0.02, 0.01, 0.05, 0.1,
                   $18, NULL, NULL, $19)`,
          [
            comparisonId,
            publicationId,
            randomUUID(),
            companyId,
            reportIds[i],
            reportIds[i + 1],
            periodEnd(comparisonCount - i),
            periodEnd(comparisonCount - i - 1),
            i,
            isLatest,
            score,
            reviewQualified ? "Moderate change" : "Notable change",
            42.0,
            quality,
            qualityLabel,
            primaryEligible,
            reviewQualified ? "exclusion: feature quality is NEEDS_REVIEW" : null,
            primaryFindingKey,
            findingPayload,
          ],
        );

        if (isLatest) {
          // Language-based discovery items only -- never
          // largest_overall_change/largest_new_disclosure_share, matching
          // the real corpus's review-qualified suppression. Seeded across
          // all three `rank_scope` values and two types so
          // `PostgresDiscoveryRepository` tests can exercise type/scope
          // filtering against real rows.
          for (const scope of ["latest_comparisons", "corpus", "company_history"]) {
            await client.query(
              `INSERT INTO app.discovery_items
                 (id, publication_id, company_id, report_comparison_id, discovery_type, rank_scope,
                  score, rank, percentile, finding_key, supporting_metric_key, supporting_value,
                  supporting_unit, quality_label)
               VALUES ($1, $2, $3, $4, 'largest_uncertainty_increase', $5,
                       1.5, 1, 80.0, 'largest_uncertainty_increase', 'uncertainty_intensity_change', 1.5,
                       'rate_per_1000_words', 'Analysis ready')`,
              [randomUUID(), publicationId, companyId, comparisonId, scope],
            );
          }
          await client.query(
            `INSERT INTO app.discovery_items
               (id, publication_id, company_id, report_comparison_id, discovery_type, rank_scope,
                score, rank, percentile, finding_key, supporting_metric_key, supporting_value,
                supporting_unit, quality_label)
             VALUES ($1, $2, $3, $4, 'largest_risk_introduction', 'corpus',
                     2.1, 1, 90.0, 'largest_risk_introduction', 'risk_language_introduction', 2.1,
                     'rate_per_1000_words', 'Strong attribution')`,
            [randomUUID(), publicationId, companyId, comparisonId],
          );

          if (company.ticker === "ACT") {
            await seedLanguageMetricsAndPassageComposition(client, publicationId, companyId, comparisonId, reportIds[i], reportIds[i + 1]);
          }
        }
      }

      if (latestComparisonId) {
        await client.query(`UPDATE app.companies SET latest_comparison_id = $1 WHERE id = $2`, [
          latestComparisonId,
          companyId,
        ]);
      }
      displayOrder += 1;
    }

    await client.query("COMMIT");
    return { publicationId };
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    await client.end();
  }
}
