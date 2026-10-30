"""#10090 class f — the Kalshi flush loop's per-transaction cost.

## the ship

At the busy hour, a live game's new Kalshi price reaches the page in about a
second, not 7-12 s.

## what these cases pin (no database; the real-PG cases are in
`tests/integration/test_kalshi_skip_locked_row_10090_pg.py`)

* `absorb_live_phases`, the planner step behind `KALSHI_WS_MERGE_LIVE_PHASES`:
  consecutive whole phases of ONE class join the head in order; another class
  stops it; a refused phase keeps its own turn; the row cap stops before the
  phase that would pass it; nothing joined leaves the plan untouched.
* The setting: only ``1`` turns it on.
* The CPU counter (`_FlushTimings.tail`): the longest flush's loop CPU and the
  minute's checkout over every flush, at the END of the Kalshi minute line with
  one argument per placeholder, and `timed_flush` reading `time.thread_time`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.tasks.kalshi_ws import (
    KALSHI_MERGE_LIVE_PHASES_ENV,
    LIVE_MERGE_MAX_ROWS,
    _FlushTimings,
    absorb_live_phases,
    kalshi_merge_live_phases_enabled,
)

SOURCE = Path(__file__).resolve().parents[1] / "app/tasks/kalshi_ws.py"


def _phase(*oids):
    return {oid: (0.5, None, None) for oid in oids}


def _key(classes):
    """A phase's class from its first outcome; None for a non-live phase."""
    return lambda phase: classes.get(next(iter(phase)))


def test_consecutive_phases_of_one_class_join_the_head_in_order():
    phases = [_phase(1), _phase(2, 3), _phase(4), _phase(9)]
    parts = absorb_live_phases(
        phases, 0, _key({1: "h", 2: "h", 4: "h", 9: None}), lambda _p: True,
    )
    assert parts == [_phase(1), _phase(2, 3), _phase(4)]
    assert phases == [_phase(1, 2, 3, 4), _phase(9)]
    assert list(phases[0]) == [1, 2, 3, 4]  # batch order kept


def test_another_class_stops_it_and_keeps_its_place():
    phases = [_phase(1), _phase(2), _phase(3), _phase(4)]
    parts = absorb_live_phases(
        phases, 0, _key({1: False, 2: False, 3: True, 4: True}), lambda _p: True,
    )
    assert parts == [_phase(1), _phase(2)]
    assert phases == [_phase(1, 2), _phase(3), _phase(4)]  # aux stays after


def test_a_refused_phase_keeps_its_own_turn_and_later_ones_still_join():
    phases = [_phase(1), _phase(2), _phase(3)]
    parts = absorb_live_phases(
        phases, 0, _key({1: "h", 2: "h", 3: "h"}), lambda p: 2 not in p,
    )
    assert parts == [_phase(1), _phase(3)]
    assert phases == [_phase(1, 3), _phase(2)]


def test_the_row_cap_stops_before_the_phase_that_would_pass_it():
    phases = [_phase(1, 2), _phase(3, 4), _phase(5, 6), _phase(7)]
    parts = absorb_live_phases(
        phases, 0, _key(dict.fromkeys(range(1, 8), "h")), lambda _p: True, max_rows=4,
    )
    assert parts == [_phase(1, 2), _phase(3, 4)]
    assert phases == [_phase(1, 2, 3, 4), _phase(5, 6), _phase(7)]
    assert LIVE_MERGE_MAX_ROWS == 200


def test_a_lone_or_unclassed_head_leaves_the_plan_untouched():
    phases = [_phase(1), _phase(2)]
    assert absorb_live_phases(phases, 0, _key({1: None, 2: None}), lambda _p: True) == []
    assert phases == [_phase(1), _phase(2)]
    assert absorb_live_phases(phases, 1, _key({2: "h"}), lambda _p: True) == []
    assert phases == [_phase(1), _phase(2)]
    refused = [_phase(1), _phase(2)]
    assert absorb_live_phases(refused, 0, _key({1: "h", 2: "h"}), lambda _p: False) == []
    assert refused == [_phase(1), _phase(2)]


def test_a_head_later_in_the_plan_absorbs_only_after_itself():
    phases = [_phase(1), _phase(2), _phase(3)]
    parts = absorb_live_phases(phases, 1, _key({1: "h", 2: "h", 3: "h"}), lambda _p: True)
    assert parts == [_phase(2), _phase(3)]
    assert phases == [_phase(1), _phase(2, 3)]


@pytest.mark.parametrize(
    ("raw", "on"),
    [(None, False), ("", False), ("0", False), ("true", False), ("1", True), (" 1 ", True)],
)
def test_only_one_turns_the_merge_on(monkeypatch, raw, on):
    if raw is None:
        monkeypatch.delenv(KALSHI_MERGE_LIVE_PHASES_ENV, raising=False)
    else:
        monkeypatch.setenv(KALSHI_MERGE_LIVE_PHASES_ENV, raw)
    assert kalshi_merge_live_phases_enabled() is on
    assert KALSHI_MERGE_LIVE_PHASES_ENV == "KALSHI_WS_MERGE_LIVE_PHASES"


def test_the_tail_names_the_longest_flushs_cpu_and_every_flushs_checkout():
    t = _FlushTimings()
    assert t.tail() == "cpu=- checkout_total=0.00s"
    for seconds, cpu, checkout in ((1.0, 0.9, 0.25), (3.0, 2.75, 0.5), (2.0, 0.1, 0.125)):
        t.waiting_lock["checkout"] = checkout
        t.flush_cpu = cpu  # as `timed_flush` sets it, just before `flushed`
        t.flushed(seconds)
        assert t.flush_cpu is None  # taken by that flush, never the next
    assert t.tail() == "cpu=2.75s checkout_total=0.88s"
    t.reset()
    assert t.tail() == "cpu=- checkout_total=0.00s"
    t.flushed(0.5)  # a flush with no counter read names none
    assert t.tail() == "cpu=- checkout_total=0.00s" and t.flushes == 1


def _function(name):
    tree = ast.parse(SOURCE.read_text())
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def test_the_minute_line_carries_the_counters_at_its_end_one_argument_each():
    call = next(
        node for node in ast.walk(_function("stats_loop"))
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "info"
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value.startswith("Kalshi WS: %d updates")
    )
    fmt = call.args[0].value
    assert fmt.endswith("skipped_locked=%d %s merged=%d merge_split=%d")
    assert fmt.count("%d") + fmt.count("%s") == len(call.args) - 1
    tail = [ast.unparse(arg) for arg in call.args[-3:]]
    assert tail == [
        "flush_timings.tail()",
        "stats.get('live_phases_merged', 0)",
        "stats.get('live_merge_split', 0)",
    ]


def test_timed_flush_reads_the_loop_threads_cpu_around_the_flush():
    text = ast.unparse(_function("timed_flush"))
    assert "cpu_started = time.thread_time()" in text
    assert text.index("flush_timings.flush_cpu = time.thread_time() - cpu_started") < (
        text.index("flush_timings.flushed(time.monotonic() - started)")
    )
