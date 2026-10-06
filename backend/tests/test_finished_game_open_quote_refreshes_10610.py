"""A FINISHED GAME STOPS HOLDING AN OPEN WINNER QUOTE FOR AN HOUR. #10610 (child of #9484).

═══ WHAT WAS SERVED ═══

Production 2026-10-06: ev15324542 served Polymarket 64252764 as `open` at 99% at
10:59Z, although the venue resolved it at 10:37Z. The quote was right when the
payload was built; the payload was then held for `FRESH_TTL_FINAL` (an hour)
because the game's STATUS was final — and a final game's markets "stop moving".
`open_winner_quote` is non-null exactly when one of them has not stopped.

═══ WHY EVERY LAYER IS TESTED ═══

The hour is chosen in FOUR places, and fixing any subset leaves the hour in
place for the reader:

| layer | consumer |
|---|---|
| Redis primary TTL | `gmc.write` |
| Redis primary read | `gmc.read` (a pre-fix slot stored for 3600 s) |
| mirror ceiling | `gmc.mirror_is_servable` |
| L1 memo | `events._read_game_markets_memo` (chose 3600 independently) |

Each class below drives the REAL function for one layer and fails if that layer
alone is reverted to a status-only decision. `TestTheWholeLadder` drives the
real route through all of them.

═══ WHAT MUST NOT CHANGE ═══

* A final body whose quote is null or absent keeps the hour fresh / five hours
  stale.
* Live and scheduled bodies keep 30 s / 150 s, quote or no quote.
* The L1 age is measured from the ORIGINAL build (#6394), not the promotion.
* Build refusal (#6355) and the missing-`created_at` refusal are untouched.

This is NOT a 30-second venue-to-screen guarantee: it bounds how long a cached
body may go on claiming the quote is open, not how fast the builder learns.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.routes import events as events_route
from app.utils import event_concept_cache as concept_cache
from app.utils import game_markets_cache as gmc

_ABSENT = object()

_QUOTE = {
    "market_id": 64252764,
    "source": "polymarket",
    "outcomes": [
        {"outcome_id": 1, "side": "home", "name": "Home", "probability": 0.99},
        {"outcome_id": 2, "side": "away", "name": "Away", "probability": 0.01},
    ],
}


class _FakeRedis:
    """In-memory Redis that records TTLs and never expires anything — so a read
    sees exactly what a slot written with a long TTL would still hold."""

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


class _Session:
    async def scalar(self, *_a, **_k):
        return None


def _body(quote=_QUOTE, event_id: int = 7) -> dict:
    body = {
        "event_id": event_id,
        "home_team": "Home",
        "away_team": "Away",
        "status": "completed",
        "totals": [],
        "player_props": [],
        "spreads": [],
        "matchups": [],
        "other": [],
        "pace": None,
        "props_script": [],
        "closed_winner_market_ids": [],
    }
    if quote is not _ABSENT:
        body["open_winner_quote"] = quote
    return body


def _stamped(status: str, *, age_s: float, quote=_QUOTE, event_id: int = 7) -> dict:
    created = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return gmc.stamp(
        _body(quote, event_id), source_status=status, created_at=created
    )


def _write_both(rc, payload, *, primary_ttl=3600, event_id: int = 7) -> None:
    """Store bytes the way a PRE-#10610 writer did: primary for the hour."""
    concept_cache.write_payload(
        rc, gmc.keys_for(event_id), payload, primary_ttl=primary_ttl
    )


@pytest.fixture(autouse=True)
def _clear_memo():
    events_route._game_markets_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()
    yield
    events_route._game_markets_cache.clear()
    events_route._STALE_REFRESH_INFLIGHT.clear()


# ---------------------------------------------------------------------------
# 1. The Redis primary WRITE.
# ---------------------------------------------------------------------------


class TestThePrimaryWrite:
    @pytest.mark.parametrize("status", ["completed", "closed"])
    def test_a_final_body_with_an_open_quote_is_stored_for_the_live_ttl(self, status):
        rc = _FakeRedis()
        assert gmc.write(7, _stamped(status, age_s=0), rc=rc) is True
        keys = gmc.keys_for(7)
        assert rc.ttls[keys.primary] == gmc.FRESH_TTL_LIVE == 30
        # The mirror keeps its 24h storage lifetime; only its SERVE age moves.
        assert rc.ttls[keys.stale] == gmc.STALE_TTL

    @pytest.mark.parametrize("quote", [None, _ABSENT])
    def test_a_final_body_with_no_open_quote_keeps_the_hour(self, quote):
        rc = _FakeRedis()
        gmc.write(7, _stamped("completed", age_s=0, quote=quote), rc=rc)
        assert rc.ttls[gmc.keys_for(7).primary] == gmc.FRESH_TTL_FINAL == 3600

    @pytest.mark.parametrize("status", ["live", "scheduled", "in_progress", ""])
    @pytest.mark.parametrize("quote", [_QUOTE, None, _ABSENT])
    def test_unfinished_bodies_are_unchanged(self, status, quote):
        rc = _FakeRedis()
        gmc.write(7, _stamped(status, age_s=0, quote=quote), rc=rc)
        assert rc.ttls[gmc.keys_for(7).primary] == gmc.FRESH_TTL_LIVE

    @pytest.mark.asyncio
    async def test_the_route_s_publish_path_stores_the_short_ttl(self):
        """The writer the route actually calls, not just the helper."""
        rc = _FakeRedis()
        with patch.object(gmc, "get_client", return_value=rc):
            await events_route._publish_game_markets(
                7, "completed", _body(), [], _Session()
            )
        assert rc.ttls[gmc.keys_for(7).primary] == gmc.FRESH_TTL_LIVE


