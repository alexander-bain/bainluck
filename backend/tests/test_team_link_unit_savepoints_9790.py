"""#9790 — one deadlock in the team-link drain costs its own unit, not the batch.

WHAT A READER SAW. The Huskies' page kept listing "Washington D/ST" after #9755
went live (v5300), though its Phase 3c predicate clears all four stored links.
New legs stayed unlinked too, so they never reached a team page.

WHY. ``_backfill_team_links`` is one transaction. Measured 09:50Z 9/30 (task
``1f38f92d``): the hockey category's autoflush hit Postgres ``deadlock
detected``. The category ``except`` swallowed it, basketball, baseball and
Phases 3/3b/3c each raised ``PendingRollbackError``, and the commit threw away
the whole batch. The task still logged ``succeeded … outcomes_linked: 1206``.

THE RIG. The rig is the #7307 sqlite rig, with a session that commits on the way
out and rolls back on an exception, as ``get_task_session`` does. The deadlock is
a driver error raised on the hockey outcome's UPDATE, so SQLAlchemy sees the
same failed flush production saw. The links are read back through a fresh
session, so a test passes only if the rows were committed.
``test_the_pre_9790_handler_loses_the_whole_batch`` is the BEFORE: the same
failure under the old try/except loses basketball too, which proves the AFTER
test can tell the two apart.
"""

from __future__ import annotations

import asyncio
import sqlite3
import unittest.mock as mock
from contextlib import asynccontextmanager

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.tasks import team_linking
from tests.test_team_link_drain_advances_7307 import (
    _AsyncShim,
    _FakeCursorStore,
    _make_engine,
)

BRUINS = 101
CELTICS = 102
HOCKEY_LEG = 1
BASKETBALL_LEG = 2


def _seed(engine) -> None:
    with Session(engine) as s:
        s.add_all([
            Sport(id=1, key="icehockey_nhl", name="NHL", active=True),
            Sport(id=2, key="basketball_nba", name="NBA", active=True),
            Team(id=BRUINS, sport_id=1, name="Boston Bruins", alternate_names=["Bruins"]),
            Team(id=CELTICS, sport_id=2, name="Boston Celtics", alternate_names=["Celtics"]),
            FuturesMarket(
                id=10, source="polymarket", external_id="pm-cup", name="Stanley Cup Champion",
                category="championship", llm_sport_category="hockey", status="open",
                market_tier=1,
            ),
            FuturesMarket(
                id=20, source="polymarket", external_id="pm-nba", name="NBA Champion",
                category="championship", llm_sport_category="basketball", status="open",
                market_tier=1,
            ),
        ])
        s.flush()
        s.add_all([
            FuturesOutcome(id=HOCKEY_LEG, market_id=10, external_id="o1", name="Boston Bruins"),
            FuturesOutcome(id=BASKETBALL_LEG, market_id=20, external_id="o2", name="Boston Celtics"),
        ])
        s.commit()


def _deadlock_on(engine, outcome_id: int) -> None:
    """Fail the UPDATE that writes ``outcome_id``, as Postgres' deadlock detector did."""

    @event.listens_for(engine, "before_cursor_execute")
    def _fail(conn, cursor, statement, params, context, executemany):
        if not statement.lstrip().upper().startswith("UPDATE FUTURES_OUTCOMES"):
            return
        rows = params if executemany else [params]
        if any(outcome_id in tuple(r) for r in rows):
            raise sqlite3.OperationalError("deadlock detected")


def _drain(engine) -> dict:
    session = Session(engine)

    @asynccontextmanager
    async def _task_session():
        try:
            yield _AsyncShim(session)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def _run():
        with mock.patch.object(team_linking, "get_task_session", _task_session), \
                mock.patch.object(team_linking, "_cursor_store", _FakeCursorStore):
            return await team_linking._backfill_team_links(limit=100, use_llm=False)

    return asyncio.run(_run())


def _committed_links(engine) -> dict:
    with Session(engine) as s:
        return dict(s.execute(select(FuturesOutcome.id, FuturesOutcome.team_id)).all())


def test_a_clean_run_links_both_legs():
    engine = _make_engine()
    _seed(engine)
    stats = _drain(engine)
    assert stats["errors"] == []
    assert stats["units_rolled_back"] == []
    assert _committed_links(engine) == {HOCKEY_LEG: BRUINS, BASKETBALL_LEG: CELTICS}


def test_a_deadlock_in_one_category_costs_that_category_only():
    engine = _make_engine()
    _seed(engine)
    _deadlock_on(engine, HOCKEY_LEG)

    stats = _drain(engine)

    assert _committed_links(engine) == {HOCKEY_LEG: None, BASKETBALL_LEG: CELTICS}
    assert stats["units_rolled_back"] == ["Category 'hockey'"]
    assert len(stats["errors"]) == 1 and "deadlock detected" in stats["errors"][0]
    # The counts describe what landed: the rolled-back hockey link is not in them.
    assert stats["outcomes_linked"] == 1
    assert stats["outcomes_linked_by_name"] == 1


def test_the_pre_9790_handler_loses_the_whole_batch():
    """BEFORE: the old per-unit try/except, no savepoint — production's 09:50 shape."""

    @asynccontextmanager
    async def _swallow(session, stats, label):
        try:
            yield
        except Exception as e:
            stats["errors"].append(f"{label}: {str(e)}")

    engine = _make_engine()
    _seed(engine)
    _deadlock_on(engine, HOCKEY_LEG)

    with mock.patch.object(team_linking, "_unit", _swallow):
        stats = _drain(engine)

    assert _committed_links(engine) == {HOCKEY_LEG: None, BASKETBALL_LEG: None}
    assert any(e.startswith("Top-level error") for e in stats["errors"])
    # ...while the result still claims the hockey link it threw away (at 09:50,
    # the 1,206 counted before the failure). Basketball never got to count: its
    # first query raised PendingRollbackError.
    assert stats["outcomes_linked"] == 1
