"""`/health/ready` STOPS PUBLISHING A SECRET AND STOPS STATING A FACT IT HAS NOT GOT. #4196.

═══ WHY ═══

#4196 asked which of two readings was wrong when `/api/health` said `degraded` while every
Redis-backed path answered 200, and named the second possibility: *"the health probe is lying.
Then our single cheapest liveness signal has been reporting degraded while the system is fine —
and `/health` is what every session runs at startup. A monitor that cries wolf gets ignored,
which is how the real one gets missed."*

That possibility is decidable **on the sibling endpoint, from the code and the served payload
alone** — no attended Redis window, which is what the issue was parked waiting for.

Measured on production 2026-09-16 17:46Z, unauthenticated (no `Authorization` header), HTTP 200:

    {"status":"ready", ...
     "last_polls":{"odds_api":null,"espn":null,"kalshi":null,"polymarket":null,"statpal":null},
     "odds_api":{... "updated_at":"2026-09-16T17:46:11+00:00","source":"cached"},
     "queue_lengths":{"background":22,"realtime":0}}

**THE PAYLOAD REFUTES ITSELF.** It says no source has ever polled, eleven seconds after the quota
cache it prints in the same object was written, with 1,146,943 Odds API requests spent. Both
cannot be true.

The cause is not a stalled poller. It is that `last_poll:odds` / `:espn` / `:kalshi` /
`:polymarket` / `:statpal` **are written by nothing in this tree** — the only stamp any writer
sets is `bainluck:last_poll:{sport_key}` (prefixed, per SPORT: `tasks/odds_polling.py`, `ex=3600`).
Five reads of a key space with no writer can only ever return five nulls. The field was never
measuring anything.

═══ THE ASSERTION THAT MATTERS MOST ═══

🔴 **`/health/ready` IS UNAUTHENTICATED AND ITS ERROR BRANCHES PRINTED `f"error: {e}"`.**

#6404 ruled exactly this for `/api/health` — *the class name, never the message* — and wrote the
reason into this very file: an exception string can carry a connection URL, and on Heroku that URL
embeds the password. It fixed one of the two open probes. `/health/ready` kept interpolating the
message on three branches, and one is strictly worse than the Redis case the rule was written
about: `OddsAPIService.check_quota()` passes the key as a **query parameter** and calls
`raise_for_status()`, and httpx puts the whole request URL in the message. So a 401/429 from The
Odds API publishes our most quota-constrained credential on an open endpoint.

`TestTheMessageIsNeverPublished` is the load-bearing half. It asserts the absence of a planted
credential in the served body — **and separately asserts that the planted credential really is in
`str(exc)`**, so the guard cannot pass by the exception having quietly stopped carrying it.

═══ WHAT MUST NOT CHANGE ═══

* `status` stays `ready`/`degraded` on the same condition, and every pre-existing key in `checks`
  survives. A readiness probe is read by machines; this is a truth fix, not a reshape.
* Absent ≠ null. The four sources nobody instruments are now ABSENT from `last_polls`; `odds_api`
  is present and may be null, which now honestly means "no sport polled within the writer's
  one-hour TTL". A future writer that reinstates the other four as nulls reintroduces the bug.
"""

import asyncio
from unittest.mock import patch

import pytest

from app.routes import health as health_route


_PLANTED_ODDS_KEY = "live-odds-api-key-do-not-publish-9f2c"
_PLANTED_REDIS_PASSWORD = "s3cr3t-redis-password-do-not-publish"


class _FakeRedis:
    """Records every key it is asked for, so the dead key space can be asserted gone."""

    def __init__(self, stamps=None, ping_exc=None):
        self._stamps = stamps or {}
        self._ping_exc = ping_exc
        self.mget_keys = []

    def ping(self):
        if self._ping_exc is not None:
            raise self._ping_exc
        return True

    def mget(self, keys):
        keys = list(keys)
        self.mget_keys.extend(keys)
        return [self._stamps.get(k) for k in keys]

    def get(self, key):
        return self._stamps.get(key)

    def llen(self, _name):
        return 0


