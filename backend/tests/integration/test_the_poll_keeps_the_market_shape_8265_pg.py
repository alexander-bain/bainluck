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
