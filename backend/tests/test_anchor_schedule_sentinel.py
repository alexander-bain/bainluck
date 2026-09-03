"""The nightly driver that makes the anchor-schedule rail run without being asked. #2853.

The rail itself was already correct and already paged (CERT-828). What was
missing was a caller, and the defect that gap produced is specific: #2804's
wrong kickoff sat on a team page for days because the only thing that could have
seen it ran when a person remembered to run it.

So these guards are about the DRIVER's four ways to be wrong, not about the
rail's arithmetic (``test_reconcile_anchor_schedule_paging`` owns that):

* **Writing.** The rail can apply moves. This driver must never reach that path,
  and not by defaulting into safety — by having no way to express it.
* **Calling an unfinished sweep clean.** The worst one, and the reason the
  module exists at all. A run that stopped on its budget knows nothing about the
  rows it never reached; if that closes the issue, the sentinel resolves a live
  defect because it ran out of time. Gotcha #53 one level up from where
  ``reconcile`` already handles it per page.
* **Running forever.** Two different runaway shapes — every page slow (deadline)
  and every page fast (page cap) — so two bounds, and a guard for each.
* **Asking about tennis.** #2852: ESPN answers for no tennis anchor (20/20
  ``no_answer`` measured), so a tennis page terminates ``authority_dark`` — the
  rail's word for an ESPN OUTAGE. A nightly sentinel that cries outage every
  night is one nobody reads. The exclusion is asserted against a real planner,
  not against the kwarg, because a kwarg that never reaches the WHERE clause
  looks identical from the call site.
"""

from __future__ import annotations

import importlib
import inspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.tasks import reconcile_anchor_schedule as rail
from app.utils.anchor_schedule import AUTHORITY_MOVES_US, SCHEDULE_VERDICTS

# NOT `from app.tasks import anchor_schedule_sentinel`: the Celery wrapper in
# `app/tasks/__init__.py` is registered under that exact name and shadows the
# submodule on the package, so the plain form hands back a Task object whose
# attribute lookups go to the task, not the module.
sentinel = importlib.import_module("app.tasks.anchor_schedule_sentinel")

UTC = timezone.utc
NOW = datetime(2026, 9, 13, 17, 0, tzinfo=UTC)


@compiles(JSONB, "sqlite")
def _jsonb_as_json_for_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL only
    return "JSON"


class _AsyncSessionOverSync:
    """A sync Session with the one awaitable the rail uses. Same rig as the
    paging tests: the statement executed is the one the shipped query built."""

    def __init__(self, session: Session):
        self._session = session

    async def execute(self, statement):
        return self._session.execute(statement)


@pytest.fixture
def db():
    from app.models.models import Base, Event, Sport

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[Event.__table__, Sport.__table__])
    with Session(engine) as session:
        session.add(Sport(id=1, key="americanfootball_nfl", name="NFL"))
        session.add(Sport(id=2, key="tennis_atp", name="ATP"))
        session.add(Sport(id=3, key="tennis_wta", name="WTA"))
        session.commit()
        yield session, _AsyncSessionOverSync(session)


def _insert(session, event_id: int, sport_id: int, *, espn_id: str = "401") -> None:
    from app.models.models import Event

    session.add(
        Event(
            id=event_id,
            sport_id=sport_id,
            espn_id=espn_id,
            home_team_name="Home",
            away_team_name="Away",
            commence_time=NOW + timedelta(days=1),
            status="scheduled",
        )
    )
    session.commit()


def _page(
    *,
    examined: int = 1,
    moves: list | None = None,
    has_more: bool = False,
    next_cursor: str | None = None,
    terminal: str = "no_work",
    eligible: int = 1,
):
    """One page as ``reconcile`` returns it."""
    by_verdict = {name: 0 for name in SCHEDULE_VERDICTS}
    by_verdict[AUTHORITY_MOVES_US] = len(moves or [])
    return {
        "measured": True,
        "terminal": terminal,
        "applied": False,
        "eligible": eligible,
        "remaining": eligible,
        "truncated": False,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "examined": examined,
        "by_verdict": by_verdict,
        "moves": moves or [],
    }


def _move(event_id: int = 7):
    return {
        "event_id": event_id,
        "espn_id": "401873124",
        "ours": "2026-09-10T17:00:00+00:00",
        "theirs": "2026-12-17T17:00:00+00:00",
        "delta_days": 98.0,
        "authority": "ESPN",
    }


