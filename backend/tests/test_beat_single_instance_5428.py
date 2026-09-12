"""#5428 / directive 1815PT: two celery beats dispatch every task twice.

The `scheduler` dyno is moving off the main `bainluck` app onto
`bainluck-heavy`, so that a release of the main site stops restarting the clock
that decides when everything runs. The worker move before it could overlap the
two dynos safely — one queue, each message delivered to exactly one consumer,
so the only cost of running both for a minute was a few cents. **This move
cannot.** Celery beat here has no distributed lock: `celery_app.conf` sets no
`beat_scheduler`, so the default `PersistentScheduler` keeps its state in a
shelve file on the dyno's own ephemeral disk. Two beat dynos do not contend for
anything. They both tick, and every scheduled task in the system runs twice.

Nothing already in the instrumentation could report that:

* `TASK_EMISSION_BUCKET_PREFIX` would read exactly double, which is
  indistinguishable from a schedule change or a backfill.
* `TASK_EMIT_WRITER_ALIVE_PREFIX` is a bare per-bucket flag — it says *some*
  publisher was alive in bucket N, never how many, and never which.

So this file guards a census that records beat IDENTITY rather than a count,
and the properties that make it usable as the move's proof. The one that has to
hold hardest is the last class: an unreadable Redis must not render as "no beat
is running", because that is the difference between an outage and the loudest
alarm this census can raise (gotcha #53).
"""

import pytest

from app.tasks import redis_state
from app.tasks.redis_state import BEAT_ALIVE_PREFIX, BeatCensusUnavailable


class _Redis:
    """Enough Redis for the census's write and read paths."""

    def __init__(self):
        self.strings = {}
        self.ttls = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.strings:
            return None
        self.strings[key] = str(value).encode()
        if ex is not None:
            self.ttls[key] = ex
        return True

    def get(self, key):
        return self.strings.get(key)

    def keys(self, pattern):
        prefix = pattern.rstrip("*")
        return [k.encode() for k in self.strings if k.startswith(prefix)]


class _DeadRedis:
    """A Redis that is reachable for nothing. Models the outage, not an absence."""

    def set(self, *a, **k):
        raise ConnectionError("redis is gone")

    def keys(self, *a, **k):
        raise ConnectionError("redis is gone")


@pytest.fixture
def fake(monkeypatch):
    r = _Redis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: r)
    # The throttle is module state and would otherwise leak between tests,
    # silently turning a "did it write" assertion into "was it recently called".
    monkeypatch.setattr(redis_state, "_last_beat_stamp_s", 0.0)
    return r


@pytest.fixture
def as_beat(monkeypatch):
    """Run the body as the `scheduler` dyno does: `celery ... beat`."""
    import sys

    monkeypatch.setattr(
        sys, "argv",
        ["celery", "-A", "app.tasks.celery_app", "beat", "--loglevel=info"],
    )


# ---------------------------------------------------------------------------
# Who counts as a beat
# ---------------------------------------------------------------------------

class TestIsBeatProcess:
    @pytest.mark.parametrize("argv,expected", [
        (["celery", "-A", "app.tasks.celery_app", "beat", "--loglevel=info"], True),
        # The Procfile's four worker lines, which publish too (a task that
        # spawns a task reaches the same signal) and must never be counted.
        (["celery", "-A", "app.tasks.celery_app", "worker", "--queues=realtime"], False),
        (["celery", "-A", "app.tasks.celery_app", "worker", "--queues=heavy"], False),
        (["uvicorn", "app.main:app", "--host", "0.0.0.0"], False),
        (["pytest"], False),
        ([], False),
        # An EMBEDDED beat is a second beat in every sense that matters here.
        (["celery", "-A", "app.tasks.celery_app", "worker", "-B"], True),
        (["celery", "-A", "app.tasks.celery_app", "worker", "--beat"], True),
    ])
    def test_only_a_beat_is_a_beat(self, monkeypatch, argv, expected):
        import sys
        monkeypatch.setattr(sys, "argv", argv)
        assert redis_state._is_beat_process() is expected

    def test_a_worker_never_stamps(self, fake, monkeypatch):
        """The census must describe schedulers, not every publisher.

        Without this the set would fill with `web.1` and four workers, and
        `MULTIPLE` — the alarm the whole census exists to raise — would be the
        permanent steady state.
        """
        import sys
        monkeypatch.setattr(sys, "argv", ["celery", "-A", "x", "worker"])
        redis_state.record_beat_alive()
        assert fake.strings == {}


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

