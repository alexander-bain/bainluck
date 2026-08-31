"""LAT-P039 (#1609, #1716): the beat's fire count must not be the task's opinion.

``record_task_started`` claimed to count "fires that BEGAN". It is called from
inside ``_tracked_run``, which is a helper the *task body* invokes — so it
counts fires whose body chose to call it, and a body chooses that only after
its own gate has run. Two whole classes of task were therefore uncountable, and
BOTH presented as a scheduling fault:

* A **self-gating** task records nothing when it declines. ``poll_all_odds``
  returns ``{"skipped": True}`` from ``should_poll_now()`` before reaching
  ``_tracked_run``, and its adaptive gate declined about half its fires —
  ``LIVE_POLL_INTERVAL`` was 32s against a 30s beat, so two consecutive fires
  could never both pass. The surface graded ``ratio 0.50`` and it was read for
  two months as the ingestion beat running at half speed.

  🔴 **THIS FILE USED TO CALL THAT DECLINE "BY DESIGN"; IT WAS A DEFECT
  (LAT-P159).** These tests are unaffected — none of them asserts the 32/30
  relationship, they drive synthetic counters — but the prose mattered: the
  gate was discarding half of every live delivery for a two-second reason, and
  three files describing it as intentional is why no lane went looking.
  ``LIVE_POLL_INTERVAL`` is now derived from ``ODDS_POLL_BEAT_SECONDS``.
  Behaviour under test here — that a self-gated decline is not a missed beat —
  is unchanged and still correct.

* A task that never calls ``_tracked_run`` **at all** never reaches
  ``record_task_label`` either, so it cannot be joined to the schedule. Thirty
  of 117 beat-scheduled tasks are in that state, and they are exactly 30 of the
  34 entries the surface reported as ``unmapped``.

Production evidence these tests encode, measured 2026-08-11 16:13 PT:

    realtime worker, 1,982s since release v3781
      app.tasks.poll_all_odds            66 executions  -> one per 30.0s
      app.tasks.sync_statpal_livescores  65 executions  -> one per 30.5s

    GET /api/admin/celery/schedule-adherence, same minute
      poll_all_odds            starts 1097 / expected 2185.8  ratio 0.50
      sync_statpal_livescores  starts 2177 / expected 2186.9  ratio 1.00

Same beat interval, same worker, same window, near-identical DELIVERY counts,
and a 2x difference in the graded ratio. The only difference between the two
tasks is that one self-gates. That is the control, and it is why this is a
measurement defect rather than a scheduling one.
"""

import ast
import inspect
from pathlib import Path

import pytest

from app.routes.admin_celery import build_schedule_adherence
from app.tasks import redis_state
from app.tasks.redis_state import TASK_DELIVERY_PREFIX, TASK_METRICS_PREFIX
from app.utils.schedule_adherence import adherence, find_lapping


class _Redis:
    """Enough Redis for the delivery counter's write and read paths."""

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
        # Real INCR creates a missing key with NO expiry and never refreshes an
        # existing one — the second half is what makes the TTL a window start.
        self.strings[key] = str(int(self.strings.get(key, b"0")) + 1).encode()

    def expire(self, key, ttl):
        # Modelled rather than stubbed. A no-op `expire` here let a mutation
        # that slides the window on every increment survive the whole suite —
        # and sliding the window IS the lifetime-counter bug LAT-P022 fixed
        # (`successes_24h` never rolled because an hourly task kept pushing the
        # TTL out). A test double that cannot express the bug cannot catch it.
        if key in self.strings:
            self.ttls[key] = ttl

    def get(self, key):
        return self.strings.get(key)

    def ttl(self, key):
        if key not in self.strings:
            return -2
        return self.ttls.get(key, -1)

    def keys(self, pattern):
        prefix = pattern.rstrip("*")
        return [k.encode() for k in self.strings if k.startswith(prefix)]


@pytest.fixture
def fake(monkeypatch):
    r = _Redis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: r)
    return r


# ---------------------------------------------------------------------------
# The counter itself
# ---------------------------------------------------------------------------

