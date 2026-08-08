"""#1494 — the search RECALL contract, executed against a real Postgres.

Why this file exists
--------------------
LAT-P002 sped up ``/api/events/search`` and was reverted (``f98d8104``) after
3 of 8 sampled production queries came back with ZERO futures. Its own
acceptance criterion 3 — the frozen gold set, no regression from 21/25 — was
listed as **OWED and never run**.

It was never run because nothing in this repo could run it:

* ``tests/integration/test_route_search.py`` uses a mock EMPTY db session, so
  the WHERE clause never executes against data — it pins response *shape*.
* the other ``*_seeded.py`` suites hand ``MagicMock`` rows back through a mocked
  session; again, no SQL runs.
* ``scripts/evals/search_gold_eval.py`` is a *scorer* — it grades results you
  give it. It does not fetch them.

So a whole class of defect — "the predicate silently stopped matching real
rows" — had no guard anywhere, on the p1 search surface. This file is that
guard: real Postgres, real tables, real ``pg_trgm``, real SQL, seeded rows that
MUST come back.

Following the precedent of ``tests/test_calibration_canonical_pg.py``: opt-in on
an env var so it skips where no Postgres exists, and wired into a dedicated CI
job (``search-recall`` in ``.github/workflows/ci.yml``) that provides one. CI is
the environment that runs this — not a dev sandbox.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \
        python3 -m pytest tests/integration/test_search_recall_contract.py -v

What each case guards
---------------------
The three queries that actually broke in production, plus the recall arms the
re-land changes:

===========================  ==========================================
case                         arm it exercises
===========================  ==========================================
masters winner               multi-term AND over ``FuturesMarket.name``
us recession 2026            name arm with a numeric term
nba champion                 name arm under a LEAGUE token present
nfl mvp                      ``_build_league_ticker_match`` (#993 L2-43)
outcome-only                 ``_outcome_id_match`` subquery
nba (league only)            bare-league arm (``league_only_explicit``)
us recession (both arms)     the LAT-P006 ``UNION`` returns EVERY arm
us recession (control row)   a sub-3-char term still FILTERS
===========================  ==========================================

``nfl mvp`` and the outcome-only case are the subtle ones: in both, the market
NAME does not contain the whole query, so a predicate change that looks
harmless on name matching alone silently drops them.

NOTE for the re-land (#1494): commit ``2c9f961f`` claims 1c drops the FTS arm
from the WHERE with "IDENTICAL recall on the frozen benchmark". **That claim has
never been tested.** These cases are what test it. (Result: it held — the
re-land preserved recall on 7 of 8 production queries where LAT-P002 lost 3.)

SCOPE LIMIT — read this before quoting a green run
--------------------------------------------------
**This gate proves PREDICATE recall, not production recall.** It seeds a handful
of rows, so every query here is fast and nothing ever hits the request budget.

That is not hypothetical. On the LAT-P005 re-land this gate reported
``SEARCH RECALL 5/5`` and CI went green, while production STILL returned zero
futures for ``us recession 2026`` — that query costs ~23.6s against the real
table and gets dropped at the 20s deadline. **Both results were correct.** The
predicate matches; the query is too slow to finish.

So a green n/n here rules out exactly one failure mode: "the WHERE clause stopped
matching rows it should match". It says nothing about:

* timeout-induced loss, which is a function of real data volume and load;
* ranking or ordering;
* anything about a table larger than the seed.

Catching the timeout class needs a cost bound on the query itself, not a recall
assertion. LAT-P006 delivered that bound as a SQL-SHAPE guard —
``TestFuturesRecallArmsAreUnionedNotOred`` in
``tests/test_search_latency_contract.py`` — rather than as a plan or wall-clock
assertion, precisely because neither is meaningful on a small seed. Do not let a
green run HERE stand in for that; they guard different failure modes.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres search recall "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]


# --------------------------------------------------------------------------
# Schema + seed
# --------------------------------------------------------------------------
# `Base.metadata.create_all` rather than `alembic upgrade head`: this gate is
# about the PREDICATE's recall, and the migration chain has its own guard
# (`tests/test_alembic.py`). create_all is derived from the same models the
# route queries, so the columns are identical, and it keeps the CI job fast and
# free of Heroku-release-specific migration behaviour.
#
# `pg_trgm` IS required — the fuzzy fallback uses `similarity()`/`%`, which do
# not exist without the extension. Index presence deliberately is NOT required:
# an index changes plan and speed, never the result set, so recall is
# index-independent by construction.

_FUTURES_SEEDS = [
    # (external_id, name, [outcome names])
    ("kalshi-masters-2026", "Masters Tournament Winner 2026", ["Scottie Scheffler"]),
    ("kalshi-recession-2026", "US Recession in 2026?", ["Yes", "No"]),
    ("kalshi-nbachamp-2026", "NBA Champion 2026", ["Boston Celtics"]),
    # League-ticker recall: "nfl" appears ONLY in the ticker, never in the name.
    ("KXNFLMVP-26", "MVP Winner?", ["Patrick Mahomes"]),
    # Outcome-only recall: the market name contains neither query term.
    ("kalshi-outcome-only", "Award Winner 2026", ["Caitlin Clark"]),
    # LAT-P006: `us recession` must return BOTH arms' rows. This one is reachable
    # ONLY via the outcome arm (the NAME contains neither "us" nor "recession"),
    # while "US Recession in 2026?" above is reachable only via the name arm. One
    # query, two arms, two different markets — so a change that collapses the
    # UNION to a single arm, or to an intersection, fails loudly instead of
    # quietly halving recall.
    ("kalshi-us-gdp", "Q4 GDP print above 3%?", ["US recession averted"]),
    # LAT-P006 control: matches `%recession%` but NOT `%us%`, in name or outcome.
    # It must stay OUT of the `us recession` result. This is what makes the
    # 2-character term's ENFORCEMENT observable — LAT-P006 staged "drop sub-3-char
    # terms from the outcome arm" as a candidate fix, and that candidate would let
    # this row in. The chosen UNION fix does not, and this pins the difference.
    ("kalshi-euro-gdp", "Euro area growth 2026?", ["Recession likely"]),
]


async def _seed(session):
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    nba = Sport(key="basketball_nba", name="NBA")
    golf = Sport(key="golf_pga", name="PGA")
    session.add_all([nba, golf])
    await session.flush()

    # One NBA event so the league-only query has something to find.
    session.add(
        Event(
            sport_id=nba.id,
            home_team_name="Boston Celtics",
            away_team_name="Los Angeles Lakers",
            commence_time=datetime.now(timezone.utc) + timedelta(days=2),
            status="scheduled",
        )
    )

    for external_id, name, outcomes in _FUTURES_SEEDS:
        market = FuturesMarket(
            source="kalshi",
            external_id=external_id,
            name=name,
            status="open",
            # Must be in the future: the route filters
            # `resolution_date IS NULL OR resolution_date >= now()`.
            resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
        )
        session.add(market)
        await session.flush()
        for outcome_name in outcomes:
            session.add(
                FuturesOutcome(
                    market_id=market.id,
                    external_id=f"{external_id}:{outcome_name}",
                    name=outcome_name,
                )
            )
    await session.commit()


@pytest.fixture
async def seeded_db():
    """A real Postgres with the real schema and the seed rows above.

    Function-scoped deliberately. ``pytest.ini`` leaves
    ``asyncio_default_fixture_loop_scope`` unset, so a module-scoped async
    fixture would outlive the function-scoped event loop that created its
    engine and fail on a closed loop. Re-seeding five markets per test is
    cheap, and it buys full isolation between cases.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await _seed(session)

    yield engine, maker

    await engine.dispose()


