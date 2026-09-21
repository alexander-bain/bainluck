"""#6354: the iPhone Browse list stops opening on rows that have no number.

`GET /api/futures/faceted` is the Browse tab's list — `FuturesListViewModel.load()`
opens on `?page=1&per_page=20&sort=soonest`, no category — and it had no outcome
gate at all. Measured on production 2026-09-15, the app's own query, three sorts
x five screens of 20:

    soonest (THE DEFAULT)   44 / 100 answer-less   (page 1 alone: 12 of 20)
    newest                  10 / 100
    trending                 0 / 100

## why this file drives real PostgreSQL and not a session double

The fix is a WHERE clause. A `FakeDB` that returns its rows whatever the query
says — the shape `test_futures_browse_unrankable_leader_uxp165.py` uses, which is
right for a display-logic fix — **cannot observe a predicate**, so a guard built
on one would be green before the fix and green after it: a vacuous test on the
exact axis that matters. The server has to be the oracle.

## what is actually being pinned, beyond "the blank row is gone"

The formatter counts outcomes AFTER `_GARBAGE_OUTCOME_RE`, so "has a row" and
"has a row a reader can see" are two different predicates and the route now
depends on them agreeing. They are written in two languages — Python `re` in the
formatter, POSIX `~*` in the gate — and they diverge in four places if nobody is
watching:

  * `re.match` anchors only at the start; POSIX `~*` anchors nowhere.
  * a NULL name is a REAL outcome to the formatter (`o.name or ""` is `""`, which
    the pattern does not match) and would be NULL — hence not-true, hence
    EXCLUDED — to a bare `!~*`.
  * `$` is not `$`: Python's matches before one trailing newline, POSIX's does
    not. Hence the `\n?`.
  * **`\s` is not `[[:space:]]`, and whether it is depends on the server.**
    Python's `\s` is Unicode and fixed; `[[:space:]]` is the database's ctype. The
    first version of this file hand-picked five Unicode spaces, found them equal,
    and wrote "measured equal here" into the route — true of PostgreSQL 14 at
    `en_US.UTF-8`, false of CI's server, which does not take NBSP. PG 14 in turn
    failed on `\x85` and `\x1c`, which the five did not include. Each one is a
    name the formatter calls garbage and the gate calls answerable: the blank row,
    again. The route now writes the class out from Python's own set, so the two
    agree by construction rather than by a measurement of one machine, and this
    file generates all 29 characters instead of choosing some.

So the equivalence itself is a test, graded by running both engines over the same
names on the same server. That is what stops a later widening of the regex from
quietly reopening the hole in the gate, which is the failure this whole class is
made of.

Two of the tests here need no Postgres and are not skipped — the written-out class
and the shape of the SQL mirror are graded on a laptop with no database, because
"the guard only runs where the schema builds" is how the NOT NULL `external_id`
in `_seed` survived into CI.
"""

from __future__ import annotations

import os

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres faceted "
        "answerability contract (CI job `search-recall` provides one)"
    ),
)


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped for the reason `test_tag_counts_real_postgres.py` records:
    `pytest.ini` leaves `asyncio_default_fixture_loop_scope` unset, so a
    module-scoped async fixture would outlive the loop that created its engine.
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


