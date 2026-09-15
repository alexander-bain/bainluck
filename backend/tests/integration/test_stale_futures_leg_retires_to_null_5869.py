"""#5869 — a futures leg that VANISHED from the book stops claiming it is impossible.

WHAT A READER SEES TODAY. `https://bainluck.com/futures/1`, MLB World Series
Winner, "Show more". Read from the served payload 2026-09-15 ~12:4xZ:

    {"name": "Athletics", "probability": 0.0, "american_odds": 331909,
     "is_winner": false, "resolution_source": null}

`0%` — the site asserting, flatly, that the Athletics cannot win the World
Series — sitting beside a price that implies 0.03%. 435 legs across 8 open
markets render that way; 122 of the 205 outcomes on "The Open Winner" are it.

── WHY 0 AND NULL ARE DIFFERENT SENTENCES, WHICH IS THE WHOLE SHIP ─────────────

`_poll_futures_odds`'s stale block (`app/tasks/futures.py`, "zero out stale
outcomes absent from API response") knows one fact: the outcome was ABSENT from
the response for over a day. "We no longer have a price" is NULL. It wrote 0,
which says IMPOSSIBLE, and nothing in that block established impossibility.

It survived because most readers of the column cannot tell the two apart — the
falsy idiom (`if o.current_probability`, `or 0`) that dominates
`routes/futures.py` folds them together, and `routes/teams.py:675` drops both.
The serializers `#6081` converted to `is not None` are the ones that CAN, and on
those the difference is the whole render:

    stored NULL -> `probability: null` -> formatProbability -> "-"
    stored 0    -> `probability: 0.0`  -> probabilityParts   -> "0%"

`probabilityParts` (`frontend/lib/probabilityDisplay.ts:136`) reaches for the
truthful `<1%` marker only when `prob > 0`, so 0 is precisely the one value that
escapes UX-P046 and prints as a hard claim.

🔴 THE REPAIR MAY NOT DERIVE A PROBABILITY FROM THE SURVIVING ODDS, and this test
deliberately does not assert one. On 430 of the 435 the zeroed legs last moved in
May–August while their priced siblings refreshed today, so
`current_american_odds` there is a months-old relic; turning it into a live price
would store a stale number as a current one on almost the whole population —
plausible, wrong, and indistinguishable from a real repair afterwards. "-" is
what we actually know. (Measured and written up on #1541; the odds column is kept
because it is the last honest quote, not because it can speak for now.)

The stored 435 are the sibling half of this ship and are retired by
`scripts/repair_5869_stale_futures_legs_claiming_impossible.py`; this file is the
producer gate, so the population cannot grow back (5 new legs joined it in the
30 days to 2026-09-15).

── WHAT EACH TEST HOLDS ────────────────────────────────────────────────────────

The round trip is the REAL task against a REAL Postgres, with two seams: the
venue (stubbed payload) and the connection. `stats["stale_zeroed"]` is asserted
in every arm that claims a retirement, because a seed that never reached the
block would satisfy a NULL assertion by doing nothing at all.
"""

from __future__ import annotations

import os
from contextlib import ExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres futures-poll "
            "round trip (CI job `search-recall` provides one)"
        ),
    ),
]

SPORT_KEY = "golf_masters_tournament_winner"
PRICED = "Scottie Scheffler"
VANISHED = "Joe Highsmith"
RECENTLY_ABSENT = "Nevill Ruiter"

#: The last quote the vanished leg carried before the book dropped it. Kept as a
#: real number so "the witness survived" is an assertion and not a tautology.
VANISHED_LAST_ODDS = 66792


def _response_market():
    """One bookmaker's column, carrying ONLY the leg that is still priced.

    The vanished legs are absent by omission — which is exactly how the venue
    expresses "this outcome is no longer in the field", and the only input the
    stale block ever gets.
    """
    return SimpleNamespace(
        bookmaker="draftkings",
        market_name="The Masters Winner",
        outcomes=[
            SimpleNamespace(name=PRICED, probability=0.25, american_odds=300),
            SimpleNamespace(name="Rory McIlroy", probability=0.20, american_odds=400),
        ],
    )


