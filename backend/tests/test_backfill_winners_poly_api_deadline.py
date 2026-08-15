"""`_backfill_polymarket_winners_from_api` must honour its CALLER's wall (queue 357).

The failure
-----------
`backfill_winners` recorded five consecutive `SoftTimeLimitExceeded`, health
critical, `recent_durations_ms` clustered hard at ~840,000 — the soft limit
exactly. The phase timer named the spot: the last boundary written to Redis was
`_start_phase("polymarket_api")` at cumulative **426.1s**, and the matching
`_end_phase` never ran. The task spent its final **414s inside one call**.

The arithmetic is exact and it is not a budget that was too generous:

    _MAX_RUNTIME = 420          # measured from this function's OWN _t0
    entered at t = 426.1s
    426.1 + 420  = 846.1  >  840  (soft_time_limit)

So the callee could obey its self-budget perfectly and still kill the task. The
constant carries its own explanation in a comment — *"resolve_winners has 9 min
soft limit"* — and that is a true fact about ONE of its two callers. Under the
other one it is simply the wrong zero. **A budget measured from the wrong zero
is not a budget, it is a duration.**

The caller's pre-phase guard could not save it either: it tests ENTRY (413.9s
remaining > `_BUDGET_MARGIN_S` of 300, so it passes) and then has no further say
for seven minutes. That is why #991 raising the margin 240 → 300 bought time
instead of fixing this — the guard was never the thing that could not see the
overrun.

Same mechanism class as #1199 in its pre-fix form, whose own docstring records
it: one indivisible inner op, a guard checked at a granularity that cannot
interrupt it, whole run lost. Different substrate — #1199's inner op was a
single SQL statement, so `statement_timeout` plus chunking fixed it. This one is
a loop of serial HTTP calls, which no statement timeout can touch. It needs the
deadline threaded in.
"""

import inspect
import time
from importlib import import_module

import pytest

#: NOT `from app.tasks import backfill_winners` — that name resolves to the
#: registered Celery task proxy, which shadows the module on the package and
#: exposes none of its private helpers.
bw = import_module("app.tasks.backfill_winners")


def _code(src: str) -> str:
    """Source with comment-only lines dropped.

    The tests below grep for phase markers, and this file's own explanatory
    comments quote those markers verbatim. Without this, a comment describing a
    deleted call reads to the grep exactly like the call still being there —
    the same confusion between a description and the thing described that let
    `_end_phase("fix_categories")` sit unpaired for so long.
    """
    return "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )


class TestTheDeadlineIsThreadedIn:
    """Signature and call sites — the half a behaviour test cannot see."""

    def test_the_function_accepts_a_caller_deadline(self):
        params = inspect.signature(
            bw._backfill_polymarket_winners_from_api
        ).parameters
        assert "deadline" in params, (
            "without a caller deadline this function can only measure from its "
            "own start, which is the defect: 426.1 + 420 > 840."
        )
        assert params["deadline"].default is None, (
            "a standalone call must still work on its own _MAX_RUNTIME"
        )

    def test_both_call_sites_pass_a_deadline(self):
        """Threading the parameter and not passing it is the silent version.

        Source-inspected deliberately: both call sites sit deep inside a
        multi-thousand-line pipeline that cannot be driven in a unit test, and
        an un-passed deadline would leave every behavioural test below green
        while production kept dying.
        """
        src = _code(inspect.getsource(bw))
        pieces = src.split("_backfill_polymarket_winners_from_api(")
        # [0] is everything before the def; [1] is the def's own signature.
        call_sites = pieces[2:]
        assert len(call_sites) == 2, (
            f"expected 2 call sites, found {len(call_sites)}"
        )
        for i, tail in enumerate(call_sites):
            args = tail.split(")")[0]
            assert "deadline=" in args, (
                f"call site {i} passes no deadline: {args!r}. Threading the "
                "parameter and not passing it leaves every behavioural test "
                "green while production keeps dying at the wall."
            )

    def test_the_self_budget_is_still_the_standalone_default(self):
        """Scope control. The fix takes the EARLIER of the two bounds; it does
        not delete the self-budget, which is correct for a standalone run."""
        src = inspect.getsource(bw._backfill_polymarket_winners_from_api)
        assert "_MAX_RUNTIME = 420" in src
        assert "_effective_stop_at(_t0, _MAX_RUNTIME, deadline)" in src


