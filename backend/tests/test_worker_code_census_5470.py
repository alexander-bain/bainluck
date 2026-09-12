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

def _full_fleet(slug):
    """One stamped slot per expected worker family — the only MATCHED shape."""
    return {
        f"bainluck/{name}.1": {"slug": slug}
        for name in redis_state.EXPECTED_WORKER_PROCESSES
    }


class TestFleetCodeVerdict:
    def test_everyone_on_the_readers_slug_is_MATCHED(self):
        out = fleet_code_verdict("137bf299", _full_fleet("137bf299"))
        assert out["verdict"] == "MATCHED"
        assert out["drifted"] == []
        assert out["unstamped_expected"] == []

    def test_a_stale_worker_is_DRIFTED_and_is_NAMED(self):
        """The live defect: which APP is stale is the only useful form of the
        answer, so the census stores identity rather than a count.

        Built by mutating ONE member of a full fleet, so the verdict can only be
        coming from the drift — a hand-built two-slot dict would also be missing
        an expected family and would pass through a different branch.
        """
        fleet = _full_fleet("137bf299")
        fleet.pop("bainluck/worker-heavy.1")
        fleet["heavy-unnamed/worker-heavy.1"] = {"slug": "cc705833"}

        out = fleet_code_verdict("137bf299", fleet)

        assert out["verdict"] == "DRIFTED"
        assert out["drifted"] == ["heavy-unnamed/worker-heavy.1"]
        assert out["unstamped_expected"] == []

    def test_an_unknown_slug_is_never_MATCHED(self):
        """THE CENTRAL PROPERTY. `bainluck-heavy` has no `runtime-dyno-metadata`,
        so its workers cannot name their slug at all. Reading that silence as
        agreement would reproduce the original defect with an instrument bolted
        on top — the receipt would go on reading green."""
        fleet = _full_fleet("137bf299")
        fleet["bainluck/worker-heavy.1"] = {"slug": None}

        out = fleet_code_verdict("137bf299", fleet)

        assert out["verdict"] == "UNKNOWN_VERSION"
        assert out["unknown"] == ["bainluck/worker-heavy.1"]

    def test_a_legacy_marker_with_no_slug_key_is_unknown_not_agreeing(self):
        fleet = _full_fleet("137bf299")
        fleet["bainluck/worker-heavy.1"] = {}
        assert fleet_code_verdict("137bf299", fleet)["verdict"] == "UNKNOWN_VERSION"

    def test_a_provable_drift_outranks_an_unknown(self):
        """Precedence, stated: an unknown is a gap in the instrument, a drift is
        a defect in the fleet. Reporting the gap would bury the defect."""
        fleet = _full_fleet("137bf299")
        fleet["bainluck/worker-realtime.1"] = {"slug": None}
        fleet["bainluck/worker-heavy.1"] = {"slug": "cc705833"}

        out = fleet_code_verdict("137bf299", fleet)

        assert out["verdict"] == "DRIFTED"
        assert out["drifted"] == ["bainluck/worker-heavy.1"]
        assert out["unknown"] == ["bainluck/worker-realtime.1"]

    def test_no_worker_at_all_is_NONE_and_NONE_is_not_healthy(self):
        out = fleet_code_verdict("137bf299", {})
        assert out["verdict"] == "NONE"

    def test_a_reader_with_no_slug_cannot_certify_agreement(self):
        """A laptop, CI, or an app whose own lab is off. Every worker agreeing on
        one slug still says nothing about whether it is the CURRENT one, so
        inventing a baseline out of that agreement would turn "we could not
        check" into "we checked"."""
        out = fleet_code_verdict(None, _full_fleet("cc705833"))
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
        fleet = _full_fleet("137bf299")
        fleet["bainluck/worker-heavy.1"] = {"slug": ""}
        assert fleet_code_verdict("137bf299", fleet)["verdict"] == "UNKNOWN_VERSION"


