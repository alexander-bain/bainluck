"""LAT-P242 (#3466) — every scheduled task gets a DURATION, and a queue gets a TOTAL.

Why this file exists, in one paragraph, because the defect is an instrument
defect and those are the ones that get re-introduced.

``_tracked_run`` is called BY THE TASK BODY. **32 of the 110 ``background`` beat
entries never call it**, so they have no duration under any label, and every
capacity model built on the label-keyed metrics scored them at ZERO
worker-seconds. latency/180 measured what that costs: the single largest
occupant of the queue in a live ``inspect`` census (``collapse_snapshots``,
45.5% of samples) is one of the 32, so an occupancy timeline reconstructed from
per-task instrumentation reported the queue IDLE during the very holes it was
built to explain, and a queue running at 91% occupancy modelled as having free
slots.

The fix is a third counter in the ``task_prerun``/``task_postrun`` family —
keyed by the celery task name, written with no cooperation from the body — plus
the per-queue total it makes computable. The tests below are grouped by the
claim they defend, and several of them exist because the first implementation
got the thing wrong in exactly that way:

* ``TestTheBeatScheduleIsKeyedByEntryName`` — the beat schedule is keyed by
  ENTRY name, not task name, and the first version looked entries up by task
  name. That silently found nothing and degraded to the default queue, which is
  ``background`` — the queue being sized. The bug would have inflated the very
  number it was built to measure.
* ``TestOneTaskCanHaveSeveralEntries`` — ``collapse_snapshots`` has three beat
  entries and they need not agree about the queue.
* ``TestTheTotalDisclosesWhatItCouldNotPrice`` — the total is a LOWER bound and
  has to say so in fields, not in a comment.
"""
import fnmatch

import pytest

from app.routes.admin_celery import _wall_fields, build_schedule_adherence, queue_demand
from app.tasks import redis_state
from app.tasks.redis_state import TASK_LIFECYCLE_PREFIX
from app.utils.schedule_adherence import QUEUE_SLOTS, beat_queues


class _Redis:
    """Enough Redis for the wall-ms write and read paths.

    ``incrby`` is modelled with real INCRBY semantics (creates a missing key
    with no expiry, never refreshes an existing one) because the window start IS
    the TTL and a double that refreshed it could not express the lifetime-counter
    bug LAT-P022 fixed. ``keys`` uses real glob matching rather than the
    ``rstrip('*')`` shortcut some older doubles use — the reader's pattern has a
    ``*`` in the MIDDLE (``prefix*:wall_ms``) and a prefix-only double would
    return keys the real Redis would not.
    """

    def __init__(self):
        self.strings = {}
        self.ttls = {}

    def pipeline(self):
        return self

    def execute(self):
        return []

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.strings:
            return None
        self.strings[key] = str(value).encode()
        if ex is not None:
            self.ttls[key] = ex
        return True

    def incr(self, key):
        self.strings[key] = str(int(self.strings.get(key, b"0")) + 1).encode()

    def incrby(self, key, amount):
        self.strings[key] = str(int(self.strings.get(key, b"0")) + amount).encode()

    def get(self, key):
        return self.strings.get(key)

    def ttl(self, key):
        if key not in self.strings:
            return -2
        return self.ttls.get(key, -1)

    def keys(self, pattern):
        return [k.encode() for k in self.strings if fnmatch.fnmatch(k, pattern)]


@pytest.fixture
def fake(monkeypatch):
    r = _Redis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: r)
    return r


def _wall_key(name):
    return f"{TASK_LIFECYCLE_PREFIX}:{name}:wall_ms"


# ---------------------------------------------------------------------------
# The counter: a duration for a task that never calls `_tracked_run`
# ---------------------------------------------------------------------------

