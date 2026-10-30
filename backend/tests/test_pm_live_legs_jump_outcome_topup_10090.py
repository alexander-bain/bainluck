"""#10090 Fix A: live headline legs jump the OUTCOME token top-up window.

Measured 2026-10-30: 15 of 64 live games with a Polymarket price had headline
legs with no CLOB token, because untokened prop condition ids sorting ahead of
them held the 300-id rotating window. Their moves waited 2.5-6.5 min for the
poll. The caller now names its live WIN markets; their legs are asked first,
outside the window's cap, under a cap of their own.
"""

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
from tests._pm_slate_market_read_10663 import answer_slate_market_read

LIVE_MARKET = 1
PROP_MARKET = 2
#: One live game's three-way moneyline: three legs, each its own condition id,
#: sorting AFTER every prop below.
LIVE_LEGS = [(LIVE_MARKET, 10 + i, f"0xf{i:063d}") for i in range(3)]
#: 400 untokened prop condition ids, all lexicographically ahead of the legs.
PROPS = [(PROP_MARKET, 1000 + i, f"0x0{i:063d}") for i in range(400)]


class Gamma:
    def __init__(self, missing=()):
        self.asked: list[list[str]] = []
        # An empty 200 for these ids: how a closed or unknown market answers.
        self.missing = set(missing)

    async def get_markets_by_conditions(self, ids, **_kw):
        self.asked.append(list(ids))
        return [
            SimpleNamespace(
                condition_id=cid,
                clob_token_ids=[cid + "-yes", cid + "-no"],
                outcomes=["Yes", "No"],
            )
            for cid in ids
            if cid not in self.missing
        ]

    async def close(self):
        pass


class Session:
    """Stored-metadata read (nothing stored, nothing stale), then names."""

    def __init__(self):
        self.updates = []

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.updates.append(stmt)
        return SimpleNamespace(all=lambda: [])


@pytest.fixture
def cursor(monkeypatch):
    store = {"value": None, "saves": []}

    async def load():
        return store["value"]

    async def save(value):
        store["saves"].append(value)
        if value:
            store["value"] = value

    async def no_rest():
        return set()

    async def rest(_cids):
        pass

    monkeypatch.setattr(topup, "load_topup_cursor", load)
    monkeypatch.setattr(topup, "save_topup_cursor", save)
    # The resting memory (#10090 follow-up) has its own file; these cases pin
    # Fix A's seat order with nothing resting.
    monkeypatch.setattr(topup, "load_priority_misses", no_rest)
    monkeypatch.setattr(topup, "save_priority_misses", rest)
    return store


def asked_live(gamma: Gamma, call: int = 0) -> set[str]:
    live = {cid for _m, _o, cid in LIVE_LEGS}
    return live & set(gamma.asked[call])


async def test_master_shape_asks_no_live_leg_when_props_sort_ahead(cursor):
    """Control: without a priority set the window is the props' and only theirs."""
    gamma = Gamma()
    await topup.topup_outcome_clob_tokens(Session(), PROPS + LIVE_LEGS, service=gamma)
    assert len(gamma.asked[0]) == 300
    assert asked_live(gamma) == set()


