"""#5470: the app that runs 29 of our tasks is not the app `/health` answers for.

`worker-heavy` moved onto `bainluck-heavy` (#5003) so that a release of the main
site would stop restarting the hourly accuracy rebuild. It worked — and nothing
syncs the new app to master. It was created 2026-09-11 13:09 PT and was still
executing that afternoon's code hours later: the matcher, every sentinel, the
calibration precomputes, the settled-leg guard that had shipped in between. The
main app reported the new commit throughout, because the web dyno really was
running it, and every post-deploy receipt banked against `/health` for a
heavy-queue task read GREEN off a process that does not execute that task.

Nothing already in the instrumentation could report it. Every counter in
`redis_state` is keyed by TASK NAME, and a task executing stale code emits,
delivers and terminates exactly like one executing fresh code. The reader and
the subject are different machines, so the subject has to say what it is
running.

So this file guards that census and the properties that make it usable as a
receipt. Two classes have to hold hardest:

* **An absent answer is never agreement.** `runtime-dyno-metadata` is enabled on
  `bainluck` and NOT on `bainluck-heavy`, so the app under suspicion cannot name
  its own slug today. `UNKNOWN_VERSION` is not a pass, and an unreadable Redis
  raises rather than rendering as an empty, healthy-looking fleet (gotcha #53).
* **Identity is per SLOT, not per process** — the opposite of the beat census
  next door, and load-bearing in the opposite direction: a restarted worker must
  overwrite its predecessor, or DRIFTED would persist for a whole TTL after the
  deploy that cleared it.
"""

import json

import pytest

from app.tasks import redis_state
from app.tasks.redis_state import (
    WORKER_CODE_PREFIX,
    WorkerCodeCensusUnavailable,
    fleet_code_verdict,
)


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
    monkeypatch.setattr(redis_state, "_last_worker_code_stamp_s", 0.0)
    return r


@pytest.fixture
def as_worker(monkeypatch):
    """Run the body as a `worker-heavy` dyno does."""
    import sys

    monkeypatch.setattr(
        sys, "argv",
        ["celery", "-A", "app.tasks.celery_app", "worker", "--queues=heavy"],
    )


def _marker(slug, ts=1000):
    return json.dumps({"ts": ts, "slug": slug}).encode()


# ---------------------------------------------------------------------------
# Who counts as a worker
# ---------------------------------------------------------------------------

class TestIsWorkerProcess:
    @pytest.mark.parametrize("argv,expected", [
        (["celery", "-A", "app.tasks.celery_app", "worker", "--queues=heavy"], True),
        (["celery", "-A", "app.tasks.celery_app", "worker", "--queues=realtime"], True),
        # The scheduler executes nothing. It is covered by the beat census next
        # door, and counting it here would put a slot in the fleet that no task
        # ever runs on.
        (["celery", "-A", "app.tasks.celery_app", "beat", "--loglevel=info"], False),
        (["uvicorn", "app.main:app", "--host", "0.0.0.0"], False),
        (["pytest"], False),
        ([], False),
        # An embedded beat IS a worker here — it executes tasks — even though the
        # census next door counts it as a beat. Two questions, one process.
        (["celery", "-A", "app.tasks.celery_app", "worker", "-B"], True),
    ])
    def test_only_a_worker_is_a_worker(self, monkeypatch, argv, expected):
        import sys
        monkeypatch.setattr(sys, "argv", argv)
        assert redis_state._is_worker_process() is expected

    def test_an_eager_caller_never_stamps(self, fake, monkeypatch):
        """The defect this gate prevents is a census that answers itself.

        `task_always_eager` executes the body in the CALLING process — a test,
        or a local script pointed at a shared Redis. That process would stamp
        the reader's own slug into a census whose whole subject is the machines
        the reader cannot speak for, and the verdict would come back MATCHED
        because it had compared the reader with itself.
        """
        import sys
        monkeypatch.setattr(sys, "argv", ["pytest"])
        redis_state.record_worker_code_alive()
        assert fake.strings == {}


# ---------------------------------------------------------------------------
# Identity — per SLOT, and the two apps must separate without dyno metadata
# ---------------------------------------------------------------------------

