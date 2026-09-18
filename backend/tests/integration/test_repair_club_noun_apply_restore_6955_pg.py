"""#6955 — the two club-noun rails' apply, partial compare-and-set and undo,
driven against a real PostgreSQL server.

WHY THIS FILE EXISTS
====================

CERT-3074 granted #6955's Polymarket arm and named this follow-up by name:
*add real-PostgreSQL coverage of apply / partial-CAS / restore*. Both rails
carry ~55 guards apiece and every one of them drives a `_StubSession` — a
hand-written object that answers three statement shapes. A stub can prove the
rail ISSUES the right statement. It cannot prove the statement DOES anything,
because the stub is also the thing deciding what the statement returns.

Four behaviours in the write block are PostgreSQL's, not ours, and a stub
necessarily fakes all four:

1. ``WHERE id = ANY(:ids)`` — array binding. SQLite cannot run it at all.
2. ``llm_sport_category IS NOT DISTINCT FROM :before`` — the compare-and-set,
   whose whole value is its NULL-safe equality. ``= NULL`` is NULL, not false,
   so a rail that used ``=`` would silently never move a row whose stored value
   is NULL, and every stub in the suite would still pass.
3. ``RETURNING id`` — the rail builds its D51 undo from the ids the database
   RETURNED rather than from the ids it planned. That distinction only exists
   when a real server can disagree with the plan.
4. ``SET LOCAL statement_timeout`` — transaction-scoped, and a real timeout
   aborts the whole transaction rather than one statement.

The compare-and-set is not a theoretical guard here. The Kalshi poller runs
every two hours and DOES reach these rows (that is the entire reason the Kalshi
rail exists — #1888's upsert never overwrites a real tag, so the poller sees
the rows and declines to fix them). A concurrent write between this rail's
SELECT and its UPDATE is an ordinary Tuesday, not a thought experiment.

WHAT IT DRIVES
==============

Both rails' own ``repair()``, through a real `AsyncSession`, over rows really
present in a real table — parametrised, so the two rails are held to ONE
contract. They were written a day apart by the same lane and their write blocks
are byte-for-byte the same shape; the thing most likely to go wrong is one of
them drifting. A parametrised file fails on the drift. Two files would not.

Only the venue doors are stubbed. Everything below them — the SELECT, the
membership gate, the cascade, the UPDATE, the commit, the undo — is the shipped
code against the shipped SQL.

THE CONCURRENT WRITER IS REAL
=============================

The partial-CAS case does not simulate a losing row by telling a stub to omit
it. It opens a SECOND engine, and therefore a second connection, and commits a
change to one row from there — in the window between the rail's SELECT and its
UPDATE. Under READ COMMITTED the rail's UPDATE then sees the newer value, the
compare-and-set declines that row, and `RETURNING` hands back only the rows
that really moved. That is the poller, reproduced.

The seam is the venue fetch: every rail reads its rows, then asks the venue,
then writes. Patching the fetch to write on its way past puts the concurrent
commit exactly where production puts it, without reaching inside `repair()`.

THE CONTROL THAT KEEPS THE UNDO HONEST
======================================

`test_the_undo_leaves_the_row_the_compare_and_set_refused_alone` is the one
that matters most, and it is the reason the rails build `restore_sql` from
`applied` rather than from `planned`. After a partial apply the plan names a
row the database never moved. An undo built from the plan would write that
row's STALE `before` value over the concurrent writer's fresher one — turning
the D51 restore, the thing the attended apply is granted on, into a second
defect that silently reverts somebody else's correct write.

So the assertion is not "the undo restored everything". It is "the undo
restored exactly what moved, and left alone the row that did not".
"""

import os

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6955 "
        "apply/partial-CAS/restore gate (CI's search-recall job provides it)"
    ),
)

# Row ids in a private band that encodes the issue number, so a stray row left
# behind by a killed run is identifiable on sight in a database this gate shares
# with ~70 siblings. Well inside the INTEGER ceiling.
KALSHI_CONTAINER = 1069550001
KALSHI_MEMBER = 1069550002
POLYMARKET_CONTAINER = 1069550011
POLYMARKET_MEMBER = 1069550012

ALL_ROW_IDS = [
    KALSHI_CONTAINER,
    KALSHI_MEMBER,
    POLYMARKET_CONTAINER,
    POLYMARKET_MEMBER,
]