class TestTheCounterIsIndependentOfTrackedRun:
    def test_a_task_that_never_calls_tracked_run_still_gets_a_duration(self, fake):
        # `collapse_snapshots` is one of the 32 and is the biggest occupant of
        # the queue. Nothing in this call path touches `_tracked_run` or a
        # label — that independence is the whole ship.
        redis_state.record_task_wall_ms("app.tasks.collapse_snapshots", 1500.0)
        assert fake.strings[_wall_key("app.tasks.collapse_snapshots")] == b"1500"

    def test_it_is_keyed_by_the_celery_name_never_by_a_short_label(self, fake):
        redis_state.record_task_wall_ms("app.tasks.refresh_registered_tournament_prices", 10)
        # The label for that task is `tournament_price_refresh` — only 53 of 148
        # labels equal the task's short name, which is why the label join could
        # never reach the 32. Nothing may be written under the label namespace.
        assert all("tournament_price_refresh" not in k for k in fake.strings)

    def test_durations_accumulate_into_a_sum_not_a_last_value(self, fake):
        for ms in (100, 250, 4):
            redis_state.record_task_wall_ms("app.tasks.t", ms)
        # A SUM is the point: worker-seconds consumed is a total, and every
        # previous attempt at it multiplied a rate by an average drawn from a
        # different window.
        assert fake.strings[_wall_key("app.tasks.t")] == b"354"

    def test_the_window_is_stamped_once_and_never_refreshed(self, fake):
        redis_state.record_task_wall_ms("app.tasks.t", 100)
        fake.ttls[_wall_key("app.tasks.t")] = 40_000  # time passes
        redis_state.record_task_wall_ms("app.tasks.t", 100)
        # Sliding the window on every write is the lifetime-counter bug: the sum
        # would become a total of unknown age and the rate derived from it
        # meaningless. INCRBY must not touch the expiry.
        assert fake.ttls[_wall_key("app.tasks.t")] == 40_000

    @pytest.mark.parametrize("bad", [-1.0, None, "slow"])
    def test_an_impossible_reading_is_refused_not_summed(self, fake, bad):
        # A monotonic clock cannot go backwards, so a negative is a bad reading
        # and not a fast run. The sum has no other sanity check available to it,
        # so a corrupt addend is unrecoverable once banked.
        redis_state.record_task_wall_ms("app.tasks.t", bad)
        assert _wall_key("app.tasks.t") not in fake.strings

    def test_an_empty_task_name_writes_nothing(self, fake):
        redis_state.record_task_wall_ms("", 100)
        redis_state.record_task_wall_ms(None, 100)
        assert fake.strings == {}


class TestTheReader:
    def test_it_returns_the_sum_with_its_own_window(self, fake):
        redis_state.record_task_wall_ms("app.tasks.a", 7000)
        rows = redis_state.get_task_wall_ms()
        assert rows["app.tasks.a"]["wall_ms"] == 7000
        # Window derived from THIS key's TTL. Borrowing the `attempts` sibling's
        # window is LAT-P024's measured error, in both directions: the two keys
        # are created and expire independently.
        assert rows["app.tasks.a"]["window_s"] == 0

    def test_the_window_ages_with_the_keys_own_ttl(self, fake):
        redis_state.record_task_wall_ms("app.tasks.a", 7000)
        fake.ttls[_wall_key("app.tasks.a")] = redis_state.WINDOW_COUNTER_TTL - 3600
        assert redis_state.get_task_wall_ms()["app.tasks.a"]["window_s"] == 3600

    def test_it_does_not_return_the_lifecycle_siblings_as_tasks(self, fake):
        redis_state.record_task_attempt("app.tasks.a")
        redis_state.record_task_terminal("app.tasks.a")
        redis_state.record_task_wall_ms("app.tasks.a", 500)
        rows = redis_state.get_task_wall_ms()
        # All three live under one prefix. A reader that split on the last colon
        # without checking the suffix would report `app.tasks.a:attempts` as a
        # task named after a counter.
        assert list(rows) == ["app.tasks.a"]

    def test_the_hard_kill_census_ignores_the_new_key(self, fake):
        redis_state.record_task_attempt("app.tasks.a")
        redis_state.record_task_terminal("app.tasks.a")
        redis_state.record_task_wall_ms("app.tasks.a", 500)
        row = redis_state.get_hard_kill_census()["app.tasks.a"]
        # The census shares the prefix and must not start counting milliseconds
        # as attempts. `hard_kills` is the residual that BOUNDS the wall-time
        # undercount, so corrupting it would break the disclosure too.
        assert row["attempts"] == 1 and row["terminals"] == 1 and row["hard_kills"] == 0


# ---------------------------------------------------------------------------
# The bug the first implementation actually had
# ---------------------------------------------------------------------------

