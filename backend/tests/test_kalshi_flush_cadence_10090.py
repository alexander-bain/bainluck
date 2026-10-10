"""#10090 — Kalshi may flush and stamp sooner, opt-in, the #10662 PM shape.

THE SHIP. A held live game's Kalshi number can move about once a second. Unset,
the shared 2 s timer and the refresher's 2 s per-event floor cap it at one stamp
per 2 s. `KALSHI_WS_PRICE_FLUSH_SECONDS` sets the timer and the floor; the
failed-write retry keeps `PRICE_FLUSH_SECONDS` and the non-live budget keeps
`FLUSH_BUDGET_SECONDS`.
Removing the variable restores the unset run exactly.
"""

import asyncio

import pytest

import app.tasks.kalshi_ws as kalshi_task
import app.tasks.live_blend_refresh as lbr
from tests.test_ws_admission_mapped_legs_9462 import (
    _arm,
    _install_quiet_socket,
    _install_session,
    _timing,
)

ENV = "KALSHI_WS_PRICE_FLUSH_SECONDS"


async def _run_recording(monkeypatch, arm):
    """Run the REAL consumer to its recycle; return (cadence calls, refreshers,
    per-call (wake is an Event, work_count() at entry, wake_coalesce_s))."""
    module, consumer, slate = _arm(monkeypatch, arm)
    _install_quiet_socket(monkeypatch)
    _install_session(monkeypatch, slate, lambda _: [])
    _timing(monkeypatch, module, refresh=0.05)
    instances, calls, wakes = [], [], []
    original = lbr.LiveBlendRefresher

    class RecordingRefresher(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

    async def cadence(
        flush, period, stop=None, *, failed_retry_interval_s=None,
        wake=None, work_count=None, wake_coalesce_s=None,
    ):
        # #10090: what each caller passes for the idle wake, asserted per
        # caller by the tests (PM's standalone flush passes neither; only
        # PM's game flush takes the post-wake coalescing pause).
        wakes.append((
            isinstance(wake, asyncio.Event),
            None if work_count is None else work_count(),
            wake_coalesce_s,
        ))
        calls.append((period, failed_retry_interval_s))
        await stop.wait()

    monkeypatch.setattr(lbr, "LiveBlendRefresher", RecordingRefresher)
    monkeypatch.setattr(lbr, "run_flush_cadence", cadence)
    await asyncio.wait_for(consumer(), timeout=3)
    return calls, instances, wakes


@pytest.mark.parametrize(
    "override,legacy,expected_period,expected_retry,expected_floor",
    [
        (None, 2, 2, None, 2),
        (None, 3.5, 3.5, None, 2),
        ("1", 2, 1, 2, 1),
        ("1", 4, 1, 4, 1),
        ("0.75", 2, 0.75, 2, 0.75),
    ],
)
async def test_real_kalshi_consumer_binds_timer_floor_and_legacy_retry(
    monkeypatch, override, legacy, expected_period, expected_retry, expected_floor,
):
    if override is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, override)
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", legacy)
    calls, instances, wakes = await _run_recording(monkeypatch, "kalshi")
    assert calls == [(expected_period, expected_retry)]
    # The Kalshi flush opts into the idle wake with a zero actual-work count.
    assert wakes == [(True, 0, None)]  # Kalshi: no coalescing pause
    (refresher,) = instances
    assert refresher.min_refresh_interval_s == expected_floor
    # Nothing else about the refresher moves with the timer.
    assert refresher.failed_retry_interval_s == 5
    assert refresher.snapshot_interval_s == 25
    assert refresher.snapshot_max_gap_s == 60


@pytest.mark.parametrize("override", ["", "garbage", "0", "-1", "nan", "inf", "-inf"])
async def test_invalid_kalshi_override_is_rejected_before_slate_or_socket(
    monkeypatch, override,
):
    _module, consumer, _ = _arm(monkeypatch, "kalshi")
    monkeypatch.setenv(ENV, override)

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid cadence reached a provider or database")

    import app.services.kalshi_ws as service
    import app.tasks.base as task_base

    monkeypatch.setattr(service, "KalshiWebSocket", forbidden)
    monkeypatch.setattr(task_base, "get_task_session", forbidden)
    with pytest.raises(ValueError, match="positive finite"):
        await consumer()


async def test_kalshi_override_does_not_change_real_pm_consumer(monkeypatch):
    monkeypatch.setenv(ENV, "1")
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    import app.tasks.polymarket_ws as poly_task

    monkeypatch.setattr(poly_task, "PRICE_FLUSH_SECONDS", 3.5)
    calls, instances, wakes = await _run_recording(monkeypatch, "polymarket")
    # The PM game flush, then its standalone flush on the base timer (962ced).
    assert calls == [(3.5, 3.5), (3.5, None)]
    # Only the game flush takes the idle wake and its coalescing pause;
    # standalone stays timer-only.
    assert wakes == [
        (True, 0, poly_task.PM_WAKE_COALESCE_SECONDS), (False, None, None),
    ]
    assert 0 < poly_task.PM_WAKE_COALESCE_SECONDS <= 0.01
    assert instances[0].min_refresh_interval_s == 2


def test_cadence_without_override_is_the_shared_timer_read_at_call_time(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 0.01)
    assert kalshi_task.kalshi_flush_cadence() == (
        0.01, lbr.DEFAULT_MIN_REFRESH_INTERVAL_S, None, None,
    )


def test_override_keeps_the_module_non_live_budget(monkeypatch):
    monkeypatch.setenv(ENV, "1")
    monkeypatch.setattr(kalshi_task, "PRICE_FLUSH_SECONDS", 2)
    assert kalshi_task.kalshi_flush_cadence() == (1.0, 1.0, 2, None)


class TestBudgetArgument:
    """`flush_budget_spent` takes the run's budget; `None` keeps the module's."""

    def _spent(self, monkeypatch, elapsed, budget):
        monkeypatch.setattr(lbr, "_mono", lambda: 100.0 + elapsed)
        return kalshi_task.flush_budget_spent(
            100.0, {1: 0.5}, {1: 77}, {99}, budget,
        )

    def test_run_budget_stops_a_non_live_phase_the_module_budget_would_start(
        self, monkeypatch,
    ):
        monkeypatch.setattr(kalshi_task, "FLUSH_BUDGET_SECONDS", 4.0)
        assert self._spent(monkeypatch, 2.5, 2.0) is True
        assert self._spent(monkeypatch, 2.5, None) is False

    def test_none_reads_the_module_budget_at_call_time(self, monkeypatch):
        monkeypatch.setattr(kalshi_task, "FLUSH_BUDGET_SECONDS", 1.0)
        assert self._spent(monkeypatch, 1.5, None) is True

    def test_live_phase_is_never_stopped_by_a_run_budget(self, monkeypatch):
        monkeypatch.setattr(lbr, "_mono", lambda: 1_000.0)
        assert kalshi_task.flush_budget_spent(
            100.0, {1: 0.5}, {1: 77}, {77}, 0.5,
        ) is False
