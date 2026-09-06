"""#3389 — the league page's snapshot must not outlive the games on it.

THE DEFECT, as measured on production `0247b0ed` on Sat 2026-09-05 with eight MLS
matches in play. `GET /api/leagues/soccer_usa_mls` at 02:26Z returned a payload
built at ~00:36Z, because #1767's revalidation is entirely reader-driven and
nobody had opened the page for 1h50m. It printed:

    Charlotte FC v Houston Dynamo   status=live   0-0   ESPN clock 66'
    Inter Miami CF v Atlanta United status=live         kickoff 23:30Z

while `GET /api/events/15291063` said `completed`, `completed_at 01:40:32Z`, FT,
and `GET /api/events/15291061` said kickoff `01:05Z`. One producer, one row, two
hours apart: the league page was serving a photograph of a game and calling it
the game.

Two independent halves of the same clock, both pinned here:

1.  **The mirror had no age bound.** `LEAGUE_STALE_TTL` is 24 hours, which is
    right for a futures board and wrong for a match. Bounded now by
    `LEAGUE_GAMES_MIRROR_MAX_AGE`, and only for payloads that carry games.

2.  **Revalidation started only after the primary had already expired.** The
    rebuild is delivered over the `background` queue — 167s, measured that night
    behind twelve `warm_typeahead` jobs — against a 300s TTL, so a league under
    continuous traffic spent about a third of its life on the mirror. Timeline,
    one read every ten seconds: `fresh` 02:35:52 → 02:40:49, `stale` 02:41:00 →
    02:43:39, `fresh` 02:43:47. `LEAGUE_EARLY_REVALIDATE_AFTER` moves the same
    single dispatch earlier so its replacement lands before the slot expires.

These assert on the SERVE DECISION — which slot the reader got and what was
dispatched — because that is where the defect lived. The payload contract is
`test_route_league_futures.py`'s and the single-flight mechanism is
`test_route_league_revalidation.py`'s; restating either would give two graders
one input (ruling 021).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.routes.league_futures import (
    GAMES_RAIL_KEYS,
    LEAGUE_EARLY_REVALIDATE_AFTER,
    LEAGUE_GAMES_MIRROR_MAX_AGE,
    LEAGUE_PRIMARY_TTL,
    LEAGUE_STALE_TTL,
    build_league,
    has_games,
    mirror_is_too_old,
    payload_age_seconds,
    league_cache_keys,
)
from tests.integration.test_route_league_revalidation import FakeRedis

pytestmark = pytest.mark.asyncio

SPORT = "soccer_usa_mls"

#: The row that was wrong, verbatim from the production read. Kept whole rather
#: than reduced to an id: the point of the incident is that a payload can be
#: internally coherent — a status, a score and a running clock that all agree
#: with each other — and still be two hours behind the match it describes.
FROZEN_MATCH = {
    "id": 15291063,
    "home_team": "Charlotte FC",
    "away_team": "Houston Dynamo",
    "status": "live",
    "commence_time": "2026-09-05T23:30:00+00:00",
    "home_score": 0,
    "away_score": 0,
    "espn": {"period": "66'", "game_clock": "66'"},
}


def _mirror(built_ago_seconds=None, games=(FROZEN_MATCH,), sections=None, stamped=True):
    """A cached league payload, aged by `built_ago_seconds`.

    `stamped=False` reproduces every mirror already sitting in production Redis
    when this ships — written before `built_at` existed. Those must fail closed,
    or the fix would exempt exactly the payloads that motivated it.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sport_key": SPORT,
        "sections": sections if sections is not None else {},
        "upcoming_games": list(games),
        "recent_results": [],
        "unreported_games": [],
        "availability": "fresh",
        "tier": "standard",
    }
    if stamped:
        age = 0 if built_ago_seconds is None else built_ago_seconds
        payload["built_at"] = (now - timedelta(seconds=age)).isoformat()
    return payload


def _seed(redis, slot, payload):
    import json

    keys = league_cache_keys(SPORT)
    redis.store[getattr(keys, slot)] = json.dumps(payload)


async def _get(client, redis, sent=None):
    """One read of the league route against `redis`, capturing dispatches."""
    sink = sent if sent is not None else []
    with patch("app.routes.league_futures._redis_or_none", return_value=redis), patch(
        "app.tasks.celery_app.send_task", side_effect=lambda *a, **k: sink.append((a, k))
    ):
        return (await client.get(f"/api/leagues/{SPORT}")).json()


