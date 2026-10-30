"""#10090 — a Kalshi game a row lock held back of a committed phase keeps the
#11138 overlay, exactly as a refused phase does.

## the rig

#11138's Kalshi rig (`test_kalshi_held_quotes_10090.held_rig`): the SHIPPED
`flush_prices` on a controlled session, with a real `HeldRowQuotes`. Games
100 (outcomes 1, 2) and 200 (outcome 3) are non-live, so the run's plan packs
them into ONE phase, as production packs up to 200 rows. Outcome 1's row is
held by another transaction: the session answers the phase's SKIP LOCKED
pre-pass (`kalshi_skip_locked_stmt`) with it, as PostgreSQL does.

## what is asserted

* game 200 is written and committed in that phase; game 100 is held back
  whole (no UPDATE for 1 or 2, no rollback, no error), still buffered;
* game 100's received quotes reach the stamp now through the overlay;
* the skip is counted (`price_rows_skipped_locked`), never an error;
* once the holder lets go, the next flush writes game 100 and the overlay
  lets go of its legs.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import tests.test_kalshi_game_isolation_10655 as isolation
from tests._kalshi_price_session import is_skip_locked_pass
from tests.pm_bulk_test_support import statement_params
from tests.test_kalshi_held_quotes_10090 import EVENT, Clock, held_rig

pytestmark = pytest.mark.asyncio


def rows_locked_elsewhere(monkeypatch, x):
    """The rig's sessions model PostgreSQL row locks for the pre-pass."""
    bind = isolation.bind_session

    def binder(session, engine):
        session.models_row_locks = True
        session = bind(session, engine)
        execute = session.execute

        async def answer(stmt, *args, **kwargs):
            if is_skip_locked_pass(stmt):
                ids = statement_params(stmt)["skip_ids"]
                held = [
                    oid for oid in ids
                    if oid in x.control["locked"] and not x.lock_released.is_set()
                ]
                x.trace.append(("skip_locked", tuple(ids), tuple(held)))
                rows = [SimpleNamespace(id=oid) for oid in held]
                return SimpleNamespace(all=lambda: rows)
            return await execute(stmt, *args, **kwargs)

        session.execute = answer
        return session

    monkeypatch.setattr(isolation, "bind_session", binder)


async def test_a_held_back_game_of_a_committed_phase_takes_the_overlay(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, live=(), locked=(1,))
    x.ns["live_event_ids"] = set()  # the run's non-live plan packs both games
    rows_locked_elsewhere(monkeypatch, x)
    x.tick(3, 0.72)

    assert await x.flush(clock.t) is True
    # One phase held both games; the pre-pass found 1 held.
    assert ("skip_locked", (1, 2, 3), (1,)) in x.trace, x.trace
    # Game 200 committed in it; game 100 was never written or rolled back.
    assert x.committed == [3]
    assert ("write", 1) not in x.trace and ("write", 2) not in x.trace
    assert not any(t[0] == "rollback" for t in x.trace)
    assert x.stats["errors"] == 0 and x.stats["requeued"] == 0
    assert x.stats["price_rows_skipped_locked"] == 2
    # Q491: still buffered, with their received values.
    assert x.batch == {1: (0.61, None, None), 2: (0.39, None, None)}
    # #11138: the held game's received quotes reach the stamp now.
    assert 1 in x.held and 2 in x.held
    assert any(
        EVENT in ids and {1, 2} <= quotes.keys() for ids, quotes in x.stamped
    ), x.stamped
    # No cooldown: the next flush retries it at once.
    assert not x.prices.lock_retry_until

    x.lock_released.set()
    clock.t += 0.25
    assert await x.flush(clock.t) is True
    assert sorted(x.committed) == [1, 2, 3]
    assert not x.batch
    assert 1 not in x.held and 2 not in x.held


def test_the_pre_pass_locks_in_phase_order_behind_the_updates_predicate():
    from sqlalchemy.dialects import postgresql

    from app.utils.kalshi_price_statement import kalshi_skip_locked_stmt

    text = str(kalshi_skip_locked_stmt(
        [(1, 0.5, None, None, False), (2, 0.4, 0.3, 0.5, True)]
    ).compile(dialect=postgresql.dialect()))
    locked = text[text.index("locked AS MATERIALIZED"):]
    # Deadlock avoidance: phase order. The settled refusal and the repeat
    # predicate run before LockRows, so a row the UPDATE would not write
    # takes no lock.
    assert "ORDER BY given.ord FOR NO KEY UPDATE OF futures_outcomes SKIP LOCKED" in locked
    assert locked.index("resolution_source IS NULL") < locked.index("FOR NO KEY UPDATE")
    assert locked.index("given.force OR") < locked.index("FOR NO KEY UPDATE")


async def test_a_held_row_holds_back_its_whole_question_even_across_events(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, live=(), locked=(1,))
    x.ns["live_event_ids"] = set()
    # Outcome 3 names game 200 but sits on market 10 with the held row.
    x.ns["market_id_by_outcome"][3] = 10
    rows_locked_elsewhere(monkeypatch, x)
    x.tick(3, 0.72)
    x.batch[4] = (0.3, None, None)  # an unrelated contract on its own market
    x.ns["market_id_by_outcome"][4] = 40

    assert await x.flush(clock.t) is True
    # Game 100 whole AND market 10 whole: the question is never written half.
    assert ("write", 3) not in x.trace and ("write", 1) not in x.trace
    assert 4 in x.committed and 3 not in x.committed
    assert x.stats["price_rows_skipped_locked"] == 3


async def test_a_held_leg_holds_back_its_whole_game_across_its_markets(monkeypatch):
    clock = Clock(monkeypatch)
    x = held_rig(monkeypatch, live=(), locked=(1,))
    x.ns["live_event_ids"] = set()
    x.ns["market_id_by_outcome"][2] = 11  # game 100's second leg, its own market
    rows_locked_elsewhere(monkeypatch, x)
    x.tick(3, 0.72)

    assert await x.flush(clock.t) is True
    # Game 100 is held back whole, both markets: no stamp reads it half written.
    assert x.committed == [3]
    assert ("write", 2) not in x.trace
    assert x.batch.keys() == {1, 2}
