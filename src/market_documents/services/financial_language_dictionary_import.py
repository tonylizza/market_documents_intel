"""Import services for Milestone 6 financial-language dictionaries.

Two sources, both driven from a local file path -- never a live download
(the Loughran-McDonald dictionary's license requires the user to obtain it
directly; tests use a small synthetic fixture, never the real file):

- `import_loughran_mcdonald`: the Loughran-McDonald Master Dictionary CSV
  (free for academic/non-commercial research use; see
  https://sraf.nd.edu/loughranmcdonald-master-dictionary/). Expected shape:
  a `Word` column plus one column per recognized category
  (`Negative`/`Positive`/`Uncertainty`/`Litigious`/`Constraining`/
  `Strong_Modal`/`Weak_Modal`, matched case- and separator-insensitively),
  where a nonzero value marks the word as belonging to that category --
  matching the real dictionary's published format (a nonzero cell is
  historically the year the tag was added, not just `1`). Unrecognized
  columns (e.g. `Negative`'s sibling stats columns, `Superfluous`,
  `Interesting`) are ignored.

- `import_custom_taxonomy`: this project's own authored YAML taxonomy
  (`config/financial_language_custom_taxonomy.yaml`) -- no licensing
  concern, since every term is authored here.

Both expand single-word terms into controlled inflection/spelling-variant
rows at import time (see `financial_language_tokenization.
expand_inflections_and_spellings`) -- never at match time.

Idempotent by `(name, version)`: re-importing an unchanged file returns the
existing dictionary without re-inserting terms; re-importing under the same
`(name, version)` with *different* file content raises, rather than silently
overwriting a dictionary version's meaning.
"""

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.exceptions import MarketDocumentsError
from market_documents.models.financial_language import FinancialLanguageDictionary, FinancialLanguageTerm
from market_documents.services.financial_language_tokenization import expand_inflections_and_spellings
from market_documents.services.similarity_tokenization import tokenize

LOUGHRAN_MCDONALD_SOURCE = (
    "Loughran-McDonald Master Dictionary (https://sraf.nd.edu/loughranmcdonald-master-dictionary/). "
    "Free for academic/non-commercial research use; a commercial license must be obtained separately "
    "for commercial use -- contact the authors directly."
)
CUSTOM_TAXONOMY_SOURCE = "Authored by this project (config/financial_language_custom_taxonomy.yaml)."

_LM_CATEGORY_COLUMNS = {
    "positive": "positive",
    "negative": "negative",
    "uncertainty": "uncertainty",
    "litigious": "litigious",
    "constraining": "constraining",
    "strongmodal": "strong_modal",
    "weakmodal": "weak_modal",
}
_LM_POLARITY = {"positive": "positive", "negative": "negative"}


class DictionaryVersionConflictError(MarketDocumentsError):
    """A dictionary with this `(name, version)` already exists with different file content."""


def compute_file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_header(name: str) -> str:
    return name.strip().lower().replace("_", "").replace(" ", "")


def _is_hit(raw_value: str) -> bool:
    raw_value = raw_value.strip()
    if not raw_value:
        return False
    try:
        return int(float(raw_value)) != 0
    except ValueError:
        return raw_value != "0"


def _get_or_create_dictionary(
    session: Session, *, name: str, version: str, source: str, source_hash: str, source_path: str, license_notes: str
) -> tuple[FinancialLanguageDictionary, bool]:
    """Returns `(dictionary, created)`. Raises `DictionaryVersionConflictError`
    if `(name, version)` already exists with a different `source_hash`."""
    existing = session.scalar(
        select(FinancialLanguageDictionary).where(
            FinancialLanguageDictionary.name == name, FinancialLanguageDictionary.version == version
        )
    )
    if existing is not None:
        if existing.source_hash != source_hash:
            raise DictionaryVersionConflictError(
                f"dictionary {name!r} version {version!r} already imported with a different file "
                f"(existing hash {existing.source_hash[:12]}, new hash {source_hash[:12]}) -- import under a "
                "new version instead of silently replacing an existing one"
            )
        return existing, False

    dictionary = FinancialLanguageDictionary(
        name=name,
        version=version,
        source=source,
        source_hash=source_hash,
        source_path=source_path,
        license_notes=license_notes,
        language="en",
        term_count=0,
    )
    session.add(dictionary)
    session.flush()
    return dictionary, True


@dataclass(frozen=True)
class _TermSpec:
    normalized_term: str
    category: str
    subcategory: str | None
    polarity: str | None
    weight: float
    notes: str | None


