"""#8265 — an ingest poll keeps the board's ``shape``, so the proved-field arms can run.

## the defect, measured on production 2026-10-03

After #10348 the 2-hourly Kalshi poll took the volume reading on every leg it
touched. The 20:45Z run did exactly that: all 25 ``KXATP-27USO`` legs read
``volume_24h 0.00`` with ``volume_24h_at == last_updated`` to the microsecond
(20:58:38.618739Z) on every priced leg. ``/api/futures/61308736`` still served
"Jakub Mensik leads at 47%" with ``prices_withheld: 0``.

The board's ``market_metadata`` was ``{competition, event_title, market_count,
kalshi_event_ticker}`` and nothing else. The same poll REPLACES that column with
the dict it builds and carries back only ``CARRIED_METADATA_KEYS``. ``shape``,
the contract ``backfill_market_shapes`` merges in, was not one of them, so
``market_is_proved_exclusive_field`` failed closed and the sixth arm never ran.
Open tier<=2 Kalshi boards, 21:05Z: all 52 polled in the last 150 minutes had no
``shape``; all 6,769 not polled had one.

## why a real server for half of this file

Same reason as #5531's file: the merge is SQL (``jsonb_build_object`` over the
EXISTING row's keys, ``||``, ``jsonb_strip_nulls``), so under a double it is a
string that can name the right key and merge nothing. Each server arm runs the
pre-#8265 expression beside the new one, and the merged JSON is handed to the
real gate and the real route helper. No tables, so PG 14 runs it as well as CI's 15.
"""

import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects.postgresql import JSONB as JSONB_TYPE

from app.tasks.polymarket_open_contracts import open_contract_asset_map
from app.tasks.polymarket_token_topup import OUTCOME_TOKEN_METADATA_KEY
from app.utils.futures_liveness import (
    CARRIED_METADATA_KEYS,
    MARKET_SHAPE_METADATA_KEY,
    VENUE_SETTLED_KEY,
    preserve_venue_settled,
)
from app.utils.futures_unsupported_price import market_is_proved_exclusive_field
from app.utils.hook_staleness import HOOK_POLICY_METADATA_KEY, HOOK_PROB_METADATA_KEY

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8265 metadata merge "
        "(CI job `search-recall` provides one)"
    ),
)

#: What the Kalshi poll builds for 61308736, read off production 2026-10-03.
_POLL_METADATA = {
    "competition": "2027 US Open Men's Singles",
    "event_title": "2027 US Open Men's Singles Winner",
    "market_count": 25,
    "kalshi_event_ticker": "KXATP-27USO",
}

#: The fields of the v2 contract the gate reads, as the backfill writes them.
_SHAPE = {
    "v": 2,
    "shape": "field",
    "outcome_relation": "competitors",
    "exhaustive": True,
    "expected_winners": 1,
}

#: The row as the backfill left it, before the poll reached it.
_CLASSIFIED_ROW = {**_POLL_METADATA, MARKET_SHAPE_METADATA_KEY: _SHAPE}

#: The keys carried before this change, for the strawman.
_PRE_8265_KEYS = (VENUE_SETTLED_KEY, HOOK_POLICY_METADATA_KEY, HOOK_PROB_METADATA_KEY)


class TestTheCarriedKey:
    def test_the_shape_is_carried(self):
        assert MARKET_SHAPE_METADATA_KEY in CARRIED_METADATA_KEYS

    def test_the_carried_name_is_the_one_the_gate_reads(self):
        # Fed through the gate rather than compared to a retyped "shape": a
        # rename on either side would otherwise leave this green while
        # production erases the real key.
        assert market_is_proved_exclusive_field(
            "field", {MARKET_SHAPE_METADATA_KEY: dict(_SHAPE)}
        )

    def test_CONTROL_the_earlier_carried_keys_are_still_carried(self):
        for key in _PRE_8265_KEYS:
            assert key in CARRIED_METADATA_KEYS

    def test_the_merge_reads_the_shape_off_the_existing_row(self):
        from sqlalchemy.dialects import postgresql

        from app.models.models import FuturesMarket

        compiled = preserve_venue_settled(None, FuturesMarket.market_metadata).compile(
            dialect=postgresql.dialect()
        )
        assert MARKET_SHAPE_METADATA_KEY in set(compiled.params.values())


