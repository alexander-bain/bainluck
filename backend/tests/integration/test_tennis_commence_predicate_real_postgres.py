"""The tennis commence_time repair's SQL predicate, against a REAL PostgreSQL.

## why this gate needs a real server

`_fix_tennis_commence_times()` (app/tasks/kalshi.py) is driven in CI today only
by `tests/test_tennis_commence_times.py`, whose `_FakeSession` answers **any**
statement containing ``futures_markets fm`` with a canned row list:

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "SELECT" in sql and "futures_markets fm" in sql:
            return _FakeResult(self._rows)

So the four clauses that decide WHICH production rows get re-dated —

    WHERE fm.source = 'kalshi'
      AND fm.llm_sport_category = 'tennis'
      AND fm.status = 'open'
      AND fm.commence_time IS NOT NULL

— are never evaluated by anything. A row is absent from the repair only because
the test author chose not to put it in the canned list, which is the test
agreeing with itself by construction. Delete any one of those clauses and every
existing test still passes. Both CERT-2020 graders named this independently as
``TENNIS-COMMENCE-SQL-PREDICATE-GUARD``; the honest fix is a real server, not a
better fake, because a fake is what is being doubted.

Five things only a server can decide here:

1. **The population filter.** Whether a `closed` / `polymarket` / basketball /
   NULL-commence row is excluded is the WHERE clause's answer, not the fixture's.
   The `closed` exclusion is the load-bearing one: the docstring's whole
   justification for the repair being safe is that a resolved row's close_time
   has already collapsed to its real settlement instant, so re-dating it would
   invalidate closing lines calibration has banked.

2. **`LEFT JOIN events`.** An unlinked market (`event_id IS NULL`) must still be
   selected, with `event_commence` arriving as NULL. Under an INNER JOIN it
   silently vanishes from the repair — and unlinked is the *common* shape. A
   fake that hands back a tuple per row cannot express a join that dropped it.

3. **`market_id = ANY(:ids)`** over a real integer array through the real
   driver, and **`AND fo.calibration_probability IS NOT NULL`** over
   three-valued logic. The fake records `params["ids"]` and executes neither.

4. **Whether the UPDATE was COMMITTED.** The fake sets a boolean. Every
   assertion below reads back on a *separate connection*, so what is asserted is
   what another process would see.

5. **NUMERIC(7,6) round-tripping.** `calibration_probability` comes back as
   `Decimal`, not float ­— a preserved value has to be compared as one.

There is no local PostgreSQL in the agent sandbox, so CI is where this runs, and
the `search-recall` job's "Verify the gate is actually armed" step is what stops
a skipped gate reading as a passing one.

## the corpus, and what each row can fail on

Nine markets, each paired with the defect it catches:

* **`moves`** — the ordinary bug: open Kalshi tennis, ticker says Sep 7, stored
  commence is Kalshi's +14d settlement backstop. Re-dated; calibration cleared.
* **`event_agrees`** — linked to an Event whose kick-off is inside the ±36h
  window. Takes the Event's *hour*, not the bare ticker midnight. This row is
  the LEFT JOIN's payload: it fails if the join stops returning `e.commence_time`.
* **`event_poisoned`** — linked to an Event itself sitting on the +14d date, so
  outside the window. Ticker date wins. The row that catches a repair which
  copies a poisoned Event date back onto the market.
* **`unlinked_stays`** — open, correct, `event_id IS NULL`. Selected, examined,
  left alone. Catches an INNER JOIN by being invisible to one.
* **`outright`** — `KXWTA-26USO`. Selected by the SQL, refused by
  `_tennis_commence_target`. Its far-future close_time IS its horizon.
* **`already_right`** — inside the 1800s tolerance. **Selected but not fixed**,
  which is the row that separates "matched the predicate" from "entered
  `fixed_ids`" — its calibration must survive.
* **`closed`** — identical to `moves` but `status='closed'`.
* **`other_source`** — identical to `moves` but `source='polymarket'`.
* **`not_tennis`** — identical to `moves` but `llm_sport_category='basketball'`.
* **`null_commence`** — open Kalshi tennis with no commence_time. If it leaked
  past the predicate the driver would raise `TypeError` on
  `m.commence_time - target`, so this row proves that clause is load-bearing in
  the strongest way available: its absence is a crash, not a wrong number.

## two-armed

`test_the_unpredicated_query_sweeps_up_rows_the_repair_must_never_touch` and
`test_the_unscoped_reset_wipes_calibration_the_repair_preserves` execute the
**mutated** shapes against the same seeded server and require the damage to be
observable. Without them a green run is equally consistent with "the corpus has
no discriminating rows in it", and the predicate's necessity would be
unfalsifiable.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres tennis commence "
        "predicate gate (CI job `search-recall` provides one)"
    ),
)

UTC = timezone.utc

#: Kalshi's +14d settlement backstop, i.e. the bug as it appears in production.
BACKSTOP = datetime(2026, 9, 21, 15, 0, tzinfo=UTC)

#: What the ticker actually encodes for the SEP07 corpus.
SEP07 = datetime(2026, 9, 7, tzinfo=UTC)
SEP06 = datetime(2026, 9, 6, tzinfo=UTC)

#: An Event kick-off inside `_TENNIS_EVENT_AGREEMENT_WINDOW` of SEP06.
SEP06_KICKOFF = datetime(2026, 9, 6, 18, 30, tzinfo=UTC)


# --------------------------------------------------------------------------
# premise
# --------------------------------------------------------------------------
# Every DB assertion below is stated in terms of a date this corpus CLAIMS a
# ticker carries. If the parser disagreed, the arms would still pass against
# each other while proving nothing about production. Pinned here, with no
# database, so a parser change fails loudly and separately.

def test_the_corpus_tickers_carry_the_dates_the_corpus_claims():
    from app.tasks.kalshi import _TENNIS_MATCH_SERIES_RE
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    assert extract_game_date_from_ticker("KXWTAMATCH-26SEP07OSARYB") == SEP07
    assert extract_game_date_from_ticker("KXATPMATCH-26SEP06PAUALC") == SEP06
    assert extract_game_date_from_ticker("KXATPDOUBLES-26SEP07ABCDEF") == SEP07

    # The outright is refused by the series allowlist, not by its date.
    assert _TENNIS_MATCH_SERIES_RE.match("KXWTA-26USO") is None

    # The exclusion rows are per-match tickers in perfect health — they are
    # excluded by the WHERE clause and by nothing else. If the parser stopped
    # reading them the exclusion arms would pass for the wrong reason.
    for ticker in (
        "KXWTAMATCH-26SEP07CLORYB",
        "KXWTAMATCH-26SEP07POLRYB",
        "KXWTAMATCH-26SEP07BSKRYB",
        "KXWTAMATCH-26SEP07NULRYB",
    ):
        assert _TENNIS_MATCH_SERIES_RE.match(ticker), ticker
        assert extract_game_date_from_ticker(ticker) == SEP07, ticker

    # `already_right` must sit inside the driver's 1800s tolerance, or it stops
    # being the "selected but not fixed" row and the reset-scope arm goes vacuous.
    assert abs(
        datetime(2026, 9, 6, 0, 10, tzinfo=UTC)
        - extract_game_date_from_ticker("KXATPMATCH-26SEP06RGTALC")
    ) < timedelta(seconds=1800)


# --------------------------------------------------------------------------
# fixture + corpus
# --------------------------------------------------------------------------

@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


#: (key, source, llm_sport_category, status, external_id, commence_time, linked_event_commence)
_MARKETS = [
    ("moves",          "kalshi",     "tennis",     "open",   "KXWTAMATCH-26SEP07OSARYB", BACKSTOP, None),
    ("event_agrees",   "kalshi",     "tennis",     "open",   "KXATPMATCH-26SEP06PAUALC", BACKSTOP, SEP06_KICKOFF),
    ("event_poisoned", "kalshi",     "tennis",     "open",   "KXATPDOUBLES-26SEP07ABCDEF", BACKSTOP, BACKSTOP),
    ("unlinked_stays", "kalshi",     "tennis",     "open",   "KXWTAMATCH-26SEP07NOWRYB", SEP07,    None),
    ("outright",       "kalshi",     "tennis",     "open",   "KXWTA-26USO",              BACKSTOP, None),
    ("already_right",  "kalshi",     "tennis",     "open",   "KXATPMATCH-26SEP06RGTALC", datetime(2026, 9, 6, 0, 10, tzinfo=UTC), None),
    ("closed",         "kalshi",     "tennis",     "closed", "KXWTAMATCH-26SEP07CLORYB", BACKSTOP, None),
    ("other_source",   "polymarket", "tennis",     "open",   "KXWTAMATCH-26SEP07POLRYB", BACKSTOP, None),
    ("not_tennis",     "kalshi",     "basketball", "open",   "KXWTAMATCH-26SEP07BSKRYB", BACKSTOP, None),
    ("null_commence",  "kalshi",     "tennis",     "open",   "KXWTAMATCH-26SEP07NULRYB", None,     None),
]

#: Markets whose commence_time the repair must leave exactly where it found it.
_MUST_NOT_MOVE = (
    "unlinked_stays",
    "outright",
    "already_right",
    "closed",
    "other_source",
    "not_tennis",
    "null_commence",
)

#: A banked calibration figure, in the column's own NUMERIC(7,6) terms.
BANKED = Decimal("0.420000")


async def _seed(conn) -> dict[str, int]:
    """Insert the corpus. Returns `{key: futures_markets.id}`.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `futures_markets.category` / `.mutually_exclusive` / `.status`
    carry a **client-side `default=`**, applied by the ORM and invisible to a raw
    INSERT — omitting one does not take the default, it raises
    `NotNullViolation`. `tests/test_pg_gate_seed_completeness.py` parses these
    statements against live ORM metadata and this file is registered in its
    `COVERED` tuple, so the check is on the real statement rather than a copied
    column list.
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
    for key, source, category, status, ext, commence, event_commence in _MARKETS:
        event_id = None
        if event_commence is not None:
            event_id = (
                await conn.execute(
                    text(
                        "INSERT INTO events "
                        "(sport_id, home_team_name, away_team_name, commence_time, status) "
                        "VALUES (:sid, :home, :away, :ct, 'scheduled') RETURNING id"
                    ),
                    {
                        "sid": sport_id,
                        "home": f"{key} home",
                        "away": f"{key} away",
                        "ct": event_commence,
                    },
                )
            ).scalar_one()

        market_id = (
            await conn.execute(
                text(
                    "INSERT INTO futures_markets "
                    "(source, external_id, name, category, mutually_exclusive, "
                    " status, llm_sport_category, commence_time, event_id) "
                    "VALUES (:source, :ext, :name, 'championship', true, "
                    "        :status, :category, :ct, :eid) RETURNING id"
                ),
                {
                    "source": source,
                    "ext": ext,
                    "name": f"{key} market",
                    "status": status,
                    "category": category,
                    "ct": commence,
                    "eid": event_id,
                },
            )
        ).scalar_one()
        ids[key] = market_id

        # One banked outcome per market, so "was this market's calibration
        # cleared?" is answerable for every row in the corpus.
        await conn.execute(
            text(
                "INSERT INTO futures_outcomes "
                "(market_id, external_id, name, calibration_probability) "
                "VALUES (:mid, :ext, :name, :cal)"
            ),
            {"mid": market_id, "ext": f"{ext}-YES", "name": f"{key} yes", "cal": BANKED},
        )

    # A second outcome on `moves` that is ALREADY NULL: the `IS NOT NULL` guard
    # must simply not match it, rather than erroring or counting it.
    await conn.execute(
        text(
            "INSERT INTO futures_outcomes "
            "(market_id, external_id, name, calibration_probability) "
            "VALUES (:mid, :ext, :name, NULL)"
        ),
        {"mid": ids["moves"], "ext": "KXWTAMATCH-26SEP07OSARYB-NO", "name": "moves no"},
    )

    return ids


