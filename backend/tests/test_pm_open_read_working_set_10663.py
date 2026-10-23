"""#10663 — the open-catalog read keeps only what the pairing needs.

Retained captures K5/K7 (10/21): the Polymarket venue process sits at
395-412 MB after each trim and 437-475 MB before it, and the dyno climbs
60-80 MB during every open-catalog read (30-130 s, seven refreshes in 54
minutes). A real-``Row`` model of that read at today's catalog (34,000
markets, 71,000 legs) put its Python working set at 87 MB over the kept
admission, two parts of it never read past the first pass:

1. the leg read held as one flat list of ~71,000 ``Row`` objects while the
   pairing rebuilt the three structures it actually reads from them, so both
   lived through the whole mapping — the reader now digests each chunk into
   ``OpenContractLegs`` as it arrives and the flat list is never built;
2. ``name`` and ``external_id`` of every open market, read, decoded and held
   for the whole pairing although the bridge reads them only for a market with
   an event (~2%) — the statement now carries them only for those rows.

Guards: the digested path pairs exactly like the flat path on every shape the
mapper reads (seeds × turn sizes); the digestion still gives the loop its
turns; the statement's projection; the bridge's indifference to event-less
names; and, through the real consumer, that the mapper is handed the digested
legs and never a list (the parent fails that one: it builds the list).
"""

import asyncio
from dataclasses import asdict

import pytest
import websockets
from sqlalchemy.dialects import postgresql

from app.tasks import live_blend_refresh as blend
from app.tasks import polymarket_open_contracts as open_mod
from app.tasks import polymarket_ws as task
from tests.test_pm_open_catalog_map_turns_10090 import _BulkRig, _Result, _catalog
from tests.test_pm_open_cycle_lifetime_10090 import until
from tests.test_ws_consumer_session_lifetime_2471 import _install
from tests.test_ws_flush_retry_q491 import POLY_SLATE_LIVE


class _ChunkedRig(_BulkRig):
    """``_BulkRig`` answering each leg statement with ITS markets' legs only
    (the ``market_ids`` bind), so a read split into several statements
    returns every leg exactly once, as production's ``= ANY`` read does."""

    def get_task_session(self, **kwargs):
        context, rig = super().get_task_session(**kwargs), self

        class Context:
            async def __aenter__(self):
                session = await context.__aenter__()
                route = session.execute

                async def chunked(stmt, params=None):
                    if str(stmt) == str(open_mod.open_contract_outcomes_stmt()):
                        ids = set(stmt.compile().params["market_ids"])
                        rig.leg_reads += 1
                        return _Result([r for r in rig.legs if r[1] in ids])
                    return await route(stmt, params)

                session.execute = chunked
                return session

            async def __aexit__(self, *exc):
                return await context.__aexit__(*exc)

        return Context()


def _ordered(admission):
    out = asdict(admission)
    return {k: list(v.items()) if isinstance(v, dict) else v for k, v in out.items()}


async def _digest(outcome_rows, chunk=2_000):
    """The reader's shape: one chunk of rows at a time, in read order."""
    legs = open_mod.OpenContractLegs()
    for i in range(0, len(outcome_rows), chunk):
        await legs.add_rows_cooperatively(outcome_rows[i:i + chunk])
    return legs


@pytest.mark.asyncio
@pytest.mark.parametrize("per_turn", [1, 7, None])
@pytest.mark.parametrize("seed", [1, 2, 3])
async def test_digested_legs_pair_exactly_like_the_flat_rows(monkeypatch, per_turn, seed):
    if per_turn is not None:
        monkeypatch.setattr(open_mod, "OPEN_MAP_ROWS_PER_TURN", per_turn)
    market_rows, outcome_rows, *rest = _catalog(seed)
    flat = open_mod.open_contract_asset_map(market_rows, outcome_rows, *rest)
    assert flat.asset_to_outcome and flat.asset_mirrors and flat.complement_of
    assert flat.counts["legs_graded"] and flat.counts["markets_without_tokens"]

    legs = await _digest(outcome_rows, chunk=37)
    assert legs.rows == len(outcome_rows)
    assert _ordered(open_mod.open_contract_asset_map(market_rows, legs, *rest)) == _ordered(flat)
    legs = await _digest(outcome_rows)
    turned = await open_mod.open_contract_asset_map_cooperatively(market_rows, legs, *rest)
    assert _ordered(turned) == _ordered(flat)
    # The bridge reads the admission, so it is the same too.
    assert list(open_mod.open_contract_event_candidates(market_rows, turned).items()) == list(
        open_mod.open_contract_event_candidates(market_rows, flat).items()
    )


def test_a_leg_row_is_read_once_and_the_same_way_in_both_paths():
    """``add`` is the one reader: NULL external ids become ``""`` in both the
    per-market legs and the by-outcome map, graded legs are recorded, and the
    per-market order is the read order."""
    legs = open_mod.OpenContractLegs()
    legs.add(11, 1, None, False)
    legs.add(12, 1, "0xa_no", True)
    legs.add(13, 2, "0xb_yes", None)
    assert legs.by_market == {1: [(11, ""), (12, "0xa_no")], 2: [(13, "0xb_yes")]}
    assert legs.ext_by_outcome == {11: "", 12: "0xa_no", 13: "0xb_yes"}
    assert legs.graded == {12}
    assert legs.rows == 3


