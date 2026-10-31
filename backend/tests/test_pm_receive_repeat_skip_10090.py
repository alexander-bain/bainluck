"""#10090: a repeated Polymarket top of book costs almost nothing on receipt.

Production 2026-10-31 01:05Z/01:23Z (v5990): receive was 40 % of the PM
loop, `_price_quotes` 23-26 % cumulative and `handle_price` 18-21 %, while
71-75 % of messages were repeats that `_skip_repeat` dropped only at the end.
"""

import pytest

from app.services import polymarket_ws as svc
from tests.test_pm_nested_bbo_10090 import FRAMES, drive


@pytest.mark.asyncio
async def test_a_price_change_frame_is_normalized_once_not_again_per_quote(monkeypatch):
    calls = []
    real = svc._price_change_quotes

    def counted(message):
        calls.append(message)
        return real(message)

    monkeypatch.setattr(svc, "_price_change_quotes", counted)
    observed, _ = await drive(monkeypatch, FRAMES[:1])
    assert len(observed) == len(FRAMES[0]["price_changes"]) == 2
    # The frame once, and the raw `best_bid_ask` sentinel once (it arrives
    # unvalidated) — never each quote the frame already produced.
    assert len(calls) == 2
    assert calls[0] is not None and calls[0].get("event_type") == "price_change"
