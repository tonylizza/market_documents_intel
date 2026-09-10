"""One-off merge of the Milestone 7 AI pilot labels into the master CSVs.

Not part of the application -- a script for this one merge operation, kept
for reproducibility. Reads the blinded case list and the seven per-bucket
pilot label CSVs, verifies every case_id is covered exactly once, and writes
the labels into both the full and blinded master CSVs plus the quality
sample CSV.
"""

import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-tonylizza-Documents-market-documents-intel/"
    "00d812d4-3338-4e13-ade1-641435bcc1d0/scratchpad"
)

LABEL_FIELDS = ["human_correspondence", "human_change", "human_significance", "human_unmatched_label", "reviewer_id", "notes"]


def load_labels() -> dict[str, dict]:
    labels: dict[str, dict] = {}
    for bucket in ["UNCHANGED", "LIGHTLY_MODIFIED", "SUBSTANTIALLY_MODIFIED", "AMBIGUOUS", "NEW", "REMOVED"]:
        path = SCRATCH / f"pilot_labels_{bucket}.csv"
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                assert row["case_id"] not in labels, f"duplicate case_id across buckets: {row['case_id']}"
                labels[row["case_id"]] = row
    return labels


def merge_case_csv(input_path: Path, output_path: Path, labels: dict[str, dict]) -> None:
    with input_path.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    seen = set()
    for row in rows:
        label = labels.get(row["case_id"])
        assert label is not None, f"no pilot label for case_id {row['case_id']}"
        seen.add(row["case_id"])
        for field in LABEL_FIELDS:
            row[field] = label[field]

    assert seen == set(labels), f"label/case mismatch: {seen ^ set(labels)}"

    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def merge_quality_csv(input_path: Path, output_path: Path) -> None:
    quality_path = SCRATCH / "pilot_labels_QUALITY.csv"
    with quality_path.open(newline="") as f:
        quality_labels = {row["case_id"]: row for row in csv.DictReader(f)}

    with input_path.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    seen = set()
    for row in rows:
        label = quality_labels.get(row["case_id"])
        assert label is not None, f"no quality label for case_id {row['case_id']}"
        seen.add(row["case_id"])
        row["quality_rating"] = label["quality_rating"]
        row["reviewer_id"] = label["reviewer_id"]
        row["notes"] = label["notes"]

    assert seen == set(quality_labels), f"quality label/case mismatch: {seen ^ set(quality_labels)}"

    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    labels = load_labels()
    print(f"Loaded {len(labels)} case labels (expected 300)")
    assert len(labels) == 300

    validation_dir = REPO_ROOT / "validation"
    merge_case_csv(
        validation_dir / "human_validation_cases.csv",
        validation_dir / "human_validation_cases_piloted.csv",
        labels,
    )
    merge_case_csv(
        validation_dir / "human_validation_cases_blinded.csv",
        validation_dir / "human_validation_cases_blinded_piloted.csv",
        labels,
    )
    merge_quality_csv(
        validation_dir / "passage_quality_review_sample.csv",
        validation_dir / "passage_quality_review_sample_piloted.csv",
    )
    print("Merged into validation/*_piloted.csv")


if __name__ == "__main__":
    main()