#: What both rails must read off the venue and write. Stated once: a rail that
#: started writing something else would pass a test that asked it what it wrote.
AFTER = "weather"
BEFORE = "hockey"

#: What the concurrent writer sets. Deliberately neither BEFORE nor AFTER, so
#: "the CAS refused" and "the CAS fired and wrote the right thing anyway" can
#: never be confused for one another.
CONCURRENT = "politics"


# ---------------------------------------------------------------------------
# The two rails, as one contract.
# ---------------------------------------------------------------------------


class _Rail:
    """One rail's bound, seed and venue doors, behind a shared interface."""

    def __init__(self, name, module_path, bound_attr, bound_value):
        self.name = name
        self.module_path = module_path
        self.bound_attr = bound_attr
        self.bound_value = bound_value

    @property
    def module(self):
        import importlib

        return importlib.import_module(self.module_path)

    def arm(self, monkeypatch, hook):
        """Stub the venue doors and hang `hook` off the event read."""
        raise NotImplementedError

    async def seed(self, conn):
        raise NotImplementedError

    @property
    def ids(self):
        raise NotImplementedError


class _KalshiRail(_Rail):
    def __init__(self):
        super().__init__(
            "kalshi",
            "app.tasks.repair_kalshi_club_noun_category",
            "CLUB_NOUN_EVENT_TICKERS",
            "KXHURCTOT-26DEC01",
        )

    @property
    def ids(self):
        return [KALSHI_CONTAINER, KALSHI_MEMBER]

    async def seed(self, conn):
        """The container row and one market the venue names, both mislabelled.

        Two rows rather than production's one, because a PARTIAL apply needs a
        row that moves beside the row that does not. Both are genuine members:
        the first is the ticker the venue echoes back, the second is in the
        venue's own `markets[]`.
        """
        await conn.execute(
            text(
                "INSERT INTO futures_markets "
                "(id, source, external_id, name, category, mutually_exclusive, "
                " status, llm_sport_category, group_id) VALUES "
                "(:id, 'kalshi', 'KXHURCTOT-26DEC01', "
                " 'How many Atlantic hurricanes will there be in 2026?', "
                " 'weather', false, 'open', :before, 'kalshi:KXHURCTOT-26DEC01')"
            ),
            {"id": KALSHI_CONTAINER, "before": BEFORE},
        )
        await conn.execute(
            text(
                "INSERT INTO futures_markets "
                "(id, source, external_id, name, category, mutually_exclusive, "
                " status, llm_sport_category, group_id) VALUES "
                "(:id, 'kalshi', 'KXHURCTOT-26DEC01-T4', "
                " 'How many Atlantic hurricanes will there be in 2026?', "
                " 'weather', false, 'open', :before, 'kalshi:KXHURCTOT-26DEC01')"
            ),
            {"id": KALSHI_MEMBER, "before": BEFORE},
        )

    def arm(self, monkeypatch, hook):
        rail = self.module

        payload = {
            "event": {
                "event_ticker": "KXHURCTOT-26DEC01",
                "category": "Climate and Weather",
                "series_ticker": "KXHURCTOT",
                "title": "How many Atlantic hurricanes will there be in 2026?",
            },
            "markets": [{"ticker": "KXHURCTOT-26DEC01-T4"}],
        }

        async def fake_event(_client, ticker):
            assert ticker == self.bound_value
            if hook is not None:
                await hook()
            return "ok", payload

        async def fake_series(_client, ticker):
            assert ticker == "KXHURCTOT"
            return "ok", {"series": {"tags": ["Hurricanes", "Natural disasters"]}}

        monkeypatch.setattr(rail, "_fetch_event", fake_event)
        monkeypatch.setattr(rail, "_fetch_series", fake_series)
        monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
        monkeypatch.setattr(rail, self.bound_attr, (self.bound_value,))


