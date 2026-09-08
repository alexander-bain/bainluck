"""#3192: the post-loop commence_time repairs stop being starved, and say so.

**The bug.** `_LOOP_DEADLINE_S = 480.0` gated two different questions with one
constant: the ingest loop's `break`, and whether the post-loop fix-up block ran
at all. `_task_started` is assigned once and `time.monotonic()` never decreases,
so tripping the first gate closed the second DETERMINISTICALLY — every beat that
reached 480s dropped all five commence_time repairs. Measured 2026-09-06: 7 of
the last 50 beats (14%, ~1 poll in 7). Kalshi dates a market by its ~14-day
settlement backstop, so the repairs are what give golf, hockey and tennis rows
their real start date; on the 06:46Z beat, ingest added 38 tennis markets and
the fix that dates them did not run, so open tennis rows dated >10d out went UP
(425 -> 463) and a WTA match played 2026-09-06 stayed filed as 2026-09-20.

**The receipt half.** The task already set `stats["post_loop_skipped_deadline"]`
and nothing read it — it reached no artifact, so an operator saw
`loop_deadline_hit: true` and could not learn a repair phase had been dropped.

Three things here are guards against the ways this repair could be undone
quietly rather than against the original bug, because each is a mistake that
passes every behavioural test:

1. **The ring trap.** The issue's own suggested fix was to persist the flag with
   a "second update". `save_scan_report` ends in `lpush` — it appends. A second
   call puts two ring entries in for one beat, so the history would cover half
   the beats it claims and every per-beat rate read off it would silently halve.
   `test_a_plain_second_save_really_would_duplicate_the_ring` is the positive
   control proving that hazard is real, so the in-place test is not vacuous.
2. **The blinding trap.** Folding the five fix-ups into a table of callables and
   looping `await _fix_fn()` keeps every behavioural test green while making
   #3403's and #3544's wiring guards blind — they AST-scan this function for a
   call to each name, and after such a refactor only `_fix_fn` remains. This was
   written, caught by those four guards, and reverted; the guard below is so the
   next person is caught by an assertion that explains itself.
3. **The re-merge trap.** Pointing the post-loop `if` back at `_LOOP_DEADLINE_S`
   restores the original bug while leaving both constants defined.
"""

import ast
import inspect
import json

import pytest

from app.tasks import kalshi as kalshi_task
from app.tasks import redis_state
from app.utils import kalshi_scan_report as ksr
from app.utils.kalshi_scan_report import (
    KalshiScanReport,
    save_scan_report,
    update_scan_report_head,
)

FIXUPS = (
    ("golf_commence_fixed", "_fix_golf_commence_times"),
    ("golf_round_dates_fixed", "_fix_golf_round_leader_dates"),
    ("hockey_commence_fixed", "_fix_hockey_commence_times"),
    ("tennis_commence_fixed", "_fix_tennis_commence_times"),
    ("stand_in_event_starts_refined", "_refine_stand_in_event_starts"),
)


def _poller_body():
    tree = ast.parse(inspect.getsource(kalshi_task))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_poll_kalshi_markets"
        ):
            return node
    raise AssertionError("_poll_kalshi_markets not found")


def _calls_in(node):
    return {
        n.func.id
        for n in ast.walk(node)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }


def _post_loop_gate():
    """The `if` guarding the post-loop block, identified by its own body.

    Anchored on `_mark_phase("post_loop")` rather than on source position,
    because every position-based anchor here has a decoy: the helper
    `_no_post_loop_budget` contains a `time.monotonic()` comparison against the
    same constant and is defined FIRST.
    """
    for node in ast.walk(_poller_body()):
        if not isinstance(node, ast.If):
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "_mark_phase"
                and child.args
                and isinstance(child.args[0], ast.Constant)
                and child.args[0].value == "post_loop"
            ):
                return node
    raise AssertionError("the post-loop block's `if` was not found")


class _Redis:
    """Just enough Redis to exercise the ring, including `lindex`/`lset`."""

    def __init__(self):
        self.kv = {}
        self.lists = {}

    def setex(self, key, ttl, value):
        self.kv[key] = value

    def get(self, key):
        return self.kv.get(key)

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start:end + 1]

    def expire(self, key, ttl):
        pass

    def lindex(self, key, idx):
        items = self.lists.get(key, [])
        try:
            return items[idx]
        except IndexError:
            return None

    def lset(self, key, idx, value):
        self.lists[key][idx] = value


@pytest.fixture
def fake(monkeypatch):
    r = _Redis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: r)
    return r


