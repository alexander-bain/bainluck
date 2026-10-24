"""Keep continuous Kalshi delivery without retaining obsolete startup rows."""

import json
import weakref

import pytest

from tests import test_ws_consumer_session_lifetime_2471 as rig_module
from tests.test_ws_flush_retry_q491 import KALSHI_SLATE, KALSHI_TICKER, _Frames


async def test_startup_rows_released_before_subscription_price_still_delivered(monkeypatch):
    class Rows(list):
        pass

    startup_refs = []
    subscriptions = []
    retained_at_subscribe = []
    original_result = rig_module._Result

    class TrackedResult(original_result):
        def all(self):
            if len(startup_refs) < 2:
                rows = Rows(super().all())
                startup_refs.append(weakref.ref(rows))
                return rows
            return super().all()

    async def record_subscription(self, payload):
        subscriptions.append(json.loads(payload))
        retained_at_subscribe.append([ref() is not None for ref in startup_refs])

    monkeypatch.setattr(rig_module, "_Result", TrackedResult)
    monkeypatch.setattr(_Frames, "send", record_subscription)
    rig = rig_module._Rig(KALSHI_SLATE)
    await rig_module._run_kalshi(
        monkeypatch,
        [rig_module._kalshi_tick("0.40", "0.44")],
        rig,
    )

    assert len(startup_refs) == 2
    assert subscriptions
    assert any(
        KALSHI_TICKER in message.get("params", {}).get("market_tickers", [])
        for message in subscriptions
    ), subscriptions
    assert retained_at_subscribe[0] == [False, False]
    assert rig.writes and rig.writes[-1][1] == pytest.approx(0.42)
    rig_module._assert_one_lent_engine(rig, "kalshi")
    rig_module._assert_disposed_once_after_last_session(rig, "kalshi")
