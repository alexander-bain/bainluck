"""#2637's candidate query, EXECUTED against a real PostgreSQL.

## Why this file has to exist, stated as the defect it caught

The rewrite of `_sync_polymarket_resolved_status` selects its population with

    SELECT DISTINCT <expr> AS eid FROM futures_markets fm WHERE ...
    ORDER BY eid::bigint

and that is not a slow query — it is a **syntax error**. Under `SELECT
DISTINCT`, PostgreSQL requires every `ORDER BY` expression to appear in the
select list, and `eid::bigint` does not. It was caught before merge only because
the query was run by hand against production.

Nothing else would have caught it. The task's unit guards drive the real
function against a recording double that matches on the SQL *string* and returns
fabricated rows, so the statement is never parsed by a database; all 23 passed
against the broken query. And the task wraps its sweep in a broad
`except Exception` that files the failure into `stats["errors"]` — so in
production this would not have crashed. It would have returned a clean summary
saying it resolved nothing, every six hours, forever: **the exact "looks like a
fix, drains 0 rows" outcome #2637 warns its implementer about**, wearing the
costume of a healthy run.

That is a writer/dialect contract split, invisible to every test that does not
touch a real database. The gate for "this statement is legal SQL" cannot be a
mock session or a source assertion.

Opt-in on `SEARCH_TEST_DATABASE_URL`, following
`test_provenance_enum_real_postgres.py`: it skips where no Postgres exists and
runs in the `search-recall` CI job, which provides one. The job's own "Verify
the gate is actually armed" step exists precisely so a skipped gate cannot read
as a passing one.

🔴 AND THIS FILE CAN BE RUN BY HAND, which the earlier wording denied ("there is
no local Postgres in the agent sandbox") and #7767 found to be half true. You
cannot MINT a cluster — `initdb` dies on `shmget` — but a lane VM already has one
running, and every table here is built by this file in a private schema rather
than from `Base.metadata.create_all`. Nothing in them needs PG15, so:

    createdb -U bain <db>
    SEARCH_TEST_DATABASE_URL="postgresql+asyncpg://bain@127.0.0.1:5432/<db>" \
      python3 -m pytest tests/integration/test_polymarket_resolved_candidate_sql_pg.py -q

runs the whole file locally in about two seconds. That matters because it is the
only cheap way to prove a case here can FAIL: mutate the fix back to the defect
and watch the gate red. The suites that genuinely are CI-only are the ones that
build the app schema — they die at setup with `syntax error at or near "NULLS"`,
because `uq_container_anchor` is `NULLS NOT DISTINCT` and the VM's server is 14.

The statements under test are imported from the modules that ship them — never
retyped here. A copy would pass while the shipped query was broken, which is the
whole failure mode.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.utils.polymarket_settlement_scan import (
    GAMMA_EVENT_ID_EXPR,
    STALE_OPEN_AGE_HOURS,
    STALE_OPEN_CENSUS_SQL,
    StaleOpenCensus,
)

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #2637 "
            "settlement-sweep SQL gate (CI job: search-recall)"
        ),
    ),
]


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


#: This gate builds its own `futures_markets` in a PRIVATE SCHEMA rather than in
#: `public`, and that is not tidiness. It shares the `search-recall` job — and
#: therefore one database — with gates that build the real schema from
#: `Base.metadata.create_all`. Dropping or shadowing `public.futures_markets`
#: would either fail outright (`futures_outcomes` holds an FK to it, so a bare
#: DROP is refused) or leave a 7-column impostor behind that `create_all`
#: silently skips over, breaking a LATER step's insert with a missing column.
#: A schema on the `search_path` is resolved first and torn down whole.
_GATE_SCHEMA = "poly_sweep_gate_2637"


@pytest.fixture
async def futures_markets_table(pg_session):
    """The columns the two statements touch, and only those.

    Deliberately not the ORM metadata: this gate is about whether PostgreSQL
    accepts the statements, so it wants the narrowest schema that lets them
    parse and plan. A row is inserted under each of the two Polymarket keying
    conventions so the reconciliation expression is exercised rather than merely
    compiled.
    """
    await pg_session.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await pg_session.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
    await pg_session.execute(text(f"SET search_path TO {_GATE_SCHEMA}, public"))
    # The columns carry the model's NOT NULL set, not just the ones the two
    # statements read, and the seed below supplies every one of them. That is
    # `test_pg_gate_seed_completeness.py`'s contract: a raw INSERT bypasses
    # SQLAlchemy's Python-side `default=`, so `category`, `mutually_exclusive`
    # and `status` are NOT excused here the way an ORM insert would excuse them.
    # Keeping the shape honest means a migration that adds a NOT NULL column
    # trips this gate too, instead of tripping it first inside CI's deploy path.
    await pg_session.execute(
        text(
            """
            CREATE TABLE futures_markets (
                id serial PRIMARY KEY,
                source varchar(50) NOT NULL,
                external_id varchar(200) NOT NULL,
                name varchar(300) NOT NULL,
                category varchar(50) NOT NULL,
                mutually_exclusive boolean NOT NULL,
                status varchar(20) NOT NULL,
                group_id varchar(200),
                commence_time timestamptz,
                market_metadata jsonb
            )
            """
        )
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO futures_markets
                (source, external_id, name, category, mutually_exclusive,
                 status, group_id, commence_time, market_metadata)
            VALUES
                -- negRisk FIELD row: the event id is the external_id.
                ('polymarket', '139236', 'US Open Winner', 'championship', true,
                 'open', NULL, now() - interval '10 days', '{}'::jsonb),
                -- decomposed SUB-MARKET row: a 0x condition id in external_id,
                -- the event id in metadata and in group_id.
                ('polymarket', '0xabc', 'Trump visits Alaska', 'prop', true,
                 'open', 'polymarket:92611', now() - interval '10 days',
                 '{"polymarket_event_id": "92611"}'::jsonb),
                -- same event, second leg: proves the DISTINCT collapses it.
                ('polymarket', '0xdef', 'Trump visits Alabama', 'prop', true,
                 'open', 'polymarket:92611', now() - interval '10 days',
                 '{"polymarket_event_id": "92611"}'::jsonb),
                -- recent: outside the 48h CENSUS window, but inside the SWEEP
                -- population. The two predicates are deliberately different —
                -- the sweep asks the venue about every unresolved row, and only
                -- the needle cares how old they are. Asserted below.
                ('polymarket', '999', 'Fresh market', 'prop', true,
                 'open', NULL, now(), '{}'::jsonb),
                -- already resolved: outside the sweep population.
                ('polymarket', '888', 'Settled market', 'prop', true,
                 'resolved', NULL, now() - interval '10 days', '{}'::jsonb),
                -- another source entirely.
                ('kalshi', '777', 'Kalshi market', 'prop', true,
                 'open', NULL, now() - interval '10 days', '{}'::jsonb)
            """
        )
    )
    await pg_session.commit()
    yield
    await pg_session.execute(text("SET search_path TO public"))
    await pg_session.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await pg_session.commit()