class TestSilenceIsNotAgreement:
    """The hole this census would otherwise have had, found by walking its own
    rollout: **a worker too stale to carry the recorder does not appear at all.**

    On the day this ships, `bainluck-heavy` is 84 commits behind. Its worker will
    not stamp — not with an unknown slug, but with nothing whatsoever — while the
    main app's two workers stamp and match. Without an expectation, the census
    would then report MATCHED, and the instrument built to expose the drift would
    have certified it on the strength of the stale machine's silence. Absence is
    the one state a census cannot see by looking harder; it has to be declared.
    """

    def test_an_expected_worker_that_never_stamped_is_not_a_pass(self):
        fleet = _full_fleet("137bf299")
        del fleet["bainluck/worker-heavy.1"]

        out = fleet_code_verdict("137bf299", fleet)

        assert out["verdict"] == "UNKNOWN_VERSION"
        assert out["unstamped_expected"] == ["worker-heavy"]
        # ...and the ones that DID answer are still reported as matching, so the
        # reader can see the gap is one app rather than the whole fleet.
        assert out["matched"] == [
            "bainluck/worker-background.1", "bainluck/worker-realtime.1",
        ]

    def test_a_provable_drift_still_outranks_a_silence(self):
        """Same precedence as the unknown case: a silence is a gap in the
        instrument's reach, a drift is a defect in the fleet."""
        fleet = _full_fleet("137bf299")
        del fleet["bainluck/worker-realtime.1"]
        fleet["bainluck/worker-heavy.1"] = {"slug": "cc705833"}

        assert fleet_code_verdict("137bf299", fleet)["verdict"] == "DRIFTED"

    def test_the_family_is_matched_on_the_whole_segment_not_a_prefix(self):
        """A prefix test would let `worker-heavy-2.1` vouch for `worker-heavy`,
        and a bare `worker` would let any one worker vouch for all three — either
        way the check becomes decoration."""
        fleet = _full_fleet("137bf299")
        del fleet["bainluck/worker-heavy.1"]
        fleet["bainluck/worker-heavy-2.1"] = {"slug": "137bf299"}

        out = fleet_code_verdict("137bf299", fleet)

        assert out["unstamped_expected"] == ["worker-heavy"]
        assert out["verdict"] == "UNKNOWN_VERSION"

    def test_main_only_census_cannot_match_when_heavy_slot_is_missing_5470(
        self, fake, monkeypatch
    ):
        """CERT-2692's required repair `5470-CENSUS-REFUSES-A-PARTIAL-FLEET`,
        by the name the block asked for, and through the READ PATH rather than
        the pure verdict — the grader's probe went through Redis, and a pure
        function passing says nothing about what the endpoint returns.

        This is the exact production state on the day this ships: the main app's
        two workers carry the recorder and stamp; `bainluck-heavy` is 84 commits
        behind, carries no recorder, and writes nothing at all.
        """
        monkeypatch.setenv("HEROKU_SLUG_COMMIT", "137bf299")
        for name in ("worker-realtime", "worker-background"):
            fake.strings[f"{WORKER_CODE_PREFIX}:bainluck/{name}.1"] = _marker("137bf299")

        report = redis_state.get_fleet_code_report()

        assert report["verdict"] != "MATCHED"
        assert report["verdict"] == "UNKNOWN_VERSION"
        assert report["unstamped_expected"] == ["worker-heavy"]

    def test_an_expired_marker_is_the_same_non_pass_as_one_never_written(
        self, fake, monkeypatch
    ):
        """The second half of the required repair: TTL-expiry coverage.

        A heavy slot that stamped once and then went away — scaled to zero, or
        dead — loses its key when `WORKER_CODE_TTL_S` runs out. That is a
        DIFFERENT cause from "too stale to carry the recorder" and arrives at the
        same place: an absent key. It must not be the moment the census relaxes
        into MATCHED, which is what a membership list built only from present
        keys would do.

        Expiry is modelled by deleting the key, because that is precisely what
        Redis does at the TTL; the TTL VALUE itself is pinned separately in
        `test_the_ttl_clears_the_slowest_cadence_and_is_still_bounded`.
        """
        monkeypatch.setenv("HEROKU_SLUG_COMMIT", "137bf299")
        for name in redis_state.EXPECTED_WORKER_PROCESSES:
            fake.strings[f"{WORKER_CODE_PREFIX}:bainluck/{name}.1"] = _marker("137bf299")

        assert redis_state.get_fleet_code_report()["verdict"] == "MATCHED"

        del fake.strings[f"{WORKER_CODE_PREFIX}:bainluck/worker-heavy.1"]

        after = redis_state.get_fleet_code_report()
        assert after["verdict"] == "UNKNOWN_VERSION"
        assert after["unstamped_expected"] == ["worker-heavy"]

    def test_the_expectation_is_exactly_the_procfiles_celery_workers(self):
        """Parsed from the Procfile, because a hand-maintained list of dynos is
        wrong the first time the formation changes — and wrong in the quiet
        direction, since a family nobody expects can go stale unobserved.

        `worker-ws` must NOT be expected: it is `python3 run_kalshi_ws.py`, runs
        no celery tasks, and would therefore never stamp. Expecting it would put
        a permanent UNKNOWN_VERSION on a healthy fleet, and a verdict that is
        never green is a verdict nobody reads.
        """
        from pathlib import Path

        procfile = Path(__file__).resolve().parents[1] / "Procfile"
        workers = set()
        for line in procfile.read_text().splitlines():
            if ":" not in line:
                continue
            name, command = line.split(":", 1)
            if "celery" in command and " worker" in command:
                workers.add(name.strip())

        assert workers, "parsed no worker lines out of the Procfile — check the parse"
        assert set(redis_state.EXPECTED_WORKER_PROCESSES) == workers
        assert "worker-ws" not in redis_state.EXPECTED_WORKER_PROCESSES
        assert "scheduler" not in redis_state.EXPECTED_WORKER_PROCESSES


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

        # This process stands in for ONE worker; the other two expected families
        # are seeded as their own stamps, because a real MATCHED needs the whole
        # fleet to have answered and this test is about the slug FORM, not the
        # expectation.
        for name in ("worker-realtime", "worker-heavy"):
            fake.strings[f"{WORKER_CODE_PREFIX}:bainluck/{name}.1"] = _marker("137bf299")

        redis_state.record_worker_code_alive(now_s=1000.0)
        report = redis_state.get_fleet_code_report()

        assert report["verdict"] == "MATCHED"
        assert report["reader_slug"] == "137bf299"
        assert "bainluck/worker-background.1" in report["matched"]

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