def _served_the_frozen_match(body) -> bool:
    return any(
        g.get("id") == FROZEN_MATCH["id"] for g in (body.get("upcoming_games") or [])
    )


class TestTheConstantsCohere:
    """The three numbers are one design; a reordering silently undoes it."""

    async def test_revalidation_starts_before_the_slot_it_replaces_expires(self):
        assert LEAGUE_EARLY_REVALIDATE_AFTER < LEAGUE_PRIMARY_TTL, (
            "revalidating at or after the TTL is what #1767 already did — the "
            "rebuild must be dispatched while the primary is still valid"
        )

    async def test_the_headroom_covers_the_measured_delivery_latency(self):
        """167s, measured 2026-09-05: `refresh_league` queues on `background`
        behind the typeahead warmers. A threshold that leaves less headroom than
        that ships a constant that cannot do its job."""
        headroom = LEAGUE_PRIMARY_TTL - LEAGUE_EARLY_REVALIDATE_AFTER
        assert headroom >= 167, (
            f"only {headroom}s to deliver a rebuild that measured 167s; the "
            f"replacement would land after the slot it replaces had expired"
        )

    async def test_a_trafficked_page_never_trips_the_mirror_bound(self):
        """The bound must fire on a quiet GAP, never on the ordinary cycle — or
        every league page under load would pay a synchronous rebuild."""
        assert LEAGUE_GAMES_MIRROR_MAX_AGE > LEAGUE_PRIMARY_TTL, (
            "a bound at or below the primary TTL would refuse the mirror during "
            "the normal stale window, putting the build on the request path"
        )

    async def test_the_bound_is_shorter_than_the_outage_mirror_it_narrows(self):
        assert LEAGUE_GAMES_MIRROR_MAX_AGE < LEAGUE_STALE_TTL, (
            "a bound at the mirror's own TTL narrows nothing"
        )


class TestTheStampIsReal:
    """Every arm below is vacuous if nothing writes `built_at`."""

    async def test_build_league_stamps_when_it_built(self, mock_db):
        before = datetime.now(timezone.utc)
        payload = await build_league(SPORT, mock_db)
        after = datetime.now(timezone.utc)

        assert "built_at" in payload, (
            "unstamped payloads fail closed, so a missing stamp would not fail "
            "any test below — it would just rebuild every league forever"
        )
        built = datetime.fromisoformat(payload["built_at"])
        assert before <= built <= after

    async def test_a_freshly_built_payload_reads_as_age_zero(self, mock_db):
        payload = await build_league(SPORT, mock_db)
        age = payload_age_seconds(payload, datetime.now(timezone.utc))
        assert age is not None and age < 5

    async def test_the_stamp_survives_the_json_round_trip_into_redis(self, mock_db):
        """`_write_league_payload` encodes with `default=str`. A stamp that only
        parses in-process would read as None off the wire — fail-closed, so
        every read would rebuild and nothing would ever be served from cache."""
        import json

        payload = await build_league(SPORT, mock_db)
        decoded = json.loads(json.dumps(payload, default=str))
        age = payload_age_seconds(decoded, datetime.now(timezone.utc))
        assert age is not None, "the stamp did not survive the cache codec"


class TestPayloadAge:
    async def test_an_unstamped_payload_cannot_say_its_age(self):
        assert payload_age_seconds({"upcoming_games": [FROZEN_MATCH]}, datetime.now(timezone.utc)) is None

    async def test_an_unparseable_stamp_cannot_say_its_age(self):
        now = datetime.now(timezone.utc)
        assert payload_age_seconds({"built_at": "last Tuesday"}, now) is None
        assert payload_age_seconds({"built_at": 1788662444}, now) is None

    async def test_a_naive_stamp_is_read_as_utc(self):
        """`json.dumps(..., default=str)` is not the only writer this file has
        ever had. A naive stamp compared against an aware `now` raises TypeError
        inside the serve decision — a 500 on the league page."""
        now = datetime(2026, 9, 6, 2, 26, tzinfo=timezone.utc)
        age = payload_age_seconds({"built_at": "2026-09-06T00:36:00"}, now)
        assert age == pytest.approx(6600, abs=1)

    async def test_a_future_stamp_reads_as_zero_not_negative(self):
        """Clock skew between web dynos is a reason to distrust the stamp, never
        a licence to serve the payload past the bound. A negative age would sail
        under every `>` comparison in the file."""
        now = datetime(2026, 9, 6, 2, 26, tzinfo=timezone.utc)
        age = payload_age_seconds({"built_at": "2026-09-06T09:00:00+00:00"}, now)
        assert age == 0.0


