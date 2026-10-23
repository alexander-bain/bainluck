"""#10090: the PM game flush may run faster than its linked props.

`PM_WS_GAME_FLUSH_SECONDS` moves only the game flush timer and the blend
floor. Linked props keep `PM_WS_PRICE_FLUSH_SECONDS` (or the legacy timer),
every failed write keeps the legacy retry, and the standalone open-contract
flush and the Kalshi consumer do not move at all. Unset, nothing changes.
"""

import asyncio

import pytest

import app.tasks.live_blend_refresh as lbr
from tests.test_ws_admission_mapped_legs_9462 import (
    _arm,
    _install_quiet_socket,
    _install_session,
    _timing,
)


def _set(monkeypatch, name, value):
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)


async def _bindings(monkeypatch, arm, *, price, game, legacy):
    """Run the real consumer to its loops and record what each one bound."""
    module, consumer, slate = _arm(monkeypatch, arm)
    _set(monkeypatch, "PM_WS_PRICE_FLUSH_SECONDS", price)
    _set(monkeypatch, "PM_WS_GAME_FLUSH_SECONDS", game)
    monkeypatch.setattr(module, "PRICE_FLUSH_SECONDS", legacy)
    _install_quiet_socket(monkeypatch)
    _install_session(monkeypatch, slate, lambda _: [])
    _timing(monkeypatch, module, refresh=0.05)
    instances = []
    calls = {}
    original = lbr.LiveBlendRefresher

    class RecordingRefresher(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

    async def cadence(flush, period, stop=None, *, failed_retry_interval_s=None,
                      **_wake):
        calls[flush.__name__] = (period, failed_retry_interval_s)
        await stop.wait()

    monkeypatch.setattr(lbr, "LiveBlendRefresher", RecordingRefresher)
    monkeypatch.setattr(lbr, "run_flush_cadence", cadence)
    await asyncio.wait_for(consumer(), timeout=3)
    (refresher,) = instances
    return calls, refresher.min_refresh_interval_s


@pytest.mark.parametrize(
    "price,game,legacy,game_period,prop_period,floor",
    [
        # Unset: exactly the #10662 behaviour, game and props together.
        (None, None, 2, 2, 2, 2),
        ("0.25", None, 2, 0.25, 0.25, 0.25),
        # Production's shape for the candidate: game 25 ms, props stay 250 ms.
        ("0.25", "0.025", 2, 0.025, 0.25, 0.025),
        # Without the shared override the props keep the legacy timer.
        (None, "0.025", 2, 0.025, 2, 0.025),
        (None, "0.5", 3.5, 0.5, 3.5, 0.5),
        # A slower game timer is honoured too; props do not follow it.
        ("0.25", "1", 2, 1, 0.25, 1),
    ],
)
async def test_game_override_moves_only_the_game_timer_and_blend_floor(
    monkeypatch, price, game, legacy, game_period, prop_period, floor,
):
    calls, refresher_floor = await _bindings(
        monkeypatch, "polymarket", price=price, game=game, legacy=legacy,
    )
    assert calls == {
        "flush_prices": (game_period, legacy),
        "flush_props": (prop_period, legacy),
        "flush_standalone": (legacy, None),
    }
    assert refresher_floor == floor


@pytest.mark.parametrize("override", ["", "garbage", "0", "-1", "nan", "inf", "-inf"])
async def test_invalid_game_override_is_rejected_before_slate_or_socket(
    monkeypatch, override,
):
    module, consumer, _ = _arm(monkeypatch, "polymarket")
    monkeypatch.setenv("PM_WS_PRICE_FLUSH_SECONDS", "0.25")
    monkeypatch.setenv("PM_WS_GAME_FLUSH_SECONDS", override)

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid cadence reached a provider or database")

    import app.services.polymarket_ws as service
    import app.tasks.base as task_base

    monkeypatch.setattr(service, "PolymarketWebSocket", forbidden)
    monkeypatch.setattr(task_base, "get_task_session", forbidden)
    with pytest.raises(ValueError, match="PM_WS_GAME_FLUSH_SECONDS must be"):
        await consumer()


async def test_game_override_does_not_change_real_kalshi_consumer(monkeypatch):
    calls, floor = await _bindings(
        monkeypatch, "kalshi", price="0.25", game="0.025", legacy=3.5,
    )
    assert list(calls.values()) == [(3.5, None)]
    assert floor == 2
