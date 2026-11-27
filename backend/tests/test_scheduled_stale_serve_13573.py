"""#13573: Keep scheduled `/related-futures` copies servable up to 10 minutes
(600 s) pre-kickoff, hard-capped at `source_commence_time`, live-checked against
`(Event.status, Event.commence_time)` once past 150 s, while `/game-markets` keeps
its 150 s ceiling.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.routes import events as events_route
from app.utils import event_concept_cache as concept_cache
from app.utils import game_markets_cache as gmc
from app.utils import related_futures_cache as rfc


class _ScalarResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}

    def get(self, k):
        return self.store.get(k)

    def setex(self, k, ttl, v):
        self.ttls[k] = ttl
        self.store[k] = v.encode() if isinstance(v, str) else v

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.store:
            return None
        self.store[k] = v.encode() if isinstance(v, str) else v
        if ex is not None:
            self.ttls[k] = ex
        return True

    def delete(self, k):
        self.ttls.pop(k, None)
        return int(self.store.pop(k, None) is not None)


class _SessionWithEventSchedule:
    def __init__(
        self,
        commence_time=None,
        *,
        status: str = "scheduled",
        fail: bool = False,
        row_present: bool = True,
    ):
        self.commence_time = commence_time
        self.status = status
        self.fail = fail
        self.row_present = row_present
        self.scalar_calls = 0
        self.execute_calls = 0

    async def scalar(self, *_a, **_k):
        self.scalar_calls += 1
        if self.fail:
            raise RuntimeError("db unavailable")
        return self.commence_time

    async def execute(self, *_a, **_k):
        self.execute_calls += 1
        if self.fail:
            raise RuntimeError("db unavailable")
        row = (self.status, self.commence_time) if self.row_present else None
        return _ScalarResult(row)


@pytest.fixture(autouse=True)
def _clear_memos():
    events_route._related_futures_cache.clear()
    events_route._game_markets_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()
    yield
    events_route._related_futures_cache.clear()
    events_route._game_markets_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()


def _rf_body(event_id: int = 7) -> dict:
    return {
        "event_id": event_id,
        "home_team": "Home",
        "away_team": "Away",
        "home_team_futures": [],
        "away_team_futures": [],
        "series_markets": [],
        "total_count": 0,
        "summary": None,
        "event_status": "scheduled",
        "box_score": [],
        "game_period": None,
        "game_clock": None,
        "league_context": None,
    }


def _gm_body(event_id: int = 7) -> dict:
    return {
        "event_id": event_id,
        "status": "scheduled",
        "moneylines": [],
        "spreads": [],
        "totals": [],
        "player_props": [],
    }


def _stamped_tier(
    tier,
    *,
    status: str,
    age_s: float,
    commence_in_s: float | None = None,
    now: datetime | None = None,
    raw_commence: object = None,
    open_winner_quote: object = None,
) -> dict:
    ref = now or datetime.now(timezone.utc)
    created = ref - timedelta(seconds=age_s)
    commence = (
        ref + timedelta(seconds=commence_in_s) if commence_in_s is not None else None
    )
    body = _rf_body() if tier is rfc else _gm_body()
    if open_winner_quote is not None:
        body[gmc.OPEN_WINNER_QUOTE_FIELD] = open_winner_quote
    if tier is rfc:
        payload = rfc.stamp(
            body,
            source_status=status,
            created_at=created,
            source_commence_time=commence,
        )
    else:
        payload = gmc.stamp(
            body,
            source_status=status,
            created_at=created,
        )
    if raw_commence is not None:
        payload[concept_cache.ENVELOPE_FIELD][rfc.SOURCE_COMMENCE_TIME_FIELD] = (
            raw_commence
        )
    return payload


# ---------------------------------------------------------------------------
# Ceiling & fresh TTL invariants across tiers
# ---------------------------------------------------------------------------


def test_scheduled_ceiling_is_ten_minutes_on_related_futures_and_game_markets_stays_150s():
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    stamped_rf = _stamped_tier(
        rfc, status="scheduled", age_s=10, commence_in_s=7200, now=now
    )
    stamped_gm = _stamped_tier(gmc, status="scheduled", age_s=10, now=now)
    assert rfc.STALE_SERVE_CEILING_LIVE == 150
    assert rfc.STALE_SERVE_CEILING_SCHEDULED == 600
    assert not hasattr(gmc, "STALE_SERVE_CEILING_SCHEDULED")
    # Status-only calls keep the page-level invariant matching `game_markets_cache`.
    assert rfc.stale_serve_ceiling_seconds("scheduled") == 150
    assert gmc.stale_serve_ceiling_seconds("scheduled") == 150
    # Only stamped scheduled `/related-futures` payloads get the 600 s ceiling.
    assert rfc.stale_serve_ceiling_seconds("scheduled", stamped_rf) == 600
    assert gmc.stale_serve_ceiling_seconds("scheduled", stamped_gm) == 150
    assert rfc.stale_serve_ceiling_seconds("live") == 150
    assert gmc.stale_serve_ceiling_seconds("live") == 150
    assert rfc.stale_serve_ceiling_seconds("completed") == 18000
    assert gmc.stale_serve_ceiling_seconds("completed") == 18000
    # Tier-specific fresh TTLs remain untouched.
    assert rfc.fresh_ttl("scheduled") == rfc.FRESH_TTL_LIVE == 60
    assert gmc.fresh_ttl("scheduled") == gmc.FRESH_TTL_LIVE == 30


# ---------------------------------------------------------------------------
# Mirror servability bounds: 10 min pre-kickoff ceiling, kickoff cap, legacy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("age_s", [151, 300, 599])
def test_pre_kickoff_scheduled_related_futures_mirror_is_servable_up_to_ten_minutes(
    age_s,
):
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    payload = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=age_s,
        commence_in_s=7200,
        now=now,
    )
    assert rfc.mirror_is_servable(payload, now=now) == (True, "fresh_enough")


def test_pre_kickoff_scheduled_related_futures_mirror_past_ten_minutes_is_refused():
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    payload = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=601,
        commence_in_s=7200,
        now=now,
    )
    assert rfc.mirror_is_servable(payload, now=now) == (False, "too_old")


def test_game_markets_scheduled_mirror_keeps_150s_ceiling():
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    over = _stamped_tier(
        gmc,
        status="scheduled",
        age_s=151,
        commence_in_s=7200,
        raw_commence=(now + timedelta(seconds=7200)).isoformat(),
        now=now,
    )
    assert gmc.mirror_is_servable(over, now=now) == (False, "too_old")


@pytest.mark.parametrize("commence_in_s", [0, -1, -300])
def test_scheduled_related_futures_mirror_at_or_past_kickoff_is_refused_immediately(
    commence_in_s,
):
    """Even a 70 s young scheduled mirror must not leak once kickoff is reached."""
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    payload = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=70,
        commence_in_s=commence_in_s,
        now=now,
    )
    assert rfc.mirror_is_servable(payload, now=now) == (False, "kickoff_passed")


@pytest.mark.parametrize("raw_commence", [None, "not-a-timestamp", ""])
def test_legacy_scheduled_mirror_without_valid_commence_time_fails_closed_at_150s(
    raw_commence,
):
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    young = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=140,
        commence_in_s=None,
        now=now,
        raw_commence=raw_commence,
    )
    over = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=151,
        commence_in_s=None,
        now=now,
        raw_commence=raw_commence,
    )
    assert rfc.mirror_is_servable(young, now=now) == (True, "fresh_enough")
    assert rfc.mirror_is_servable(over, now=now) == (False, "too_old")


@pytest.mark.parametrize("tier", [rfc, gmc], ids=["related_futures", "game_markets"])
def test_live_and_completed_ceilings_are_unaffected_by_commence_time(tier):
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    live_over = _stamped_tier(
        tier, status="live", age_s=151, commence_in_s=7200, now=now
    )
    assert tier.mirror_is_servable(live_over, now=now) == (False, "too_old")

    final_ok = _stamped_tier(
        tier, status="completed", age_s=4 * 3600, commence_in_s=-5 * 3600, now=now
    )
    assert tier.mirror_is_servable(final_ok, now=now) == (True, "fresh_enough")

    if tier is gmc:
        open_quote_over = _stamped_tier(
            gmc,
            status="completed",
            age_s=200,
            now=now,
            open_winner_quote={"probability": 0.99},
        )
        assert gmc.mirror_is_servable(open_quote_over, now=now) == (False, "too_old")


# ---------------------------------------------------------------------------
# Live schedule check (> 150 s scheduled mirrors verify live DB state)
# ---------------------------------------------------------------------------


def test_extended_live_check_threshold_and_live_event_rules():
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    starts_in_2h = now + timedelta(hours=2)

    under_150 = _stamped_tier(
        rfc, status="scheduled", age_s=150, commence_in_s=7200, now=now
    )
    over_150 = _stamped_tier(
        rfc, status="scheduled", age_s=151, commence_in_s=7200, now=now
    )
    live_payload = _stamped_tier(
        rfc, status="live", age_s=200, commence_in_s=7200, now=now
    )
    assert rfc.extended_scheduled_mirror_needs_live_check(under_150, now=now) is False
    assert rfc.extended_scheduled_mirror_needs_live_check(over_150, now=now) is True
    assert rfc.extended_scheduled_mirror_needs_live_check(live_payload, now=now) is False

    assert rfc.live_event_allows_scheduled_mirror(
        over_150, "scheduled", starts_in_2h, now=now
    ) == (True, "still_scheduled")
    assert rfc.live_event_allows_scheduled_mirror(
        over_150, "live", starts_in_2h, now=now
    ) == (False, "status_changed")
    assert rfc.live_event_allows_scheduled_mirror(
        over_150, "scheduled", now - timedelta(minutes=5), now=now
    ) == (False, "live_kickoff_passed")
    assert rfc.live_event_allows_scheduled_mirror(
        over_150, "scheduled", now + timedelta(minutes=30), now=now
    ) == (False, "commence_time_moved")
    assert rfc.live_event_allows_scheduled_mirror(
        over_150, "scheduled", None, now=now
    ) == (False, "commence_time_missing")


# ---------------------------------------------------------------------------
# End-to-end route tests: stale_ok + async refresh + live DB guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_related_futures_under_150s_serves_stale_ok_without_db_read():
    rc = _FakeRedis()
    builds = []
    refreshed = []
    mirror = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=120,
        commence_in_s=7200,
        now=datetime.now(timezone.utc),
    )
    rfc.write(7, mirror, rc=rc)
    rc.delete(rfc.keys_for(7).primary)

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        return _rf_body(event_id), "scheduled", [], True

    def _fake_refresh(name, rebuild):
        refreshed.append(name)
        return True

    db = _SessionWithEventSchedule(datetime.now(timezone.utc) + timedelta(hours=2))
    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ), patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
        served = await events_route.get_related_futures(7, False, db)

    assert builds == []
    assert db.execute_calls == 0
    assert refreshed == ["related_futures:7"]
    assert served[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"


@pytest.mark.asyncio
async def test_route_related_futures_past_150s_checks_live_db_and_serves_pre_kickoff():
    rc = _FakeRedis()
    builds = []
    refreshed = []
    commence = datetime.now(timezone.utc) + timedelta(hours=2)

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        return _rf_body(event_id), "scheduled", [], True

    def _fake_refresh(name, rebuild):
        refreshed.append(name)
        return True

    # Build once via route with DB commence_time stamped.
    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ):
        publish_db = _SessionWithEventSchedule(commence)
        first = await events_route.get_related_futures(7, False, publish_db)
        assert first[concept_cache.ENVELOPE_FIELD][rfc.SOURCE_COMMENCE_TIME_FIELD]
        assert publish_db.scalar_calls == 1

    # Simulate 5 minutes later (age=300s > 150s and < 600s, still scheduled pre-kickoff):
    # route performs 1 live (status, commence_time) read, serves `stale_ok`, refreshes async.
    older = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=300,
        now=datetime.now(timezone.utc),
    )
    older = rfc.with_source_commence_time(older, commence)
    rfc.write(7, older, rc=rc)
    rc.delete(rfc.keys_for(7).primary)
    events_route._related_futures_cache.clear()

    check_db = _SessionWithEventSchedule(commence, status="scheduled")
    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ), patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
        served = await events_route.get_related_futures(7, False, check_db)

    assert builds == [7]
    assert check_db.execute_calls == 1
    assert refreshed == ["related_futures:7"]
    assert served[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"


@pytest.mark.asyncio
async def test_route_related_futures_refuses_extended_mirror_when_event_is_live_now():
    """Guard: mirror stamped 'scheduled, starts in 2h' is refused when game is live now."""
    rc = _FakeRedis()
    builds = []
    refreshed = []
    now = datetime.now(timezone.utc)
    starts_in_2h = now + timedelta(hours=2)
    older = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=300,
        now=now,
    )
    older = rfc.with_source_commence_time(older, starts_in_2h)
    rfc.write(7, older, rc=rc)
    rc.delete(rfc.keys_for(7).primary)

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        body = _rf_body(event_id)
        body["event_status"] = "live"
        return body, "live", [], True

    def _fake_refresh(name, rebuild):
        refreshed.append(name)
        return True

    live_db = _SessionWithEventSchedule(starts_in_2h, status="live")
    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ), patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
        rebuilt = await events_route.get_related_futures(7, False, live_db)

    assert live_db.execute_calls == 1
    assert refreshed == []
    assert builds == [7]
    assert rebuilt[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


@pytest.mark.asyncio
async def test_route_related_futures_refuses_extended_mirror_when_kickoff_moved_5m_ago():
    """Guard: mirror stamped 'scheduled, starts in 2h' is refused if start moved to 5m ago."""
    rc = _FakeRedis()
    builds = []
    refreshed = []
    now = datetime.now(timezone.utc)
    starts_in_2h = now + timedelta(hours=2)
    five_min_ago = now - timedelta(minutes=5)
    older = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=300,
        now=now,
    )
    older = rfc.with_source_commence_time(older, starts_in_2h)
    rfc.write(7, older, rc=rc)
    rc.delete(rfc.keys_for(7).primary)

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        body = _rf_body(event_id)
        body["event_status"] = "scheduled"
        return body, "scheduled", [], True

    def _fake_refresh(name, rebuild):
        refreshed.append(name)
        return True

    moved_db = _SessionWithEventSchedule(five_min_ago, status="scheduled")
    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ), patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
        rebuilt = await events_route.get_related_futures(7, False, moved_db)

    assert moved_db.execute_calls == 1
    assert refreshed == []
    assert builds == [7]
    assert rebuilt[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["moved_earlier_in_future", "db_failure"])
async def test_route_related_futures_refuses_extended_mirror_on_moved_start_or_db_error(
    case,
):
    rc = _FakeRedis()
    builds = []
    now = datetime.now(timezone.utc)
    starts_in_2h = now + timedelta(hours=2)
    older = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=300,
        now=now,
    )
    older = rfc.with_source_commence_time(older, starts_in_2h)
    rfc.write(7, older, rc=rc)
    rc.delete(rfc.keys_for(7).primary)

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        return _rf_body(event_id), "scheduled", [], True

    db = (
        _SessionWithEventSchedule(now + timedelta(minutes=30), status="scheduled")
        if case == "moved_earlier_in_future"
        else _SessionWithEventSchedule(fail=True)
    )
    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ):
        rebuilt = await events_route.get_related_futures(7, False, db)

    assert db.execute_calls == 1
    assert builds == [7]
    assert rebuilt[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


@pytest.mark.asyncio
async def test_route_related_futures_refuses_mirror_after_kickoff_and_rebuilds_sync():
    rc = _FakeRedis()
    builds = []
    commence = datetime.now(timezone.utc) - timedelta(seconds=10)
    past_kickoff = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=70,
        now=datetime.now(timezone.utc),
    )
    past_kickoff = rfc.with_source_commence_time(past_kickoff, commence)
    rfc.write(7, past_kickoff, rc=rc)
    rc.delete(rfc.keys_for(7).primary)

    async def _fake_build(event_id, db, debug=False):
        builds.append(event_id)
        body = _rf_body(event_id)
        body["event_status"] = "live"
        return body, "live", [], True

    db = _SessionWithEventSchedule(commence, status="scheduled")
    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ):
        rebuilt = await events_route.get_related_futures(7, False, db)

    assert db.execute_calls == 0
    assert builds == [7]
    assert rebuilt[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


@pytest.mark.asyncio
async def test_route_game_markets_stays_at_150s_ceiling_and_does_not_query_commence_time():
    rc = _FakeRedis()
    builds = []
    refreshed = []

    async def _fake_build(event_id, db):
        builds.append(event_id)
        return _gm_body(event_id), "scheduled", []

    def _fake_refresh(name, rebuild):
        refreshed.append(name)
        return True

    over_150 = _stamped_tier(
        gmc,
        status="scheduled",
        age_s=151,
        now=datetime.now(timezone.utc),
    )
    gmc.write(7, over_150, rc=rc)
    rc.delete(gmc.keys_for(7).primary)

    db = _SessionWithEventSchedule(datetime.now(timezone.utc) + timedelta(hours=2))
    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ), patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
        rebuilt = await events_route.get_game_markets(7, db)

    assert builds == [7]
    assert refreshed == []
    assert db.scalar_calls == 0
    assert db.execute_calls == 0
    assert rebuilt[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


# ---------------------------------------------------------------------------
# Publish helpers stamp only `scheduled` on `/related-futures` and fail closed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_stamps_commence_time_only_for_scheduled_rf_and_handles_db_errors():
    rc = _FakeRedis()
    future_kickoff = datetime(2026, 11, 28, 18, 0, tzinfo=timezone.utc)

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        gmc, "get_client", return_value=rc
    ):
        # Scheduled `/related-futures` with valid commence_time -> stamped.
        sched_db = _SessionWithEventSchedule(future_kickoff)
        sched_rf = await events_route._publish_related_futures(
            7, "scheduled", _rf_body(7), [], sched_db
        )
        assert sched_db.scalar_calls == 1
        assert rfc.source_commence_time_of(sched_rf) == future_kickoff

        # `/game-markets` does not ride along (zero commence_time query/stamp).
        sched_gm_db = _SessionWithEventSchedule(future_kickoff)
        sched_gm = await events_route._publish_game_markets(
            7, "scheduled", _gm_body(7), [], sched_gm_db
        )
        assert sched_gm_db.scalar_calls == 0
        assert (
            rfc.SOURCE_COMMENCE_TIME_FIELD
            not in sched_gm[concept_cache.ENVELOPE_FIELD]
        )

        # Live `/related-futures` -> zero commence_time DB lookup and no field stamped.
        live_db = _SessionWithEventSchedule(future_kickoff)
        live_rf = await events_route._publish_related_futures(
            8, "live", _rf_body(8), [], live_db
        )
        assert live_db.scalar_calls == 0
        assert rfc.source_commence_time_of(live_rf) is None

        # Failing DB -> no raise, omits field, ceiling fails closed at 150 s.
        bad_db = _SessionWithEventSchedule(fail=True)
        degraded = await events_route._publish_related_futures(
            9, "scheduled", _rf_body(9), [], bad_db
        )
        assert bad_db.scalar_calls == 1
        assert rfc.source_commence_time_of(degraded) is None
        assert rfc.stale_serve_ceiling_seconds("scheduled", degraded) == 150