class TestWhichPayloadsTheBoundApplesTo:
    async def test_a_payload_with_games_has_games(self):
        assert has_games(_mirror())

    async def test_a_futures_only_payload_has_no_games(self):
        assert not has_games(_mirror(games=(), sections={"awards": [{"id": 1}]}))

    async def test_every_games_rail_arms_the_bound(self):
        """Derived from `GAMES_RAIL_KEYS`, not restated — #3245's lesson. A
        fourth rail is covered the moment it joins the tuple."""
        assert len(GAMES_RAIL_KEYS) >= 3, (
            "population guard: this loop is vacuous if the tuple has lost rails"
        )
        now = datetime.now(timezone.utc)
        blank = _mirror(built_ago_seconds=LEAGUE_GAMES_MIRROR_MAX_AGE + 60, games=())
        assert not mirror_is_too_old(blank, now), "the baseline must be exempt"

        for rail in GAMES_RAIL_KEYS:
            armed = dict(blank, **{rail: [{"id": 1}]})
            assert mirror_is_too_old(armed, now), (
                f"a mirror carrying only `{rail}` describes games and went "
                f"unbounded — the #3245 shape, one rail at a time"
            )


class TestTheMirrorIsRefusedWhenItIsTooOldToDescribeAGame:
    async def test_the_measured_incident_is_not_served(self, client):
        """1h50m old, printing a finished match as live at 66'. The exact read."""
        redis = FakeRedis()
        _seed(redis, "stale", _mirror(built_ago_seconds=6600))

        body = await _get(client, redis)

        assert not _served_the_frozen_match(body), (
            "the league page served a 1h50m-old snapshot showing Charlotte–Houston "
            "as live at 66' while the event row said completed at 01:40Z"
        )

    async def test_a_mirror_inside_the_bound_is_still_served(self, client):
        """The other direction. Without this arm the bound could be `always` and
        every league page would rebuild on the request path."""
        redis = FakeRedis()
        _seed(redis, "stale", _mirror(built_ago_seconds=LEAGUE_GAMES_MIRROR_MAX_AGE - 60))

        body = await _get(client, redis)

        assert _served_the_frozen_match(body)
        assert body["availability"] == "stale"

    async def test_the_boundary_is_served_and_one_second_past_it_is_not(self, client):
        redis = FakeRedis()
        _seed(redis, "stale", _mirror(built_ago_seconds=LEAGUE_GAMES_MIRROR_MAX_AGE - 1))
        assert _served_the_frozen_match(await _get(client, redis))

        redis = FakeRedis()
        _seed(redis, "stale", _mirror(built_ago_seconds=LEAGUE_GAMES_MIRROR_MAX_AGE + 1))
        assert not _served_the_frozen_match(await _get(client, redis))

    async def test_an_unstamped_mirror_with_games_fails_closed(self, client):
        """Every mirror in production Redis at deploy time is unstamped. Reading
        "no stamp" as "young" would pin exactly those payloads for their full 24
        hours — the fix exempting the population it was written for."""
        redis = FakeRedis()
        _seed(redis, "stale", _mirror(stamped=False))

        assert not _served_the_frozen_match(await _get(client, redis))

    async def test_a_futures_only_mirror_keeps_its_24h_outage_copy(self, client):
        """The bound narrows the mirror for games and nothing else. A standing
        futures board a day old is very nearly right, and that copy is the whole
        reason the 24h mirror exists."""
        redis = FakeRedis()
        _seed(
            redis,
            "stale",
            _mirror(built_ago_seconds=LEAGUE_STALE_TTL - 60, games=(), sections={"awards": [{"id": 7}]}),
        )

        body = await _get(client, redis)

        assert body["availability"] == "stale"
        assert body["sections"] == {"awards": [{"id": 7}]}

    async def test_an_unstamped_futures_only_mirror_is_also_kept(self, client):
        """Fail-closed is scoped to games. Failing closed on futures boards too
        would cold-build every league once at deploy for no correctness gain."""
        redis = FakeRedis()
        _seed(redis, "stale", _mirror(games=(), sections={"awards": [{"id": 7}]}, stamped=False))

        body = await _get(client, redis)

        assert body["sections"] == {"awards": [{"id": 7}]}