class TestWorkerIdentity:
    def test_a_restarted_worker_reuses_its_slot_key(self, monkeypatch):
        """No pid in the identity, and that is the whole point.

        `beat_identity` includes the pid because two beats in one place ARE the
        hazard. Here the question is what code a slot is running, so the new
        process must overwrite the old answer. With a pid in the key, every
        deploy would leave the previous slug beside the new one and the census
        would report DRIFTED for a full TTL after the deploy that fixed it —
        i.e. it would be wrong at the exact moment anybody reads it.
        """
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        monkeypatch.setenv("DYNO", "worker-heavy.1")

        monkeypatch.setattr(redis_state.os, "getpid", lambda: 111)
        one = redis_state.worker_code_identity()
        monkeypatch.setattr(redis_state.os, "getpid", lambda: 222)
        two = redis_state.worker_code_identity()

        assert one == two == "bainluck-heavy/worker-heavy.1"

    def test_the_two_apps_separate_with_no_dyno_metadata(self, monkeypatch):
        """The collision that would hide the defect outright.

        `HEROKU_APP_NAME` arrives with the `runtime-dyno-metadata` lab, which is
        enabled on `bainluck` and NOT on `bainluck-heavy` — absent on exactly the
        app being watched. If identity depended on it, a `worker-heavy.1` on each
        app would share one key, one would overwrite the other, and a fleet on
        two different commits would be reported as one agreeing fleet.
        """
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        monkeypatch.setenv("DYNO", "worker-heavy.1")

        monkeypatch.setenv("HEAVY_APP", "1")
        heavy = redis_state.worker_code_identity()
        monkeypatch.delenv("HEAVY_APP", raising=False)
        main = redis_state.worker_code_identity()

        assert heavy != main

    @pytest.mark.parametrize("value", ["0", "", "false", "no"])
    def test_only_the_exact_string_1_means_the_heavy_app(self, monkeypatch, value):
        """One app-identity rule in this repo, not two that drift apart.

        The Procfile release line tests `HEAVY_APP` for the exact string `'1'`
        (`test_heavy_app_release_guard.py`), because a truthy test would read
        someone spelling "off" as `HEAVY_APP=0` as the heavy app and skip the
        migrations. The same spelling must mean the same app here.
        """
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        monkeypatch.setenv("HEAVY_APP", value)
        assert redis_state.worker_app_label() == "unnamed"

    def test_app_name_is_used_when_present(self, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        monkeypatch.setenv("DYNO", "worker-background.1")
        assert redis_state.worker_code_identity() == "bainluck/worker-background.1"


# ---------------------------------------------------------------------------
# The stamp
# ---------------------------------------------------------------------------

class TestRecordWorkerCodeAlive:
    def test_stamps_a_key_named_for_the_slot_with_a_ttl(self, fake, as_worker, monkeypatch):
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
        monkeypatch.setenv("DYNO", "worker-heavy.1")

        redis_state.record_worker_code_alive(now_s=1000.0)

        key = f"{WORKER_CODE_PREFIX}:bainluck-heavy/worker-heavy.1"
        assert key in fake.strings
        # The TTL is the expiry mechanism: a slot that stops stamping must drop
        # out on its own, or a decommissioned app would be reported as a live
        # member of the fleet forever.
        assert fake.ttls[key] == redis_state.WORKER_CODE_TTL_S

    def test_the_stamp_carries_the_slug_it_is_running(self, fake, as_worker, monkeypatch):
        """The writer half. Seeded-reader tests below cover how a slug is
        REPORTED and none of them would notice if the stamp never recorded one."""
        monkeypatch.setenv("HEROKU_SLUG_COMMIT", "cc705833" + "a" * 32)

        redis_state.record_worker_code_alive(now_s=1000.0)

        key = f"{WORKER_CODE_PREFIX}:{redis_state.worker_code_identity()}"
        assert json.loads(fake.strings[key].decode())["slug"] == "cc705833"

    def test_the_stamp_records_no_slug_rather_than_a_wrong_one(self, fake, as_worker, monkeypatch):
        """No dyno metadata means unknown, and unknown must reach the reader.

        The tempting shortcut — fall back to the reader's own commit, or to
        "current" — would make the census report agreement on precisely the app
        it was built because nobody could see.
        """
        monkeypatch.delenv("HEROKU_SLUG_COMMIT", raising=False)
        redis_state.record_worker_code_alive(now_s=1000.0)

        key = f"{WORKER_CODE_PREFIX}:{redis_state.worker_code_identity()}"
        assert json.loads(fake.strings[key].decode())["slug"] is None

    def test_throttled_within_the_refresh_window(self, fake, as_worker):
        redis_state.record_worker_code_alive(now_s=1000.0)
        fake.strings.clear()

        redis_state.record_worker_code_alive(
            now_s=1000.0 + redis_state.WORKER_CODE_REFRESH_S - 1)
        assert fake.strings == {}, "re-stamped inside the throttle window"

        redis_state.record_worker_code_alive(
            now_s=1000.0 + redis_state.WORKER_CODE_REFRESH_S)
        assert fake.strings, "never re-stamped after the throttle window"

    def test_a_redis_fault_costs_one_stamp_not_the_next_window(self, monkeypatch, as_worker):
        """The throttle clock advances only on a write that succeeded."""
        monkeypatch.setattr(redis_state, "_last_worker_code_stamp_s", 0.0)
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _DeadRedis())
        redis_state.record_worker_code_alive(now_s=1000.0)  # must not raise

        good = _Redis()
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: good)
        redis_state.record_worker_code_alive(now_s=1001.0)
        assert good.strings, "a failed stamp consumed the throttle window"

    def test_never_raises_in_front_of_a_task(self, monkeypatch, as_worker):
        """Best-effort by contract: this sits on `task_prerun`, so a Redis fault
        costs a stamp and never a run."""
        monkeypatch.setattr(redis_state, "_last_worker_code_stamp_s", 0.0)
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _DeadRedis())
        redis_state.record_worker_code_alive(now_s=1000.0)

    def test_the_ttl_clears_the_slowest_cadence_and_is_still_bounded(self):
        """Pinned from BOTH sides, because it is a tuned constant.

        Lower bound: the tightest heavy-queue entry is `match_prediction_markets`
        every 15 minutes (337s p50), so a live worker touches this path ~4x an
        hour. A TTL at or under that cadence would expire a healthy worker into
        `unknown` between two runs and manufacture the alarm.

        Upper bound: a slot scaled away keeps its marker for the whole TTL, so a
        day-long TTL would report a decommissioned app as a live fleet member
        through an entire working day.
        """
        assert redis_state.WORKER_CODE_TTL_S >= 4 * 15 * 60
        assert redis_state.WORKER_CODE_TTL_S <= 4 * 60 * 60
        assert redis_state.WORKER_CODE_REFRESH_S >= 30
        assert redis_state.WORKER_CODE_TTL_S >= 10 * redis_state.WORKER_CODE_REFRESH_S