async def _select(expr):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(select(expr))).scalar()
    finally:
        await engine.dispose()


def _existing(existing):
    from sqlalchemy import cast, literal
    from sqlalchemy.dialects.postgresql import JSONB

    return cast(literal(json.dumps(existing)), JSONB)


async def _merge(new_metadata, existing):
    """The real expression, with ``existing`` standing in for the row's column."""
    return await _select(preserve_venue_settled(new_metadata, _existing(existing)))


async def _old_merge(new_metadata, existing):
    """The pre-#8265 expression: the same merge over the keys carried before."""
    from sqlalchemy import cast, func
    from sqlalchemy.dialects.postgresql import JSONB

    col = _existing(existing)
    kept = func.jsonb_strip_nulls(
        func.jsonb_build_object(*(a for k in _PRE_8265_KEYS for a in (k, col[k])))
    )
    return await _select(
        func.nullif(
            func.coalesce(cast(new_metadata, JSONB), cast("{}", JSONB)).op("||")(kept),
            cast("{}", JSONB),
        )
    )


@needs_postgres
@pytest.mark.asyncio
class TestTheMergeOnARealServer:
    async def test_a_poll_keeps_the_shape_and_the_board_stays_a_proved_field(self):
        merged = await _merge(dict(_POLL_METADATA), _CLASSIFIED_ROW)
        assert merged[MARKET_SHAPE_METADATA_KEY] == _SHAPE
        for k, v in _POLL_METADATA.items():
            assert merged[k] == v
        assert market_is_proved_exclusive_field("field", merged)

    async def test_STRAWMAN_the_old_merge_erased_it_and_the_gate_failed_closed(self):
        # The rig must be able to show the defect: this is production's
        # 61308736 metadata at 21:05Z, byte for byte in keys.
        merged = await _old_merge(dict(_POLL_METADATA), _CLASSIFIED_ROW)
        assert merged == _POLL_METADATA
        assert not market_is_proved_exclusive_field("field", merged)

    async def test_CONTROL_an_unclassified_board_is_not_given_a_shape(self):
        merged = await _merge(dict(_POLL_METADATA), dict(_POLL_METADATA))
        assert MARKET_SHAPE_METADATA_KEY not in merged
        assert not market_is_proved_exclusive_field("field", merged)

    @pytest.mark.parametrize(
        "new_metadata, existing",
        [
            (dict(_POLL_METADATA), dict(_POLL_METADATA)),
            (dict(_POLL_METADATA), {**_POLL_METADATA, VENUE_SETTLED_KEY: "2026-10-01T00:00:00"}),
            (None, {"competition": "x"}),
        ],
    )
    async def test_CONTROL_with_no_shape_to_keep_the_merge_is_what_it_was(
        self, new_metadata, existing
    ):
        assert await _merge(new_metadata, existing) == await _old_merge(new_metadata, existing)


# --- the reader: the merged row reaches the sixth arm --------------------------

_TOUCH = datetime(2026, 10, 3, 20, 58, 38, 618739, tzinfo=timezone.utc)


def _leg(oid, name, prob, ask):
    """A leg as 61308736 stored it at 21:00Z: no bid, a fresh zero volume."""
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=prob,
        current_yes_bid=0.0,
        current_yes_ask=ask,
        resolution_source=None,
        is_winner=None,
        volume_24h=0.0,
        volume_24h_at=_TOUCH,
        last_updated=_TOUCH,
    )


def _board(metadata):
    return SimpleNamespace(
        source="kalshi",
        market_type="field",
        market_metadata=metadata,
        outcomes=[
            _leg(230781795, "Jakub Mensik", 0.47, 0.47),
            _leg(230781780, "Carlos Alcaraz", 0.05, 0.46),
            _leg(230781797, "Casper Ruud", 0.03, 0.50),
        ],
    )


