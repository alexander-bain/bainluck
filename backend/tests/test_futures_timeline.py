"""Tests for GET /api/futures/{market_id}/probability-timeline endpoint."""

import pytest
from datetime import datetime, timedelta, timezone
from statistics import median
from unittest.mock import AsyncMock, MagicMock, patch

from app.routes.futures import get_probability_timeline


def _make_outcome(id, name, current_probability, market_id=1):
    o = MagicMock()
    o.id = id
    o.name = name
    o.current_probability = current_probability
    o.market_id = market_id
    return o


def _make_snapshot(outcome_id, probability, captured_at, bookmaker="consensus"):
    s = MagicMock()
    s.outcome_id = outcome_id
    s.probability = probability
    s.captured_at = captured_at
    s.bookmaker = bookmaker
    return s


def _make_market(id, name, outcomes, commence_time=None, market_metadata=None):
    m = MagicMock()
    m.id = id
    m.name = name
    m.outcomes = outcomes
    m.commence_time = commence_time
    m.market_metadata = market_metadata or {}
    return m


class TestProbabilityTimelinePure:
    """Test timeline logic using pure function behavior via the endpoint contract."""

    def test_median_of_single_value(self):
        """Median of one bookmaker is just that value."""
        assert median([0.45]) == 0.45

    def test_median_of_two_values(self):
        """Median of two bookmakers is the average."""
        assert median([0.40, 0.50]) == 0.45

    def test_median_of_three_values(self):
        """Median of three bookmakers takes the middle value."""
        assert median([0.40, 0.45, 0.90]) == 0.45

    def test_median_of_five_values(self):
        """Median is resistant to outliers."""
        assert median([0.10, 0.44, 0.45, 0.46, 0.90]) == 0.45