class TestBeatIdentity:
    def test_two_beats_separate_even_with_no_dyno_metadata(self, monkeypatch):
        """The hazard is reported on an app that was never configured for it.

        `HEROKU_APP_NAME` arrives with the `runtime-dyno-metadata` lab, which is
        enabled on `bainluck` and NOT on `bainluck-heavy`. If identity depended
        on it, the two beats would both be `unknown-app/scheduler.1` during
        exactly the handover this census is for, collapse to one key, and the
        census would report SINGLE while both were dispatching.
        """
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        monkeypatch.setenv("DYNO", "scheduler.1")

        monkeypatch.setattr(redis_state.os, "getpid", lambda: 111)
        one = redis_state.beat_identity()
        monkeypatch.setattr(redis_state.os, "getpid", lambda: 222)
        two = redis_state.beat_identity()

        assert one != two, "two beat processes collapsed to one identity"

    def test_app_name_is_used_when_present(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        monkeypatch.setenv("DYNO", "scheduler.1")
        assert redis_state.beat_identity().startswith("bainluck-heavy/scheduler.1/")


# ---------------------------------------------------------------------------
# The stamp
# ---------------------------------------------------------------------------

class TestRecordBeatAlive:
    def test_stamps_a_key_named_for_the_identity_with_a_ttl(self, fake, as_beat, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        monkeypatch.setenv("DYNO", "scheduler.1")

        redis_state.record_beat_alive(now_s=1000.0)

        key = f"{BEAT_ALIVE_PREFIX}:{redis_state.beat_identity()}"
        assert key in fake.strings
        # The TTL is the whole expiry mechanism: one key per beat, each dying on
        # its own, is what makes a STOPPED beat drop out. A set with a refreshed
        # TTL would keep a dead beat alive forever behind a live sibling.
        assert fake.ttls[key] == redis_state.BEAT_ALIVE_TTL_S

    def test_the_stamp_carries_the_slug_it_is_running(self, fake, as_beat, monkeypatch):
        """The writer half of the drift question.

        Seeded-reader tests cover how a slug is REPORTED and none of them
        notices if the stamp never records one — a mutant pinning the payload's
        slug to None survived the whole file until this existed.
        """
        import json

        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        monkeypatch.setenv("DYNO", "scheduler.1")
        monkeypatch.setenv("HEROKU_SLUG_COMMIT", "3d322638aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

        redis_state.record_beat_alive(now_s=1000.0)

        key = f"{BEAT_ALIVE_PREFIX}:{redis_state.beat_identity()}"
        assert json.loads(fake.strings[key].decode())["slug"] == "3d322638"

    def test_the_stamp_records_no_slug_rather_than_a_wrong_one(self, fake, as_beat, monkeypatch):
        """No dyno metadata means unknown, and unknown must reach the reader."""
        import json

        monkeypatch.delenv("HEROKU_SLUG_COMMIT", raising=False)
        redis_state.record_beat_alive(now_s=1000.0)

        key = f"{BEAT_ALIVE_PREFIX}:{redis_state.beat_identity()}"
        assert json.loads(fake.strings[key].decode())["slug"] is None

    def test_throttled_within_the_refresh_window(self, fake, as_beat):
        redis_state.record_beat_alive(now_s=1000.0)
        fake.strings.clear()

        redis_state.record_beat_alive(now_s=1000.0 + redis_state.BEAT_ALIVE_REFRESH_S - 1)
        assert fake.strings == {}, "re-stamped inside the throttle window"

        redis_state.record_beat_alive(now_s=1000.0 + redis_state.BEAT_ALIVE_REFRESH_S)
        assert fake.strings, "never re-stamped after the throttle window"

    def test_ttl_outlives_the_refresh_by_enough_fires_to_matter(self):
        """A live beat must not be readable as gone between two stamps.

        The tightest beat entry fires every 10s, so a beat that is alive at all
        publishes many times inside the TTL. Pinned from both sides (the tuned
        constant rule): a TTL at or below the refresh would expire a healthy
        beat mid-move and read as NONE.
        """
        assert redis_state.BEAT_ALIVE_TTL_S >= 4 * redis_state.BEAT_ALIVE_REFRESH_S
        assert redis_state.BEAT_ALIVE_REFRESH_S >= 10

    def test_a_redis_fault_costs_one_stamp_not_the_next_window(self, monkeypatch, as_beat):
        """The throttle clock advances only on a write that succeeded.

        If it advanced on failure, a single blip would suppress stamping for a
        whole REFRESH_S and a healthy beat could flicker out of the census.
        """
        monkeypatch.setattr(redis_state, "_last_beat_stamp_s", 0.0)
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _DeadRedis())
        redis_state.record_beat_alive(now_s=1000.0)  # must not raise

        good = _Redis()
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: good)
        redis_state.record_beat_alive(now_s=1001.0)
        assert good.strings, "a failed stamp consumed the throttle window"

    def test_never_raises_on_the_publish_path(self, monkeypatch, as_beat):
        """Best-effort by contract: a Redis fault costs a stamp, never a fire."""
        monkeypatch.setattr(redis_state, "_last_beat_stamp_s", 0.0)
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _DeadRedis())
        redis_state.record_beat_alive(now_s=1000.0)