@pytest.fixture
async def search(seeded_db):
    """Call the REAL route through the app, against the REAL database."""
    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    _engine, maker = seeded_db

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:

        async def _do(q: str) -> dict:
            resp = await client.get("/api/events/search", params={"q": q})
            assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
            return resp.json()

        yield _do

    app.dependency_overrides.clear()


@pytest.fixture
async def typeahead(seeded_db):
    """LAT-P007: the same real-Postgres treatment for `/typeahead`.

    Nothing in this repo exercised typeahead recall against real rows, so its
    predicate could be changed freely and silently. It is the surface that fires
    on every keystroke, so it deserves the guard more than `/search` does, not
    less.

    Redis is patched out: `typeahead_search` reads a cache before touching the
    database, and a hit would make every assertion here test Redis instead of the
    predicate.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.services.database import get_db, get_db_rw

    _engine, maker = seeded_db

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override

    with patch("app.tasks.redis_state.get_redis_client", side_effect=RuntimeError("no redis")):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def _do(q: str) -> dict:
                resp = await client.get("/api/events/typeahead", params={"q": q})
                assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
                return resp.json()

            yield _do

    app.dependency_overrides.clear()


def _typeahead_texts(payload) -> list[str]:
    items = payload.get("suggestions", payload) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    return [str(i.get("text") or i.get("name") or "") for i in items if isinstance(i, dict)]


def _futures_names(payload: dict) -> list[str]:
    return [f.get("name") or f.get("market_name") for f in payload.get("futures", [])]


# --------------------------------------------------------------------------
# The contract
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query,must_find",
    [
        # The three that actually returned ZERO futures in production.
        ("masters winner", "Masters Tournament Winner 2026"),
        ("us recession 2026", "US Recession in 2026?"),
        ("nba champion", "NBA Champion 2026"),
        # Name contains no "nfl" — reachable ONLY via the ticker prefix arm.
        ("nfl mvp", "MVP Winner?"),
    ],
)
async def test_query_returns_its_market(search, query, must_find):
    names = _futures_names(await search(query))
    assert must_find in names, (
        f"RECALL REGRESSION: {query!r} returned {names!r}, missing {must_find!r}. "
        "A query that returns HTTP 200 with the right answer absent is worse "
        "than a slow one — this is the exact shape that reverted LAT-P002."
    )


async def test_outcome_only_recall(search):
    """The market NAME contains neither term; only an OUTCOME name matches.

    Guards `_outcome_id_match`. A predicate change that keeps name matching
    working drops this silently.
    """
    names = _futures_names(await search("caitlin clark"))
    assert "Award Winner 2026" in names, (
        f"outcome-only recall lost: got {names!r}"
    )


async def test_union_returns_rows_from_every_recall_arm(search):
    """LAT-P006: the recall arms are UNIONed, so one query returns BOTH arms.

    `us recession` reaches "US Recession in 2026?" only through the NAME arm and
    "Q4 GDP print above 3%?" only through the OUTCOME arm. Both must come back.

    This is the guard for the shape LAT-P006 shipped. Combining the arms with a
    top-level `OR` timed out in production (>10s; the live request measured
    23.57s and returned zero futures for a market that exists), so they are now
    combined with `UNION` — set-identical, 437ms. The failure mode a UNION
    introduces that an OR cannot is collapsing to ONE arm, or to an INTERSECT.
    Either halves recall while every single-arm test in this file still passes.
    """
    names = _futures_names(await search("us recession"))
    assert "US Recession in 2026?" in names, (
        f"NAME-arm row lost from the union: got {names!r}"
    )
    assert "Q4 GDP print above 3%?" in names, (
        f"OUTCOME-arm row lost from the union: got {names!r}. The arms are being "
        "intersected or one arm was dropped — a UNION must return both."
    )


async def test_short_term_is_still_enforced_in_the_outcome_arm(search):
    """A sub-3-character term still FILTERS; it was not dropped to buy speed.

    `%us%` is a 2-char infix pattern, unservable by a pg_trgm GIN, and it seq-scans
    3 GB of `futures_outcomes` in production (6,865ms for 64,200 rows — where the
    3-char control `%ing%` returns MORE rows in 1,171ms). The tempting fix is to
    drop such terms from the outcome arm. LAT-P006 measured that the term is not
    the driver — the top-level OR is — and fixed the OR instead, so the term keeps
    its meaning.

    "Euro area growth 2026?" matches `%recession%` (outcome "Recession likely")
    but nothing matches `%us%`. If it starts appearing for `us recession`, a short
    term has been silently dropped and the query now means something else.
    """
    names = _futures_names(await search("us recession"))
    assert "Euro area growth 2026?" not in names, (
        f"the 2-char term `us` stopped filtering: got {names!r}. Dropping "
        "sub-3-char terms widens the query — that is a precision regression, not "
        "an optimisation."
    )


async def test_league_only_query_still_broad(search):
    """`league_only_explicit`: a bare league token keeps the wide arm.

    The re-land's 1b narrows the league arm by AND-ing the remaining terms.
    A league-ONLY query has no remaining terms and must not be narrowed to
    nothing.
    """
    payload = await search("nba")
    found = payload.get("results") or []
    assert found or _futures_names(payload), (
        "a bare league query returned nothing at all — 1b over-narrowed"
    )


async def test_recall_summary(search, capsys):
    """Emit the found-count the way criterion 3 asks for it.

    Printed so the CI job log carries the numbers, satisfying #1494's
    'RUN, with output quoted' — a gate whose result nobody can read is the
    same as a gate nobody ran.
    """
    cases = [
        ("masters winner", "Masters Tournament Winner 2026"),
        ("us recession 2026", "US Recession in 2026?"),
        ("nba champion", "NBA Champion 2026"),
        ("nfl mvp", "MVP Winner?"),
        ("caitlin clark", "Award Winner 2026"),
    ]
    found, missing = 0, []
    for query, expected in cases:
        if expected in _futures_names(await search(query)):
            found += 1
        else:
            missing.append(query)

    with capsys.disabled():
        print(f"\nSEARCH RECALL: {found}/{len(cases)} found", flush=True)
        if missing:
            print(f"SEARCH RECALL MISSING: {missing}", flush=True)
        # Printed EVERY run, next to the number, because the number is the thing
        # people will quote. See SCOPE LIMIT in the module docstring: this gate
        # went 5/5 green on the LAT-P005 re-land while production still returned
        # zero futures for `us recession 2026`. Both were correct.
        print(
            "SEARCH RECALL SCOPE: predicate recall only, on a small seeded DB. "
            "This gate CANNOT detect timeout-induced recall loss (#1494) — a green "
            "n/n here does not mean production recall is intact.",
            flush=True,
        )

    assert found == len(cases), f"recall {found}/{len(cases)}, missing {missing}"


# --------------------------------------------------------------------------
# LAT-P007 — /typeahead recall, against real Postgres
# --------------------------------------------------------------------------
async def test_typeahead_still_finds_its_market(typeahead):
    """The 3-char+ path keeps working after the UNION + non-correlated rewrite.

    `/typeahead` measured 9,682ms -> 2,414ms on the same 990 production rows.
    Both changes are set-identical, so recall must be untouched.
    """
    texts = _typeahead_texts(await typeahead("recession"))
    assert any("Recession" in t for t in texts), (
        f"typeahead lost its market: got {texts!r}"
    )


async def test_typeahead_outcome_recall_survives_above_the_threshold(typeahead):
    """The outcome arm still runs at 3+ characters.

    "Award Winner 2026" is reachable ONLY through an outcome name
    ("Caitlin Clark"). The sub-3-char skip must not have disabled the arm
    outright — it is scoped to short queries, nothing else.
    """
    texts = _typeahead_texts(await typeahead("caitlin"))
    assert any("Award Winner" in t for t in texts), (
        f"typeahead outcome-name recall lost above the threshold: got {texts!r}"
    )


async def test_typeahead_short_query_answers_without_the_outcome_scan(typeahead):
    """A 2-char query must still answer, and must not 500.

    At two characters the outcome arm is skipped: it measured 8,633ms against
    3 GB of `futures_outcomes` and returned 17 of 20 visible rows as substring
    accidents (Lamprecht, Baltimore, Guterres). The endpoint still has to
    RESPOND — `min_length=2`, so this is a legal query and the most common one
    a user fires.
    """
    payload = await typeahead("re")
    assert isinstance(_typeahead_texts(payload), list)