class TestRecordTaskDelivery:
    def test_counts_by_celery_name_not_by_label(self, fake):
        redis_state.record_task_delivery("app.tasks.poll_all_odds")
        key = f"{TASK_DELIVERY_PREFIX}:app.tasks.poll_all_odds"
        assert fake.strings[key] == b"1"
        # The label-keyed namespace must be untouched: keying deliveries by the
        # celery name is what lets a task with no label be graded at all.
        assert not any(k.startswith(TASK_METRICS_PREFIX) for k in fake.strings)

    def test_window_is_stamped_once_and_never_slides(self, fake):
        key = f"{TASK_DELIVERY_PREFIX}:app.tasks.x"
        redis_state.record_task_delivery("app.tasks.x")
        fake.ttls[key] = 40_000  # 46,400s of window has elapsed
        redis_state.record_task_delivery("app.tasks.x")
        # SET NX declined, so the elapsed window survived the second increment.
        # An EXPIRE here is what made successes_24h a lifetime total (LAT-P022).
        assert fake.strings[key] == b"2"
        assert fake.ttls[key] == 40_000

    def test_empty_name_writes_nothing(self, fake):
        redis_state.record_task_delivery("")
        redis_state.record_task_delivery(None)
        assert fake.strings == {}

    def test_never_raises_when_redis_is_down(self, monkeypatch):
        def boom():
            raise RuntimeError("redis is gone")

        monkeypatch.setattr(redis_state, "get_redis_client", boom)
        # It runs before every task in the system. It must never be the reason
        # one fails to start.
        redis_state.record_task_delivery("app.tasks.x")


class TestGetAllTaskDeliveries:
    def test_returns_fires_with_the_window_that_makes_them_a_rate(self, fake):
        redis_state.record_task_delivery("app.tasks.a")
        redis_state.record_task_delivery("app.tasks.a")
        fake.ttls[f"{TASK_DELIVERY_PREFIX}:app.tasks.a"] = 86_400 - 600
        got = redis_state.get_all_task_deliveries()
        assert got == {"app.tasks.a": {"fires": 2, "window_s": 600.0}}

    def test_unmeasurable_window_is_none_not_zero(self, fake):
        # A key with no expiry is an unbounded lifetime total. Zero age would
        # read as an infinitely fast rate — the reading LAT-P024 exists to stop.
        fake.strings[f"{TASK_DELIVERY_PREFIX}:app.tasks.b"] = b"9"
        assert redis_state.get_all_task_deliveries()["app.tasks.b"]["window_s"] is None

    def test_celery_names_containing_dots_survive_the_key_split(self, fake):
        redis_state.record_task_delivery("app.tasks.sync_statpal_livescores")
        assert "app.tasks.sync_statpal_livescores" in redis_state.get_all_task_deliveries()


# ---------------------------------------------------------------------------
# The grader — the production defect, reproduced
# ---------------------------------------------------------------------------

class TestSelfGatedIsNotBehind:
    """The poll_all_odds shape: delivered on time, half of it gated by design."""

    #: 1,097 starts against 2,186 expected in an 18.2h window — the real numbers.
    GATED = dict(starts=1097, starts_window_s=65_575.0, interval_s=30.0,
                 terminals=1150)

    def test_without_deliveries_the_old_reading_still_says_behind(self):
        # The defect, pinned. This is what production reported for two months,
        # and it must keep reporting it when there is no delivery count — the
        # fallback may not silently invent a healthy verdict out of nothing.
        got = adherence(**self.GATED)
        assert got["verdict"] == "behind"
        assert got["ratio"] == 0.5
        assert got["numerator"] == "starts"

    def test_with_deliveries_the_beat_reads_on_schedule(self):
        got = adherence(**self.GATED, deliveries=2186,
                        deliveries_window_s=65_575.0)
        assert got["verdict"] == "on_schedule"
        assert got["ratio"] == 1.0
        assert got["numerator"] == "deliveries"

    def test_the_skips_are_reported_rather_than_vanishing(self):
        got = adherence(**self.GATED, deliveries=2186,
                        deliveries_window_s=65_575.0)
        assert got["self_gated_fires"] == 2186 - 1097
        # Silence here is what let 1,089 intentional skips read as lateness.
        assert "self-gated" in got["reason"]

    def test_a_genuinely_dead_beat_is_still_caught(self):
        # The fix must not be a mute button. If the DELIVERIES collapse, the
        # verdict is behind no matter how healthy the started-work count looks.
        got = adherence(starts=5, starts_window_s=65_575.0, interval_s=30.0,
                        deliveries=5, deliveries_window_s=65_575.0)
        assert got["verdict"] == "behind"
        assert "deliveries" in got["reason"]

    def test_self_gated_count_never_goes_negative(self):
        # A body can record a start in one 24h window while the delivery that
        # produced it was counted in the previous one.
        got = adherence(starts=100, starts_window_s=3600.0, interval_s=60.0,
                        deliveries=90, deliveries_window_s=3600.0)
        assert got["self_gated_fires"] == 0

    def test_deliveries_without_a_window_falls_back_rather_than_guessing(self):
        # A count of unknown age is not a rate. Refusing is the LAT-P024 lesson.
        got = adherence(**self.GATED, deliveries=2186, deliveries_window_s=None)
        assert got["numerator"] == "starts"
        assert got["verdict"] == "behind"

    def test_overruns_still_outranks_a_healthy_delivery_rate(self):
        # poll_all_odds really does take 46s p95 against a 30s interval. The
        # fire-rate fix must not bury the finding that is genuinely true.
        got = adherence(**self.GATED, deliveries=2186,
                        deliveries_window_s=65_575.0,
                        durations_ms=[46_156] * 20)
        assert got["verdict"] == "overruns"