@pytest.fixture
async def pg_session(pg_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    maker = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


async def _seed(session, rows):
    """Insert `(name, tag, outcome_names)` markets; `outcome_names=[]` means none.

    `resolution_date` is left NULL so every row satisfies the route's unresolved
    arm and the ordering between them is never what decides a test.

    🔴 `external_id` IS SET, and it has to be. The column is NOT NULL, so a seed
    that omits it raises `NotNullViolationError` on the INSERT and every test in
    this file errors before it asserts anything — which is exactly how this file
    first ran in CI. It is invisible on a machine that cannot run the file at all
    (the schema needs PostgreSQL 15 for `NULLS NOT DISTINCT`; Homebrew's default
    is 14), so the harness was only ever graded by the server that could build it.
    The value is per-row unique because the real table treats it as an identity.
    """
    from app.models import FuturesMarket, FuturesOutcome

    made = {}
    for index, (name, tag, outcome_names) in enumerate(rows):
        market = FuturesMarket(
            name=name,
            source="polymarket",
            external_id=f"seed-6354-{index}",
            status="open",
            event_id=None,
            resolution_date=None,
            market_tags=[tag],
            llm_sport_category="tennis",
        )
        session.add(market)
        await session.flush()
        for position, outcome_name in enumerate(outcome_names):
            session.add(
                FuturesOutcome(
                    market_id=market.id,
                    external_id=f"seed-6354-{index}-{position}",
                    name=outcome_name,
                    current_probability=0.5,
                )
            )
        made[name] = market.id
    await session.commit()
    return made


async def _faceted(session, **kwargs):
    """Drive the real route function.

    Every `Query(...)` parameter is passed explicitly: calling a FastAPI endpoint
    as a plain function leaves the defaults bound as `Query` objects, which
    SQLAlchemy then tries to coerce.
    """
    from app.routes.futures import faceted_futures_search

    params = dict(
        tags=None,
        sport=None,
        category=None,
        stakes=None,
        narrative=None,
        audience=None,
        q=None,
        sort=None,
        page=1,
        per_page=25,
        db=session,
    )
    params.update(kwargs)
    return await faceted_futures_search(**params)


# ── the strawman arm ─────────────────────────────────────────────────────────
#
# Without this, every assertion below could pass against a route that served
# nothing at all, or against a harness whose seed never reached the server.


@needs_postgres
async def test_the_harness_really_can_serve_a_market(pg_session):
    """A priced market arrives. If this fails, nothing else in this file means
    anything — the seeds, the session and the route are the instrument."""
    await _seed(pg_session, [("Priced market", "sport:tennis", ["Alcaraz", "Sinner"])])

    payload = await _faceted(pg_session)

    assert [m["name"] for m in payload["markets"]] == ["Priced market"]
    assert payload["total"] == 1
    assert payload["markets"][0]["outcome_count"] == 2


@needs_postgres
async def test_the_harness_really_can_serve_the_defect(pg_session):
    """The answer-less row is reachable when the gate is not looking.

    Proved by asking the same server the pre-fix question directly, rather than
    by trusting that the seed would have shown up: if this row could not reach a
    page even without a gate, the ship test below would be green for the wrong
    reason (an empty control), which is the failure mode notice 50 is about.
    """
    from sqlalchemy import text

    await _seed(pg_session, [("Answer-less market", "sport:tennis", [])])

    ungated = await pg_session.execute(
        text(
            "SELECT count(*) FROM futures_markets "
            "WHERE status = 'open' AND event_id IS NULL "
            "AND (resolution_date IS NULL OR resolution_date >= now())"
        )
    )
    assert ungated.scalar() == 1, (
        "the seeded answer-less market does not satisfy the route's OTHER base "
        "conditions, so its absence below would prove nothing about the gate"
    )


# ── the ship ─────────────────────────────────────────────────────────────────


@needs_postgres
async def test_a_market_with_no_outcome_rows_is_not_served(pg_session):
    await _seed(
        pg_session,
        [
            ("Priced market", "sport:tennis", ["Alcaraz", "Sinner"]),
            ("Answer-less market", "sport:tennis", []),
        ],
    )

    payload = await _faceted(pg_session)

    assert [m["name"] for m in payload["markets"]] == ["Priced market"]


@needs_postgres
async def test_total_excludes_it_so_the_app_can_trust_has_more(pg_session):
    """`hasMore` is `markets.count < total` in `FuturesListViewModel`.

    A `total` that still counted the withdrawn rows would leave the app asking
    for pages that can never fill, so the count query and the page query have to
    move together — which is the whole reason the predicate lives in the shared
    `conditions` list rather than in a filter over the formatted page.
    """
    await _seed(
        pg_session,
        [
            ("Priced market", "sport:tennis", ["Alcaraz", "Sinner"]),
            ("Answer-less one", "sport:tennis", []),
            ("Answer-less two", "sport:tennis", []),
        ],
    )

    payload = await _faceted(pg_session)

    assert payload["total"] == 1
    assert len(payload["markets"]) == 1


@needs_postgres
async def test_a_facet_chip_counts_only_what_tapping_it_would_show(pg_session):
    """A chip is a promise about the list.

    The facet counter is raw SQL and the list filter is ORM; they are two
    statements that must mean one thing, so this asserts the chip's number
    against the `total` of the request that chip issues.
    """
    await _seed(
        pg_session,
        [
            ("Priced market", "sport:tennis", ["Alcaraz", "Sinner"]),
            ("Answer-less one", "sport:tennis", []),
            ("Answer-less two", "sport:tennis", []),
        ],
    )

    payload = await _faceted(pg_session)

    chip = next(
        tag for tag in payload["facets"]["sport"] if tag["tag"] == "sport:tennis"
    )
    tapped = await _faceted(pg_session, tags='["sport:tennis"]')

    assert chip["count"] == 1
    assert chip["count"] == tapped["total"]


@needs_postgres
async def test_every_served_row_has_a_number_including_the_garbage_named(pg_session):
    """The contract, stated as the reader would: no row arrives with nothing on it.

    A market whose every outcome is named `player AB` is the second road to the
    same blank card — `_GARBAGE_OUTCOME_RE` empties it in the formatter, so a gate
    that asked only "does a row exist" would serve it with `outcome_count: 0`.
    Production holds none of these today; the gate covers them anyway, because an
    empty set is a reason to keep a gate honest, not a licence to leave a hole.
    """
    await _seed(
        pg_session,
        [
            ("Priced market", "sport:tennis", ["Alcaraz", "Sinner"]),
            ("Garbage-named only", "sport:tennis", ["player A", "player BC"]),
        ],
    )

    payload = await _faceted(pg_session)

    assert [m["name"] for m in payload["markets"]] == ["Priced market"]
    assert all(m["outcome_count"] > 0 for m in payload["markets"])


@needs_postgres
async def test_the_is_null_arm_is_defence_and_the_schema_says_so(pg_session):
    """The `IS NULL` arm, graded honestly — it guards a state the column forbids.

    🔴 THIS TEST USED TO SEED `name=None` AND ASSERT THE ROW SURVIVED, and that
    was wrong in a way worth keeping written down: `futures_outcomes.name` is
    `NOT NULL`, in the model AND on production (`information_schema` says
    `is_nullable = NO`; `count(*) WHERE name IS NULL` is 0 of ~1.1M). So the seed
    could not be inserted at all — it died on the constraint, in CI, where the
    file first ran — and the thing it claimed to prove ("a nameless-but-priced
    rung stays on the page") describes a row that cannot exist.

    The `IS NULL` arm STAYS. It costs nothing, it fails safe, and the SQL reason
    for it is real: a bare `name !~* '…'` is NULL — hence not true, hence
    excluded — for a NULL name, so the arm is what the predicate would need the
    day that column becomes nullable. What changes is the claim: it is defence,
    not a live path, and the file may not pretend otherwise.

    So this asserts the world we are actually in, and becomes a tripwire the day
    we leave it: if `name` is ever made nullable, this fails and whoever did it
    re-reads the arm and writes the behavioural test that is possible by then.
    """
    from sqlalchemy import text

    nullable = (
        await pg_session.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'futures_outcomes' AND column_name = 'name'"
            )
        )
    ).scalar()

    assert nullable == "NO", (
        "`futures_outcomes.name` is now nullable — the `IS NULL` arm of "
        "`_HAS_ANY_OUTCOME_ROW` just stopped being defensive and became a live "
        "path. Write the behavioural test that is possible now, and correct the "
        "route comment, which describes this arm as guarding real rows."
    )

    # The arm is still there. Textual, deliberately: there is no reachable state
    # left to observe it with, and a test that cannot fail is worse than one that
    # says plainly which kind of check it is.
    from app.routes.futures import _HAS_ANY_OUTCOME_ROW

    assert "IS NULL" in str(
        _HAS_ANY_OUTCOME_ROW.compile(compile_kwargs={"literal_binds": True})
    ), "the IS NULL arm was removed while the column it guards is still NOT NULL"


