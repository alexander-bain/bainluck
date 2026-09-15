"""A `redis: false` ON `/api/health` SAYS WHICH FAILURE IT WAS. #6404.

═══ WHY ═══

integrator/int375 measured `/api/health` on production 2026-09-15 17:06–17:09Z:
**4 of 19 samples `redis: false`**, `db: true` throughout, and a **true→false flip on the
SAME `process_id` 21 s apart** — so not one sick dyno behind a load balancer, and not general
dyno distress. It survived a release and has read `ok` since. Intermittent, and a single green
read is not a refutation.

`except Exception: redis_ok = False` discarded the reason, and the candidates want opposite
responses:

* `ConnectionError` — a TLS handshake EOF on a fresh connection, i.e. #1197's documented churn.
  `get_redis_client` mints a NEW client and a NEW pool on every call (275 call sites, no cache
  anywhere), so every probe is an independent handshake — which is exactly the shape that makes
  one process flip.
* `TimeoutError` — Redis answered too slowly. `elapsed_ms` near the socket bound is the tell,
  and this one is a real degradation.
* anything else — a probe bug, and *a `degraded` that does not mean degraded trains every lane
  to ignore the field*.

═══ THE ASSERTION THAT MATTERS MOST ═══

🔴 **`/api/health` IS UNAUTHENTICATED AND A REDIS EXCEPTION STRING CAN CARRY THE PASSWORD.**
`redis.from_url` errors quote the connection URL, and on Heroku that URL embeds the credential.
The obvious implementation of this ship — `str(exc)` — publishes a live secret on an open
endpoint, on the one code path nobody reads until it fires, and the standing rule is that a
secret reaching a tracked or served surface means ROTATE, not "delete the line".

`TestTheMessageIsNeverPublished` is therefore the load-bearing half of this file, and it asserts
the absence of a planted password rather than the presence of the class name.

═══ WHAT MUST NOT CHANGE ═══

* `status`, `db`, `redis` and the status code keep their exact pre-existing semantics. Every
  uptime monitor reads the bool; this ship is additive or it is a breaking change wearing a
  diagnostic hat.
* `redis_check` is present on SUCCESS too. A healthy probe's latency is the baseline the next
  flap is read against; publishing it only on failure leaves the number with nothing to compare
  to, which is how the original `false` came to mean nothing.
"""

import json
from unittest.mock import patch

import pytest

from app.routes import health as health_route


_PLANTED_SECRET = "s3cr3t-redis-password-do-not-publish"


def _payload(response) -> dict:
    return json.loads(response.body)


class _Boom:
    """A client whose `ping` raises `exc`."""

    def __init__(self, exc):
        self._exc = exc

    def ping(self):
        raise self._exc


async def _ok_db(*_a, **_k):
    return None


def _run(exc=None):
    """Call the route with the Redis ping either healthy or raising `exc`."""
    client = _Boom(exc) if exc is not None else type("_Ok", (), {"ping": lambda self: True})()
    with patch("app.tasks.redis_state.get_redis_client", return_value=client):
        import asyncio

        return asyncio.run(health_route.api_health_check())


@pytest.fixture(autouse=True)
def _db_always_up():
    """This file is about the Redis half; keep the DB half out of the way."""

    class _Conn:
        async def execute(self, *_a, **_k):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

    class _Engine:
        def connect(self):
            return _Conn()

    with patch("app.services.database.engine", _Engine()):
        yield


# ---------------------------------------------------------------------------
# 1. The secret. This is the half worth having.
# ---------------------------------------------------------------------------


class TestTheMessageIsNeverPublished:
    def test_a_connection_url_in_the_exception_does_not_reach_the_payload(self):
        """🔴 `/api/health` needs no auth. `str(exc)` here would publish a password.

        Asserted over the WHOLE serialised body rather than over one field, so a
        future writer who adds a second diagnostic key cannot reintroduce it
        somewhere this test was not looking.
        """
        exc = ConnectionError(
            f"Error connecting to rediss://:{_PLANTED_SECRET}@ec2-1-2-3-4.compute.amazonaws.com:6379"
        )
        body = _run(exc).body.decode()
        assert _PLANTED_SECRET not in body
        assert "amazonaws.com" not in body
        assert "rediss://" not in body

    def test_the_class_name_is_what_is_published(self):
        """The whole diagnostic, and it carries no secret."""
        exc = ConnectionError(f"rediss://:{_PLANTED_SECRET}@host:6379")
        assert _payload(_run(exc))["redis_check"]["error"] == "ConnectionError"


# ---------------------------------------------------------------------------
# 2. The three candidates are now distinguishable.
# ---------------------------------------------------------------------------


class TestTheFailureNamesItself:
    @pytest.mark.parametrize(
        "exc, expected",
        [
            (ConnectionError("handshake eof"), "ConnectionError"),
            (TimeoutError("too slow"), "TimeoutError"),
            (ValueError("a probe bug"), "ValueError"),
        ],
    )
    def test_each_candidate_is_reported_by_its_own_name(self, exc, expected):
        body = _payload(_run(exc))
        assert body["redis"] is False
        assert body["redis_check"]["error"] == expected

    def test_a_healthy_probe_reports_no_error_but_still_reports_a_baseline(self):
        """Present on SUCCESS too, so the next flap has something to compare to."""
        body = _payload(_run())
        assert body["redis"] is True
        assert body["redis_check"]["error"] is None
        assert isinstance(body["redis_check"]["elapsed_ms"], int)
        assert body["redis_check"]["elapsed_ms"] >= 0

    def test_elapsed_ms_is_measured_even_when_the_ping_raises(self):
        """A timeout's tell is its DURATION; an instant refusal's is the lack of one."""
        body = _payload(_run(TimeoutError("slow")))
        assert isinstance(body["redis_check"]["elapsed_ms"], int)


# ---------------------------------------------------------------------------
# 3. The pre-existing contract. Additive, or it is a breaking change.
# ---------------------------------------------------------------------------


class TestTheMonitorContractIsUnchanged:
    def test_a_redis_failure_is_still_degraded_at_200(self):
        """`db or redis` keeps the 200: one tier down is degraded, not dead."""
        r = _run(ConnectionError("x"))
        assert r.status_code == 200
        body = _payload(r)
        assert body["status"] == "degraded"
        assert body["db"] is True
        assert body["redis"] is False

    def test_a_healthy_probe_is_still_ok_at_200(self):
        r = _run()
        assert r.status_code == 200
        assert _payload(r)["status"] == "ok"

    def test_the_pre_existing_keys_all_survive(self):
        """NOT VACUOUS: a rewrite that drops `dyno` or `process_id` would break the
        #2107 per-process coverage read, which is why they are there at all."""
        body = _payload(_run())
        for key in (
            "status",
            "db",
            "redis",
            "commit",
            "uptime_seconds",
            "dyno",
            "process_id",
        ):
            assert key in body, f"{key} disappeared from /api/health"

    def test_redis_stays_a_bare_bool_and_is_not_replaced_by_the_new_block(self):
        """Every uptime monitor reads this field. It must not become a dict."""
        assert _payload(_run())["redis"] is True
        assert _payload(_run(ConnectionError("x")))["redis"] is False
