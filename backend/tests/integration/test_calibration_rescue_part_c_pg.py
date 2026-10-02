"""``POST /api/calibration/rescue`` runs Part C — executed against a REAL PostgreSQL.

## the defect

The route's docstring said "Run Part C rescue directly", and the July 27 rescue
rail allowlists it for apply. Its SQL was a private copy that had drifted from
Part C on all three things Part C exists to enforce:

* **no event link** — it rewrote non-event markets, where Part C's own docstring
  says opening is the honest price and a later quote is the settlement;
* **no closing-line boundary** — it took the LAST snapshot ever recorded, so a
  final-round or post-settlement quote became the "forecast";
* **no source scope** — DataGolf model legs, whose contract is the model's
  pre-tournament reading (A1-dg, #762), were rewritten too.

Reproduced locally on the DataGolf specimen shape: a winner forecast at 0.10
before the tournament read back **0.95** — its final-round in-play reading. And
the row then no longer equals its opening, so no writer ever looks at it again.

## the corpus

* ``DG_WINNER`` — DataGolf, no event, stamp 0.10 = opening, pre-start reading
  0.12, in-play 0.95. Must keep **0.10**.
* ``NONEVENT`` — Kalshi weather market, no event, stamp 0.30, later quote 0.99.
  Must keep **0.30**.
* ``LINKED`` — event-linked, stamp 0.50, last quote before the event 0.55,
  after it 0.90. Must become **0.55** — the closing line, proving the route
  still does Part C's job and the controls above are not green because the
  route now does nothing.

``test_the_old_statement_fails_this_corpus`` executes the removed SQL on the same
rows and requires it to write 0.95 / 0.99 / 0.90, so a green run means this
corpus can tell the two rules apart.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres calibration "
        "rescue gate (CI job `search-recall` provides one)"
    ),
)

T0 = datetime(2026, 6, 4, 0, 0, tzinfo=timezone.utc)
DAY = timedelta(days=1)

SPORT = 9122001
EVENT = 9122101
DG_MARKET, NONEVENT_MARKET, LINKED_MARKET = 9122201, 9122202, 9122203
DG_WINNER, NONEVENT, LINKED = 9122301, 9122302, 9122303

#: The private statement the route ran before it was pointed at Part C.
OLD_RESCUE_SQL = """
    WITH stuck AS (
        SELECT fo.id AS outcome_id, fo.opening_probability
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fm.id = fo.market_id
        WHERE fm.status = 'resolved'
          AND fo.calibration_probability IS NOT NULL
          AND fo.opening_probability IS NOT NULL
          AND fo.calibration_probability = fo.opening_probability
        LIMIT :limit
    ),
    last_snap AS (
        SELECT DISTINCT ON (s.outcome_id)
            s.outcome_id,
            fos.probability
        FROM stuck s
        JOIN futures_odds_snapshots fos ON fos.outcome_id = s.outcome_id
        WHERE fos.probability > 0 AND fos.probability < 1
        ORDER BY s.outcome_id, fos.captured_at DESC
    )
    UPDATE futures_outcomes fo
    SET calibration_probability = ls.probability
    FROM last_snap ls
    WHERE fo.id = ls.outcome_id
      AND ls.probability != fo.opening_probability
"""


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture
async def session():
    """Real Postgres with the real schema, dropped and rebuilt, then seeded."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await _seed(s)
        yield s
    await engine.dispose()