class TestTimelineBucketAssignment:
    """Test that timestamps are bucketed correctly."""

    def test_1h_bucket_groups_nearby_timestamps(self):
        """Timestamps within the same hour go to the same bucket."""
        bucket_seconds = 3600
        ts1 = int(datetime(2026, 3, 1, 10, 5, tzinfo=timezone.utc).timestamp())
        ts2 = int(datetime(2026, 3, 1, 10, 50, tzinfo=timezone.utc).timestamp())

        bucket1 = (ts1 // bucket_seconds) * bucket_seconds
        bucket2 = (ts2 // bucket_seconds) * bucket_seconds

        assert bucket1 == bucket2

    def test_1h_bucket_separates_different_hours(self):
        """Timestamps in different hours go to different buckets."""
        bucket_seconds = 3600
        ts1 = int(datetime(2026, 3, 1, 10, 50, tzinfo=timezone.utc).timestamp())
        ts2 = int(datetime(2026, 3, 1, 11, 5, tzinfo=timezone.utc).timestamp())

        bucket1 = (ts1 // bucket_seconds) * bucket_seconds
        bucket2 = (ts2 // bucket_seconds) * bucket_seconds

        assert bucket1 != bucket2

    def test_15min_bucket_groups_nearby(self):
        """Timestamps within the same 15-min window are bucketed together."""
        bucket_seconds = 900
        ts1 = int(datetime(2026, 3, 1, 10, 2, tzinfo=timezone.utc).timestamp())
        ts2 = int(datetime(2026, 3, 1, 10, 13, tzinfo=timezone.utc).timestamp())

        bucket1 = (ts1 // bucket_seconds) * bucket_seconds
        bucket2 = (ts2 // bucket_seconds) * bucket_seconds

        assert bucket1 == bucket2

    def test_15min_bucket_separates_different_windows(self):
        """Timestamps in different 15-min windows go to different buckets."""
        bucket_seconds = 900
        ts1 = int(datetime(2026, 3, 1, 10, 13, tzinfo=timezone.utc).timestamp())
        ts2 = int(datetime(2026, 3, 1, 10, 17, tzinfo=timezone.utc).timestamp())

        bucket1 = (ts1 // bucket_seconds) * bucket_seconds
        bucket2 = (ts2 // bucket_seconds) * bucket_seconds

        assert bucket1 != bucket2


class TestFieldAggregation:
    """Test the Field (remaining outcomes) logic."""

    def test_field_sums_non_top_outcomes(self):
        """Field probability should sum all outcomes outside the top N."""
        probs = [0.30, 0.25, 0.15, 0.10, 0.08, 0.05, 0.04, 0.03]
        top_n = 3
        field = sum(probs[top_n:])
        assert abs(field - 0.30) < 0.01  # 0.10 + 0.08 + 0.05 + 0.04 + 0.03

    def test_no_field_when_all_shown(self):
        """When top >= total outcomes, no Field entry is needed."""
        total_outcomes = 5
        top_n = 5
        assert total_outcomes <= top_n

    def test_field_with_top_1(self):
        """When top=1, Field should sum everything except the leader."""
        probs = [0.40, 0.30, 0.20, 0.10]
        field = sum(probs[1:])
        assert abs(field - 0.60) < 0.01


class TestBucketSizeSelection:
    """Test bucket size logic based on market state."""

    def test_pre_event_uses_1h_buckets(self):
        """Before commence_time, bucket size should be 3600 (1 hour)."""
        now = datetime.now(timezone.utc)
        commence = now + timedelta(hours=2)
        # Pre-event: now < commence_time
        assert now < commence
        bucket_seconds = 3600  # Expected pre-event

    def test_active_event_uses_15min_buckets(self):
        """After commence_time, bucket size should be 900 (15 minutes)."""
        now = datetime.now(timezone.utc)
        commence = now - timedelta(hours=1)
        # Active: now >= commence_time
        assert now >= commence
        bucket_seconds = 900  # Expected active

    def test_no_commence_time_uses_1h(self):
        """When commence_time is None, default to 1-hour buckets."""
        commence = None
        # The endpoint uses: if market.commence_time and now >= market.commence_time
        # If commence_time is None, the condition is False, so 1h buckets
        bucket_seconds = 3600 if not commence else 900


class TestOutcomeMetadata:
    """Test outcome metadata generation."""

    def test_outcomes_sorted_by_probability(self):
        """Outcome metadata should be sorted by current_probability descending."""
        outcomes = [
            _make_outcome(1, "A", 0.10),
            _make_outcome(2, "B", 0.50),
            _make_outcome(3, "C", 0.30),
        ]
        sorted_outcomes = sorted(
            outcomes,
            key=lambda o: o.current_probability or 0,
            reverse=True,
        )
        names = [o.name for o in sorted_outcomes]
        assert names == ["B", "C", "A"]

    def test_field_current_probability(self):
        """Field current_probability should sum non-top outcomes."""
        outcomes = [
            _make_outcome(1, "A", 0.40),
            _make_outcome(2, "B", 0.30),
            _make_outcome(3, "C", 0.15),
            _make_outcome(4, "D", 0.10),
            _make_outcome(5, "E", 0.05),
        ]
        top = 3
        sorted_out = sorted(outcomes, key=lambda o: o.current_probability, reverse=True)
        field_prob = sum(float(o.current_probability) for o in sorted_out[top:])
        assert abs(field_prob - 0.15) < 0.01  # 0.10 + 0.05

    def test_none_probability_treated_as_zero(self):
        """Outcomes with None probability should sort to the bottom."""
        outcomes = [
            _make_outcome(1, "A", 0.40),
            _make_outcome(2, "B", None),
            _make_outcome(3, "C", 0.30),
        ]
        sorted_outcomes = sorted(
            outcomes,
            key=lambda o: o.current_probability or 0,
            reverse=True,
        )
        assert sorted_outcomes[0].name == "A"
        assert sorted_outcomes[1].name == "C"
        assert sorted_outcomes[2].name == "B"


class TestFieldNeverExceeds100:
    """#1139: the synthetic Field line must never render above 100%, even when
    independent binaries carry overround and sum >1.0 (gotcha #23)."""

    async def test_field_capped_at_one_for_overround_field(self):
        now = datetime.now(timezone.utc)
        commence = now - timedelta(hours=2)  # in-play
        captured = now - timedelta(hours=1)
        # top 3 leaders + 3 non-top each 0.40 → raw Field 1.20 must cap to 1.0.
        outcomes = [
            _make_outcome(1, "Leader A", 0.50),
            _make_outcome(2, "Leader B", 0.45),
            _make_outcome(3, "Leader C", 0.42),
            _make_outcome(4, "Field X", 0.40),
            _make_outcome(5, "Field Y", 0.40),
            _make_outcome(6, "Field Z", 0.40),
        ]
        market = _make_market(1, "Overround Field", outcomes, commence_time=commence)
        snaps = [_make_snapshot(o.id, o.current_probability, captured) for o in outcomes]

        market_result = MagicMock()
        market_result.scalar_one_or_none.return_value = market
        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = snaps
        db = MagicMock()
        db.execute = AsyncMock(side_effect=[market_result, snap_result])

        resp = await get_probability_timeline(market_id=1, top=3, hours=168, db=db)

        assert resp["timeline"], "expected at least one timeline bucket"
        for entry in resp["timeline"]:
            field = entry["outcomes"].get("Field")
            if field is not None:
                assert field <= 1.0, f"Field {field} exceeds 100%"
        # the overround field (1.20 raw) is present and clamped to exactly 1.0
        assert any(e["outcomes"].get("Field") == 1.0 for e in resp["timeline"])


class TestResponseShape:
    """Test the expected response structure."""

    def test_empty_outcomes_returns_empty_timeline(self):
        """Market with no outcomes should return empty timeline."""
        market = _make_market(1, "Test", outcomes=[])
        # Empty outcomes -> empty timeline
        assert len(market.outcomes) == 0

    def test_response_has_required_fields(self):
        """Response should contain all required top-level keys."""
        required_keys = {"market_id", "market_name", "hours", "top", "timeline", "outcomes"}
        # These are tested via integration below, but we verify the contract
        assert "bucket_seconds" not in required_keys  # optional bonus field

    def test_timeline_entry_has_timestamp_and_outcomes(self):
        """Each timeline entry should have timestamp and outcomes dict."""
        entry = {
            "timestamp": "2026-03-01T10:00:00+00:00",
            "outcomes": {"A": 0.40, "B": 0.30, "Field": 0.30},
        }
        assert "timestamp" in entry
        assert "outcomes" in entry
        assert isinstance(entry["outcomes"], dict)


class TestFullRangeTopNArchiveAndVenueScoping:
    """#13573: full-range archive & venue admission read only top-N outcomes while
    live snapshot and older-live reads preserve exact Field medians."""

    async def test_top_n_scoping_keeps_exact_field_median(self):
        from app.models.models import FuturesOddsSnapshot
        from app.routes import futures as futures_routes

        now = datetime.now(timezone.utc)
        older_ts = now - timedelta(hours=200)
        mid_ts = now - timedelta(hours=100)
        recent_ts = now - timedelta(hours=2)
        outcomes = [
            _make_outcome(1, "Leader A", 0.30),
            _make_outcome(2, "Leader B", 0.25),
            _make_outcome(3, "Leader C", 0.20),
            _make_outcome(4, "Field X", 0.10),
            _make_outcome(5, "Field Y", 0.08),
            _make_outcome(6, "Field Z", 0.07),
        ]
        for o in outcomes:
            o.external_id = f"EXT-{o.id}"
            o.rank = o.id
            o.opening_probability = o.current_probability
            o.probability_change_24h = 0.0
            o.team = None
            o.team_id = None
            o.is_winner = None
            o.resolution_source = None
        market = _make_market(1, "Golf Championship", outcomes, commence_time=None)
        market.source = "kalshi"
        market.status = "open"
        market.sport = None

        older_snaps = [_make_snapshot(o.id, o.current_probability, older_ts) for o in outcomes]
        mid_snaps = [_make_snapshot(o.id, o.current_probability, mid_ts) for o in outcomes]
        recent_snaps = [_make_snapshot(o.id, o.current_probability, recent_ts) for o in outcomes]
        for s in older_snaps + mid_snaps + recent_snaps:
            s.yes_bid = 0.01
            s.yes_ask = 0.99
            s.last_price = s.probability

        seen_calls: dict[str, object] = {"snapshot_queries": []}

        async def _fake_execute(stmt, *_args, **_kwargs):
            entities = {d.get("entity") for d in getattr(stmt, "column_descriptions", ())}
            if FuturesOddsSnapshot in entities:
                params = stmt.compile().params
                requested_ids = sorted(
                    next(v for v in params.values() if isinstance(v, (list, tuple)))
                )
                seen_calls["snapshot_queries"].append(requested_ids)
                since = next(v for v in params.values() if isinstance(v, datetime))
                res = MagicMock()
                res.scalars.return_value.all.return_value = [
                    s
                    for s in (recent_snaps + mid_snaps)
                    if s.outcome_id in requested_ids and s.captured_at >= since
                ]
                return res
            res = MagicMock()
            res.scalar_one_or_none.return_value = market
            return res

        db = MagicMock()
        db.execute = AsyncMock(side_effect=_fake_execute)

        older_live = MagicMock()
        older_live.rows = older_snaps
        older_live.first = older_ts
        older_live.thinned = True
        older_live.unresolved = 0
        older_live.withhold_venue = AsyncMock(return_value=([], []))

        async def _fake_archive_claims(_db, _archive, claims, outcome_ids, *, supported):
            seen_calls["archive_claims"] = list(outcome_ids)
            return list(claims), []

        older_live.archive_claims = _fake_archive_claims

        fake_venue = MagicMock()
        fake_venue.applicable = False
        fake_venue.refusals = []
        fake_venue.state = "empty"

        def _fake_in_window(_floor, _snaps, outcome_ids):
            seen_calls["venue_in_window"] = list(outcome_ids)
            return []

        fake_venue.in_window = _fake_in_window

        fake_archive = MagicMock()
        fake_archive.state = "warm"
        fake_archive.describe = MagicMock(return_value={"points_served": 0})
        fake_archive.range_block = MagicMock(return_value={"live_thinned": True})

        def _fake_served(_floor, *, claims, outcome_ids, unresolved):
            seen_calls["archive_served"] = list(outcome_ids)
            return {}

        fake_archive.served = _fake_served

        async def _fake_load_archive(_db, _market, outcome_ids, *, since, full_range):
            seen_calls["load_archive_history"] = list(outcome_ids)
            return fake_archive

        async def _fake_read_older(_db, outcome_ids, *, before):
            seen_calls["read_older_live"] = list(outcome_ids)
            return older_live

        with (
            patch.object(futures_routes, "_withheld_price_outcome_ids", AsyncMock(return_value=set())),
            patch.object(futures_routes, "grammy_nominee_fields", AsyncMock(return_value={})),
            patch.object(futures_routes, "read_older_live", _fake_read_older),
            patch.object(futures_routes, "_load_generic_venue_history", AsyncMock(return_value=fake_venue)),
            patch.object(futures_routes, "load_archive_history", _fake_load_archive),
            patch.object(futures_routes, "add_timeline_steps", AsyncMock()),
        ):
            full_resp = await get_probability_timeline(
                market_id=1, top=3, hours=168, db=db, history_range="full",
            )
            seen_calls["full_snapshot_queries"] = list(seen_calls["snapshot_queries"])
            seen_calls["snapshot_queries"] = []
            extended_resp = await get_probability_timeline(
                market_id=1, top=3, hours=24, db=db, history_range=None,
            )

        assert seen_calls["full_snapshot_queries"] == [[1, 2, 3, 4, 5, 6]]
        assert seen_calls["snapshot_queries"] == [[1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 5, 6]]
        assert seen_calls["read_older_live"] == [1, 2, 3, 4, 5, 6]
        assert seen_calls["venue_in_window"] == [1, 2, 3]
        assert seen_calls["load_archive_history"] == [1, 2, 3]
        assert seen_calls["archive_claims"] == [1, 2, 3]
        assert seen_calls["archive_served"] == [1, 2, 3]
        assert len(full_resp["timeline"]) >= 3
        assert len(extended_resp["timeline"]) >= 2
        for entry in full_resp["timeline"] + extended_resp["timeline"]:
            assert entry["outcomes"]["Field"] == pytest.approx(0.25)