@needs_postgres
@pytest.mark.asyncio
class TestTheBoardAfterAPoll:
    async def test_the_specimen_board_withholds_its_unsupported_head(self):
        from app.routes.futures import _unsupported_head_outcome_ids

        merged = await _merge(dict(_POLL_METADATA), _CLASSIFIED_ROW)
        assert _unsupported_head_outcome_ids(_board(merged), set()) == {
            230781795,
            230781780,
            230781797,
        }

    async def test_STRAWMAN_after_the_old_merge_the_arm_withheld_nothing(self):
        from app.routes.futures import _unsupported_head_outcome_ids

        merged = await _old_merge(dict(_POLL_METADATA), _CLASSIFIED_ROW)
        assert _unsupported_head_outcome_ids(_board(merged), set()) == set()


# --- #10090: the Polymarket poll keeps a parent's outcome-token map ------------
#
# Same REPLACE, a different key. `topup_outcome_clob_tokens` stamps
# `clob_yes_token_by_outcome` on a game's moneyline parent; the socket reads it
# to put the headline legs on the live connection. The hourly poll's
# `_process_event_batch` rebuilt the parent's metadata without it. Production
# 2026-10-30: six live games read `all_legs` at 21:20Z and `no_tokens` after
# the 21:54:45Z poll (`updated_at` 21:54:45-49Z on all six, key absent).
#
# The clause under test is the one the REAL writer emits: the sunk-recovery pass
# from #8373's rig drives `_process_event_batch` (the hourly poll's writer) over
# Gamma's own bytes for event 1058697, and the server runs that clause against a
# seeded row in a temp `futures_markets` (which shadows any real one).

#: The keys carried before #10090, for the strawman.
_PRE_10090_KEYS = _PRE_8265_KEYS + (MARKET_SHAPE_METADATA_KEY,)

_PARENT_ID = 61799932  # the #8373 specimen's parent row
_CUBS, _RED_SOX = 230900001, 230900002
_TOKEN_MAP = {str(_CUBS): "7101", str(_RED_SOX): "7102"}

#: The parent as the outcome top-up left it, before the poll reached it.
_TOPPED_UP_PARENT = {
    "polymarket_event_id": "1058697",
    "event_title": "Chicago Cubs vs. Boston Red Sox",
    "venue_game_start": "2026-09-27T19:05:00+00:00",
    OUTCOME_TOKEN_METADATA_KEY: dict(_TOKEN_MAP),
}


async def _real_poll_clause(monkeypatch):
    from tests.test_polymarket_sunk_open_events_6758 import _parent_update_set, _Row
    from tests.test_polymarket_sunk_unlinked_game_arm_8373 import SPECIMEN, _run

    _st, writer, *_ = await _run(monkeypatch, unlinked=[_Row(_PARENT_ID, SPECIMEN)])
    return _parent_update_set(writer, SPECIMEN)["market_metadata"]


async def _run_over_seeded_row(expr, existing):
    """``expr`` evaluated against one seeded row, as ON CONFLICT would see it."""
    from sqlalchemy import column, insert, select, table, text
    from sqlalchemy.ext.asyncio import create_async_engine

    seeded = table("futures_markets", column("id"), column("market_metadata", JSONB_TYPE))
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as conn:
            await conn.execute(text(
                "CREATE TEMP TABLE futures_markets (id integer, market_metadata jsonb)"
            ))
            await conn.execute(
                insert(seeded).values(id=_PARENT_ID, market_metadata=existing)
            )
            return (await conn.execute(select(expr))).scalar()
    finally:
        await engine.dispose()


def _with_keys(expr_keys, new_metadata, col):
    """The merge over ``expr_keys`` — the shape of every past carried list."""
    from sqlalchemy import cast, func
    from sqlalchemy.dialects.postgresql import JSONB

    kept = func.jsonb_strip_nulls(
        func.jsonb_build_object(*(a for k in expr_keys for a in (k, col[k])))
    )
    return func.nullif(
        func.coalesce(cast(new_metadata, JSONB), cast("{}", JSONB)).op("||")(kept),
        cast("{}", JSONB),
    )



def _subscribed(metadata, legs=((_CUBS, "c-cubs"), (_RED_SOX, "c-sox"))):
    """What the open-contract socket subscribes for this parent's two legs."""
    meta = metadata or {}
    admission = open_contract_asset_map(
        [(
            _PARENT_ID,
            meta.get("clob_token_ids"),
            meta.get("clobTokenIds"),
            meta.get(OUTCOME_TOKEN_METADATA_KEY),
            15331415,
            "Chicago Cubs vs. Boston Red Sox",
            "1058697",
        )],
        [(oid, _PARENT_ID, ext, False) for oid, ext in legs],
    )
    return admission.asset_to_outcome, admission.counts


