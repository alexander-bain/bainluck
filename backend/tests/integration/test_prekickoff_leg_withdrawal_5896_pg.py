"""#5896's LEG-grain pre-kick-off withdrawal, executed against real PostgreSQL.

## why this gate exists, stated as the gap it closes

`5896-CLEAR-ANSWERED-LEGS-IN-MIXED-BOOKS-WITHOUT-HARMING-LIVE-SIBLINGS` makes
exactly one promise in its name: on a MIXED book — some legs answered at the
venue, some still trading — the answered leg's stored artifact goes and **the
trading sibling's real price stays**. That promise lives entirely in one clause
of one statement, ``AND fo.external_id = :external_id``.

`tests/test_linked_books_stop_quoting_a_settled_prekickoff_market_5896.py`
drives the writer against a RECORDING fake session: it asserts which statement
object was issued and with which bound parameters, and executes no SQL. That is
the right instrument for "did the writer decide correctly", and it is measured:
deleting the leg-grain call kills two of its guards.

But it cannot see what the statement DOES. Measured, on this branch, before this
file existed — delete `AND fo.external_id = :external_id`, making the leg
statement market-grain again and re-introducing the precise harm the ship's name
refuses:

    test_the_trading_sibling_keeps_its_real_price ......... PASSED
    test_the_leg_statement_differs_from_its_sibling ....... FAILED

**One text guard failed and the behavioural sibling-safety guard did not.** The
headline safety property was defended by a string comparison — a guard that
pins the intent and can never observe the row. `_bound_values(...)` reports the
parameters the writer passed; whether the UPDATE those parameters drive reaches
one leg or the whole ladder is the server's answer and nobody was asking it.

So this gate executes **production's own statement objects**, imported, never a
copy: `_KALSHI_WITHDRAW_PRE_KICKOFF_LEG_SQL` and — in the two-armed arm below —
its market-grain sibling `_KALSHI_WITHDRAW_PRE_KICKOFF_SQL`. Nothing here can
drift out of step with the writer, because there is nothing here to drift.

## what only a server can decide

1. **The grain.** Whether the UPDATE touches one leg or every rung of the ladder
   is what the WHERE clause evaluates, not what the caller intended.
2. **`fo.market_id = :market_id`** alongside the external_id. A Kalshi ticker is
   unique within a book, not across the table; the `decoy` row below carries the
   target's exact ticker on a different market and must survive.
3. **The two pre-kick-off clauses, separately.** `e.status = 'scheduled'` and
   `e.commence_time > NOW()` are not the same test. `past_sched` and `completed`
   below each satisfy one and fail the other, so neither clause can be deleted
   without a row noticing.
4. **`fo.current_probability IS NOT NULL`** over three-valued logic — the
   idempotence the hourly pass relies on to report a row it actually changed.
5. **Whether the UPDATE was COMMITTED.** Every assertion reads back on a
   SEPARATE connection, so what is asserted is what another process would see.

## the corpus, and what each row can fail on

One mixed book, then one control per clause. Every control carries the target's
own ticker where it can, so a control that survives does so because of the
clause under test and not because it was unrecognisable.

* **`mixed` / `SAN`** — the target: answered at the venue, price stored by an
  earlier hour, on an event our own row says has not kicked off. Seeded
  ``is_winner = true``, because the venue HAS answered it — the statement
  deliberately carries no `is_winner` exclusion, and this row is what makes that
  absence load-bearing rather than merely undisputed.
* **`mixed` / `ALA`** — the trading sibling. The whole ship. Its price must be
  exactly where it was seeded.
* **`mixed` / `NUL`** — a leg already withdrawn (`current_probability IS NULL`).
  Must not be matched and must not be counted.
* **`decoy`** — a DIFFERENT market on the same event, carrying `SAN`'s exact
  ticker, and otherwise a perfectly valid target. Catches a statement that drops
  `fo.market_id`: without that clause the `fo`/`fm` correlation is gone, the
  UPDATE degenerates to a cross join filtered only on the OTHER market's event,
  and every leg anywhere holding that ticker goes with it.
* **`live_evt`** — event `status='live'`, kicked off an hour ago. Its settled
  leg's price is a CLOSING LINE that calibration banks (gotcha #21); withdrawing
  it is the over-reach `#5896`'s own after-check watched for.
* **`past_sched`** — `status='scheduled'` but `commence_time` in the past. Fails
  only the clock clause.
* **`completed`** — `status='completed'` but `commence_time` in the future.
  Fails only the status clause.

## two-armed

`test_the_market_grain_sibling_would_take_the_trading_leg_down` executes the
market-grain statement against the same seeded book and REQUIRES the damage to
be observable. Without it a green run is equally consistent with "this corpus
has no mixed book in it", and the leg clause's necessity would be
unfalsifiable — which is exactly the state the fake-session suite was in.

Opt-in on `SEARCH_TEST_DATABASE_URL`, like its neighbours; CI's `search-recall`
job provides one and its skip-detector stops an unrun gate reading as a pass.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

#: Applied per-test rather than as a module-wide `pytestmark`, deliberately.
#: The premise arm below needs no database, and under a module-wide mark it
#: would be SKIPPED everywhere a server is absent — which is every local run and
#: every CI job but one. The text guard it carries is the only thing standing
#: between the two-armed arm and a pair of unrelated statements, so it is the
#: last arm that should be conditional. (It would also inherit `asyncio` and
#: warn, being a plain function.)
needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the #5896 leg-grain withdrawal "
        "gate (CI job `search-recall` provides one)"
    ),
)

#: Every DB arm carries both; the premise arm carries neither.
pg_test = (needs_postgres, pytest.mark.asyncio)


def _pg(fn):
    for mark in pg_test:
        fn = mark(fn)
    return fn

# --------------------------------------------------------------------------
# ids
# --------------------------------------------------------------------------
# Explicit, and namespaced to this ship, for the reason
# `test_folded_market_sport_net_6221_pg.py` paid for: `search-recall` shares ONE
# database across every gate, earlier gates seed `sports` with explicit ids
# without advancing the sequence, and `ON CONFLICT (key) DO NOTHING` draws
# `nextval` BEFORE it evaluates the conflict — so a genuinely new key dies on
# `sports_pkey`. Naming our own ids sidesteps the sequence entirely.

SPORT_ID = 58960001
EVENT_FUTURE = 58960010  # scheduled, kicks off in 6h  — the pre-kick-off shape
EVENT_LIVE = 58960011  # live, kicked off an hour ago
EVENT_PAST_SCHED = 58960012  # still 'scheduled', but the clock has passed
EVENT_COMPLETED = 58960013  # 'completed', yet dated in the future

MARKET_MIXED = 58960100
MARKET_DECOY = 58960101
MARKET_LIVE = 58960102
MARKET_PAST_SCHED = 58960103
MARKET_COMPLETED = 58960104

#: The answered leg's ticker. Deliberately reused by every control that can hold
#: it, so no control survives merely by being unrecognisable.
SAN = "KXEREDIVISIETOTAL-26SEP13EXCFCU-SAN"
#: The trading sibling on the same ladder — the row the ship is named after.
ALA = "KXEREDIVISIETOTAL-26SEP13EXCFCU-ALA"
#: A leg an earlier hour already withdrew.
NUL = "KXEREDIVISIETOTAL-26SEP13EXCFCU-NUL"

#: Stored prices, in the column's own NUMERIC terms.
SETTLED_PRICE = Decimal("0.9900")
SIBLING_PRICE = Decimal("0.4200")
SETTLED_ODDS = -9900
SIBLING_ODDS = 138

#: (market_id, event_id, key)
_MARKETS = [
    (MARKET_MIXED, EVENT_FUTURE, "mixed"),
    (MARKET_DECOY, EVENT_FUTURE, "decoy"),
    (MARKET_LIVE, EVENT_LIVE, "live_evt"),
    (MARKET_PAST_SCHED, EVENT_PAST_SCHED, "past_sched"),
    (MARKET_COMPLETED, EVENT_COMPLETED, "completed"),
]

#: Every (market, leg) that holds a price the statement must NOT take.
_MUST_SURVIVE = [
    (MARKET_MIXED, ALA, SIBLING_PRICE, SIBLING_ODDS),
    (MARKET_DECOY, SAN, SETTLED_PRICE, SETTLED_ODDS),
    (MARKET_LIVE, SAN, SETTLED_PRICE, SETTLED_ODDS),
    (MARKET_PAST_SCHED, SAN, SETTLED_PRICE, SETTLED_ODDS),
    (MARKET_COMPLETED, SAN, SETTLED_PRICE, SETTLED_ODDS),
]


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that made its engine.

    `create_all` only, never `drop_all` — the `search-recall` database is shared
    with ~55 sibling gates and this one owns nothing but its own id block.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _clear(conn)

    yield engine

    async with engine.begin() as conn:
        await _clear(conn)
    await engine.dispose()


async def _clear(conn) -> None:
    """Remove only this gate's own id block, in FK order."""
    await conn.execute(
        text("DELETE FROM futures_outcomes WHERE market_id = ANY(:ids)"),
        {"ids": [m for m, _, _ in _MARKETS]},
    )
    await conn.execute(
        text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
        {"ids": [m for m, _, _ in _MARKETS]},
    )
    await conn.execute(
        text("DELETE FROM events WHERE id = ANY(:ids)"),
        {
            "ids": [
                EVENT_FUTURE,
                EVENT_LIVE,
                EVENT_PAST_SCHED,
                EVENT_COMPLETED,
            ]
        },
    )
    await conn.execute(text("DELETE FROM sports WHERE id = :id"), {"id": SPORT_ID})