# ---------------------------------------------------------------------------
# 2. The mirror CEILING.
# ---------------------------------------------------------------------------


class TestTheMirrorCeiling:
    def test_an_open_quote_mirror_is_servable_inside_150s(self):
        ok, reason = gmc.mirror_is_servable(_stamped("completed", age_s=140))
        assert (ok, reason) == (True, "fresh_enough")

    def test_an_open_quote_mirror_is_refused_past_150s_not_five_hours(self):
        """BEFORE.json: an 1800 s-old open-quote mirror was accepted."""
        for age in (151, 1800, 17_000):
            ok, reason = gmc.mirror_is_servable(_stamped("completed", age_s=age))
            assert (ok, reason) == (False, "too_old"), age

    @pytest.mark.parametrize("quote", [None, _ABSENT])
    def test_a_no_quote_final_mirror_keeps_the_five_hour_ceiling(self, quote):
        ok, _ = gmc.mirror_is_servable(_stamped("completed", age_s=1800, quote=quote))
        assert ok
        ok, reason = gmc.mirror_is_servable(
            _stamped("completed", age_s=5 * 3600 + 5, quote=quote)
        )
        assert (ok, reason) == (False, "too_old")

    def test_a_live_mirror_keeps_150s(self):
        assert gmc.mirror_is_servable(_stamped("live", age_s=140, quote=None))[0]
        assert not gmc.mirror_is_servable(_stamped("live", age_s=151, quote=None))[0]

    def test_a_status_only_caller_still_gets_the_status_ceiling(self):
        """`related_futures_cache` passes a status and no body."""
        assert gmc.stale_serve_ceiling_seconds("completed") == 5 * 3600
        assert gmc.stale_serve_ceiling_seconds("live") == 150

    def test_missing_created_at_is_still_refused(self):
        payload = _stamped("completed", age_s=0)
        payload[concept_cache.ENVELOPE_FIELD].pop("created_at")
        assert gmc.mirror_is_servable(payload) == (False, "no_created_at")


# ---------------------------------------------------------------------------
# 3. The Redis primary READ — bytes a pre-#10610 writer stored for the hour.
# ---------------------------------------------------------------------------