# ---------------------------------------------------------------------------
# The census — facts only
# ---------------------------------------------------------------------------

class TestGetWorkerCodeCensus:
    def test_lists_each_slot_and_the_slug_it_named(self, fake):
        fake.strings[f"{WORKER_CODE_PREFIX}:bainluck/worker-background.1"] = _marker("137bf299")
        fake.strings[f"{WORKER_CODE_PREFIX}:heavy-unnamed/worker-heavy.1"] = _marker("cc705833")

        out = redis_state.get_worker_code_census()

        assert out["count"] == 2
        assert out["workers"] == [
            "bainluck/worker-background.1",
            "heavy-unnamed/worker-heavy.1",
        ]
        assert out["slugs"] == ["137bf299", "cc705833"]

    def test_an_unreadable_redis_raises_rather_than_reading_as_an_empty_fleet(self, monkeypatch):
        """gotcha #53: an outage and "no worker has ever stamped" must not
        produce one answer, and neither may be rendered as "no drift"."""
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: _DeadRedis())
        with pytest.raises(WorkerCodeCensusUnavailable):
            redis_state.get_worker_code_census()

    def test_a_marker_in_an_unexpected_shape_is_still_a_LIVE_WORKER(self, fake):
        """Dropping it would under-count the fleet while it is half-upgraded,
        which is during a deploy, which is when this census is read."""
        fake.strings[f"{WORKER_CODE_PREFIX}:bainluck/worker-heavy.1"] = b"1"

        out = redis_state.get_worker_code_census()

        assert out["count"] == 1
        assert out["slugs"] == ["unknown"]

    def test_the_census_reads_only_its_own_namespace(self, fake):
        fake.strings[f"{WORKER_CODE_PREFIX}:bainluck/worker-heavy.1"] = _marker("137bf299")
        fake.strings["bainluck:beat_alive:bainluck/scheduler.1/10"] = _marker("137bf299")
        fake.strings["bainluck:task_lifecycle:x:attempts"] = b"5"

        assert redis_state.get_worker_code_census()["workers"] == [
            "bainluck/worker-heavy.1"
        ]


