"""#7307 — the team-link drain advances, so a binding fix reaches production rows.

WHAT WENT WRONG. ``_backfill_team_links`` is the only writer of
``futures_outcomes.team_id``. Its Phase 2 selector was::

    WHERE team_id IS NULL AND <skip regex> AND <US sports>
    ORDER BY market_id
    LIMIT :limit

with no memory of where the previous run stopped, and there is no attempted
marker on the table. A row that FAILS to bind stays ``team_id IS NULL`` and is
re-selected the next hour, and the hour after that, forever — the queue only
ever drains by *successful* binds. Measured on production 2026-09-19: 1,469,773
rows match that selector and the head of the order is college-basketball
outcomes with no ``teams`` row at all.

WHAT IT COST. PR #7301 fixed a real matching defect under #7188 — a sibling's
bare-city alias made a club's own full name ambiguous, leaving 862 legs bound to
nothing. The lowest ``market_id`` among them is 199,045. The drain never got
past the head, so a correct, fully guard-tested, merged fix bound **nothing**.
Its after-check had to be withdrawn as unpayable.

WHY THESE TESTS ARE SHAPED THIS WAY. The defect is in a SELECT, and a mocked
session cannot select — it can only hand back whatever the test already decided
the answer is. So the corpus is a real database: two markets, a head that can
never bind and a tail that can, and the question each test asks is the
production one — *after the second run, is the tail bound?*

``test_the_head_that_cannot_bind_blocks_the_tail_when_the_cursor_is_severed`` is
the BEFORE. It reproduces the production behaviour by forcing every cursor read
to 0, and it is what makes the AFTER non-vacuous: without it, a corpus small
enough to fit in one batch would pass either way.
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import (  # noqa: E402
    Base,
    FuturesMarket,
    FuturesOutcome,
    Sport,
    Team,
)
from app.tasks import team_linking  # noqa: E402


# --- the sqlite rig ---------------------------------------------------------
#
# Two shims, both narrow and both about the DIALECT, never about the answer:
#
#  * ``~*`` is Postgres' case-insensitive regex operator and sqlite has no such
#    token. ``before_cursor_execute`` rewrites it to sqlite's ``REGEXP``, which
#    is sugar for ``regexp(pattern, value)`` — registered below with the same
#    case-insensitive semantics. The predicate that runs is production's own
#    pattern against production's own column.
#  * ``_AsyncShim`` is the repo's established async surface over a real sync
#    session (see test_futures_categories_unclassified_4047.py); there is no
#    aiosqlite in this sandbox.


def _regexp(pattern, value):  # pragma: no cover - exercised through SQL
    if value is None:
        return False
    return re.search(pattern, value, re.IGNORECASE) is not None


def _make_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _register(dbapi_conn, _record):  # pragma: no cover - connection hook
        dbapi_conn.create_function("regexp", 2, _regexp)

    @event.listens_for(engine, "before_cursor_execute", retval=True)
    def _pg_regex_to_sqlite(conn, cursor, statement, params, context, executemany):
        return statement.replace(" ~* ", " REGEXP "), params

    Base.metadata.create_all(engine)
    return engine


class _AsyncShim:
    """Async surface over a real sync session. The statements are production's."""

    def __init__(self, session: Session):
        self._s = session

    async def execute(self, statement, *args, **kwargs):
        return self._s.execute(statement, *args, **kwargs)

    async def get(self, entity, ident):
        return self._s.get(entity, ident)

    async def commit(self):
        self._s.commit()

    async def rollback(self):
        self._s.rollback()

    async def close(self):
        pass


class _FakeCursorStore:
    """A dict with Redis' three verbs. A store, not an oracle."""

    def __init__(self):
        self.data: dict[str, str] = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, _ttl, value):
        self.data[key] = str(value)

    def delete(self, key):
        self.data.pop(key, None)


# --- the corpus -------------------------------------------------------------

# The head: four college outcomes in the lowest-id market. No `teams` row
# exists for any of them, which is exactly production's head (market_id 3,
# "NCAAB Championship Winner", 102 unbindable rows).
_HEAD_NAMES = ["Fresno St Bulldogs", "UIC Flames", "Wichita St Shockers", "Drake Bulldogs"]

