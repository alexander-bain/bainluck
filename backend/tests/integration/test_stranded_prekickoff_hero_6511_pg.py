"""#6511's stranded-hero backstop, executed against real PostgreSQL.

## why this gate exists, stated as the gap it closes

#5896 taught the two-minute beat to stop writing a Kalshi settlement back as a
price, and it works: on the specimen both legs of
``KXATPCHALLENGERDOUBLES-26SEP16MASSUKTRUHA`` read NULL from 06:53Z and stayed
NULL. The page went on serving **99% – 1%** under **"Starts in 19m"** for
**79 minutes** anyway, because the hero and the chart do not read
``futures_outcomes`` — they read ``Event.win_probability_sources``, and
:func:`_clear_pre_kickoff_settled_outcome` had been written believing that
clearing the leg withdrew the key by making the blend stage skip its write.

A SKIPPED WRITE IS NOT A WITHDRAWAL. It stops a new grade being stored; the
grade already stored stays exactly where it is. So the beat now runs
:data:`_KALSHI_STRANDED_PRE_KICKOFF_HERO_SQL` and hands each row it finds to
#5771's own :data:`_KALSHI_WITHDRAW_EVENT_HERO_SQL`.

## what only a server can decide, and why the fake-session gate cannot

The wiring guards assert which statement object the beat issued and with which
bound parameters. That is the right instrument for "did the writer decide
correctly", and it can say nothing at all about the two things this ship is:

1. **Whether the selector finds a book that is ALREADY QUIET.** This is the
   named trap on the issue. Every path-keyed clear hangs off "this pass cleared
   a leg", and #6511's specimen had been NULL for 67 minutes before the reader
   ever saw it — so a withdrawal keyed on the clear arrives one pass too late,
   forever. The selector reads no counter and no clear; it asks the rows. Only
   a server evaluates the ``NOT EXISTS``.

2. **Whether it can be made to delete a hero that is still speaking.** The
   dangerous shape is the one the hourly pass documented when it refused to run
   the hero statement on a mixed book: a silent stored speaker beside a trading
   sibling. ``EVENT_TWO_MARKETS`` below is exactly that row, and whether the
   ``NOT EXISTS`` sees the sibling is the server's answer, not the caller's.

Both statements are IMPORTED, never copied, so there is nothing here that can
drift out of step with production.

## the corpus, and what each row can fail on

Every event below carries a ``kalshi`` hero worth 0.99 — the grade shape the
ship is named for — so no control survives by being unrecognisable. What
differs is only the clause under test.

* **``stranded``** — the target. Scheduled, kicks off in 6h, one Kalshi market
  whose every leg is NULL. Also carries a ``polymarket`` key, because the
  statement must take one source and not the row.
* **``speaking``** — same shape, but its leg still holds a price. The hero is
  backed and must stand.
* **``two_markets``** — the stored speaker (``MARKET_TWO_A``) is silent while a
  SECOND Kalshi market on the same event still quotes. The hero must stand, and
  the ``eligibility.market_id`` deliberately names the silent one so that a
  selector keyed on the stored speaker rather than on the event would take it.
* **``live``** / **``past_sched``** — settled means settled (gotcha #21). Each
  fails exactly ONE of the two pre-kick-off clauses, so neither
  ``e.status = 'scheduled'`` nor ``e.commence_time > NOW()`` can be deleted
  without a row noticing.

  🔴 ``live`` IS DATED IN THE FUTURE ON PURPOSE, and the first draft of this
  file had it an hour in the past. That is the natural-looking seed and it
  makes the status arm VACUOUS: a live event that has also kicked off fails the
  clock clause as well, so deleting ``e.status = 'scheduled'`` leaves it
  excluded anyway. Measured — the mutation passed 11/11 before this row was
  re-dated. A control that fails two clauses tests neither. (The shape is real:
  `commence_time` drifts behind a venue's own state, which is #6057's class.)
* **``no_kalshi``** — a ``kalshi`` key with no Kalshi market at all, beside a
  PRICED polymarket market. The phantom-orphan class, owned by
  ``_cleanup_orphaned_blend_sources`` since #1163; two sweeps with two opinions
  about one key is how they drift. It also proves the JOIN's
  ``fm.source = 'kalshi'`` filter, since its priced leg is on the wrong source.
* **``poly_only``** — a quiet Kalshi book on an event whose hero has no
  ``kalshi`` key. Nothing to withdraw, and the statement must not invent one.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.tasks.prediction_market_matching import (
    _KALSHI_STRANDED_PRE_KICKOFF_HERO_SQL,
    _STRANDED_HERO_SWEEP_LIMIT,
)
from app.tasks.futures_price_refresh import _KALSHI_WITHDRAW_EVENT_HERO_SQL

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

#: Applied per-test, not module-wide: the premise arm needs no database and its
#: text guard is the last arm that should be conditional. Same reasoning as the
#: #5896 leg gate beside this file.
needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #6511 stranded-hero gate "
        "(CI job `search-recall` provides one)"
    ),
)

pg_test = (needs_postgres, pytest.mark.asyncio)


def _pg(fn):
    for mark in pg_test:
        fn = mark(fn)
    return fn


# --------------------------------------------------------------------------
# ids — explicit and namespaced to this ship, for the reason the sibling gate
# records: `search-recall` shares ONE database across every gate and
# `ON CONFLICT` draws `nextval` before it evaluates the conflict.
# --------------------------------------------------------------------------
SPORT_ID = 65110001

EVENT_STRANDED = 65110010
EVENT_SPEAKING = 65110011
EVENT_TWO_MARKETS = 65110012
EVENT_LIVE = 65110013
EVENT_PAST_SCHED = 65110014
EVENT_NO_KALSHI = 65110015
EVENT_POLY_ONLY = 65110016

MARKET_STRANDED = 65110100
MARKET_SPEAKING = 65110101
MARKET_TWO_A = 65110102  # the stored speaker, silent
MARKET_TWO_B = 65110103  # a second Kalshi market, still quoting
MARKET_LIVE = 65110104
MARKET_PAST_SCHED = 65110105
MARKET_POLY_ONLY = 65110106
MARKET_PM_SOURCE = 65110107  # source='polymarket', priced, on EVENT_NO_KALSHI

#: The grade a settled contract leaves behind, in the column's own terms.
GRADE = Decimal("0.9900")
#: A real pre-match quote.
QUOTE = Decimal("0.4200")

_ALL_EVENTS = [
    EVENT_STRANDED,
    EVENT_SPEAKING,
    EVENT_TWO_MARKETS,
    EVENT_LIVE,
    EVENT_PAST_SCHED,
    EVENT_NO_KALSHI,
    EVENT_POLY_ONLY,
]

#: (market_id, event_id, source, key)
_MARKETS = [
    (MARKET_STRANDED, EVENT_STRANDED, "kalshi", "stranded"),
    (MARKET_SPEAKING, EVENT_SPEAKING, "kalshi", "speaking"),
    (MARKET_TWO_A, EVENT_TWO_MARKETS, "kalshi", "two_a"),
    (MARKET_TWO_B, EVENT_TWO_MARKETS, "kalshi", "two_b"),
    (MARKET_LIVE, EVENT_LIVE, "kalshi", "live"),
    (MARKET_PAST_SCHED, EVENT_PAST_SCHED, "kalshi", "past_sched"),
    (MARKET_POLY_ONLY, EVENT_POLY_ONLY, "kalshi", "poly_only"),
    (MARKET_PM_SOURCE, EVENT_NO_KALSHI, "polymarket", "pm_source"),
]


def _hero(market_id: int | None, *, polymarket: bool = False) -> str:
    """The stored blend entry, in the shape production writes it.

    ``eligibility.market_id`` is carried because #5771's first arm reads it, and
    a fixture that omitted it would exercise only the second arm — leaving the
    arm that CAN delete a live speaker untested on every row.
    """
    wps: dict = {}
    if market_id is not None:
        wps["kalshi"] = {
            "value": 0.99,
            "updated_at": "2026-09-16T07:01:13.475405+00:00",
            "eligibility": {
                "rule": "live_blend.admissible_as_blend_speaker@5031",
                "market_id": market_id,
            },
        }
    if polymarket:
        wps["polymarket"] = {"value": 0.58, "updated_at": "2026-09-16T07:01:13+00:00"}
    return json.dumps(wps)


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that made its
    engine. `create_all` only, never `drop_all` — the database is shared and
    this gate owns nothing but its own id block.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _clear(conn)
        await _seed(conn)

    yield engine

    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn) -> None:
    """Remove only this gate's own id block, in FK order."""
    ids = [m for m, _, _, _ in _MARKETS]
    await conn.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"), {"ids": ids}
    )
    await conn.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"), {"ids": ids}
    )
    await conn.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": _ALL_EVENTS}
    )
    await conn.execute(text("DELETE FROM sports WHERE id = :id"), {"id": SPORT_ID})


