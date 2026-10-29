"""#10090 — the team-link drain holds no outcome row lock while it waits on the LLM.

WHAT A READER SAW. Venue prices froze for a chunk of games. Measured 00:13Z
10/29 (Speed's lock watch): the team-link drain sat ``idle in transaction`` for
145 s, its last statement the category team load (``_load_teams_by_sport``). The
venue price writer's ``futures_outcomes`` lock CTE queued behind it, gave up at
its lock timeout and retried.

WHY. ``_backfill_team_links`` was one transaction. A category's links are ORM
assignments; its savepoint release flushes them as ``UPDATE futures_outcomes``,
and those row locks lasted until the drain committed at the very end — across
every later category's ``llm.classify_player_team_cached``, a synchronous
OpenAI call that also blocks the event loop. Inside one category the same thing
happened sooner: the identity lookup before the LLM step autoflushed the links
already decided.

THE RIG. The #7307 sqlite rig on a FILE database, so a second connection is a
second session. The LLM stub is the slow step. In it, (1) the statements the
drain has run since its last COMMIT must hold no ``UPDATE futures_outcomes``,
and (2) another connection must take the write lock on an outcome row within
500 ms, as the venue writer's ``lock_timeout`` would. sqlite's write lock covers
the whole file, so (2) is stricter than Postgres' row lock: it passes only when
the drain holds no write at all. Both are red on the pre-#10090 code: the hockey
link from the earlier category is flushed and uncommitted when basketball's LLM
call runs.
"""

from __future__ import annotations

import asyncio
import sqlite3
import unittest.mock as mock
from contextlib import asynccontextmanager

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.models import FuturesMarket, FuturesOutcome, Sport, Team
from app.services import llm
from app.tasks import team_linking
from tests.test_team_link_drain_advances_7307 import (
    _AsyncShim,
    _FakeCursorStore,
    _make_engine,
)

BRUINS = 101
CELTICS = 102
HOCKEY_LEG = 1  # "Boston Bruins" — linked by name in the first category
CELTICS_LEG = 2  # "Boston Celtics" — linked by name, same category as the LLM leg
PLAYER_LEG = 3  # "Jaylen Brown" — only the LLM can place him


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
            FuturesMarket(
                id=30, source="polymarket", external_id="pm-mvp", name="NBA MVP",
                category="award", llm_sport_category="basketball", status="open",
                market_tier=2,
            ),
        ])
        s.flush()
        s.add_all([
            FuturesOutcome(id=HOCKEY_LEG, market_id=10, external_id="o1", name="Boston Bruins"),
            FuturesOutcome(id=CELTICS_LEG, market_id=20, external_id="o2", name="Boston Celtics"),
            FuturesOutcome(id=PLAYER_LEG, market_id=30, external_id="o3", name="Jaylen Brown"),
        ])
        s.commit()


def _record_statements(engine) -> list[str]:
    log: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _sql(conn, cursor, statement, params, context, executemany):
        log.append(statement.lstrip().upper())

    @event.listens_for(engine, "commit")
    def _commit(conn):
        log.append("COMMIT")

    @event.listens_for(engine, "rollback")
    def _rollback(conn):
        log.append("ROLLBACK")

    return log


def _uncommitted_outcome_writes(log: list[str]) -> list[str]:
    since = log[max((i for i, s in enumerate(log) if s in ("COMMIT", "ROLLBACK")), default=-1) + 1:]
    return [s for s in since if s.startswith("UPDATE FUTURES_OUTCOMES")]


def _second_session_takes_the_row(path: str) -> str:
    """The venue writer's move: lock an outcome row, give up after 500 ms."""
    conn = sqlite3.connect(path, timeout=0.5, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE futures_outcomes SET name = name WHERE id = ?", (CELTICS_LEG,))
        conn.execute("ROLLBACK")
        return "locked"
    except sqlite3.OperationalError as e:
        return f"refused: {e}"
    finally:
        conn.close()


def _drain(engine, path: str):
    seen: list[dict] = []
    log = _record_statements(engine)
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

    async def _no_identity(*_a, **_k):
        return None

    def _slow_llm(player_name, sport_category=None, market_name=None):
        seen.append({
            "player": player_name,
            "uncommitted_outcome_writes": _uncommitted_outcome_writes(log),
            "second_session": _second_session_takes_the_row(path),
        })
        return "Boston Celtics"

    async def _run():
        with mock.patch.object(team_linking, "get_task_session", _task_session), \
                mock.patch.object(team_linking, "_cursor_store", _FakeCursorStore), \
                mock.patch.object(llm, "is_available", lambda: True), \
                mock.patch.object(llm, "classify_player_team_cached", _slow_llm), \
                mock.patch(
                    "app.services.team_identity.team_identity_service.resolve_team",
                    _no_identity,
                ):
            return await team_linking._backfill_team_links(limit=100, use_llm=True)

    return asyncio.run(_run()), seen


def _committed_links(engine) -> dict:
    with Session(engine) as s:
        return dict(s.execute(select(FuturesOutcome.id, FuturesOutcome.team_id)).all())


def _file_engine(tmp_path):
    path = str(tmp_path / "drain.sqlite")
    return _make_engine(f"sqlite:///{path}"), path


def test_no_outcome_write_is_open_while_the_llm_runs(tmp_path):
    engine, path = _file_engine(tmp_path)
    _seed(engine)

    stats, seen = _drain(engine, path)

    assert [s["player"] for s in seen] == ["Jaylen Brown"]
    assert seen[0]["uncommitted_outcome_writes"] == []


def test_another_session_can_lock_an_outcome_row_during_the_llm_step(tmp_path):
    engine, path = _file_engine(tmp_path)
    _seed(engine)

    stats, seen = _drain(engine, path)

    assert seen[0]["second_session"] == "locked"


def test_the_links_still_land_and_count(tmp_path):
    """Same links, same counts as before #10090 — only when they are written moved."""
    engine, path = _file_engine(tmp_path)
    _seed(engine)

    stats, _ = _drain(engine, path)

    assert stats["errors"] == [] and stats["units_rolled_back"] == []
    assert _committed_links(engine) == {
        HOCKEY_LEG: BRUINS, CELTICS_LEG: CELTICS, PLAYER_LEG: CELTICS,
    }
    assert stats["outcomes_linked"] == 3
    assert stats["outcomes_linked_by_name"] == 2
    assert stats["outcomes_linked_by_llm"] == 1


def test_a_category_that_fails_after_its_llm_step_lands_none_of_its_links(tmp_path):
    """The buffered links go down with their unit, as the flushed ones did (#9790)."""
    engine, path = _file_engine(tmp_path)
    _seed(engine)
    @event.listens_for(engine, "before_cursor_execute")
    def _fail(conn, cursor, statement, params, context, executemany):
        if not statement.lstrip().upper().startswith("UPDATE FUTURES_OUTCOMES"):
            return
        rows = params if executemany else [params]
        if any(PLAYER_LEG in tuple(r) for r in rows):
            raise sqlite3.OperationalError("deadlock detected")

    stats, _ = _drain(engine, path)

    assert _committed_links(engine) == {HOCKEY_LEG: BRUINS, CELTICS_LEG: None, PLAYER_LEG: None}
    assert stats["units_rolled_back"] == ["Category 'basketball'"]
    assert stats["outcomes_linked"] == 1
