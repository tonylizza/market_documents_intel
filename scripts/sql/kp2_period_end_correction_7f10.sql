-- Track 7F.10: KP2 period-end correction (research database, LOCAL only).
--
-- Report data/raw/KP2/2025/annual_report.pdf (sha256 3bcf6f68572a...) is the
-- FY2025 annual report, not FY2024. Evidence (docs/fresh-neon-cutover-prep-7f10.md
-- section 9): cover p.1 "ANNUAL REPORT FOR THE FINANCIAL YEAR ENDED 31 DECEMBER
-- 2025"; p.92 "STATEMENTS OF PROFIT OR LOSS ... FOR THE YEAR ENDED 31 DECEMBER
-- 2025" (columns Dec 2025 / Dec 2024); p.93 "STATEMENTS OF FINANCIAL POSITION AS
-- AT 31 DECEMBER 2025"; Directors' Report signed 24 March 2026 (p.37); BDO LLP
-- audit opinion dated 24 March 2026 (p.91); PDF creation date 2026-03-24.
--
-- The 2026-07-17 manual note ("corrected period_end from 2025-12-31 to
-- 2024-12-31") cites no page and is contradicted by every one of the above.
-- The FY2024 report (published ~March 2025) is genuinely absent from the corpus.
--
-- Effect: the only affected pair (KP2 FY2023 -> this report) keeps its identity
-- (same earlier/later report ids, same ordering) but its gap becomes 24 months.
-- It is NOT a transition period (12-month December year ends on both sides), so
-- is_transition stays false; the irregular gap is flagged by the pipeline's own
-- gap rules. Downstream reruns for that pair only (similarity, alignment,
-- features, language signals) follow separately with --force.
--
-- Guarded: aborts unless the rows are exactly in the expected pre-correction
-- state, so it can never be re-applied or applied to a different database.

\set ON_ERROR_STOP on
BEGIN;

DO $$
DECLARE
    n integer;
BEGIN
    SELECT count(*) INTO n FROM reports
    WHERE id = '6727add6-a49e-45ee-8153-74bc358cea76'
      AND local_path = 'data/raw/KP2/2025/annual_report.pdf'
      AND sha256 LIKE '3bcf6f68572a%'
      AND period_end = DATE '2024-12-31'
      AND metadata_status = 'VALIDATED';
    IF n <> 1 THEN
        RAISE EXCEPTION 'KP2 report not in expected pre-correction state (matched % rows)', n;
    END IF;

    SELECT count(*) INTO n FROM report_pairs
    WHERE id = '393f45ef-e61e-47f4-8ea5-f299cb518d79'
      AND earlier_report_id = '8ac44907-16b3-41be-b0aa-a2047f51d366'
      AND later_report_id = '6727add6-a49e-45ee-8153-74bc358cea76'
      AND gap_months = 12;
    IF n <> 1 THEN
        RAISE EXCEPTION 'KP2 pair not in expected pre-correction state (matched % rows)', n;
    END IF;

    -- No other KP2 report may already hold 2025-12-31 (uq_reports_company_period_end).
    SELECT count(*) INTO n FROM reports r
    WHERE r.company_id = (SELECT company_id FROM reports WHERE id = '6727add6-a49e-45ee-8153-74bc358cea76')
      AND r.period_end = DATE '2025-12-31';
    IF n <> 0 THEN
        RAISE EXCEPTION 'another KP2 report already has period_end 2025-12-31';
    END IF;
END $$;

UPDATE reports
SET period_end = DATE '2025-12-31',
    validation_notes = validation_notes || E'\n'
        || 'Track 7F.10 correction (CONFIRMED_2025): period_end 2024-12-31 -> 2025-12-31. '
        || 'Evidence: cover p.1 "FINANCIAL YEAR ENDED 31 DECEMBER 2025"; p.92 income statement '
        || '"FOR THE YEAR ENDED 31 DECEMBER 2025" (Dec 2025 vs Dec 2024 comparatives); p.93 '
        || '"STATEMENTS OF FINANCIAL POSITION AS AT 31 DECEMBER 2025"; Directors'' Report signed '
        || '24 March 2026 (p.37); BDO audit opinion dated 24 March 2026 (p.91). Supersedes the '
        || '2026-07-17 note, which cited no page. FY2024 report is not in the corpus.',
    updated_at = now()
WHERE id = '6727add6-a49e-45ee-8153-74bc358cea76';

UPDATE report_pairs
SET gap_months = 24,
    updated_at = now()
WHERE id = '393f45ef-e61e-47f4-8ea5-f299cb518d79';

COMMIT;