class TestThePrimaryRead:
    def test_a_young_open_quote_primary_is_live(self):
        rc = _FakeRedis()
        _write_both(rc, _stamped("completed", age_s=10))
        body, state = gmc.read(7, rc=rc)
        assert state == "live"
        assert body["open_winner_quote"] == _QUOTE

    def test_an_hour_stored_open_quote_primary_past_30s_is_not_live(self):
        """The slot is still in Redis (written for 3600 s) — it must not read
        as `live`; it falls to the mirror, which serves it stale with a rebuild."""
        rc = _FakeRedis()
        _write_both(rc, _stamped("completed", age_s=60))
        body, state = gmc.read(7, rc=rc)
        assert state == "stale_ok"
        assert body[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"

    def test_past_150s_from_the_original_build_the_reader_rebuilds(self):
        rc = _FakeRedis()
        _write_both(rc, _stamped("completed", age_s=1800))
        assert gmc.read(7, rc=rc) == (None, "stale_too_old")

    @pytest.mark.parametrize("quote", [None, _ABSENT])
    def test_a_no_quote_final_primary_is_live_for_the_hour(self, quote):
        rc = _FakeRedis()
        _write_both(rc, _stamped("completed", age_s=1800, quote=quote))
        assert gmc.read(7, rc=rc)[1] == "live"

    def test_a_live_primary_is_not_age_checked(self):
        """Redis's own TTL bounds a live slot; a reader whose clock runs ahead of
        the writer's must not demote it. Unchanged behaviour."""
        rc = _FakeRedis()
        _write_both(rc, _stamped("live", age_s=40), primary_ttl=30)
        assert gmc.read(7, rc=rc)[1] == "live"

    def test_an_open_quote_primary_with_no_created_at_is_still_refused(self):
        """The envelope check refuses it before any TTL decision — unchanged."""
        rc = _FakeRedis()
        payload = _stamped("completed", age_s=0)
        payload[concept_cache.ENVELOPE_FIELD].pop("created_at")
        _write_both(rc, payload)
        assert gmc.read(7, rc=rc) == (None, "miss")

    def test_a_primary_with_no_parseable_age_counts_as_outlived(self):
        """Defensive arm for bytes that pass the envelope check but cannot be
        aged: never trusted as `live` for the hour."""
        payload = _stamped("completed", age_s=0)
        payload[concept_cache.ENVELOPE_FIELD]["created_at"] = "not-a-time"
        assert gmc.primary_outlived_fresh_ttl(payload) is True
        payload["open_winner_quote"] = None
        assert gmc.primary_outlived_fresh_ttl(payload) is False

    def test_another_build_s_primary_is_still_refused_first(self):
        rc = _FakeRedis()
        with patch.object(gmc, "current_build_id", return_value="v-old"):
            _write_both(rc, _stamped("completed", age_s=60))
        with patch.object(gmc, "current_build_id", return_value="v-next"):
            assert gmc.read(7, rc=rc) == (None, "stale_build")


# ---------------------------------------------------------------------------
# 4. The L1 memo.
# ---------------------------------------------------------------------------


class TestTheMemo:
    def _seed(self, status, *, age_s, quote=_QUOTE):
        body = gmc.with_availability(
            _stamped(status, age_s=age_s, quote=quote), gmc.AVAILABILITY_LIVE
        )
        events_route._game_markets_cache[7] = (
            time.time() - age_s,
            status,
            events_route._current_build_id(),
            body,
        )
        return body

    @pytest.mark.parametrize("status", ["completed", "closed"])
    def test_an_open_quote_entry_expires_at_30s(self, status):
        """BEFORE.json: L1 returned a 1800 s-old open quote."""
        self._seed(status, age_s=31)
        assert events_route._read_game_markets_memo(7) is None

    def test_an_open_quote_entry_inside_30s_still_hits(self):
        body = self._seed("completed", age_s=10)
        assert events_route._read_game_markets_memo(7) is body

    @pytest.mark.parametrize("quote", [None, _ABSENT])
    def test_a_no_quote_final_entry_keeps_the_hour(self, quote):
        body = self._seed("completed", age_s=1800, quote=quote)
        assert events_route._read_game_markets_memo(7) is body
        self._seed("completed", age_s=3601, quote=quote)
        assert events_route._read_game_markets_memo(7) is None

    def test_a_live_entry_is_unchanged(self):
        body = self._seed("live", age_s=20)
        assert events_route._read_game_markets_memo(7) is body
        self._seed("live", age_s=31)
        assert events_route._read_game_markets_memo(7) is None


# ---------------------------------------------------------------------------
# 5. The whole ladder, through the real route.
# ---------------------------------------------------------------------------


class TestTheWholeLadder:
    @pytest.mark.asyncio
    async def test_L2_to_L1_promotion_keeps_the_original_build_deadline(self):
        """L2 hands over a 25 s-old open-quote body as `live`. L1 must expire it
        5 s later, not 30 s after the promotion (#6394's seam, at 30 s)."""
        rc = _FakeRedis()
        _write_both(rc, _stamped("completed", age_s=25), primary_ttl=30)

        async def _must_not_build(event_id, db):  # pragma: no cover - guard
            raise AssertionError("L2 was supposed to serve")

        with patch.object(gmc, "get_client", return_value=rc), patch.object(
            events_route, "_build_game_markets", _must_not_build
        ):
            served = await events_route.get_game_markets(7, _Session())
        assert served[concept_cache.ENVELOPE_FIELD]["availability"] == "live"
        assert events_route._read_game_markets_memo(7) is not None

        later = time.time() + 6
        with patch("time.time", return_value=later):
            assert events_route._read_game_markets_memo(7) is None

    @pytest.mark.asyncio
    async def test_after_30s_an_ordinary_read_schedules_the_rebuild(self):
        """Every layer agrees: L1 misses, the hour-stored primary is not `live`,
        the mirror serves stale inside 150 s with ONE rebuild behind it."""
        rc = _FakeRedis()
        _write_both(rc, _stamped("completed", age_s=45))
        builds, scheduled = [], []

        async def _fake_build(event_id, db):
            builds.append(event_id)
            return _body(None), "completed", []

        def _fake_refresh(name, rebuild):
            scheduled.append(name)
            return True

        with patch.object(gmc, "get_client", return_value=rc), patch.object(
            events_route, "_build_game_markets", _fake_build
        ), patch.object(events_route, "_serve_stale_and_refresh", _fake_refresh):
            body = await events_route.get_game_markets(7, _Session())

        assert body[concept_cache.ENVELOPE_FIELD]["availability"] == "stale_ok"
        assert scheduled == ["game_markets:7"]
        assert builds == []
        assert 7 not in events_route._game_markets_cache

    @pytest.mark.asyncio
    async def test_past_150s_the_reader_rebuilds_and_the_closed_quote_keeps_the_hour(self):
        rc = _FakeRedis()
        _write_both(rc, _stamped("completed", age_s=1800))
        builds = []

        async def _fake_build(event_id, db):
            builds.append(event_id)
            return _body(None), "completed", []

        with patch.object(gmc, "get_client", return_value=rc), patch.object(
            events_route, "_build_game_markets", _fake_build
        ):
            body = await events_route.get_game_markets(7, _Session())

        assert builds == [7]
        assert body["open_winner_quote"] is None
        assert rc.ttls[gmc.keys_for(7).primary] == gmc.FRESH_TTL_FINAL