# ---------------------------------------------------------------------------
# The verdict — pure, so it can be asked about states this fleet has not reached
# ---------------------------------------------------------------------------

class TestFleetCodeVerdict:
    def test_everyone_on_the_readers_slug_is_MATCHED(self):
        out = fleet_code_verdict("137bf299", {
            "bainluck/worker-background.1": {"slug": "137bf299"},
            "bainluck/worker-realtime.1": {"slug": "137bf299"},
        })
        assert out["verdict"] == "MATCHED"
        assert out["drifted"] == []

    def test_a_stale_worker_is_DRIFTED_and_is_NAMED(self):
        """The live defect: which APP is stale is the only useful form of the
        answer, so the census stores identity rather than a count."""
        out = fleet_code_verdict("137bf299", {
            "bainluck/worker-background.1": {"slug": "137bf299"},
            "heavy-unnamed/worker-heavy.1": {"slug": "cc705833"},
        })
        assert out["verdict"] == "DRIFTED"
        assert out["drifted"] == ["heavy-unnamed/worker-heavy.1"]
        assert out["matched"] == ["bainluck/worker-background.1"]

    def test_an_unknown_slug_is_never_MATCHED(self):
        """THE CENTRAL PROPERTY. `bainluck-heavy` has no `runtime-dyno-metadata`,
        so its workers cannot name their slug at all. Reading that silence as
        agreement would reproduce the original defect with an instrument bolted
        on top — the receipt would go on reading green."""
        out = fleet_code_verdict("137bf299", {
            "bainluck/worker-background.1": {"slug": "137bf299"},
            "heavy-unnamed/worker-heavy.1": {"slug": None},
        })
        assert out["verdict"] == "UNKNOWN_VERSION"
        assert out["unknown"] == ["heavy-unnamed/worker-heavy.1"]

    def test_a_legacy_marker_with_no_slug_key_is_unknown_not_agreeing(self):
        out = fleet_code_verdict("137bf299", {"bainluck/worker-heavy.1": {}})
        assert out["verdict"] == "UNKNOWN_VERSION"

    def test_a_provable_drift_outranks_an_unknown(self):
        """Precedence, stated: an unknown is a gap in the instrument, a drift is
        a defect in the fleet. Reporting the gap would bury the defect."""
        out = fleet_code_verdict("137bf299", {
            "a/worker.1": {"slug": None},
            "b/worker.1": {"slug": "cc705833"},
        })
        assert out["verdict"] == "DRIFTED"
        assert out["drifted"] == ["b/worker.1"]
        assert out["unknown"] == ["a/worker.1"]

    def test_no_worker_at_all_is_NONE_and_NONE_is_not_healthy(self):
        out = fleet_code_verdict("137bf299", {})
        assert out["verdict"] == "NONE"

    def test_a_reader_with_no_slug_cannot_certify_agreement(self):
        """A laptop, CI, or an app whose own lab is off. Every worker agreeing on
        one slug still says nothing about whether it is the CURRENT one, so
        inventing a baseline out of that agreement would turn "we could not
        check" into "we checked"."""
        out = fleet_code_verdict(None, {
            "a/worker.1": {"slug": "cc705833"},
            "b/worker.1": {"slug": "cc705833"},
        })
        assert out["verdict"] == "UNKNOWN_VERSION"
        assert out["reader_slug"] is None

    def test_workers_contradicting_each_other_is_DRIFTED_with_no_baseline(self):
        """Decidable without any baseline at all: they cannot all be right.
        (Memory of the same shape: some defects are decidable from the rows
        alone, with no ground truth.)"""
        out = fleet_code_verdict(None, {
            "a/worker.1": {"slug": "cc705833"},
            "b/worker.1": {"slug": "137bf299"},
        })
        assert out["verdict"] == "DRIFTED"
        assert out["drifted"] == ["a/worker.1", "b/worker.1"]

    def test_an_empty_string_slug_is_unknown_not_a_value(self):
        """`''` and absent are the same fact here and must not split into two
        answers — an empty string would otherwise compare unequal to the reader
        and read as a DRIFT that is really a missing variable."""
        out = fleet_code_verdict("137bf299", {"a/worker.1": {"slug": ""}})
        assert out["verdict"] == "UNKNOWN_VERSION"