# ---------------------------------------------------------------------------
# The census
# ---------------------------------------------------------------------------

class TestGetBeatInstances:
    def test_one_beat_is_SINGLE(self, fake):
        fake.strings[f"{BEAT_ALIVE_PREFIX}:bainluck/scheduler.1/10"] = b"1"
        out = redis_state.get_beat_instances()
        assert out["verdict"] == "SINGLE"
        assert out["count"] == 1

    def test_two_beats_are_MULTIPLE_and_are_NAMED(self, fake):
        """The hazard, and the reason the census stores identity not a count.

        Mid-move the only question worth asking is *which app* the second beat
        is on, and a count cannot answer it.
        """
        fake.strings[f"{BEAT_ALIVE_PREFIX}:bainluck/scheduler.1/10"] = b"1"
        fake.strings[f"{BEAT_ALIVE_PREFIX}:bainluck-heavy/scheduler.1/20"] = b"1"

        out = redis_state.get_beat_instances()
        assert out["verdict"] == "MULTIPLE"
        assert out["count"] == 2
        assert out["instances"] == [
            "bainluck-heavy/scheduler.1/20",
            "bainluck/scheduler.1/10",
        ]

    def test_no_beat_is_NONE_and_NONE_is_not_healthy(self, fake):
        out = redis_state.get_beat_instances()
        assert out["verdict"] == "NONE"
        assert out["count"] == 0

    def test_an_unreadable_redis_raises_rather_than_reading_as_NONE(self, monkeypatch):
        """gotcha #53: an outage and an empty fleet must not produce one answer.

        Returning `[]` here would render the single most alarming state this
        census can report — nothing is scheduling anything — as an ordinary row,
        and would do it at exactly the moment Redis is sick.
        """
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _DeadRedis())
        with pytest.raises(BeatCensusUnavailable):
            redis_state.get_beat_instances()

    def test_a_legacy_bare_marker_is_still_COUNTED(self, fake):
        """The count must not depend on the payload format.

        A marker written by a release before the slug was carried parses as an
        int, not a dict. Dropping it would under-count beats at exactly the
        moment a fleet is half-upgraded — which is during a deploy, which is
        when two beats are most likely to coexist.
        """
        fake.strings[f"{BEAT_ALIVE_PREFIX}:bainluck/scheduler.1/10"] = b"1"
        out = redis_state.get_beat_instances()
        assert out["count"] == 1
        assert out["verdict"] == "SINGLE"
        assert out["slugs"] == ["unknown"]

    def test_the_slug_is_reported_because_the_schedule_is_code(self, fake):
        """A beat on an older slug runs an older schedule.

        `bainluck-heavy` was 88 commits behind `bainluck` when the scheduler
        move was written. A beat entry added in that gap would simply never
        fire, with no other observer anywhere in the system.
        """
        import json
        fake.strings[f"{BEAT_ALIVE_PREFIX}:bainluck-heavy/scheduler.1/20"] = json.dumps(
            {"ts": 1000, "slug": "3d322638"}
        ).encode()

        out = redis_state.get_beat_instances()
        assert out["slugs"] == ["3d322638"]
        assert out["detail"]["bainluck-heavy/scheduler.1/20"]["slug"] == "3d322638"

    def test_an_absent_slug_reads_unknown_never_current(self, fake):
        """Unknown must not be rendered as agreement — that is the safe direction."""
        import json
        fake.strings[f"{BEAT_ALIVE_PREFIX}:a/scheduler.1/1"] = json.dumps(
            {"ts": 1000, "slug": None}
        ).encode()
        assert redis_state.get_beat_instances()["slugs"] == ["unknown"]

    def test_two_beats_on_different_slugs_show_both(self, fake):
        import json
        fake.strings[f"{BEAT_ALIVE_PREFIX}:bainluck/scheduler.1/10"] = json.dumps(
            {"ts": 1000, "slug": "cc705833"}
        ).encode()
        fake.strings[f"{BEAT_ALIVE_PREFIX}:bainluck-heavy/scheduler.1/20"] = json.dumps(
            {"ts": 1000, "slug": "3d322638"}
        ).encode()

        out = redis_state.get_beat_instances()
        assert out["verdict"] == "MULTIPLE"
        assert out["slugs"] == ["3d322638", "cc705833"]

    def test_the_census_reads_only_its_own_namespace(self, fake):
        """A neighbouring key must never be counted as a beat."""
        fake.strings[f"{BEAT_ALIVE_PREFIX}:bainluck/scheduler.1/10"] = b"1"
        fake.strings["bainluck:task_emit_writer_alive:b99"] = b"1"
        fake.strings["bainluck:task_lifecycle:x:attempts"] = b"5"

        out = redis_state.get_beat_instances()
        assert out["instances"] == ["bainluck/scheduler.1/10"]


