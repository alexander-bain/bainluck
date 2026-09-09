"""#4229's Kalshi backfill, executed against a REAL PostgreSQL.

## what this guards, and why nothing cheaper would have caught it

CERT-2372 blocked the classifier-only SHA with a precise finding: the diff
makes every one of these markets *classify* as ``politics`` while the stored
rows stay ``hockey``, because ``app/tasks/kalshi.py`` writes the tag through
``coalesce(nullif(existing, 'other'), new)`` and therefore never overwrites a
real tag. The required repair it named is
``4229-BACKFILL-THE-FOUR-LIVE-SENATE-ROWS``: *"a test that seeds an existing
`hockey` Kalshi row, executes the shipped correction, and reads back
`politics`, with an Ottawa/Belleville control unchanged."* That sentence is the
spec for this file.

The claim is **"a stored row changed value"**, and the only thing that can
observe a stored row changing value is a server that stored it. A mock session
returns whatever ``rowcount`` it is handed, which is precisely the number under
test; and the failure mode being guarded — a coalesce silently preserving the
old value — is a *write that appears to succeed and changes nothing*. That is
the shape my own #4157 work walked into: a guard whose subject never executed
still reported success. So this runs the real ``repair()`` over a real
``futures_markets`` row and reads the column back.

There is no local PostgreSQL in the agent sandbox (``initdb`` dies on
``shmget``), so ``search-recall`` is this gate's only reader, and it names the
file in a hand-written step with the all-skipped detector its neighbours carry.
Adding the file is not adding the gate.

## the corpus, and what each row can fail on

Four rows, each paired with the defect it catches:

* **the subject** (``109237``) — a Kalshi row stored ``hockey`` whose name is
  the real production string *"Which Senators will vote for Kevin Warsh as Fed
  chair?"*. Must read back ``politics``. This is the row CERT-2372 said would
  not move.
* **the Ottawa control** (``59693566``) — a Kalshi row stored ``hockey`` named
  *"NHL: OTT Senators Total Points"*, and **deliberately placed inside**
  :data:`SENATE_ROW_IDS`' blast radius by the test's own monkeypatch. This is
  the assertion that matters: it proves the repair is gated on the shipped
  classifier's per-row verdict and not merely on membership of an id list. A
  blind ``UPDATE ... WHERE id IN (...)`` passes every other test in this file
  and fails this one.
* **the Belleville control** (``111229``) — stored ``hockey``, name *"Belleville
  Senators vs Hartford Wolf Pack"*, NOT in the id list. Guards the other
  direction: the repair must not widen itself into a name predicate, which
  would sweep the 133 resolved Belleville/Ottawa rows that match ``senat*``.
* **the Polymarket row** (``114420``) — in the id list, classifies
  ``politics``, but ``source='polymarket'``. Must be refused with reason
  ``not_kalshi``: that writer assigns unconditionally and owns its own rows, so
  this rail must not race it.

## the arm that proves red-first

``test_a_blind_id_update_cannot_pass_this`` executes the naive repair — the
one-statement ``UPDATE ... WHERE id IN (SENATE_ROW_IDS)`` a reviewer would
reach for — and requires it to corrupt the Ottawa control. A green run of this
file therefore means the classifier gate was proved *necessary*, not that
nothing objected.
"""

from __future__ import annotations

import os

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #4229 Kalshi "
        "senate backfill (CI job `search-recall` provides one)"
    ),
)

#: Real production strings, read off production 2026-09-09. Invented names
#: would not exercise the mechanism: the whole subject is whether the SHIPPED
#: classifier moves this exact text, so a paraphrase could pass while the
#: production row stayed put.
SUBJECT_ID = 109237
SUBJECT_NAME = "Which Senators will vote for Kevin Warsh as Fed chair?"
SUBJECT_TICKER = "KXVOTEFEDCHAIR-27"

OTTAWA_ID = 59693566
OTTAWA_NAME = "NHL: OTT Senators Total Points"

BELLEVILLE_ID = 111229
BELLEVILLE_NAME = "Belleville Senators vs Hartford Wolf Pack"

POLYMARKET_ID = 114420
POLYMARKET_NAME = "How many senators will vote for Trump's Fed chair nominee?"


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
    """Insert the corpus through the ORM.

    Deliberately the ORM and not raw INSERT: `futures_markets` carries
    client-side defaults that a raw INSERT does not apply, and this file has no
    reason to re-litigate that. (It is consequently outside
    `test_pg_gate_seed_completeness.py`'s raw-INSERT arm, which keys on the
    presence of `INSERT INTO`.)
    """
    from app.models import FuturesMarket

    for mid, source, name, ext in (
        (SUBJECT_ID, "kalshi", SUBJECT_NAME, SUBJECT_TICKER),
        (OTTAWA_ID, "kalshi", OTTAWA_NAME, "KXNHLPOINTS-26"),
        (BELLEVILLE_ID, "kalshi", BELLEVILLE_NAME, "KXAHLGAME-26"),
        (POLYMARKET_ID, "polymarket", POLYMARKET_NAME, "pm-fedchair"),
    ):
        session.add(
            FuturesMarket(
                id=mid,
                source=source,
                external_id=ext,
                name=name,
                llm_sport_category="hockey",
                status="open",
            )
        )
    await session.commit()