# ---------------------------------------------------------------------------
# The composition — the two halves must truncate the same way
# ---------------------------------------------------------------------------

class TestFleetCodeReport:
    def test_a_worker_on_the_readers_own_release_reports_MATCHED_end_to_end(
        self, fake, as_worker, monkeypatch
    ):
        """Writer and reader must agree on the FORM of a slug, not just its value.

        Heroku's `HEROKU_SLUG_COMMIT` is a full 40-character sha; the stamp keeps
        8. If either side stopped truncating, every comparison in the fleet would
        come back DRIFTED — a permanent false alarm on a healthy fleet, which is
        the failure mode that gets an alarm switched off.
        """
        monkeypatch.setenv("HEROKU_SLUG_COMMIT", "137bf299" + "b" * 32)
        monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
        monkeypatch.setenv("DYNO", "worker-background.1")

        redis_state.record_worker_code_alive(now_s=1000.0)
        report = redis_state.get_fleet_code_report()

        assert report["verdict"] == "MATCHED"
        assert report["reader_slug"] == "137bf299"
        assert report["matched"] == ["bainluck/worker-background.1"]

    def test_the_reader_slug_can_be_stated_rather_than_taken_from_the_ambient_env(
        self, fake
    ):
        fake.strings[f"{WORKER_CODE_PREFIX}:heavy-unnamed/worker-heavy.1"] = _marker("cc705833")
        assert redis_state.get_fleet_code_report("137bf299")["verdict"] == "DRIFTED"


# ---------------------------------------------------------------------------
# The wiring — the census is worthless if nothing stamps it
# ---------------------------------------------------------------------------

class TestPrerunHookWiring:
    """THE HOOK IS INVOKED, NOT READ.

    The first version of this class scanned the hook's source for the recorder's
    name, and a mutation battery walked straight through it: deleting the
    recorder from the hook's `from app.tasks.redis_state import (...)` line
    leaves the CALL in the source — so the scan still passes — while the call
    itself raises `NameError` into the hook's own bare `except Exception: pass`
    and the census silently never gets stamped again. A source scan can prove a
    call is written down; only an invocation proves it runs.
    """

    class _Request:
        def __init__(self, retries=0, is_eager=False):
            self.retries = retries
            self.is_eager = is_eager

    class _Sender:
        name = "app.tasks.match_prediction_markets"

        def __init__(self, request):
            self.request = request

    @pytest.fixture
    def spies(self, monkeypatch):
        """Silence the three delivery counters, watch the code stamp."""
        seen = {"code": 0, "delivery": 0}
        monkeypatch.setattr(redis_state, "record_task_attempt", lambda *a, **k: None)
        monkeypatch.setattr(
            redis_state, "record_task_delivery_bucket", lambda *a, **k: None)
        monkeypatch.setattr(
            redis_state, "record_worker_code_alive",
            lambda *a, **k: seen.__setitem__("code", seen["code"] + 1))
        monkeypatch.setattr(
            redis_state, "record_task_delivery",
            lambda *a, **k: seen.__setitem__("delivery", seen["delivery"] + 1))
        return seen

    def test_the_delivery_hook_stamps_the_running_code(self, spies):
        """`task_prerun` is the one place that runs inside every worker process
        on a cadence, so it is the only thing that can keep the census fresh."""
        from app import tasks as tasks_pkg

        tasks_pkg._record_delivery(sender=self._Sender(self._Request()), task=None)

        assert spies["code"] == 1

    @pytest.mark.parametrize("request_kwargs", [
        {"retries": 1},        # a retry is not a beat fire...
        {"is_eager": True},    # ...and an eager call never crossed a wire
    ])
    def test_the_stamp_survives_the_filters_written_for_the_schedule_question(
        self, spies, request_kwargs
    ):
        """A retry does not make this worker less alive, or its slug less true.

        Both filters exist because a fact about the TASK was being read as a fact
        about the SCHEDULER. Inheriting them here would repeat that mistake one
        question over: this stamp is a fact about the PROCESS. Asserted
        behaviourally — the delivery counter must stop and the code stamp must
        not — because an ordering assertion over source text passes just as
        happily when the call has been deleted.
        """
        from app import tasks as tasks_pkg

        tasks_pkg._record_delivery(
            sender=self._Sender(self._Request(**request_kwargs)), task=None)

        assert spies["delivery"] == 0, "the filter under test did not fire"
        assert spies["code"] == 1, "the code stamp inherited a filter that is not about it"