async def test_live_legs_are_all_asked_on_the_first_pass(cursor, caplog):
    gamma = Gamma()
    with caplog.at_level("INFO"):
        filled = await topup.topup_outcome_clob_tokens(
            Session(),
            PROPS + LIVE_LEGS,
            service=gamma,
            priority_market_ids={LIVE_MARKET},
        )
    assert len(gamma.asked) == 1
    assert asked_live(gamma) == {cid for _m, _o, cid in LIVE_LEGS}
    # Ahead of the window, so they ride Gamma's first batch of 40.
    assert gamma.asked[0][:3] == [cid for _m, _o, cid in LIVE_LEGS]
    # The window still gets its full 300 after them.
    assert len(gamma.asked[0]) == 303
    for _mid, oid, cid in LIVE_LEGS:
        assert filled[oid] == (LIVE_MARKET, cid + "-yes")
    assert any(
        "live_legs_asked=3 live_legs_tokened=3" in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


async def test_the_log_counts_only_the_live_legs_gamma_tokened(cursor, caplog):
    gamma = Gamma(missing={LIVE_LEGS[0][2]})
    with caplog.at_level("INFO"):
        await topup.topup_outcome_clob_tokens(
            Session(),
            PROPS + LIVE_LEGS,
            service=gamma,
            priority_market_ids={LIVE_MARKET},
        )
    assert any(
        "live_legs_asked=3 live_legs_tokened=2" in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


async def test_the_rotating_window_still_advances_past_the_priority_set(cursor):
    gamma = Gamma()
    for _ in range(2):
        await topup.topup_outcome_clob_tokens(
            Session(),
            PROPS + LIVE_LEGS,
            service=gamma,
            priority_market_ids={LIVE_MARKET},
        )
    props = [cid for _m, _o, cid in PROPS]
    first, second = (call[3:] for call in gamma.asked)
    assert first == props[:300]
    assert second == props[300:] + props[:200]
    # The cursor is the window's own: a live leg never becomes its position.
    assert cursor["saves"] == [props[299], props[199]]


async def test_the_priority_cap_holds_and_overflow_joins_the_window(cursor, caplog):
    gamma = Gamma()
    flood = [(LIVE_MARKET, 5000 + i, f"0xe{i:063d}") for i in range(250)]
    with caplog.at_level("WARNING"):
        for _ in range(2):
            await topup.topup_outcome_clob_tokens(
                Session(),
                PROPS + flood,
                service=gamma,
                max_priority=200,
                priority_market_ids={LIVE_MARKET},
            )
    flood_ids = [cid for _m, _o, cid in flood]
    for asked in gamma.asked:
        assert asked[:200] == flood_ids[:200]
        assert len(asked) == 200 + 300
    # The 50 over the cap compete in the window instead of vanishing: they sort
    # after the props, so the window's second turn reaches them.
    assert set(flood_ids[200:]).isdisjoint(gamma.asked[0])
    assert set(flood_ids[200:]) <= set(gamma.asked[1][200:])
    assert any("priority cap of 200" in r.getMessage() for r in caplog.records)


async def test_the_default_priority_cap_is_200():
    assert topup.MAX_PRIORITY_OUTCOME_CONDITIONS == 200
    params = inspect.signature(topup.topup_outcome_clob_tokens).parameters
    assert params["max_priority"].default == 200


async def test_the_catalog_refresh_passes_its_live_win_markets(monkeypatch):
    """Execute the real slate loader; the outcome top-up gets live WIN ids."""
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
        (1, "31415", winner, "scheduled"),
        (2, "31416", prop, "live"),
        (3, "31417", {}, "live"),
        (4, "31418", winner, "live"),
    ]
    outcomes = [(mid * 10, mid, f"0x{mid:03d}") for mid, *_ in markets]
    slate_rows = [
        (oid, mid, ext, dict((m[0], m[1]) for m in markets)[mid], 100 + mid)
        for oid, mid, ext in outcomes
    ]

    class SlateSession:
        def __init__(self, batches):
            self.batches = iter(batches)

        async def execute(self, stmt):
            rows = answer_slate_market_read(stmt, next(self.batches))
            return SimpleNamespace(all=lambda: rows)

    session = SlateSession([slate_rows, markets, outcomes])
    calls = []

    @asynccontextmanager
    async def context():
        yield session

    async def market_topup(*_a, **_k):
        return {}

    async def outcome_topup(session, targets, **kwargs):
        calls.append((list(targets), kwargs))
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
        topup_clob_tokens=market_topup,
        topup_outcome_clob_tokens=outcome_topup,
        condition_id_of=topup.condition_id_of,
    )
    exec(
        compile(ast.Module(body=[loader], type_ignores=[]), "pm_slate", "exec"),
        namespace,
    )
    await namespace["load_game_slate"]()
    assert len(calls) == 1
    targets, kwargs = calls[0]
    assert {mid for mid, _oid, _ext in targets} == {1, 2, 3, 4}
    assert set(kwargs["priority_market_ids"]) == {3, 4}