async def _seed(conn) -> None:
    """Insert the corpus.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `sports.active`, `futures_markets.category` / `.mutually_exclusive`
    / `.status` and `events.status` carry a **client-side `default=`** applied by
    the ORM and invisible to a raw INSERT — omitting one raises
    `NotNullViolation` rather than taking the default.
    `tests/test_pg_gate_seed_completeness.py` parses these statements against
    live ORM metadata and this file is registered in its `COVERED` tuple.

    🔴 THE EVENT CLOCKS COME FROM THE SERVER. The statement under test says
    `e.commence_time > NOW()`; a hard-coded timestamp would be a correct seed on
    the day it was written and would quietly stop selecting anything later, at
    which point the withdrawal arm passes having withdrawn nothing.
    """
    await conn.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": SPORT_ID, "k": f"test_6511_{SPORT_ID}", "n": "Test 6511"},
    )

    for event_id, status, offset, wps in (
        (EVENT_STRANDED, "scheduled", "+6 hours", _hero(MARKET_STRANDED, polymarket=True)),
        (EVENT_SPEAKING, "scheduled", "+6 hours", _hero(MARKET_SPEAKING)),
        (EVENT_TWO_MARKETS, "scheduled", "+6 hours", _hero(MARKET_TWO_A)),
        # FUTURE-dated on purpose — see the module docstring. Dated in the past
        # it fails both pre-kick-off clauses and isolates neither.
        (EVENT_LIVE, "live", "+6 hours", _hero(MARKET_LIVE)),
        (EVENT_PAST_SCHED, "scheduled", "-1 hour", _hero(MARKET_PAST_SCHED)),
        (EVENT_NO_KALSHI, "scheduled", "+6 hours", _hero(999999999)),
        (EVENT_POLY_ONLY, "scheduled", "+6 hours", _hero(None, polymarket=True)),
    ):
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                "commence_time, status, win_probability_sources) VALUES "
                f"(:id, :sid, 'Masabayashi 6511', 'Truong 6511', "
                f"NOW() + interval '{offset}', :st, CAST(:wps AS jsonb))"
            ),
            {"id": event_id, "sid": SPORT_ID, "st": status, "wps": wps},
        )

    for market_id, event_id, source, key in _MARKETS:
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, event_id, source, external_id, "
                "name, category, mutually_exclusive, status) VALUES "
                "(:id, :eid, :src, :ext, :name, 'championship', true, 'open')"
            ),
            {
                "id": market_id,
                "eid": event_id,
                "src": source,
                "ext": f"KX6511-{key.upper()}",
                "name": f"{key} market 6511",
            },
        )

    # The quiet books: every leg NULL, which is the state #5896's clear leaves
    # behind and the state the reader was harmed in.
    for market_id in (
        MARKET_STRANDED,
        MARKET_TWO_A,
        MARKET_LIVE,
        MARKET_PAST_SCHED,
        MARKET_POLY_ONLY,
    ):
        await _leg(conn, market_id, "YES", None, is_winner=True)
        await _leg(conn, market_id, "NO", None, is_winner=False)

    # The books still speaking.
    await _leg(conn, MARKET_SPEAKING, "YES", QUOTE, is_winner=None)
    await _leg(conn, MARKET_TWO_B, "YES", QUOTE, is_winner=None)
    # Priced, but on the wrong SOURCE — it must not keep EVENT_NO_KALSHI's key
    # alive, and it must not make EVENT_NO_KALSHI selectable either.
    await _leg(conn, MARKET_PM_SOURCE, "YES", QUOTE, is_winner=None)