# ---------------------------------------------------------------------------
# The endpoint — CERT-2675's rule, on the sibling route this one was copied from
# ---------------------------------------------------------------------------

class TestEndpointNeverEchoesTheException:
    """A Redis error string carries the URL it was dialling, and on Heroku the
    credentials embedded in `REDIS_URL` with it. CodeQL calls it "information
    exposure through an exception"; CERT-2675 withheld a token for exactly this
    shape on `/celery/beat-instances`, which this endpoint is modelled on.

    The assertion is made against the WHOLE serialized response rather than the
    `error` key, because the defect is "this text reaches a reader" and a later
    edit moving it into `reason` or a nested dict would satisfy a key-scoped
    assertion while changing nothing about the exposure.
    """

    SENTINEL = "redis://h:sekrit-passw0rd@ec2-1-2-3-4.compute.amazonaws.com:6379"

    def _call(self, monkeypatch, exc):
        import asyncio

        from app.routes import admin_celery
        from app.tasks import redis_state as rs

        monkeypatch.setattr(admin_celery, "_check_admin_secret", lambda *a, **k: None)

        def _boom(*a, **k):
            raise exc

        monkeypatch.setattr(rs, "get_fleet_code_report", _boom)
        out = asyncio.run(admin_celery.fleet_code(request=None, secret="x"))
        return out, json.dumps(out)

    def test_an_unreadable_census_never_echoes_exception_details(self, monkeypatch):
        out, body = self._call(monkeypatch, WorkerCodeCensusUnavailable(self.SENTINEL))

        assert self.SENTINEL not in body
        assert "sekrit-passw0rd" not in body
        # and suppressing the detail must not turn an outage into a quiet pass.
        assert out["verdict"] == "INCONCLUSIVE"
        assert out["status"] == "unreadable"

    def test_the_detail_is_logged_rather_than_discarded(self, monkeypatch, caplog):
        """Suppressed is not lost — otherwise the cheapest way to pass the test
        above is to delete the information and trade a disclosure bug for a
        debugging one."""
        import logging

        with caplog.at_level(logging.ERROR, logger="app.routes.admin_celery"):
            self._call(monkeypatch, WorkerCodeCensusUnavailable(self.SENTINEL))

        assert any(
            self.SENTINEL in r.getMessage() or self.SENTINEL in str(r.exc_info)
            for r in caplog.records
        ), "the cause must reach the log even though it must not reach the body"

    def test_the_endpoint_is_behind_the_admin_secret(self, monkeypatch):
        """It names dyno slots and release shas. Not a secret, not public either
        — and the sibling census next door is gated the same way."""
        import asyncio

        from app.routes import admin_celery

        called = {}

        def _check(secret, request=None):
            called["yes"] = True
            raise PermissionError("denied")

        monkeypatch.setattr(admin_celery, "_check_admin_secret", _check)
        with pytest.raises(PermissionError):
            asyncio.run(admin_celery.fleet_code(request=None, secret="wrong"))
        assert called
