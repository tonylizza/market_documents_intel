from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from pypdf import PdfReader

PDF_MAGIC = b"%PDF"
YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; JSE-IAR-Downloader/1.0; "
        "+https://github.com/your-account/jse-iar-downloader)"
    )
}


@dataclass(frozen=True)
class Candidate:
    ticker: str
    company_name: str
    fiscal_year: int
    url: str
    source_page: str
    link_text: str
    discovery_method: str
    priority: int


@dataclass
class ManifestRecord:
    ticker: str
    company_name: str
    fiscal_year: int
    source_page: str
    source_url: str
    remote_filename: str
    local_path: str
    sha256: str
    bytes_downloaded: int
    page_count: int | None
    detected_years: str
    discovery_method: str
    validation_status: str
    status: str
    error: str


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_years(value: str, start_year: int, end_year: int) -> list[int]:
    years = []
    for match in YEAR_RE.findall(value or ""):
        year = int(match)
        if start_year <= year <= end_year:
            years.append(year)
    return sorted(set(years))


def matches_any(value: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, value) for pattern in patterns)


def looks_like_pdf_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith(".pdf") or ".pdf/" in path


def fetch_html_requests(session: requests.Session, url: str, timeout: int) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def fetch_html_playwright(url: str, timeout: int) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "This archive requires JavaScript. Install Playwright with: "
            "pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
        html = page.content()
        browser.close()
    return html


def extract_candidates_from_html(
    *,
    html: str,
    source_page: str,
    ticker: str,
    company_name: str,
    method: str,
    include_patterns: list[str],
    exclude_patterns: list[str],
    start_year: int,
    end_year: int,
    priority: int,
) -> list[Candidate]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[Candidate] = []

    for anchor in soup.find_all("a", href=True):
        href = urljoin(source_page, anchor.get("href", ""))
        link_text = normalize_text(anchor.get_text(" ", strip=True))
        context = normalize_text(
            " ".join(
                filter(
                    None,
                    [
                        link_text,
                        unquote(href),
                        anchor.parent.get_text(" ", strip=True) if anchor.parent else "",
                    ],
                )
            )
        )

        if not matches_any(context, include_patterns):
            continue
        if exclude_patterns and matches_any(context, exclude_patterns):
            continue

        years = extract_years(context, start_year, end_year)
        if not years:
            continue

        # Some archive links open an intermediate HTML post. Keep them; the
        # resolver will follow one level and find the actual PDF.
        candidates.append(
            Candidate(
                ticker=ticker,
                company_name=company_name,
                fiscal_year=years[-1],
                url=href,
                source_page=source_page,
                link_text=link_text,
                discovery_method=method,
                priority=priority,
            )
        )

    return candidates