async def _leg(conn, market_id, external_id, probability, *, is_winner) -> None:
    await conn.execute(
        text(
            "INSERT INTO futures_outcomes (market_id, external_id, name, "
            "current_probability, is_winner) VALUES (:mid, :ext, :name, :p, :w)"
        ),
        {
            "mid": market_id,
            "ext": f"KX6511-{market_id}-{external_id}",
            "name": f"{external_id} leg",
            "p": probability,
            "w": is_winner,
        },
    )


async def _select(engine) -> dict[int, int]:
    """Run production's selector. Returns ``{event_id: market_id}``."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                _KALSHI_STRANDED_PRE_KICKOFF_HERO_SQL,
                {"limit": _STRANDED_HERO_SWEEP_LIMIT},
            )
        ).all()
    return {e: m for e, m in rows if e in _ALL_EVENTS}


async def _sweep(engine) -> int:
    """Selector + withdrawal, exactly as the beat composes them. Rows cleared."""
    selected = await _select(engine)
    cleared = 0
    async with engine.begin() as conn:
        for market_id in selected.values():
            cleared += len(
                (
                    await conn.execute(
                        _KALSHI_WITHDRAW_EVENT_HERO_SQL, {"market_id": market_id}
                    )
                ).fetchall()
            )
    return cleared


async def _heroes(engine) -> dict[int, dict]:
    """Read every event's stored blend back on a SEPARATE connection.

    A value visible only inside the writer's own transaction is not a value
    another process would see, and "did it COMMIT" is half of what this is for.
    """
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, win_probability_sources FROM events "
                    "WHERE id = ANY(:ids)"
                ),
                {"ids": _ALL_EVENTS},
            )
        ).all()
    return {eid: (wps or {}) for eid, wps in rows}


# --------------------------------------------------------------------------
# the ship
# --------------------------------------------------------------------------


@_pg
async def test_a_book_already_quiet_still_loses_its_stranded_hero(pg_engine):
    """THE NAMED TRAP (#6511). Every leg of `MARKET_STRANDED` was NULL before
    this pass began — nothing here cleared anything — and the key must still go.

    A withdrawal hung off "this pass cleared a leg" passes its own tests and
    never fires on the specimen, which had been quiet for 67 minutes when the
    reader saw 99% under "Starts in 19m"."""
    assert EVENT_STRANDED in await _select(pg_engine)

    assert await _sweep(pg_engine) >= 1

    assert "kalshi" not in (await _heroes(pg_engine))[EVENT_STRANDED]


@_pg
async def test_the_withdrawal_takes_one_source_and_not_the_row(pg_engine):
    """`polymarket` is still speaking for this event and is a different venue's
    opinion. The statement removes a key; it must never empty the column."""
    await _sweep(pg_engine)

    wps = (await _heroes(pg_engine))[EVENT_STRANDED]
    assert "polymarket" in wps
    assert wps["polymarket"]["value"] == 0.58


@_pg
async def test_a_kalshi_book_still_quoting_keeps_its_hero(pg_engine):
    """The hero is BACKED. Withdrawing it would delete a true number and leave
    the page quoting the sources that are left — a regression dressed as a fix."""
    assert EVENT_SPEAKING not in await _select(pg_engine)

    await _sweep(pg_engine)

    assert "kalshi" in (await _heroes(pg_engine))[EVENT_SPEAKING]


@_pg
async def test_a_silent_speaker_beside_a_trading_sibling_is_left_alone(pg_engine):
    """The shape the hourly pass refused to touch, and the reason it refused.

    `eligibility.market_id` names `MARKET_TWO_A`, which is silent — so #5771's
    FIRST arm matches on it and would delete the key. What stops that is the
    selector: it asks whether ANY Kalshi market on the EVENT still holds a
    price, and `MARKET_TWO_B` does. A selector keyed on the stored speaker
    instead of the event takes this row and deletes a live Kalshi number."""
    assert EVENT_TWO_MARKETS not in await _select(pg_engine)

    await _sweep(pg_engine)

    assert "kalshi" in (await _heroes(pg_engine))[EVENT_TWO_MARKETS]


@_pg
@pytest.mark.parametrize(
    "event_id,clause",
    [
        (EVENT_LIVE, "e.status = 'scheduled'"),
        (EVENT_PAST_SCHED, "e.commence_time > NOW()"),
    ],
)
async def test_after_kickoff_the_hero_stands(pg_engine, event_id, clause):
    """SETTLED MEANS SETTLED (gotcha #21). Once the contest has started the
    answer IS the number and it is calibration's evidence.

    Parametrised because the two clauses are not one test: each row below fails
    exactly one of them, so neither can be deleted without a row noticing."""
    assert event_id not in await _select(pg_engine), clause

    await _sweep(pg_engine)

    assert "kalshi" in (await _heroes(pg_engine))[event_id], clause


@_pg
async def test_an_event_with_no_kalshi_market_is_left_to_its_own_owner(pg_engine):
    """The phantom-orphan class, owned by `_cleanup_orphaned_blend_sources`
    since #1163. Two sweeps with two opinions about one key is how they drift,
    so the JOIN declines the row rather than racing for it.

    It also proves the JOIN's `fm.source = 'kalshi'` filter: this event's only
    market is a PRICED polymarket one, so a selector that forgot the source
    filter would both see a market here and think it still quoting."""
    assert EVENT_NO_KALSHI not in await _select(pg_engine)

    await _sweep(pg_engine)

    assert "kalshi" in (await _heroes(pg_engine))[EVENT_NO_KALSHI]


@_pg
async def test_a_quiet_book_under_no_kalshi_hero_is_not_selected(pg_engine):
    """`jsonb_exists` is the whole membership test. There is nothing to withdraw
    and the statement must not invent a row to report."""
    assert EVENT_POLY_ONLY not in await _select(pg_engine)

    await _sweep(pg_engine)

    assert (await _heroes(pg_engine))[EVENT_POLY_ONLY].get("polymarket") is not None


@_pg
async def test_the_selector_names_a_market_that_belongs_to_the_event(pg_engine):
    """`MIN(fm.id)` only has to name a Kalshi market of THIS event: #5771's
    statement joins `fm.id = :market_id AND e.id = fm.event_id`, so a market
    from another event withdraws nothing at all and the sweep reports zero
    while the page stays wrong."""
    assert (await _select(pg_engine))[EVENT_STRANDED] == MARKET_STRANDED


@_pg
async def test_the_sweep_is_idempotent(pg_engine):
    """It runs every two minutes over a population that is usually empty. The
    second pass must find nothing, not re-report the first pass's work."""
    assert await _sweep(pg_engine) >= 1

    assert await _select(pg_engine) == {}
    assert await _sweep(pg_engine) == 0


def test_the_beat_issues_productions_own_statements_not_a_copy():
    """The premise, and the only arm that needs no server.

    Both statements are imported into the beat. If either is ever re-written
    locally, every behavioural arm above goes on passing against a copy while
    production runs something else."""
    import inspect

    from app.tasks import prediction_market_matching as pmm

    body = inspect.getsource(pmm._poll_live_prediction_market_prices)

    assert "_KALSHI_STRANDED_PRE_KICKOFF_HERO_SQL" in body
    assert "from app.tasks.futures_price_refresh import" in body
    assert "_KALSHI_WITHDRAW_EVENT_HERO_SQL" in body
    # The withdrawal is SQL we did not write here — a second `UPDATE events`
    # in this beat would be a second opinion about when a hero may go.
    assert "win_probability_sources = " not in body
