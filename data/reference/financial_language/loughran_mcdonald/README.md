# Loughran-McDonald Master Dictionary

This directory holds the Loughran-McDonald Master Dictionary CSV used by the
Milestone 6 financial-language signals. **The CSV itself is not committed** --
it is free for academic/non-commercial research use, but the publisher does
not state redistribution permission, so this repository only tracks this
README plus the directory structure (see `.gitignore`).

## Obtaining the file

1. Download the current Master Dictionary CSV from
   <https://sraf.nd.edu/loughranmcdonald-master-dictionary/> (the "Master
   Dictionary" link under "Sentiment Word Lists").
2. Note the exact filename -- it encodes the vintage/version (e.g.
   `Loughran-McDonald_MasterDictionary_1993-2025.csv`).

## Where to place it

```
data/reference/financial_language/loughran_mcdonald/<version>/<original-filename>
```

`<version>` is the coverage-year span embedded in the downloaded filename
(e.g. `1993-2025`). Do not rename the file -- the importer records the exact
`source_path` and a SHA-256 `source_hash` of the file as supplied, for
lineage.

## Importing

```
.venv/bin/python -m market_documents.cli.main language dictionary-import \
  --name loughran_mcdonald \
  --version <version> \
  --path data/reference/financial_language/loughran_mcdonald/<version>/<original-filename>
```

Alternatively, set `LOUGHRAN_MCDONALD_DICTIONARY_PATH` in `.env` (see
`.env.example`) to the file's path so it's discoverable without repeating
`--path` on every command that needs it.

## Licensing

Free for academic/non-commercial research use. A commercial license must be
obtained separately for commercial use -- contact the authors directly
(loughranmcdonald@gmail.com per the SRAF page). Not redistributed in this
repository; obtain your own copy from the source above.