class TestTheBeatScheduleIsKeyedByEntryName:
    def test_a_tasks_queue_is_found_though_the_entry_key_is_arbitrary(self):
        # THE BUG. The entry key here is "some-entry-name"; the task is
        # `app.tasks.grinder`. A lookup by task name finds nothing and falls
        # through to the default queue — which is `background`, the queue being
        # sized. The wrong answer and the plausible answer are the same string,
        # which is why this needs a non-default expectation to be a test at all.
        schedule = {"some-entry-name": {
            "task": "app.tasks.grinder", "schedule": 60.0,
            "options": {"queue": "heavy"},
        }}
        assert beat_queues(schedule) == {"app.tasks.grinder": ["heavy"]}

    def test_beat_options_override_task_routes(self):
        # Celery's precedence, and it is the reverse of how the routing block
        # reads. Getting it backwards credits the multi-minute grinders that
        # were deliberately pinned to `heavy` back to `background`.
        schedule = {"e": {"task": "app.tasks.t", "schedule": 60.0,
                          "options": {"queue": "heavy"}}}
        routes = {"app.tasks.t": {"queue": "background"}}
        assert beat_queues(schedule, routes) == {"app.tasks.t": ["heavy"]}

    def test_task_routes_apply_when_the_entry_names_no_queue(self):
        schedule = {"e": {"task": "app.tasks.t", "schedule": 60.0}}
        routes = {"app.tasks.t": {"queue": "realtime"}}
        assert beat_queues(schedule, routes) == {"app.tasks.t": ["realtime"]}

    def test_the_default_queue_is_the_last_resort_not_the_first_guess(self):
        schedule = {"e": {"task": "app.tasks.t", "schedule": 60.0}}
        assert beat_queues(schedule, {}, "background") == {"app.tasks.t": ["background"]}


class TestOneTaskCanHaveSeveralEntries:
    SPLIT = {
        "a": {"task": "app.tasks.collapse_snapshots", "schedule": 60.0,
              "options": {"queue": "background"}},
        "b": {"task": "app.tasks.collapse_snapshots", "schedule": 120.0,
              "options": {"queue": "heavy"}},
        "c": {"task": "app.tasks.collapse_snapshots", "schedule": 180.0,
              "options": {"queue": "background"}},
    }

    def test_disagreeing_entries_are_reported_as_a_list_not_collapsed(self):
        # Three entries, two distinct queues, de-duplicated but not reduced to
        # one. Picking either would be inventing an attribution.
        assert beat_queues(self.SPLIT) == {
            "app.tasks.collapse_snapshots": ["background", "heavy"]
        }

    def test_a_split_task_is_priced_into_NEITHER_queue_and_is_named(self):
        wall = {"app.tasks.collapse_snapshots": {"wall_ms": 3_600_000, "window_s": 3600}}
        out = queue_demand(beat_queues(self.SPLIT), wall, QUEUE_SLOTS)
        # 1,000 worker-seconds/hour of real demand that cannot be attributed —
        # `wall_ms` is per task, not per entry. It is excluded from both sums
        # and NAMED on both queues, because unattributed demand that vanishes
        # silently is the failure this whole ship is about.
        assert out["background"]["worker_seconds_per_hour"] == 0.0
        assert out["heavy"]["worker_seconds_per_hour"] == 0.0
        for q in ("background", "heavy"):
            assert out[q]["tasks_split_across_queues"] == [
                "app.tasks.collapse_snapshots"
            ]
            # And not double-counted as merely unpriced, which would read as
            # "no data" rather than "data we refuse to attribute".
            assert out[q]["tasks_unpriced"] == 0


# ---------------------------------------------------------------------------
# The total, and what it admits it cannot see
# ---------------------------------------------------------------------------

class TestTheQueueTotal:
    def test_demand_is_summed_against_the_queues_real_capacity(self):
        schedule = {
            "a": {"task": "app.tasks.x", "schedule": 60.0},
            "b": {"task": "app.tasks.y", "schedule": 60.0},
        }
        wall = {
            "app.tasks.x": {"wall_ms": 1_800_000, "window_s": 3600},  # 1800 wsec/hr
            "app.tasks.y": {"wall_ms": 3_600_000, "window_s": 3600},  # 3600 wsec/hr
        }
        out = queue_demand(beat_queues(schedule), wall, QUEUE_SLOTS)["background"]
        assert out["worker_seconds_per_hour"] == 5400.0
        # 2 slots x 3600s. Utilisation 0.75 — and the point of the field is that
        # crossing 1.0 is PROOF of oversubscription, which no ranking of the
        # queue's occupants can ever establish.
        assert out["capacity_worker_seconds_per_hour"] == 7200
        assert out["utilisation"] == 0.75

    def test_a_rate_is_taken_against_each_tasks_own_window_never_a_nominal_day(self):
        # Two tasks, identical sums, windows differing 24x. Dividing both by a
        # nominal 24h would report them as equal demand; LAT-P024 measured this
        # exact error at 6x on a live counter.
        schedule = {
            "a": {"task": "app.tasks.x", "schedule": 60.0},
            "b": {"task": "app.tasks.y", "schedule": 60.0},
        }
        wall = {
            "app.tasks.x": {"wall_ms": 3_600_000, "window_s": 3600},
            "app.tasks.y": {"wall_ms": 3_600_000, "window_s": 86400},
        }
        out = queue_demand(beat_queues(schedule), wall, QUEUE_SLOTS)["background"]
        assert out["worker_seconds_per_hour"] == pytest.approx(3600 + 150, abs=0.5)