# The tail: the shape of the 862 legs PR #7301 fixed — a club's own full name,
# in a market far up the id order.
_TAIL_NAMES = ["Boston Red Sox", "Chicago Cubs"]


def _seed(session: Session, *, tail_status: str = "open") -> None:
    session.add_all([
        Sport(id=1, key="basketball_ncaab", name="NCAAB", active=True),
        Sport(id=2, key="baseball_mlb", name="MLB", active=True),
    ])
    session.add_all([
        Team(id=101, sport_id=2, name="Boston Red Sox", alternate_names=["Red Sox"]),
        Team(id=102, sport_id=2, name="Chicago Cubs", alternate_names=["Cubs"]),
    ])
    session.add(FuturesMarket(
        id=3, source="kalshi", external_id="head", name="NCAAB Championship Winner",
        category="championship", llm_sport_category="basketball", status="open",
        market_tier=1,
    ))
    session.add(FuturesMarket(
        id=199045, source="kalshi", external_id="tail", name="MLB World Series Champion 2026",
        category="championship", llm_sport_category="baseball", status=tail_status,
        market_tier=1,
    ))
    session.flush()
    oid = 1
    for name in _HEAD_NAMES:
        session.add(FuturesOutcome(id=oid, market_id=3, external_id=f"h{oid}", name=name))
        oid += 1
    for name in _TAIL_NAMES:
        session.add(FuturesOutcome(id=oid, market_id=199045, external_id=f"t{oid}", name=name))
        oid += 1
    session.commit()


def _run_drain(session: Session, store, *, limit: int, runs: int = 1) -> list[dict]:
    """Drive the real task against the real corpus, ``runs`` times."""

    @asynccontextmanager
    async def _fake_task_session():
        yield _AsyncShim(session)

    out = []
    for _ in range(runs):
        out.append(asyncio.run(_drive(_fake_task_session, store, limit)))
    return out


async def _drive(fake_task_session, store, limit):
    import unittest.mock as mock

    with mock.patch.object(team_linking, "get_task_session", fake_task_session), \
            mock.patch.object(team_linking, "_cursor_store", lambda: store):
        return await team_linking._backfill_team_links(limit=limit, use_llm=False)


def _tail_team_ids(session: Session) -> list:
    return list(session.execute(
        select(FuturesOutcome.team_id)
        .where(FuturesOutcome.market_id == 199045)
        .order_by(FuturesOutcome.id)
    ).scalars().all())


# --- BEFORE: the defect, reproduced ----------------------------------------


def test_the_head_that_cannot_bind_blocks_the_tail_when_the_cursor_is_severed():
    """Sever the cursor read and production's behaviour comes back.

    This is the control for every assertion below: it proves the corpus is big
    enough for the head to hide the tail, so an AFTER that finds the tail bound
    can only have got there by advancing.
    """
    import unittest.mock as mock

    engine = _make_engine()
    with Session(engine) as session:
        _seed(session)
        store = _FakeCursorStore()
        with mock.patch.object(team_linking, "_read_cursor", lambda rc, key: 0):
            _run_drain(session, store, limit=4, runs=3)
        assert _tail_team_ids(session) == [None, None], (
            "with the cursor severed the drain must keep re-reading the head; "
            "if the tail bound here the corpus is too small to be a control"
        )


# --- AFTER: the fix ---------------------------------------------------------


def test_a_row_that_fails_to_bind_is_not_re_selected_on_the_next_run():
    engine = _make_engine()
    with Session(engine) as session:
        _seed(session)
        store = _FakeCursorStore()
        first, second = _run_drain(session, store, limit=4, runs=2)

    # Run 1 takes the first three head rows (open budget = limit - floor = 3).
    assert first["selected_open"] == 3
    assert first["cursor_open_start"] == 0
    assert first["outcomes_linked"] == 0, "the head cannot bind — that is the point"
    # Run 2 starts past them, and therefore reaches rows run 1 never saw.
    assert second["cursor_open_start"] == 3
    assert second["outcomes_linked"] == 2, (
        "run 2 must spend its budget on unseen rows, not re-read the three "
        "that failed in run 1"
    )


