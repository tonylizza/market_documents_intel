from market_documents.services.human_validation_analysis import (
    binary_change_metrics,
    change_confusion_matrix,
    cohens_kappa,
    correspondence_precision,
    inter_rater_reliability,
    ordered_change_agreement,
    similarity_vs_human_change,
    spearman_correlation,
    unmatched_validity,
    weighted_kappa,
)


def _row(**kwargs):
    base = {
        "case_id": "M7-0001",
        "sample_bucket": "UNCHANGED",
        "company": "ACT",
        "system_alignment_status": "UNCHANGED",
        "system_confidence": "HIGH",
        "system_semantic_similarity": "",
        "system_lexical_cosine_similarity": "",
        "system_jaccard_similarity": "",
        "system_edit_similarity": "",
        "system_combined_score": "",
        "human_correspondence": "",
        "human_change": "",
        "human_significance": "",
        "human_unmatched_label": "",
    }
    base.update(kwargs)
    return base


def test_correspondence_precision_overall_and_by_group():
    rows = [
        _row(system_confidence="HIGH", human_correspondence="YES"),
        _row(system_confidence="HIGH", human_correspondence="YES"),
        _row(system_confidence="HIGH", human_correspondence="NO"),
        _row(system_confidence="NEEDS_REVIEW", human_correspondence="NO"),
        _row(sample_bucket="NEW", human_correspondence="YES"),  # excluded: not a matched bucket
    ]
    result = correspondence_precision(rows, group_by="system_confidence")
    assert result["overall"]["n"] == 4
    assert result["overall"]["precision"] == 0.5
    assert result["by_group"]["HIGH"]["precision"] == 2 / 3
    assert result["by_group"]["NEEDS_REVIEW"]["precision"] == 0.0


def test_correspondence_precision_ignores_unlabeled_rows():
    rows = [_row(human_correspondence=""), _row(human_correspondence="YES")]
    result = correspondence_precision(rows)
    assert result["overall"]["n"] == 1


def test_unmatched_validity_new_and_removed():
    rows = [
        _row(sample_bucket="NEW", human_unmatched_label="NO_CORRESPONDENCE"),
        _row(sample_bucket="NEW", human_unmatched_label="NO_CORRESPONDENCE"),
        _row(sample_bucket="NEW", human_unmatched_label="CORRESPONDENCE_EXISTS"),
        _row(sample_bucket="REMOVED", human_unmatched_label="STRUCTURAL_SPLIT_MERGE"),
    ]
    result = dict(unmatched_validity(rows))
    assert result["NEW"]["n"] == 3
    assert result["NEW"]["precision_no_correspondence"] == 2 / 3
    assert result["REMOVED"]["n"] == 1
    assert result["REMOVED"]["structural_split_merge_rate"] == 1.0


def test_change_confusion_matrix_and_agreement():
    rows = [
        _row(human_correspondence="YES", human_change="EFFECTIVELY_UNCHANGED", system_alignment_status="UNCHANGED"),
        _row(human_correspondence="YES", human_change="MINOR", system_alignment_status="LIGHTLY_MODIFIED"),
        _row(human_correspondence="YES", human_change="SUBSTANTIAL", system_alignment_status="UNCHANGED"),  # 2 apart
        _row(human_correspondence="NO", human_change="MINOR", system_alignment_status="LIGHTLY_MODIFIED"),  # excluded
    ]
    result = change_confusion_matrix(rows)
    assert result["n"] == 3
    assert result["exact_agreement"] == 2 / 3
    assert result["within_one_category"] == 2 / 3  # the SUBSTANTIAL/UNCHANGED row is 2 categories apart


def test_binary_change_metrics():
    rows = [
        _row(human_correspondence="YES", human_change="EFFECTIVELY_UNCHANGED", system_alignment_status="UNCHANGED"),  # tn
        _row(human_correspondence="YES", human_change="MINOR", system_alignment_status="LIGHTLY_MODIFIED"),  # tp
        _row(human_correspondence="YES", human_change="MINOR", system_alignment_status="UNCHANGED"),  # fn
        _row(human_correspondence="YES", human_change="EFFECTIVELY_UNCHANGED", system_alignment_status="LIGHTLY_MODIFIED"),  # fp
    ]
    result = binary_change_metrics(rows)
    assert result["confusion"] == {"tp": 1, "fp": 1, "tn": 1, "fn": 1}
    assert result["accuracy"] == 0.5
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5


def test_ordered_change_agreement_perfect_correlation():
    rows = [
        _row(human_correspondence="YES", human_change="EFFECTIVELY_UNCHANGED", system_alignment_status="UNCHANGED"),
        _row(human_correspondence="YES", human_change="MINOR", system_alignment_status="LIGHTLY_MODIFIED"),
        _row(human_correspondence="YES", human_change="SUBSTANTIAL", system_alignment_status="SUBSTANTIALLY_MODIFIED"),
    ]
    result = ordered_change_agreement(rows)
    assert result["spearman"] == 1.0
    assert result["mean_absolute_category_difference"] == 0.0


def test_similarity_vs_human_change_skips_missing_values():
    rows = [
        _row(human_correspondence="YES", human_change="EFFECTIVELY_UNCHANGED", system_semantic_similarity="0.99"),
        _row(human_correspondence="YES", human_change="SUBSTANTIAL", system_semantic_similarity="0.40"),
        _row(human_correspondence="YES", human_change="MINOR", system_semantic_similarity=""),
    ]
    result = similarity_vs_human_change(rows)
    assert result["system_semantic_similarity"]["n"] == 2
    assert result["system_semantic_similarity"]["spearman"] == -1.0


def test_cohens_kappa_perfect_and_chance():
    assert cohens_kappa(["YES", "NO", "YES"], ["YES", "NO", "YES"]) == 1.0
    # Independent-looking disagreement should be well below 1.
    kappa = cohens_kappa(["YES", "NO", "YES", "NO"], ["NO", "YES", "NO", "YES"])
    assert kappa is not None and kappa < 0


def test_weighted_kappa_ordinal():
    assert weighted_kappa([0, 1, 2], [0, 1, 2], num_categories=3) == 1.0
    # Off-by-one should be penalized less than off-by-two.
    near = weighted_kappa([0, 1, 2], [1, 2, 1], num_categories=3)
    far = weighted_kappa([0, 1, 2], [2, 0, 0], num_categories=3)
    assert near is not None and far is not None
    assert near > far


def test_spearman_correlation_handles_ties():
    assert spearman_correlation([1, 2, 3], [1, 2, 3]) == 1.0
    assert spearman_correlation([1, 2, 3], [3, 2, 1]) == -1.0
    assert spearman_correlation([1, 1, 1], [1, 2, 3]) is None  # zero variance -> undefined


def test_inter_rater_reliability_matches_by_case_id():
    reviewer_a = [
        _row(case_id="C1", human_correspondence="YES", human_change="MINOR"),
        _row(case_id="C2", human_correspondence="NO", human_change=""),
    ]
    reviewer_b = [
        _row(case_id="C1", human_correspondence="YES", human_change="MINOR"),
        _row(case_id="C2", human_correspondence="YES", human_change=""),
    ]
    result = inter_rater_reliability(reviewer_a, reviewer_b)
    assert result.n_overlap == 2
    assert result.correspondence_raw_agreement == 0.5
