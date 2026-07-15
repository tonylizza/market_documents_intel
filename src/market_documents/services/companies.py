from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.company import Company


def load_companies_from_yaml(session: Session, config_path: Path) -> dict[str, Company]:
    """Idempotently get-or-create Company rows from config/companies.yaml.

    Never overwrites an already-registered company's name -- config is only
    ever used to fill in companies that don't exist yet.
    """
    data = yaml.safe_load(config_path.read_text())
    entries = data.get("companies", []) if data else []

    existing = {c.ticker: c for c in session.scalars(select(Company))}
    result: dict[str, Company] = dict(existing)

    for entry in entries:
        ticker = str(entry["ticker"]).strip().upper()
        if ticker in result:
            continue
        company = Company(ticker=ticker, company_name=entry["company_name"])
        session.add(company)
        result[ticker] = company

    session.flush()
    return result
