"""One ambiguous fixture must not discard a whole sport's pass. #4307.

PILLAR: TRUTH. SHIP: an MLB game stops sitting on an uncorrected kickoff time
and a stuck ``live`` badge because the hourly pass that fixes it died before it
committed anything.

THE DEFECT, as it shipped
═════════════════════════
``_sync_statpal_schedules`` resolved a past fixture's row by StatPal id with::

    event = fid_result.scalar_one_or_none()

``scalar_one_or_none()`` **raises** ``MultipleResultsFound`` when two rows come
back, and on 2026-09-09 seven ``statpal_fixture_id`` values in production were
carried by two rows each (NHL 3, MLB 2, NBA 2) — every one a twin. Today's was
MLB ``364906``: events 15300848 (``suspended``) and 15307210 (``completed``),
San Francisco Giants v St. Louis Cardinals, differing by one space in the club
name.

WHY THE RAISE COST THE WHOLE PASS AND NOT ONE FIXTURE
══════════════════════════════════════════════════════
``get_task_session`` (``app/tasks/base.py:59-66``) commits only on a clean exit
and rolls back on any exception, and ``_sync_statpal_schedules`` has no
intermediate commit. So the exception discarded every ``commence_time``
correction, every ``live`` → ``completed`` transition, every ``statpal_end_time``
fill and every score update the pass had already accumulated — and the
playoff-gap live-create block below it never ran at all.

Measured 2026-09-09 ~11:30Z: ``statpal_schedules`` reported ``starts_24h 39``,
``failures_24h 7`` over a 34,419s window with ``last_failure_type
MultipleResultsFound`` at 11:02:00Z — minute :02 is ``sync-statpal-schedules-mlb``
— i.e. ~7 of MLB's ~9.6 passes in that window. Sentry ``BAINLUCK-16X``: 21
events in the 24h buckets, first seen 2026-09-08T01:03:31Z. The task's own
``health`` field read ``healthy`` throughout.

WHAT THESE GUARDS ARE FOR
═════════════════════════
The behavioural half is the one that matters, and it is built so it can FAIL:
the rail's session context mirrors production's commit/rollback exactly, so a
raise anywhere in the pass loses the sibling's write. Without that fidelity the
test would pass on the shipped code (gotcha: a rig that renders nothing on every
arm reads as a clean diff), so ``TestTheRailCanSeeTheDefect`` re-runs the same
scenario through the verbatim shipped resolution and REQUIRES the raise.

The structural half pins the call site, because the defect was one method name
and a future edit could reintroduce it against a fixture that happens to be
unique.
"""

from __future__ import annotations

import ast
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles

from app.tasks.statpal_sync import row_for_statpal_id


# `Event` carries Postgres JSONB/ARRAY columns that sqlite cannot render as DDL.
# The repo's standing shim (see `test_authority_failover_3473`), so this rail can
# create the real tables from the real models.
@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"

SOURCE_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "app/tasks/statpal_sync.py"
)

MLB = "baseball_mlb"

#: The id production carried on two rows on 2026-09-09, and the two event ids.
COLLIDING_FIXTURE_ID = "364906"
#: A second fixture in the same pass, processed AFTER the colliding one. Its
#: write is the thing the raise used to destroy.
SIBLING_FIXTURE_ID = "364999"


# ─────────────────────────────────────────────────────────────────────────────
# The judgement, driven directly
# ─────────────────────────────────────────────────────────────────────────────


class TestThePredicate:
    """``row_for_statpal_id`` — one game, no game, or an ambiguity."""

    def test_one_row_is_the_game(self):
        row = object()
        assert row_for_statpal_id([row]) == (row, False)

    def test_no_rows_is_not_a_collision(self):
        """A past fixture we hold no row for is the ordinary case, not a finding."""
        assert row_for_statpal_id([]) == (None, False)

    def test_two_rows_is_a_collision_and_yields_no_row(self):
        """Both halves matter: it must FLAG, and it must not pick one."""
        first, second = object(), object()
        row, collided = row_for_statpal_id([first, second])
        assert collided is True
        assert row is None, (
            "Returning either row is the `.first()` behaviour this exists to "
            "refuse — the two rows are a twin and which is the game is exactly "
            "what they disagree about (D55)."
        )

    def test_three_rows_is_also_a_collision(self):
        assert row_for_statpal_id([object()] * 3) == (None, True)

    def test_it_accepts_any_sequence(self):
        """SQLAlchemy's `.scalars().all()` is not a list on every version."""
        row = object()
        assert row_for_statpal_id(tuple([row])) == (row, False)