class TestTheControl:
    """sync_statpal_livescores: same beat, same window, no gate. Reads 1.00."""

    def test_an_ungated_task_reads_the_same_either_way(self):
        kw = dict(starts=2177, starts_window_s=65_606.0, interval_s=30.0)
        without = adherence(**kw)
        with_deliveries = adherence(**kw, deliveries=2186,
                                    deliveries_window_s=65_606.0)
        assert without["verdict"] == with_deliveries["verdict"] == "on_schedule"

    def test_boundary_noise_does_not_get_a_sentence(self):
        # The real control numbers: 2,186 deliveries against 2,177 starts is a
        # 0.4% gap from two counters born ~30s apart, not a gate. The number is
        # still carried; a health surface that narrates noise gets muted.
        got = adherence(starts=2177, starts_window_s=65_606.0, interval_s=30.0,
                        deliveries=2186, deliveries_window_s=65_606.0)
        assert got["self_gated_fires"] == 9
        assert got["reason"] == ""

    def test_mismatched_windows_are_not_differenced(self):
        # The delivery counter is born at its own deploy, so for its first day
        # it is far younger than the starts counter. Subtracting across those is
        # exactly the cross-window arithmetic this module exists to refuse, and
        # the answer is None (unknown), never 0 (nothing was gated).
        got = adherence(starts=1097, starts_window_s=65_575.0, interval_s=30.0,
                        deliveries=20, deliveries_window_s=600.0)
        assert got["self_gated_fires"] is None
        assert got["numerator"] == "deliveries"


# ---------------------------------------------------------------------------
# #1716 — the work-list stops hiding a task that never finishes
# ---------------------------------------------------------------------------

class TestNeverCompletes:
    #: precompute_interestingness, production 2026-08-10: 10 starts, 0 terminals,
    #: graded on_schedule with an empty reason, absent from the work-list.
    DEAD = dict(starts=10, starts_window_s=36_000.0, interval_s=3600.0,
                terminals=0)

    def test_zero_terminals_is_flagged(self):
        assert adherence(**self.DEAD)["never_completes"] is True

    def test_it_appears_in_the_work_list_despite_being_on_schedule(self):
        got = adherence(**self.DEAD)
        assert got["verdict"] == "on_schedule"  # the schedule question is fine
        assert [r["task"] for r in find_lapping({"dead": got})] == ["dead"]

    def test_it_sorts_above_every_schedule_verdict(self):
        graded = {
            "overruns": adherence(starts=59, starts_window_s=3600, interval_s=60,
                                  durations_ms=[59_000] * 5),
            "dead": adherence(**self.DEAD),
        }
        assert [r["task"] for r in find_lapping(graded)][0] == "dead"

    def test_a_completing_task_is_not_flagged(self):
        got = adherence(starts=10, starts_window_s=36_000.0, interval_s=3600.0,
                        terminals=9)
        assert got["never_completes"] is False
        assert find_lapping({"ok": got}) == []

    def test_unknown_terminals_are_not_read_as_zero(self):
        # gotcha #53: an absent observation is not an observed absence. A task
        # with no metrics row has UNKNOWN completions, and calling that "never
        # completes" would manufacture an alarm out of a missing join.
        got = adherence(starts=10, starts_window_s=36_000.0, interval_s=3600.0,
                        terminals=None)
        assert got["never_completes"] is False

    def test_too_few_fires_to_mean_anything_is_not_flagged(self):
        # One fire and no completion is the overwhelmingly likely shape for a
        # healthy task whose single run is still in flight.
        got = adherence(starts=1, starts_window_s=36_000.0, interval_s=3600.0,
                        terminals=0)
        assert got["never_completes"] is False