@pytest.mark.asyncio
async def test_digestion_gives_the_loop_a_turn_every_n_rows(monkeypatch):
    monkeypatch.setattr(open_mod, "OPEN_MAP_ROWS_PER_TURN", 7)
    _market_rows, outcome_rows, *_rest = _catalog(4)
    ticks, done = [0], asyncio.Event()

    async def ticker():
        while not done.is_set():
            ticks[0] += 1
            await asyncio.sleep(0)

    probe = asyncio.create_task(ticker())
    await asyncio.sleep(0)
    start = ticks[0]
    legs = await open_mod.OpenContractLegs().add_rows_cooperatively(outcome_rows)
    turns = ticks[0] - start
    done.set()
    await probe
    assert legs.rows == len(outcome_rows)
    # Pauses come before row 7, 14, ...: (n - 1) // 7 of them; the ticker runs once each.
    assert turns >= (len(outcome_rows) - 1) // 7


def test_market_read_carries_name_and_external_id_only_with_an_event():
    stmt = open_mod.open_contract_markets_stmt()
    keys = [c.key for c in stmt.selected_columns]
    # Same seven positions the mapper (``row[:4]``) and the bridge
    # (``row[4]``, ``row[5]``, ``row[6]``) index.
    assert len(keys) == 7 and keys[0] == "id" and keys[4:] == ["event_id", "name", "external_id"], keys
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    for column in ("futures_markets.name", "futures_markets.external_id"):
        assert (
            f"CASE WHEN (futures_markets.event_id IS NOT NULL) THEN {column} END" in sql
        ), sql
    # The predicate is the same read as before: unsettled Polymarket markets.
    assert "futures_markets.source = " in sql and "futures_markets.settled_at IS NULL" in sql


@pytest.mark.asyncio
async def test_the_bridge_never_read_an_event_less_market_name():
    """Rows as the parent read them (every name present) and as the statement
    now returns them (name/external_id NULL without an event) bridge the same
    legs to the same events; the event-bearing game winners are still bridged."""
    market_rows, outcome_rows, *rest = _catalog(5)
    assert any(r[4] is None and r[5] for r in market_rows)  # event-less rows with names
    admission = open_mod.open_contract_asset_map(market_rows, outcome_rows, *rest)
    full = open_mod.open_contract_event_candidates(market_rows, admission)
    assert full
    projected = [
        (mid, a, b, by_outcome, event, name if event is not None else None,
         ext if event is not None else None)
        for mid, a, b, by_outcome, event, name, ext in market_rows
    ]
    assert open_mod.open_contract_asset_map(projected, outcome_rows, *rest).counts == admission.counts
    assert list(open_mod.open_contract_event_candidates(projected, admission).items()) == list(full.items())
    assert list(
        (await open_mod.open_contract_event_candidates_cooperatively(projected, admission)).items()
    ) == list(full.items())


@pytest.mark.asyncio
async def test_the_real_consumer_hands_the_mapper_digested_legs_not_a_row_list(monkeypatch):
    """Through `_run_polymarket_ws_consumer`: the open read's mapper call
    receives ``OpenContractLegs`` holding every leg row the chunks returned,
    and the admission it produces is the one the flat rows would have given.
    On the parent the mapper receives a ``list`` (the flat rows), so this fails
    there for the stated reason."""
    n = 40
    rig, stop = _ChunkedRig(n), asyncio.Event()
    rig.leg_reads = 0
    rig.slate = POLY_SLATE_LIVE

    class Socket:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, payload):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    class Refresher(blend.LiveBlendRefresher):
        async def refresh(self, *args, **kwargs):
            return None

        async def refresh_pending(self, **kwargs):
            return None

    real_map = open_mod.open_contract_asset_map_cooperatively
    handed = []

    async def observed(market_rows, outcome_rows, *args, **kwargs):
        handed.append(outcome_rows)
        return await real_map(market_rows, outcome_rows, *args, **kwargs)

    _install(monkeypatch, rig)
    monkeypatch.setattr(websockets, "connect", lambda *args, **kwargs: Socket())
    monkeypatch.setattr(blend, "LiveBlendRefresher", Refresher)
    monkeypatch.setattr(open_mod, "open_contract_asset_map_cooperatively", observed)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 10)
    # Six leg statements: the reader must keep every chunk it digests.
    monkeypatch.setattr(open_mod, "OUTCOME_READ_MARKETS", 7)
    monkeypatch.delenv("PM_WS_PRICE_FLUSH_SECONDS", raising=False)
    monkeypatch.delenv("POLYMARKET_WS_OPEN_RECEIVER_PROCESS", raising=False)
    monkeypatch.setenv("POLYMARKET_WS_OPEN_CONTRACT_PRICES", "1")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "1")

    async def stop_after_the_first_open_read():
        await until(lambda: len(handed) >= 1)
        stop.set()

    stopper = asyncio.create_task(stop_after_the_first_open_read())
    await asyncio.wait_for(task._run_polymarket_ws_consumer(stop=stop), 5)
    await stopper
    (legs, *_later) = handed
    assert isinstance(legs, open_mod.OpenContractLegs), type(legs)
    assert rig.leg_reads == 6
    assert legs.rows == len(rig.legs) == 2 * n
    assert legs.by_market == {
        900 + i: [(9000 + 2 * i, f"0xbulk{i}_yes"), (9001 + 2 * i, f"0xbulk{i}_no")]
        for i in range(n)
    }
    assert not legs.graded
    flat = open_mod.open_contract_asset_map(rig.markets, rig.legs, set(), set(), {})
    digested = open_mod.open_contract_asset_map(rig.markets, legs, set(), set(), {})
    assert _ordered(digested) == _ordered(flat)
    assert len(flat.asset_to_outcome) == 2 * n