def _candidate_sql() -> str:
    """The sweep's population query, lifted from the shipped source.

    Read out of `app/tasks/polymarket.py` rather than retyped: the defect this
    file exists for was a malformed statement, and a hand-copied statement in
    the test could be well-formed while the shipped one is not.
    """
    import inspect

    import app.tasks.polymarket as poly_mod

    src = inspect.getsource(poly_mod._sync_polymarket_resolved_status)
    match = re.search(
        r'text\(f"""\s*(SELECT eid FROM.*?ORDER BY eid::bigint)\s*"""\)',
        src,
        re.S,
    )
    assert match, (
        "could not find the candidate-population query in "
        "_sync_polymarket_resolved_status — if it was renamed or restructured, "
        "update this extractor rather than deleting the gate (a gate that "
        "cannot find its subject must fail, never silently pass)"
    )
    return match.group(1).replace("{GAMMA_EVENT_ID_EXPR}", GAMMA_EVENT_ID_EXPR)


class TestTheSweepPopulationQueryIsLegalSQL:
    async def test_it_executes(self, pg_session, futures_markets_table):
        """The whole point. `SELECT DISTINCT ... ORDER BY eid::bigint` raises
        `ProgrammingError: for SELECT DISTINCT, ORDER BY expressions must
        appear in select list` — and the task's broad `except` would have
        reported that as a run that simply found nothing to do."""
        rows = (await pg_session.execute(text(_candidate_sql()))).fetchall()

        assert [r[0] for r in rows] == ["999", "92611", "139236"], (
            "the population query returned the wrong set — expected the three "
            "unresolved Polymarket event ids in ascending NUMERIC order "
            f"(the resolved row and the Kalshi row excluded); got {rows}"
        )

    async def test_the_sweep_population_is_not_keyed_on_staleness(
        self, pg_session, futures_markets_table
    ):
        """The sweep asks the venue about every unresolved row; only the NEEDLE
        cares how old they are.

        Event `999` commences `now()` — outside the 48h census window — and must
        still be swept. Narrowing the sweep to the census predicate would be the
        staleness key #2637 forbids, arriving through the back door: a market
        that settles within 48h of starting (most of them) would then never be
        reached at all.
        """
        rows = {r[0] for r in (await pg_session.execute(text(_candidate_sql())))}

        assert "999" in rows, (
            "a recently-started unresolved market was excluded from the sweep"
        )

    async def test_it_orders_numerically_not_lexicographically(
        self, pg_session, futures_markets_table
    ):
        """`ORDER BY eid` (text) would give 139236 before 92611.

        The cursor is `int(batch_ids[-1])` and resumes with `> cursor`, so a
        lexicographic order would skip most of the population on every resumed
        run — and would do it silently.
        """
        rows = [r[0] for r in (await pg_session.execute(text(_candidate_sql())))]

        assert rows == sorted(rows, key=int), rows
        assert rows != sorted(rows), (
            "this fixture no longer discriminates: pick ids whose numeric and "
            "text orders differ, or the assertion above proves nothing"
        )

    async def test_both_polymarket_keying_conventions_are_reached(
        self, pg_session, futures_markets_table
    ):
        """negRisk field rows key on `external_id`; decomposed sub-market rows
        key on metadata/`group_id`. A sweep that reconciles only one convention
        leaves the other permanently stuck."""
        rows = {r[0] for r in (await pg_session.execute(text(_candidate_sql())))}

        assert "139236" in rows, "the negRisk field convention was not reached"
        assert "92611" in rows, "the sub-market convention was not reached"