# ---------------------------------------------------------------------------
# How long, not just whether (#5470, after #5662)
#
# Until heavy self-sync shipped, `bainluck-heavy` moved only when a person
# redeployed it, so `slug != reader` WAS the defect and the word DRIFTED was
# rare enough to mean something. #5662 made main release several times an hour
# and heavy converge behind it, so DRIFTED became the steady state: read live at
# 22:15Z on 9/12 with heavy HEALTHY (it had self-synced 37 minutes earlier), the
# endpoint said DRIFTED. Notice 48 asks every lane to read this line to
# discharge a heavy receipt, and a line that is red whenever anyone looks is a
# line nobody reads — the real wedge then hides inside the permanent red.
#
# So the marker carries a second clock and the verdict carries the number. What
# these tests defend is that the number is HONEST where it is absent: a missing
# age must read as "cannot say", never as 0, because 0 renders as "it just
# changed", which is precisely how a worker stuck for a week would pass.
# ---------------------------------------------------------------------------

def _aged_marker(slug, since, ts=None):
    return json.dumps(
        {"ts": ts if ts is not None else since, "slug": slug, "slug_since": since}
    ).encode()


class TestTheStampRemembersWhenTheCodeChanged:
    KEY = f"{WORKER_CODE_PREFIX}:heavy-unnamed/worker-heavy.1"

    def _stamp(self, fake, monkeypatch, slug, now):
        monkeypatch.setenv("HEAVY_APP", "1")
        monkeypatch.setenv("DYNO", "worker-heavy.1")
        monkeypatch.delenv("HEROKU_APP_NAME", raising=False)
        if slug is None:
            monkeypatch.delenv("HEROKU_SLUG_COMMIT", raising=False)
        else:
            monkeypatch.setenv("HEROKU_SLUG_COMMIT", slug)
        monkeypatch.setattr(redis_state, "_last_worker_code_stamp_s", 0.0)
        redis_state.record_worker_code_alive(now_s=now)
        return json.loads(fake.strings[self.KEY].decode())

    def test_a_first_stamp_dates_the_code_to_now(self, fake, as_worker, monkeypatch):
        got = self._stamp(fake, monkeypatch, "aaaaaaaa", now=1_000_000)
        assert got["slug_since"] == 1_000_000

    def test_the_same_slug_carries_its_original_date_so_the_age_GROWS(
        self, fake, as_worker, monkeypatch
    ):
        """The whole point. If each stamp reset the clock, a worker wedged for a
        week would report an age of `REFRESH_S` forever — the instrument would
        agree with the bug."""
        self._stamp(fake, monkeypatch, "aaaaaaaa", now=1_000_000)
        later = self._stamp(fake, monkeypatch, "aaaaaaaa", now=1_600_000)

        assert later["slug_since"] == 1_000_000, "the date of the CODE, not of the stamp"
        assert later["ts"] == 1_600_000, "liveness is still the stamp's own clock"

    def test_a_new_slug_resets_the_date(self, fake, as_worker, monkeypatch):
        """A converging worker must look converging: heavy landing on a new sha
        is the healthy event, and inheriting the old date would render the
        recovery as a deepening wedge."""
        self._stamp(fake, monkeypatch, "aaaaaaaa", now=1_000_000)
        after = self._stamp(fake, monkeypatch, "bbbbbbbb", now=1_600_000)
        assert after["slug_since"] == 1_600_000

    def test_a_marker_written_before_this_shipped_restarts_the_clock(
        self, fake, as_worker, monkeypatch
    ):
        """A legacy marker has a `ts` and no `slug_since`. Adopting its `ts`
        would be inventing a measurement nobody took; `now` understates the age,
        which is the direction that cannot manufacture a false alarm."""
        fake.strings[self.KEY] = _marker("aaaaaaaa", ts=500)
        got = self._stamp(fake, monkeypatch, "aaaaaaaa", now=1_000_000)
        assert got["slug_since"] == 1_000_000

    def test_two_consecutive_unknowns_are_not_stability(
        self, fake, as_worker, monkeypatch
    ):
        """A worker that cannot name its code has nothing to have been on
        since."""
        first = self._stamp(fake, monkeypatch, None, now=1_000_000)
        second = self._stamp(fake, monkeypatch, None, now=1_600_000)
        assert first["slug"] is None and second["slug"] is None
        assert second["slug_since"] == 1_600_000

    @pytest.mark.parametrize("poison", [0, -1, 9_999_999_999, "yesterday", None])
    def test_an_unusable_carried_date_is_refused_not_propagated(
        self, fake, as_worker, monkeypatch, poison
    ):
        """A future date (a clock that went backwards) would freeze this worker's
        age negative forever, and age is the entire signal."""
        fake.strings[self.KEY] = json.dumps(
            {"ts": 500, "slug": "aaaaaaaa", "slug_since": poison}
        ).encode()
        got = self._stamp(fake, monkeypatch, "aaaaaaaa", now=1_000_000)
        assert got["slug_since"] == 1_000_000

    def test_a_fault_reading_the_PRIOR_marker_still_lands_the_NEW_stamp(
        self, as_worker, monkeypatch
    ):
        """The read is an enrichment. Letting it escape into the caller's except
        would drop the stamp entirely and turn a healthy worker into an absence,
        which this census reads as UNKNOWN_VERSION — a worse answer than a reset
        clock."""
        class _GetFails(_Redis):
            def get(self, key):
                raise ConnectionError("redis read is gone")

        r = _GetFails()
        monkeypatch.setattr(redis_state, "get_redis_client", lambda: r)
        got = json.loads(self._stamp(r, monkeypatch, "aaaaaaaa", now=1_000_000)
                         and r.strings[self.KEY].decode())
        assert got["slug"] == "aaaaaaaa"
        assert got["slug_since"] == 1_000_000


