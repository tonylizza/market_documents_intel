# JSE Integrated Annual Report Downloader

A configurable downloader for the ten JSE symbols:

`SUR, SBP, KP2, BEL, EOH, CLH, ART, SDL, ACT, ISA`

It supports:

- static archive pages
- predictable year-based URL patterns
- paginated WordPress archives
- hybrid archive/pattern discovery
- optional Playwright rendering for JavaScript-heavy sites
- intermediate HTML pages that link to the PDF
- PDF signature checks, SHA-256 hashes, page counts, and fiscal-year validation
- normalized local storage and a CSV manifest

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

EOH/iOCO and City Lodge are marked as JavaScript-rendered. Install the optional dependency:

```bash
pip install playwright
playwright install chromium
```

## Discover links without downloading

```bash
python download_reports.py --discover-only
```

The candidate URLs are written to:

```text
data/discovered_candidates.json
```

Review this file before the first bulk download. It is especially useful for identifying site-layout changes or an incorrect report type.

## Download all configured reports

```bash
python download_reports.py
```

Download a subset:

```bash
python download_reports.py --tickers SUR,SBP,BEL
```

Replace existing local files:

```bash
python download_reports.py --overwrite
```

## Output structure

```text
data/
  raw/
    SUR/
      2016/
        annual_report.pdf
      2017/
        annual_report.pdf
  report_manifest.csv
  discovered_candidates.json
```

The manifest records source URL, discovery method, remote filename, local path, SHA-256 hash, byte size, page count, years detected in the first five pages, and validation status.

## Important validation behavior

A report is saved when the response is a valid PDF. The downloader then checks whether the expected fiscal year appears in text extracted from the first five pages.

- `year_confirmed`: expected year was detected
- `year_not_confirmed`: PDF is valid, but the expected year was not found near the front
- `pdf_parse_error`: the file could not be parsed

`year_not_confirmed` is a review flag, not automatic rejection. Some reports place the fiscal year deeper in the document or use graphics on the cover.

## Adjusting a company rule

All site-specific behavior is in `companies.yaml`. For example, Sabvest uses both an archive and a URL template:

```yaml
- ticker: SBP
  discovery:
    method: hybrid
    archive_url: https://www.sabvestcapital.com/investment.php
    url_patterns:
      - https://www.sabvestcapital.com/pdf/{year}/AnnualReport.pdf
```

If a company changes its archive URL or naming convention, edit the YAML rather than the Python code.

## Known caveats

- Corporate websites change. Run `--discover-only` and review candidates before a large download.
- EOH/iOCO and City Lodge may require Playwright because their report lists are JavaScript-driven.
- Older reports can live on retired domains. Add them under `explicit_urls` when found.
- A corporate reorganization or name change may make reports textually incomparable even when the ticker is continuous. Preserve this information in your later analysis metadata.
- Respect each website's terms, robots policy, and rate limits. The default delay is one second between requests.