async def _seed(session):
    """Two stale legs and one that will be re-priced.

    `VANISHED` is the specimen: absent from the response AND older than the
    24-hour floor. `RECENTLY_ABSENT` is the control for that floor — absent from
    the same response, but seen an hour ago, so a transient venue omission must
    not retire it.
    """
    from app.models.models import FuturesMarket, FuturesOutcome

    now = datetime.now(timezone.utc)

    # No `Sport` row on purpose. `sports.key` is UNIQUE and this fixture no
    # longer drops anything, so seeding one would collide with a neighbour in
    # the shared CI database or with this file's own second run. The task links
    # through `sport_map.get(_infer_base_sport(...))` and
    # `futures_markets.sport_id` is nullable, so the absence costs nothing the
    # block under test can observe.
    market = FuturesMarket(
        source="odds_api",
        external_id=SPORT_KEY,
        sport_id=None,
        name="The Masters Winner",
        category="championship",
        mutually_exclusive=True,
        status="open",
    )
    session.add(market)
    await session.flush()

    session.add_all(
        [
            FuturesOutcome(
                market_id=market.id,
                external_id=PRICED,
                name=PRICED,
                current_probability=0.24,
                current_american_odds=310,
                last_updated=now - timedelta(days=3),
                rank=1,
                is_winner=None,
            ),
            FuturesOutcome(
                market_id=market.id,
                external_id=VANISHED,
                name=VANISHED,
                current_probability=0.05,
                current_american_odds=VANISHED_LAST_ODDS,
                probability_change_24h=-0.01,
                last_updated=now - timedelta(days=3),
                rank=9,
                is_winner=None,
            ),
            FuturesOutcome(
                market_id=market.id,
                external_id=RECENTLY_ABSENT,
                name=RECENTLY_ABSENT,
                current_probability=0.03,
                current_american_odds=3200,
                last_updated=now - timedelta(hours=1),
                rank=12,
                is_winner=None,
            ),
        ]
    )
    await session.commit()
    return market


async def _run_poll(session):
    """Run the REAL `_poll_futures_odds` against this session.

    The service is a stub rather than the real `OddsAPIService` with one method
    patched, because every call this task makes on it is network; the parse and
    the aggregation below it are the production functions, so the shape the
    block sees is the shape production builds.
    """
    service = SimpleNamespace(
        get_sports_with_outrights=AsyncMock(return_value=[{"key": SPORT_KEY}]),
        get_futures_odds=AsyncMock(return_value={}),
        _parse_futures=lambda response, sport_key: [_response_market()],
        last_requests_used=1,
        last_requests_remaining=None,  # skips the quota recorder, which is Redis
        close=AsyncMock(),
    )

    @asynccontextmanager
    async def _session_cm():
        yield session

    with ExitStack() as es:
        es.enter_context(
            patch("app.tasks.futures.OddsAPIService", return_value=service)
        )
        es.enter_context(patch("app.tasks.futures.get_task_session", _session_cm))
        es.enter_context(
            patch(
                "app.tasks.redis_state.check_quota_guard",
                return_value=(True, "test"),
            )
        )
        from app.tasks.futures import _poll_futures_odds

        stats = await _poll_futures_odds()

    # The per-sport loop swallows failures into `stats["errors"]` — it must, one
    # bad sport may not wipe a poll — so an unasserted error list would let a
    # silently-skipped market read as a passing round trip (gotcha #42/#53).
    assert stats["errors"] == [], f"the poll reported errors: {stats['errors']}"
    await session.commit()
    return stats


async def _legs(session):
    rows = await session.execute(
        text(
            "SELECT o.external_id, o.current_probability, o.current_american_odds, "
            "       o.probability_change_24h "
            "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
            " WHERE m.source = 'odds_api' AND m.external_id = :k"
        ),
        {"k": SPORT_KEY},
    )
    return {
        r[0]: {"prob": r[1], "american": r[2], "move": r[3]}
        for r in rows.fetchall()
    }