# ---------------------------------------------------------------------------
# The join — 30 tasks stop being invisible
# ---------------------------------------------------------------------------

class TestDeliveriesRescueTheUnjoinable:
    BEAT = {"e": {"task": "app.tasks.collapse_snapshots", "schedule": 3600.0}}

    def test_a_task_with_no_label_is_graded_from_its_deliveries(self):
        # collapse_snapshots never calls _tracked_run, so it has no label and no
        # metrics — one of the 30. Before this it could only ever be `unmapped`.
        got = build_schedule_adherence(
            self.BEAT, [], {},
            {"app.tasks.collapse_snapshots": {"fires": 12, "window_s": 43_200.0}},
        )
        assert got["unmapped"] == []
        assert got["graded"] == 1
        assert got["all"]["app.tasks.collapse_snapshots"]["verdict"] == "on_schedule"

    def test_it_is_not_slandered_as_never_completing(self):
        got = build_schedule_adherence(
            self.BEAT, [], {},
            {"app.tasks.collapse_snapshots": {"fires": 12, "window_s": 43_200.0}},
        )
        g = got["all"]["app.tasks.collapse_snapshots"]
        assert g["terminals"] is None
        assert g["never_completes"] is False

    def test_no_deliveries_and_no_label_is_still_honestly_unmapped(self):
        got = build_schedule_adherence(self.BEAT, [], {}, {})
        assert [u["task"] for u in got["unmapped"]] == ["app.tasks.collapse_snapshots"]
        assert got["graded"] == 0

    def test_deliveries_are_omitted_entirely_without_breaking_the_join(self):
        # The route's old three-argument call must keep working: an Integrator
        # rebase or a caller this lane did not find must not throw.
        got = build_schedule_adherence(self.BEAT, [], {})
        assert got["graded"] == 0


# ---------------------------------------------------------------------------
# Structural guards — the defect class, not just this instance
# ---------------------------------------------------------------------------

def _tasks_module_ast():
    path = Path(inspect.getfile(__import__("app.tasks", fromlist=["x"])))
    return ast.parse(path.read_text()), path


class TestTheCounterCannotDriftBackIntoTheTaskBody:
    def test_delivery_is_recorded_from_celery_task_prerun(self):
        # The whole fix is WHERE the count happens. A helper the body calls can
        # only see fires the body hands it; the signal sees every delivery of
        # every task before any body runs — and, unlike a decorator or a base
        # class, cannot be forgotten when someone adds task 118.
        tree, _ = _tasks_module_ast()
        src = ast.dump(tree)
        assert "task_prerun" in src, "the prerun signal wiring is gone"

        handlers = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and any("task_prerun" in ast.dump(d) for d in n.decorator_list)
        ]
        assert handlers, "no function is connected to task_prerun"
        assert any(
            isinstance(c, ast.Call) and getattr(c.func, "id", None) == "record_task_delivery"
            for h in handlers for c in ast.walk(h)
        ), "task_prerun no longer records the delivery"

    def test_delivery_is_not_recorded_inside_tracked_run(self):
        # Moving it back into _tracked_run would silently restore the defect:
        # every self-gated skip and every task that never calls the helper would
        # go uncounted again, and the surface would report both as lateness.
        tree, _ = _tasks_module_ast()
        tracked = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "_tracked_run")
        assert not any(
            isinstance(c, ast.Call) and getattr(c.func, "id", None) == "record_task_delivery"
            for c in ast.walk(tracked)
        )

    def test_the_self_gating_shape_that_caused_this_still_exists(self):
        # Not a defect to fix — an adaptive gate is correct behaviour, and the
        # instrument is what was wrong. Asserted so that if someone ever
        # "simplifies" the gate away, the reason this counter exists is not
        # quietly lost with it.
        tree, _ = _tasks_module_ast()
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "poll_all_odds")
        first_tracked = min(
            c.lineno for c in ast.walk(fn)
            if isinstance(c, ast.Call) and getattr(c.func, "id", None) == "_tracked_run"
        )
        early = [r for r in ast.walk(fn)
                 if isinstance(r, ast.Return) and r.lineno < first_tracked]
        assert early, "poll_all_odds no longer self-gates — re-read LAT-P039"