@needs_postgres
async def test_the_gate_and_the_formatter_agree_on_every_name(pg_session):
    """The equivalence itself, graded by running both engines over one list.

    Python `re` decides what the card draws; POSIX `~*` decides what the page
    carries. They are the same rule written twice, and a later widening of
    `_GARBAGE_OUTCOME_RE` that forgets this file is exactly how the hole reopens.
    Behavioural rather than textual on purpose — the two dialects are not
    character-identical and never will be.
    """
    from sqlalchemy import text

    from app.routes.futures import _GARBAGE_OUTCOME_SQL, _GARBAGE_OUTCOME_RE

    names = [
        "player A",
        "player AB",
        "player ABC",
        "PLAYER ab",
        "player  AB",
        "player ABCD",
        "players AB",
        "player",
        "Alcaraz",
        "AZ",
        "Player A extra",
        "",
        # ── the cases that actually caught a divergence ──────────────────────
        # The list above is all ASCII-space and no line terminator, so it agrees
        # under a gate that is WRONG: it passed against the trailing-`\n` hole.
        # A `$` is not a `$` — Python's matches at end-of-string OR immediately
        # before ONE trailing newline, POSIX's only at end-of-string — so
        # "player AB\n" was garbage to the formatter (`outcome_count: 0`) and
        # answerable to the gate: the market cleared the predicate and served
        # the blank row this whole file exists to remove. Hence `\n?` in
        # `_GARBAGE_OUTCOME_SQL`, and hence these rows.
        "player AB\n",  # THE HOLE: Python `$` takes it, bare POSIX `$` does not
        "player AB\n\n",  # control: two newlines are garbage to NEITHER engine
        "player AB\nx",  # control: text after the newline, garbage to neither
        "player AB ",  # control: `\n?` must not drift into a whitespace class
        "player AB\r",  # control: CR is not the newline `$` forgives
        "player AB\xa0",  # control: nor is any other space the `$` forgives
        "xplayer AB",  # control: `re.match` anchors at the start, `~*` must too
    ] + [
        # ── THE SECOND HOLE, and the reason the list is generated ────────────
        # An earlier version of this file hand-picked five Unicode spaces, found
        # them equal on the machine it ran on, and wrote "measured equal here"
        # into the route. That claim was true of PostgreSQL 14 at `en_US.UTF-8`
        # and false of CI's server, where `[[:space:]]` does not take NBSP: the
        # name was garbage to the formatter and answerable to the gate, which is
        # the same blank row as the newline hole. On PG 14 the same form failed
        # on `\x85` and `\x1c`, which the hand-picked five did not include.
        #
        # A measurement of a locale-dependent operator over a list somebody chose
        # is not a contract. So: EVERY character Python's `\s` matches, in both
        # letter cases, generated — the gate has to agree on all 29 or say which.
        f"player{space}{initials}"
        for space in (chr(c) for c in range(0x110000) if chr(c).isspace())
        for initials in ("AB", "ab")
    ]

    for name in names:
        in_python = bool(_GARBAGE_OUTCOME_RE.match(name))
        in_postgres = (
            await pg_session.execute(
                text("SELECT :name ~* :pattern"),
                {"name": name, "pattern": _GARBAGE_OUTCOME_SQL},
            )
        ).scalar()
        assert in_python == in_postgres, (
            f"{name!r}: the formatter says garbage={in_python} and the gate says "
            f"garbage={in_postgres} — the card and the page no longer agree"
        )