class _PolymarketRail(_Rail):
    def __init__(self):
        super().__init__(
            "polymarket",
            "app.tasks.repair_polymarket_club_noun_category",
            "CLUB_NOUN_EVENT_IDS",
            "744619",
        )

    @property
    def ids(self):
        return [POLYMARKET_CONTAINER, POLYMARKET_MEMBER]

    async def seed(self, conn):
        """The container, carrying the event id, and one sub-row that does not.

        The asymmetry is the defect the Polymarket rail navigates and it is
        reproduced here rather than flattened: only the container answers the
        `market_metadata->>'polymarket_event_id'` read, and the sub-row reaches
        the SELECT through `group_id` and the membership gate through its
        question. A real JSONB value, because `->>` is one of the four things
        this file exists to exercise.
        """
        await conn.execute(
            text(
                "INSERT INTO futures_markets "
                "(id, source, external_id, name, category, mutually_exclusive, "
                " status, llm_sport_category, group_id, market_metadata) VALUES "
                "(:id, 'polymarket', 'pm-6955-container', "
                " 'How many hurricanes will form during the Atlantic Hurricane "
                "Season in 2026?', "
                " 'weather', false, 'open', :before, 'polymarket:744619', "
                " '{\"polymarket_event_id\": \"744619\"}'::jsonb)"
            ),
            {"id": POLYMARKET_CONTAINER, "before": BEFORE},
        )
        await conn.execute(
            text(
                "INSERT INTO futures_markets "
                "(id, source, external_id, name, category, mutually_exclusive, "
                " status, llm_sport_category, group_id, market_metadata) VALUES "
                "(:id, 'polymarket', 'pm-6955-member', "
                " 'Will there be 1-3 hurricanes during the Atlantic Hurricane "
                "Season in 2026?', "
                " 'weather', false, 'open', :before, 'polymarket:744619', "
                " '{}'::jsonb)"
            ),
            {"id": POLYMARKET_MEMBER, "before": BEFORE},
        )

    def arm(self, monkeypatch, hook):
        rail = self.module

        payload = {
            "title": (
                "How many hurricanes will form during the Atlantic Hurricane "
                "Season in 2026?"
            ),
            "tags": [
                {"label": "Weather"},
                {"label": "climate"},
                {"label": "hurricane"},
                {"label": "Hurricane Season"},
            ],
            "markets": [
                {
                    "question": (
                        "Will there be 1-3 hurricanes during the Atlantic "
                        "Hurricane Season in 2026?"
                    )
                },
            ],
        }

        async def fake_fetch(_client, event_id):
            assert event_id == self.bound_value
            if hook is not None:
                await hook()
            return "ok", payload

        monkeypatch.setattr(rail, "_fetch_event", fake_fetch)
        monkeypatch.setattr(rail, "VENUE_PAUSE", 0)
        monkeypatch.setattr(rail, self.bound_attr, (self.bound_value,))


RAILS = [_KalshiRail(), _PolymarketRail()]
RAIL_IDS = [r.name for r in RAILS]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _closure(*roots):
    """The tables these rails need, and nothing else.

    Borrowed from the #5621 gate for the same reason it was written there:
    `Base.metadata.create_all()` emits DDL for every model and one unrelated
    table carries `NULLS NOT DISTINCT`, which is PostgreSQL 15+ only. Building
    the whole schema would make this gate's ability to RUN depend on a clause
    no part of it uses, and the failure would read as "the #6955 gate is
    broken" rather than "the server is old".
    """
    seen: dict = {}
    pending = list(roots)
    while pending:
        table = pending.pop()
        if table.key in seen:
            continue
        seen[table.key] = table
        for fk in table.foreign_keys:
            pending.append(fk.column.table)
    return list(seen.values())


@pytest.fixture
async def pg_engine():
    """Function-scoped: `pytest.ini` leaves the fixture loop scope unset."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import FuturesMarket
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, tables=_closure(FuturesMarket.__table__), checkfirst=True
            )
        )
    yield engine
    await engine.dispose()


@pytest.fixture
async def seeded(pg_engine, request):
    """Seed this rail's rows and remove them however the test ends.

    The cleanup is by id and runs in a `finally`, because this database is
    shared with ~70 sibling gates: a happy-path-only teardown leaves rows that
    fail somebody else's census, and a `drop_all` would take their tables with
    it.
    """
    rail = request.param
    async with pg_engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
            {"ids": ALL_ROW_IDS},
        )
        await rail.seed(conn)
    try:
        yield rail
    finally:
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM futures_markets WHERE id = ANY(:ids)"),
                {"ids": ALL_ROW_IDS},
            )


async def _stored(engine, ids):
    """What the table actually holds — the only witness that counts here."""
    async with engine.begin() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, llm_sport_category FROM futures_markets "
                    "WHERE id = ANY(:ids) ORDER BY id"
                ),
                {"ids": ids},
            )
        ).all()
    return {r.id: r.llm_sport_category for r in rows}


async def _drive(engine, rail, monkeypatch, *, apply, hook=None):
    """Run the rail's own `repair()` on a real session."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    rail.arm(monkeypatch, hook)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        return await rail.module.repair(session, apply=apply)