# ---------------------------------------------------------------------------
# LAT-P043 (codex C-RV-1, #1802) — an ATTEMPT is not a DELIVERY
#
# `task_prerun` fires before every execution attempt. LAT-P039 counted all of
# them, so a retrying beat task manufactured up to `max_retries + 1` deliveries
# out of one scheduled fire — inflating precisely the denominator that would
# otherwise have exposed the missed schedule. Three beat-scheduled tasks retry
# (`sync_sports`, `discover_events`, and the 30s `poll_all_odds`), and
# `poll_all_odds` is the task this whole surface was built to grade.
#
# The same receiver was also blind to `task_always_eager`: an in-process call
# with no broker and no publication counted as schedule evidence.
#
# Both are the original defect wearing a different hat — a fact about the TASK
# read as a fact about the SCHEDULER (gotcha #53).
# ---------------------------------------------------------------------------


class _FakeRequest:
    def __init__(self, retries=0, is_eager=False):
        self.retries = retries
        self.is_eager = is_eager


class _FakeTask:
    def __init__(self, name="app.tasks.poll_all_odds", request=None):
        self.name = name
        if request is not None:
            self.request = request


def _run_handler(monkeypatch, **request_kwargs):
    """Fire the real `task_prerun` receiver and return what it recorded."""
    import app.tasks as tasks_module
    import app.tasks.redis_state as redis_state

    recorded = []
    monkeypatch.setattr(
        redis_state, "record_task_delivery", lambda name: recorded.append(name)
    )
    sender = _FakeTask(request=_FakeRequest(**request_kwargs))
    tasks_module._record_delivery(sender=sender, task=sender)
    return recorded


class TestAnAttemptIsNotADelivery:
    def test_first_attempt_is_recorded(self, monkeypatch):
        assert _run_handler(monkeypatch) == ["app.tasks.poll_all_odds"]

    def test_retry_attempt_is_not_recorded(self, monkeypatch):
        # The measured shape: celery emits prerun twice for one retrying task,
        # same task id, `retries` 0 then 1. Only the first crossed the beat.
        assert _run_handler(monkeypatch, retries=1) == []

    def test_exhausted_retries_are_not_recorded_either(self, monkeypatch):
        assert _run_handler(monkeypatch, retries=3) == []

    def test_eager_execution_is_not_recorded(self, monkeypatch):
        # No broker, no publication — an eager run against a shared Redis must
        # not write schedule evidence.
        assert _run_handler(monkeypatch, is_eager=True) == []

    def test_an_unreadable_request_still_records(self, monkeypatch):
        # Fail toward counting. If celery ever changes the request shape, an
        # upper bound is a worse number than the truth but a far better one
        # than a silent zero, which would read as "the beat stopped".
        import app.tasks as tasks_module
        import app.tasks.redis_state as redis_state

        recorded = []
        monkeypatch.setattr(
            redis_state, "record_task_delivery", lambda name: recorded.append(name)
        )
        sender = _FakeTask()  # no `request` attribute at all
        tasks_module._record_delivery(sender=sender, task=sender)
        assert recorded == ["app.tasks.poll_all_odds"]

    def test_the_retrying_beat_tasks_this_protects_still_retry(self):
        # If these stop retrying the guard is not wrong, but the reason it was
        # written should not vanish silently with them.
        tree, _ = _tasks_module_ast()
        retrying = set()
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef):
                continue
            for c in ast.walk(fn):
                if isinstance(c, ast.Call) and getattr(c.func, "attr", None) == "retry":
                    retrying.add(fn.name)
        assert {"sync_sports", "discover_events", "poll_all_odds"} & retrying, (
            "no beat-scheduled task retries any more — re-read C-RV-1"
        )


class TestTheAttemptFilterCannotBeDroppedSilently:
    def test_the_receiver_consults_retries_and_eager(self):
        # Structural, because the behavioural tests above pass a fake request:
        # deleting the filter would be caught by them, but reading the WRONG
        # celery field would not be, and this pins the field names.
        tree, _ = _tasks_module_ast()
        handlers = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and any("task_prerun" in ast.dump(d) for d in n.decorator_list)
        ]
        assert handlers, "no function is connected to task_prerun"
        src = " ".join(ast.dump(h) for h in handlers)
        assert "retries" in src, "the prerun receiver no longer filters retries"
        assert "is_eager" in src, "the prerun receiver no longer filters eager runs"