class TestTheNeedleCensusIsLegalSQL:
    async def test_it_executes_and_reads_into_the_dataclass(
        self, pg_session, futures_markets_table
    ):
        """`StaleOpenCensus` unpacks the row POSITIONALLY, so a column added to
        the SQL without a matching field is a silent value swap, not an error."""
        row = (
            await pg_session.execute(
                text(STALE_OPEN_CENSUS_SQL),
                {"stale_hours": STALE_OPEN_AGE_HOURS},
            )
        ).one()

        census = StaleOpenCensus(
            stale_open=row[0],
            distinct_events=row[1],
            unaddressable=row[2],
            oldest_commence=row[3],
        )
        # Three stale-open Polymarket rows across two events; the recent row,
        # the resolved row and the Kalshi row are all excluded.
        assert census.stale_open == 3, row
        assert census.distinct_events == 2, row
        assert census.unaddressable == 0, row
        assert census.oldest_commence is not None


# --- CERT-751: the guard has to be proven on ROWS, not on the statement ------

_GUARD_SCHEMA = "poly_mixed_parent_guard_751"


def _resolve_sql() -> str:
    """The resolve UPDATE, lifted from the shipped source.

    Same contract as :func:`_candidate_sql` and for a sharper reason: CERT-751
    blocked this ship because every existing guard asserted the BIND LIST while
    the defect lived in which ROWS the statement selects with it. A retyped
    statement here could carry the guard while the shipped one does not.
    """
    import inspect

    import app.tasks.polymarket as poly_mod

    src = inspect.getsource(poly_mod._sync_polymarket_resolved_status)
    match = re.search(
        r'text\("""\s*(UPDATE futures_markets\s+SET status = \'resolved\'.*?)\s*"""\)',
        src,
        re.S,
    )
    assert match, (
        "could not find the resolve UPDATE in _sync_polymarket_resolved_status "
        "— if it was renamed or restructured, update this extractor rather "
        "than deleting the gate (a gate that cannot find its subject must "
        "fail, never silently pass)"
    )
    return match.group(1)