class TestItCannotWrite:
    """The apply path is not merely defaulted off — it is unreachable."""

    def test_the_driver_exposes_no_apply_parameter(self):
        """A caller cannot ask for a write, so no future caller can pass one
        through by accident. `apply=False` as a default would be one keyword
        away from a data write on a nightly beat."""
        params = inspect.signature(sentinel._run_anchor_schedule_sentinel).parameters
        assert "apply" not in params
        assert "apply" not in inspect.signature(sentinel._sweep).parameters

    @pytest.mark.asyncio
    async def test_every_call_to_the_rail_passes_apply_false(self, monkeypatch):
        """Asserted on what RUNS: capture the kwargs the sweep actually hands the
        rail, over several pages, rather than trusting the source line."""
        seen = []

        async def fake_reconcile(session, **kwargs):
            seen.append(kwargs)
            more = len(seen) < 3
            return _page(
                has_more=more,
                next_cursor=f"c{len(seen)}" if more else None,
            )

        monkeypatch.setattr(sentinel, "reconcile", fake_reconcile)
        await sentinel._sweep(
            object(),
            limit=10,
            sport=None,
            lookback=rail.DEFAULT_LOOKBACK,
            horizon=rail.DEFAULT_HORIZON,
            deadline_seconds=60.0,
            max_pages=10,
        )

        assert len(seen) == 3
        assert all(call["apply"] is False for call in seen)


class TestAnUnfinishedSweepIsNotAnAllClear:
    """The class this module is most likely to get wrong, so it is guarded from
    both directions — a truncated clean run must not close, and a complete clean
    run must."""

    @pytest.mark.asyncio
    async def test_a_budget_truncated_clean_run_neither_files_nor_closes(
        self, monkeypatch
    ):
        """It ran out of pages having seen no drift. It has learned nothing about
        the rest of the window, so it may not resolve the issue."""
        # The stub window always has more to see, so the sweep can only ever
        # stop on its own bound.
        state = await _run_with_stub_session(
            monkeypatch, max_pages=2, deadline_seconds=60.0
        )

        assert state["complete"] is False
        assert state["stopped_by"] == "max_pages"
        assert state["moves"] == []
        assert state["filing"] is None, "a truncated clean sweep must not file OR close"

    @pytest.mark.asyncio
    async def test_a_complete_clean_run_does_close(self, monkeypatch):
        """The control arm. Without this, the test above passes for a sentinel
        that never files anything at all."""
        state = await _run_with_stub_session(
            monkeypatch,
            pages=[_page(has_more=False)],
            max_pages=5,
            deadline_seconds=60.0,
        )
        assert state["complete"] is True
        assert state["filing"] is not None
        assert state["filing"]["red"] is False

    @pytest.mark.asyncio
    async def test_drift_found_before_the_budget_ran_out_is_still_filed(
        self, monkeypatch
    ):
        """A real finding does not become unreal because the sweep stopped after
        it. Truncation gates the GREEN, not the RED."""
        state = await _run_with_stub_session(
            monkeypatch,
            pages=[_page(moves=[_move()], has_more=True, next_cursor="c")],
            max_pages=1,
            deadline_seconds=60.0,
        )
        assert state["complete"] is False
        assert state["filing"]["red"] is True


class TestTheBudgetActuallyBounds:
    @pytest.mark.asyncio
    async def test_the_page_cap_stops_a_window_that_never_ends(self, monkeypatch):
        """The every-page-is-fast runaway: a deadline alone would spend hundreds
        of upstream calls before noticing."""
        state = await _run_with_stub_session(
            monkeypatch, max_pages=4, deadline_seconds=3600.0
        )
        assert state["pages"] == 4
        assert state["stopped_by"] == "max_pages"

    @pytest.mark.asyncio
    async def test_the_deadline_stops_a_window_whose_pages_are_slow(self, monkeypatch):
        """The every-page-is-slow runaway. Time is faked, so the guard does not
        branch on the real clock (gotcha #44)."""
        ticks = iter([0.0] + [100.0 * i for i in range(1, 40)])
        monkeypatch.setattr(sentinel._time, "monotonic", lambda: next(ticks))

        state = await _run_with_stub_session(
            monkeypatch, max_pages=100, deadline_seconds=250.0
        )
        assert state["stopped_by"] == "deadline"
        assert state["pages"] < 100

    @pytest.mark.asyncio
    async def test_two_dark_pages_stop_the_sweep(self, monkeypatch):
        """One dark page can be a bad slice; a second is an outage, and grinding
        on would spend the budget to learn the same thing."""
        state = await _run_with_stub_session(
            monkeypatch,
            pages=[
                _page(terminal="authority_dark", has_more=True, next_cursor="a"),
                _page(terminal="authority_dark", has_more=True, next_cursor="b"),
            ],
            max_pages=50,
            deadline_seconds=600.0,
        )
        assert state["stopped_by"] == "authority_dark"
        assert state["terminal"] == "authority_dark"
        assert state["pages"] == 2

    @pytest.mark.asyncio
    async def test_a_single_dark_page_does_not_stop_the_sweep(self, monkeypatch):
        """Control for the arm above: the recovery path must stay reachable, or
        one flaky slice silently truncates every night."""
        state = await _run_with_stub_session(
            monkeypatch,
            pages=[
                _page(terminal="authority_dark", has_more=True, next_cursor="a"),
                _page(terminal="no_work", has_more=False),
            ],
            max_pages=50,
            deadline_seconds=600.0,
        )
        assert state["stopped_by"] is None
        assert state["complete"] is True
        assert state["pages"] == 2


