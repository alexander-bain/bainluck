"""#4229's Polymarket repair, executed against a REAL PostgreSQL.

## what this guards, and why nothing cheaper would have caught it

CERT-2382 blocked the first SHA with a precise finding. The UPDATE carried
``updated_at = NOW()`` — added out of habit — and on this table ``updated_at``
is not bookkeeping: **the card renders it as the market's own relative date.**
The Fed Chair card's before-LOOK reads ``May 17`` in the corner, which IS the
115-day staleness shown to a reader. Applying that SHA would have left the
four-month-old prices untouched while presenting them as observed *just now*: a
reader-visible TRUTH regression introduced by the TRUTH repair, in the same
statement that fixed the badge.

The required repair it named is ``4229-PRESERVE-THE-MARKETS-OBSERVATION-CLOCK``:
*"update only ``llm_sport_category``, require that exact assignment set in the
guard, and prove an old timestamp survives apply unchanged."* The first two
clauses are pinned in ``tests/test_repair_polymarket_senate_category_4229.py``
by AST scan. **The third is this file, and it cannot be anywhere else.**

Why a source scan is not enough for the third clause, and this is the whole
argument for the file: ``FuturesMarket.updated_at`` is declared
``onupdate=func.now()``. That fires for SQLAlchemy Core and ORM ``update()``
constructs. This rail writes through ``text()``, which it does not fire for —
and the models file says as much about the raw-SQL settlement writers. So
"``updated_at`` survives" currently rests on **an interaction between a column
default and a statement style**, neither of which is visible in the repair's own
source. A future edit that switched the rail from ``text()`` to
``sqlalchemy.update()`` would keep every source-scan guard green, write no
``updated_at`` clause anywhere, and bump the timestamp on every repaired row.
Only a server that stored the row can see that.

The same reasoning the Kalshi sibling's real-Postgres file carries: the claim is
about what a database ends up holding, and a stub session returns whatever it is
handed.

## the corpus, and what each row can fail on

* **the subject** (``114420`` / event ``162276``) — the real production row,
  stored ``hockey``, seeded with ``updated_at`` at the real production value
  **2026-05-17**. Must read back ``politics`` with that timestamp **byte-for-byte
  unchanged**. This is the row CERT-2382 said would be presented as fresh.
* **the hockey control** (``115387`` / event ``193680``) — "Red Wings vs.
  Senators", stored ``hockey``, and deliberately placed INSIDE the repair's
  bound by the test's own monkeypatch. It proves the rail is gated on the
  venue's per-event verdict and not on membership of an id list: a blind
  ``UPDATE ... WHERE event_id IN (...)`` passes every other assertion here and
  fails this one. Its timestamp must not move either — a refused event must not
  be touched at all.

## the arm that proves red-first

``test_a_repair_that_stamps_the_clock_cannot_pass_this`` executes the BLOCKED
statement — the same UPDATE with ``updated_at = NOW()`` restored — and requires
the timestamp assertion to fail. A green run of this file therefore means the
observation clock is preserved *and* that preserving it was proved necessary,
rather than that nothing objected.

The venue is stubbed with the real captured Gamma payloads. That is deliberate
and is not a weakening: the claim under test is what the DATABASE ends up
holding, and a CI gate that reached out to Gamma would be graded on Gamma's
uptime. The venue gate itself is proved against those same payloads in the unit
file.
"""

from __future__ import annotations

import os

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #4229 Polymarket "
        "senate repair (CI job `search-recall` provides one)"
    ),
)

#: Real production values, read off production 2026-09-09. The timestamp is the
#: actual stored one, not a round number: it is the thing a reader sees as
#: "May 17" on the card, and the point of the test is that it does not move.
SUBJECT_ID = 114420
SUBJECT_EVENT = "162276"
SUBJECT_NAME = "How many senators will vote for Trump's Fed chair nominee?"
SUBJECT_UPDATED_AT = "2026-05-17T21:05:41.447680+00:00"

CONTROL_ID = 115387
CONTROL_EVENT = "193680"
CONTROL_NAME = "Red Wings vs. Senators"
CONTROL_UPDATED_AT = "2026-04-02T11:22:33.123456+00:00"

#: The same trimmed Gamma payloads the unit file uses, verified to return the
#: same verdict as the full ones.
SUBJECT_PAYLOAD = {
    "title": SUBJECT_NAME,
    "tags": [{"label": "Trump"}, {"label": "Politics"}, {"label": "Fed"}],
    "markets": [{"question": "Will 55 senators vote “Yea” for Trump’s Fed Chair nominee?"}],
}

CONTROL_PAYLOAD = {
    "title": CONTROL_NAME,
    "tags": [{"label": "Sports"}, {"label": "NHL"}, {"label": "Games"}],
    "markets": [{"question": CONTROL_NAME}],
}

PAYLOADS = {SUBJECT_EVENT: SUBJECT_PAYLOAD, CONTROL_EVENT: CONTROL_PAYLOAD}


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    return url.replace("postgres://", "postgresql://", 1).replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


