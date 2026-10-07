"""#10661 — a held Kalshi game no longer holds the independent games after it.

Executes the SHIPPED `flush_prices` / `drain_prices` closures (AST) on the
#10655 rig, whose session fakes Postgres's lock rule: a transaction that set
`lock_timeout` gives up on a held row with SQLSTATE 55P03; one that did not
waits for the holder. Commit/publication ordering only, not production timing;
`tests/integration/test_kalshi_price_lock_budget_pg_10661.py` holds the real
row locks.
"""
import ast
import asyncio
from pathlib import Path

import pytest

from app.tasks.kalshi_ws import PRICE_PHASE_LOCK_TIMEOUT_MS
from tests.test_kalshi_game_isolation_10655 import rig

GAME_100 = (1, 2)  # outcomes of event 100 (one market, two siblings)
SOURCE = Path(__file__).resolve().parents[1] / "app/tasks/kalshi_ws.py"


async def bounded(coro):
    """Every flush is bounded: a mutant that waits on the held row must fail."""
    return await asyncio.wait_for(coro, 2)


def with_drain(r, *, attempts=3):
    """Bind the shipped `drain_prices` to the rig's exec'd `flush_prices`."""
    tree = ast.parse(SOURCE.read_text())
    (node,) = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
               and n.name == "drain_prices"]
    r.ns["FINAL_FLUSH_ATTEMPTS"] = attempts
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), r.ns)
    return r.ns["drain_prices"]


def test_the_budget_is_500ms():
    assert PRICE_PHASE_LOCK_TIMEOUT_MS == 500


async def test_a_held_first_game_lets_the_later_game_commit_and_refresh():
    """THE SHIP. Before #10661 the held game stopped the flush at its phase."""
    r = rig(locked={1})
    r.release.set()
    assert await bounded(r.flush()) is False  # a retained phase still waits a full interval
    assert r.committed == [3, 9]
    assert set(r.batch) == set(GAME_100)
    # The failed component published, receipted and refreshed nothing.
    assert ("rollback", ()) in r.trace
    assert ("refresh", (200,)) in r.trace
    assert not any(t[0] == "refresh" and 100 in t[1] for t in r.trace)
    assert not any(t[0] == "publish" and set(t[1]) & set(GAME_100) for t in r.trace)
    assert not any(t[0] == "receipt" and set(t[1]) & set(GAME_100) for t in r.trace)
    assert ("receipt", (3,)) in r.trace
    assert r.stats["errors"] == 1
    assert r.stats["requeued"] == 2  # only the held component, not the tail
    assert r.stats["flushes"] == 1  # counted once, on the first commit
    assert r.stats["price_updates"] == 2

    # The next flush pays the retained game once the holder lets go.
    r.lock_released.set()
    assert await bounded(r.flush()) is True
    assert r.committed == [3, 9, 1, 2]
    assert not r.batch
    assert r.stats["flushes"] == 2


async def test_every_periodic_phase_arms_the_budget_first():
    r = rig()
    r.release.set()
    assert await bounded(r.flush()) is True
    opened = [i for i, t in enumerate(r.trace) if t[0] == "lock_timeout"]
    assert [r.trace[i] for i in opened] == [("lock_timeout", "500ms")] * 3
    # Armed before the phase's first write, in every transaction.
    for i in opened:
        assert r.trace[i + 1][0] == "write"


async def test_any_other_error_still_stops_the_whole_tail():
    r = rig(failed=1)
    r.release.set()
    assert await bounded(r.flush()) is False
    assert r.committed == []
    assert set(r.batch) == {1, 2, 3, 9}
    assert r.stats["requeued"] == 4
    assert not any(t[0] in ("publish", "refresh", "receipt") for t in r.trace)


async def test_a_newer_tick_buffered_during_the_held_flush_survives():
    r = rig(locked={1})
    task = asyncio.create_task(r.flush())
    await asyncio.wait_for(r.entered.wait(), 2)  # game 200's write is in flight
    r.batch[1] = (.9, .89, .91)  # a fresher tick for the held game
    r.batch[3] = (.8, .79, .81)  # and for the game being written
    r.release.set()
    assert await asyncio.wait_for(task, 2) is False
    assert r.batch == {1: (.9, .89, .91), 2: (.4, .39, .41), 3: (.8, .79, .81)}
    r.lock_released.set()
    assert await bounded(r.flush()) is True
    assert not r.batch


