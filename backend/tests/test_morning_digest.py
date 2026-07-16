"""Tests for Morning Digest v1 content selection + rendering (Queue #200)."""

from datetime import datetime, timezone

from app.utils.morning_digest import (
    DigestCandidate,
    is_stale_dated_bucket,
    render_digest_payload,
    select_digest_candidates,
)


def _cand(mid, name, prob, interest, category=None, dedup_key=None, volume=None, leader="Yes"):
    return DigestCandidate(
        market_id=mid,
        name=name,
        leader_name=leader,
        leader_prob=prob,
        interestingness=interest,
        volume_24h=volume,
        category=category,
        dedup_key=dedup_key,
    )


def test_selects_by_interestingness_descending():
    cands = [
        _cand(1, "Low", 0.5, 10.0),
        _cand(2, "High", 0.5, 90.0),
        _cand(3, "Mid", 0.5, 50.0),
    ]
    picked = select_digest_candidates(cands, limit=3)
    assert [c.market_id for c in picked] == [2, 3, 1]


def test_respects_limit():
    cands = [_cand(i, f"Q{i}", 0.5, float(100 - i), dedup_key=f"k{i}") for i in range(20)]
    picked = select_digest_candidates(cands, limit=5)
    assert len(picked) == 5


def test_dedups_by_dedup_key():
    cands = [
        _cand(1, "Dup A", 0.6, 90.0, dedup_key="same"),
        _cand(2, "Dup B", 0.6, 80.0, dedup_key="same"),
        _cand(3, "Other", 0.6, 70.0, dedup_key="other"),
    ]
    picked = select_digest_candidates(cands, limit=5)
    assert [c.market_id for c in picked] == [1, 3]


def test_caps_per_category():
    cands = [
        _cand(1, "P1", 0.6, 99.0, category="politics", dedup_key="p1"),
        _cand(2, "P2", 0.6, 98.0, category="politics", dedup_key="p2"),
        _cand(3, "P3", 0.6, 97.0, category="politics", dedup_key="p3"),
        _cand(4, "E1", 0.6, 50.0, category="economics", dedup_key="e1"),
    ]
    picked = select_digest_candidates(cands, limit=5, max_per_category=2)
    cats = [c.category for c in picked]
    assert cats.count("politics") == 2
    assert "economics" in cats


def test_affinity_boosts_matching_category():
    cands = [
        _cand(1, "Politics", 0.5, 50.0, category="politics", dedup_key="p"),
        _cand(2, "Sports", 0.5, 55.0, category="sports", dedup_key="s"),
    ]
    # Without affinity, sports (55) beats politics (50).
    assert select_digest_candidates(cands, limit=1)[0].market_id == 2
    # With a strong politics affinity, politics wins.
    picked = select_digest_candidates(cands, limit=1, category_affinities={"politics": 0.5})
    assert picked[0].market_id == 1


def test_render_payload_lines_and_deeplink():
    items = [
        _cand(42, "Will the Fed cut rates in September?", 0.64, 80.0, leader="Yes"),
        _cand(7, "Who wins the Best Picture Oscar?", 0.31, 70.0, leader="Some Long Film Title"),
    ]
    payload = render_digest_payload(items)
    assert payload.title
    assert "64%" in payload.body
    assert "31%" in payload.body
    assert payload.body.count("\n") == 1  # two items -> one newline
    # Deep link points at the top item.
    assert payload.data["type"] == "morning_digest"
    assert payload.data["market_id"] == "42"
    assert payload.data["url"] == "/futures/42"
    assert len(payload.items) == 2


def test_render_empty_is_graceful():
    payload = render_digest_payload([])
    assert payload.title
    assert payload.body
    assert payload.data["url"] == "/discover"


def test_payload_id_adds_open_tracking_to_deeplink():
    """#209 rider (measurement_spec §2): the digest funnel's open-tracking params
    ride the deep link, joined to push_sent via utm_campaign == payload_id."""
    items = [_cand(42, "Will the Fed cut rates?", 0.64, 80.0, leader="Yes")]
    payload = render_digest_payload(items, payload_id="digest-20260716")
    assert payload.data["payload_id"] == "digest-20260716"
    url = payload.data["url"]
    assert url.startswith("/futures/42?")
    assert "utm_source=push" in url
    assert "utm_medium=morning_digest" in url
    assert "utm_campaign=digest-20260716" in url


def test_payload_id_tracking_on_default_discover_link():
    payload = render_digest_payload([], payload_id="digest-20260716")
    assert payload.data["url"].startswith("/discover?")
    assert "utm_campaign=digest-20260716" in payload.data["url"]