class TestTheBoundArithmetic:
    """The defect itself, in isolation: which zero the budget measures from.

    `_effective_stop_at` exists as a module-level function precisely so this can
    be asserted without Redis, a DB session and the Gamma client — the three
    things that made the original defect only reachable in production.
    """

    def test_a_standalone_call_keeps_its_own_budget(self):
        """No caller deadline — the self-relative budget is the whole answer."""
        assert bw._effective_stop_at(1000.0, 420.0, None) == 1420.0

    def test_the_production_failure_arithmetic(self):
        """The exact numbers from the five failing runs.

        Entered at cumulative 426.1s of an 840s task, with the caller's
        effective budget 840 - 300 = 540s. The self-budget alone would have
        permitted 426.1 + 420 = 846.1s — past the wall, which is the failure.
        """
        pipeline_start = 0.0
        entered_at = 426.1
        caller_deadline = pipeline_start + 840 - 300  # 540.0

        self_only = bw._effective_stop_at(entered_at, 420.0, None)
        assert self_only == pytest.approx(846.1), (
            "the shipped behaviour: a budget measured from the wrong zero"
        )
        assert self_only > 840, "and it overruns the soft limit — the bug"

        combined = bw._effective_stop_at(entered_at, 420.0, caller_deadline)
        assert combined == 540.0
        assert combined < 840, "the fix stops the callee ahead of the wall"

    def test_the_self_budget_still_wins_when_it_is_the_earlier_bound(self):
        """A generous caller must not extend the callee past its own budget.

        Otherwise `resolve_winners` — whose 540s soft limit the 420s constant
        was sized against — would inherit a longer leash than it can afford.
        """
        assert bw._effective_stop_at(0.0, 420.0, 10_000.0) == 420.0

    def test_an_already_expired_deadline_stops_immediately(self):
        now = time.monotonic()
        assert bw._effective_stop_at(now, 420.0, now - 1) == now - 1


class TestTheInnerOpIsBounded:
    """The gotcha half: a boundary-only check cannot interrupt one batch."""

    def test_phase_b_checks_the_deadline_per_event_not_per_batch(self):
        """200 SERIAL round-trips is the longest uninterrupted op in the task.

        Checking only at the batch edge would let a single batch run for
        minutes past the wall — `project_budget_guard_inner_op` verbatim: bound
        the longest single uninterrupted op, not the loop boundaries.
        """
        # `_code()` here is load-bearing, and a mutation test is what proved it:
        # with the real guard deleted, the COMMENT explaining the guard still
        # contained `_out_of_time()` and the grep passed. A test satisfied by
        # prose about the thing is not a test of the thing.
        src = _code(inspect.getsource(bw._backfill_polymarket_winners_from_api))
        # Anchored on CODE, not on the `# --- Phase B ---` banner: `_code()`
        # strips comment lines, so a comment anchor would not survive its own
        # sanitiser. Same trap as the one above, one level up.
        inner = src.split("event_ids = list(by_event.keys())")[1]
        per_event = inner.split("for event_id in batch:")[1]
        guard = per_event.split("await service.get_event_by_id")[0]
        assert "_out_of_time()" in guard, (
            "the per-event loop must test the deadline BEFORE each fetch; a "
            "check only at the 200-event batch boundary is what a boundary "
            "guard around an unbounded inner op means."
        )

    def test_both_batch_loops_use_the_combined_stop_and_report_which_fired(self):
        src = inspect.getsource(bw._backfill_polymarket_winners_from_api)
        assert "_time.monotonic() - _t0 > _MAX_RUNTIME" not in src, (
            "a surviving self-relative check re-introduces the wrong zero"
        )
        for arm in ("phase_a", "phase_b", "phase_b_inner"):
            assert f'"{arm}"' in src, (
                f"the {arm} stop must name itself in stats['deadline_hit'] — a "
                "truncated run that reports nothing is indistinguishable from a "
                "run with nothing to do (gotcha #53)."
            )


class TestTheUntimedRegionIsNamed:
    """40% of the pipeline had no phase timer, so a death there was invisible."""

    def test_the_orphan_end_phase_is_gone(self):
        src = _code(inspect.getsource(bw))
        assert '_end_phase("fix_categories")' not in src, (
            "`_end_phase` is `if name in _phase_times:` — an unpaired end is a "
            "silent no-op that reads like a measured region."
        )

    def test_the_region_between_polymarket_api_and_link_props_is_timed(self):
        src = _code(inspect.getsource(bw))
        assert '_start_phase("prob_and_datagolf")' in src
        assert '_end_phase("prob_and_datagolf")' in src

    def test_every_start_phase_has_a_matching_end_phase(self):
        """The general form, so the next orphan fails here instead of shipping.

        This is the check whose absence let `fix_categories` sit unpaired long
        enough that nobody remembered it had never once appeared in a phase map.
        """
        import re

        src = _code(inspect.getsource(bw))
        starts = set(re.findall(r'_start_phase\("([a-z0-9_]+)"\)', src))
        ends = set(re.findall(r'_end_phase\("([a-z0-9_]+)"\)', src))
        assert starts == ends, (
            f"unpaired phase markers — started but never ended: "
            f"{sorted(starts - ends)}; ended but never started: "
            f"{sorted(ends - starts)}"
        )