async def test_refresh_debt_keeps_games_together_so_nothing_continues_past_it():
    """The planner joins every game while a stamp is owed; a held row then
    holds them all, and the debt is not paid ahead of the unwritten prices."""
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    r = rig(locked={1})

    class RecordingRefresher(LiveBlendRefresher):
        async def _refresh_batch(self, event_ids, now):
            r.trace.append(("real-refresh", tuple(sorted(event_ids))))
            for event_id in event_ids:
                self._last_refresh_at[event_id] = now

        async def publish_market_changes(self, session):
            r.trace.append(("publish", tuple(session.rows)))

    refresher = RecordingRefresher("kalshi")
    refresher.adopt_pending({200})
    r.ns["blend_refresher"] = refresher
    r.release.set()
    assert await bounded(r.flush(flush_started=100.0)) is False
    assert r.committed == [9]
    assert set(r.batch) == {1, 2, 3}
    assert not any(t[0] == "real-refresh" for t in r.trace)
    assert refresher.pending_event_ids() == frozenset({200})


async def test_the_real_refresher_stamps_the_continued_game_after_its_commit():
    from app.tasks.live_blend_refresh import LiveBlendRefresher

    r = rig(locked={1})

    class RecordingRefresher(LiveBlendRefresher):
        async def _refresh_batch(self, event_ids, now):
            r.trace.append(("real-refresh", tuple(sorted(event_ids)), tuple(r.committed)))
            for event_id in event_ids:
                self._last_refresh_at[event_id] = now

        async def publish_market_changes(self, session):
            r.trace.append(("publish", tuple(session.rows)))

    refresher = RecordingRefresher("kalshi")
    r.ns["blend_refresher"] = refresher
    r.release.set()
    assert await bounded(r.flush(flush_started=100.0)) is False
    stamps = [t for t in r.trace if t[0] == "real-refresh"]
    assert stamps == [("real-refresh", (200,), (3,))]
    assert r.trace.index(("commit", (3,))) < r.trace.index(("publish", (3,)))
    assert r.trace.index(("publish", (3,))) < r.trace.index(stamps[0])
    assert r.trace.index(stamps[0]) < r.trace.index(("commit", (9,)))
    assert refresher.pending_event_ids() == frozenset()


async def test_cancellation_while_a_later_game_writes_keeps_every_unpaid_row():
    r = rig(locked={1})
    task = asyncio.create_task(r.flush())
    await asyncio.wait_for(r.entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert r.committed == []
    assert set(r.batch) == {1, 2, 3, 9}


async def test_the_final_drain_waits_for_the_lock_instead_of_dropping():
    """Live's required correction to the prototype. Three back-to-back attempts
    at 500 ms each would strand the held game's prices (final_flush_dropped)."""
    r = rig(locked={1})
    drain = with_drain(r)
    r.release.set()
    task = asyncio.create_task(drain())
    for _ in range(50):
        await asyncio.sleep(0)
    assert not task.done()
    assert ("lock-wait", 1) in r.trace
    assert not any(t[0] == "lock_timeout" for t in r.trace)
    r.lock_released.set()
    await asyncio.wait_for(task, 2)
    assert r.committed == [1, 2, 3, 9]
    assert not r.batch
    assert r.stats["final_flush_dropped"] == 0
    assert r.stats["final_flush_retries"] == 0


async def test_strawman_a_drain_under_the_periodic_budget_drops_the_held_game():
    """The control that makes the drain test mean something: the same drain,
    mutated to call the periodic flush, strands the held game's two prices."""
    r = rig(locked={1})
    tree = ast.parse(SOURCE.read_text())
    (node,) = [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
               and n.name == "drain_prices"]
    text = ast.unparse(node)
    assert text.count("flush_prices(final_drain=True)") == 1
    r.ns["FINAL_FLUSH_ATTEMPTS"] = 3
    exec(text.replace("flush_prices(final_drain=True)", "flush_prices()"), r.ns)
    r.release.set()
    await asyncio.wait_for(r.ns["drain_prices"](), 2)
    assert r.committed == [3, 9]
    assert r.stats["final_flush_dropped"] == 2
