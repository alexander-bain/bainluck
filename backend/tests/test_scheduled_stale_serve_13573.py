"""#13573: Keep scheduled Season Futures / game-markets copies servable while
rebuilding (up to 1 hour pre-kickoff, hard-capped at `source_commence_time`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.routes import events as events_route
from app.utils import event_concept_cache as concept_cache
from app.utils import game_markets_cache as gmc
from app.utils import related_futures_cache as rfc


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


class _SessionWithCommenceTime:
    def __init__(self, commence_time=None, *, fail: bool = False):
        self.commence_time = commence_time
        self.fail = fail
        self.scalar_calls = 0

    async def scalar(self, *_a, **_k):
        self.scalar_calls += 1
        if self.fail:
            raise RuntimeError("db unavailable")
        return self.commence_time


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
    payload = tier.stamp(
        body,
        source_status=status,
        created_at=created,
        source_commence_time=commence,
    )
    if raw_commence is not None:
        payload[concept_cache.ENVELOPE_FIELD][gmc.SOURCE_COMMENCE_TIME_FIELD] = (
            raw_commence
        )
    return payload


# ---------------------------------------------------------------------------
# Ceiling & fresh TTL invariants across both tiers
# ---------------------------------------------------------------------------


def test_scheduled_ceiling_is_one_hour_and_shared_while_fresh_ttls_stay_unchanged():
    assert rfc.STALE_SERVE_CEILING_SCHEDULED == 3600
    assert gmc.STALE_SERVE_CEILING_SCHEDULED == 3600
    assert rfc.stale_serve_ceiling_seconds("scheduled") == 3600
    assert gmc.stale_serve_ceiling_seconds("scheduled") == 3600
    assert rfc.stale_serve_ceiling_seconds("live") == 150
    assert gmc.stale_serve_ceiling_seconds("live") == 150
    assert rfc.stale_serve_ceiling_seconds("completed") == 18000
    assert gmc.stale_serve_ceiling_seconds("completed") == 18000
    # Tier-specific fresh TTLs remain untouched.
    assert rfc.fresh_ttl("scheduled") == rfc.FRESH_TTL_LIVE == 60
    assert gmc.fresh_ttl("scheduled") == gmc.FRESH_TTL_LIVE == 30


# ---------------------------------------------------------------------------
# Mirror servability bounds: 1 h pre-kickoff ceiling, kickoff cap, legacy fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tier", [rfc, gmc], ids=["related_futures", "game_markets"])
@pytest.mark.parametrize("age_s", [200, 1800, 3599])
def test_pre_kickoff_scheduled_mirror_is_servable_up_to_one_hour(tier, age_s):
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    payload = _stamped_tier(
        tier,
        status="scheduled",
        age_s=age_s,
        commence_in_s=7200,
        now=now,
    )
    assert tier.mirror_is_servable(payload, now=now) == (True, "fresh_enough")


@pytest.mark.parametrize("tier", [rfc, gmc], ids=["related_futures", "game_markets"])
def test_pre_kickoff_scheduled_mirror_past_one_hour_is_refused(tier):
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    payload = _stamped_tier(
        tier,
        status="scheduled",
        age_s=3601,
        commence_in_s=7200,
        now=now,
    )
    assert tier.mirror_is_servable(payload, now=now) == (False, "too_old")


@pytest.mark.parametrize("tier", [rfc, gmc], ids=["related_futures", "game_markets"])
@pytest.mark.parametrize("commence_in_s", [0, -1, -300])
def test_scheduled_mirror_at_or_past_kickoff_is_refused_immediately(tier, commence_in_s):
    """Even a 70 s young scheduled mirror must not leak once kickoff is reached."""
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    payload = _stamped_tier(
        tier,
        status="scheduled",
        age_s=70,
        commence_in_s=commence_in_s,
        now=now,
    )
    assert tier.mirror_is_servable(payload, now=now) == (False, "kickoff_passed")


@pytest.mark.parametrize("tier", [rfc, gmc], ids=["related_futures", "game_markets"])
@pytest.mark.parametrize("raw_commence", [None, "not-a-timestamp", ""])
def test_legacy_scheduled_mirror_without_valid_commence_time_fails_closed_at_150s(
    tier, raw_commence
):
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    young = _stamped_tier(
        tier,
        status="scheduled",
        age_s=140,
        commence_in_s=None,
        now=now,
        raw_commence=raw_commence,
    )
    over = _stamped_tier(
        tier,
        status="scheduled",
        age_s=151,
        commence_in_s=None,
        now=now,
        raw_commence=raw_commence,
    )
    assert tier.mirror_is_servable(young, now=now) == (True, "fresh_enough")
    assert tier.mirror_is_servable(over, now=now) == (False, "too_old")


@pytest.mark.parametrize("tier", [rfc, gmc], ids=["related_futures", "game_markets"])
def test_live_and_completed_ceilings_are_unaffected_by_commence_time(tier):
    now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
    # Even if a `live` payload somehow carries a future kickoff string, it keeps the 150 s ceiling.
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
# End-to-end route tests: section stays visible via `stale_ok` + async refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_related_futures_serves_pre_kickoff_mirror_past_150s_and_rebuilds_async():
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
        db = _SessionWithCommenceTime(commence)
        first = await events_route.get_related_futures(7, False, db)
        assert first[concept_cache.ENVELOPE_FIELD][rfc.SOURCE_COMMENCE_TIME_FIELD]
        assert db.scalar_calls == 1

    # Simulate 36 minutes later (primary expired, mirror age ~2,160 s, still pre-kickoff):
    # age exceeds 150 s, yet under 3,600 s so reader sees `stale_ok` and schedules 1 rebuild.
    older = _stamped_tier(
        rfc,
        status="scheduled",
        age_s=2160,
        now=datetime.now(timezone.utc),
        commence_in_s=7200,
    )
    rfc.write(7, older, rc=rc)
    rc.delete(rfc.keys_for(7).primary)
    events_route._related_futures_cache.clear()

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ), patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
        served = await events_route.get_related_futures(7, False, _SessionWithCommenceTime())

    assert builds == [7], "pre-kickoff mirror should keep the section populated without blocking"
    assert refreshed == ["related_futures:7"]
    assert served[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"


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

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        events_route, "_build_related_futures", _fake_build
    ):
        rebuilt = await events_route.get_related_futures(7, False, _SessionWithCommenceTime())

    assert builds == [7]
    assert rebuilt[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


@pytest.mark.asyncio
async def test_route_game_markets_obeys_same_scheduled_pre_kickoff_and_kickoff_law():
    rc = _FakeRedis()
    builds = []
    refreshed = []

    async def _fake_build(event_id, db):
        builds.append(event_id)
        return _gm_body(event_id), "scheduled", []

    def _fake_refresh(name, rebuild):
        refreshed.append(name)
        return True

    pre_kickoff = _stamped_tier(
        gmc,
        status="scheduled",
        age_s=2160,
        now=datetime.now(timezone.utc),
        commence_in_s=7200,
    )
    gmc.write(7, pre_kickoff, rc=rc)
    rc.delete(gmc.keys_for(7).primary)

    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ), patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
        served = await events_route.get_game_markets(7, _SessionWithCommenceTime())

    assert builds == []
    assert refreshed == ["game_markets:7"]
    assert served[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"

    # Past kickoff forces synchronous rebuild.
    past_kickoff = _stamped_tier(
        gmc,
        status="scheduled",
        age_s=40,
        now=datetime.now(timezone.utc),
        commence_in_s=-5,
    )
    gmc.write(7, past_kickoff, rc=rc)
    rc.delete(gmc.keys_for(7).primary)
    events_route._game_markets_cache.clear()

    with patch.object(gmc, "get_client", return_value=rc), patch.object(
        events_route, "_build_game_markets", _fake_build
    ):
        rebuilt = await events_route.get_game_markets(7, _SessionWithCommenceTime())

    assert builds == [7]
    assert rebuilt[concept_cache.ENVELOPE_FIELD]["availability"] == "live"


# ---------------------------------------------------------------------------
# Publish helpers stamp only `scheduled` and degrade fail-closed on DB errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_stamps_commence_time_only_for_scheduled_and_handles_db_errors():
    rc = _FakeRedis()
    future_kickoff = datetime(2026, 11, 28, 18, 0, tzinfo=timezone.utc)

    with patch.object(rfc, "get_client", return_value=rc), patch.object(
        gmc, "get_client", return_value=rc
    ):
        # Scheduled with valid commence_time -> stamped.
        sched_db = _SessionWithCommenceTime(future_kickoff)
        sched_rf = await events_route._publish_related_futures(
            7, "scheduled", _rf_body(7), [], sched_db
        )
        assert sched_db.scalar_calls == 1
        assert rfc.source_commence_time_of(sched_rf) == future_kickoff

        sched_gm_db = _SessionWithCommenceTime(future_kickoff)
        sched_gm = await events_route._publish_game_markets(
            7, "scheduled", _gm_body(7), [], sched_gm_db
        )
        assert sched_gm_db.scalar_calls == 1
        assert gmc.source_commence_time_of(sched_gm) == future_kickoff

        # Live and completed -> zero commence_time DB lookup and no field stamped.
        live_db = _SessionWithCommenceTime(future_kickoff)
        live_rf = await events_route._publish_related_futures(
            8, "live", _rf_body(8), [], live_db
        )
        assert live_db.scalar_calls == 0
        assert rfc.source_commence_time_of(live_rf) is None

        # Failing DB -> no raise, omits field, ceiling fails closed at 150 s.
        bad_db = _SessionWithCommenceTime(fail=True)
        degraded = await events_route._publish_related_futures(
            9, "scheduled", _rf_body(9), [], bad_db
        )
        assert bad_db.scalar_calls == 1
        assert rfc.source_commence_time_of(degraded) is None
        assert gmc.stale_serve_ceiling_seconds("scheduled", degraded) == 150