def _install_real_session(monkeypatch, engine):
    """Point the production driver at the real server.

    The only seam `_fix_tennis_commence_times` has is `get_task_session`, so the
    function under test is otherwise untouched — its SQL, its loop and its
    commit are production's.
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
    """Read the stored state on a SEPARATE connection.

    A value visible only inside the driver's own transaction is not a value
    another process would see, and "did it COMMIT" is half of what this gate is
    for.
    """
    commence: dict[str, datetime | None] = {}
    calibration: dict[str, list] = {}
    async with engine.connect() as conn:
        for key, mid in ids.items():
            commence[key] = (
                await conn.execute(
                    text("SELECT commence_time FROM futures_markets WHERE id = :id"),
                    {"id": mid},
                )
            ).scalar_one()
            rows = (
                await conn.execute(
                    text(
                        "SELECT calibration_probability FROM futures_outcomes "
                        "WHERE market_id = :id ORDER BY id"
                    ),
                    {"id": mid},
                )
            ).all()
            calibration[key] = [r[0] for r in rows]
    return commence, calibration


def _aware(dt):
    """`TIMESTAMP WITHOUT TIME ZONE` comes back naive; compare in UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# --------------------------------------------------------------------------
# the repair, driven against the real server
# --------------------------------------------------------------------------