class TestTheTotalDisclosesWhatItCouldNotPrice:
    def test_a_task_with_no_wall_time_is_counted_and_named_never_dropped(self):
        schedule = {
            "a": {"task": "app.tasks.priced", "schedule": 60.0},
            "b": {"task": "app.tasks.silent", "schedule": 60.0},
        }
        wall = {"app.tasks.priced": {"wall_ms": 3_600_000, "window_s": 3600}}
        out = queue_demand(beat_queues(schedule), wall, QUEUE_SLOTS)["background"]
        # Unknown demand, not zero demand. Dropping it from the denominator is
        # the mistake that made a 91%-occupied queue model as having headroom.
        assert out["tasks_priced"] == 1
        assert out["tasks_unpriced"] == 1
        assert out["unpriced_tasks"] == ["app.tasks.silent"]

    def test_an_unmeasurable_window_withholds_the_rate_rather_than_zeroing_it(self):
        # `window_s` is None when the key's TTL cannot be read. A zero-age
        # window reads as an infinitely fast rate; a zero RATE reads as no
        # demand. Both are wrong and the second is the one that gets acted on.
        schedule = {"a": {"task": "app.tasks.x", "schedule": 60.0}}
        wall = {"app.tasks.x": {"wall_ms": 5000, "window_s": None}}
        out = queue_demand(beat_queues(schedule), wall, QUEUE_SLOTS)["background"]
        assert out["worker_seconds_per_hour"] == 0.0
        assert out["tasks_unpriced"] == 1 and out["unpriced_tasks"] == ["app.tasks.x"]

    def test_utilisation_is_withheld_when_the_slot_count_is_unknown(self):
        schedule = {"a": {"task": "app.tasks.x", "schedule": 60.0,
                          "options": {"queue": "a-queue-nobody-declared"}}}
        wall = {"app.tasks.x": {"wall_ms": 3_600_000, "window_s": 3600}}
        out = queue_demand(beat_queues(schedule), wall, QUEUE_SLOTS)
        row = out["a-queue-nobody-declared"]
        # The demand is still real and still reported; only the ratio is
        # withheld. Utilisation is the one number here that gets acted on
        # directly, so computing it against a guessed denominator is the worst
        # available failure.
        assert row["worker_seconds_per_hour"] == 3600.0
        assert row["slots"] is None and row["utilisation"] is None


# ---------------------------------------------------------------------------
# The fields on the surface
# ---------------------------------------------------------------------------

