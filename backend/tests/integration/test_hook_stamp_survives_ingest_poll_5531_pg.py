"""#5531 — a hook the writer just stamped survives the next ingest poll, and is served.

## the defect, measured on production 2026-09-25 (v5028, after PR #8487)

The first post-release `enrich_market_hooks` run (06:41Z) wrote 100 sentences, each
with ``hook_policy_version: 2`` and ``hook_probability_at_generation`` in the SAME
statement. An hour later:

    stamp kept, row untouched since      46   served on the page
    stamp LOST, row touched after write  48   withheld (43 Kalshi, 5 Polymarket)

The Kalshi and Polymarket upserts REPLACE ``market_metadata`` with a freshly built
dict and carry back exactly one key (``preserve_venue_settled``, #2222). Both hook
keys went with the rest, and ``is_hook_stale`` check 0 read the now-silent row as
policy 1 and retired a sentence whose leader had not moved (61143926 Minnesota,
61143932 Buffalo). A second clause also fired on the specimen 62013557: the writer
stores the raw venue leader ("Los Angeles D"), the serializer compared it with the
repaired display name ("Los Angeles Dodgers"), and read that as a leader change.

## why a real server for half of this file

The merge is SQL — ``jsonb_build_object`` over the EXISTING row's keys, ``||``,
``jsonb_strip_nulls``, ``NULLIF(..., '{}')``. Under a double it is a string that can
contain the right key names and still merge nothing. Every server arm runs the
PRE-#5531 expression beside the new one: a strawman that must erase the stamps, and
parity controls wherever there is no hook stamp to keep. The ``_pg`` arms feed the real
expression a JSONB literal standing in for the existing row and SELECT the result.
No tables, so it runs on the 14.x Homebrew server as well as CI's postgres:15.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.utils.futures_liveness import (
    CARRIED_METADATA_KEYS,
    VENUE_SETTLED_KEY,
    preserve_venue_settled,
)
from app.utils.hook_staleness import (
    CURRENT_HOOK_POLICY_VERSION,
    HOOK_POLICY_METADATA_KEY,
    HOOK_PROB_METADATA_KEY,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #5531 metadata merge "
        "(CI job `search-recall` provides one)"
    ),
)

#: What a Kalshi poll builds for a game market — production 62013557's keys, minus
#: the two it never knows about.
_POLL_METADATA = {
    "competition": "Pro Baseball",
    "event_title": "Los Angeles D vs San Francisco",
    "market_count": 2,
    "kalshi_event_ticker": "KXMLBGAME-26SEP252215LADSF",
}

#: The row as the hook writer left it at 06:41Z.
_STAMPED_ROW = {
    **_POLL_METADATA,
    "shape": {"v": 2, "shape": "duel"},
    HOOK_POLICY_METADATA_KEY: CURRENT_HOOK_POLICY_VERSION,
    HOOK_PROB_METADATA_KEY: 0.765,
}


class TestTheCarriedKeys:
    def test_the_hook_stamps_are_carried_by_the_names_the_checker_reads(self):
        # Imported from hook_staleness, not retyped: a renamed key on either side
        # would otherwise leave this passing while production erases the real one.
        assert HOOK_POLICY_METADATA_KEY in CARRIED_METADATA_KEYS
        assert HOOK_PROB_METADATA_KEY in CARRIED_METADATA_KEYS

    def test_CONTROL_the_venue_settled_stamp_is_still_carried(self):
        assert VENUE_SETTLED_KEY in CARRIED_METADATA_KEYS

    def test_the_merge_reads_every_carried_key_off_the_existing_row(self):
        from sqlalchemy.dialects import postgresql

        from app.models.models import FuturesMarket

        compiled = preserve_venue_settled(None, FuturesMarket.market_metadata).compile(
            dialect=postgresql.dialect()
        )
        params = set(compiled.params.values())
        for key in CARRIED_METADATA_KEYS:
            assert key in params, f"{key} is not read back from the existing row"
        assert str(compiled).count("futures_markets.market_metadata[") == len(
            CARRIED_METADATA_KEYS
        )


async def _merge(new_metadata, existing):
    """Run the real expression with ``existing`` standing in for the row's column."""
    from sqlalchemy import cast, literal, select
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.asyncio import create_async_engine

    existing_col = cast(literal(json.dumps(existing)), JSONB) if existing is not None else cast(literal(None), JSONB)
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as conn:
            value = (await conn.execute(select(preserve_venue_settled(new_metadata, existing_col)))).scalar()
    finally:
        await engine.dispose()
    return value


async def _old_merge(new_metadata, existing):
    """The pre-#5531 expression: only the venue-settled stamp was carried back."""
    from sqlalchemy import cast, func, literal, select
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.asyncio import create_async_engine

    existing_col = cast(literal(json.dumps(existing)), JSONB) if existing is not None else cast(literal(None), JSONB)
    kept = func.jsonb_strip_nulls(
        func.jsonb_build_object(VENUE_SETTLED_KEY, existing_col[VENUE_SETTLED_KEY])
    )
    old = func.nullif(
        func.coalesce(cast(new_metadata, JSONB), cast("{}", JSONB)).op("||")(kept),
        cast("{}", JSONB),
    )
    engine = create_async_engine(DB_URL)
    try:
        async with engine.connect() as conn:
            value = (await conn.execute(select(old))).scalar()
    finally:
        await engine.dispose()
    return value


