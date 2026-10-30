"""#10090 (Argon Rank 3) — the consumer maintains `headline_aux_outcome_ids`,
and the final drain never splits a live game (lane1's REVISE on 2c1ce924).

`test_flush_loop_live_aux_phase_10090.py` seeds the aux set straight onto its
flush rig, so nothing there proves the REAL consumer fills it. With the
startup fill deleted, Rank 3 is inert in production and every one of those
tests stays green. These run the real consumer on the changed-scope rig:

* startup fills the set from the linked tickers;
* a re-scope rebuilds it IN PLACE (the flush holds the same object): a new aux
  outcome joins, a removed one that is still buffered is carried, a removed
  one with nothing buffered leaves, and a bridged winner is never aux;
* the final drain writes each live game — headline and aux — as one phase.

Mutants these kill (each survives the author's file and the changed-scope,
flush-budget, held-quotes and mixed-batch suites): Ma drop the `apply_scope`
update, Mb drop the buffered carry, Mc delete the startup fill, Me let the
final drain split. Probes adopted from lane1's review (P2, P2b, P4).
"""

import asyncio

import pytest

import app.tasks.live_blend_refresh as lbr
import tests.test_flush_loop_live_aux_phase_10090 as bfile
import tests.test_kalshi_changed_scope_continuity_10090 as cs


AUX_A_T = "KXNEWPROPA-26OCT08SFLAR-X"
AUX_B_T = "KXNEWPROPB-26OCT09DALPHI-Y"


class AuxScope(cs.Scope):
    """The changed-scope rig with one aux market per game: version 1 links
    game A + aux 72; version 2 drops aux 72 and adds game B + aux 74."""

    async def execute(self, statement, *args):
        columns = [str(c) for c in getattr(statement, "selected_columns", ())]
        if columns == ["futures_markets.external_id", "futures_markets.id",
                       "futures_markets.event_id"]:
            rows = [(cs._event(cs.GAME_A), 7, 900)]
            rows += ([(cs._event(AUX_A_T), 12, 900)] if self.version == 1 else
                     [(cs._event(cs.GAME_B), 9, 904), (cs._event(AUX_B_T), 13, 904)])
            return cs.Result(rows)
        if columns == ["futures_outcomes.external_id", "futures_outcomes.market_id",
                       "futures_outcomes.id"]:
            rows = [(cs.GAME_A, 7, 71)]
            rows += ([(AUX_A_T, 12, 72)] if self.version == 1 else
                     [(cs.GAME_B, 9, 73), (AUX_B_T, 13, 74)])
            return cs.Result(rows)
        return await super().execute(statement, *args)


@pytest.mark.asyncio
async def test_startup_fills_the_aux_set_and_a_rescope_keeps_it_in_place(monkeypatch):
    """Mc (startup fill), Ma (`apply_scope` update) and Mb (buffered carry)."""
    held = {}
    gate = asyncio.Event()

    class Capturing(cs.Prices):
        def __init__(self, scope):
            super().__init__(scope)
            held["prices"] = self

        async def phase(self, session, values, **kw):
            if 72 in values and not gate.is_set():
                # A row lock refuses the write until after the re-scope, so
                # the price is still buffered (owed) when the scope changes.
                held["in_flight"] = True
                exc = RuntimeError("lock timeout")
                exc.sqlstate = "55P03"
                raise exc
            async for result in super().phase(session, values, **kw):
                yield result

    monkeypatch.setattr(cs, "Prices", Capturing)
    monkeypatch.setattr(cs, "MARKET_BY_OUTCOME", {**cs.MARKET_BY_OUTCOME, 72: 12, 74: 13})
    scope = AuxScope()
    running, _sockets, _acking, socket_for, opened_sockets = cs._rig(monkeypatch, scope)
    try:
        await cs._until(lambda: opened_sockets() == 3, "startup sockets")
        aux = held["prices"].headline_aux_outcome_ids
        assert aux == {72}, "startup fills the aux set from the linked tickers"
        game_1 = socket_for({cs.GAME_A, AUX_A_T})
        # Buffered when its market leaves scope: carried with its aux status.
        await game_1.deliver("ticker", {"market_ticker": AUX_A_T, "price_dollars": "0.40"})
        await cs._until(lambda: held.get("in_flight"), "the aux write in flight")
        assert 72 not in scope.written
        scope.version = 2
        await cs._until(lambda: opened_sockets() == 5, "changed scope")
        assert held["prices"].headline_aux_outcome_ids is aux, "kept IN PLACE"
        assert aux == {72, 74}, "new aux joins; the buffered removed aux is carried"
        assert 81 not in aux, "the bridged OPEN_1 winner is never aux"
    finally:
        gate.set()
        await cs._stop(running)


@pytest.mark.asyncio
async def test_a_rescope_drops_a_removed_aux_with_nothing_buffered(monkeypatch):
    """Ma, from the other side: an unbuffered removed aux outcome leaves."""
    held = {}

    class Capturing(cs.Prices):
        def __init__(self, scope):
            super().__init__(scope)
            held["prices"] = self

    monkeypatch.setattr(cs, "Prices", Capturing)
    scope = AuxScope()
    running, _sockets, _acking, _socket_for, opened_sockets = cs._rig(monkeypatch, scope)
    try:
        await cs._until(lambda: opened_sockets() == 3, "startup sockets")
        scope.version = 2
        await cs._until(lambda: opened_sockets() == 5, "changed scope")
        assert held["prices"].headline_aux_outcome_ids == {74}
    finally:
        await cs._stop(running)


@pytest.mark.asyncio
async def test_the_final_drain_keeps_each_live_game_one_whole_phase(monkeypatch):
    """Me: with the aux set populated, the final drain still writes the live
    game's headline and its whole board in one phase."""
    built = bfile.rig()  # the aux set IS populated
    monkeypatch.setattr(lbr, "_mono", lambda: built.clock["now"])
    built.buffer.update(bfile.batch_oldest_aux_first())
    assert await built.flush(None, final_drain=True) is True
    assert not built.buffer
    head_a = next(rows for rows in built.commits if bfile.HEAD_A[0] in rows)
    assert set(bfile.HEAD_A) | set(bfile.AUX_A) <= set(head_a), "whole game, one phase"
