"""#8466 — the Polymarket poll writer stamps, and repairs, a leg's OWN date (real Postgres).

PILLAR: TRUTH. SHIP: "US x Iran ceasefire continues through September 30?"
stops reading "Resolves Oct 31, 2026" on Discover.

The unit file proves the parser and the helper. What only Postgres can grade is
the UPSERT: the leg's insert carries its date, and the on-conflict update — which
never wrote ``resolution_date`` at all, so no re-ingest could repair a row —
now rewrites it on an open leg and leaves a settled one where it is. A session
double records the dict it was handed; it cannot say what ``ON CONFLICT DO
UPDATE`` left in the row.

The payload is Gamma's own bytes for the filed event
(``tests/fixtures/polymarket_leg_dates_8466``), driven through the REAL parser and
the REAL ``_process_event_batch``. The "legacy" rows are made by the same writer
fed the same bytes with every leg's ``endDate`` removed — the exact state
production holds, written by the shipped code path rather than seeded by hand.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8466 leg-date gate",
)

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "polymarket_leg_dates_8466"
    / "gamma-event-1038648.json"
)
EVENT_ID = "1038648"


def _utc(y, m, d):
    return datetime(y, m, d, 23, 59, tzinfo=timezone.utc)


EVENT_END = _utc(2026, 10, 31)
#: condition-id prefix → (leg, its own endDate, open at capture)
LEGS = {
    "0x7c162a2f68": ("September 20?", _utc(2026, 9, 20), False),
    "0x3ebfc39ef5": ("September 25?", _utc(2026, 9, 25), True),
    "0x690fafd3b7": ("September 30?", _utc(2026, 9, 30), True),
    "0x3738ad9665": ("October 31?", _utc(2026, 10, 31), True),
    "0xb70b8da783": ("November 30?", _utc(2026, 11, 30), True),
    "0x32851891e7": ("December 31?", _utc(2026, 12, 31), True),
}
SETTLED = "0x7c162a2f68"


def _raw() -> dict:
    return json.loads(FIXTURE.read_text())


def _without_leg_dates(raw: dict, only: str | None = None) -> dict:
    out = copy.deepcopy(raw)
    for m in out["markets"]:
        if only is None or m["conditionId"].startswith(only):
            m.pop("endDate", None)
    return out


@pytest.fixture
async def pg_engine(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    import app.tasks.base as task_base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(task_base, "DATABASE_URL", DB_URL)
    yield engine
    await engine.dispose()


async def _poll_write(raw: dict) -> None:
    """The REAL discovery-poll writer, the one that stamped the event's date."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models import FuturesMarket, FuturesOddsSnapshot, FuturesOutcome
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.polymarket import _process_event_batch
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.odds_math import probability_to_american

    class _Counting(dict):
        def __missing__(self, key):
            return 0

    stats = _Counting({"errors": []})
    event = PolymarketAPIService()._parse_event(raw)
    assert event is not None and len(event.markets) == 6
    await _process_event_batch(
        [event], stats, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot,
        pg_insert, probability_to_american, compute_market_tier,
    )
    assert not stats["errors"], stats["errors"]


async def _dates(engine) -> tuple[datetime, dict[str, tuple[datetime, str]]]:
    from sqlalchemy import text

    async with engine.connect() as conn:
        parent = (await conn.execute(text(
            "SELECT resolution_date FROM futures_markets "
            "WHERE source='polymarket' AND external_id=:eid"
        ), {"eid": EVENT_ID})).scalar_one()
        rows = (await conn.execute(text(
            "SELECT external_id, resolution_date, status FROM futures_markets "
            "WHERE source='polymarket' AND group_type='polymarket_sub_market'"
        ))).fetchall()
    legs = {r[0][:12]: (r[1], r[2]) for r in rows}
    assert set(legs) == set(LEGS), "the writer did not mint exactly the six legs"
    return parent, legs


async def test_a_first_write_stamps_every_leg_with_its_own_date(pg_engine):
    await _poll_write(_raw())
    parent, legs = await _dates(pg_engine)
    assert parent == EVENT_END, "the parent row is the event and keeps its date"
    assert {k: v[0] for k, v in legs.items()} == {k: v[1] for k, v in LEGS.items()}
    # The filed specimen, by name.
    assert legs["0x690fafd3b7"][0] == _utc(2026, 9, 30)


async def test_the_legacy_shape_is_what_the_old_stamp_wrote(pg_engine):
    """Control: without leg dates the writer falls back to the event's, which is
    production's state — every child at Oct 31. If this failed, the repair arm
    below would be repairing rows that were never wrong."""
    await _poll_write(_without_leg_dates(_raw()))
    _, legs = await _dates(pg_engine)
    assert {v[0] for v in legs.values()} == {EVENT_END}
    assert legs[SETTLED][1] == "resolved" and legs["0x690fafd3b7"][1] == "open"


async def test_a_re_ingest_repairs_every_open_leg_and_leaves_the_settled_one(pg_engine):
    await _poll_write(_without_leg_dates(_raw()))
    await _poll_write(_raw())
    _, legs = await _dates(pg_engine)
    for prefix, (name, own, is_open) in LEGS.items():
        got = legs[prefix][0]
        if is_open:
            assert got == own, f"open leg {name} was not repaired: {got}"
        else:
            assert got == EVENT_END, (
                f"settled leg {name} was rewritten to {got}; its calibration closing "
                "line was drawn against the stored date"
            )


async def test_a_leg_the_venue_serves_undated_keeps_the_date_it_has(pg_engine):
    await _poll_write(_raw())
    await _poll_write(_without_leg_dates(_raw(), only="0xb70b8da783"))
    _, legs = await _dates(pg_engine)
    assert legs["0xb70b8da783"][0] == _utc(2026, 11, 30), (
        "an absent endDate is not a claim the leg ends with its event"
    )
    assert legs["0x690fafd3b7"][0] == _utc(2026, 9, 30)