async def _seed(conn) -> None:
    """Insert the corpus.

    🔴 EVERY NOT NULL COLUMN IS SPELLED OUT, INCLUDING THE ONES THAT LOOK
    OPTIONAL. `sports.active`, `futures_markets.category` / `.mutually_exclusive`
    / `.status` and `events.status` carry a **client-side `default=`** applied by
    the ORM and invisible to a raw INSERT — omitting one does not take the
    default, it raises `NotNullViolation`.
    `tests/test_pg_gate_seed_completeness.py` parses these statements against
    live ORM metadata and this file is registered in its `COVERED` tuple.

    🔴 THE EVENT CLOCKS COME FROM THE SERVER, not from a literal. The statement
    under test says `e.commence_time > NOW()`; a hard-coded timestamp would be a
    correct seed on the day it was written and would quietly stop selecting
    anything later, at which point the withdrawal arm passes having withdrawn
    nothing.
    """
    await conn.execute(
        text("INSERT INTO sports (id, key, name, active) VALUES (:id, :k, :n, true)"),
        {"id": SPORT_ID, "k": f"test_5896_{SPORT_ID}", "n": "Test 5896"},
    )

    for event_id, status, offset in (
        (EVENT_FUTURE, "scheduled", "+6 hours"),
        (EVENT_LIVE, "live", "-1 hour"),
        (EVENT_PAST_SCHED, "scheduled", "-1 hour"),
        (EVENT_COMPLETED, "completed", "+6 hours"),
    ):
        await conn.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                "commence_time, status) VALUES "
                f"(:id, :sid, 'Excelsior 5896', 'Utrecht 5896', NOW() + interval '{offset}', :st)"
            ),
            {"id": event_id, "sid": SPORT_ID, "st": status},
        )

    for market_id, event_id, key in _MARKETS:
        await conn.execute(
            text(
                "INSERT INTO futures_markets (id, event_id, source, external_id, "
                "name, category, mutually_exclusive, status) VALUES "
                "(:id, :eid, 'kalshi', :ext, :name, 'championship', true, 'open')"
            ),
            {
                "id": market_id,
                "eid": event_id,
                "ext": f"KX5896-{key.upper()}",
                "name": f"{key} market 5896",
            },
        )

    # The mixed book: an answered leg, a trading sibling, and one already gone.
    #
    # `is_winner = true` on the answered leg is deliberate. The venue HAS
    # answered it, so that is the honest shape — and the statement carries no
    # `is_winner` exclusion on purpose. Seeding it any other way would leave
    # that documented absence untested.
    await _leg(conn, MARKET_MIXED, SAN, SETTLED_PRICE, SETTLED_ODDS, is_winner=True)
    await _leg(conn, MARKET_MIXED, ALA, SIBLING_PRICE, SIBLING_ODDS, is_winner=None)
    await _leg(conn, MARKET_MIXED, NUL, None, None, is_winner=None)

    # One priced leg per control, carrying the target's own ticker.
    for market_id in (
        MARKET_DECOY,
        MARKET_LIVE,
        MARKET_PAST_SCHED,
        MARKET_COMPLETED,
    ):
        await _leg(
            conn, market_id, SAN, SETTLED_PRICE, SETTLED_ODDS, is_winner=True
        )


