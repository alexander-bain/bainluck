"""`_refine_stand_in_event_starts()`'s SQL and commit, against a REAL PostgreSQL.

## why this gate needs a real server

The rules of the repair are pure and are proved without a database in
`tests/test_stand_in_event_start_refinement.py`. Three things in this rail are
NOT pure, and a fake session can only agree with itself about them:

1. **`WHERE e.commence_time_source = ANY(:derived)`** binds a Python
   `list[str]` to a Postgres `text[]`. That is a driver contract, not a Python
   one. `sorted(DERIVED_COMMENCE_SOURCES)` on a frozenset is the sort of
   expression that raises only when a real driver sees it.

2. **`AND fm.status = 'open'`** is the one WHERE clause the pure predicate does
   NOT duplicate — `_stand_in_refinement_target` never sees a status. Delete it
   and finished matches get re-dated, and no unit test in the tree can tell.
   `test_the_unscoped_query_redates_events_for_matches_already_over` executes
   the mutated shape and requires the damage to be visible.

3. **Whether the UPDATE was COMMITTED, and that it wrote BOTH columns.** Every
   assertion below reads back on a *separate connection*, so what is asserted
   is what another process — the API serving `/api/events/{id}` — would see.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs.

## the corpus

Eight events, each paired with the defect it catches:

* **`refines`** — the ship. Stand-in at Sep 7 midnight, open Kalshi
  `KXATPMATCH` market at the venue's `2026-09-07T18:00Z`. Moves, and its
  `commence_time_source` becomes `kalshi_occurrence`.
* **`two_markets`** — one event, TWO open markets disagreeing about the hour.
  Proves the ORDER BY + dedupe: exactly one write, and a deterministic value.
  Under the pre-dedupe loop the survivor depended on server row order.
* **`itf_next_day`** — the measured Asian ITF draw, +33.5h. Moves.
* **`espn_event`** — identical market, but the event's start came from ESPN.
  The non-overwrite control the cert BLOCK named.
* **`no_source_event`** — `commence_time_source IS NULL`, which is most of the
  table. Must be invisible to `= ANY(:derived)`; a NULL never equals anything,
  so this row also proves the clause is not accidentally `IS DISTINCT FROM`.
* **`closed_market`** — identical to `refines` but the market is `closed`. The
  row that makes clause (2) above load-bearing.
* **`backstop_market`** — dated-match ticker whose market is still on the +14d
  settlement close. Selected by the SQL, refused by the window. This is the
  deploy-ordering row: the repair may run before the poll re-times the market.
* **`outright_market`** — `KXWTA-26USO`, +14d close. Selected by the SQL,
  refused by the dated-fixture gate. Without that gate this event would be
  dragged a fortnight out.

#3562 adds two more, because the gate is no longer tennis-shaped:

* **`soccer_fixture`** — `KXLIGUE1GAME-26SEP20OLMPSG`, the Ligue 1 fixture whose
  page said the wrong DAY. `llm_sport_category='soccer'`, so it also proves the
  tennis-scoped market fix-up cannot see it. Moves, +21.75h.
* **`nfl_prop`** — `KXNFLRACE-26SEP14DENKC-35`, a race-to-N-points prop on a
  Monday-night game: occurrence 2026-09-15T03:15Z against a ticker naming the
  14th. **+27.25h and a different calendar day**, which is the case a
  "same UTC day" rule would have refused.

and, for CERT-2087's required repair, **`test_the_refresh_reaches_a_row_the_poll_never_will`** —
the regression the BLOCK named. A dated fixture ALREADY in the table, market on its settlement
close and event on ticker midnight, with the discovery loop's existing tail never reached (which is
what production does on 24 of 24 beats) and the poll's post-loop remainder dropped by its own
deadline. The shipped scheduled path must still put the venue's occurrence on the market, on the
Event, and on what the event API reads. On the pre-repair code every one of those stays wrong.

and the composition driver `test_both_post_loop_fixups_in_the_shipped_order`,
which is the assertion neither #3488's branch nor #3532's could make alone:
`_fix_tennis_commence_times` and `_refine_stand_in_event_starts` are two writers
of `futures_markets.commence_time` / `events.commence_time` in one post-loop
block, and #3532 was filed because the first clobbered the venue hour the poll
had just stored. Running one of them proves nothing about that.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres stand-in event "
        "start gate (CI job `search-recall` provides one)"
    ),
)

UTC = timezone.utc

STAND_IN_SEP07 = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
STAND_IN_SEP06 = datetime(2026, 9, 6, 0, 0, tzinfo=UTC)
STAND_IN_SEP20 = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
STAND_IN_SEP14 = datetime(2026, 9, 14, 0, 0, tzinfo=UTC)
PUBLISHED = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
PUBLISHED_LATER = datetime(2026, 9, 7, 20, 30, tzinfo=UTC)
ITF_PUBLISHED = datetime(2026, 9, 7, 9, 30, tzinfo=UTC)
BACKSTOP = datetime(2026, 9, 21, 6, 5, tzinfo=UTC)
#: Venue-read 2026-09-06 (notice 26), #3562.
LIGUE1_PUBLISHED = datetime(2026, 9, 20, 21, 45, tzinfo=UTC)
NFL_PUBLISHED = datetime(2026, 9, 15, 3, 15, tzinfo=UTC)


# (key, event_source, event_commence,
#  [(external_id, source, status, market_commence, llm_sport_category), ...])
_EVENTS = [
    ("refines", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07ZVEDAR", "kalshi", "open", PUBLISHED, "tennis"),
    ]),
    ("two_markets", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07AAAZZZ", "kalshi", "open", PUBLISHED, "tennis"),
        ("KXATPMATCH-26SEP07BBBZZZ", "kalshi", "open", PUBLISHED_LATER, "tennis"),
    ]),
    ("itf_next_day", "kalshi_ticker", STAND_IN_SEP06, [
        ("KXITFMATCH-26SEP06STOISH-STO", "kalshi", "open", ITF_PUBLISHED, "tennis"),
    ]),
    ("espn_event", "espn", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07ESPESP", "kalshi", "open", PUBLISHED, "tennis"),
    ]),
    ("no_source_event", None, STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07NULNUL", "kalshi", "open", PUBLISHED, "tennis"),
    ]),
    ("closed_market", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07CLOCLO", "kalshi", "closed", PUBLISHED, "tennis"),
    ]),
    ("backstop_market", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXATPMATCH-26SEP07FARFAR", "kalshi", "open", BACKSTOP, "tennis"),
    ]),
    ("outright_market", "kalshi_ticker", STAND_IN_SEP07, [
        ("KXWTA-26USO", "kalshi", "open", BACKSTOP, "tennis"),
    ]),
    # ---- #3562 -----------------------------------------------------------
    ("soccer_fixture", "kalshi_ticker", STAND_IN_SEP20, [
        ("KXLIGUE1GAME-26SEP20OLMPSG", "kalshi", "open", LIGUE1_PUBLISHED,
         "soccer"),
    ]),
    ("nfl_prop", "kalshi_ticker", STAND_IN_SEP14, [
        ("KXNFLRACE-26SEP14DENKC-35", "kalshi", "open", NFL_PUBLISHED,
         "football"),
    ]),
]

#: Events whose commence_time the repair must leave exactly where it found it.
_MUST_NOT_MOVE = (
    "espn_event",
    "no_source_event",
    "closed_market",
    "backstop_market",
    "outright_market",
)

#: Events the repair must move, and to what.
_MUST_MOVE = {
    "refines": PUBLISHED,
    "two_markets": PUBLISHED,        # ORDER BY external_id -> AAAZZZ wins
    "itf_next_day": ITF_PUBLISHED,
    "soccer_fixture": LIGUE1_PUBLISHED,
    "nfl_prop": NFL_PUBLISHED,
}


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema. Function-scoped for the reason
    `test_tennis_commence_predicate_real_postgres.py` records: `pytest.ini`
    leaves `asyncio_default_fixture_loop_scope` unset, so a module-scoped async
    fixture would outlive the loop that made its engine."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


async def _seed(conn) -> dict[str, int]:
    """Insert the corpus. Returns `{key: events.id}`.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status`
    carry a **client-side `default=`**, applied by the ORM and invisible to a
    raw INSERT — omitting one raises `NotNullViolation` rather than taking the
    default. `tests/test_pg_gate_seed_completeness.py` parses these statements
    against live ORM metadata and this file is registered in its `COVERED`
    tuple, so the check is on the real statement rather than a copied list.
    """
    sport_id = (
        await conn.execute(
            text(
                "INSERT INTO sports (key, name, active) "
                "VALUES ('tennis_atp', 'ATP', true) RETURNING id"
            )
        )
    ).scalar_one()

    ids: dict[str, int] = {}
    for key, event_source, event_commence, markets in _EVENTS:
        event_id = (
            await conn.execute(
                text(
                    "INSERT INTO events "
                    "(sport_id, home_team_name, away_team_name, commence_time, "
                    " commence_time_source, status) "
                    "VALUES (:sid, :home, :away, :ct, :src, 'scheduled') RETURNING id"
                ),
                {
                    "sid": sport_id,
                    "home": f"{key} home",
                    "away": f"{key} away",
                    "ct": event_commence,
                    "src": event_source,
                },
            )
        ).scalar_one()
        ids[key] = event_id

        for ext, source, status, market_commence, sport in markets:
            await conn.execute(
                text(
                    "INSERT INTO futures_markets "
                    "(source, external_id, name, category, mutually_exclusive, "
                    " status, llm_sport_category, commence_time, event_id) "
                    "VALUES (:source, :ext, :name, 'championship', true, "
                    "        :status, :sport, :ct, :eid)"
                ),
                {
                    "source": source,
                    "ext": ext,
                    "name": f"{key} market",
                    "status": status,
                    "sport": sport,
                    "ct": market_commence,
                    "eid": event_id,
                },
            )

    return ids


def _install_real_session(monkeypatch, engine):
    """Point the production driver at the real server.

    The only seam `_refine_stand_in_event_starts` has is `get_task_session`, so
    the function under test is otherwise untouched — its SQL, its loop, its
    dedupe and its commit are production's.
    """
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    import app.tasks.kalshi as kalshi_task

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def _session():
        async with maker() as session:
            yield session

    monkeypatch.setattr(kalshi_task, "get_task_session", _session)


async def _read_back(engine, ids):
    """Read every event's start on a SEPARATE connection — what another process
    would see, which is the only thing "committed" can mean here."""
    out = {}
    async with engine.connect() as conn:
        for key, event_id in ids.items():
            row = (
                await conn.execute(
                    text(
                        "SELECT commence_time, commence_time_source, status "
                        "FROM events WHERE id = :id"
                    ),
                    {"id": event_id},
                )
            ).one()
            out[key] = row
    return out


# ---------------------------------------------------------------------------
# the driver
# ---------------------------------------------------------------------------

@needs_postgres
async def test_the_repair_moves_only_the_stand_ins_and_commits_the_move(
    pg_engine, monkeypatch
):
    from app.tasks.kalshi import _refine_stand_in_event_starts
    from app.utils.event_completion import KALSHI_OCCURRENCE_COMMENCE_SOURCE

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)
    moved = await _refine_stand_in_event_starts()

    # Events moved, not rows examined: `two_markets` contributes ONE.
    assert moved == len(_MUST_MOVE), moved

    after = await _read_back(pg_engine, ids)

    for key, expected in _MUST_MOVE.items():
        assert after[key].commence_time == expected, key
        assert after[key].commence_time_source == KALSHI_OCCURRENCE_COMMENCE_SOURCE, key

    for key in _MUST_NOT_MOVE:
        original = next(e[2] for e in _EVENTS if e[0] == key)
        original_source = next(e[1] for e in _EVENTS if e[0] == key)
        assert after[key].commence_time == original, key
        assert after[key].commence_time_source == original_source, key


@needs_postgres
async def test_the_repair_never_writes_status(pg_engine, monkeypatch):
    """Promotion stays the promotion gate's decision, asked of a real time.
    A repair that also flipped `status` would settle unscored rows at the
    sport's maximum duration — the q076 failure this ship exists to end, not
    to relocate."""
    from app.tasks.kalshi import _refine_stand_in_event_starts

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)
    await _refine_stand_in_event_starts()

    after = await _read_back(pg_engine, ids)
    assert {r.status for r in after.values()} == {"scheduled"}


@needs_postgres
async def test_a_second_run_is_a_no_op(pg_engine, monkeypatch):
    """The poll runs this every cycle. Once an event carries
    `kalshi_occurrence` it is no longer in `DERIVED_COMMENCE_SOURCES`, so the
    SQL cannot select it again — the repair converges instead of rewriting the
    same rows forever (which is the #2020 shape from the other end)."""
    from app.tasks.kalshi import _refine_stand_in_event_starts

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)
    first = await _refine_stand_in_event_starts()
    before = await _read_back(pg_engine, ids)
    second = await _refine_stand_in_event_starts()
    after = await _read_back(pg_engine, ids)

    assert first == len(_MUST_MOVE)
    assert second == 0
    assert {k: v.commence_time for k, v in before.items()} == {
        k: v.commence_time for k, v in after.items()
    }


@needs_postgres
async def test_the_derived_array_binds_through_the_real_driver(pg_engine):
    """`= ANY(:derived)` with a Python list against a `varchar` column, and a
    NULL row that must not match. Executed as its own statement so a bind
    failure is attributed here rather than surfacing as "the repair moved 0"."""
    from app.utils.event_completion import DERIVED_COMMENCE_SOURCES

    async with pg_engine.begin() as conn:
        await _seed(conn)

    async with pg_engine.connect() as conn:
        selected = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM events "
                    "WHERE commence_time_source = ANY(:derived)"
                ),
                {"derived": sorted(DERIVED_COMMENCE_SOURCES)},
            )
        ).scalar_one()

    expected = sum(1 for e in _EVENTS if e[1] in DERIVED_COMMENCE_SOURCES)
    assert selected == expected, (selected, expected)
    # ...and the NULL row is genuinely excluded rather than counted.
    assert any(e[1] is None for e in _EVENTS)


# ---------------------------------------------------------------------------
# two-armed: the mutated shapes must do observable damage
# ---------------------------------------------------------------------------

@needs_postgres
async def test_the_unscoped_query_redates_events_for_matches_already_over(
    pg_engine,
):
    """Drop `AND fm.status = 'open'` and the damage is real and invisible to
    every pure test in the tree, because `_stand_in_refinement_target` never
    sees a status. Without this arm a green run is equally consistent with
    "the corpus has no closed row in it"."""
    async with pg_engine.begin() as conn:
        await _seed(conn)

    async with pg_engine.connect() as conn:
        swept = (
            await conn.execute(
                text("""
                    SELECT fm.external_id
                    FROM events e
                    JOIN futures_markets fm ON fm.event_id = e.id
                    WHERE e.commence_time_source = ANY(:derived)
                      AND fm.source = 'kalshi'
                      AND fm.commence_time IS NOT NULL
                """),
                {"derived": ["kalshi_ticker"]},
            )
        ).scalars().all()

    assert "KXATPMATCH-26SEP07CLOCLO" in swept, (
        "the closed market must be swept up by the unpredicated query, or the "
        "status clause has nothing to be load-bearing about"
    )


# ---------------------------------------------------------------------------
# the composition — two writers, one post-loop block, one column each
# ---------------------------------------------------------------------------

async def _read_markets(engine, externals):
    out = {}
    async with engine.connect() as conn:
        for ext in externals:
            out[ext] = (
                await conn.execute(
                    text(
                        "SELECT commence_time FROM futures_markets "
                        "WHERE external_id = :ext"
                    ),
                    {"ext": ext},
                )
            ).scalar_one()
    return out


@needs_postgres
async def test_both_post_loop_fixups_in_the_shipped_order(pg_engine, monkeypatch):
    """The assertion neither branch that raced here could make on its own.

    #3532 and #3488/#3544 were the same ship built twice, and INTEGRATOR-232's
    question — are these two writers complementary or redundant? — could not be
    answered by either test suite, because each drove ONE of them. This drives
    both, in the order `_poll_kalshi_markets` calls them, against real Postgres,
    and asserts the END state of both columns:

    * `refines` — the market already holds the venue's 18:00Z. The market-side
      fix-up must LEAVE it (the #3488 `current_commence` guard); if it re-dates
      it to the ticker midnight, the refiner then measures a 0-minute move and
      the event page keeps the wrong day. That is the exact live regression
      #3532 documented, and only the composition can see it.
    * `backstop_market` — the market is still on the +14d close. The market-side
      fix-up pulls it back to the ticker day; the event, already on that day,
      correctly does not move. Convergence, not a fight.
    * `soccer_fixture` — `llm_sport_category='soccer'`, so the tennis-scoped
      market fix-up is blind to it while the widened event-side gate reaches
      it. This is what says #3562's classifier widening did NOT widen the
      market-side re-dater with it.
    """
    from app.tasks.kalshi import (
        _fix_tennis_commence_times,
        _refine_stand_in_event_starts,
    )
    from app.utils.event_completion import KALSHI_OCCURRENCE_COMMENCE_SOURCE

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)

    # The shipped order. Reversing these two lines is what the ordering guard
    # in tests/test_stand_in_event_start_refinement.py forbids; this is what
    # the order is FOR.
    await _fix_tennis_commence_times()
    await _refine_stand_in_event_starts()

    markets = await _read_markets(
        pg_engine,
        [
            "KXATPMATCH-26SEP07ZVEDAR",
            "KXATPMATCH-26SEP07FARFAR",
            "KXLIGUE1GAME-26SEP20OLMPSG",
        ],
    )
    events = await _read_back(pg_engine, ids)

    # 1. the venue hour survives the market-side fix-up...
    assert markets["KXATPMATCH-26SEP07ZVEDAR"] == PUBLISHED
    # ...and reaches the field the page renders.
    assert events["refines"].commence_time == PUBLISHED
    assert events["refines"].commence_time_source == KALSHI_OCCURRENCE_COMMENCE_SOURCE

    # 2. the backstop market is pulled back to its ticker day, and the event —
    #    already there — is left alone rather than dragged a fortnight out.
    assert markets["KXATPMATCH-26SEP07FARFAR"] == STAND_IN_SEP07
    assert events["backstop_market"].commence_time == STAND_IN_SEP07
    assert events["backstop_market"].commence_time_source == "kalshi_ticker"

    # 3. the soccer market is untouched by the tennis-scoped writer and its
    #    event still gets the published hour.
    assert markets["KXLIGUE1GAME-26SEP20OLMPSG"] == LIGUE1_PUBLISHED
    assert events["soccer_fixture"].commence_time == LIGUE1_PUBLISHED


@needs_postgres
async def test_the_composition_breaks_if_the_market_writer_stops_preserving(
    pg_engine, monkeypatch
):
    """The two-armed half of the test above.

    Neutralise #3488's `current_commence` guard — the one line that says "a
    market already off the backstop is not on the backstop" — and the market
    side re-dates 18:00Z back to midnight, after which the refiner measures a
    0-minute move and refuses. The event page keeps saying the previous
    evening. If this arm does not go red, the composition test above is
    agreeing with itself.
    """
    import app.tasks.kalshi as kalshi_task

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)

    real = kalshi_task._tennis_commence_target

    def _no_preserve(external_id, event_commence, current_commence=None):
        # Exactly the pre-#3488 shape: decide without consulting what the
        # market already holds.
        return real(external_id, event_commence, None)

    monkeypatch.setattr(kalshi_task, "_tennis_commence_target", _no_preserve)

    await kalshi_task._fix_tennis_commence_times()
    await kalshi_task._refine_stand_in_event_starts()

    markets = await _read_markets(pg_engine, ["KXATPMATCH-26SEP07ZVEDAR"])
    events = await _read_back(pg_engine, ids)

    assert markets["KXATPMATCH-26SEP07ZVEDAR"] == STAND_IN_SEP07, (
        "with the guard neutralised the market MUST be clobbered back to "
        "midnight — otherwise this arm proves nothing about it"
    )
    assert events["refines"].commence_time == STAND_IN_SEP07
    assert events["refines"].commence_time_source == "kalshi_ticker"


@needs_postgres
async def test_without_the_dated_fixture_gate_an_outright_moves_a_fortnight(
    pg_engine, monkeypatch
):
    """Neutralise gate 2 and the outright's event is dragged from Sep 7 to the
    +14d settlement close. Asserted by driving the REAL rail with the gate
    stubbed to True, so what is proved is that the production call site
    consults it — not that a re-implementation would have."""
    import app.tasks.kalshi as kalshi_task

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)
    monkeypatch.setattr(kalshi_task, "_is_dated_fixture_ticker", lambda _t: True)

    # The window still refuses a +336h move, so widen it too: the two bounds
    # are independent and this arm is about gate 2.
    monkeypatch.setattr(
        kalshi_task, "_STAND_IN_REFINEMENT_MAX", timedelta(days=30)
    )
    await kalshi_task._refine_stand_in_event_starts()

    after = await _read_back(pg_engine, ids)
    assert after["outright_market"].commence_time == BACKSTOP, (
        "with the gates neutralised the outright MUST move — otherwise this "
        "arm proves nothing about them"
    )


# ---------------------------------------------------------------------------
# CERT-2087's required regression — the row the poll never reaches
# ---------------------------------------------------------------------------

#: The Ligue 1 fixture from #3562, as production actually holds it: ingested
#: days ago, market on the +2d3h settlement close, event on ticker midnight.
#:
#: 🔴 ANCHORED TO THE CLOCK, DELIBERATELY, AND OFFSET FIRST (gotcha #44). The
#: refresh's candidate query has a ±21-day horizon — the floor half of gotcha
#: #41, without which an oldest-first sweep spends its budget on last season.
#: A literal `2026-09-11` would pass today and then rot silently out of the
#: horizon in three weeks' time, turning this regression into a test that
#: cannot fail. Offset from now, THEN truncate to midnight; no branch on the
#: clock anywhere, so all 12 faked clocks in `scripts/clock_sweep.py` agree.
_REFRESH_STAND_IN = (
    datetime.now(UTC) + timedelta(days=5)
).replace(hour=0, minute=0, second=0, microsecond=0)
#: The venue's shape, measured on the real fixture 2026-09-06 (notice 26):
#: `KXLIGUE1GAME-26SEP11RENOLM` occurrence +21h45m, close +3d 0h45m.
_REFRESH_OCCURRENCE = _REFRESH_STAND_IN + timedelta(hours=21, minutes=45)
_REFRESH_CLOSE = _REFRESH_STAND_IN + timedelta(days=3, minutes=45)
_REFRESH_TICKER = (
    "KXLIGUE1GAME-"
    + _REFRESH_STAND_IN.strftime("%y%b%d").upper()
    + "RENOLM"
)
_REFRESH_OCC_ISO = _REFRESH_OCCURRENCE.strftime("%Y-%m-%dT%H:%M:%SZ")
_REFRESH_CLOSE_ISO = _REFRESH_CLOSE.strftime("%Y-%m-%dT%H:%M:%SZ")
_REFRESH_VENUE_PAYLOAD = {
    "KXLIGUE1GAME": [{
        "ticker": _REFRESH_TICKER + "-REN",
        "event_ticker": _REFRESH_TICKER,
        "occurrence_datetime": _REFRESH_OCC_ISO,
        "close_time": _REFRESH_CLOSE_ISO,
    }],
}


class _FakeVenue:
    """Kalshi's `/markets?series_ticker=...` payload, verbatim in shape.

    ONLY the HTTP call is faked. `parse_markets` is delegated to the REAL
    `KalshiAPIService`, so the payload below goes through production's own
    parser — which is the point: #3569 is the incident where the venue changed
    its key set and a raw reader went dark with no error. A fake that also
    faked the parse would agree with itself about exactly that.

    Records what it was asked for, so the test can assert the task reads ONE
    request per series rather than one per market — the reason the candidate
    query groups by series at all.
    """

    def __init__(self, payload, raise_on=()):
        from app.services.kalshi_api import KalshiAPIService

        self.payload = payload
        self.raise_on = set(raise_on)
        self.asked: list[str] = []
        self._real = KalshiAPIService()

    async def get_markets(self, status=None, series_ticker=None, limit=None,
                          cursor=None, event_ticker=None):
        self.asked.append(series_ticker)
        if series_ticker in self.raise_on:
            raise RuntimeError("429 Too Many Requests")
        return list(self.payload.get(series_ticker, [])), None

    def parse_markets(self, raw):
        return self._real.parse_markets(raw)


async def _seed_already_ingested(conn) -> int:
    """One dated fixture as an EXISTING row, plus the linkage the repair needs.

    `volume_updated_at` is deliberately days old: this row is exactly what the
    discovery loop's new-first ordering leaves behind.
    """
    sport_id = (
        await conn.execute(
            text(
                "INSERT INTO sports (key, name, active) "
                "VALUES ('soccer_france_ligue_one', 'Ligue 1', true) RETURNING id"
            )
        )
    ).scalar_one()

    event_id = (
        await conn.execute(
            text(
                "INSERT INTO events "
                "(sport_id, home_team_name, away_team_name, commence_time, "
                " commence_time_source, status) "
                "VALUES (:sid, 'Stade Rennais', 'Marseille', :ct, "
                "        'kalshi_ticker', 'scheduled') RETURNING id"
            ),
            {"sid": sport_id, "ct": _REFRESH_STAND_IN},
        )
    ).scalar_one()

    await conn.execute(
        text(
            "INSERT INTO futures_markets "
            "(source, external_id, name, category, mutually_exclusive, status, "
            " llm_sport_category, commence_time, event_id, volume_updated_at) "
            "VALUES ('kalshi', :ext, 'Rennes vs Marseille', 'championship', true, "
            "        'open', 'soccer', :ct, :eid, :touched)"
        ),
        {
            "ext": _REFRESH_TICKER,
            "ct": _REFRESH_CLOSE,
            "eid": event_id,
            "touched": datetime.now(UTC) - timedelta(days=5),
        },
    )
    return event_id


def _install_fake_venue(monkeypatch, venue):
    import app.services.kalshi_api as kalshi_api

    monkeypatch.setattr(kalshi_api, "KalshiAPIService", lambda *a, **k: venue)


@needs_postgres
async def test_the_refresh_reaches_a_row_the_poll_never_will(
    pg_engine, monkeypatch
):
    """CERT-2087's regression. Fails on the pre-repair code, three ways.

    The setup is production's, not a convenience: the row is ALREADY ingested
    (`volume_updated_at` five days old), so the discovery loop's new-first
    ordering never revisits it — measured at zero existing events on 24 of 24
    beats (#3518). Its market therefore still holds the +2d3h settlement close,
    and `_refine_stand_in_event_starts` — living in the poll's own
    deadline-guarded post-loop remainder — is *correct* to refuse it, because
    +72h45m is far outside the 36h event window.

    So neither existing writer can move this row, and both are behaving as
    designed. The refresh is the third path, and it must land all three:
    the market, the Event, and the value the event API reads back.
    """
    from app.tasks.kalshi import (
        _refine_stand_in_event_starts,
        _refresh_dated_fixture_starts,
    )
    from app.utils.event_completion import KALSHI_OCCURRENCE_COMMENCE_SOURCE

    async with pg_engine.begin() as conn:
        event_id = await _seed_already_ingested(conn)

    _install_real_session(monkeypatch, pg_engine)

    # 1. THE CONTROL: the shipped post-loop repair, run on this row, does
    #    nothing — and is right not to. Without this arm the test below is
    #    equally consistent with "the poll would have fixed it anyway".
    assert await _refine_stand_in_event_starts() == 0
    async with pg_engine.connect() as conn:
        assert (await conn.execute(
            text("SELECT commence_time FROM events WHERE id = :id"),
            {"id": event_id},
        )).scalar_one() == _REFRESH_STAND_IN

    # 2. the refresh, driven through the same seam the scheduled task uses.
    venue = _FakeVenue(_REFRESH_VENUE_PAYLOAD)
    _install_fake_venue(monkeypatch, venue)

    stats = await _refresh_dated_fixture_starts()

    assert venue.asked == ["KXLIGUE1GAME"], venue.asked
    assert stats["markets_moved"] == 1, stats
    assert stats["events_moved"] == 1, stats

    # 3. read back on a SEPARATE connection — what another process sees.
    async with pg_engine.connect() as conn:
        market_ct = (await conn.execute(
            text("SELECT commence_time FROM futures_markets "
                 "WHERE external_id = :ext"),
            {"ext": _REFRESH_TICKER},
        )).scalar_one()
        event_row = (await conn.execute(
            text("SELECT commence_time, commence_time_source FROM events "
                 "WHERE id = :id"),
            {"id": event_id},
        )).one()

    assert market_ct == _REFRESH_OCCURRENCE
    assert event_row.commence_time == _REFRESH_OCCURRENCE
    assert event_row.commence_time_source == KALSHI_OCCURRENCE_COMMENCE_SOURCE


@needs_postgres
async def test_what_the_event_api_reads_back_is_the_published_hour(
    pg_engine, monkeypatch
):
    """The third clause of the regression: the value the PAGE gets.

    `GET /api/events/{id}` loads the row through the ORM and serves
    `commence_time=event.commence_time` (`_format_event`). This asserts that
    ORM read against the real server on a fresh session — the same projection
    the route performs — rather than raw SQL, because an ORM identity-map or
    expiry problem is invisible to a `text()` SELECT and would be exactly the
    kind of thing to survive every assertion above.

    It is a projection assertion, not an HTTP call: this repo has no real-
    Postgres harness for the events router, and inventing one blind (there is
    no local PostgreSQL in the agent sandbox, so it could not be run before
    CI) would be a worse risk than stating plainly what is proved. The
    remaining, unproved gap is the route's own serialisation, which is pinned
    by source below and by `tests/integration/test_route_events_seeded.py`.
    """
    import inspect

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.models import Event

    async with pg_engine.begin() as conn:
        event_id = await _seed_already_ingested(conn)

    _install_real_session(monkeypatch, pg_engine)
    _install_fake_venue(monkeypatch, _FakeVenue(_REFRESH_VENUE_PAYLOAD))

    from app.tasks.kalshi import _refresh_dated_fixture_starts
    await _refresh_dated_fixture_starts()

    maker = async_sessionmaker(pg_engine, class_=AsyncSession)
    async with maker() as read_session:
        event = await read_session.get(Event, event_id)
        assert event is not None
        assert event.commence_time == _REFRESH_OCCURRENCE

    # ...and the route really does serve that attribute rather than deriving
    # its own start from a ticker or a market.
    import app.routes.events as events_route

    src = inspect.getsource(events_route._format_event)
    assert "commence_time=event.commence_time" in src

    # The detail cache must EXPIRE, or a repaired row would be served stale
    # until the dyno restarted. 300s is the bound this ship inherits.
    assert 0 < events_route._EVENT_DETAIL_DEFAULT_TTL <= 900


@needs_postgres
async def test_a_rate_limited_series_is_skipped_not_recorded_as_no_occurrence(
    pg_engine, monkeypatch
):
    """A 429 is a SKIP, never a verdict.

    The failure this forbids is the expensive one: writing "the venue published
    no start" because the venue declined to answer. The row must be left
    exactly as found, so the next run — which sorts most-stale-first — picks it
    up first.
    """
    from app.tasks.kalshi import _refresh_dated_fixture_starts

    async with pg_engine.begin() as conn:
        event_id = await _seed_already_ingested(conn)

    _install_real_session(monkeypatch, pg_engine)
    venue = _FakeVenue({}, raise_on={"KXLIGUE1GAME"})
    _install_fake_venue(monkeypatch, venue)

    stats = await _refresh_dated_fixture_starts()

    assert venue.asked == ["KXLIGUE1GAME"]
    assert stats["series_failed"] == 1
    assert stats["markets_moved"] == 0 and stats["events_moved"] == 0

    async with pg_engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT e.commence_time AS ec, fm.commence_time AS mc "
                 "FROM events e JOIN futures_markets fm ON fm.event_id = e.id "
                 "WHERE e.id = :id"),
            {"id": event_id},
        )).one()

    assert row.ec == _REFRESH_STAND_IN
    assert row.mc == _REFRESH_CLOSE


@needs_postgres
async def test_the_refresh_converges_and_stops_selecting_what_it_fixed(
    pg_engine, monkeypatch
):
    """It runs every two hours forever. A second pass must be a no-op.

    The mechanism is not a flag: writing `kalshi_occurrence` takes the event
    out of `DERIVED_COMMENCE_SOURCES`, so the candidate query cannot see it
    again. Asserted by running twice and requiring the venue not to be asked
    the second time — the cheap proof that the CANDIDATE set shrank, rather
    than the write being re-applied to the same value.
    """
    from app.tasks.kalshi import _refresh_dated_fixture_starts

    async with pg_engine.begin() as conn:
        await _seed_already_ingested(conn)

    _install_real_session(monkeypatch, pg_engine)
    venue = _FakeVenue(_REFRESH_VENUE_PAYLOAD)
    _install_fake_venue(monkeypatch, venue)

    first = await _refresh_dated_fixture_starts()
    second = await _refresh_dated_fixture_starts()

    assert first["events_moved"] == 1
    assert second["events_moved"] == 0
    assert venue.asked == ["KXLIGUE1GAME"], (
        "the second run must not even ask the venue — if it does, the event is "
        "still in the candidate set and this task rewrites the same row forever"
    )
