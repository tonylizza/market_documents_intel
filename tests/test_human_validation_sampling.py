from market_documents.services.human_validation_sampling import (
    _diversified_pick,
    _length_bucket,
    _sqrt_weighted_quota,
)


def test_length_bucket_boundaries():
    assert _length_bucket(0) == "SHORT"
    assert _length_bucket(59) == "SHORT"
    assert _length_bucket(60) == "MEDIUM"
    assert _length_bucket(200) == "MEDIUM"
    assert _length_bucket(201) == "LONG"


def test_sqrt_weighted_quota_respects_availability():
    counts = {"HIGH": 1000, "MEDIUM": 10, "LOW": 5, "NEEDS_REVIEW": 0}
    quota = _sqrt_weighted_quota(counts, target=60)
    assert sum(quota.values()) == 60
    assert quota["NEEDS_REVIEW"] == 0
    for key in counts:
        assert quota[key] <= counts[key]
    # sqrt weighting still favors the larger bucket, but not proportionally --
    # HIGH's 100x availability advantage over MEDIUM should not produce a 100x quota gap.
    assert quota["HIGH"] < 60
    assert quota["MEDIUM"] > 0


def test_sqrt_weighted_quota_target_exceeds_total_availability():
    counts = {"HIGH": 3, "MEDIUM": 2}
    quota = _sqrt_weighted_quota(counts, target=60)
    assert quota["HIGH"] == 3
    assert quota["MEDIUM"] == 2


def test_sqrt_weighted_quota_all_zero():
    counts = {"HIGH": 0, "MEDIUM": 0}
    quota = _sqrt_weighted_quota(counts, target=10)
    assert quota == {"HIGH": 0, "MEDIUM": 0}


def test_diversified_pick_is_deterministic_for_a_given_seed():
    import random

    class Item:
        def __init__(self, id_, ticker, bucket):
            self.id = id_
            self.ticker = ticker
            self.bucket = bucket

    items = [Item(f"id-{i}", ticker, "SHORT") for i, ticker in enumerate(["ACT"] * 5 + ["KP2"] * 5)]

    def key_fn(item):
        return f"{item.ticker}:{item.bucket}"

    picked_a = _diversified_pick(random.Random(42), items, key_fn, 4)
    picked_b = _diversified_pick(random.Random(42), items, key_fn, 4)
    assert [p.id for p in picked_a] == [p.id for p in picked_b]


def test_diversified_pick_spreads_across_groups():
    import random

    class Item:
        def __init__(self, id_, ticker):
            self.id = id_
            self.ticker = ticker

    items = [Item(f"id-{i}", "ACT") for i in range(20)] + [Item(f"id-kp2-{i}", "KP2") for i in range(2)]

    picked = _diversified_pick(random.Random(7), items, lambda item: item.ticker, 4)
    tickers = {p.ticker for p in picked}
    # Both groups have items available, so a round-robin draw of 4 must
    # include both, not just the 20-item majority group.
    assert tickers == {"ACT", "KP2"}


def test_diversified_pick_never_exceeds_available():
    import random

    class Item:
        def __init__(self, id_):
            self.id = id_

    items = [Item("only-one")]
    picked = _diversified_pick(random.Random(1), items, lambda item: "group", 5)
    assert len(picked) == 1