async def _leg(conn, market_id, external_id, probability, odds, *, is_winner) -> None:
    await conn.execute(
        text(
            "INSERT INTO futures_outcomes (market_id, external_id, name, "
            "current_probability, current_american_odds, is_winner) VALUES "
            "(:mid, :ext, :name, :p, :o, :w)"
        ),
        {
            "mid": market_id,
            "ext": external_id,
            "name": f"{external_id} leg",
            "p": probability,
            "o": odds,
            "w": is_winner,
        },
    )


async def _read_back(engine) -> dict[tuple[int, str], tuple]:
    """Read stored prices on a SEPARATE connection.

    A value visible only inside the writer's own transaction is not a value
    another process would see, and "did it COMMIT" is half of what this is for.
    """
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT market_id, external_id, current_probability, "
                    "current_american_odds FROM futures_outcomes "
                    "WHERE market_id = ANY(:ids)"
                ),
                {"ids": [m for m, _, _ in _MARKETS]},
            )
        ).all()
    return {(r[0], r[1]): (r[2], r[3]) for r in rows}


def _assert_survivors(stored, *, because):
    for market_id, leg, price, odds in _MUST_SURVIVE:
        assert stored[(market_id, leg)] == (price, odds), (
            f"({market_id}, {leg}) lost its real price — {because}"
        )