@pytest.fixture
async def mixed_parent_rows(pg_session):
    """Gamma event 92611, reduced to the shape the grader actually found.

    A `polymarket_event` PARENT carrying two legs — one the venue closed, one
    still trading — beside the settled leg's own decomposed CHILD row. That is
    the production pair (parent 113566 over 24 closed and 26 live legs); two
    legs reproduce it exactly, because the predicate is an `IN`, and an `IN`
    does not care whether the mixed set has 2 members or 50.
    """
    await pg_session.execute(text(f"DROP SCHEMA IF EXISTS {_GUARD_SCHEMA} CASCADE"))
    await pg_session.execute(text(f"CREATE SCHEMA {_GUARD_SCHEMA}"))
    await pg_session.execute(text(f"SET search_path TO {_GUARD_SCHEMA}, public"))
    await pg_session.execute(
        text(
            """
            CREATE TABLE futures_markets (
                id serial PRIMARY KEY,
                source varchar(50) NOT NULL,
                external_id varchar(200) NOT NULL,
                name varchar(300) NOT NULL,
                category varchar(50) NOT NULL,
                mutually_exclusive boolean NOT NULL,
                status varchar(20) NOT NULL,
                settled_at timestamptz,
                market_metadata jsonb
            )
            """
        )
    )
    await pg_session.execute(
        text(
            """
            CREATE TABLE futures_outcomes (
                id serial PRIMARY KEY,
                market_id integer NOT NULL,
                external_id varchar(200) NOT NULL,
                name varchar(300) NOT NULL
            )
            """
        )
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO futures_markets
                (source, external_id, name, category, mutually_exclusive,
                 status, market_metadata)
            VALUES
                ('polymarket', '92611', 'Trump visits (parent)', 'championship',
                 true, 'open', '{}'::jsonb),
                ('polymarket', '0xsettled', 'Trump visits Alaska', 'prop',
                 true, 'open', '{}'::jsonb)
            """
        )
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO futures_outcomes (market_id, external_id, name)
            VALUES
                ((SELECT id FROM futures_markets WHERE external_id = '92611'),
                 '0xsettled', 'Alaska'),
                ((SELECT id FROM futures_markets WHERE external_id = '92611'),
                 '0xtrading', 'Alabama'),
                ((SELECT id FROM futures_markets WHERE external_id = '0xsettled'),
                 '0xsettled', 'Alaska')
            """
        )
    )
    await pg_session.commit()
    yield
    await pg_session.execute(text("SET search_path TO public"))
    await pg_session.execute(text(f"DROP SCHEMA IF EXISTS {_GUARD_SCHEMA} CASCADE"))
    await pg_session.commit()