class TestTheOutcomeTokenMapIsCarried:
    def test_the_map_is_carried(self):
        assert OUTCOME_TOKEN_METADATA_KEY in CARRIED_METADATA_KEYS

    def test_the_carried_name_is_the_one_the_socket_reads(self):
        # Through the reader, not a retyped string: a rename on either side
        # would otherwise leave this green while production erases the key.
        assets, _ = _subscribed({OUTCOME_TOKEN_METADATA_KEY: dict(_TOKEN_MAP)})
        assert assets == {"7101": _CUBS, "7102": _RED_SOX}

    def test_CONTROL_the_earlier_carried_keys_are_still_carried(self):
        for key in _PRE_10090_KEYS:
            assert key in CARRIED_METADATA_KEYS

    async def test_the_polymarket_writers_clause_reads_the_map_off_the_existing_row(
        self, monkeypatch
    ):
        from sqlalchemy.dialects import postgresql

        expr = await _real_poll_clause(monkeypatch)
        params = expr.compile(dialect=postgresql.dialect()).params
        assert OUTCOME_TOKEN_METADATA_KEY in set(
            v for v in params.values() if isinstance(v, str)
        ), "the poll's ON CONFLICT clause REPLACES the outcome-token map"


@needs_postgres
@pytest.mark.asyncio
class TestThePollKeepsTheMapOnARealServer:
    async def test_the_real_poll_clause_keeps_the_map_and_the_legs_stay_subscribed(
        self, monkeypatch
    ):
        expr = await _real_poll_clause(monkeypatch)
        merged = await _run_over_seeded_row(expr, dict(_TOPPED_UP_PARENT))
        assert merged[OUTCOME_TOKEN_METADATA_KEY] == _TOKEN_MAP
        # The poll's own fresh keys still win: the moved start replaced the
        # stored one (#8373's ship rides the same write).
        assert merged["venue_game_start"].startswith("2026-09-25T17:05")
        assets, _ = _subscribed(merged)
        assert assets == {"7101": _CUBS, "7102": _RED_SOX}

    async def test_STRAWMAN_the_pre_10090_clause_erased_it_and_no_leg_was_subscribed(self):
        from sqlalchemy import column, table

        col = table("futures_markets", column("market_metadata", JSONB_TYPE)).c.market_metadata
        merged = await _run_over_seeded_row(
            _with_keys(_PRE_10090_KEYS, {"polymarket_event_id": "1058697"}, col),
            dict(_TOPPED_UP_PARENT),
        )
        assert OUTCOME_TOKEN_METADATA_KEY not in merged
        assets, counts = _subscribed(merged)
        assert assets == {}
        assert counts["markets_without_tokens"] == 1

    async def test_CONTROL_a_parent_never_topped_up_is_not_given_a_map(self, monkeypatch):
        expr = await _real_poll_clause(monkeypatch)
        bare = {k: v for k, v in _TOPPED_UP_PARENT.items() if k != OUTCOME_TOKEN_METADATA_KEY}
        merged = await _run_over_seeded_row(expr, bare)
        assert OUTCOME_TOKEN_METADATA_KEY not in merged

    async def test_a_duel_keeps_the_fresh_market_tokens_and_the_socket_still_pairs_by_them(self):
        # A one-market event's parent gets Gamma's own `clob_token_ids` from the
        # poll. A map carried beside it changes nothing: the socket pairs by the
        # market's tokens whenever their count equals its leg count, and reads
        # the map only otherwise — the precedence this change keeps.
        fresh = {"polymarket_event_id": "1058697", "clob_token_ids": ["9001", "9002"]}
        existing = {**_TOPPED_UP_PARENT, "clob_token_ids": ["8001", "8002"]}
        merged = await _merge(fresh, existing)
        assert merged["clob_token_ids"] == ["9001", "9002"]
        assert merged[OUTCOME_TOKEN_METADATA_KEY] == _TOKEN_MAP
        assets, _ = _subscribed(merged)
        assert assets == {"9001": _CUBS, "9002": _RED_SOX}