# --------------------------------------------------------------------------
# premise
# --------------------------------------------------------------------------
# Stated with no database, so a statement that stops being the shape this gate
# reasons about fails loudly and separately rather than making an arm vacuous.


def test_the_two_statements_differ_by_exactly_the_leg_clause():
    from app.tasks.futures_price_refresh import (
        _KALSHI_WITHDRAW_PRE_KICKOFF_LEG_SQL,
        _KALSHI_WITHDRAW_PRE_KICKOFF_SQL,
    )

    leg = str(_KALSHI_WITHDRAW_PRE_KICKOFF_LEG_SQL)
    market = str(_KALSHI_WITHDRAW_PRE_KICKOFF_SQL)
    assert leg != market
    assert leg.replace("       AND fo.external_id = :external_id\n", "") == market, (
        "the leg statement is its market-grain sibling plus one clause; if that "
        "stopped being true, the two-armed arm below is comparing two unrelated "
        "statements and proves nothing about the grain"
    )


# --------------------------------------------------------------------------
# the statement, executed
# --------------------------------------------------------------------------


@_pg
async def test_the_answered_leg_is_withdrawn_and_its_trading_sibling_is_not(pg_engine):
    """The ship, both halves, on real rows."""
    from app.tasks.futures_price_refresh import _KALSHI_WITHDRAW_PRE_KICKOFF_LEG_SQL

    async with pg_engine.begin() as conn:
        await _seed(conn)

    async with pg_engine.begin() as conn:
        returned = (
            await conn.execute(
                _KALSHI_WITHDRAW_PRE_KICKOFF_LEG_SQL,
                {"market_id": MARKET_MIXED, "external_id": SAN},
            )
        ).fetchall()

    assert len(returned) == 1, (
        f"expected exactly the one answered leg, got {len(returned)} rows — "
        "the count is what the writer reports as "
        "`pre_kickoff_settled_legs_withdrawn`"
    )

    stored = await _read_back(pg_engine)

    # The artifact is gone — BOTH columns, because the ladder renders the odds
    # too and a half-withdrawal is the same lie in different units.
    assert stored[(MARKET_MIXED, SAN)] == (None, None)

    # And the rest of the ladder is untouched. This is the ship's name.
    _assert_survivors(stored, because="the leg clause must confine the withdrawal")

    # The already-withdrawn leg is still NULL and was not in the RETURNING set.
    assert stored[(MARKET_MIXED, NUL)] == (None, None)