def test_the_tail_binds_once_the_window_has_moved_off_the_unbindable_head():
    engine = _make_engine()
    with Session(engine) as session:
        _seed(session)
        store = _FakeCursorStore()
        _run_drain(session, store, limit=4, runs=2)
        assert _tail_team_ids(session) == [101, 102]


def test_the_cursor_wraps_when_a_pass_runs_off_the_end():
    """The store starts with a cursor ALREADY SET, or the test cannot see a wrap.

    An empty store is indistinguishable from a cleared one, so a run that never
    writes the key would pass an "is it absent" assertion for the wrong reason.
    """
    engine = _make_engine()
    with Session(engine) as session:
        _seed(session)
        store = _FakeCursorStore()
        store.data[team_linking._CURSOR_KEY_OPEN] = "2"
        # limit 12 -> floor 3 -> open budget 9, above the four rows left after
        # id 2, so the open pass under-fills on its first read.
        first = _run_drain(session, store, limit=12, runs=1)[0]

        assert first["cursor_open_start"] == 2
        assert first["wrapped_open"] is True
        assert team_linking._CURSOR_KEY_OPEN not in store.data, (
            "a wrap must clear the key so the next run re-scans from the head"
        )

        second = _run_drain(session, store, limit=12, runs=1)[0]
        assert second["cursor_open_start"] == 0, "the wrap must actually rewind"


def test_the_resolved_backlog_keeps_its_reserved_share_of_every_batch():
    """The open pass may not take the whole batch while resolved rows wait."""
    engine = _make_engine()
    with Session(engine) as session:
        _seed(session, tail_status="resolved")
        # Four open head rows, two resolved tail rows, batch of 4:
        # open budget is 3, so the resolved pass still gets 1.
        stats = _run_drain(session, store := _FakeCursorStore(), limit=4, runs=1)[0]
        assert stats["selected_open"] == 3
        assert stats["selected_resolved"] == 1
        assert store.data[team_linking._CURSOR_KEY_RESOLVED] == "5"


def test_a_pass_given_no_budget_does_not_rewind_its_cursor():
    """0 rows from a 0-row ask is not the end of the table."""
    engine = _make_engine()
    with Session(engine) as session:
        _seed(session, tail_status="resolved")
        store = _FakeCursorStore()
        store.data[team_linking._CURSOR_KEY_RESOLVED] = "4"
        # limit 1 -> floor 0 -> open budget 1, resolved budget 0.
        stats = _run_drain(session, store, limit=1, runs=1)[0]

    assert stats["selected_resolved"] == 0
    assert "wrapped_resolved" not in stats
    assert store.data[team_linking._CURSOR_KEY_RESOLVED] == "4"
    assert stats["errors"] == [], (
        "a starved pass must be skipped outright — running it for zero rows and "
        "then reading rows[-1] is an IndexError the drain would swallow"
    )


def test_the_cursor_does_not_move_when_the_batch_never_commits():
    """A cursor written before a rollback steps the window past unlinked rows.

    The session here SELECTS normally and fails on the way out, which is what a
    failed commit looks like from inside the task. A rig that blew up before the
    passes ran would leave nothing to write and would assert nothing.
    """
    import unittest.mock as mock

    engine = _make_engine()
    with Session(engine) as session:
        _seed(session)

        @asynccontextmanager
        async def _commit_fails():
            yield _AsyncShim(session)
            raise RuntimeError("commit failed")

        store = _FakeCursorStore()
        with mock.patch.object(team_linking, "get_task_session", _commit_fails), \
                mock.patch.object(team_linking, "_cursor_store", lambda: store):
            stats = asyncio.run(
                team_linking._backfill_team_links(limit=4, use_llm=False)
            )

    assert stats["selected_open"] == 3, "the passes must have run and had rows to bank"
    assert stats["errors"], "the failure must be recorded, not swallowed"
    assert store.data == {}, (
        "a cursor banked before the commit steps the window past rows nothing linked"
    )