async def _seed(session):
    """Insert the corpus through the ORM (client-side defaults apply)."""
    from app.models.models import (
        Event,
        FuturesMarket,
        FuturesOddsSnapshot,
        FuturesOutcome,
        Sport,
    )

    session.add(Sport(id=SPORT, key="golf_pga_rescue", name="PGA", group="Golf"))
    await session.flush()
    session.add(
        Event(
            id=EVENT,
            sport_id=SPORT,
            external_id="rescue-gate-event",
            home_team_name="Home",
            away_team_name="Away",
            commence_time=T0,
            status="completed",
        )
    )
    for mid, source, ext, category, event_id in (
        (DG_MARKET, "datagolf", "datagolf:pga:999:win", "golf", None),
        (NONEVENT_MARKET, "kalshi", "KXHIGHNY-26JUN04", "weather", None),
        (LINKED_MARKET, "kalshi", "KXMLBGAME-26JUN04", "baseball", EVENT),
    ):
        session.add(
            FuturesMarket(
                id=mid,
                source=source,
                external_id=ext,
                name=f"rescue gate {mid}",
                category=category,
                llm_sport_category=category,
                status="resolved",
                event_id=event_id,
                commence_time=T0,
                resolution_date=T0 + 4 * DAY,
            )
        )
    await session.flush()
    corpus = {
        DG_WINNER: (DG_MARKET, 0.10, [(-3 * DAY, 0.10), (-DAY, 0.12), (3 * DAY, 0.95)]),
        NONEVENT: (NONEVENT_MARKET, 0.30, [(-3 * DAY, 0.30), (2 * DAY, 0.99)]),
        LINKED: (LINKED_MARKET, 0.50, [(-3 * DAY, 0.50), (-DAY, 0.55), (DAY, 0.90)]),
    }
    for oid, (mid, stamp, _) in corpus.items():
        session.add(
            FuturesOutcome(
                id=oid,
                market_id=mid,
                external_id=f"rescue_{oid}",
                name=f"leg {oid}",
                opening_probability=stamp,
                calibration_probability=stamp,
                is_winner=True,
                resolution_source="api_settlement",
            )
        )
    await session.flush()
    for oid, (_, _, snaps) in corpus.items():
        for offset, prob in snaps:
            session.add(
                FuturesOddsSnapshot(
                    outcome_id=oid,
                    bookmaker="rescue_gate",
                    probability=prob,
                    captured_at=T0 + offset,
                    reading_count=1,
                )
            )
    await session.commit()


async def _prices(session) -> dict[int, float]:
    from sqlalchemy import text

    rows = await session.execute(
        text(
            "SELECT id, calibration_probability FROM futures_outcomes "
            "WHERE id = ANY(:ids)"
        ),
        {"ids": [DG_WINNER, NONEVENT, LINKED]},
    )
    return {r.id: float(r.calibration_probability) for r in rows}


async def _call_route(session, monkeypatch):
    from app.routes import calibration as route

    monkeypatch.setattr(route, "_check_admin_secret", lambda *a, **k: None)
    return await route.calibration_rescue(request=None, db=session, secret="", limit=50000)


async def test_the_route_reprices_only_what_part_c_reprices(session, monkeypatch):
    body = await _call_route(session, monkeypatch)

    prices = await _prices(session)
    assert prices[DG_WINNER] == pytest.approx(0.10), "DataGolf model leg was rewritten"
    assert prices[NONEVENT] == pytest.approx(0.30), "non-event market was rewritten"
    assert prices[LINKED] == pytest.approx(0.55), "event-linked leg did not get its closing line"
    assert body == {"rescued": 1, "limit": 50000}


async def test_a_second_call_changes_nothing(session, monkeypatch):
    await _call_route(session, monkeypatch)
    body = await _call_route(session, monkeypatch)

    assert body["rescued"] == 0
    assert await _prices(session) == {
        DG_WINNER: pytest.approx(0.10),
        NONEVENT: pytest.approx(0.30),
        LINKED: pytest.approx(0.55),
    }


async def test_the_old_statement_fails_this_corpus(session):
    from sqlalchemy import text

    await session.execute(text(OLD_RESCUE_SQL), {"limit": 50000})
    await session.commit()

    prices = await _prices(session)
    assert prices == {
        DG_WINNER: pytest.approx(0.95),
        NONEVENT: pytest.approx(0.99),
        LINKED: pytest.approx(0.90),
    }