@pytest.fixture
async def session():
    """Real Postgres with the real schema, dropped and rebuilt."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(_asyncpg_url(DB_URL))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed(session):
    """Insert the corpus through the ORM, with EXPLICIT stale timestamps.

    `updated_at` is written here rather than left to `server_default` precisely
    because the assertion is that it does not move: a row created `now()` would
    make "unchanged" and "stamped now" indistinguishable, and the test would
    pass against the very defect it exists to catch.
    """
    from datetime import datetime

    from app.models import FuturesMarket

    for mid, event_id, name, stamp in (
        (SUBJECT_ID, SUBJECT_EVENT, SUBJECT_NAME, SUBJECT_UPDATED_AT),
        (CONTROL_ID, CONTROL_EVENT, CONTROL_NAME, CONTROL_UPDATED_AT),
    ):
        session.add(
            FuturesMarket(
                id=mid,
                source="polymarket",
                external_id=event_id,
                name=name,
                llm_sport_category="hockey",
                status="open",
                market_metadata={"polymarket_event_id": event_id},
                updated_at=datetime.fromisoformat(stamp),
            )
        )
    await session.commit()


async def _row(session, market_id: int):
    from sqlalchemy import select

    from app.models import FuturesMarket

    return (
        await session.execute(
            select(
                FuturesMarket.llm_sport_category, FuturesMarket.updated_at
            ).where(FuturesMarket.id == market_id)
        )
    ).one()


def _stub_venue(monkeypatch, rail):
    async def fake_fetch(_client, event_id):
        payload = PAYLOADS.get(event_id)
        if payload is None:
            return "not_at_venue", None
        return "ok", payload

    monkeypatch.setattr(rail, "_fetch_event", fake_fetch)
    monkeypatch.setattr(rail, "VENUE_PAUSE", 0)


@needs_postgres
@pytest.mark.asyncio
async def test_the_stored_row_reads_back_politics(session, monkeypatch):
    """The badge moves. Without this the repair does nothing at all."""
    from app.tasks import repair_polymarket_senate_category as rail

    await _seed(session)
    _stub_venue(monkeypatch, rail)
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", (SUBJECT_EVENT, CONTROL_EVENT))

    out = await rail.repair(session, apply=True)

    category, _stamp = await _row(session, SUBJECT_ID)
    assert category == "politics", (
        "the Fed Chair row did not move; the whole ship is this row's badge"
    )
    assert out["counts"]["rows_written"] == 1


@needs_postgres
@pytest.mark.asyncio
async def test_the_observation_clock_survives_the_apply(session, monkeypatch):
    """🔴 CERT-2382's required repair, third clause, and the reason this file exists.

    `updated_at` is rendered on the card as the market's own relative date. The
    prices did not change, so the date must not either.
    """
    from datetime import datetime

    from app.tasks import repair_polymarket_senate_category as rail

    await _seed(session)
    _stub_venue(monkeypatch, rail)
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", (SUBJECT_EVENT, CONTROL_EVENT))

    before = datetime.fromisoformat(SUBJECT_UPDATED_AT)
    await rail.repair(session, apply=True)
    category, stamp = await _row(session, SUBJECT_ID)

    assert category == "politics", "guard the precondition, or the assertion below is vacuous"
    assert stamp == before, (
        f"the repair moved the observation clock from {before} to {stamp}. The "
        "card renders this as the market's relative date, so unchanged May 17 "
        "prices would now be presented to a reader as observed just now."
    )


@needs_postgres
@pytest.mark.asyncio
async def test_the_venue_spares_a_real_hockey_event_inside_the_bound(session, monkeypatch):
    """The control, forced INSIDE the id bound so only the venue's verdict can spare it.

    68 of the 74 events censused look like this one. A blind id update passes
    every other assertion in this file and fails here.
    """
    from datetime import datetime

    from app.tasks import repair_polymarket_senate_category as rail

    await _seed(session)
    _stub_venue(monkeypatch, rail)
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", (SUBJECT_EVENT, CONTROL_EVENT))

    await rail.repair(session, apply=True)
    category, stamp = await _row(session, CONTROL_ID)

    assert category == "hockey", (
        "Red Wings vs. Senators was relabelled. The rail is no longer gated on "
        "the venue's per-event verdict."
    )
    assert stamp == datetime.fromisoformat(CONTROL_UPDATED_AT), (
        "a REFUSED event had its timestamp moved; a refusal must touch nothing"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_a_dry_run_changes_nothing_on_the_server(session, monkeypatch):
    from datetime import datetime

    from app.tasks import repair_polymarket_senate_category as rail

    await _seed(session)
    _stub_venue(monkeypatch, rail)
    monkeypatch.setattr(rail, "SENATE_EVENT_IDS", (SUBJECT_EVENT, CONTROL_EVENT))

    out = await rail.repair(session, apply=False)

    category, stamp = await _row(session, SUBJECT_ID)
    assert category == "hockey"
    assert stamp == datetime.fromisoformat(SUBJECT_UPDATED_AT)
    assert out["terminal"] == "dry_run"
    assert out["planned"], "a dry run that plans nothing would make this vacuous"


@needs_postgres
@pytest.mark.asyncio
async def test_a_repair_that_stamps_the_clock_cannot_pass_this(session):
    """🔴 RED-FIRST. Execute the BLOCKED statement and require the assertion to fail.

    Without this arm, `test_the_observation_clock_survives_the_apply` proves only
    that nothing objected — it would pass identically against a rail that never
    wrote the row at all. Here the write definitely happens and the timestamp
    definitely moves, so the assertion above is shown to have teeth.
    """
    from datetime import datetime

    from sqlalchemy import text

    await _seed(session)
    before = datetime.fromisoformat(SUBJECT_UPDATED_AT)

    # The exact statement CERT-2382 blocked.
    await session.execute(
        text(
            """
            UPDATE futures_markets
            SET llm_sport_category = :llm,
                updated_at = NOW()
            WHERE id = ANY(:ids)
            """
        ),
        {"llm": "politics", "ids": [SUBJECT_ID]},
    )
    await session.commit()

    category, stamp = await _row(session, SUBJECT_ID)
    assert category == "politics", "the blocked statement must really write, or this arm is vacuous"
    assert stamp != before, (
        "the blocked statement did NOT move the timestamp, so "
        "`test_the_observation_clock_survives_the_apply` cannot fail and proves "
        "nothing. Most likely `updated_at` stopped being a plain column."
    )