def resolve_intermediate_page(
    session: requests.Session,
    candidate: Candidate,
    include_patterns: list[str],
    exclude_patterns: list[str],
    timeout: int,
) -> Candidate:
    if looks_like_pdf_url(candidate.url):
        return candidate

    try:
        html = fetch_html_requests(session, candidate.url, timeout)
    except requests.RequestException:
        return candidate

    soup = BeautifulSoup(html, "html.parser")
    possible: list[tuple[int, str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(candidate.url, anchor["href"])
        text = normalize_text(anchor.get_text(" ", strip=True))
        context = normalize_text(f"{text} {unquote(href)}")
        if not looks_like_pdf_url(href):
            continue
        if exclude_patterns and matches_any(context, exclude_patterns):
            continue
        score = 0
        if matches_any(context, include_patterns):
            score += 10
        if str(candidate.fiscal_year) in context:
            score += 5
        possible.append((score, href, text))

    if not possible:
        return candidate

    possible.sort(reverse=True)
    _, href, text = possible[0]
    return Candidate(
        **{**asdict(candidate), "url": href, "link_text": text or candidate.link_text}
    )


def discover_company(
    session: requests.Session,
    company: dict[str, Any],
    start_year: int,
    end_year: int,
    timeout: int,
) -> list[Candidate]:
    ticker = company["ticker"].upper()
    name = company["company_name"]
    discovery = company["discovery"]
    method = discovery["method"]
    include_patterns = discovery.get("include_patterns", [r"(?i)annual report"])
    exclude_patterns = discovery.get("exclude_patterns", [])
    candidates: list[Candidate] = []

    if method in {"archive_page", "hybrid", "paginated_archive"}:
        archive_urls: list[str] = []
        archive_url = discovery.get("archive_url")
        if archive_url:
            archive_urls.append(archive_url)

        if method == "paginated_archive":
            pattern = discovery["page_url_pattern"]
            max_pages = int(discovery.get("max_pages", 10))
            archive_urls.extend(pattern.format(page=page) for page in range(2, max_pages + 1))

        for page_index, source_page in enumerate(archive_urls):
            try:
                if discovery.get("render_javascript", False):
                    html = fetch_html_playwright(source_page, timeout)
                else:
                    html = fetch_html_requests(session, source_page, timeout)
            except Exception as exc:
                print(f"[{ticker}] archive fetch failed: {source_page}: {exc}")
                continue

            found = extract_candidates_from_html(
                html=html,
                source_page=source_page,
                ticker=ticker,
                company_name=name,
                method=method,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                start_year=start_year,
                end_year=end_year,
                priority=10 - min(page_index, 9),
            )
            candidates.extend(found)

    if method in {"url_pattern", "hybrid"}:
        for pattern_index, pattern in enumerate(discovery.get("url_patterns", [])):
            for year in range(start_year, end_year + 1):
                candidates.append(
                    Candidate(
                        ticker=ticker,
                        company_name=name,
                        fiscal_year=year,
                        url=pattern.format(year=year),
                        source_page=discovery.get("archive_url", pattern),
                        link_text=f"Annual Report {year}",
                        discovery_method="url_pattern",
                        priority=100 - pattern_index,
                    )
                )

    for year_text, url in discovery.get("explicit_urls", {}).items():
        year = int(year_text)
        if start_year <= year <= end_year:
            candidates.append(
                Candidate(
                    ticker=ticker,
                    company_name=name,
                    fiscal_year=year,
                    url=url,
                    source_page=url,
                    link_text=f"Annual Report {year}",
                    discovery_method="explicit_url",
                    priority=200,
                )
            )

    resolved = [
        resolve_intermediate_page(
            session, c, include_patterns, exclude_patterns, timeout
        )
        for c in candidates
    ]

    # Deduplicate and keep the highest-priority candidate per year/url.
    unique: dict[tuple[int, str], Candidate] = {}
    for candidate in resolved:
        key = (candidate.fiscal_year, candidate.url)
        current = unique.get(key)
        if current is None or candidate.priority > current.priority:
            unique[key] = candidate
    return list(unique.values())


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def inspect_pdf(content: bytes, expected_year: int) -> tuple[int | None, list[int], str]:
    temp_path = Path(".jse_iar_temp.pdf")
    try:
        temp_path.write_bytes(content)
        reader = PdfReader(str(temp_path))
        page_count = len(reader.pages)
        text_parts: list[str] = []
        for page in reader.pages[: min(5, page_count)]:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                continue
        preview = normalize_text(" ".join(text_parts))
        detected = sorted(set(int(x) for x in YEAR_RE.findall(preview)))
        status = "year_confirmed" if expected_year in detected else "year_not_confirmed"
        return page_count, detected, status
    except Exception as exc:
        return None, [], f"pdf_parse_error:{exc}"
    finally:
        temp_path.unlink(missing_ok=True)


def download_candidate(
    session: requests.Session,
    candidate: Candidate,
    output_dir: Path,
    timeout: int,
    overwrite: bool,
) -> ManifestRecord:
    destination = output_dir / candidate.ticker / str(candidate.fiscal_year) / "annual_report.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)

    base = ManifestRecord(
        ticker=candidate.ticker,
        company_name=candidate.company_name,
        fiscal_year=candidate.fiscal_year,
        source_page=candidate.source_page,
        source_url=candidate.url,
        remote_filename=unquote(Path(urlparse(candidate.url).path).name),
        local_path=str(destination),
        sha256="",
        bytes_downloaded=0,
        page_count=None,
        detected_years="",
        discovery_method=candidate.discovery_method,
        validation_status="not_checked",
        status="",
        error="",
    )

    if destination.exists() and not overwrite:
        content = destination.read_bytes()
        page_count, detected, validation = inspect_pdf(content, candidate.fiscal_year)
        base.sha256 = sha256_bytes(content)
        base.bytes_downloaded = len(content)
        base.page_count = page_count
        base.detected_years = ";".join(map(str, detected))
        base.validation_status = validation
        base.status = "already_exists"
        return base

    try:
        response = session.get(candidate.url, timeout=timeout, allow_redirects=True)
        if response.status_code == 404:
            base.status = "not_found"
            return base
        response.raise_for_status()
        content = response.content
        content_type = response.headers.get("Content-Type", "").lower()
        if not content.startswith(PDF_MAGIC) and "application/pdf" not in content_type:
            base.status = "not_pdf"
            base.error = f"content_type={content_type}"
            return base

        page_count, detected, validation = inspect_pdf(content, candidate.fiscal_year)
        destination.write_bytes(content)
        base.sha256 = sha256_bytes(content)
        base.bytes_downloaded = len(content)
        base.page_count = page_count
        base.detected_years = ";".join(map(str, detected))
        base.validation_status = validation
        base.status = "downloaded"
        return base
    except Exception as exc:
        base.status = "error"
        base.error = str(exc)
        return base


def choose_best_by_year(candidates: list[Candidate]) -> dict[int, list[Candidate]]:
    by_year: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        by_year.setdefault(candidate.fiscal_year, []).append(candidate)
    for year in by_year:
        by_year[year].sort(key=lambda c: c.priority, reverse=True)
    return by_year


def write_manifest(records: list[ManifestRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(ManifestRecord.__annotations__)
    with path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(record) for record in records)


def write_discovery_log(candidates: list[Candidate], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(candidate) for candidate in candidates], indent=2),
        encoding="utf-8",
    )


def run(config_path: Path, tickers: set[str] | None, overwrite: bool, discover_only: bool) -> int:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    study = config["study"]
    start_year = int(study["start_year"])
    end_year = int(study["end_year"])
    timeout = int(study.get("timeout_seconds", 60))
    delay = float(study.get("request_delay_seconds", 1.0))
    output_dir = Path(study.get("output_dir", "data/raw"))
    manifest_path = Path(study.get("manifest_path", "data/report_manifest.csv"))

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    all_candidates: list[Candidate] = []
    records: list[ManifestRecord] = []

    companies = config["companies"]
    if tickers:
        companies = [c for c in companies if c["ticker"].upper() in tickers]

    for company in companies:
        ticker = company["ticker"].upper()
        print(f"\n[{ticker}] discovering reports...")
        candidates = discover_company(session, company, start_year, end_year, timeout)
        all_candidates.extend(candidates)
        by_year = choose_best_by_year(candidates)
        print(f"[{ticker}] found candidates for {len(by_year)} fiscal years")

        if discover_only:
            continue

        for year in range(start_year, end_year + 1):
            year_candidates = by_year.get(year, [])
            if not year_candidates:
                records.append(
                    ManifestRecord(
                        ticker=ticker,
                        company_name=company["company_name"],
                        fiscal_year=year,
                        source_page=company["discovery"].get("archive_url", ""),
                        source_url="",
                        remote_filename="",
                        local_path="",
                        sha256="",
                        bytes_downloaded=0,
                        page_count=None,
                        detected_years="",
                        discovery_method=company["discovery"]["method"],
                        validation_status="not_checked",
                        status="not_discovered",
                        error="",
                    )
                )
                continue

            # Try candidates in priority order until one returns a PDF.
            selected_record: ManifestRecord | None = None
            for candidate in year_candidates:
                print(f"[{ticker}] {year}: trying {candidate.url}")
                record = download_candidate(session, candidate, output_dir, timeout, overwrite)
                if record.status in {"downloaded", "already_exists"}:
                    selected_record = record
                    break
                selected_record = record
                time.sleep(delay)
            assert selected_record is not None
            records.append(selected_record)
            time.sleep(delay)

    write_discovery_log(all_candidates, Path("data/discovered_candidates.json"))
    if not discover_only:
        write_manifest(records, manifest_path)
        print(f"\nManifest: {manifest_path}")
    print("Discovery log: data/discovered_candidates.json")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download JSE integrated annual reports")
    parser.add_argument("--config", type=Path, default=Path("companies.yaml"))
    parser.add_argument("--tickers", help="Comma-separated ticker subset, e.g. SUR,SBP")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tickers = {x.strip().upper() for x in args.tickers.split(",")} if args.tickers else None
    return run(args.config, tickers, args.overwrite, args.discover_only)


if __name__ == "__main__":
    raise SystemExit(main())