class TestTheFieldsRideEveryEntry:
    def test_the_trio_is_present_even_when_there_is_no_wall_time(self):
        # A key that appears only when it is interesting makes its absence
        # unreadable — the rule the `matched_*` pair is already written under.
        assert _wall_fields(None) == {
            "wall_ms_24h": None, "wall_window_s": None,
            "worker_seconds_per_hour": None,
        }

    @pytest.mark.parametrize("window_s", [None, 0, -1])
    def test_a_present_row_with_an_unmeasurable_window_withholds_the_RATE(
        self, window_s
    ):
        """The sum is real; the rate is not computable. Say so, do not say 0.

        A separate test from the absent-row case above and NOT a duplicate of
        it: that one returns early and never reaches this branch, so a mutant
        that defaults ``worker_seconds_per_hour`` to ``0.0`` right here survived
        the whole file until this was added. The two states it conflates are
        opposites on the surface this feeds — "this task costs nothing" is a
        reason to leave a queue alone, and "we could not measure what this task
        costs" is a reason not to trust the total at all.
        """
        fields = _wall_fields({"wall_ms": 5000, "window_s": window_s})
        assert fields["wall_ms_24h"] == 5000
        assert fields["worker_seconds_per_hour"] is None

    def test_an_unmapped_entry_carries_its_worker_seconds(self):
        # THE SHIP, in one assertion. `app.tasks.invisible` has no metrics and
        # no label — it is one of the 32 — and the surface can now say what it
        # costs. Before this it could only say that it could not be graded.
        out = build_schedule_adherence(
            {"e": {"task": "app.tasks.invisible", "schedule": 60.0}}, [], {},
            wall_ms={"app.tasks.invisible": {"wall_ms": 1_800_000, "window_s": 3600}},
        )
        assert out["graded"] == 0
        row = out["unmapped"][0]
        assert row["task"] == "app.tasks.invisible"
        assert row["worker_seconds_per_hour"] == 1800.0
        assert row["queues"] == ["background"]

    def test_wall_time_never_moves_the_adherence_verdict(self):
        # A task can consume half a queue while adhering perfectly to its
        # cadence. Letting consumption touch the verdict would conflate "is it
        # running often enough" with "can this queue afford it" — two questions
        # whose answers point at opposite remedies.
        sched = {"e": {"task": "app.tasks.foo", "schedule": 60.0}}
        metrics = [{"task": "foo", "starts_24h": 60, "starts_window_s": 3600,
                    "successes_24h": 60, "recent_durations_ms": [10]}]
        label_map = {"app.tasks.foo": "foo"}
        without = build_schedule_adherence(sched, metrics, label_map)
        with_wall = build_schedule_adherence(
            sched, metrics, label_map,
            wall_ms={"app.tasks.foo": {"wall_ms": 86_400_000, "window_s": 3600}},
        )
        assert (without["all"]["app.tasks.foo"]["verdict"]
                == with_wall["all"]["app.tasks.foo"]["verdict"])

    def test_the_queue_total_covers_unmapped_entries_too(self):
        # Restricting the total to `graded` would rebuild the exact blind spot
        # it exists to remove: the 32 are unmapped BY DEFINITION.
        out = build_schedule_adherence(
            {"e": {"task": "app.tasks.invisible", "schedule": 60.0}}, [], {},
            wall_ms={"app.tasks.invisible": {"wall_ms": 3_600_000, "window_s": 3600}},
        )
        assert out["graded"] == 0
        assert out["queue_demand"]["background"]["worker_seconds_per_hour"] == 3600.0


# ---------------------------------------------------------------------------
# The signal wiring — the half most able to fail silently
# ---------------------------------------------------------------------------