def _report(started_at="2026-09-08T10:00:00+00:00", **kw):
    return KalshiScanReport(started_at=started_at, **kw)


def _ring(fake):
    return [json.loads(x) for x in fake.lists.get(ksr._RING_KEY, [])]


# --------------------------------------------------------------------------
# 1. The gate is its own budget now
# --------------------------------------------------------------------------
class TestTheRepairBudgetIsNotTheIngestBudget:
    def test_the_two_deadlines_are_separate_constants(self):
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        assert "_POST_LOOP_DEADLINE_S = 540.0" in src
        assert "_LOOP_DEADLINE_S = 480.0" in src

    def test_the_post_loop_block_is_gated_on_the_post_loop_deadline(self):
        """The re-merge trap: both constants can exist while the `if` that
        matters still reads the ingest one, which restores the bug exactly.

        Found by AST, not by a character window. The first written version
        sliced from `_POST_LOOP_FIXUP_KEYS` to the next `if time.monotonic()`
        and asserted on that line — which is the one inside
        `_no_post_loop_budget`, not the block's own gate. It passed with the
        real gate mutated back to `_LOOP_DEADLINE_S`: a guard for this exact
        regression that did not catch it.
        """
        gate = _post_loop_gate()
        names = {n.id for n in ast.walk(gate.test) if isinstance(n, ast.Name)}
        assert "_POST_LOOP_DEADLINE_S" in names, names
        assert "_LOOP_DEADLINE_S" not in names, (
            "the post-loop block is gated on the INGEST deadline again — "
            "tripping the loop deadline once more closes this block "
            "deterministically, which is the whole of #3192"
        )

    def test_the_repair_budget_is_larger_than_the_ingest_budget(self):
        """Otherwise this ship does nothing: the block would still be closed by
        the moment the loop stops."""
        assert kalshi_task and True
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        post = float(src.split("_POST_LOOP_DEADLINE_S = ")[1].split("\n")[0])
        loop = float(src.split("_LOOP_DEADLINE_S = ")[1].split("#")[0].strip())
        assert post > loop, (post, loop)

    def test_it_still_leaves_headroom_under_the_soft_time_limit(self):
        """540 must stay below `soft_time_limit=600` with room for the last
        repair to finish, or this trades a skipped fix-up for a SIGTERM."""
        import app.tasks as tasks_pkg

        task_src = inspect.getsource(tasks_pkg)
        decl = task_src[task_src.index('name="app.tasks.poll_kalshi_markets"'):]
        soft = int(decl.split("soft_time_limit=")[1].split(",")[0])
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        post = float(src.split("_POST_LOOP_DEADLINE_S = ")[1].split("\n")[0])
        assert post < soft, (post, soft)
        assert soft - post >= 30, f"only {soft - post}s for the last repair"

    def test_every_fixup_rechecks_the_budget_before_it_starts(self):
        """The interior check is the new safety. The OLD gate was consulted once
        before five sequential repairs and never again, so a beat entering at
        479s could start its fifth well past any bound with nothing checking."""
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        for key, _fn in FIXUPS:
            assert f'_no_post_loop_budget("{key}")' in src, key

    def test_the_budget_helper_records_the_skip_rather_than_only_refusing(self):
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        body = src[src.index("def _no_post_loop_budget"):]
        body = body[:body.index("\n\n")]
        assert "_post_loop_skipped.append" in body


# --------------------------------------------------------------------------
# 2. The blinding trap
# --------------------------------------------------------------------------
class TestTheFixupsAreStillCalledDirectlyByName:
    """A table of callables passes every behaviour test and blinds four
    existing wiring guards at once. Caught here with the reason attached."""

    def test_all_five_are_direct_calls_in_the_poller(self):
        called = _calls_in(_poller_body())
        for key, fn in FIXUPS:
            assert fn in called, (
                f"{fn} is no longer called directly by name in "
                f"_poll_kalshi_markets. If this became `await _fix_fn()` in a "
                f"loop, the behaviour is fine but #3403's and #3544's wiring "
                f"guards can no longer see the call at all — they AST-scan for "
                f"exactly this name. Keep the calls explicit."
            )

    def test_the_skip_list_holds_names_not_callables(self):
        """`_POST_LOOP_FIXUP_KEYS` must stay inert data; the moment it holds the
        functions, the direct calls above become redundant and get deleted."""
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        table = src[src.index("_POST_LOOP_FIXUP_KEYS = ("):]
        table = table[:table.index(")")]
        for _key, fn in FIXUPS:
            assert fn not in table, fn

    def test_the_five_keys_are_exactly_the_five_repairs(self):
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        table = src[src.index("_POST_LOOP_FIXUP_KEYS = ("):]
        table = table[:table.index(")")]
        for key, _fn in FIXUPS:
            assert f'"{key}"' in table, key