@needs_postgres
@pytest.mark.asyncio
async def test_the_real_predicate_selects_only_the_rows_the_repair_may_move(
    pg_engine, monkeypatch
):
    from app.tasks.kalshi import _fix_tennis_commence_times

    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    _install_real_session(monkeypatch, pg_engine)
    fixed = await _fix_tennis_commence_times()

    commence, calibration = await _read_back(pg_engine, ids)

    # Three rows move, and only three: the plain bug, the one that defers to a
    # nearby Event, and the one that refuses a poisoned Event.
    assert fixed == 3, f"expected 3 repairs, got {fixed}"

    assert _aware(commence["moves"]) == SEP07
    assert _aware(commence["event_agrees"]) == SEP06_KICKOFF, (
        "the LEFT JOIN must deliver e.commence_time — an Event inside the ±36h "
        "window owns the hour, the ticker only knows the day"
    )
    assert _aware(commence["event_poisoned"]) == SEP07, (
        "an Event sitting on the +14d date is outside the window and must not "
        "be copied back onto the market"
    )

    # Everything else is exactly where it was seeded.
    seeded = {key: ct for key, _, _, _, _, ct, _ in _MARKETS}
    for key in _MUST_NOT_MOVE:
        assert _aware(commence[key]) == seeded[key], f"{key} was moved and must not be"

    # Calibration is cleared for the three that moved and for nobody else.
    assert calibration["moves"] == [None, None]
    assert calibration["event_agrees"] == [None]
    assert calibration["event_poisoned"] == [None]
    for key in _MUST_NOT_MOVE:
        assert calibration[key] == [BANKED], (
            f"{key} did not move, so its banked calibration must survive"
        )