class TestTennisIsExcludedFromThePopulationItself:
    """#2852. Asserted against a real planner: a kwarg that never reaches the
    WHERE clause is indistinguishable from one that does, at the call site."""

    @pytest.mark.asyncio
    async def test_the_loader_does_not_return_tennis_rows(self, db):
        session, async_session = db
        _insert(session, 1, 1)  # NFL
        _insert(session, 2, 2)  # ATP
        _insert(session, 3, 3)  # WTA

        rows = await rail._load_rows(
            async_session,
            sport=None,
            limit=50,
            lookback=rail.DEFAULT_LOOKBACK,
            horizon=rail.DEFAULT_HORIZON,
            now=NOW,
            exclude_sports=rail.EXCLUDED_SPORT_KEYS,
        )
        assert [row.event_id for row in rows] == [1]

    @pytest.mark.asyncio
    async def test_eligible_excludes_them_too_so_the_census_agrees(self, db):
        """Two definitions of "eligible" is how a census comes to disagree with
        the thing it counts: if only the fetch excluded tennis, every night would
        report examined=1/3 and read as permanently truncated."""
        session, async_session = db
        _insert(session, 1, 1)
        _insert(session, 2, 2)
        _insert(session, 3, 3)

        eligible = await rail._count_eligible(
            async_session,
            sport=None,
            lookback=rail.DEFAULT_LOOKBACK,
            horizon=rail.DEFAULT_HORIZON,
            now=NOW,
            exclude_sports=rail.EXCLUDED_SPORT_KEYS,
        )
        assert eligible == 1

    @pytest.mark.asyncio
    async def test_without_the_exclusion_they_come_back(self, db):
        """The red arm. Without it, both tests above would pass against a
        database that simply had no tennis in it."""
        session, async_session = db
        _insert(session, 1, 1)
        _insert(session, 2, 2)
        _insert(session, 3, 3)

        rows = await rail._load_rows(
            async_session,
            sport=None,
            limit=50,
            lookback=rail.DEFAULT_LOOKBACK,
            horizon=rail.DEFAULT_HORIZON,
            now=NOW,
        )
        assert [row.event_id for row in rows] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_the_driver_passes_the_exclusion_through(self, monkeypatch):
        """And the sweep actually asks for it — the two halves above prove the
        query honours it, this proves the nightly caller requests it."""
        seen = []

        async def fake_reconcile(session, **kwargs):
            seen.append(kwargs)
            return _page(has_more=False)

        monkeypatch.setattr(sentinel, "reconcile", fake_reconcile)
        await sentinel._sweep(
            object(),
            limit=10,
            sport=None,
            lookback=rail.DEFAULT_LOOKBACK,
            horizon=rail.DEFAULT_HORIZON,
            deadline_seconds=60.0,
            max_pages=5,
        )
        assert seen[0]["exclude_sports"] == rail.EXCLUDED_SPORT_KEYS
        assert "tennis_atp" in seen[0]["exclude_sports"]


class TestTheIssueSaysWhatItCannotSee:
    def test_the_body_names_the_blind_spots(self):
        """A sentinel whose silence reads as "the event graph is fine" is worse
        than no sentinel — the id-less and preseason twins are invisible to it."""
        note = sentinel._blind_spots_note()
        assert "#2857" in note and "#2866" in note and "#2852" in note
        assert "espn_id" in note

    def test_the_body_carries_the_dedupe_declaration(self):
        state = {
            "terminal": "plan_only",
            "examined": 10,
            "eligible": 10,
            "pages": 1,
            "moves": [_move()],
            "by_verdict": {name: 0 for name in SCHEDULE_VERDICTS},
            "fingerprint": "anchor-schedule-drift",
        }
        body = sentinel._issue_body(state, now=NOW)
        assert f"{sentinel.MARKER_KEY}:anchor-schedule-drift" in body
        assert "401873124" in body, "the evidence pack must name the drifting anchor"
        assert "Nothing was written" in body


async def _run_with_stub_session(
    monkeypatch,
    *,
    pages: list | None = None,
    max_pages: int,
    deadline_seconds: float,
):
    """Drive ``_run_anchor_schedule_sentinel`` with the DB and GitHub stubbed.

    ``pages`` is consumed in order; once exhausted the last page repeats, which
    is what lets the budget guards run against an endless window.
    """
    import contextlib

    supplied = list(pages or [_page(has_more=True, next_cursor="c", eligible=999)])

    async def fake_reconcile(session, **kwargs):
        return supplied.pop(0) if len(supplied) > 1 else supplied[0]

    @contextlib.asynccontextmanager
    async def fake_session():
        yield object()

    filed = {}

    def fake_reconcile_issue(**kwargs):
        filed.update(kwargs)
        return dict(kwargs)

    monkeypatch.setattr(sentinel, "reconcile", fake_reconcile)
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.tasks.sentinel_filing",
        type("M", (), {"reconcile_issue": staticmethod(fake_reconcile_issue)}),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.tasks.base",
        type("M", (), {"get_task_session": staticmethod(fake_session)}),
    )

    return await sentinel._run_anchor_schedule_sentinel(
        file_issues=True,
        max_pages=max_pages,
        deadline_seconds=deadline_seconds,
        now=NOW,
    )