# --------------------------------------------------------------------------
# 3. The ring trap
# --------------------------------------------------------------------------
class TestTheReceiptUpdateDoesNotDuplicateTheRing:
    def test_a_plain_second_save_really_would_duplicate_the_ring(self, fake):
        """POSITIVE CONTROL. Without this, the in-place test below could pass
        because nothing writes the ring at all."""
        r = _report()
        save_scan_report(r)
        save_scan_report(r)
        assert len(_ring(fake)) == 2

    def test_one_beat_leaves_exactly_one_ring_entry(self, fake):
        r = _report()
        save_scan_report(r)
        r.post_loop_fixups_ran = {"tennis_commence_fixed": 38}
        assert update_scan_report_head(r) is True
        assert len(_ring(fake)) == 1

    def test_the_head_carries_the_post_loop_outcome_after_the_update(self, fake):
        r = _report()
        save_scan_report(r)
        assert _ring(fake)[0]["post_loop_fixups_ran"] == {}
        r.post_loop_fixups_ran = {"tennis_commence_fixed": 38}
        r.post_loop_fixups_skipped = ["stand_in_event_starts_refined"]
        update_scan_report_head(r)
        head = _ring(fake)[0]
        assert head["post_loop_fixups_ran"] == {"tennis_commence_fixed": 38}
        assert head["post_loop_fixups_skipped"] == ["stand_in_event_starts_refined"]

    def test_the_last_key_is_updated_too(self, fake):
        r = _report()
        save_scan_report(r)
        r.post_loop_fixups_ran = {"hockey_commence_fixed": 2}
        update_scan_report_head(r)
        last = json.loads(fake.kv[ksr._LAST_KEY])
        assert last["post_loop_fixups_ran"] == {"hockey_commence_fixed": 2}

    def test_it_refuses_a_head_that_belongs_to_another_beat(self, fake):
        """`LSET 0` is positional. If an overlapping beat pushed after our save,
        rewriting index 0 would clobber ITS entry — worse than missing fields."""
        mine = _report(started_at="2026-09-08T10:00:00+00:00")
        save_scan_report(mine)
        sibling = _report(started_at="2026-09-08T10:05:00+00:00")
        save_scan_report(sibling)

        mine.post_loop_fixups_ran = {"tennis_commence_fixed": 38}
        assert update_scan_report_head(mine) is False
        head = _ring(fake)[0]
        assert head["started_at"] == "2026-09-08T10:05:00+00:00"
        assert head["post_loop_fixups_ran"] == {}
        assert len(_ring(fake)) == 2

    def test_an_empty_ring_still_refreshes_the_last_key(self, fake):
        r = _report()
        r.post_loop_fixups_ran = {"golf_commence_fixed": 4}
        assert update_scan_report_head(r) is False
        assert json.loads(fake.kv[ksr._LAST_KEY])["post_loop_fixups_ran"] == {
            "golf_commence_fixed": 4
        }
        assert _ring(fake) == []

    def test_a_dead_redis_does_not_take_the_beat_down(self, monkeypatch):
        def _boom():
            raise RuntimeError("redis down")

        monkeypatch.setattr(redis_state, "get_redis_client", _boom)
        assert update_scan_report_head(_report()) is False