# --------------------------------------------------------------------------
# two-armed: the mutated shapes, against the same seeded server
# --------------------------------------------------------------------------

@needs_postgres
@pytest.mark.asyncio
async def test_the_unpredicated_query_sweeps_up_rows_the_repair_must_never_touch(
    pg_engine,
):
    """Each WHERE clause, deleted, against the same corpus.

    If this passes and the arm above also passes, the exclusions above were
    decided by the predicate. If this FAILS, the corpus stopped containing a
    row that discriminates and the arm above has gone vacuous — which is the
    outcome a fake session can never report.
    """
    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    base = """
        SELECT fm.id
        FROM futures_markets fm
        LEFT JOIN events e ON e.id = fm.event_id
        WHERE fm.source = 'kalshi'
          AND fm.llm_sport_category = 'tennis'
          AND fm.status = 'open'
          AND fm.commence_time IS NOT NULL
    """

    async with pg_engine.connect() as conn:
        selected = {
            r[0] for r in (await conn.execute(text(base))).all()
        }
        # The real predicate does not see any of the four exclusion rows.
        for key in ("closed", "other_source", "not_tennis", "null_commence"):
            assert ids[key] not in selected, f"{key} is already inside the predicate"

        for key, clause in (
            ("closed", "AND fm.status = 'open'"),
            ("other_source", "AND fm.source = 'kalshi'"),
            ("not_tennis", "AND fm.llm_sport_category = 'tennis'"),
            ("null_commence", "AND fm.commence_time IS NOT NULL"),
        ):
            mutated = base.replace(clause, "")
            assert mutated != base, f"clause not found verbatim: {clause}"
            rows = {r[0] for r in (await conn.execute(text(mutated))).all()}
            assert ids[key] in rows, (
                f"deleting `{clause}` did not admit {key} — this corpus cannot "
                "prove that clause is load-bearing"
            )

        # The LEFT JOIN, made INNER: every unlinked market disappears, including
        # `moves`, the ordinary shape the whole repair exists for.
        inner = base.replace("LEFT JOIN events", "INNER JOIN events")
        assert inner != base
        rows = {r[0] for r in (await conn.execute(text(inner))).all()}
        assert ids["moves"] in selected and ids["moves"] not in rows, (
            "an INNER JOIN must lose the unlinked markets — if it does not, the "
            "LEFT is not load-bearing and this corpus has no unlinked row in it"
        )


@needs_postgres
@pytest.mark.asyncio
async def test_the_unscoped_reset_wipes_calibration_the_repair_preserves(pg_engine):
    """`market_id = ANY(:ids)`, deleted.

    `already_right` and `outright` both MATCH the population filter and are both
    deliberately not repaired. They are the collateral an unscoped reset takes,
    and the reason the driver collects `fixed_ids` rather than reusing the rows
    it scanned.
    """
    async with pg_engine.begin() as conn:
        ids = await _seed(conn)

    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE futures_outcomes fo "
                "SET calibration_probability = NULL "
                "WHERE fo.calibration_probability IS NOT NULL"
            )
        )

    _, calibration = await _read_back(pg_engine, ids)
    for key in ("already_right", "outright", "closed"):
        assert calibration[key] == [None], (
            f"the unscoped reset did not reach {key}, so this corpus cannot show "
            "that scoping the reset to fixed_ids protects anything"
        )