@needs_postgres
@pytest.mark.asyncio
class TestTheMergeOnARealServer:
    async def test_a_poll_keeps_the_hook_stamps_it_does_not_know_about(self):
        merged = await _merge(dict(_POLL_METADATA), _STAMPED_ROW)
        assert merged[HOOK_POLICY_METADATA_KEY] == CURRENT_HOOK_POLICY_VERSION
        assert merged[HOOK_PROB_METADATA_KEY] == 0.765
        # …and the poll's own keys are what the poll sent
        for k, v in _POLL_METADATA.items():
            assert merged[k] == v

    async def test_STRAWMAN_the_old_single_key_merge_really_did_erase_them(self):
        # The rig must be able to show the defect, or the test above proves only
        # that a JSONB literal round-trips. This is the pre-#5531 expression.
        merged = await _old_merge(dict(_POLL_METADATA), _STAMPED_ROW)
        assert HOOK_POLICY_METADATA_KEY not in merged
        assert HOOK_PROB_METADATA_KEY not in merged

    @pytest.mark.parametrize(
        "new_metadata, existing",
        [
            (dict(_POLL_METADATA), dict(_POLL_METADATA)),
            (dict(_POLL_METADATA), None),
            # A poll with NO metadata: through SQLAlchemy+asyncpg a Python None cast
            # to JSONB binds as JSON `null`, so both expressions return `[null, {}]`
            # here — not the SQL NULL #2222's docstring promises. Pre-existing and
            # unreached on production (0 array-shaped kalshi/polymarket rows,
            # 2026-09-25); asserted as PARITY so this change is proven not to move it.
            (None, {"competition": "x"}),
            (None, {**_POLL_METADATA, VENUE_SETTLED_KEY: "2026-09-20T00:00:00"}),
        ],
    )
    async def test_CONTROL_with_no_hook_stamp_to_keep_the_merge_is_what_it_was(
        self, new_metadata, existing
    ):
        assert await _merge(new_metadata, existing) == await _old_merge(new_metadata, existing)

    async def test_CONTROL_absent_keys_are_not_invented(self):
        merged = await _merge(dict(_POLL_METADATA), dict(_POLL_METADATA))
        assert HOOK_POLICY_METADATA_KEY not in merged
        assert HOOK_PROB_METADATA_KEY not in merged
        assert VENUE_SETTLED_KEY not in merged

    async def test_CONTROL_the_venue_settled_stamp_still_survives(self):
        merged = await _merge(
            dict(_POLL_METADATA), {**_POLL_METADATA, VENUE_SETTLED_KEY: "2026-09-20T00:00:00"}
        )
        assert merged[VENUE_SETTLED_KEY] == "2026-09-20T00:00:00"


# --- the serializer: the leader is compared in the writer's vocabulary ----------


def _outcome(oid, external_id, name, prob):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=external_id,
        current_probability=prob,
        current_american_odds=-300,
        rank=oid,
        rank_change_24h=None,
        probability_change_24h=0.0,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=None,
    )


def _dodgers_market(hook_leader_at_generation):
    """Production 62013557 as stored at 06:41Z, stamps intact."""
    return SimpleNamespace(
        id=62013557,
        name="Los Angeles D vs San Francisco",
        description=None,
        category="sports",
        source="kalshi",
        external_id="KXMLBGAME-26SEP252215LADSF",
        status="open",
        sport=None,
        sport_id=None,
        event_id=None,
        market_type=None,
        market_tier=1,
        llm_sport_category="baseball",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=(
            "The Los Angeles Dodgers are scheduled to play against the San Francisco "
            "Giants on September 25, 2026, at 10:15 PM ET."
        ),
        hook_generated_at=datetime.now(timezone.utc) - timedelta(hours=1),
        hook_leader_at_generation=hook_leader_at_generation,
        image_url=None,
        category_tags=[],
        market_metadata={
            HOOK_POLICY_METADATA_KEY: CURRENT_HOOK_POLICY_VERSION,
            HOOK_PROB_METADATA_KEY: 0.765,
        },
        outcomes=[
            _outcome(234103403, "KXMLBGAME-26SEP252215LADSF-LAD", "Los Angeles D", 0.765),
            _outcome(234103404, "KXMLBGAME-26SEP252215LADSF-SF", "San Francisco", 0.235),
        ],
    )


class TestTheLeaderIsComparedInTheWritersVocabulary:
    def test_a_repaired_leader_name_is_not_a_leader_change(self):
        from app.routes.futures import _format_market_detail

        detail = _format_market_detail(_dodgers_market("Los Angeles D"), None, set())
        # the reader sees the repaired name…
        leader = max(detail["outcomes"], key=lambda o: o["probability"] or 0)
        assert leader["name"] == "Los Angeles Dodgers"
        # …and the sentence written about that same outcome is served
        assert detail["hook_withheld"] is False
        assert detail["hook_description"].startswith("The Los Angeles Dodgers")

    def test_CONTROL_a_real_leader_change_is_still_withheld(self):
        from app.routes.futures import _format_market_detail

        detail = _format_market_detail(_dodgers_market("San Francisco"), None, set())
        assert detail["hook_withheld"] is True
        assert detail["hook_description"] is None
