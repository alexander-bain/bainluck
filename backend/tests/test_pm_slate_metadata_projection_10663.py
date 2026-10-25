"""#10663: the slate's market read selects four metadata keys, not the blob.

``load_game_slate`` used to select the whole ``futures_markets.market_metadata``
of every slate market and read four keys from it: the two token-array spellings,
the stored per-outcome tokens and the content-understanding label. It now
selects exactly those keys (``slate_market_stmt``) and rebuilds a dict holding
the ones present (``slate_market_rows``), so the row loop is unchanged.

The real nested loader runs here with only its database and Gamma top-ups
faked. The database answers the columns each statement actually selects over
the same STORED rows (``answer_slate_market_read``), so the blob arm and the
projected arm read identical storage and must return identical slates.
"""

import ast
import inspect
import textwrap
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.models import Event, FuturesMarket, FuturesOutcome
import app.tasks.polymarket_token_topup as topup
import app.tasks.polymarket_ws as ws
from tests._pm_slate_link_read_10663 import answer_slate_link_read
from tests._pm_slate_market_read_10663 import (
    answer_slate_market_read,
    is_slate_market_read,
)

#: Written out, not imported: a key dropped from the source must fail here.
FOUR_KEYS = (
    "clob_token_ids",
    "clobTokenIds",
    "clob_yes_token_by_outcome",
    "content_understanding_v1",
)


def label(venue_type, **extra):
    return {
        "content_understanding_v1": {
            "v": 1, "semantic_type": venue_type, "venue_type": venue_type, **extra,
        }
    }


WINNER = label("moneyline")
COMPLETED_MATCH = label("tennis_completed_match")
#: Bulk the slate never reads; it must not change any answer.
NOISE = {"polymarket_event_id": "31415", "description": "x" * 4096, "tags": [1, 2]}

#: (market_id, external_id, STORED market_metadata, event status), one per
#: behaviour in live's released packet (#10663, 2026-10-22 03:45Z).
STORED = [
    (1, "0xa01", {**WINNER, **NOISE, "clob_token_ids": ["a1", "a2"]}, "live"),
    (2, "0xa02", {"clob_token_ids": '["b1", "b2"]'}, "live"),  # JSON string
    (3, "0xa03", {"clobTokenIds": ["c1", "c2"]}, "scheduled"),  # camel only
    (4, "0xa04", {"clob_token_ids": [], "clobTokenIds": ["d1", "d2"]}, "live"),
    (5, "0xa05", {"clob_token_ids": []}, "live"),  # empty: top-up target
    (6, "0xa06", {**NOISE}, "live"),  # absent tokens, other keys present
    (7, "0xa07", None, "scheduled"),  # NULL metadata
    (8, "0xa08", {**COMPLETED_MATCH, "clob_token_ids": ["h1", "h2"]}, "live"),
    (9, "0xa09", {"content_understanding_v1": {  # unversioned: no refusal
        "semantic_type": "tennis_completed_match",
        "venue_type": "tennis_completed_match"}}, "live"),
    (10, "0xa10", {**label("tennis_completed_match", v=999)}, "live"),  # future
    (11, "917153", {**WINNER, "clob_yes_token_by_outcome": {  # parent row
        "110": "p110", "111": "p111", "bad": "pbad", "112": "", "113": None,
    }}, "live"),
    (12, "0xa12", {"clob_token_ids": "not json"}, "live"),
    (13, "0xa13", {"clob_token_ids": None, "clobTokenIds": '["m1", "m2"]'}, "live"),
    (14, "0xa14", {"clob_token_ids": ["n1", "n2"], "content_understanding_v1": None},
     "suspended"),
    (15, "0xa15", label("total"), "live"),  # labelled prop, no tokens
]

OUTCOMES = [
    (oid, mid, ext)
    for mid, cond, *_ in STORED
    if mid != 11
    for oid, ext in ((mid * 10, cond), (mid * 10 + 1, cond + "_side1"))
] + [
    (110, 11, "0xp110"), (111, 11, "0xp111"), (112, 11, "0xp112"),
    (113, 11, "0xp113"), (114, 11, "not-a-condition"),
]
SLATE = [(oid, mid, ext, dict((m[0], m[1]) for m in STORED)[mid], 900 + mid)
         for oid, mid, ext in OUTCOMES]


def blob_stmt(market_ids):
    """The parent's read, verbatim: the whole blob."""
    return (
        select(FuturesMarket.id, FuturesMarket.external_id,
               FuturesMarket.market_metadata, Event.status)
        .join(Event, FuturesMarket.event_id == Event.id)
        .where(FuturesMarket.id.in_(list(market_ids)))
    )


