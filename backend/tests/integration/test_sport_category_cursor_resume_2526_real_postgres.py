"""#2526 — the sport-category rail's cursor, resumed against real Postgres.

The rail prints ``next_cursor.after_date`` as an ISO string and the dispatcher
hands that same string back on the next call. asyncpg binds
``CAST(:after_date AS timestamptz)`` as a TYPED parameter and refuses a ``str``,
so on production (2026-09-24 00:40Z) every page after the first failed with
"expected a datetime.date or datetime.datetime instance, got 'str'" — reported
by the rail as a SELECT timeout. No drain of this rail had ever reached page
two. Every unit guard runs a recording session, which accepts any Python type;
this file is the one place the bind meets the driver that refused it.

Three resolved table-tennis events, one per page (``limit=1``), walked with the
cursor exactly as the rail emitted it. The venue answers table tennis for all
three, so nothing is written and the walk is the whole assertion.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #2526 cursor-resume gate "
            "against real Postgres (CI job `search-recall` provides one)"
        ),
    ),
]

UTC = timezone.utc

#: (Gamma event id, anchor market id, commence_time), newest first — the rail's order.
EVENTS = (
    ("925261", 72526003, datetime(2026, 9, 2, 12, 0, tzinfo=UTC)),
    ("943345", 72526002, datetime(2026, 8, 31, 18, 55, 34, tzinfo=UTC)),
    ("901234", 72526001, datetime(2026, 8, 20, 9, 30, tzinfo=UTC)),
)


SECOND_MARKET = 72526012


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture
async def session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import FuturesMarket
    from app.services.database import Base

    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for event_id, market_id, commence in EVENTS:
            s.add(
                FuturesMarket(
                    id=market_id,
                    source="polymarket",
                    external_id=f"0x2526{market_id}",
                    name=f"Table tennis match {event_id}",
                    status="resolved",
                    llm_sport_category="table_tennis",
                    commence_time=commence,
                    market_metadata={"polymarket_event_id": event_id},
                )
            )
        # lane1b/550: a SECOND market on the middle event, above its anchor, so
        # the apply test proves the write reaches every id the page selected.
        s.add(
            FuturesMarket(
                id=SECOND_MARKET,
                source="polymarket",
                external_id=f"0x2526{SECOND_MARKET}",
                name="Table tennis match 943345 (set 1)",
                status="resolved",
                llm_sport_category="table_tennis",
                commence_time=EVENTS[1][2],
                market_metadata={"polymarket_event_id": "943345"},
            )
        )
        await s.commit()
    try:
        async with maker() as s:
            yield s
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


async def test_the_emitted_cursor_walks_every_page_on_asyncpg(session, monkeypatch):
    from app.tasks import repair_polymarket_sport_category as rail
    from tests.test_repair_polymarket_sport_category_q496 import _SETKA, _venue

    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
    seen = _venue(monkeypatch, {event_id: _SETKA for event_id, _m, _c in EVENTS})

    cursor: dict = {}
    for page, (event_id, market_id, commence) in enumerate(EVENTS, start=1):
        out = await rail.repair(session, apply=False, status_scope="not_open", limit=1, **cursor)
        assert out["counts"]["events_examined"] == 1, (
            f"page {page} examined nothing — terminal={out.get('terminal')!r}: "
            f"{str(out.get('reason'))[:300]}"
        )
        assert seen[-1] == event_id, f"page {page} read {seen[-1]}, expected {event_id}"
        cursor = out["next_cursor"]
        # The cursor is the STRING the dispatcher will hand back — the input that failed.
        assert isinstance(cursor["after_date"], str)
        assert cursor == {"after_date": commence.isoformat(), "after_id": market_id}

    assert seen == [e for e, _m, _c in EVENTS]
    last = await rail.repair(session, apply=False, status_scope="not_open", limit=1, **cursor)
    assert last["counts"]["events_examined"] == 0
    assert last.get("terminal") != "paused_target_timeout", str(last.get("reason"))[:300]


async def test_a_z_suffixed_cursor_date_resumes_on_asyncpg(session, monkeypatch):
    """The form an operator types from a UTC stamp, not the one the rail prints."""
    from app.tasks import repair_polymarket_sport_category as rail
    from tests.test_repair_polymarket_sport_category_q496 import _SETKA, _venue

    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
    seen = _venue(monkeypatch, {event_id: _SETKA for event_id, _m, _c in EVENTS})

    out = await rail.repair(
        session,
        apply=False,
        status_scope="not_open",
        limit=1,
        after_date="2026-08-31T18:55:34Z",
        after_id=72526003,
    )
    assert out["counts"]["events_examined"] == 1, str(out.get("reason"))[:300]
    assert seen == ["943345"]


async def test_an_apply_on_a_resumed_page_writes_every_selected_market_on_asyncpg(
    session, monkeypatch
):
    """lane1b/550: production 2026-09-24 02:29Z. The resolved-cohort write, keyed
    on the event id alone, was a 4.7s sequential scan against a 1.0s budget, so
    every `not_open` apply paused on its first event. It is now keyed on the
    page's own `market_ids` — an `integer[]` bind, which only the real driver can
    accept or refuse. The page is the production specimen's: resumed below the
    newest event, so it selects 943345 and nothing else."""
    from sqlalchemy import text

    from app.tasks import repair_polymarket_sport_category as rail
    from tests.test_repair_polymarket_sport_category_q496 import _TENNIS, _venue

    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
    seen = _venue(monkeypatch, {"943345": _TENNIS})

    out = await rail.repair(
        session,
        apply=True,
        status_scope="not_open",
        limit=1,
        after_date=EVENTS[0][2].isoformat(),
        after_id=EVENTS[0][1],
    )

    assert seen == ["943345"]
    assert out["terminal"] == "changed", (
        f"terminal={out.get('terminal')!r}: {str(out.get('reason'))[:300]}"
    )
    assert out["counts"]["markets_written"] == 2
    assert [r["event_id"] for r in out["receipts"]] == ["943345"]
    rows = dict(
        (
            await session.execute(
                text("SELECT id, llm_sport_category FROM futures_markets ORDER BY id")
            )
        ).all()
    )
    assert rows[EVENTS[1][1]] == "tennis" and rows[SECOND_MARKET] == "tennis", rows
    # The other two events were never on this page and must be exactly as seeded.
    assert rows[EVENTS[0][1]] == "table_tennis" and rows[EVENTS[2][1]] == "table_tennis", rows