class TestThePrerunPostrunPair:
    """Driven through celery's REAL signals, not by calling the handlers.

    The handlers are connected inside a bare ``try/except`` and swallow every
    exception by contract, because they run before and after every task in the
    system. That is the correct design and it is also why nothing about this
    pair fails loudly: a handler that is never connected, and a handler that is
    connected and raises on every call, both present as a counter that stays at
    zero. So these tests ``send()`` the actual signals and assert the Redis
    write, which is the only observation that can tell working from wired-up.
    """

    @pytest.fixture
    def signals(self):
        from celery.signals import task_postrun, task_prerun

        import app.tasks as tasks_module

        tasks_module._INFLIGHT_STARTS.clear()
        return task_prerun, task_postrun, tasks_module

    class _Task:
        def __init__(self, name, retries=0):
            self.name = name
            self.request = type("R", (), {"retries": retries, "is_eager": False})()

    def test_a_task_that_never_calls_tracked_run_is_measured_end_to_end(
        self, fake, signals
    ):
        prerun, postrun, _ = signals
        task = self._Task("app.tasks.collapse_snapshots")
        prerun.send(sender=task, task_id="id-1", task=task)
        postrun.send(sender=task, task_id="id-1", task=task)
        # THE SHIP. Nothing in this path is `_tracked_run` and nothing is a
        # label. `collapse_snapshots` is one of the 32 and the largest occupant
        # of the queue; before this it had no duration under any label at all.
        assert int(fake.strings[_wall_key("app.tasks.collapse_snapshots")]) >= 0
        assert _wall_key("app.tasks.collapse_snapshots") in fake.strings

    def test_a_terminal_with_no_recorded_start_writes_NOTHING(self, fake, signals):
        prerun, postrun, _ = signals
        task = self._Task("app.tasks.orphan")
        # No prerun: this child never saw the start (the signal was connected
        # mid-flight by a deploy, or the cap discarded the entry).
        postrun.send(sender=task, task_id="never-seen", task=task)
        # A 0 here would silently DEFLATE the total this counter exists to
        # compute, and deflating a capacity measurement is the direction that
        # gets a queue left alone. Absent must stay absent.
        assert _wall_key("app.tasks.orphan") not in fake.strings

    def test_the_start_is_taken_before_the_retry_filter(self, fake, signals):
        prerun, postrun, _ = signals
        task = self._Task("app.tasks.retrier", retries=3)
        prerun.send(sender=task, task_id="id-r", task=task)
        postrun.send(sender=task, task_id="id-r", task=task)
        # A retry is NOT a beat fire — `deliveries` filters it, correctly, and
        # grades a schedule. It IS a slot occupied for its full duration, so
        # this counter must see it. The two counters answer different questions
        # and must not share a predicate; sharing one here would understate the
        # demand a retrying task actually places on its queue.
        assert _wall_key("app.tasks.retrier") in fake.strings

    def test_the_inflight_map_does_not_grow_without_bound(self, fake, signals):
        prerun, _, tasks_module = signals
        task = self._Task("app.tasks.killed")
        cap = tasks_module._INFLIGHT_STARTS_CAP
        # Every one of these is SIGKILLed before `task_postrun`, so no entry is
        # ever popped. That population is real (it is `attempts - terminals`),
        # and this map lives in a worker child with a 200MB budget.
        for i in range(cap * 3):
            prerun.send(sender=task, task_id=f"id-{i}", task=task)
        assert len(tasks_module._INFLIGHT_STARTS) <= cap

    def test_the_entries_dropped_under_pressure_are_the_OLDEST(self, fake, signals):
        prerun, postrun, tasks_module = signals
        task = self._Task("app.tasks.t")
        cap = tasks_module._INFLIGHT_STARTS_CAP
        for i in range(cap + 1 + cap // 4):
            prerun.send(sender=task, task_id=f"id-{i}", task=task)
        # Oldest-first, because the entries least likely to still have a
        # postrun coming are the ones that have been waiting longest. Evicting
        # the newest would discard the executions that are actually in flight.
        assert "id-0" not in tasks_module._INFLIGHT_STARTS
        assert f"id-{cap + cap // 4}" in tasks_module._INFLIGHT_STARTS

    def test_the_pair_still_records_the_terminal_it_always_recorded(
        self, fake, signals
    ):
        prerun, postrun, _ = signals
        task = self._Task("app.tasks.t")
        prerun.send(sender=task, task_id="id-x", task=task)
        postrun.send(sender=task, task_id="id-x", task=task)
        # The wall-time write was added INTO the terminal handler. The hard-kill
        # residual (`attempts - terminals`) is what BOUNDS this counter's
        # undercount, so breaking it would remove the disclosure along with the
        # measurement.
        census = redis_state.get_hard_kill_census()["app.tasks.t"]
        assert census["attempts"] == 1 and census["terminals"] == 1


# ---------------------------------------------------------------------------
# The capacity denominator
# ---------------------------------------------------------------------------

class TestTheSlotCountsMatchTheProcfile:
    def test_every_queue_mirrors_its_worker_concurrency(self):
        """The denominator of every capacity claim, pinned to the dyno formation.

        Widened from the background-only guard that already existed. A
        concurrency change on ANY queue is either a dyno purchase or a
        correctness change to every utilisation figure on the adherence
        surface, and neither may land silently.
        """
        import pathlib
        import re

        procfile = pathlib.Path(__file__).resolve().parents[1] / "Procfile"
        assert procfile.is_file(), f"Procfile not found at {procfile}"
        text = procfile.read_text()

        for queue, mirrored in QUEUE_SLOTS.items():
            line = next(
                (ln for ln in text.splitlines()
                 if ln.startswith(f"worker-{queue}:")),
                None,
            )
            assert line, f"no worker-{queue} entry in the Procfile"
            found = re.search(r"--concurrency=(\d+)", line)
            assert found, f"worker-{queue} has no --concurrency: {line}"
            assert int(found.group(1)) == mirrored, (
                f"worker-{queue} runs --concurrency={found.group(1)} but "
                f"QUEUE_SLOTS mirrors {mirrored}. Every `utilisation` on the "
                f"schedule-adherence surface is computed against this number."
            )

    def test_the_typeahead_budget_reads_the_same_number(self):
        # Derived, not transcribed a second time. Two modules price capacity
        # against this constant and a second copy is a second thing to forget.
        from app.utils.typeahead_beat_budget import BACKGROUND_WORKER_CONCURRENCY

        assert BACKGROUND_WORKER_CONCURRENCY is QUEUE_SLOTS["background"]
