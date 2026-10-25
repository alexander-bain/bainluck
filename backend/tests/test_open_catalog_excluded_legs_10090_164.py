"""The open-contract read never fetches legs of markets the game arm owns. #10090 attempt164.

Polymarket's open-contract arm (#9484) reads every unsettled market, then every
leg of those markets, and only then `open_contract_asset_map` skips the markets
the game slate already owns (`excluded_market_ids`). On the reviewed fixture
that read 28,600 legs to admit 4,000: 12,300 game-owned ids were requested and
then discarded, on the restart path that holds open-market prices back.

The correction drops excluded markets from the LEG read only. Market rows are
still read whole (the counts and the event bridge use them) and the mapper
still receives `excluded_market_ids`, so the admission must be identical.

The loader is a closure inside the socket coroutine, so this runs its exact
source (extracted by AST) with only `get_task_session` swapped for a counting
fake that serves rows from memory.
"""

from __future__ import annotations

import ast
import inspect
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

import pytest

from app.tasks import polymarket_open_contracts as catalog
from app.tasks import polymarket_ws as task
from app.tasks.ws_open_contracts import (
    open_contract_bridge_event_stmt,
    open_contract_event_bridge,
)

GAME = range(1, 31)      # markets the game arm owns
OPEN = range(31, 41)     # markets only the open arm can admit


def _market_rows():
    # (market_id, clob_token_ids, clobTokenIds, clob_yes_token_by_outcome,
    #  event_id, name, external_id) — `open_contract_markets_stmt`'s shape.
    rows = [(m, [f"{m}01", f"{m}02"], None, None, None, f"M{m}", f"x{m}") for m in (*GAME, *OPEN)]
    # An open market whose tokens are the game arm's mirrors them.
    rows.append((41, ["101", "102"], None, None, None, "M41", "x41"))
    # A tokenless open market mirrors the game leg by exact condition.
    rows.append((42, None, None, None, None, "M42", "x42"))
    return rows


def _legs(market_id):
    # (outcome_id, market_id, external_id, graded) — `open_contract_outcomes_stmt`.
    cond = "0x00000001" if market_id in (1, 41, 42) else f"0x{market_id:08x}"
    return [
        (market_id * 2, market_id, cond, False),
        (market_id * 2 + 1, market_id, cond + "_side1", market_id == 35),
    ]


def _loader(requested):
    src = inspect.getsource(task)
    node = next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "read_open_contracts"
    )
    rows = _market_rows()

    class _Result:
        def __init__(self, found):
            self._found = found

        def all(self):
            return self._found

    class _Session:
        async def execute(self, stmt, *args, **kwargs):
            ids = stmt.compile().params.get("market_ids")
            if ids is None:
                return _Result(rows)
            requested.append(list(ids))
            return _Result([leg for m in ids for leg in _legs(m)])

    @asynccontextmanager
    async def session():
        yield _Session()

    ns = {k: getattr(catalog, k) for k in dir(catalog)}
    ns.update(
        logger=logging.getLogger("catalog164"),
        open_contract_bridge_event_stmt=open_contract_bridge_event_stmt,
        open_contract_event_bridge=open_contract_event_bridge,
        open_contract_prices_enabled=lambda: True,
        get_task_session=session,
    )
    exec(compile(ast.get_source_segment(src, node), inspect.getfile(task), "exec"), ns)
    return ns["read_open_contracts"]


def _unfiltered_admission(excluded, taken, contracts):
    """The admission from reading EVERY market's legs (the pre-164 read)."""
    rows = _market_rows()
    legs = [leg for r in rows for leg in _legs(r[0])]
    return catalog.open_contract_asset_map(rows, legs, taken, excluded, contracts)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "excluded",
    [
        pytest.param(set(GAME), id="game-slate"),
        pytest.param(set(), id="no-exclusions"),
        pytest.param({r[0] for r in _market_rows()}, id="all-excluded"),
    ],
)
async def test_excluded_legs_are_not_read_and_admission_is_identical(excluded):
    requested: list[list[int]] = []
    taken = {"101", "102"} if excluded else set()
    contracts = {"0x00000001:0": "101", "0x00000001:1": "102"} if excluded else {}
    admission, failed, _bridge, bridge_failed = await _loader(requested)(
        taken, excluded, contracts
    )
    assert not failed and not bridge_failed

    asked = {m for ids in requested for m in ids}
    assert not asked & excluded, "game-owned legs were read then discarded"
    assert asked == {r[0] for r in _market_rows()} - excluded

    assert asdict(admission) == asdict(_unfiltered_admission(excluded, taken, contracts))
    assert admission.counts["markets"] == len(_market_rows())
    assert admission.counts["markets_on_game_slate"] == len(excluded)