def _concurrent_writer(target_id, value=CONCURRENT):
    """A commit from a genuinely different connection, as the poller makes it.

    A second engine rather than a second checkout of the first, so there is no
    chance of the write sharing the rail's transaction and quietly being part
    of it — which would make the compare-and-set match and the test pass for
    the wrong reason.
    """

    async def hook():
        from sqlalchemy.ext.asyncio import create_async_engine

        other = create_async_engine(DB_URL)
        try:
            async with other.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE futures_markets SET llm_sport_category = :v "
                        "WHERE id = :id"
                    ),
                    {"v": value, "id": target_id},
                )
        finally:
            await other.dispose()

    return hook


def _parametrise(fn):
    return needs_postgres(
        pytest.mark.parametrize("seeded", RAILS, ids=RAIL_IDS, indirect=True)(fn)
    )


# ---------------------------------------------------------------------------
# 1. APPLY
# ---------------------------------------------------------------------------


@_parametrise
async def test_an_apply_really_moves_the_rows_and_returns_the_ids_it_moved(
    pg_engine, seeded, monkeypatch
):
    """THE SHIP, read off the table rather than off the rail's own report.

    Every stub test in both suites asserts what `repair()` SAID. This one
    re-reads `futures_markets` afterwards and asserts what the database now
    HOLDS — the only statement that survives the rail reporting a write it
    never made.
    """
    rail = seeded
    assert await _stored(pg_engine, rail.ids) == dict.fromkeys(rail.ids, BEFORE)

    out = await _drive(pg_engine, rail, monkeypatch, apply=True)

    assert out["counts"]["rows_written"] == len(rail.ids)
    assert sorted(p["id"] for p in out["applied"]) == sorted(rail.ids)
    assert out["terminal"] == "changed"
    assert await _stored(pg_engine, rail.ids) == dict.fromkeys(rail.ids, AFTER)


@_parametrise
async def test_a_dry_run_leaves_every_row_exactly_where_it_was(
    pg_engine, seeded, monkeypatch
):
    """The control without which the apply test proves nothing.

    A rail that wrote on every pass would satisfy the apply case perfectly.
    """
    rail = seeded

    out = await _drive(pg_engine, rail, monkeypatch, apply=False)

    assert out["counts"]["rows_written"] == 0
    assert out["applied"] == []
    assert out["terminal"] == "dry_run"
    assert sorted(p["id"] for p in out["planned"]) == sorted(rail.ids)
    assert await _stored(pg_engine, rail.ids) == dict.fromkeys(rail.ids, BEFORE)


# ---------------------------------------------------------------------------
# 2. PARTIAL COMPARE-AND-SET
# ---------------------------------------------------------------------------


@_parametrise
async def test_a_concurrent_commit_between_the_read_and_the_write_is_refused(
    pg_engine, seeded, monkeypatch
):
    """The poller, reproduced: one row changes under the rail mid-pass.

    The compare-and-set must decline exactly that row and move the other, and
    `rows_written` must report the smaller number — the rail counts what
    `RETURNING` handed back, so a rail that counted the plan instead would
    claim two here and be wrong on the one number an operator reads as proof.
    """
    rail = seeded
    loser, mover = rail.ids

    out = await _drive(
        pg_engine, rail, monkeypatch, apply=True, hook=_concurrent_writer(loser)
    )

    # The plan was made before the concurrent commit, so it still names both.
    assert sorted(p["id"] for p in out["planned"]) == sorted(rail.ids)
    # What actually moved is one row.
    assert out["counts"]["rows_written"] == 1
    assert [p["id"] for p in out["applied"]] == [mover]

    assert await _stored(pg_engine, rail.ids) == {
        loser: CONCURRENT,
        mover: AFTER,
    }


@_parametrise
async def test_the_rail_reports_the_partial_as_a_gap_between_planned_and_applied(
    pg_engine, seeded, monkeypatch
):
    """A partial apply has to be VISIBLE, not smoothed into one number.

    Both rails return `planned` and `applied` side by side for this reason. If
    a later edit ever folded them together an operator would read a clean pass
    and never learn a row was refused.
    """
    rail = seeded
    loser, _mover = rail.ids

    out = await _drive(
        pg_engine, rail, monkeypatch, apply=True, hook=_concurrent_writer(loser)
    )

    planned_ids = {p["id"] for p in out["planned"]}
    applied_ids = {p["id"] for p in out["applied"]}
    assert planned_ids - applied_ids == {loser}


