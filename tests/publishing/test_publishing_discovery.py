import uuid

from market_documents.publishing.discovery import DiscoveryCandidate, rank_discovery_items
from market_documents.publishing.findings import ComparisonMetrics


def _metrics(**overrides) -> ComparisonMetrics:
    defaults = dict(
        disclosure_change_score=None,
        feature_quality_ok=False,
        feature_primary_eligible=False,
        net_tone_change=None,
        uncertainty_intensity_change=None,
        risk_language_introduction=None,
        risk_language_removal=None,
        governance_language_change=None,
        financial_condition_language_change=None,
        financial_condition_share_change=None,
        financial_condition_topic_mix_change=None,
        governance_share_change=None,
        governance_topic_mix_change=None,
        financial_condition_topic_change=None,
        governance_topic_change=None,
        uncertainty_topic_change=None,
        report_side_quality_ok=False,
        report_side_primary_eligible=False,
        alignment_change_quality_ok=False,
        alignment_change_primary_eligible=False,
        new_rate_words=None,
    )
    defaults.update(overrides)
    return ComparisonMetrics(**defaults)


def _candidate(company_id, is_latest, **metric_overrides) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        report_comparison_id=uuid.uuid4(),
        company_id=company_id,
        is_latest_for_company=is_latest,
        metrics=_metrics(**metric_overrides),
    )


def test_ineligible_candidates_never_ranked():
    company = uuid.uuid4()
    candidates = [_candidate(company, True, financial_condition_topic_change=0.9, report_side_quality_ok=False)]
    items = rank_discovery_items(candidates)
    assert items == []


def test_sub_epsilon_candidate_never_ranked_even_as_sole_pool_member():
    company = uuid.uuid4()
    candidates = [
        _candidate(company, True, financial_condition_topic_change=0.001, report_side_quality_ok=True, report_side_primary_eligible=True)
    ]
    items = rank_discovery_items(candidates)
    assert not any(i.discovery_type == "largest_financial_condition_shift" for i in items)


def test_corpus_scope_ranks_across_companies():
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    candidates = [
        _candidate(c1, False, financial_condition_topic_change=0.9, report_side_quality_ok=True, report_side_primary_eligible=True),
        _candidate(c2, False, financial_condition_topic_change=0.5, report_side_quality_ok=True, report_side_primary_eligible=True),
    ]
    items = [i for i in rank_discovery_items(candidates) if i.discovery_type == "largest_financial_condition_shift" and i.rank_scope == "corpus"]
    assert len(items) == 2
    assert items[0].rank == 1 and items[0].supporting_value == 0.9
    assert items[1].rank == 2 and items[1].supporting_value == 0.5


def test_company_history_scope_pools_are_per_company():
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    candidates = [
        _candidate(c1, False, financial_condition_topic_change=0.9, report_side_quality_ok=True, report_side_primary_eligible=True),
        _candidate(c1, False, financial_condition_topic_change=0.5, report_side_quality_ok=True, report_side_primary_eligible=True),
        _candidate(c2, False, financial_condition_topic_change=0.3, report_side_quality_ok=True, report_side_primary_eligible=True),
    ]
    items = [
        i for i in rank_discovery_items(candidates)
        if i.discovery_type == "largest_financial_condition_shift" and i.rank_scope == "company_history"
    ]
    c1_items = [i for i in items if i.company_id == c1]
    c2_items = [i for i in items if i.company_id == c2]
    assert len(c1_items) == 2
    assert len(c2_items) == 1
    assert c2_items[0].rank == 1  # sole member of its own pool, not competing with c1


def test_latest_comparisons_scope_excludes_non_latest():
    c1, c2 = uuid.uuid4(), uuid.uuid4()
    candidates = [
        _candidate(c1, True, financial_condition_topic_change=0.9, report_side_quality_ok=True, report_side_primary_eligible=True),
        _candidate(c1, False, financial_condition_topic_change=0.99, report_side_quality_ok=True, report_side_primary_eligible=True),
        _candidate(c2, True, financial_condition_topic_change=0.5, report_side_quality_ok=True, report_side_primary_eligible=True),
    ]
    items = [
        i for i in rank_discovery_items(candidates)
        if i.discovery_type == "largest_financial_condition_shift" and i.rank_scope == "latest_comparisons"
    ]
    assert len(items) == 2
    assert all(i.supporting_value in (0.9, 0.5) for i in items)


def test_deterministic_tiebreak_by_comparison_id():
    company = uuid.uuid4()
    id_a = uuid.UUID(int=1)
    id_b = uuid.UUID(int=2)
    candidates = [
        DiscoveryCandidate(
            report_comparison_id=id_b, company_id=company, is_latest_for_company=False,
            metrics=_metrics(financial_condition_topic_change=0.5, report_side_quality_ok=True, report_side_primary_eligible=True),
        ),
        DiscoveryCandidate(
            report_comparison_id=id_a, company_id=company, is_latest_for_company=False,
            metrics=_metrics(financial_condition_topic_change=0.5, report_side_quality_ok=True, report_side_primary_eligible=True),
        ),
    ]
    items = [i for i in rank_discovery_items(candidates) if i.discovery_type == "largest_financial_condition_shift" and i.rank_scope == "corpus"]
    # exact tie in magnitude -> lower string-sorted id wins rank 1
    assert items[0].report_comparison_id == id_a
    assert items[1].report_comparison_id == id_b


def test_rerun_is_byte_identical():
    company = uuid.uuid4()
    candidates = [
        _candidate(company, True, financial_condition_topic_change=0.7, report_side_quality_ok=True, report_side_primary_eligible=True),
        _candidate(company, False, financial_condition_topic_change=0.3, report_side_quality_ok=True, report_side_primary_eligible=True),
    ]
    first = rank_discovery_items(candidates)
    second = rank_discovery_items(candidates)
    assert first == second


def test_percentile_and_rank_contiguous():
    company = uuid.uuid4()
    candidates = [
        _candidate(company, False, financial_condition_topic_change=v, report_side_quality_ok=True, report_side_primary_eligible=True)
        for v in (0.9, 0.7, 0.5, 0.3)
    ]
    items = sorted(
        (i for i in rank_discovery_items(candidates) if i.discovery_type == "largest_financial_condition_shift" and i.rank_scope == "corpus"),
        key=lambda i: i.rank,
    )
    assert [i.rank for i in items] == [1, 2, 3, 4]
    assert items[0].percentile == 100.0
    assert items[-1].percentile == 25.0


def test_disabled_discovery_types_never_ranked():
    # Track 7F.9: huge values that pass every gate still never produce a
    # ranking for a disabled type -- they have no CandidateSpec at all.
    company = uuid.uuid4()
    candidates = [
        _candidate(
            company, True,
            disclosure_change_score=0.99, feature_quality_ok=True, feature_primary_eligible=True,
            new_rate_words=0.9,
            risk_language_introduction=50.0, risk_language_removal=50.0,
            alignment_change_quality_ok=True, alignment_change_primary_eligible=True,
        )
    ]
    assert rank_discovery_items(candidates) == []