# --------------------------------------------------------------------------
# 4. Absent, empty and failed stay three different things (gotcha #53)
# --------------------------------------------------------------------------
class TestTheThreeOutcomesAreDistinguishable:
    def test_ran_and_fixed_nothing_is_not_never_ran(self):
        r = _report(post_loop_fixups_ran={"golf_commence_fixed": 0})
        d = r.to_dict()
        assert d["post_loop_fixups_ran"]["golf_commence_fixed"] == 0
        assert "tennis_commence_fixed" not in d["post_loop_fixups_ran"]

    def test_a_failed_fixup_is_not_recorded_as_a_zero(self):
        """"ran and there was nothing to repair" and "blew up and repaired
        nothing" are opposite readings that produce the same number."""
        r = _report(post_loop_fixups_failed=["tennis_commence_fixed"])
        d = r.to_dict()
        assert "tennis_commence_fixed" not in d["post_loop_fixups_ran"]
        assert d["post_loop_fixups_failed"] == ["tennis_commence_fixed"]

    def test_the_POLLER_records_a_failure_as_a_failure(self):
        """The three tests around this one build the dataclass by hand, so they
        prove the SHAPE can express three states and nothing about whether the
        beat writes them. Recording a crashed fix-up as `_post_loop_ran[k] = 0`
        survives all of them — it was mutated in and every one stayed green.

        Asserted over each handler's AST: an `except` around a repair may add to
        `_post_loop_failed` and may never touch `_post_loop_ran`, because a 0
        there reads as "ran, nothing to repair" — the opposite of what happened.
        """
        handlers = [
            h
            for node in ast.walk(_poller_body())
            if isinstance(node, ast.Try)
            for h in node.handlers
            if "_post_loop" in ast.dump(h)
        ]
        assert len(handlers) == len(FIXUPS), len(handlers)
        for h in handlers:
            dumped = ast.dump(h)
            assert "_post_loop_failed" in dumped
            assert "_post_loop_ran" not in dumped, (
                "a fix-up that raised is being recorded in `post_loop_fixups_ran` "
                "— a 0 there is indistinguishable from a repair that ran and "
                "found nothing to do"
            )

    def test_every_repair_has_a_named_failure_arm(self):
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        for key, _fn in FIXUPS:
            assert f'_post_loop_failed.append("{key}")' in src, key

    def test_skipped_for_budget_is_not_failed(self):
        r = _report(post_loop_fixups_skipped=["tennis_commence_fixed"])
        d = r.to_dict()
        assert d["post_loop_fixups_skipped"] == ["tennis_commence_fixed"]
        assert d["post_loop_fixups_failed"] == []

    def test_the_never_entered_case_names_every_casualty(self):
        """The pairing is the invariant: the flag alone cannot say WHICH."""
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        tail = src[src.index('stats["post_loop_skipped_deadline"] = True'):]
        assert "_post_loop_skipped = list(_POST_LOOP_FIXUP_KEYS)" in tail

    def test_the_flag_and_an_empty_ran_map_travel_together(self):
        r = _report(
            post_loop_skipped_deadline=True,
            post_loop_fixups_skipped=[k for k, _ in FIXUPS],
        )
        d = r.to_dict()
        assert d["post_loop_skipped_deadline"] is True
        assert d["post_loop_fixups_ran"] == {}
        assert len(d["post_loop_fixups_skipped"]) == 5

    def test_the_defaults_read_as_a_clean_beat(self):
        d = _report().to_dict()
        assert d["post_loop_skipped_deadline"] is False
        assert d["post_loop_fixups_skipped"] == []
        assert d["post_loop_fixups_failed"] == []


# --------------------------------------------------------------------------
# 5. The fields survive persistence
# --------------------------------------------------------------------------
class TestTheFieldsReachAReader:
    def test_the_report_declares_all_four_fields(self):
        d = _report().to_dict()
        for f in (
            "post_loop_skipped_deadline",
            "post_loop_fixups_ran",
            "post_loop_fixups_skipped",
            "post_loop_fixups_failed",
        ):
            assert f in d, f

    def test_the_serialized_form_is_json_round_trippable(self):
        r = _report(
            post_loop_fixups_ran={"tennis_commence_fixed": 38},
            post_loop_fixups_skipped=["stand_in_event_starts_refined"],
            post_loop_fixups_failed=["hockey_commence_fixed"],
        )
        back = json.loads(json.dumps(r.to_dict()))
        assert back["post_loop_fixups_ran"] == {"tennis_commence_fixed": 38}
        assert back["post_loop_fixups_skipped"] == ["stand_in_event_starts_refined"]
        assert back["post_loop_fixups_failed"] == ["hockey_commence_fixed"]

    def test_the_poller_actually_writes_them_onto_the_report(self):
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        for f in (
            "post_loop_skipped_deadline",
            "post_loop_fixups_ran",
            "post_loop_fixups_skipped",
            "post_loop_fixups_failed",
        ):
            assert f"_report.{f} = " in src, f

    def test_the_poller_updates_the_head_and_does_not_save_twice(self):
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        assert "update_scan_report_head(_report)" in src
        assert src.count("save_scan_report(_report)") == 1

    def test_the_report_is_bound_before_the_try_that_assigns_it(self):
        """Everything in the report block is best-effort and only warns, so an
        unbound `_report` would turn a warned instrument failure into a real
        UnboundLocalError inside the beat (gotcha #7)."""
        src = inspect.getsource(kalshi_task._poll_kalshi_markets)
        assert src.index("_report = None") < src.index("_report = KalshiScanReport(")
