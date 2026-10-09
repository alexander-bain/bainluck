"""#10090: live WIN token recovery advances under a held metadata-request cap."""

import ast
import inspect
import textwrap
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.sql.dml import Update

from app.models.models import Event, FuturesMarket, FuturesOutcome
import app.tasks.polymarket_token_topup as topup
import app.tasks.polymarket_ws as ws


class Service:
    def __init__(self, *, fail=False):
        self.asked = []
        self.fail = fail

    async def get_markets_by_conditions(self, ids):
        self.asked.append(ids)
        if self.fail:
            raise RuntimeError("Gamma unavailable")
        return [
            SimpleNamespace(
                condition_id=cid, clob_token_ids=[cid + "-yes", cid + "-no"]
            )
            for cid in ids
            if cid.startswith("0xf")
        ]


class Session:
    def __init__(self, batches=()):
        self.batches = iter(batches)
        self.updates = []

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates.append(stmt)
            rows = []
        else:
            rows = next(self.batches)
        return SimpleNamespace(all=lambda: rows)


@pytest.fixture
def positions(monkeypatch):
    saved = {}
    monkeypatch.setattr(topup, "_read_cursor_sync", lambda key: saved.get(key))
    monkeypatch.setattr(
        topup, "_write_cursor_sync", lambda cursor, key: saved.__setitem__(key, cursor)
    )
    return saved


async def test_real_slate_prioritizes_live_win_and_keeps_both_token_orientations(
    positions,
):
    """Execute the real nested slate loader; fake only DB, Gamma and held cap."""
    winner = {
        "content_understanding_v1": {
            "v": 1,
            "semantic_type": "moneyline",
            "venue_type": "moneyline",
        }
    }
    prop = {
        "content_understanding_v1": {
            "v": 1,
            "semantic_type": "total",
            "venue_type": "total",
        }
    }
    markets = [
        (1, "0x001", winner, "scheduled"),
        (2, "0x002", prop, "live"),
        (3, "0xffe", {}, "live"),  # unknown label keeps existing WIN eligibility
        (4, "0xfff", winner, "live"),
    ]
    outcomes = [(mid * 10, mid, cid + "_side1") for mid, cid, *_ in markets]
    outcomes += [(mid * 10 + 1, mid, cid) for mid, cid, *_ in markets]
    slate_rows = [
        (oid, mid, ext, dict((m[0], m[1]) for m in markets)[mid], 100 + mid)
        for oid, mid, ext in outcomes
    ]
    session = Session([slate_rows, markets, outcomes])
    service = Service()

    @asynccontextmanager
    async def context():
        yield session

    async def capped(session, markets, **kwargs):
        return await topup.topup_clob_tokens(
            session, markets, service=service, max_markets=2, **kwargs
        )

    async def outcome_topup(*args):
        return {}

    source = ast.parse(
        textwrap.dedent(inspect.getsource(ws._run_polymarket_ws_consumer))
    )
    loader = next(
        n
        for n in source.body[0].body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "load_game_slate"
    )
    namespace = dict(
        vars(ws),
        select=select,
        Event=Event,
        FuturesMarket=FuturesMarket,
        FuturesOutcome=FuturesOutcome,
        get_task_session=context,
        topup_clob_tokens=capped,
        topup_outcome_clob_tokens=outcome_topup,
    )
    exec(
        compile(ast.Module(body=[loader], type_ignores=[]), "real_pm_slate", "exec"),
        namespace,
    )
    loaded = await namespace["load_game_slate"]()
    assert service.asked == [["0xffe", "0xfff"]]
    assert loaded["market_ids"] == {1, 2, 3, 4}  # no subscription scope removal
    assert loaded["non_blend_market_ids"] == {2}
    assert loaded["asset_to_outcome"]["0xfff-yes"] == 41
    assert loaded["asset_to_outcome"]["0xfff-no"] == 40
    assert len(session.updates) == 2


async def test_unfillable_live_conditions_rotate_before_lower_priority(positions):
    service, session = Service(), Session()
    markets = [(1, "0x001"), (2, "0x002"), (3, "0xfff"), (4, "0x000")]
    for _ in range(3):
        await topup.topup_clob_tokens(
            session,
            markets,
            service=service,
            max_markets=1,
            priority_market_ids={1, 2, 3},
        )
    assert service.asked == [["0x001"], ["0x002"], ["0xfff"]]
    assert len(session.updates) == 1
    assert all(key.endswith(":live_win") for key in positions)


async def test_lower_priority_continuation_uses_remaining_seats(positions):
    service, session = Service(), Session()
    markets = [(1, "0xfff"), (2, "0x001"), (3, "0x002"), (4, "0x003")]
    for _ in range(3):
        await topup.topup_clob_tokens(
            session, markets, service=service, max_markets=2, priority_market_ids={1}
        )
    assert service.asked == [["0xfff", "0x001"], ["0xfff", "0x002"], ["0xfff", "0x003"]]
    assert set(positions) == {topup.MARKET_TOPUP_CURSOR_KEY + ":other"}


async def test_gamma_failure_advances_live_window_and_still_raises(positions):
    service, session = Service(fail=True), Session()
    markets = [(1, "0x001"), (2, "0xfff")]
    with pytest.raises(RuntimeError, match="Gamma unavailable"):
        await topup.topup_clob_tokens(
            session, markets, service=service, max_markets=1, priority_market_ids={1, 2}
        )
    service.fail = False
    assert await topup.topup_clob_tokens(
        session, markets, service=service, max_markets=1, priority_market_ids={1, 2}
    ) == {2: ["0xfff-yes", "0xfff-no"]}
    assert service.asked == [["0x001"], ["0xfff"]]


async def test_unaddressable_parent_cannot_take_live_seat(positions):
    service, session = Service(), Session()
    filled = await topup.topup_clob_tokens(
        session,
        [(1, "31415"), (2, "0xfff")],
        service=service,
        max_markets=1,
        priority_market_ids={1},
    )
    assert service.asked == [["0xfff"]]
    assert filled == {2: ["0xfff-yes", "0xfff-no"]}