def test_no_payload_id_leaves_deeplink_clean():
    """Backward compatible: without a payload_id the deep link is untouched."""
    items = [_cand(42, "Q?", 0.64, 80.0)]
    payload = render_digest_payload(items)
    assert payload.data["url"] == "/futures/42"
    assert "payload_id" not in payload.data


def test_drops_near_certain_leaders():
    cands = [
        _cand(1, "Boring 100%", 1.0, 99.0, dedup_key="a"),
        _cand(2, "Boring 98%", 0.98, 98.0, dedup_key="b"),
        _cand(3, "Interesting", 0.62, 50.0, dedup_key="c"),
    ]
    picked = select_digest_candidates(cands, limit=5)
    # Near-certain leaders (>=0.97) are dropped despite higher interestingness.
    assert [c.market_id for c in picked] == [3]


def test_probability_clamped_and_rounded():
    items = [_cand(1, "Q", 1.5, 50.0, leader="Yes")]  # out-of-range prob
    payload = render_digest_payload(items)
    assert "100%" in payload.body


# Queue #201 Item 2: dated-bucket staleness suppression. A market whose title
# implies a past month must never rank into a later digest, even though the
# candidate SQL pool only drops a *past resolution_date* (Kalshi's settlement
# date for a month-named market lands ~2 weeks into the NEXT month — gotcha #883,
# so the row survives the query with a future resolution_date). Seed at a fixed
# hour (gotcha #44) — never datetime.now().
_JULY_15 = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_drops_stale_dated_bucket_when_now_passed():
    cands = [
        _cand(1, "Most rain in LA in May 2026", 0.60, 99.0, category="weather", dedup_key="a"),
        _cand(2, "Who wins the 2026 election?", 0.55, 50.0, category="politics", dedup_key="b"),
    ]
    picked = select_digest_candidates(cands, limit=5, now=_JULY_15)
    # The May-dated bucket is stale by July; only the fresh market survives.
    assert [c.market_id for c in picked] == [2]


def test_fresh_dated_market_survives():
    cands = [
        _cand(1, "Most rain in LA in September 2026", 0.60, 99.0, category="weather", dedup_key="a"),
    ]
    picked = select_digest_candidates(cands, limit=5, now=_JULY_15)
    assert [c.market_id for c in picked] == [1]


def test_staleness_is_opt_in_via_now():
    # Backward compat: without `now`, no time-dependent filtering runs, so the
    # pure ranker behaves exactly as before (the stale bucket is NOT dropped).
    cands = [_cand(1, "Most rain in LA in May 2026", 0.60, 99.0, dedup_key="a")]
    assert [c.market_id for c in select_digest_candidates(cands, limit=5)] == [1]


def test_is_stale_dated_bucket_helper():
    stale = _cand(1, "Rain in LA in May 2026", 0.5, 50.0, category="weather")
    fresh = _cand(2, "Rain in LA in August 2026", 0.5, 50.0, category="weather")
    assert is_stale_dated_bucket(stale, _JULY_15) == "stale_explicit_title_month"
    assert is_stale_dated_bucket(fresh, _JULY_15) is None


# --- Feed-parity quality gate in _gather_digest_candidates (Queue #202, Item 2) ---


class _FakeOutcome:
    def __init__(self, name, prob):
        self.name = name
        self.current_probability = prob


class _FakeMarket:
    def __init__(self, mid, name, category, external_id, outcomes, volume=1000.0):
        self.id = mid
        self.name = name
        self.llm_sport_category = category
        self.canonical_market_key = None
        self.group_id = None
        self.volume_24h = volume
        self.external_id = external_id
        self.outcomes = outcomes


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def unique(self):
        return self

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *args, **kwargs):
        return _FakeResult(self._rows)


class _FakeRedis:
    def mget(self, keys):
        return [None] * len(keys)


def test_gather_applies_feed_parity_quality_gate():
    """The digest must never surface a market the Discover feed would suppress."""
    import asyncio

    from app.tasks.morning_digest import _gather_digest_candidates

    compelling = _FakeMarket(
        1,
        "Will Democrats win the 2028 US Presidential election?",
        "politics",
        "KXPRES-28",
        [_FakeOutcome("Yes", 0.55), _FakeOutcome("No", 0.45)],
    )
    # margin_turnout_excluded -> quality_class == "suppress" in the feed.
    suppressed = _FakeMarket(
        2,
        "Voter turnout in the 2026 Georgia Senate election",
        "politics",
        "KXTURNOUT-26GA",
        [_FakeOutcome("Over 60%", 0.60), _FakeOutcome("Under 60%", 0.40)],
    )

    cands = asyncio.run(
        _gather_digest_candidates(_FakeSession([compelling, suppressed]), _FakeRedis())
    )
    ids = {c.market_id for c in cands}
    assert 1 in ids, "compelling market should survive the quality gate"
    assert 2 not in ids, "feed-suppressed market must be dropped from the digest"