class TestTheVerdictCarriesTheNumberNotJustTheWord:
    def test_each_worker_reports_its_age_on_its_current_code(self):
        got = fleet_code_verdict(
            "cccccccc",
            {
                "bainluck/worker-realtime.1": {"slug": "cccccccc", "slug_since": 9_000},
                "bainluck/worker-background.1": {"slug": "cccccccc", "slug_since": 9_000},
                "bainluck-heavy/worker-heavy.1": {"slug": "aaaaaaaa", "slug_since": 8_000},
            },
            now_s=10_000,
        )
        assert got["on_slug_s"]["bainluck-heavy/worker-heavy.1"] == 2_000
        assert got["on_slug_s"]["bainluck/worker-realtime.1"] == 1_000

    def test_an_age_that_cannot_be_measured_is_None_and_NEVER_zero(self):
        """0 renders as "it just changed" — the reading under which a worker
        stuck for a week passes. A legacy marker must say "cannot say"."""
        got = fleet_code_verdict(
            "cccccccc",
            {
                "bainluck/worker-realtime.1": {"slug": "cccccccc"},
                "bainluck/worker-background.1": {"slug": "cccccccc"},
                "bainluck-heavy/worker-heavy.1": {"slug": "aaaaaaaa"},
            },
            now_s=10_000,
        )
        ages = got["on_slug_s"]
        assert set(ages) == {
            "bainluck/worker-realtime.1",
            "bainluck/worker-background.1",
            "bainluck-heavy/worker-heavy.1",
        }
        assert all(v is None for v in ages.values())
        assert 0 not in ages.values()

    def test_the_drift_reason_states_how_long_and_a_long_wedge_reads_DIFFERENTLY(self):
        """Vacuity guard: the verdict word is identical in both, so if the
        reason did not move, this instrument would still be the one that cannot
        tell one desk batch from six days."""
        def _reason(age_s):
            return fleet_code_verdict(
                "cccccccc",
                {
                    "bainluck/worker-realtime.1": {"slug": "cccccccc", "slug_since": 1},
                    "bainluck/worker-background.1": {"slug": "cccccccc", "slug_since": 1},
                    "bainluck-heavy/worker-heavy.1": {
                        "slug": "aaaaaaaa", "slug_since": 1_000_000 - age_s
                    },
                },
                now_s=1_000_000,
            )

        fresh = _reason(40 * 60)
        wedged = _reason(6 * 24 * 3600)

        assert fresh["verdict"] == wedged["verdict"] == "DRIFTED"
        assert "40m" in fresh["reason"]
        assert "144h00m" in wedged["reason"]
        assert fresh["reason"] != wedged["reason"]

    def test_the_reason_reports_the_STALEST_not_an_average(self):
        """A fleet is as wedged as its worst slot, and one fresh restart must
        not bury one stuck one."""
        got = fleet_code_verdict(
            None,
            {
                "a/worker-realtime.1": {"slug": "aaaaaaaa", "slug_since": 1_000_000 - 60},
                "b/worker-heavy.1": {"slug": "bbbbbbbb", "slug_since": 1_000_000 - 36_000},
            },
            expected=(),
            now_s=1_000_000,
        )
        assert got["verdict"] == "DRIFTED"
        assert "10h00m" in got["reason"], got["reason"]

    def test_all_ages_unknown_says_so_rather_than_going_quiet(self):
        """Silence is not agreement — the same rule `unstamped_expected` exists
        for. A DRIFTED with no age clause would read as a plain old alarm."""
        got = fleet_code_verdict(
            "cccccccc",
            {
                "bainluck/worker-realtime.1": {"slug": "cccccccc"},
                "bainluck/worker-background.1": {"slug": "cccccccc"},
                "bainluck-heavy/worker-heavy.1": {"slug": "aaaaaaaa"},
            },
            now_s=10_000,
        )
        assert got["verdict"] == "DRIFTED"
        assert "NOT known" in got["reason"]

    def test_a_partly_measurable_set_names_how_many_cannot_say(self):
        got = fleet_code_verdict(
            None,
            {
                "a/worker-realtime.1": {"slug": "aaaaaaaa", "slug_since": 1_000_000 - 600},
                "b/worker-heavy.1": {"slug": "bbbbbbbb"},
            },
            expected=(),
            now_s=1_000_000,
        )
        assert "10m" in got["reason"]
        assert "1 of them cannot say" in got["reason"]

    def test_a_MATCHED_fleet_still_publishes_its_ages(self):
        """The matched slots are the control: they say the fleet is moving at
        all, which is what makes a heavy slot's age readable."""
        got = fleet_code_verdict(
            "cccccccc",
            {
                "bainluck/worker-realtime.1": {"slug": "cccccccc", "slug_since": 9_400},
                "bainluck/worker-background.1": {"slug": "cccccccc", "slug_since": 9_400},
                "bainluck-heavy/worker-heavy.1": {"slug": "cccccccc", "slug_since": 9_400},
            },
            now_s=10_000,
        )
        assert got["verdict"] == "MATCHED"
        assert got["on_slug_s"]["bainluck-heavy/worker-heavy.1"] == 600

    def test_no_automatic_BEHIND_verdict_exists_yet(self):
        """Deliberate non-feature, asserted so nobody adds one without the
        measurement. A grace window needs #5662's true convergence period; it is
        measured at 136-294 min on a sample too small to size a bound on, and
        guessing it would hard-code an answer into the instrument asking the
        question (#5470)."""
        got = fleet_code_verdict(
            "cccccccc",
            {
                "bainluck/worker-realtime.1": {"slug": "cccccccc", "slug_since": 1},
                "bainluck/worker-background.1": {"slug": "cccccccc", "slug_since": 1},
                "bainluck-heavy/worker-heavy.1": {"slug": "aaaaaaaa", "slug_since": 999_900},
            },
            now_s=1_000_000,
        )
        assert got["verdict"] == "DRIFTED", "a short age is still DRIFTED, with the number"