class _FakeDB:
    def __init__(self, exc=None):
        self._exc = exc

    async def execute(self, *_a, **_k):
        if self._exc is not None:
            raise self._exc
        return None


def _run(redis=None, db_exc=None, quota=None, quota_exc=None):
    """Call the readiness route with each of its three dependencies controlled."""
    redis = redis if redis is not None else _FakeRedis()

    def _quota():
        if quota_exc is not None:
            raise quota_exc
        return quota if quota is not None else {
            "status": "ok",
            "health": "healthy",
            "remaining": 3_853_057,
            "used": 1_146_943,
            "updated_at": "2026-09-16T17:46:11+00:00",
        }

    with patch("app.tasks.redis_state.get_redis_client", return_value=redis), patch(
        "app.tasks.redis_state.get_odds_api_quota", _quota
    ):
        return asyncio.run(health_route.readiness_check(db=_FakeDB(db_exc)))


# ---------------------------------------------------------------------------
# 1. The secret. This is the half worth having.
# ---------------------------------------------------------------------------


class TestTheMessageIsNeverPublished:
    def test_the_odds_api_key_really_is_in_the_exception_string(self):
        """NOT VACUOUS — the premise, asserted rather than recalled.

        If httpx ever stops embedding the request URL, the leak test below would
        start passing for a reason that has nothing to do with our fix. This
        pins the hazard itself, so that day fails HERE, loudly, instead of
        silently disarming the guard next to it.
        """
        import httpx

        request = httpx.Request(
            "GET", f"https://api.the-odds-api.com/v4/sports/?apiKey={_PLANTED_ODDS_KEY}"
        )
        with pytest.raises(httpx.HTTPStatusError) as caught:
            httpx.Response(401, request=request).raise_for_status()

        assert _PLANTED_ODDS_KEY in str(caught.value)

    def test_an_odds_api_failure_does_not_publish_the_api_key(self):
        """🔴 The branch that can hold a live credential on an open endpoint.

        Asserted over the WHOLE serialised body rather than one field, so a
        future writer who adds a second diagnostic key cannot reintroduce it
        somewhere this test was not looking.
        """
        import httpx

        request = httpx.Request(
            "GET", f"https://api.the-odds-api.com/v4/sports/?apiKey={_PLANTED_ODDS_KEY}"
        )
        exc = httpx.HTTPStatusError(
            f"Client error '401 Unauthorized' for url '{request.url}'",
            request=request,
            response=httpx.Response(401, request=request),
        )

        body = str(_run(quota_exc=exc))

        assert _PLANTED_ODDS_KEY not in body
        assert "apiKey" not in body
        assert "the-odds-api.com" not in body

    def test_a_redis_failure_does_not_publish_the_connection_url(self):
        """The case #6404 ruled on the other endpoint, now held on this one."""
        exc = ConnectionError(
            f"Error connecting to rediss://:{_PLANTED_REDIS_PASSWORD}"
            f"@ec2-1-2-3-4.compute.amazonaws.com:6379"
        )
        body = str(_run(redis=_FakeRedis(ping_exc=exc)))

        assert _PLANTED_REDIS_PASSWORD not in body
        assert "rediss://" not in body
        assert "amazonaws.com" not in body

    def test_a_database_failure_does_not_publish_the_dsn(self):
        exc = RuntimeError(
            f"could not connect: postgresql://u:{_PLANTED_REDIS_PASSWORD}@db.internal:5432/bain"
        )
        body = str(_run(db_exc=exc))

        assert _PLANTED_REDIS_PASSWORD not in body
        assert "postgresql://" not in body

    @pytest.mark.parametrize(
        "kwargs, field, expected",
        [
            ({"db_exc": RuntimeError("x")}, "database", "error: RuntimeError"),
            (
                {"redis": _FakeRedis(ping_exc=TimeoutError("slow"))},
                "redis",
                "error: TimeoutError",
            ),
            ({"quota_exc": ValueError("x")}, "odds_api", "error: ValueError"),
        ],
    )
    def test_the_class_name_is_what_is_published(self, kwargs, field, expected):
        """The whole diagnostic, and it carries no secret."""
        assert _run(**kwargs)["checks"][field] == expected


