"""#10090 — one ambiguity episode survives a sibling stamp fencing its retry.

Executes the production flush closure through the held-quote rig: a refused
short probe's immediate ordinary attempt is fenced behind an admitted sibling
event's running stamp, and the next flush must still use the ordinary budget
inside the SAME episode. Controlled transactions, not PostgreSQL timing.
"""

import asyncio

import pytest

from tests.test_kalshi_held_quotes_10090 import Clock, PERIOD, held_rig


@pytest.mark.asyncio
async def test_mixed_phase_fence_does_not_restart_short_probe_episode(monkeypatch):
    clock = Clock(monkeypatch)
    start = clock.t
    # Event 100 has two legs, outcome 1 locked and positively ambiguous.
    # Event 200/outcome 3 accepts the existing held-quote overlay.
    x = held_rig(monkeypatch, answer={1}, live=(100, 200))
    x.tick(3, .70)
    # Exercise the planner's explicit fallback: unknown market membership
    # retains the complete batch as one phase, including both events.
    x.ns["market_id_by_outcome"].pop(3)
    entered, release = asyncio.Event(), asyncio.Event()

    async def hold_sibling_stamp(ids, **kwargs):
        assert set(ids) == {200}
        entered.set()
        await release.wait()

    x.ns["blend_refresher"].refresh = hold_sibling_stamp
    try:
        assert await x.flush(flush_started=clock.t)
        assert entered.is_set()
        assert x.stats["stamp_fenced"] == 3
        assert set(x.batch) == {1, 2, 3} and not x.committed
        assert 1 not in x.held and 2 not in x.held
        assert [v for k, v in x.trace if k == "lock_timeout"] == ["1ms"]
        first_episode = dict(x.prices.ambiguous_retry_since)

        # Let the admitted sibling finish. The next permitted attempt must
        # remember the positive ambiguity and use the original 50 ms budget.
        release.set()
        await x.prices.stamping
        clock.t += PERIOD
        assert await x.flush(flush_started=clock.t)
        assert set(x.batch) == {1, 2, 3} and not x.committed
        assert 1 not in x.held and 2 not in x.held
        budgets = [v for k, v in x.trace if k == "lock_timeout"]
        observed = {
            "first_episode": first_episode,
            "budgets": budgets,
            "final_episode": dict(x.prices.ambiguous_retry_since),
        }
        assert observed == {
            "first_episode": {1: start, 2: start, 3: start},
            "budgets": ["1ms", "50ms"],
            "final_episode": {1: start, 2: start, 3: start},
        }, observed
    finally:
        release.set()
        if x.prices.stamping is not None:
            await x.prices.stamping