# ─────────────────────────────────────────────────────────────────────────────
# The rail
# ─────────────────────────────────────────────────────────────────────────────


def _wire(monkeypatch, *, faithful_rollback: bool = True):
    """Two MLB rows sharing one StatPal id, plus a clean sibling row.

    The session context mirrors ``get_task_session``: commit on a clean exit,
    **rollback** on an exception. That fidelity is the whole point — a rail that
    commits regardless cannot tell the fix from the defect.

    Returns ``(session, ids)``.
    """
    from sqlalchemy import create_engine
    from sqlalchemy import event as sa_event
    from sqlalchemy.orm import Session

    import app.tasks.base as task_base
    from app.models.models import (
        Base, Event, Sport, Team, TeamIdentityMapping,
    )

    engine = create_engine("sqlite://")
    # `team_identity_service.resolve_team` runs inside the loop, so its two
    # tables are part of the rail even though nothing here asserts on them.
    Base.metadata.create_all(
        engine,
        tables=[
            Event.__table__,
            Sport.__table__,
            Team.__table__,
            TeamIdentityMapping.__table__,
        ],
    )
    session = Session(engine, expire_on_commit=False)

    now = datetime.now(timezone.utc)
    sport = Sport(key=MLB, name="MLB")
    session.add(sport)
    session.flush()

    # The twin: one id, two rows — production's MLB 364906.
    twin_a = Event(
        sport_id=sport.id,
        home_team_name="San Francisco Giants",
        away_team_name="St.Louis Cardinals",
        commence_time=now - timedelta(hours=6),
        status="suspended",
        statpal_fixture_id=COLLIDING_FIXTURE_ID,
    )
    twin_b = Event(
        sport_id=sport.id,
        home_team_name="San Francisco Giants",
        away_team_name="St. Louis Cardinals",
        commence_time=now - timedelta(hours=6),
        status="completed",
        statpal_fixture_id=COLLIDING_FIXTURE_ID,
    )
    # The sibling, processed after the twin, with a kickoff 40 minutes wrong —
    # the correction is what the pass exists to make, and what the raise ate.
    sibling = Event(
        sport_id=sport.id,
        home_team_name="Detroit Tigers",
        away_team_name="Minnesota Twins",
        commence_time=now - timedelta(hours=3),
        status="live",
        statpal_fixture_id=SIBLING_FIXTURE_ID,
    )
    session.add_all([twin_a, twin_b, sibling])
    session.commit()
    ids = {
        "twin_a": twin_a.id,
        "twin_b": twin_b.id,
        "sibling": sibling.id,
        "sport": sport.id,
    }

    @sa_event.listens_for(session, "loaded_as_persistent")
    def _reattach_utc(_sess, instance):  # pragma: no cover - test rail
        for attr, value in list(instance.__dict__.items()):
            if isinstance(value, datetime) and value.tzinfo is None:
                instance.__dict__[attr] = value.replace(tzinfo=timezone.utc)

    class _Ctx:
        async def __aenter__(self_inner):
            return _AsyncShim(session)

        async def __aexit__(self_inner, exc_type, *_):
            if exc_type is not None and faithful_rollback:
                session.rollback()
                return False
            session.commit()
            return False

    monkeypatch.setattr(task_base, "get_task_session", lambda: _Ctx())
    monkeypatch.setattr(
        "app.tasks.statpal_sync.get_task_session", lambda: _Ctx(), raising=False
    )
    return session, ids


class _AsyncShim:
    """A sync Session wearing the async Session's two awaited methods."""

    def __init__(self, session):
        self._s = session

    async def execute(self, *a, **kw):
        return self._s.execute(*a, **kw)

    async def flush(self, *a, **kw):
        return self._s.flush(*a, **kw)

    async def commit(self):
        return self._s.commit()

    async def rollback(self):
        return self._s.rollback()

    def add(self, obj):
        return self._s.add(obj)

    def __getattr__(self, name):
        return getattr(self._s, name)


def _fixtures(now):
    """The two fixtures StatPal serves, colliding one FIRST."""
    from app.services.statpal_api import StatPalFixture

    return [
        StatPalFixture(
            fixture_id=COLLIDING_FIXTURE_ID,
            home_team="San Francisco Giants",
            away_team="St. Louis Cardinals",
            start_time=now - timedelta(hours=6),
            status="finished",
        ),
        StatPalFixture(
            fixture_id=SIBLING_FIXTURE_ID,
            home_team="Detroit Tigers",
            away_team="Minnesota Twins",
            # 40 minutes later than the row holds — a correction, not rounding.
            start_time=now - timedelta(hours=3) + timedelta(minutes=40),
            status="finished",
        ),
    ]