async def _category(session, market_id: int) -> str:
    from sqlalchemy import select

    from app.models import FuturesMarket

    return (
        await session.execute(
            select(FuturesMarket.llm_sport_category).where(
                FuturesMarket.id == market_id
            )
        )
    ).scalar_one()


@needs_postgres
@pytest.mark.asyncio
async def test_the_stored_kalshi_row_reads_back_politics(session):
    """The exact thing CERT-2372 said would not happen."""
    from app.tasks.repair_kalshi_senate_category import repair

    await _seed(session)
    assert await _category(session, SUBJECT_ID) == "hockey", "seed precondition"

    result = await repair(session, apply=True)

    assert await _category(session, SUBJECT_ID) == "politics"
    assert result["changed"] >= 1
    assert result["terminal"] == "changed"


@needs_postgres
@pytest.mark.asyncio
async def test_the_ottawa_control_inside_the_id_list_is_refused(session, monkeypatch):
    """Membership of the id list must NOT be sufficient to relabel a row.

    The Ottawa row is forced INTO the bound, so only the shipped classifier's
    per-row verdict can save it. This is the assertion a blind
    `UPDATE ... WHERE id IN (...)` fails.
    """
    from app.tasks import repair_kalshi_senate_category as rail

    await _seed(session)
    monkeypatch.setattr(
        rail, "SENATE_ROW_IDS", (SUBJECT_ID, OTTAWA_ID), raising=True
    )

    result = await rail.repair(session, apply=True)

    assert await _category(session, OTTAWA_ID) == "hockey"
    assert await _category(session, SUBJECT_ID) == "politics"
    refusals = {r["id"]: r["reason"] for r in result["refused"]}
    assert refusals[OTTAWA_ID] == "classifier_disagrees"


@needs_postgres
@pytest.mark.asyncio
async def test_a_blind_id_update_cannot_pass_this(session, monkeypatch):
    """Red-first: the naive repair corrupts the Ottawa control.

    Executes the one-statement update a reviewer would reach for, so a green
    file means the classifier gate was proved necessary.
    """
    from sqlalchemy import update

    from app.models import FuturesMarket

    await _seed(session)
    await session.execute(
        update(FuturesMarket)
        .where(FuturesMarket.id.in_((SUBJECT_ID, OTTAWA_ID)))
        .values(llm_sport_category="politics")
    )
    await session.commit()

    assert await _category(session, OTTAWA_ID) == "politics", (
        "the blind update is supposed to corrupt the control — if it did not, "
        "this file's central assertion is no longer load-bearing"
    )


@needs_postgres
@pytest.mark.asyncio
async def test_belleville_outside_the_list_is_never_examined(session):
    """The repair must not widen itself into a name predicate."""
    from app.tasks.repair_kalshi_senate_category import repair

    await _seed(session)
    result = await repair(session, apply=True)

    assert await _category(session, BELLEVILLE_ID) == "hockey"
    seen = {r["id"] for r in result["planned"]} | {r["id"] for r in result["refused"]}
    assert BELLEVILLE_ID not in seen


@needs_postgres
@pytest.mark.asyncio
async def test_the_polymarket_row_is_refused_as_not_kalshi(session):
    """That writer assigns unconditionally and owns its own rows."""
    from app.tasks.repair_kalshi_senate_category import repair

    await _seed(session)
    result = await repair(session, apply=True)

    assert await _category(session, POLYMARKET_ID) == "hockey"
    refusals = {r["id"]: r["reason"] for r in result["refused"]}
    assert refusals[POLYMARKET_ID] == "not_kalshi"


@needs_postgres
@pytest.mark.asyncio
async def test_dry_run_writes_nothing_and_still_reports_the_plan(session):
    """D51's plan half: the payload is the backup, so it must be complete."""
    from app.tasks.repair_kalshi_senate_category import repair

    await _seed(session)
    result = await repair(session, apply=False)

    assert await _category(session, SUBJECT_ID) == "hockey"
    assert result["terminal"] == "dry_run"
    assert result["changed"] == 0
    planned = {p["id"]: p for p in result["planned"]}
    assert planned[SUBJECT_ID]["before"] == "hockey"
    assert planned[SUBJECT_ID]["classifier"] == "politics"
