"""Shared fixture-building helpers for Milestone 6 financial-language tests.

Not a test module itself. Builds on `_feature_fixtures.build_manual_alignment_
pair` (hand-specified AlignmentRun/PassageAlignment population) plus a real
`build_features` call, and writes small synthetic Loughran-McDonald-shaped
CSV / custom-taxonomy-shaped YAML dictionary files to a tmp_path -- the real
Loughran-McDonald file is never used in tests (license + no live network
dependency).
"""

from pathlib import Path

import yaml

from market_documents.services.feature_extraction import build_features
from tests._feature_fixtures import build_manual_alignment_pair

# Synthetic Loughran-McDonald-shaped CSV: one row per test term. Nonzero
# values (mirroring the real dictionary's "year added" convention) mark
# category membership; "loss" deliberately spans two categories to exercise
# multi-category term handling.
LM_CSV_HEADER = "Word,Negative,Positive,Uncertainty,Litigious,Constraining,Strong_Modal,Weak_Modal\n"
LM_CSV_ROWS = (
    "LOSS,2009,0,0,2009,0,0,0\n"
    "STRONG,0,2009,0,0,0,0,0\n"
    "UNCERTAIN,0,0,2009,0,0,0,0\n"
    "MUST,0,0,0,0,2009,0,0\n"
    "ALWAYS,0,0,0,0,0,2009,0\n"
    "COULD,0,0,0,0,0,0,2009\n"
    "LOSS,2009,0,0,2009,0,0,0\n"  # exact duplicate row -- duplicate-term handling
)


def write_synthetic_lm_csv(tmp_path: Path, filename: str = "lm_synthetic.csv") -> Path:
    path = tmp_path / filename
    path.write_text(LM_CSV_HEADER + LM_CSV_ROWS)
    return path


CUSTOM_TAXONOMY_YAML = {
    "categories": {
        "risk": {"subcategories": {"credit": ["credit risk"], "liquidity": ["liquidity risk"]}},
        "governance": {"subcategories": {"board": ["board of directors"]}},
    }
}


def write_synthetic_taxonomy_yaml(tmp_path: Path, filename: str = "taxonomy_synthetic.yaml") -> Path:
    path = tmp_path / filename
    path.write_text(yaml.safe_dump(CUSTOM_TAXONOMY_YAML))
    return path


def build_language_ready_pair(
    db_session,
    *,
    ticker: str,
    earlier_texts,
    later_texts,
    rows,
    gap_months: int = 12,
    is_transition: bool = False,
):
    """`build_manual_alignment_pair` plus a real `build_features` call, so
    the pair has a current successful FeatureRun/ReportPairFeatures ready
    for `build_language_signals` to select."""
    pair, alignment_run, earlier_passages, later_passages, _sim = build_manual_alignment_pair(
        db_session,
        ticker=ticker,
        gap_months=gap_months,
        is_transition=is_transition,
        earlier_texts=earlier_texts,
        later_texts=later_texts,
        rows=rows,
    )
    feature_outcome = build_features(db_session, pair)
    return pair, alignment_run, earlier_passages, later_passages, feature_outcome