def _stub_service(monkeypatch, now):
    """StatPal serves the two fixtures and no live games."""
    import app.services.statpal_api as statpal_api

    fixtures = _fixtures(now)

    class _Service:
        async def get_fixtures(self, sport):
            return list(fixtures)

        async def get_live_scores(self, sport):
            return []

        async def close(self):
            return None

    monkeypatch.setattr(statpal_api, "is_available", lambda: True)
    monkeypatch.setattr(statpal_api, "StatPalAPIService", lambda *a, **kw: _Service())


# ─────────────────────────────────────────────────────────────────────────────
# The behaviour
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_pass_survives_the_collision_and_the_sibling_is_written(
    monkeypatch,
):
    """The ship: a twin costs its own fixture, and nothing else.

    Three assertions, because the defect could hide behind any one of them:
    it does not raise, it COMMITS (the sibling's correction is on the row after
    the pass returns), and the collision is reported as a count rather than
    absorbed.
    """
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    session, ids = _wire(monkeypatch)
    _stub_service(monkeypatch, now)

    result = await _sync_statpal_schedules(MLB)

    assert result.get("schedule_fid_collision_skipped") == 1, (
        "The ambiguous fixture must be COUNTED, not silently absorbed — a "
        f"refusal nobody measures is a refusal nobody sees. Got: {result}"
    )

    from app.models.models import Event

    # Expunge, not refresh — see the note in the rollback control below.
    session.expunge_all()
    sibling = session.get(Event, ids["sibling"])
    expected = now - timedelta(hours=3) + timedelta(minutes=40)
    assert abs((sibling.commence_time - expected).total_seconds()) < 5, (
        "The sibling's kickoff correction is the work the raise used to throw "
        "away. It must be on the row AFTER the pass returns — which means the "
        f"pass reached it AND committed. Got {sibling.commence_time}."
    )
    assert sibling.commence_time_source == "statpal"


@pytest.mark.asyncio
async def test_neither_twin_is_enriched(monkeypatch):
    """It skips — it does not pick one. Stamping a twin deepens it (D35)."""
    from app.models.models import Event
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    session, ids = _wire(monkeypatch)
    _stub_service(monkeypatch, now)

    before = {
        k: session.get(Event, ids[k]).status for k in ("twin_a", "twin_b")
    }

    await _sync_statpal_schedules(MLB)

    session.expunge_all()
    for k in ("twin_a", "twin_b"):
        row = session.get(Event, ids[k])
        assert row.status == before[k], (
            f"{k} changed status. The pass may not guess which of two rows is "
            "the game — that is the twin's own disagreement (D55, #2693)."
        )


