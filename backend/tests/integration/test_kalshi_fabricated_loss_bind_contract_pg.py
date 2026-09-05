"""The fabricated-loss drain's bind contract, against a REAL asyncpg connection.

Why this file exists, and why 19,000 green unit tests were not enough
---------------------------------------------------------------------
`repair_kalshi_fabricated_loss` is the drain for #1852/#2528 — 63,733 Kalshi legs
carrying a fabricated ``is_winner = false``, which is why those cards sum to
~1,500% instead of 100%. It was built 2026-08-14, certified twice (C-CERT-1852
and R2), and carries a large unit suite.

**Its endpoint had never completed a single work selection.** Measured against
production 2026-09-05, both unsharded and with ``?sport=``::

    POST /api/admin/repairs/kalshi-fabricated-loss?apply=false&limit=1
    -> "work selection did not complete: ProgrammingError:
        asyncpg.exceptions.AmbiguousParameterError:
        could not determine data type of parameter $1"   (0.1 s)

The line was::

    AND (:sport IS NULL OR fm.llm_sport_category = :sport)

asyncpg prepares a statement with **no parameter types**, so Postgres infers them
from the query text alone, and the FIRST occurrence of a parameter fixes its
type. ``$1 IS NULL`` fixes ``$1`` as ``unknown``; the later ``= $1`` cannot
re-resolve it; the prepare dies before a row is read — whatever value is bound.
That is why the keyset predicate two lines below it casts both halves, and why
every sibling rail writes ``:sport::text`` on BOTH sides
(``repair_polymarket_leg_label.py`` :457-458, :758). This one line did not.

Nothing in the unit suite could see it: the session doubles never prepare a
statement, so the WHERE clause never meets a type system. This file is the
boundary that can reject it — it executes the rail's real statements through the
real driver, so any future parameter this rail cannot type fails HERE rather than
on the first attended production run.

Opt-in on ``SEARCH_TEST_DATABASE_URL``, following the other real-Postgres
contracts; CI's ``search-recall`` job provides a Postgres 15 service and asserts
the gate did not silently skip.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import repair_kalshi_fabricated_loss as rail
from app.utils.kalshi_fabricated_loss import (
    POPULATION_HAVING_SQL,
    REPAIRABLE_SOURCE,
)
from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres "
            "fabricated-loss bind contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, real asyncpg parameter-type inference.

    Function-scoped: ``pytest.ini`` leaves ``asyncio_default_fixture_loop_scope``
    unset, so a module-scoped async fixture would outlive the event loop that
    created its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


async def _seed_one_fabricated_loss_market(
    session, *, sport="baseball", ext="KXBIND-26"
):
    """One market in the drain's population: 2 legs, no winner, all api_settlement.

    Raw ``text()`` INSERTs deliberately — this gate exists to exercise the
    driver's own type handling, and the ORM would adapt values on the way in.
    Python-side column defaults therefore do NOT apply, so every NOT NULL column
    with only a ``default=`` is supplied explicitly.
    """
    from sqlalchemy import text

    resolved = datetime.now(timezone.utc) - timedelta(days=PROVABLY_PURGED_AGE_DAYS - 5)
    market_id = (
        await session.execute(
            text("""
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     resolution_date, external_id, llm_sport_category)
                VALUES
                    (:name, 'kalshi', 'championship', TRUE, 'resolved',
                     :resolved, :ext, :sport)
                RETURNING id
                """),
            {
                "name": "Fabricated-loss bind contract market",
                "resolved": resolved,
                "ext": ext,
                "sport": sport,
            },
        )
    ).scalar()

    for leg in ("YES", "NO"):
        await session.execute(
            text("""
                INSERT INTO futures_outcomes
                    (market_id, name, external_id, is_winner, resolution_source)
                VALUES (:mid, :name, :ext, FALSE, :source)
                """),
            {
                "mid": market_id,
                "name": leg.title(),
                "ext": f"{ext}-{leg}",
                "source": REPAIRABLE_SOURCE,
            },
        )

    await session.commit()
    return market_id, resolved


async def _work(session, **params):
    from sqlalchemy import text

    args = {
        "lim": 10,
        "sport": None,
        "after_date": None,
        "after_id": None,
        "band_min_age": None,
        "band_max_age": None,
    }
    args.update(params)
    return (await session.execute(text(rail._WORK_SQL), args)).all()


async def test_the_unsharded_work_selection_executes_against_real_postgres(pg_session):
    """THE SPECIMEN. This is the call the runbook makes first.

    Pre-fix this raises ``AmbiguousParameterError`` on ``$1`` before a row is
    read, which is what the production endpoint did on 2026-09-05.
    """
    market_id, _ = await _seed_one_fabricated_loss_market(pg_session)

    rows = await _work(pg_session)

    assert [r.market_id for r in rows] == [market_id], (
        "the unsharded drain must select the fabricated-loss market. An "
        "exception here means a parameter this rail binds cannot be typed by "
        "Postgres; zero rows with no exception means the population predicate "
        "moved."
    )


async def test_the_sharded_work_selection_still_filters(pg_session):
    """The over-reach control: the cast must not turn the filter into a no-op.

    A cast that made ``:sport`` always match would be the cheapest way to pass
    the test above while quietly widening every attended run's scope.
    """
    baseball, _ = await _seed_one_fabricated_loss_market(
        pg_session, sport="baseball", ext="KXBIND-BASE"
    )
    await _seed_one_fabricated_loss_market(
        pg_session, sport="hockey", ext="KXBIND-HOCK"
    )

    assert [r.market_id for r in await _work(pg_session, sport="baseball")] == [
        baseball
    ]
    assert await _work(pg_session, sport="chess") == []
    assert len(await _work(pg_session)) == 2, "no shard means no filter"


async def test_the_cursor_this_rail_hands_back_is_one_it_accepts(pg_session):
    """The round trip, closed: `next_cursor` out, `?after_date=` in, and page two.

    The population is 63,733 legs at ``APPLY_MARKET_CAP`` markets a call, so the
    drain is nothing BUT paging — and this loop was open. ``keyset_after``
    emits ``after_date`` as ``date.isoformat()``, the route declares
    ``after_date: str``, and asyncpg refuses a ``str`` for a ``timestamptz``
    parameter rather than casting it (psycopg2 would have). Page one worked;
    page two died on ``DataError: invalid input for query argument``.

    So the assertion is the whole loop rather than a bind type: the cursor is
    taken FROM `keyset_after`, put through the REAL query-string decoder, then
    through `parse_cursor_date`, then executed. Nothing here restates a value
    the rail computed.

    CERT-1892 blocked the version of this test that skipped the decoder. A
    params dictionary is not a query string, and the character that was being
    eaten — `isoformat()`'s `+` — is eaten only by the transport. The test was
    green over a user path that could not work. `QueryParams` is the same class
    Starlette hands the route, so it is in the loop now; the route itself, with
    the cursor appended to a URL as text, is pinned in
    `tests/test_kalshi_fabricated_loss_cursor_transport_p1010.py`.
    """
    from starlette.datastructures import QueryParams

    from app.utils.repair_apply_plan import keyset_after

    def _through_the_query_string(value: str) -> str:
        return QueryParams(f"after_date={value}")["after_date"]

    first, _ = await _seed_one_fabricated_loss_market(pg_session, ext="KXBIND-P1")
    second, _ = await _seed_one_fabricated_loss_market(pg_session, ext="KXBIND-P2")

    page_one = await _work(pg_session, lim=1)
    assert [r.market_id for r in page_one] == [first]

    cursor = keyset_after(page_one, examined=1)
    assert cursor["after_id"] == first
    assert isinstance(
        cursor["after_date"], str
    ), "the emitted cursor is a STRING — that is the fact the parse exists for"
    assert (
        _through_the_query_string(cursor["after_date"]) == cursor["after_date"]
    ), "the cursor changed in transit, which is CERT-1892's defect"

    page_two = await _work(
        pg_session,
        lim=1,
        after_date=rail.parse_cursor_date(
            _through_the_query_string(cursor["after_date"])
        ),
        after_id=cursor["after_id"],
    )
    assert [r.market_id for r in page_two] == [
        second
    ], "the resume must advance past the row page one returned"

    exhausted = keyset_after(page_two, examined=1)
    assert (
        await _work(
            pg_session,
            lim=1,
            after_date=rail.parse_cursor_date(
                _through_the_query_string(exhausted["after_date"])
            ),
            after_id=exhausted["after_id"],
        )
        == []
    ), "the walk must end, not wrap"


async def test_a_hand_typed_date_is_accepted_and_a_broken_one_is_refused(pg_session):
    """The two shapes an operator actually types, and neither may be ignored.

    A naive date is what somebody pastes from the plan by hand; it is read as
    UTC. Anything unreadable is REFUSED by name — a cursor half silently
    dropped to ``None`` re-reads page one and reports it as a resume, which is
    the `?offset=` bug rebuilt one level down.
    """
    first, _ = await _seed_one_fabricated_loss_market(pg_session, ext="KXBIND-H1")
    await _seed_one_fabricated_loss_market(pg_session, ext="KXBIND-H2")

    naive = rail.parse_cursor_date("2000-01-01T00:00:00")
    assert naive.tzinfo is not None, "asyncpg wants the tzinfo explicit"
    rows = await _work(pg_session, after_date=naive, after_id=0)
    assert len(rows) == 2, "a floor before both rows must return both"

    with pytest.raises(ValueError):
        rail.parse_cursor_date("page two please")

    out = await rail.repair(
        pg_session, apply=False, after_date="page two please", after_id=first
    )
    assert out["refused"] == "CURSOR_DATE_UNPARSEABLE"
    assert out["measured"] is False


async def test_the_census_executes_against_real_postgres(pg_session):
    """The other statement the runbook opens with, on the same rail.

    THIS GATE ALREADY PAID FOR ITSELF. Its previous docstring said the census
    "carries no parameters today, which is exactly why it belongs here: a
    parameter added to the census later meets Postgres in CI rather than in an
    attended window." CAL-P1012 (#3195) added two, and this test failed in CI on
    the first push — before any attended run, exactly as written.
    """
    from sqlalchemy import text

    await _seed_one_fabricated_loss_market(pg_session)

    rows = (
        await pg_session.execute(
            text(rail._CENSUS_SQL), {"lo": 0, "hi": 2_000_000_000}
        )
    ).all()

    assert [r.source for r in rows] == ["kalshi"]
    assert rows[0].markets == 1 and int(rows[0].outcomes) == 2


async def test_the_census_range_bound_really_bounds(pg_session):
    """The chunk bound EXCLUDES, against the real planner and the real driver.

    A CAST that prepares proves the types resolve; it does not prove the
    predicate selects. A range above the seeded market must come back empty —
    otherwise every chunk returns the whole table and the walk sums the
    population once per chunk.
    """
    from sqlalchemy import text

    market_id, _ = await _seed_one_fabricated_loss_market(pg_session)

    inside = (
        await pg_session.execute(
            text(rail._CENSUS_SQL), {"lo": market_id - 1, "hi": market_id}
        )
    ).all()
    above = (
        await pg_session.execute(
            text(rail._CENSUS_SQL), {"lo": market_id, "hi": market_id + 1_000}
        )
    ).all()

    assert [r.markets for r in inside] == [1], "half-open: lo is EXCLUSIVE"
    assert above == [], "half-open: hi is INCLUSIVE, so the next range must be empty"


async def test_the_census_entry_point_completes_against_real_postgres(
    pg_session, monkeypatch
):
    """The whole walk, driven through its real entry point on real Postgres.

    CAL-P076 banked the reason: a pure test suite cannot tell you a task RUNS.
    37 tests, a green suite, and the task died in 73 ms on its first production
    invocation, on the first line that touched a session. The census walk issues
    ``SET LOCAL statement_timeout`` per chunk, reads ``MAX(market_id)``, and
    executes the bound aggregate in a loop — a session protocol no double
    exercises. Only the durable bank is faked here (it is standalone, so it would
    reach the app's own database rather than this one); the unit suite covers it.
    """
    banked: dict[str, object] = {}

    async def _fake_load():
        return (banked.get("record"), "ok" if "record" in banked else "missing")

    async def _fake_save(record):
        banked["record"] = record
        return True, "ok"

    monkeypatch.setattr(rail, "_load_census", _fake_load)
    monkeypatch.setattr(rail, "_save_census", _fake_save)

    await _seed_one_fabricated_loss_market(pg_session)

    out = await rail.census(pg_session)

    assert out["measured"] is True, out.get("reason")
    assert out["walk"]["complete"] is True
    assert out["walk"]["chunks_measured"] >= 1
    assert out["totals"]["markets"] == 1
    assert out["totals"]["outcomes"] == 2
    assert out["kalshi"]["markets"] == 1
    # And the completion test the whole change exists for is expressible: the
    # addressed bands are readable off a walk that reached the end.
    assert banked["record"]["complete"] is True


#: The work selection AS IT WAS before CAL-P1013 rewrote it (#2528) — the grouped
#: whole-table aggregate that cost 10.8s in August and 18.2s-and-cancelled on
#: 2026-09-05, once ``futures_outcomes`` reached 3,957,119 rows.
#:
#: It is kept here as an EXECUTABLE REFERENCE, not as documentation. The rewrite's
#: entire claim is that it selects the same markets in the same order by a cheaper
#: route, and the only way to hold a claim like that is to run both and diff the
#: rows. A prose assertion that two SQL statements agree is the thing that goes
#: stale (#2779: a hand-copied table that rotted five times).
#:
#: The parts that are SHARED with the shipped statement are INTERPOLATED FROM THE
#: SHIPPED CONSTANTS, never re-typed: the population predicate is
#: ``POPULATION_HAVING_SQL`` itself and the floor is ``PROVABLY_PURGED_AGE_DAYS``
#: itself. So a future change to what the population MEANS moves both sides at
#: once and this gate keeps testing the shape rather than freezing a definition
#: nobody meant to freeze. Only the SHAPE — group-then-join vs drive-then-probe —
#: is frozen, which is exactly the thing under test.
_WORK_SQL_BEFORE_THE_LATERAL = f"""
    SELECT fm.id AS market_id,
           fm.external_id AS event_ticker,
           fm.mutually_exclusive AS mutex,
           fm.llm_sport_category AS sport,
           fm.status AS our_status,
           fm.resolution_date AS resolution_date,
           EXTRACT(EPOCH FROM (NOW() - fm.resolution_date)) / 86400.0 AS age_days
    FROM (
      SELECT fo.market_id,
             COUNT(*) AS n_out
      FROM futures_outcomes fo
      GROUP BY fo.market_id
      HAVING {POPULATION_HAVING_SQL}
    ) mx
    JOIN futures_markets fm ON fm.id = mx.market_id
    WHERE fm.source = 'kalshi'
      AND fm.resolution_date IS NOT NULL
      AND fm.resolution_date >= NOW() - INTERVAL '{PROVABLY_PURGED_AGE_DAYS} days'
      AND (CAST(:sport AS text) IS NULL OR fm.llm_sport_category = CAST(:sport AS text))
      AND (
            CAST(:after_date AS timestamptz) IS NULL
         OR (fm.resolution_date, fm.id)
              > (CAST(:after_date AS timestamptz), CAST(:after_id AS bigint))
          )
    ORDER BY fm.resolution_date ASC, fm.id ASC
    LIMIT :lim
"""


async def _seed_market(
    session,
    *,
    ext,
    days_ago,
    legs=("YES", "NO"),
    winner_leg=None,
    source=REPAIRABLE_SOURCE,
    market_source="kalshi",
    sport="baseball",
):
    """One market at a chosen age, with control over the three exclusion knobs.

    ``legs`` sizes the market (a ONE-leg market is the ``COUNT(*) >= 2`` edge),
    ``winner_leg`` gives it a winner (the ``FILTER (WHERE is_winner) = 0`` edge)
    and ``source`` sets the grading provenance (the ``api_settlement`` edge).
    """
    from sqlalchemy import text

    resolved = datetime.now(timezone.utc) - timedelta(days=days_ago)
    market_id = (
        await session.execute(
            text("""
                INSERT INTO futures_markets
                    (name, source, category, mutually_exclusive, status,
                     resolution_date, external_id, llm_sport_category)
                VALUES
                    (:name, :msrc, 'championship', TRUE, 'resolved',
                     :resolved, :ext, :sport)
                RETURNING id
                """),
            {
                "name": f"work-selection {ext}",
                "msrc": market_source,
                "resolved": resolved,
                "ext": ext,
                "sport": sport,
            },
        )
    ).scalar()

    for leg in legs:
        await session.execute(
            text("""
                INSERT INTO futures_outcomes
                    (market_id, name, external_id, is_winner, resolution_source)
                VALUES (:mid, :name, :ext, :win, :source)
                """),
            {
                "mid": market_id,
                "name": leg.title(),
                "ext": f"{ext}-{leg}",
                "win": leg == winner_leg,
                "source": source,
            },
        )

    await session.commit()
    return market_id


async def _reference_work(session, **params):
    from sqlalchemy import text

    args = {"lim": 10, "sport": None, "after_date": None, "after_id": None}
    args.update(params)
    return (
        await session.execute(text(_WORK_SQL_BEFORE_THE_LATERAL), args)
    ).all()


async def _mixed_population(session):
    """Four members and five near-misses, ages deliberately out of id order.

    THE INSERTION ORDER IS THE POINT and it is not the reading order. Seeded
    oldest-first, the ids come out ascending in the same sequence as the dates,
    so "sorted by id" and "sorted by resolution_date" are the same answer and an
    ordering test over the fixture proves nothing — it passes just as happily
    against a plan that lost the sort entirely. (That is not a hypothetical: the
    first version of this fixture did exactly that, and the anti-vacuity
    assertion in the ordering test below is what caught it, in CI, on the run
    that was meant to prove the rewrite.)

    So the four members go in as recent, future, oldest, middle, and are RETURNED
    in resolution_date order. Id order and date order are now different answers
    and only one of them is the contract.
    """
    recent = await _seed_market(session, ext="KXWORK-NEW", days_ago=10)
    future = await _seed_market(session, ext="KXWORK-FUT", days_ago=-9)
    oldest = await _seed_market(session, ext="KXWORK-OLD", days_ago=60)
    middle = await _seed_market(session, ext="KXWORK-MID", days_ago=40)

    # Near-misses, one per exclusion the population predicate makes.
    await _seed_market(session, ext="KXWORK-ONELEG", days_ago=30, legs=("YES",))
    await _seed_market(
        session, ext="KXWORK-WON", days_ago=30, winner_leg="YES"
    )
    await _seed_market(
        session, ext="KXWORK-MANUAL", days_ago=30, source="manual_review"
    )
    await _seed_market(
        session,
        ext="KXWORK-POLY",
        days_ago=30,
        market_source="polymarket",
        sport="hockey",
    )
    # Below the floor: older than the measured purge bound.
    await _seed_market(
        session, ext="KXWORK-PURGED", days_ago=PROVABLY_PURGED_AGE_DAYS + 5
    )

    return [oldest, middle, recent, future]


async def test_the_lateral_rewrite_selects_exactly_what_the_grouped_form_did(
    pg_session,
):
    """CAL-P1013 (#2528): the rewrite is answer-identical, run against both.

    The old form is not merely slow — on 2026-09-05 it was CANCELLED at its own
    18s bound on every production call, sharded and unsharded, so the drain
    could not so much as build a plan. Making it finish is worthless if it
    finishes on a different set of markets: this rail writes to `is_winner`, and
    a work list that quietly widened would write outside the population the
    census measures and the after-check re-reads.

    So both statements run, over a population that exercises every exclusion,
    and the assertion is on the ROWS — including their order, which the keyset
    cursor is a position in.
    """
    expected = await _mixed_population(pg_session)

    shipped = await _work(pg_session)
    reference = await _reference_work(pg_session)

    assert [r.market_id for r in shipped] == [r.market_id for r in reference], (
        "the LATERAL probe and the grouped aggregate disagree about WHICH "
        "markets are in the drain's population, or about their ORDER"
    )
    assert [r.market_id for r in shipped] == expected, (
        "both forms agree with each other but not with the population this test "
        "seeded — the predicate itself moved"
    )
    assert [tuple(r) for r in shipped] == [tuple(r) for r in reference], (
        "the two forms return different COLUMNS or different values in them; "
        "the plan builder reads mutex, sport, our_status and age_days off these "
        "rows"
    )


async def test_the_rewrite_agrees_with_the_grouped_form_under_a_shard_and_a_cursor(
    pg_session,
):
    """The same identity under the two parameters an attended drain actually uses.

    An identity that holds only for the unparameterised call is not the identity
    the operator relies on: every call after the first carries a cursor, and the
    old refusal's advice was to carry a shard.
    """
    await _mixed_population(pg_session)
    await _seed_market(pg_session, ext="KXWORK-HOCKEY", days_ago=20, sport="hockey")

    for params in (
        {"sport": "baseball"},
        {"sport": "hockey"},
        {"sport": "chess"},
        {"lim": 2},
        {"lim": 1},
    ):
        assert [r.market_id for r in await _work(pg_session, **params)] == [
            r.market_id for r in await _reference_work(pg_session, **params)
        ], f"the two forms disagree under {params}"

    everything = [r.market_id for r in await _work(pg_session, lim=50)]
    page_one = await _work(pg_session, lim=1)
    resumed = {
        "lim": 50,
        "after_date": page_one[0].resolution_date,
        "after_id": page_one[0].market_id,
    }
    assert [r.market_id for r in await _work(pg_session, **resumed)] == [
        r.market_id for r in await _reference_work(pg_session, **resumed)
    ]
    # Derived from the unsharded listing, never hand-written. The first draft of
    # this line said `members[1:]` and forgot that the hockey market seeded two
    # lines up also joins the population — so it asserted a four-row resume was
    # three rows and failed in CI on a defect that was entirely the test's.
    assert [
        r.market_id for r in await _work(pg_session, **resumed)
    ] == everything[1:], (
        "the resume must return everything except the row page one returned, in "
        "the same order"
    )


async def test_the_work_selection_is_ordered_oldest_first_not_by_id(pg_session):
    """The sort is a CONTRACT here, not a nicety, and the rewrite moved it.

    Oldest-first-within-a-floor is what reaches the at-risk band before the
    retention cliff destroys it, and the keyset cursor names a POSITION in this
    order — a page returned out of order hands back a cursor that skips
    everything it stepped over, silently, because every row returned is still a
    genuine population member.

    The seeded ages ascend against the insertion order, so id order and date
    order are different answers and only one of them is right.
    """
    members = await _mixed_population(pg_session)

    rows = await _work(pg_session)

    assert [r.market_id for r in rows] == members, "not in resolution_date order"
    assert [r.market_id for r in rows] != sorted(
        r.market_id for r in rows
    ), "the fixture must make id order and date order DIFFER, or this proves nothing"
    dates = [r.resolution_date for r in rows]
    assert dates == sorted(dates), "oldest first"


async def test_the_near_misses_stay_out_of_the_lateral_form(pg_session):
    """The three exclusions, each proven by a market that differs in one field.

    The LATERAL restates the population predicate against a single market rather
    than a GROUP BY, and the case that changes shape is the one-leg market: it
    used to fail to form a group, and now it forms an aggregate row that HAVING
    must reject. If ``COUNT(*) >= 2`` were dropped, 4,372 correctly-settled
    one-leg binaries would enter the drain's work list and be sent to the venue.
    """
    await _mixed_population(pg_session)

    selected = {r.event_ticker for r in await _work(pg_session, lim=50)}

    for excluded, why in (
        ("KXWORK-ONELEG", "a one-leg binary that settled NO is an ordinary loser"),
        ("KXWORK-WON", "a market with a winner is not all-loser"),
        ("KXWORK-MANUAL", "only api_settlement losses are fabricated ones"),
        ("KXWORK-POLY", "this rail is Kalshi's"),
        ("KXWORK-PURGED", "past the purge bound the venue cannot answer"),
    ):
        assert excluded not in selected, why


async def _band_population(session):
    """Five members spread across the sort, one per decade of age.

    Ages descend against the insertion order for the same reason
    ``_mixed_population`` does: a band that reads the wrong edge still returns
    rows, and a fixture whose id order agrees with its date order cannot tell a
    correct band from a lucky one.
    """
    ids = {}
    for age in (80, 65, 55, 40, 20):
        ids[age] = await _seed_market(session, ext=f"KXBAND-{age}", days_ago=age)
    return ids


async def test_the_band_selects_the_ages_it_names_and_no_others(pg_session):
    """``?band=47-67`` means ages 47..67 INCLUSIVE, and nothing outside it.

    #3257 shape 3. The whole point of the band is that an operator can name the
    stretch of the sort the venue still answers for, so the mapping from the two
    numbers to the two date bounds is the contract — and it is the one thing a
    fixture-only test cannot hold, because ``NOW() - :n * INTERVAL '1 day'`` is
    evaluated by Postgres.
    """
    ids = await _band_population(pg_session)

    selected = {
        r.market_id
        for r in await _work(pg_session, lim=50, band_min_age=47, band_max_age=67)
    }

    assert selected == {ids[65], ids[55]}, (
        "the band must admit exactly the seeded ages inside 47..67 — got "
        f"{selected}, expected the 65d and 55d markets"
    )
    assert ids[80] not in selected, "80d is older than the band's max edge"
    assert ids[40] not in selected, "40d is younger than the band's min edge"
    assert ids[20] not in selected, "20d is younger than the band's min edge"


async def test_the_max_is_the_OLDER_edge_not_the_younger_one(pg_session):
    """The direction, held on its own, because reversing it still returns rows.

    ``band_max_age`` is a LOWER bound on ``resolution_date`` and ``band_min_age``
    is an UPPER one. Swap the two binds in ``_WORK_SQL`` and this fixture still
    yields a non-empty, plausible page — every row in it is a genuine population
    member — so nothing but an assertion about WHICH rows can catch it. Under the
    swap the band below selects the 20d and 40d markets instead of the 80d one.
    """
    ids = await _band_population(pg_session)

    selected = {
        r.market_id
        for r in await _work(pg_session, lim=50, band_min_age=70, band_max_age=86)
    }

    assert selected == {ids[80]}, (
        "band=70-86 is the OLD end of the sort (the measured dead head); it must "
        f"select the 80-day market alone — got {selected}"
    )


async def test_a_band_keeps_the_oldest_first_sort_inside_itself(pg_session):
    """Band-first paging is worthless if the band is not itself drained in order.

    The at-risk cohort is drained oldest-first so the rows nearest the purge
    cliff go first; and the keyset resumes at a POSITION in this order, so a band
    that reordered its own page would hand back a cursor that skips.
    """
    await _band_population(pg_session)

    rows = await _work(pg_session, lim=50, band_min_age=30, band_max_age=86)

    dates = [r.resolution_date for r in rows]
    assert dates == sorted(dates), "oldest first inside the band too"
    assert len(rows) == 4, "30..86 covers every seeded age but the 20-day one"


async def test_no_band_is_the_whole_population_unchanged(pg_session):
    """The default path must be byte-identical to the pre-band behaviour.

    Both binds NULL is the no-band case, and it is the one every existing caller
    takes. A band predicate that failed open to "select nothing" would empty the
    drain while every band test still passed.
    """
    ids = await _band_population(pg_session)

    selected = {r.market_id for r in await _work(pg_session, lim=50)}

    assert set(ids.values()) <= selected, (
        "with no band the walk must still see every member of the population"
    )


async def test_a_band_narrower_than_the_population_still_pages_by_keyset(pg_session):
    """The band COMPOSES with the cursor; it does not replace it.

    Shape 3 was chosen over a floor partly because it stacks on the existing
    keyset. If the cursor were ignored inside a band, a drain would re-read the
    band's first page forever and report progress each time.
    """
    ids = await _band_population(pg_session)

    first = await _work(pg_session, lim=1, band_min_age=30, band_max_age=86)
    assert [r.market_id for r in first] == [ids[80]]

    resumed = await _work(
        pg_session,
        lim=50,
        band_min_age=30,
        band_max_age=86,
        after_date=first[0].resolution_date,
        after_id=first[0].market_id,
    )

    assert [r.market_id for r in resumed] == [ids[65], ids[55], ids[40]], (
        "the resume must continue inside the band, not restart it"
    )


async def test_the_per_market_leg_read_executes(pg_session):
    """`_legs` is what the plan is built from; its bind is typed by its column."""
    market_id, _ = await _seed_one_fabricated_loss_market(pg_session)

    legs = await rail._legs(pg_session, market_id)

    assert len(legs) == 2
    assert {leg.resolution_source for leg in legs} == {REPAIRABLE_SOURCE}
    assert not any(leg.is_winner for leg in legs)
