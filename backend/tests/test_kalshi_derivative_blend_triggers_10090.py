"""Prop price delivery continues while redundant fresh winner refresh is skipped."""

import pytest

from app.tasks.kalshi_ws import kalshi_non_speaking_ticker
from app.utils.futures_rank import rerank_market_fields_stmt
from tests.test_kalshi_game_isolation_10655 import rig


@pytest.mark.asyncio
async def test_derivatives_write_publish_but_winner_unknown_debt_and_drain_refresh():
    derivative = "KXNFLTOTAL-26OCT08NYJBUF"
    winner = "KXNFLGAME-26OCT08NYJBUF"
    assert kalshi_non_speaking_ticker(derivative)
    for ticker in (winner, None, "", "KXUNLISTEDPROP-26OCT08NYJBUF"):
        assert not kalshi_non_speaking_ticker(ticker)

    def setup(tickers, *, pending=(), only_first=False):
        r = rig(pending=pending)
        r.release.set()
        # Execute the production flush closure with its current rank statement.
        r.ns["rerank_market_fields_stmt"] = rerank_market_fields_stmt
        r.ns["non_blend_outcome_ids"] = {
            oid for oid, ticker in tickers.items()
            if kalshi_non_speaking_ticker(ticker)
        }
        if only_first:
            r.batch.pop(3)
            r.batch.pop(9)
        return r

    prop = setup({1: derivative, 2: derivative})
    assert await prop.flush() is True
    assert prop.committed == [1, 2, 3, 9] and not prop.batch
    assert ("publish", (1, 2)) in prop.trace
    assert ("refresh", (100,)) not in prop.trace
    assert ("refresh", ()) in prop.trace
    assert ("refresh", (200,)) in prop.trace

    for ticker in (winner, None, "", "KXUNLISTEDPROP-26OCT08NYJBUF"):
        speaking = setup({1: ticker, 2: derivative})
        assert await speaking.flush() is True
        assert ("refresh", (100,)) in speaking.trace
        assert speaking.committed == [1, 2, 3, 9] and not speaking.batch

    # New bridge/admission members are conservatively speaking by default.
    bridge = setup({1: derivative, 2: derivative})
    bridge.events[9] = 900
    assert await bridge.flush() is True
    assert ("refresh", (900,)) in bridge.trace

    debt = setup({1: derivative, 2: derivative}, pending={100}, only_first=True)
    assert await debt.flush() is True
    assert ("refresh", ()) in debt.trace
    assert await debt.flush() is True
    assert ("pending",) in debt.trace

    drain = setup({1: derivative, 2: derivative}, only_first=True)
    assert await drain.flush(final_drain=True) is True
    assert ("refresh", (100,)) in drain.trace
    assert drain.committed == [1, 2] and not drain.batch
