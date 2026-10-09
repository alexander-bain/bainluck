"""#10662: PM may flush sooner without shortening retries or changing Kalshi."""

import asyncio

import pytest

import app.tasks.live_blend_refresh as lbr
from tests.test_ws_admission_mapped_legs_9462 import (
    _arm,
    _install_quiet_socket,
    _install_session,
    _timing,
)
from tests.test_ws_flush_cadence_10090 import _FakeTime


@pytest.mark.parametrize(
    "override,legacy,expected_period,expected_floor",
    [
        (None, 2, 2, 2),
        (None, 3.5, 3.5, 2),
        (None, 0.5, 0.5, 2),
        ("1", 2, 1, 1),
        ("1", 4, 1, 1),
        ("2.5", 2, 2.5, 2.5),
    ],
)
async def test_real_pm_consumer_binds_timer_floor_and_legacy_retry(
    monkeypatch,
    override,
    legacy,
    expected_period,
    expected_floor,
):
    module, consumer, slate = _arm(monkeypatch, "polymarket")
    if override is None:
        monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    else:
        monkeypatch.setenv("PM_WS_PRICE_FLUSH_SECONDS", override)
    monkeypatch.setattr(module, "PRICE_FLUSH_SECONDS", legacy)
    _install_quiet_socket(monkeypatch)
    _install_session(monkeypatch, slate, lambda _: [])
    _timing(monkeypatch, module, refresh=0.05)
    instances = []
    calls = []
    original = lbr.LiveBlendRefresher

    class RecordingRefresher(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

    async def cadence(flush, period, stop=None, *, failed_retry_interval_s=None,
                      wake=None, work_count=None):
        calls.append((period, failed_retry_interval_s))
        if failed_retry_interval_s is not None:
            assert isinstance(wake, asyncio.Event) and work_count() == 0
        else:
            assert wake is None and work_count is None
        await stop.wait()

    monkeypatch.setattr(lbr, "LiveBlendRefresher", RecordingRefresher)
    monkeypatch.setattr(lbr, "run_flush_cadence", cadence)
    await asyncio.wait_for(consumer(), timeout=3)
    # #10090: the game flush, then the standalone open-contract flush on
    # the base timer with the base retry (962ced1dc6).
    assert calls == [(expected_period, legacy), (legacy, None)]
    (refresher,) = instances
    assert refresher.min_refresh_interval_s == expected_floor
    assert refresher.failed_retry_interval_s == 5
    assert refresher.snapshot_interval_s == 25
    assert refresher.snapshot_max_gap_s == 60
    assert lbr.DELIVERY_RECEIPT_MAX_STAMPS == 40


@pytest.mark.parametrize("override", ["", "garbage", "0", "-1", "nan", "inf", "-inf"])
async def test_invalid_pm_override_is_rejected_before_slate_or_socket(
    monkeypatch,
    override,
):
    module, consumer, _ = _arm(monkeypatch, "polymarket")
    monkeypatch.setenv("PM_WS_PRICE_FLUSH_SECONDS", override)

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid cadence reached a provider or database")

    import app.services.polymarket_ws as service
    import app.tasks.base as task_base

    monkeypatch.setattr(service, "PolymarketWebSocket", forbidden)
    monkeypatch.setattr(task_base, "get_task_session", forbidden)
    with pytest.raises(ValueError, match="positive finite"):
        await consumer()


async def test_pm_override_does_not_change_real_kalshi_consumer(monkeypatch):
    module, consumer, slate = _arm(monkeypatch, "kalshi")
    monkeypatch.setenv("PM_WS_PRICE_FLUSH_SECONDS", "1")
    monkeypatch.setattr(module, "PRICE_FLUSH_SECONDS", 3.5)
    _install_quiet_socket(monkeypatch)
    _install_session(monkeypatch, slate, lambda _: [])
    _timing(monkeypatch, module, refresh=0.05)
    instances = []
    calls = []
    original = lbr.LiveBlendRefresher

    class RecordingRefresher(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

    async def cadence(flush, period, stop=None, *, failed_retry_interval_s=None):
        calls.append((period, failed_retry_interval_s))
        await stop.wait()

    monkeypatch.setattr(lbr, "LiveBlendRefresher", RecordingRefresher)
    monkeypatch.setattr(lbr, "run_flush_cadence", cadence)
    await asyncio.wait_for(consumer(), timeout=3)
    assert calls == [(3.5, None)]
    assert instances[0].min_refresh_interval_s == 2


@pytest.mark.parametrize("period,retry", [(1, 2), (1, 4), (0.5, None), (3.5, None)])
async def test_failure_delay_can_keep_legacy_period_independent_of_timer(
    monkeypatch,
    period,
    retry,
):
    clock = _FakeTime(monkeypatch)
    stop = asyncio.Event()
    calls = []

    async def flush(started):
        clock.t += 0.2
        calls.append((started, clock.t))
        if len(calls) == 2:
            stop.set()
        return False

    await lbr.run_flush_cadence(
        flush,
        period,
        stop=stop,
        failed_retry_interval_s=retry,
    )
    assert calls[0][0] == pytest.approx(1_000_000.1 + period)
    expected_retry = period if retry is None else retry
    assert calls[1][0] - calls[0][1] == pytest.approx(expected_retry)


async def test_retry_override_leaves_healthy_start_to_start_schedule(monkeypatch):
    clock = _FakeTime(monkeypatch)
    stop = asyncio.Event()
    starts = []

    async def flush(started):
        starts.append(started)
        clock.t += 0.2
        if len(starts) == 3:
            stop.set()
        return True

    await lbr.run_flush_cadence(
        flush,
        1,
        stop=stop,
        failed_retry_interval_s=2,
    )
    assert [b - a for a, b in zip(starts, starts[1:])] == [1, 1]