def _insert_terms(session: Session, dictionary: FinancialLanguageDictionary, specs: list[_TermSpec]) -> int:
    """Insert deduplicated `(normalized_term, category)` rows, expanding
    single-word terms into controlled inflection/spelling variants. Returns
    the number of rows actually inserted."""
    seen: set[tuple[str, str]] = set()
    inserted = 0
    for spec in specs:
        forms = {spec.normalized_term} | expand_inflections_and_spellings(spec.normalized_term)
        for form in sorted(forms):
            key = (form, spec.category)
            if key in seen:
                continue
            seen.add(key)
            is_variant = form != spec.normalized_term
            session.add(
                FinancialLanguageTerm(
                    dictionary_id=dictionary.id,
                    term=form,
                    normalized_term=form,
                    category=spec.category,
                    subcategory=spec.subcategory,
                    polarity=spec.polarity,
                    weight=spec.weight,
                    is_phrase=" " in form,
                    phrase_token_count=len(form.split()) if " " in form else 1,
                    notes=(f"inflection_or_spelling_variant_of:{spec.normalized_term}" if is_variant else spec.notes),
                )
            )
            inserted += 1
    return inserted


def import_loughran_mcdonald(
    session: Session, path: Path, *, version: str, name: str = "loughran_mcdonald"
) -> tuple[FinancialLanguageDictionary, bool]:
    """Import the Loughran-McDonald Master Dictionary from a local CSV.
    Returns `(dictionary, created)` -- `created=False` on an idempotent
    re-import of an unchanged file."""
    source_hash = compute_file_hash(path)
    dictionary, created = _get_or_create_dictionary(
        session,
        name=name,
        version=version,
        source=LOUGHRAN_MCDONALD_SOURCE,
        source_hash=source_hash,
        source_path=str(path),
        license_notes=(
            "Free for academic/non-commercial research use per the publisher's terms; not redistributed in "
            "this repository -- obtain the source CSV directly from sraf.nd.edu and import locally."
        ),
    )
    if not created:
        return dictionary, False

    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
    if reader.fieldnames is None:
        raise MarketDocumentsError(f"{path} has no header row")
    header_map = {_normalize_header(h): h for h in reader.fieldnames}
    word_column = header_map.get("word")
    if word_column is None:
        raise MarketDocumentsError(f"{path} has no 'Word' column (found: {reader.fieldnames})")
    category_columns = {
        category: header_map[normalized]
        for normalized, category in _LM_CATEGORY_COLUMNS.items()
        if normalized in header_map
    }
    if not category_columns:
        raise MarketDocumentsError(
            f"{path} has none of the recognized Loughran-McDonald category columns (found: {reader.fieldnames})"
        )

    specs: list[_TermSpec] = []
    for row in reader:
        word = (row.get(word_column) or "").strip()
        if not word:
            continue
        normalized_tokens = tokenize(word)
        if not normalized_tokens:
            continue
        normalized_term = " ".join(normalized_tokens)
        for category, column in category_columns.items():
            if _is_hit(row.get(column) or ""):
                specs.append(
                    _TermSpec(
                        normalized_term=normalized_term,
                        category=category,
                        subcategory=None,
                        polarity=_LM_POLARITY.get(category),
                        weight=1.0,
                        notes=None,
                    )
                )

    dictionary.term_count = _insert_terms(session, dictionary, specs)
    session.flush()
    return dictionary, True


def import_custom_taxonomy(
    session: Session, path: Path, *, version: str, name: str = "custom_domain_taxonomy"
) -> tuple[FinancialLanguageDictionary, bool]:
    """Import this project's own authored domain taxonomy from YAML.
    Returns `(dictionary, created)`."""
    source_hash = compute_file_hash(path)
    dictionary, created = _get_or_create_dictionary(
        session,
        name=name,
        version=version,
        source=CUSTOM_TAXONOMY_SOURCE,
        source_hash=source_hash,
        source_path=str(path),
        license_notes="Authored by this project; no third-party licensing restrictions.",
    )
    if not created:
        return dictionary, False

    data = yaml.safe_load(path.read_text()) or {}
    specs: list[_TermSpec] = []
    for category, category_body in (data.get("categories") or {}).items():
        for subcategory, terms in (category_body.get("subcategories") or {}).items():
            for term in terms or []:
                normalized_tokens = tokenize(str(term))
                if not normalized_tokens:
                    continue
                specs.append(
                    _TermSpec(
                        normalized_term=" ".join(normalized_tokens),
                        category=str(category),
                        subcategory=str(subcategory),
                        polarity=None,
                        weight=1.0,
                        notes=None,
                    )
                )

    dictionary.term_count = _insert_terms(session, dictionary, specs)
    session.flush()
    return dictionary, True