class TestARefusedMirrorStillBeatsAnOutage:
    async def test_a_degraded_build_falls_back_to_the_too_old_mirror(self, client):
        """The bound chooses between two real answers. It must not trade a
        ten-minute-old page for `tier: None` and an empty board."""
        redis = FakeRedis()
        _seed(redis, "stale", _mirror(built_ago_seconds=6600))

        async def _degraded(sport_key, db):
            """What `build_league` returns when its market query times out."""
            return {
                "sport_key": sport_key,
                "sections": {},
                "total_markets": 0,
                "error": "timeout",
                "tier": None,
                "availability": "degraded",
                "pool_counts": {"answers": 0, "dropped": 0, "settled": 0},
                "section_counts": {},
            }

        with patch("app.routes.league_futures._redis_or_none", return_value=redis), patch(
            "app.tasks.celery_app.send_task", side_effect=lambda *a, **k: None
        ), patch("app.routes.league_futures.build_league", _degraded):
            body = (await client.get(f"/api/leagues/{SPORT}")).json()

        assert _served_the_frozen_match(body), (
            "a database outage must still get the mirror — the age bound decides "
            "which real answer is better, not whether to answer at all"
        )
        assert body["availability"] == "stale"

    async def test_the_served_mirror_declares_how_old_it_is(self, client):
        """Ruling 025 clause 4. `stale` alone does not separate the forty-second
        copy from the two-hour one, and on 2026-09-05 only the second was a lie.
        Proving that took a production read; the envelope should have said it."""
        redis = FakeRedis()
        _seed(redis, "stale", _mirror(built_ago_seconds=200))

        body = await _get(client, redis)

        assert body["stale_age_seconds"] == pytest.approx(200, abs=5)


class TestRevalidationStartsBeforeTheSlotExpires:
    async def test_an_aged_primary_hit_dispatches_a_rebuild(self, client):
        redis = FakeRedis()
        _seed(redis, "primary", _mirror(built_ago_seconds=LEAGUE_EARLY_REVALIDATE_AFTER + 10))
        sent = []

        body = await _get(client, redis, sent)

        assert len(sent) == 1, (
            "the rebuild must be dispatched while the primary is still valid — "
            "starting it at expiry is what left a 167s stale window every cycle"
        )
        assert sent[0][1]["args"][0] == SPORT

    async def test_the_aged_primary_is_still_served_immediately(self, client):
        """Revalidate BEHIND the response. An early refresh that made the reader
        wait would be a latency regression sold as a freshness fix."""
        redis = FakeRedis()
        _seed(redis, "primary", _mirror(built_ago_seconds=LEAGUE_EARLY_REVALIDATE_AFTER + 10))

        body = await _get(client, redis)

        assert _served_the_frozen_match(body)
        assert body["availability"] == "fresh", "a valid primary is not stale"

    async def test_a_young_primary_hit_dispatches_nothing(self, client):
        redis = FakeRedis()
        _seed(redis, "primary", _mirror(built_ago_seconds=LEAGUE_EARLY_REVALIDATE_AFTER - 30))
        sent = []

        await _get(client, redis, sent)

        assert sent == [], (
            "revalidating a young slot would rebuild several times per TTL for "
            "no freshness gain"
        )

    async def test_a_futures_only_primary_never_revalidates_early(self, client):
        """Scoped to games, like the bound. A standing board does not need a
        rebuild three times an hour."""
        redis = FakeRedis()
        _seed(
            redis,
            "primary",
            _mirror(built_ago_seconds=LEAGUE_PRIMARY_TTL - 1, games=(), sections={"awards": [{"id": 1}]}),
        )
        sent = []

        await _get(client, redis, sent)

        assert sent == []

    async def test_an_unstamped_primary_revalidates_rather_than_coasting(self, client):
        """Fail closed here too: an unstamped primary is a pre-deploy payload of
        unknown age, and coasting on it would delay the first correct build by a
        full TTL on every league at once."""
        redis = FakeRedis()
        _seed(redis, "primary", _mirror(stamped=False))
        sent = []

        body = await _get(client, redis, sent)

        assert len(sent) == 1
        assert _served_the_frozen_match(body), "still served — only revalidated behind"

    async def test_a_burst_on_an_aged_primary_produces_one_rebuild(self, client):
        """Single-flight applies to the early dispatch too, or a popular page
        would fire one rebuild per reader for the last 150s of every cycle."""
        redis = FakeRedis()
        _seed(redis, "primary", _mirror(built_ago_seconds=LEAGUE_EARLY_REVALIDATE_AFTER + 10))
        sent = []

        for _ in range(4):
            await _get(client, redis, sent)

        assert len(sent) == 1, f"expected single-flight, got {len(sent)}"