async def test_the_written_out_space_class_is_exactly_pythons():
    """`_PYTHON_SPACE_CHARS` is hardcoded; this is the scan that keeps it honest.

    The route writes the whitespace class out rather than asking the server for
    `[[:space:]]`, which is what makes the two engines agree independently of the
    database's ctype. The cost of hardcoding is that a Python upgrade adding a
    whitespace character would silently narrow the gate — one character the
    formatter calls garbage and the gate calls answerable, which is the blank row
    again. So the full code-point range is scanned HERE, where 1.1M iterations are
    affordable and an import is not.

    Needs no Postgres: it grades the constant, not the server. That is on purpose
    — this half must fail on a laptop with no database, not only in CI.
    """
    from app.routes.futures import _PYTHON_SPACE_CHARS

    expected = "".join(chr(c) for c in range(0x110000) if chr(c).isspace())

    assert _PYTHON_SPACE_CHARS == expected, (
        "the written-out class has drifted from Python's own `\\s`: missing "
        f"{[hex(ord(c)) for c in expected if c not in _PYTHON_SPACE_CHARS]}, extra "
        f"{[hex(ord(c)) for c in _PYTHON_SPACE_CHARS if c not in expected]}"
    )
    # Ordered by code point and free of the four characters a bracket expression
    # reads as syntax — the two properties that let it be interpolated raw.
    assert list(_PYTHON_SPACE_CHARS) == sorted(_PYTHON_SPACE_CHARS)
    assert not (set(_PYTHON_SPACE_CHARS) & set("]^-\\"))


async def test_the_sql_mirror_asks_the_server_nothing_about_whitespace():
    """The property the fix is, stated where a reader of the diff will see it.

    `[[:space:]]` is decided by the database's ctype, so a predicate built on it
    is a different predicate on a different server — and both of this file's
    whitespace holes were that, not a typo. A reviewer restoring the "simpler"
    POSIX class would pass every other test in this file on their own machine.
    """
    from app.routes.futures import _GARBAGE_OUTCOME_SQL, _PYTHON_SPACE_CHARS

    assert "[:space:]" not in _GARBAGE_OUTCOME_SQL, (
        "the gate must not ask the server what whitespace is — that is the bug"
    )
    assert "[" + _PYTHON_SPACE_CHARS + "]" in _GARBAGE_OUTCOME_SQL
    # The trailing `\n?` mirrors Python's `$` and is NOT part of the class.
    assert _GARBAGE_OUTCOME_SQL.endswith(r"\n?$")