# ---------------------------------------------------------------------------
# The wiring — the census is worthless if nothing stamps it
# ---------------------------------------------------------------------------

class TestPublishHookWiring:
    def test_the_emission_hook_stamps_liveness(self):
        """`record_beat_alive` is called from `before_task_publish`.

        That hook is the one place in the codebase that runs inside the
        scheduler process on a cadence, so it is the only thing that can keep
        the census fresh. A source read rather than a live publish, which needs
        a broker — stated plainly because a source scan proves the call is
        present, not that it runs; the production read in the cert is what
        proves the latter.
        """
        import inspect

        from app import tasks as tasks_pkg

        src = inspect.getsource(tasks_pkg._record_emission)
        assert "record_beat_alive" in src

    def test_liveness_is_stamped_before_the_retry_filter(self):
        """A retry is not a beat fire, but a process is not less alive for it.

        If the stamp sat after the `retries > 0` early return it would inherit a
        filter written for a different question.
        """
        import inspect

        from app import tasks as tasks_pkg

        src = inspect.getsource(tasks_pkg._record_emission)
        assert src.index("record_beat_alive(") < src.index("_published_retries")


# ---------------------------------------------------------------------------
# The repair required by CERT-2675 — a Redis error string is not a payload
# ---------------------------------------------------------------------------

class TestCensusUnavailableNeverEchoesTheException:
    """The endpoint must not hand a reader the text of a Redis failure.

    CodeQL flagged the first version as "information exposure through an
    exception" and CERT-2675 withheld the token for it. The concrete loss is
    not abstract: a redis-py connection error renders the URL it was dialling,
    which on Heroku carries the credentials embedded in `REDIS_URL`, and this
    endpoint is reachable with nothing but the admin secret.

    The sentinel below stands in for that string. The assertion is deliberately
    made against the WHOLE serialized response rather than the `error` key
    alone: the defect is "this text reaches a reader", and a later edit that
    moved it into `reason`, or into a nested detail dict, would satisfy a
    key-scoped assertion while changing nothing about the exposure.
    """

    SENTINEL = "redis://h:sekrit-passw0rd@ec2-1-2-3-4.compute.amazonaws.com:6379"

    def _call(self, monkeypatch, exc):
        import asyncio
        import json

        from app.routes import admin_celery
        from app.tasks import redis_state

        monkeypatch.setattr(
            admin_celery, "_check_admin_secret", lambda *a, **k: None
        )

        def _boom():
            raise exc

        monkeypatch.setattr(redis_state, "get_beat_instances", _boom)
        out = asyncio.run(admin_celery.beat_instances(request=None, secret="x"))
        return out, json.dumps(out)

    def test_beat_census_unavailable_never_echoes_exception_details(
        self, monkeypatch
    ):
        from app.tasks.redis_state import BeatCensusUnavailable

        out, body = self._call(
            monkeypatch, BeatCensusUnavailable(self.SENTINEL)
        )

        assert self.SENTINEL not in body
        assert "sekrit-passw0rd" not in body
        # and the verdict half is untouched: suppressing the detail must not
        # turn an outage into a quiet pass (gotcha #53).
        assert out["verdict"] == "INCONCLUSIVE"
        assert out["status"] == "unreadable"

    def test_the_detail_is_logged_rather_than_discarded(self, monkeypatch, caplog):
        """Suppressed is not the same as lost — an operator still needs the cause.

        Without this, the cheapest way to pass the test above is to delete the
        information entirely, which trades a disclosure bug for a debugging one.
        """
        import logging

        from app.tasks.redis_state import BeatCensusUnavailable

        with caplog.at_level(logging.ERROR, logger="app.routes.admin_celery"):
            self._call(monkeypatch, BeatCensusUnavailable(self.SENTINEL))

        assert any(
            self.SENTINEL in r.getMessage() or self.SENTINEL in str(r.exc_info)
            for r in caplog.records
        ), "the cause must reach the log even though it must not reach the body"