def test_the_inherited_scope_filters_still_run_inside_this_rig():
    """The rig's own canary: production's skip list and sport scope really fire.

    The ``~*`` → ``REGEXP`` rewrite is the one place this file could quietly stop
    running production's query. If the shim ever missed, every test above would
    still pass against a *wider* selector and prove nothing about the real one.
    A skipped name and an out-of-scope sport in the corpus make that visible.
    """
    engine = _make_engine()
    with Session(engine) as session:
        session.add_all([
            Sport(id=2, key="baseball_mlb", name="MLB", active=True),
            Sport(id=3, key="soccer_epl", name="EPL", active=True),
        ])
        session.add(Team(id=101, sport_id=2, name="Boston Red Sox", alternate_names=["Red Sox"]))
        session.add_all([
            FuturesMarket(
                id=10, source="kalshi", external_id="mlb", name="MLB World Series Champion 2026",
                category="championship", llm_sport_category="baseball", status="open",
            ),
            FuturesMarket(
                id=11, source="kalshi", external_id="epl", name="EPL Winner",
                category="championship", llm_sport_category="soccer", status="open",
            ),
        ])
        session.flush()
        session.add_all([
            # Matches "^(Yes|No|Over|Under|Draw|Tie|Push)$" and is 4 chars, so
            # only the regex can exclude it.
            FuturesOutcome(id=1, market_id=10, external_id="s", name="Over"),
            FuturesOutcome(id=2, market_id=10, external_id="t", name="Boston Red Sox"),
            # Out of _US_SPORTS.
            FuturesOutcome(id=3, market_id=11, external_id="u", name="Manchester City"),
        ])
        session.commit()

        stats = _run_drain(session, _FakeCursorStore(), limit=8, runs=1)[0]

    assert stats["selected_open"] == 1, (
        f"only 'Boston Red Sox' is in scope; got {stats['selected_open']} — the "
        "skip regex or the sport scope is not being applied by this rig"
    )
    assert stats["outcomes_linked"] == 1


def test_the_window_is_ordered_by_the_same_column_the_cursor_bounds():
    """``WHERE id > :c ORDER BY market_id`` would skip rows and never come back.

    The two are only interchangeable while ids and market_ids happen to rise
    together, which they do in production and in the corpus above — so this
    test builds one where they do not: the bindable market has the LOWER
    outcome ids and the HIGHER market_id.
    """
    engine = _make_engine()
    with Session(engine) as session:
        session.add_all([
            Sport(id=1, key="basketball_ncaab", name="NCAAB", active=True),
            Sport(id=2, key="baseball_mlb", name="MLB", active=True),
        ])
        session.add_all([
            Team(id=101, sport_id=2, name="Boston Red Sox", alternate_names=["Red Sox"]),
            Team(id=102, sport_id=2, name="Chicago Cubs", alternate_names=["Cubs"]),
        ])
        session.add(FuturesMarket(
            id=100, source="kalshi", external_id="late", name="NCAAB Championship Winner",
            category="championship", llm_sport_category="basketball", status="open",
        ))
        session.add(FuturesMarket(
            id=500, source="kalshi", external_id="early", name="MLB World Series Champion 2026",
            category="championship", llm_sport_category="baseball", status="open",
        ))
        session.flush()
        session.add_all([
            FuturesOutcome(id=10, market_id=500, external_id="a", name="Boston Red Sox"),
            FuturesOutcome(id=11, market_id=500, external_id="b", name="Chicago Cubs"),
            FuturesOutcome(id=20, market_id=100, external_id="c", name="UIC Flames"),
            FuturesOutcome(id=21, market_id=100, external_id="d", name="Drake Bulldogs"),
        ])
        session.commit()

        stats = _run_drain(session, _FakeCursorStore(), limit=4, runs=1)[0]

    # Ordered by id the first three rows are 10, 11, 20 — two of them bind.
    # Ordered by market_id they would be 20, 21, 10 — one binds, and the cursor
    # banked (10) then hides 11 behind rows the order has already passed.
    assert stats["outcomes_linked"] == 2


# --- the budget split -------------------------------------------------------


@pytest.mark.parametrize("limit,expected", [(2000, 500), (4, 1), (2, 1), (1, 0), (0, 0)])
def test_resolved_floor(limit, expected):
    assert team_linking._resolved_floor(limit) == expected


def test_an_unreadable_cursor_starts_at_the_head_rather_than_skipping_rows():
    class _Junk:
        def get(self, _key):
            return b"not-a-number"

    assert team_linking._read_cursor(_Junk(), "k") == 0
    assert team_linking._read_cursor(None, "k") == 0