@pytest.mark.asyncio
async def test_a_clean_pass_reports_zero_not_nothing(monkeypatch):
    """0 is a reading. An absent key cannot be told from a guard that never ran."""
    from app.tasks.statpal_sync import _sync_statpal_schedules

    now = datetime.now(timezone.utc)
    session, ids = _wire(monkeypatch)
    _stub_service(monkeypatch, now)

    # Break the collision: give one twin its own id.
    from app.models.models import Event

    twin_b = session.get(Event, ids["twin_b"])
    twin_b.statpal_fixture_id = "364906-b"
    session.commit()

    result = await _sync_statpal_schedules(MLB)

    assert "schedule_fid_collision_skipped" in result, (
        "The key must always be present (gotcha #53: an absence and a zero are "
        "different answers)."
    )
    assert result["schedule_fid_collision_skipped"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# The control — the rail must be able to SEE the defect
# ─────────────────────────────────────────────────────────────────────────────


class TestTheRailCanSeeTheDefect:
    """Re-run the scenario through the shipped resolution; require the raise.

    Without this, a rail whose session committed regardless of the exception —
    or which never reached the colliding fixture at all — would pass on the
    broken code and prove nothing.
    """

    @pytest.mark.asyncio
    async def test_scalar_one_or_none_raises_on_the_production_pair(
        self, monkeypatch
    ):
        from sqlalchemy import select
        from sqlalchemy.exc import MultipleResultsFound

        from app.models.models import Event

        session, _ids = _wire(monkeypatch)

        result = session.execute(
            select(Event).where(
                Event.statpal_fixture_id == COLLIDING_FIXTURE_ID
            )
        )
        with pytest.raises(MultipleResultsFound):
            result.scalar_one_or_none()

    @pytest.mark.asyncio
    async def test_a_raise_mid_pass_loses_the_siblings_write(self, monkeypatch):
        """The cost claim, demonstrated: rollback discards the earlier write.

        This is why the fix is 'do not raise' rather than 'let the task retry'.
        """
        from app.models.models import Event

        session, ids = _wire(monkeypatch)
        import app.tasks.base as task_base

        sibling = session.get(Event, ids["sibling"])
        original = sibling.commence_time

        with pytest.raises(RuntimeError):
            async with task_base.get_task_session() as s:
                row = s.get(Event, ids["sibling"])
                row.commence_time = original + timedelta(minutes=40)
                await s.flush()
                raise RuntimeError("MultipleResultsFound stands in here")

        # Expunge, not expire: a still-persistent instance is refreshed without
        # firing `loaded_as_persistent`, so sqlite's naive datetime comes back
        # unreattached and the comparison below raises instead of asserting.
        session.expunge_all()
        after = session.get(Event, ids["sibling"])
        assert abs((after.commence_time - original).total_seconds()) < 5, (
            "The rollback must discard the pending correction. If this fails "
            "the rail is not faithful to `get_task_session` and every other "
            "assertion in this file is worth less."
        )


# ─────────────────────────────────────────────────────────────────────────────
# The call site
# ─────────────────────────────────────────────────────────────────────────────


class TestTheCallSite:
    """The resolution may not go back to raising inside the loop."""

    def _anchor_lookup_source(self) -> str:
        """Only the `if fixture.fixture_id:` branch that resolves the anchor.

        Scoped to the BRANCH, not the file and not even the whole function. The
        function legitimately holds a SECOND `scalar_one_or_none()` — the
        live-create existence check, whose query carries `.limit(1)` and so can
        never raise. A function-wide ban would red on that safe call, and a
        reviewer would "fix" it by loosening the guard.
        """
        tree = ast.parse(SOURCE_PATH.read_text())
        for fn in ast.walk(tree):
            if not (
                isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef))
                and fn.name == "_sync_statpal_schedules"
            ):
                continue
            for node in ast.walk(fn):
                if not isinstance(node, ast.If):
                    continue
                branch = ast.unparse(node)
                if "Event.statpal_fixture_id == fixture.fixture_id" in branch:
                    return branch
            raise AssertionError(
                "the anchor-resolution branch is gone — if the lookup moved, "
                "move this guard with it rather than deleting it"
            )
        raise AssertionError("_sync_statpal_schedules not found")

    def test_the_anchor_lookup_does_not_call_scalar_one_or_none(self):
        source = self._anchor_lookup_source()
        assert "scalar_one_or_none" not in source, (
            "`scalar_one_or_none()` raises `MultipleResultsFound` on the seven "
            "ids production carries on two rows, and this function has no "
            "intermediate commit — so the raise costs the whole pass (#4307). "
            "Resolve through `row_for_statpal_id`."
        )

    def test_it_resolves_through_the_named_judgement(self):
        source = self._anchor_lookup_source()
        assert "row_for_statpal_id(" in source, (
            "The ambiguity must be resolved by the named helper, so the "
            "judgement stays testable on its own."
        )

    def test_the_safe_sibling_call_is_left_alone(self):
        """The ban is on the UNBOUNDED lookup, not on the method.

        Pins that the guard above is narrow on purpose: the live-create
        existence check still uses `scalar_one_or_none()` and is still correct,
        because its query is `.limit(1)`. If someone widens the ban to the file,
        this fails and says why.
        """
        tree = ast.parse(SOURCE_PATH.read_text())
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
            and n.name == "_sync_statpal_schedules"
        )
        body = ast.unparse(fn)
        assert "existing.scalar_one_or_none()" in body
        assert ".limit(1)" in body

    def test_the_guard_fires_on_the_code_that_shipped(self):
        """A structural guard is only worth having if it reds on the real code.

        The detector is "does this branch text contain the raising call", so the
        control feeds it the branch exactly as production ran it.
        """
        shipped_branch = (
            "if fixture.fixture_id:\n"
            "    fid_result = await session.execute("
            "select(Event).where(Event.statpal_fixture_id == fixture.fixture_id))\n"
            "    event = fid_result.scalar_one_or_none()"
        )
        assert "scalar_one_or_none" in shipped_branch, (
            "the control's own input no longer contains the defect"
        )
        assert "row_for_statpal_id(" not in shipped_branch