def _fk_closure(metadata, *names):
    """The named tables plus every table they reach through a foreign key.

    The sibling real-Postgres tests build the WHOLE schema, which needs
    PostgreSQL 15: `uq_container_anchor` is declared `NULLS NOT DISTINCT` and 14
    cannot parse it. The task under test writes four tables, so the closure of
    those four is both the honest scope and the reason this gate is runnable on
    the PG 14 a laptop has as well as the 15 CI provides — a gate only CI can
    run is a gate nobody runs before pushing.
    """
    want, seen = list(names), set()
    while want:
        name = want.pop()
        if name in seen:
            continue
        seen.add(name)
        for fk in metadata.tables[name].foreign_keys:
            want.append(fk.column.table.name)
    return [metadata.tables[n] for n in seen]


#: Everything this test owns, deleted child-first before each run. Scoped by the
#: market's own `external_id` rather than by table, which is what lets this gate
#: share a database with the ten steps that run before it in the same CI job.
_CLEAN = (
    """DELETE FROM futures_odds_snapshots s
        USING futures_outcomes o, futures_markets m
        WHERE s.outcome_id = o.id AND o.market_id = m.id
          AND m.source = 'odds_api' AND m.external_id = :k""",
    """DELETE FROM futures_outcomes o
        USING futures_markets m
        WHERE o.market_id = m.id
          AND m.source = 'odds_api' AND m.external_id = :k""",
    "DELETE FROM futures_markets WHERE source = 'odds_api' AND external_id = :k",
)