def real_loader(stored, **overrides):
    """The real ``load_game_slate``, its DB answering ``stored`` rows."""
    executed, calls = [], []

    class Session:
        async def execute(self, stmt):
            executed.append(stmt)
            sql = str(stmt)
            if "linked_event_id" in sql:
                rows = answer_slate_link_read(stmt, SLATE)  # #10663
            elif is_slate_market_read(stmt):
                rows = answer_slate_market_read(stmt, stored)
            elif sql.startswith("SELECT futures_outcomes.id, futures_outcomes.market_id"):
                rows = OUTCOMES
            else:  # pragma: no cover - the loader reads nothing else here
                raise AssertionError(sql)
            return SimpleNamespace(all=lambda: list(rows))

    @asynccontextmanager
    async def context():
        yield Session()

    async def market_topup(session, markets, **kwargs):
        calls.append(("market", list(markets), kwargs))
        return {mid: [f"g{mid}y", f"g{mid}n"] for mid, cond in markets if cond}

    async def outcome_topup(session, targets):
        calls.append(("outcome", list(targets)))
        return {oid: (mid, f"o{oid}") for mid, oid, ext in targets
                if topup.condition_id_of(ext)}

    source = ast.parse(
        textwrap.dedent(inspect.getsource(ws._run_polymarket_ws_consumer))
    )
    loader = next(
        n for n in source.body[0].body
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
        **overrides,
    )
    exec(compile(ast.Module(body=[loader], type_ignores=[]), "pm_slate", "exec"),
         namespace)
    return namespace["load_game_slate"], executed, calls


def market_read(executed):
    reads = [stmt for stmt in executed if is_slate_market_read(stmt)]
    assert len(reads) == 1, [str(s) for s in executed]
    return reads[0]


def selected_metadata(stmt):
    """``(bare blob selected?, [subscripted keys])`` off the compiled read."""
    bare = any(
        getattr(c, "name", None) == "market_metadata"
        and getattr(getattr(c, "table", None), "name", None) == "futures_markets"
        for c in stmt.selected_columns
    )
    compiled = stmt.compile(dialect=postgresql.dialect())
    keys = [v for k, v in compiled.params.items() if k.startswith("market_metadata")]
    return bare, keys, str(compiled)


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_live_only", [False, True])
async def test_the_real_slate_read_selects_four_keys_never_the_blob(stored_live_only):
    load, executed, _ = real_loader(STORED)
    await load(stored_live_only=stored_live_only)
    bare, keys, sql = selected_metadata(market_read(executed))
    assert not bare, sql
    assert sorted(keys) == sorted(FOUR_KEYS), sql
    columns = sql.split(" FROM ")[0]
    assert "futures_markets.market_metadata," not in columns
    assert columns.count("futures_markets.market_metadata[") == 4


def test_the_strawman_blob_read_is_what_the_guard_refuses():
    bare, keys, _ = selected_metadata(blob_stmt([1]))
    assert bare and keys == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stored_live_only", [False, True])
async def test_projected_rows_load_the_same_slate_as_the_full_blob(stored_live_only):
    projected, projected_sql, projected_calls = real_loader(STORED)
    full, full_sql, full_calls = real_loader(
        STORED, slate_market_stmt=blob_stmt, slate_market_rows=iter,
    )
    got = await projected(stored_live_only=stored_live_only)
    want = await full(stored_live_only=stored_live_only)
    assert selected_metadata(market_read(full_sql))[0]  # the arm really read blobs
    assert not selected_metadata(market_read(projected_sql))[0]
    assert got == want
    assert projected_calls == full_calls  # top-up targets and priority seats


@pytest.mark.asyncio
async def test_every_packet_behaviour_holds_on_the_projected_read():
    load, _, calls = real_loader(STORED)
    slate = await load()
    # 1. Venue label: versioned non-winner labels refuse; unversioned, future
    #    and absent labels do not.
    assert slate["non_blend_market_ids"] == {8, 15}
    # 3. Token arrays: list, JSON string, camel, `[] or camel`, null-or-camel.
    a2m = slate["asset_to_market"]
    for mid, tokens in {1: "a", 2: "b", 3: "c", 4: "d", 8: "h", 13: "m", 14: "n"}.items():
        assert a2m[f"{tokens}1"] == a2m[f"{tokens}2"] == mid
    assert slate["asset_to_outcome"]["b1"] == 20  # JSON-string tokens pair by leg
    # Empty, absent, NULL, malformed and label-only rows stream no token of
    # their own and are exactly the market top-up's targets.
    (_, missing, kwargs), *_ = calls
    assert {mid for mid, _cond in missing} == {5, 6, 7, 9, 10, 11, 12, 15}
    # 4. Live WIN priority: stored `live` and not venue-refused (8, 15);
    #    scheduled 3/7 and suspended 14 take no seat.
    assert kwargs["priority_market_ids"] == {1, 2, 4, 5, 6, 9, 10, 11, 12, 13}
    assert slate["condition_to_market"]["917153"] == 11
    assert slate["condition_to_market"]["0xa07"] == 7


@pytest.mark.asyncio
async def test_stored_outcome_tokens_skip_invalid_ids_and_empty_tokens():
    load, _, calls = real_loader(STORED)
    slate = await load(stored_live_only=True)
    assert calls == []  # the stored-live read asks Gamma nothing
    # 2. Only valid integer ids with a token, and only outcomes of the market.
    assert slate["outcome_yes_token"] == {110: "p110", 111: "p111"}
    assert slate["asset_to_outcome"]["p110"] == 110
    assert "pbad" not in slate["asset_to_market"]


def test_rebuilt_metadata_holds_only_present_keys():
    keys = ws._slate_metadata_keys()
    assert keys == FOUR_KEYS
    rows = list(ws.slate_market_rows([
        (1, "0x1", None, None, None, None, "live"),
        (2, "0x2", ["t"], None, {"5": "y"}, None, "scheduled"),
    ]))
    assert rows == [
        (1, "0x1", {}, "live"),
        (2, "0x2", {"clob_token_ids": ["t"], "clob_yes_token_by_outcome": {"5": "y"}},
         "scheduled"),
    ]
