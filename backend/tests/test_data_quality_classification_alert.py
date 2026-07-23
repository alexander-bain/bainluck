"""Queue #246 Item 2 — the crying-wolf discipline for the classification health
check: a commodity ingest surge (tier-5 spike, category healthy, tiering active)
must NOT page CRITICAL, while a genuine classifier/tiering stall must.
"""
from app.tasks.data_quality import classify_classification_health


def _call(**over):
    base = dict(
        total_markets=25000,
        tier_5_rate=0.05,
        tier_5_count=1250,
        category_null_rate=0.0,
        category_null_count=0,
        tiering_active=True,
        tiered_count=1200,
        is_ingest_surge=False,
    )
    base.update(over)
    return classify_classification_health(**base)


def test_healthy_returns_none():
    assert _call() is None


def test_commodity_surge_is_info_not_critical():
    # r255's exact shape: 94% tier-5 from a 26.5K match-market surge, category
    # classifier healthy (4 nulls), tiering still promoting to 1-4.
    v = _call(
        tier_5_rate=0.94, tier_5_count=23468,
        category_null_rate=0.0002, category_null_count=4,
        tiering_active=True, tiered_count=1217, is_ingest_surge=True,
    )
    assert v is not None
    assert v["severity"] == "info"
    assert "ingest surge" in v["message"]


def test_bounded_tiering_lag_is_info():
    # Elevated tier-5, no surge, but tiering active + category healthy → ceiling-lag.
    v = _call(tier_5_rate=0.40, tier_5_count=10000, is_ingest_surge=False, tiering_active=True)
    assert v["severity"] == "info"
    assert "bounded tiering" in v["message"]


def test_category_classifier_stall_is_critical():
    # The HONEST unclassified signal: the category classifier failed.
    v = _call(category_null_rate=0.45, category_null_count=11250)
    assert v["severity"] == "critical"
    assert "category classifier stalled" in v["message"]


def test_tiering_stall_without_surge_is_critical():
    # tier-5 flood, ZERO promotions, and NOT explained by a surge → real stall.
    v = _call(
        tier_5_rate=0.80, tier_5_count=20000,
        tiering_active=False, tiered_count=0, is_ingest_surge=False,
    )
    assert v["severity"] == "critical"
    assert "tiering stalled" in v["message"]


def test_tier5_flood_with_surge_is_not_critical():
    # Same tier-5 flood + zero promotions, but a surge explains it → not paged.
    v = _call(
        tier_5_rate=0.80, tier_5_count=20000,
        tiering_active=False, tiered_count=0, is_ingest_surge=True,
    )
    assert v is None or v["severity"] != "critical"


def test_category_warn_band():
    v = _call(category_null_rate=0.20, category_null_count=5000)
    assert v["severity"] == "warning"


def test_small_sample_never_alerts():
    assert _call(total_markets=5, tier_5_rate=1.0, category_null_rate=1.0) is None