@pytest.fixture
async def pg_session():
    """Real Postgres, real schema, for the tables this task touches.

    Real Postgres and not a unit double because the market upsert compiles
    through `pg_insert(...).on_conflict_do_update(...)`, which no other dialect
    emits — the block under test only runs after that statement returns an id.

    🔴 IT DOES NOT DROP. The sibling real-Postgres fixtures open with
    `drop_all()` over the WHOLE schema, which is self-consistent: everything goes,
    so every dependency goes with it. A dropping fixture scoped to four tables is
    NOT the same thing, and the difference is invisible on a laptop. Eight other
    tables hold a foreign key INTO `futures_markets` (`prediction_challenges`,
    `settlement_captures`, `curation_signals`, …); on a fresh local database
    those tables do not exist, so the scoped `drop_all` succeeded, and in CI —
    where ten earlier steps in this same job have already built the full schema
    in the same database — it raised `DependentObjectsStillExistError` and every
    test in the file ERRORed at setup. So: create what is missing, delete only
    the rows this file owns, and leave the neighbours alone.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that created
    its engine.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    tables = _fk_closure(
        Base.metadata,
        "sports",
        "futures_markets",
        "futures_outcomes",
        "futures_odds_snapshots",
    )

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tables, checkfirst=True)
        # Both market keys: the producer fixture's and the repair fixture's.
        # Cleaning only the first leaves the repair rows behind, and the second
        # run of this file then plans over two generations of them.
        for key in (SPORT_KEY, REPAIR_KEY):
            for stmt in _CLEAN:
                await conn.execute(text(stmt), {"k": key})

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session

    await engine.dispose()


class TestAVanishedLegRetiresToNull:
    """The ship. Master stores 0 here and the page prints `0%`."""

    async def test_the_vanished_leg_holds_no_price_rather_than_a_zero(
        self, pg_session
    ):
        await _seed(pg_session)
        stats = await _run_poll(pg_session)

        assert stats.get("stale_zeroed") == 1, (
            "the stale block never ran, so the assertion below would pass on a "
            f"seed that was simply never touched. stats: {stats}"
        )

        got = await _legs(pg_session)
        assert got[VANISHED]["prob"] is None, (
            f"{VANISHED} stored {got[VANISHED]['prob']!r}. A stored 0 serves as "
            "`probability: 0.0` and renders a flat `0%` — the site asserting the "
            "outcome is IMPOSSIBLE. All this block observed is that the venue "
            "stopped listing it, which is `-`."
        )

    async def test_the_last_quote_is_not_destroyed_with_the_price(self, pg_session):
        """The odds column is the last honest thing we know; retiring is not erasing."""
        await _seed(pg_session)
        await _run_poll(pg_session)

        got = await _legs(pg_session)
        assert got[VANISHED]["american"] == VANISHED_LAST_ODDS, (
            "the surviving quote was overwritten. `current_american_odds` is the "
            "only record of what the book last said about this outcome, and the "
            "repair on the stored population keys on it being present."
        )

    async def test_the_movement_delta_retires_in_the_same_breath(self, pg_session):
        """CERT-627, co-asserted so a later edit to this block cannot drop it."""
        await _seed(pg_session)
        await _run_poll(pg_session)

        got = await _legs(pg_session)
        assert got[VANISHED]["move"] is None, (
            "a dead outcome has no movement, and this line refreshes "
            "`last_updated` — the stamp the movement window expires on — so "
            "leaving the delta hands `/api/futures/movers` a market that just "
            "vanished from the feed, wearing a fresh timestamp."
        )


class TestTheBlockStillOnlyTouchesWhatItShould:
    """Both controls. A mutation that widens the retirement fails here, not above."""

    async def test_a_leg_the_venue_still_prices_is_untouched(self, pg_session):
        await _seed(pg_session)
        await _run_poll(pg_session)

        got = await _legs(pg_session)
        assert got[PRICED]["prob"] is not None and float(got[PRICED]["prob"]) > 0, (
            f"{PRICED} is in the response and came back "
            f"{got[PRICED]['prob']!r} — the retirement reached a live leg."
        )

    async def test_a_leg_absent_for_only_an_hour_is_not_retired(self, pg_session):
        """The 24h floor: a transient venue omission is not a vanished outcome."""
        await _seed(pg_session)
        stats = await _run_poll(pg_session)

        got = await _legs(pg_session)
        assert got[RECENTLY_ABSENT]["prob"] is not None, (
            f"{RECENTLY_ABSENT} was last seen an hour ago and is absent from ONE "
            "response. Retiring it turns every transient API omission into a "
            f"dash on the page. stats: {stats}"
        )
        assert stats.get("stale_zeroed") == 1, (
            "exactly one leg qualifies; a second retirement means the floor "
            f"stopped holding. stats: {stats}"
        )


# ─── THE REPAIR HALF ────────────────────────────────────────────────────────
#
# Everything above guards the PRODUCER: new arrivals store NULL. The 373 legs
# already carrying a stored `0` are retired by
# `scripts/repair_5869_stale_futures_legs_claiming_impossible.py`, and until
# 2026-09-15 nothing executed one line of it.
#
# It shipped certed and GREEN, and its very first production invocation died on
# `ImportError: cannot import name 'AsyncSessionLocal'` — a symbol that exists
# nowhere in this codebase. The unit tests passed because they stub the session,
# and every statement in `run()` sits below that import. A repair that cannot
# open a connection is indistinguishable, from the outside, from a repair that
# ran and found nothing to do (gotcha #53).
#
# So this class drives the REAL `run()` against real PostgreSQL rather than
# re-implementing its steps here. A test that rebuilt the apply loop would have
# been green on the broken script, which is the whole failure being guarded.

REPAIR_KEY = "golf_masters_repair_5869"
REPAIR_STALE = ("Repair Stale One", "Repair Stale Two")
REPAIR_LIVE = "Repair Live Sibling"
REPAIR_NO_ODDS = "Repair Zero With No Odds"
REPAIR_SETTLED = "Repair Zero But Settled"

#: The price the book puts back on a retired leg AFTER the repair ran. Any real
#: number works; it only has to be distinguishable from the stale 0.
REPRICED = 0.07


def _repair_module():
    """Load the repair script by path — `backend/scripts/` is not a package."""
    import importlib.util
    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "scripts"
        / "repair_5869_stale_futures_legs_claiming_impossible.py"
    )
    spec = importlib.util.spec_from_file_location("_repair_5869", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _seed_repair(session):
    """Legs already carrying a stored 0 — the population the producer fix cannot reach.

    Two specimens plus three controls, one of which (`REPAIR_LIVE`) is also load
    bearing in the other direction: the repair's `EXISTS (sibling priced within
    7 days)` clause means the specimens are only selected BECAUSE this row is
    here and fresh.
    """
    from app.models.models import FuturesMarket, FuturesOutcome

    now = datetime.now(timezone.utc)
    stale = now - timedelta(days=3)

    market = FuturesMarket(
        source="odds_api",
        external_id=REPAIR_KEY,
        sport_id=None,
        name="The Masters Winner (repair fixture)",
        category="championship",
        mutually_exclusive=True,
        status="open",
    )
    session.add(market)
    await session.flush()

    rows = [
        # the specimens: stored 0 beside a real quote, nothing settled
        (REPAIR_STALE[0], 0, 331909, stale, None),
        (REPAIR_STALE[1], 0, 221277, stale, None),
        # the fresh sibling that qualifies the market
        (REPAIR_LIVE, 0.42, -150, now, None),
        # control: a 0 with no surviving quote is not this defect's fingerprint
        (REPAIR_NO_ODDS, 0, None, stale, None),
        # control: a graded 0 is a RESULT, and results are never rewritten
        (REPAIR_SETTLED, 0, 331909, stale, "espn"),
    ]
    for name, prob, american, seen, resolution in rows:
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=name,
                name=name,
                current_probability=prob,
                current_american_odds=american,
                last_updated=seen,
                resolution_source=resolution,
            )
        )
    await session.commit()
    return market.id


async def _repair_ids(session):
    """This fixture's outcome ids by name — the rollback is asserted by membership."""
    rows = await session.execute(
        text(
            "SELECT o.external_id, o.id "
            "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
            " WHERE m.source = 'odds_api' AND m.external_id = :k"
        ),
        {"k": REPAIR_KEY},
    )
    return {r[0]: r[1] for r in rows.fetchall()}


async def _repair_legs(session):
    rows = await session.execute(
        text(
            "SELECT o.external_id, o.current_probability, o.current_american_odds "
            "  FROM futures_outcomes o JOIN futures_markets m ON m.id = o.market_id "
            " WHERE m.source = 'odds_api' AND m.external_id = :k"
        ),
        {"k": REPAIR_KEY},
    )
    return {r[0]: {"prob": r[1], "american": r[2]} for r in rows.fetchall()}


async def _run_repair(module, session, monkeypatch, **flags):
    """Call the script's own `run()`, on this session, as an attended invocation.

    `run()` resolves `async_session_maker` from `app.services.database` at call
    time, so patching the attribute is what redirects it at the test database —
    and it is also why a symbol that does not exist there fails this test rather
    than reaching production.
    """
    import app.services.database as database_module

    @asynccontextmanager
    async def _session():
        yield session

    monkeypatch.setattr(database_module, "async_session_maker", _session)
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")

    args = SimpleNamespace(**{"backup": False, "apply": False, "limit": 0, **flags})
    return await module.run(args)


async def _clear_repair_banks(session, module):
    """Drop this fixture's rows out of the runtime backup tables, if they exist."""
    for table in (module.BAK_TABLE, module.MANIFEST_TABLE):
        present = (
            await session.execute(text(f"SELECT to_regclass('{table}') IS NOT NULL"))
        ).scalar_one()
        if present:
            await session.execute(
                text(
                    f"DELETE FROM {table} WHERE outcome_id IN ("
                    "  SELECT o.id FROM futures_outcomes o"
                    "    JOIN futures_markets m ON m.id = o.market_id"
                    "   WHERE m.source = 'odds_api' AND m.external_id = :k)"
                ),
                {"k": REPAIR_KEY},
            )
            # …and the previous run's ids, whose outcomes the fixture already
            # deleted. They reconcile against nothing, but they accumulate in a
            # CI database that ten other steps share.
            await session.execute(
                text(
                    f"DELETE FROM {table} b WHERE NOT EXISTS ("
                    "  SELECT 1 FROM futures_outcomes o WHERE o.id = b.outcome_id)"
                )
            )
    await session.commit()


class TestTheRepairActuallyRuns:
    """The roundtrip, executed. Its absence is why the first invocation died."""

    async def test_the_repair_retires_the_stored_zeros_and_spares_the_controls(
        self, pg_session, monkeypatch
    ):
        module = _repair_module()
        await _seed_repair(pg_session)
        await _clear_repair_banks(pg_session, module)

        code = await _run_repair(
            module, pg_session, monkeypatch, backup=True, apply=True
        )
        assert code == 0, (
            f"the repair exited {code}. A non-zero here is the script refusing "
            "or crashing — and a crash looks exactly like a clean no-op from "
            "the outside, which is how the AsyncSessionLocal defect reached "
            "production certed GREEN."
        )

        got = await _repair_legs(pg_session)
        for name in REPAIR_STALE:
            assert got[name]["prob"] is None, (
                f"{name} still stores {got[name]['prob']!r}. The stored 0 is the "
                "reader-visible half of #5869: it serves as `probability: 0.0` "
                "and prints a flat `0%`, the site asserting IMPOSSIBLE."
            )
            assert got[name]["american"] is not None, (
                f"{name} lost its last quote. Retiring a price is not erasing "
                "the record of what the book last said."
            )

        assert float(got[REPAIR_LIVE]["prob"]) == pytest.approx(0.42), (
            "the repair reached the priced sibling — the one row that must "
            "survive, since it is what qualifies the market in the first place."
        )
        assert got[REPAIR_NO_ODDS]["prob"] == 0, (
            "a 0 with no surviving quote does not carry this defect's "
            "fingerprint; retiring it widens the repair past what was measured."
        )
        assert got[REPAIR_SETTLED]["prob"] == 0, (
            "a graded 0 is a RESULT. Settled means settled — this repair may "
            "never rewrite one."
        )

    async def test_the_restore_does_not_overwrite_a_price_that_came_back(
        self, pg_session, monkeypatch
    ):
        """The documented undo, run after the book re-prices a retired leg.

        Measured 2026-09-15: the unguarded form put the stale `0` back over a
        real `0.07`, re-asserting IMPOSSIBLE about an outcome that is quoted
        again — an undo that reintroduces the defect on a NEWER row than the one
        it banked. The `IS NULL` clause is the reverse of the forward write's
        compare-and-swap and is what makes the rollback safe to keep offering.
        """
        module = _repair_module()
        await _seed_repair(pg_session)
        await _clear_repair_banks(pg_session, module)

        await _run_repair(module, pg_session, monkeypatch, backup=True, apply=True)

        # the producer sees this leg again and stores a real number
        await pg_session.execute(
            text(
                "UPDATE futures_outcomes o SET current_probability = :p "
                "  FROM futures_markets m "
                " WHERE m.id = o.market_id AND m.external_id = :k "
                "   AND o.external_id = :n"
            ),
            {"p": REPRICED, "k": REPAIR_KEY, "n": REPAIR_STALE[0]},
        )
        await pg_session.commit()

        # The script's OWN rollback statement, not a copy of it. A copy here
        # would stay green while the documented undo rotted — the defect this
        # test exists for lived in the prose form, not in the test's idea of it.
        restored = {
            r[0] for r in (await pg_session.execute(text(module.SQL["restore"]))).fetchall()
        }
        await pg_session.commit()

        # Asserted by MEMBERSHIP, not by row count. The rollback is global on
        # purpose — it undoes the whole manifest, which is what a rollback is —
        # so in the CI database it also restores whatever a neighbouring run
        # banked, and a count assertion here would fail on other people's rows.
        ids = await _repair_ids(pg_session)
        assert ids[REPAIR_STALE[1]] in restored, (
            "the leg nobody re-priced was not restored, so the guard clause is "
            "sparing everything and the rollback does nothing at all."
        )
        assert ids[REPAIR_STALE[0]] not in restored, (
            "the rollback restored the leg the book re-priced. That is the "
            "clobber: a stale 0 written back over a live quote."
        )

        got = await _repair_legs(pg_session)
        assert float(got[REPAIR_STALE[0]]["prob"]) == pytest.approx(REPRICED), (
            f"the restore overwrote a refreshed {REPRICED} with "
            f"{got[REPAIR_STALE[0]]['prob']!r}. Dropping the `IS NULL` clause "
            "turns the rollback into a second bug: it re-asserts IMPOSSIBLE "
            "about a leg the book is quoting again."
        )
        assert got[REPAIR_STALE[1]]["prob"] == 0, (
            "the leg that nobody re-priced was NOT restored, so the guard is "
            "not sparing rows by refusing to do anything at all."
        )