# ---------------------------------------------------------------------------
# 2. The field stops claiming a measurement it never took.
# ---------------------------------------------------------------------------


class TestLastPollsReadsAKeySpaceSomethingWrites:
    def test_the_dead_unprefixed_keys_are_never_read_again(self):
        """`last_poll:odds` and its four siblings have no writer at any call site."""
        redis = _FakeRedis()
        _run(redis=redis)

        assert redis.mget_keys, "the probe asked Redis for nothing at all"
        for key in redis.mget_keys:
            assert key.startswith("bainluck:last_poll:"), f"read a key nothing writes: {key}"

    def test_it_reads_the_key_the_poller_actually_stamps(self):
        """`tasks/odds_polling.py` sets `bainluck:last_poll:{sport_key}` to an epoch float."""
        redis = _FakeRedis({"bainluck:last_poll:americanfootball_nfl": b"1789500000.0"})

        last_polls = _run(redis=redis)["checks"]["last_polls"]

        assert last_polls["odds_api"] == "2026-09-15T19:20:00+00:00"

    def test_the_freshest_sport_is_the_one_reported(self):
        """Per-sport stamps, one source-level answer: the most recent wins."""
        redis = _FakeRedis(
            {
                "bainluck:last_poll:americanfootball_nfl": b"1789500000.0",
                "bainluck:last_poll:baseball_mlb": b"1789503600.0",
                "bainluck:last_poll:icehockey_nhl": b"1789496400.0",
            }
        )

        assert _run(redis=redis)["checks"]["last_polls"]["odds_api"] == (
            "2026-09-15T20:20:00+00:00"
        )

    def test_the_four_uninstrumented_sources_are_absent_not_null(self):
        """Absent is "we do not measure this"; null is "measured, never seen".

        Printing null for four sources nobody stamps is the whole defect — it
        read as "espn has never polled" on an endpoint saying `ready`.
        """
        last_polls = _run(redis=_FakeRedis())["checks"]["last_polls"]

        for source in ("espn", "kalshi", "polymarket", "statpal"):
            assert source not in last_polls, f"{source} is back, and nothing writes its stamp"

    def test_no_stamp_is_null_and_that_now_means_something(self):
        """The writer's `ex=3600` is what makes this meaningful: no sport in an hour."""
        assert _run(redis=_FakeRedis())["checks"]["last_polls"] == {"odds_api": None}

    def test_a_corrupt_stamp_does_not_take_the_probe_down(self):
        """One bad value must never wipe the pass (gotcha #42)."""
        redis = _FakeRedis(
            {
                "bainluck:last_poll:americanfootball_nfl": b"not-a-timestamp",
                "bainluck:last_poll:baseball_mlb": b"1789503600.0",
            }
        )

        assert _run(redis=redis)["checks"]["last_polls"]["odds_api"] == (
            "2026-09-15T20:20:00+00:00"
        )

    def test_a_redis_outage_still_degrades_to_unavailable(self):
        """Pre-existing behaviour: the block is best-effort, not a 500."""

        class _Dead(_FakeRedis):
            def mget(self, keys):
                raise ConnectionError("down")

        assert _run(redis=_Dead())["checks"]["last_polls"] == "unavailable"


# ---------------------------------------------------------------------------
# 3. The pre-existing contract. A truth fix, not a reshape.
# ---------------------------------------------------------------------------


class TestTheProbeContractIsUnchanged:
    def test_a_healthy_probe_is_still_ready(self):
        body = _run()
        assert body["status"] == "ready"
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["redis"] == "ok"

    def test_a_failing_dependency_still_degrades(self):
        assert _run(db_exc=RuntimeError("x"))["status"] == "degraded"

    def test_every_pre_existing_check_survives(self):
        checks = _run()["checks"]
        for key in ("database", "redis", "last_polls", "odds_api", "queue_lengths"):
            assert key in checks, f"{key} disappeared from /health/ready"

    def test_uptime_seconds_survives(self):
        assert isinstance(_run()["uptime_seconds"], int)