class TestTheMixedParentGuardSelectsTheRightRows:
    """CERT-751's BLOCK, executed against PostgreSQL.

    The unit suite can prove the statement CONTAINS a guard. Only this can
    prove the guard SELECTS correctly — which is the exact gap the grader
    found, and the reason a token was withheld.
    """

    async def _run(self, pg_session):
        settled = ["0xsettled"]
        extended = ["0xsettled", "0xsettled_yes", "0xsettled_no"]
        open_raw = ["0xtrading"]
        open_extended = ["0xtrading", "0xtrading_yes", "0xtrading_no"]
        await pg_session.execute(
            text(_resolve_sql()),
            {
                "cids": extended,
                "raw_cids": settled,
                "terminal_cids": extended,
                "terminal_raw": settled,
                "open_cids": open_extended,
                "open_raw": open_raw,
                "proof_stamp": '{"proof": "winner"}',
                "reason_stamp": '{"reason": "closed_without_terminal_price"}',
            },
        )
        rows = (
            await pg_session.execute(
                text(
                    "SELECT external_id, status FROM futures_markets "
                    "ORDER BY external_id"
                )
            )
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    async def test_the_still_trading_parent_is_not_resolved(
        self, pg_session, mixed_parent_rows
    ):
        status = await self._run(pg_session)

        assert status["92611"] == "open", (
            "the parent of a partly-settled event was marked resolved on the "
            "strength of ONE closed leg while 'Alabama' is still trading — "
            "this is CERT-751's finding, and it pulls a live market off every "
            f"open surface. statuses={status}"
        )

    async def test_the_settled_child_is_still_resolved(
        self, pg_session, mixed_parent_rows
    ):
        """The other direction, and the half of #2637 that was always right.

        A guard that withheld the child too would be 'safe' and useless: the
        whole ship is that finished events stop being sold as open.
        """
        status = await self._run(pg_session)

        assert status["0xsettled"] == "resolved", (
            "the settled child of a mixed event was withheld, so the guard is "
            f"over-refusing and the ship does nothing. statuses={status}"
        )


# --- #7767: the settling UPDATEs, EXECUTED -----------------------------------
#
# The sibling gates above prove the sweep's SELECTs are legal SQL. These prove
# the two statements the sweep WRITES with do the thing the ship claims, on rows
# that reproduce the production shapes — because #7767 was not a syntax error
# and not a missing clause. Both statements already wrote the correct price;
# they were simply never allowed to reach the rows that needed it, and a source
# assertion can only say the predicate changed, never that the change repairs
# the leg or that it leaves the healthy ones alone.
#
# Imported from `app.tasks.polymarket`, never retyped, for the reason this
# file's own docstring gives: a copy would pass while the shipped statement was
# broken, which is the whole failure mode.

_SETTLE_GATE_SCHEMA = "poly_settle_gate_7767"


@pytest.fixture
async def futures_outcomes_table(pg_session):
    """The five rows that decide this ship, and why each one is here.

    `specimen` is `/futures/113360`'s hero, to the value: graded a loser by us,
    resolved NO at Gamma, published at 1.0 off a `lastTradePrice` its own book
    prices out. `crowned_at_a_losing_price` is the #6110 direction — a leg we
    graded a WINNER carrying a loser's number — which the same rule must also
    correct rather than merely decline to delete. The two `already_*` rows are
    the controls that keep this from being a rule that rewrites the world every
    six hours, and `ungraded` is the capability control: the statements must
    still perform their original job.
    """
    await pg_session.execute(
        text(f"DROP SCHEMA IF EXISTS {_SETTLE_GATE_SCHEMA} CASCADE")
    )
    await pg_session.execute(text(f"CREATE SCHEMA {_SETTLE_GATE_SCHEMA}"))
    await pg_session.execute(
        text(f"SET search_path TO {_SETTLE_GATE_SCHEMA}, public")
    )
    # `current_probability` carries the production type, not `float`: the skip
    # casts to `numeric(7,6)` and a looser column would let 0.9999995 read as
    # equal to 1.0 here while differing in production.
    await pg_session.execute(
        text(
            """
            CREATE TABLE futures_outcomes (
                id serial PRIMARY KEY,
                market_id integer NOT NULL,
                external_id varchar(200) NOT NULL,
                name varchar(300) NOT NULL,
                current_probability numeric(7,6),
                current_american_odds integer,
                is_winner boolean,
                resolution_source varchar(50),
                price_changed_at timestamptz
            )
            """
        )
    )
    await pg_session.execute(
        text(
            """
            INSERT INTO futures_outcomes
                (market_id, external_id, name, current_probability,
                 current_american_odds, is_winner, resolution_source,
                 price_changed_at)
            VALUES
                (113360, '0xspecimen', '0', 1.0, NULL, false,
                 'api_settlement', now() - interval '4 days'),
                (113360, '0xcrowned', 'winner', 0.42, -120, true,
                 'api_settlement', now() - interval '4 days'),
                (113360, '0xalready_lost', 'lost', 0.0, NULL, false,
                 'api_settlement', now() - interval '4 days'),
                (113360, '0xalready_won', 'won', 1.0, NULL, true,
                 'api_settlement', now() - interval '4 days'),
                (113360, '0xungraded', 'ungraded', 0.31, 225, NULL, NULL,
                 now() - interval '4 days')
            """
        )
    )
    await pg_session.commit()
    yield pg_session
    await pg_session.execute(
        text(f"DROP SCHEMA IF EXISTS {_SETTLE_GATE_SCHEMA} CASCADE")
    )
    await pg_session.commit()


class TestSettlingWritesReachTheLegsTheyGraded:
    """#7767 — `/futures/113360` printed 100% for an outcome Gamma resolved NO."""

    #: The venue's answer for this board, as `settled_legs` returns it: the
    #: specimen and the already-lost control are NO, the two winners are YES.
    _LOSERS = ["0xspecimen", "0xalready_lost", "0xungraded"]
    _WINNERS = ["0xcrowned", "0xalready_won"]

    async def _settle(self, session):
        """Run both shipped statements once; return (winner_rows, loser_rows)."""
        from app.tasks.polymarket import settle_outcomes_stmt

        won = await session.execute(
            settle_outcomes_stmt("1.0", "true"), {"cids": self._WINNERS}
        )
        lost = await session.execute(
            settle_outcomes_stmt("0.0", "false"), {"cids": self._LOSERS}
        )
        await session.commit()
        return won.rowcount, lost.rowcount

    async def _read(self, session):
        rows = (
            await session.execute(
                text(
                    "SELECT external_id, current_probability, is_winner, "
                    "current_american_odds, resolution_source "
                    "FROM futures_outcomes ORDER BY external_id"
                )
            )
        ).fetchall()
        return {r[0]: r[1:] for r in rows}

    async def test_the_published_price_stops_contradicting_our_own_verdict(
        self, futures_outcomes_table
    ):
        """The ship. A leg we graded NO stops being published at 100%."""
        session = futures_outcomes_table
        before = await self._read(session)
        assert before["0xspecimen"][0] == Decimal("1.000000"), "bad fixture"

        await self._settle(session)
        after = await self._read(session)

        price, is_winner, odds, source = after["0xspecimen"]
        assert price == Decimal("0.000000"), (
            "the hero of /futures/113360 is still published at "
            f"{price} for an outcome Gamma resolved NO — the settling write "
            "cannot reach a leg that already carries its own grade"
        )
        assert is_winner is False and source == "api_settlement"
        assert odds is None, "american odds for a resolved contract are undefined"

    async def test_a_settled_winner_carrying_a_losing_price_is_also_corrected(
        self, futures_outcomes_table
    ):
        """#6110's direction, which the same seal blocked and is worse.

        A champion shown at 42% is the mirror of the specimen, and a rule that
        only looked at losers would leave it there.
        """
        session = futures_outcomes_table
        await self._settle(session)
        price, is_winner, odds, _ = (await self._read(session))["0xcrowned"]

        assert price == Decimal("1.000000") and is_winner is True
        assert odds is None

    async def test_a_leg_already_holding_its_settlement_is_not_rewritten(
        self, futures_outcomes_table
    ):
        """Idempotence, measured as rowcount rather than as an unchanged value.

        A statement that rewrote every settled leg on every six-hourly run would
        produce the same table and a great deal of churn, so reading the values
        back cannot tell the two apart. The controls sit inside the SAME
        `ANY(:cids)` list as the rows that do change, so the counts below are
        the skip.
        """
        session = futures_outcomes_table
        won, lost = await self._settle(session)
        assert (won, lost) == (1, 2), (
            f"expected exactly the crowned leg and the specimen+ungraded to be "
            f"written, got winners={won} losers={lost}"
        )

        won_again, lost_again = await self._settle(session)
        assert (won_again, lost_again) == (0, 0), (
            "the steady state still writes rows, so every settled leg is "
            "churned on every run"
        )

    async def test_the_settled_champion_keeps_its_crown(
        self, futures_outcomes_table
    ):
        """#6110's trap, stated as a control rather than as a promise.

        `resolution_source IS NOT NULL` alone would delete the champion from
        every board the moment a championship is decided. `is_winner` is the
        discriminator and this is the row that proves it is being read.
        """
        session = futures_outcomes_table
        await self._settle(session)
        price, is_winner, _, source = (await self._read(session))["0xalready_won"]

        assert (price, is_winner, source) == (
            Decimal("1.000000"),
            True,
            "api_settlement",
        )

    async def test_an_ungraded_leg_is_still_graded(self, futures_outcomes_table):
        """Capability control: the original job of these statements survives.

        A predicate tightened until it only admitted damaged rows would pass
        every test above and stop the sweep settling anything new.
        """
        session = futures_outcomes_table
        await self._settle(session)
        price, is_winner, odds, source = (await self._read(session))["0xungraded"]

        assert (price, is_winner, source) == (
            Decimal("0.000000"),
            False,
            "api_settlement",
        )
        assert odds is None

    async def test_the_change_stamp_moves_only_for_the_legs_that_moved(
        self, futures_outcomes_table
    ):
        """#2024: `price_changed_at` records that the PRICE moved, not that a
        write ran. The two controls must keep their old stamp."""
        session = futures_outcomes_table
        stamps_before = {
            r[0]: r[1]
            for r in (
                await session.execute(
                    text(
                        "SELECT external_id, price_changed_at FROM futures_outcomes"
                    )
                )
            ).fetchall()
        }
        await self._settle(session)
        stamps_after = {
            r[0]: r[1]
            for r in (
                await session.execute(
                    text(
                        "SELECT external_id, price_changed_at FROM futures_outcomes"
                    )
                )
            ).fetchall()
        }

        for moved in ("0xspecimen", "0xcrowned", "0xungraded"):
            assert stamps_after[moved] > stamps_before[moved], moved
        for held in ("0xalready_lost", "0xalready_won"):
            assert stamps_after[held] == stamps_before[held], held