@_pg
async def test_it_is_idempotent_on_a_leg_it_already_withdrew(pg_engine):
    """`current_probability IS NOT NULL` is what keeps the hourly pass honest.

    Without it the second run reports a withdrawal it did not perform, and the
    summary counter — the instrument #5771 was read through — starts counting
    hours instead of rows.
    """
    from app.tasks.futures_price_refresh import _KALSHI_WITHDRAW_PRE_KICKOFF_LEG_SQL

    async with pg_engine.begin() as conn:
        await _seed(conn)

    async def _run():
        async with pg_engine.begin() as conn:
            return (
                await conn.execute(
                    _KALSHI_WITHDRAW_PRE_KICKOFF_LEG_SQL,
                    {"market_id": MARKET_MIXED, "external_id": SAN},
                )
            ).fetchall()

    assert len(await _run()) == 1
    assert len(await _run()) == 0, "the second run must report nothing to withdraw"

    stored = await _read_back(pg_engine)
    _assert_survivors(stored, because="a re-run must not widen")


@_pg
@pytest.mark.parametrize(
    "market_id,clause",
    [
        (MARKET_LIVE, "e.status = 'scheduled'"),
        (MARKET_PAST_SCHED, "e.commence_time > NOW()"),
        (MARKET_COMPLETED, "e.status = 'scheduled'"),
    ],
)
async def test_the_statement_refuses_a_leg_outside_the_pre_kickoff_window(
    pg_engine, market_id, clause
):
    """Each control, asked for by its own ticker, refused by one clause.

    `past_sched` and `completed` are the pair that separate the two pre-kick-off
    clauses: each satisfies one and fails the other, so neither can be deleted
    without a row here noticing.

    `decoy` is deliberately NOT in this list. It is a legitimate target when the
    statement is asked for it BY NAME — its own leg, on a pre-kick-off event, is
    exactly what the statement is for. Its job is to survive a call aimed at a
    DIFFERENT market, which is asserted in the withdrawal arm above.
    """
    from app.tasks.futures_price_refresh import _KALSHI_WITHDRAW_PRE_KICKOFF_LEG_SQL

    async with pg_engine.begin() as conn:
        await _seed(conn)

    async with pg_engine.begin() as conn:
        returned = (
            await conn.execute(
                _KALSHI_WITHDRAW_PRE_KICKOFF_LEG_SQL,
                {"market_id": market_id, "external_id": SAN},
            )
        ).fetchall()

    assert returned == [], f"`{clause}` did not refuse market {market_id}"

    stored = await _read_back(pg_engine)
    _assert_survivors(stored, because=f"`{clause}` must hold")


# --------------------------------------------------------------------------
# two-armed: the harm the leg clause exists to prevent, made observable
# --------------------------------------------------------------------------


@_pg
async def test_the_market_grain_sibling_would_take_the_trading_leg_down(pg_engine):
    """Production's OWN market-grain statement, on the same mixed book.

    This is the arm that makes every assertion above mean something. If it
    fails, this corpus has no mixed book in it — no ladder where a settled leg
    and a trading one sit together inside the pre-kick-off window — and
    "the sibling survived" would be true of a row nothing could have reached.

    It also is the ship's central claim, executed rather than argued: the
    market-grain statement could not be spent here, and this is the price it
    would have taken.
    """
    from app.tasks.futures_price_refresh import _KALSHI_WITHDRAW_PRE_KICKOFF_SQL

    async with pg_engine.begin() as conn:
        await _seed(conn)

    async with pg_engine.begin() as conn:
        returned = (
            await conn.execute(
                _KALSHI_WITHDRAW_PRE_KICKOFF_SQL, {"market_id": MARKET_MIXED}
            )
        ).fetchall()

    # Both priced legs of the ladder, not one: the settled leg AND the contract
    # that is still trading.
    assert len(returned) == 2, (
        f"the market-grain statement took {len(returned)} legs off this book — "
        "the corpus is supposed to hold a settled leg and a trading one inside "
        "the window, so this gate's other arms cannot discriminate"
    )

    stored = await _read_back(pg_engine)
    assert stored[(MARKET_MIXED, ALA)] == (None, None), (
        "the trading sibling kept its price under the MARKET-grain statement, "
        "so this corpus cannot show that the leg clause protects anything"
    )