# ---------------------------------------------------------------------------
# 3. THE D51 UNDO, ACTUALLY RUN
# ---------------------------------------------------------------------------


@_parametrise
async def test_the_restore_sql_runs_and_puts_the_moved_rows_back(
    pg_engine, seeded, monkeypatch
):
    """D51 is granted on this string. Until now nothing had executed it.

    `restore_sql` was unit-tested as TEXT — that it names the right ids and
    quotes the right values. Text that looks runnable and is not is exactly the
    failure the Kalshi rail's docstring records a sibling shipping, so the only
    assertion worth making is the one that runs it.
    """
    rail = seeded

    out = await _drive(pg_engine, rail, monkeypatch, apply=True)
    assert await _stored(pg_engine, rail.ids) == dict.fromkeys(rail.ids, AFTER)

    undo = out["restore_sql"]
    assert undo.strip(), "an applied pass must hand back a non-empty undo"

    async with pg_engine.begin() as conn:
        for statement in [s for s in undo.split(";") if s.strip()]:
            await conn.execute(text(statement))

    assert await _stored(pg_engine, rail.ids) == dict.fromkeys(rail.ids, BEFORE)


@_parametrise
async def test_the_undo_leaves_the_row_the_compare_and_set_refused_alone(
    pg_engine, seeded, monkeypatch
):
    """🔴 THE ONE THAT MATTERS: the undo is built from RETURNING, not the plan.

    After a partial apply the PLAN names a row the database never moved. An
    undo built from the plan would write that row's stale `hockey` over the
    concurrent writer's `politics` — reverting somebody else's correct write
    under the banner of a safety feature, and doing it during the one operation
    an operator runs precisely because they believe it is safe.

    So the undo must restore the row that moved and say nothing at all about
    the row that did not.
    """
    rail = seeded
    loser, mover = rail.ids

    out = await _drive(
        pg_engine, rail, monkeypatch, apply=True, hook=_concurrent_writer(loser)
    )

    undo = out["restore_sql"]
    assert str(loser) not in undo, (
        "the undo names the row the compare-and-set refused — it was built "
        "from `planned` rather than from what `RETURNING` handed back, and "
        "running it would revert the concurrent writer"
    )

    async with pg_engine.begin() as conn:
        for statement in [s for s in undo.split(";") if s.strip()]:
            await conn.execute(text(statement))

    assert await _stored(pg_engine, rail.ids) == {
        loser: CONCURRENT,  # untouched, because it never moved
        mover: BEFORE,  # back where it started
    }


# ---------------------------------------------------------------------------
# 4. THE NULL CASE — what `IS NOT DISTINCT FROM` is FOR
# ---------------------------------------------------------------------------


@_parametrise
async def test_a_stored_null_is_moved_because_the_compare_is_null_safe(
    pg_engine, seeded, monkeypatch
):
    """A row with no category at all must still be repaired.

    This is the clause's entire reason for existing and it is invisible to
    every stub in both suites, because a stub comparing in Python gets
    `None == None` right for free. PostgreSQL does not: with `=` the predicate
    would evaluate to NULL, the row would silently not match, and `rows_written`
    would read one lower with no error anywhere. Untagged rows are ordinary —
    the poller writes `llm_sport_category` only when it has a verdict.
    """
    rail = seeded
    null_row, other = rail.ids

    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE futures_markets SET llm_sport_category = NULL "
                "WHERE id = :id"
            ),
            {"id": null_row},
        )

    out = await _drive(pg_engine, rail, monkeypatch, apply=True)

    assert out["counts"]["rows_written"] == 2
    assert await _stored(pg_engine, rail.ids) == {
        null_row: AFTER,
        other: AFTER,
    }

    # And the undo has to put the NULL back as NULL, not as the string 'None'.
    async with pg_engine.begin() as conn:
        for statement in [s for s in out["restore_sql"].split(";") if s.strip()]:
            await conn.execute(text(statement))

    assert await _stored(pg_engine, rail.ids) == {
        null_row: None,
        other: BEFORE,
    }
