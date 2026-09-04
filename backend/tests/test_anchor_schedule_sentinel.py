"""The nightly driver that makes the anchor-schedule rail run without being asked. #2853.

The rail itself was already correct and already paged (CERT-828). What was
missing was a caller, and the defect that gap produced is specific: #2804's
wrong kickoff sat on a team page for days because the only thing that could have
seen it ran when a person remembered to run it.

So these guards are about the DRIVER's five ways to be wrong, not about the
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
* **Bounding without continuing (CERT-843).** The one the first presentation got
  wrong. A budget whose every run restarts at the oldest row is not a bound, it
  is a blind spot: the tail is never examined, the front is rescanned nightly,
  and the morning report looks *finished*. Guarded as the two-run reproduction
  the block asked for — run one truncates, run two begins after its cursor, and
  drift planted in the tail is detected only because of it.
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


class _FakeRedis:
    """The three calls the continuation store makes. Bytes on the way out,
    because the real client returns bytes and a `str` stub would hide a decode
    bug that only shows up in production."""

    def __init__(self):
        self.data: dict[str, bytes] = {}
        self.deletes = 0
        # Which keys were written, in order. The two keys cannot be written
        # atomically, so the ORDER is part of the contract (CERT-896).
        self.write_order: list[str] = []

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, ttl, value):
        self.write_order.append(key)
        self.data[key] = value.encode() if isinstance(value, str) else value

    def delete(self, key):
        self.deletes += 1
        self.write_order.append(key)
        self.data.pop(key, None)


class _MarkerWriteFailsRedis(_FakeRedis):
    """Everything works except writing the pass marker (CERT-896).

    Two keys cannot be written atomically and both writes swallow their
    exceptions, so one landing without the other is a state the mechanism has
    to survive. This is the half that matters: the cursor advances and the
    claim does not.
    """

    def __init__(self):
        super().__init__()
        self.fail_pass_writes = False

    def setex(self, key, ttl, value):
        if self.fail_pass_writes and key == sentinel.PASS_STATE_KEY:
            raise RuntimeError("marker write failed")
        super().setex(key, ttl, value)


class _ContinuationWriteFailsRedis(_FakeRedis):
    """The mirror of :class:`_MarkerWriteFailsRedis` — the marker lands and the
    position does not (CERT-898's named follow-up).

    Marker-first ordering makes THIS the likely half, which is exactly why it
    needs its own arm: the store is left holding a claim that names a position
    it does not have. The binding refuses it, so the direction is safe; what it
    costs is the close, and that cost is what this arm pins.
    """

    def __init__(self):
        super().__init__()
        self.fail_cursor_writes = False

    def setex(self, key, ttl, value):
        if self.fail_cursor_writes and key == sentinel.CURSOR_STATE_KEY:
            raise RuntimeError("continuation write failed")
        super().setex(key, ttl, value)


class _BrokenRedis:
    """Every call raises — the outage arm."""

    def get(self, key):
        raise RuntimeError("redis is down")

    def setex(self, key, ttl, value):
        raise RuntimeError("redis is down")

    def delete(self, key):
        raise RuntimeError("redis is down")


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


class TestConsecutiveNightsContinueEachOther:
    """CERT-843. A budget without a continuation is not a bound, it is a blind
    spot: every night restarts at the oldest row, the tail is never examined,
    and the morning report looks finished. These are the guards for that."""

    @pytest.mark.asyncio
    async def test_run_one_truncates_run_two_begins_after_its_cursor(self, monkeypatch):
        """The reproduction the BLOCK asked for, as a guard: two runs sharing one
        store, asserting the SECOND starts where the first stopped."""
        redis = _FakeRedis()

        night_one_cursors: list = []
        await _run_with_stub_session(
            monkeypatch,
            pages=[_page(has_more=True, next_cursor="after-page-1", eligible=999)],
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            seen_cursors=night_one_cursors,
        )
        assert night_one_cursors == [None], "night one starts at the oldest row"

        night_two_cursors: list = []
        await _run_with_stub_session(
            monkeypatch,
            pages=[_page(has_more=False)],
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            seen_cursors=night_two_cursors,
        )
        assert night_two_cursors == [
            "after-page-1"
        ], "night two must resume, not rescan the front slice"

    @pytest.mark.asyncio
    async def test_tail_drift_is_detected_on_the_resumed_run(self, monkeypatch):
        """The point of the whole mechanism: a bad anchor sitting behind night
        one's cutoff is reported on night two. Before the repair it never was.

        The drift lives at a POSITION, not on a call count — the window answers
        clean at the front and dirty past `tail`. So this fails if night two
        rescans the front, which a page-ordered stub could not detect.
        """
        redis = _FakeRedis()

        def window(cursor):
            if cursor is None:  # the front slice: clean, and there is more
                return _page(has_more=True, next_cursor="tail", eligible=999)
            return _page(moves=[_move(4242)], has_more=False, eligible=999)

        first = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=window,
        )
        assert first["moves"] == [], "night one sees only the clean front slice"
        assert first["continuation"] == "tail"

        # Night two is budgeted exactly as tightly as night one — ONE page. That
        # is the whole discrimination: with the continuation it lands on the
        # tail and sees 4242; without it, it spends its single page re-reading
        # the clean front and reports nothing, forever.
        second = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=window,
        )
        assert [m["event_id"] for m in second["moves"]] == [4242]
        assert second["filing"]["red"] is True

    @pytest.mark.asyncio
    async def test_a_finished_sweep_clears_the_continuation(self, monkeypatch):
        """Otherwise every later night resumes from a stale tail and the FRONT of
        the window stops being examined — the same blind spot, mirrored."""
        redis = _FakeRedis()
        redis.setex(sentinel.CURSOR_STATE_KEY, 1, "stale")

        state = await _run_with_stub_session(
            monkeypatch,
            pages=[_page(has_more=False)],
            max_pages=5,
            deadline_seconds=60.0,
            redis=redis,
        )
        assert state["continuation"] is None
        assert sentinel.CURSOR_STATE_KEY not in redis.data
        assert redis.deletes >= 1, "cleared by DELETE, not by writing an empty value"

    @pytest.mark.asyncio
    async def test_a_resumed_run_that_finishes_still_does_not_close(self, monkeypatch):
        """It reached the end of the window having examined only the TAIL.
        Everything before its cursor went unlooked-at tonight, so `complete` must
        stay False and the issue must not be closed."""
        redis = _FakeRedis()
        redis.setex(sentinel.CURSOR_STATE_KEY, 1, "somewhere-in-the-middle")

        state = await _run_with_stub_session(
            monkeypatch,
            pages=[_page(has_more=False)],
            max_pages=5,
            deadline_seconds=60.0,
            redis=redis,
        )
        assert state["resumed_from"] == "somewhere-in-the-middle"
        assert state["complete"] is False
        assert state["filing"] is None, "a tail-only run may not close the issue"

    @pytest.mark.asyncio
    async def test_an_exhausted_cursor_restarts_instead_of_stalling(self, monkeypatch):
        """A saved position points into a MOVING window and can age out entirely.
        A driver that just stopped on the empty page would report `partial`
        having examined nothing, every night, silently — worse than the bug it
        was added to fix."""
        redis = _FakeRedis()
        redis.setex(sentinel.CURSOR_STATE_KEY, 1, "long-past-the-window")
        seen: list = []

        state = await _run_with_stub_session(
            monkeypatch,
            pages=[
                _page(examined=0, has_more=False),  # the cursor is off the end
                _page(examined=5, has_more=False),  # the restart from the front
            ],
            max_pages=5,
            deadline_seconds=60.0,
            redis=redis,
            seen_cursors=seen,
        )
        assert seen == [
            "long-past-the-window",
            None,
        ], "it restarted from the oldest row"
        assert state["restarted_from_exhausted_cursor"] is True
        assert state["examined"] == 5

    @pytest.mark.asyncio
    async def test_a_redis_outage_degrades_to_a_full_restart(self, monkeypatch):
        """Losing the place is survivable; refusing to run is not. A fault must
        leave the rail doing exactly what it did before continuations existed."""
        seen: list = []
        state = await _run_with_stub_session(
            monkeypatch,
            pages=[_page(has_more=False)],
            max_pages=5,
            deadline_seconds=60.0,
            redis=_BrokenRedis(),
            seen_cursors=seen,
        )
        assert seen == [None]
        assert state["measured"] is True
        assert state["complete"] is True


class TestTheWindowPassIsWhatCloses:
    """#2983. The close was gated on ONE unresumed run reaching the end of the
    window, and no such night exists at this population: a fresh run cannot
    cover 685 rows in a 300s deadline (night one measured 600/685,
    ``stopped_by: deadline``), and the night that does reach the end got there
    by resuming. So the sentinel could file and could never close, and #2978
    would have stayed open after every row in it was repaired.

    Coverage was never the defect — nights one and two together see the window.
    Nothing recorded the UNION. These guards are for the thing that now does,
    and they are written in pairs, because a mechanism that closes is only safe
    if the ways it must NOT close are pinned at the same time:

    * a two-night chain closes  ↔  a chain with no marker to continue does not;
    * a fresh pass closes  ↔  a pass older than the bound does not;
    * and the trap this mechanism creates if built naively — night one files
      five drifting rows, night two sweeps a clean tail, and the close resolves
      an issue whose five rows are still wrong.
    """

    @staticmethod
    def _two_page_window():
        """A window that takes exactly two one-page nights to cross."""

        def window(cursor):
            if cursor is None:  # the front slice, and there is more behind it
                return _page(has_more=True, next_cursor="c1", eligible=999)
            return _page(has_more=False, eligible=999)  # the tail ends the window

        return window

    @pytest.mark.asyncio
    async def test_a_two_night_chain_closes_the_issue(self, monkeypatch):
        """THE repair. Night one truncates on its budget; night two resumes and
        reaches the end. Between them the window has been seen, so the pass is
        complete and the clean bill may be filed.

        Under the old `complete = stopped_by is None and not resumed` this fails
        on night two: `resumed` is True, so `complete` is False and nothing is
        ever closed. That is the ablation — the previous guards all pass against
        a sentinel with no close path at all, because every one of them asserts
        a single run's verdict.
        """
        redis = _FakeRedis()

        first = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=self._two_page_window(),
        )
        assert first["complete"] is False, "one night has not seen the window"
        assert first["continuation"] == "c1"
        assert first["filing"] is None

        second = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=self._two_page_window(),
        )
        assert second["resumed_from"] == "c1", "night two must be a RESUMED run"
        assert second["complete"] is True, "the chain saw the window"
        assert second["filing"] is not None and second["filing"]["red"] is False

    @pytest.mark.asyncio
    async def test_a_finished_chain_clears_its_marker_so_the_next_pass_is_fresh(
        self, monkeypatch
    ):
        """Otherwise a stale marker would let a later single tail-only run claim
        a union it was never part of — the close bug, mirrored."""
        redis = _FakeRedis()
        for _ in range(2):
            await _run_with_stub_session(
                monkeypatch,
                max_pages=1,
                deadline_seconds=60.0,
                redis=redis,
                page_for=self._two_page_window(),
            )
        assert sentinel.PASS_STATE_KEY not in redis.data
        assert sentinel.CURSOR_STATE_KEY not in redis.data

    @pytest.mark.asyncio
    async def test_a_resume_with_no_marker_to_continue_cannot_close(self, monkeypatch):
        """The broken-chain arm, and the shape this repair actually ARRIVES in:
        production is carrying a bare cursor written by the old code, with no
        marker beside it. A run resuming onto that has a good position and no
        provenance, so it sweeps and does not close."""
        redis = _FakeRedis()
        redis.setex(sentinel.CURSOR_STATE_KEY, 1, "written-by-the-old-code")

        state = await _run_with_stub_session(
            monkeypatch,
            pages=[_page(has_more=False)],
            max_pages=5,
            deadline_seconds=60.0,
            redis=redis,
        )
        assert state["resumed_from"] == "written-by-the-old-code"
        assert state["pass_open"] is False
        assert state["complete"] is False
        assert state["filing"] is None
        assert "CHAIN-BROKEN" in sentinel._summarize(state)

    @pytest.mark.asyncio
    async def test_drift_on_night_one_is_not_closed_by_a_clean_night_two(
        self, monkeypatch
    ):
        """The trap. Night one finds drift and files it; night two sweeps a
        clean tail and reaches the end. The union has been seen — but five rows
        in it are still wrong, so GREEN is the PASS's verdict, not the last
        run's. Without this the repair would resolve live drift, which is worse
        than the defect it fixes."""
        redis = _FakeRedis()

        def window(cursor):
            if cursor is None:
                return _page(
                    moves=[_move(4242)], has_more=True, next_cursor="c1", eligible=999
                )
            return _page(has_more=False, eligible=999)

        first = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=window,
        )
        assert first["filing"]["red"] is True

        second = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=window,
        )
        assert second["moves"] == [], "night two's own slice is clean"
        assert second["complete"] is True, "and the chain did reach the end"
        assert second["pass_drift_seen"] is True
        assert second["filing"] is None, "but the pass ends RED, so nothing closes"
        assert second["terminal"] == "plan_only"

    @pytest.mark.asyncio
    async def test_a_pass_older_than_the_bound_does_not_close(self, monkeypatch):
        """A close asserts the window is clean NOW. The oldest observation in a
        chain is as old as the pass, so past the bound it is not evidence about
        tonight — rows have been re-anchored since and the floor has moved days
        beyond where the pass began."""
        redis = _FakeRedis()

        await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=self._two_page_window(),
            now=NOW,
        )
        late = NOW + timedelta(seconds=sentinel.MAX_PASS_AGE_SECONDS + 60)
        state = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=self._two_page_window(),
            now=late,
        )
        assert state["resumed_from"] == "c1", "it still resumed — coverage is unharmed"
        assert state["pass_expired"] is True
        assert state["complete"] is False
        assert state["filing"] is None
        assert "PASS-EXPIRED" in sentinel._summarize(state)

    @pytest.mark.asyncio
    async def test_a_pass_inside_the_bound_still_closes(self, monkeypatch):
        """Control for the arm above. Without it, an age bound of zero would
        pass every expiry test while breaking the repair outright."""
        redis = _FakeRedis()
        await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=self._two_page_window(),
            now=NOW,
        )
        state = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=self._two_page_window(),
            now=NOW + timedelta(seconds=sentinel.MAX_PASS_AGE_SECONDS - 60),
        )
        assert state["pass_expired"] is False
        assert state["complete"] is True
        assert state["filing"]["red"] is False

    @pytest.mark.asyncio
    async def test_expiry_costs_the_close_and_never_the_position(self, monkeypatch):
        """The regression this bound could easily cause. If an expired pass also
        cleared the continuation, a window that has outgrown three nights of
        budget would restart at the oldest row every cycle and its tail would
        never be examined at all — CERT-843's blind spot with extra steps. So
        the expired night must still hand its ADVANCED position on."""
        redis = _FakeRedis()
        await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=self._two_page_window(),
            now=NOW,
        )
        state = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=lambda cursor: _page(
                has_more=True, next_cursor="c2", eligible=999
            ),
            now=NOW + timedelta(seconds=sentinel.MAX_PASS_AGE_SECONDS + 60),
        )
        assert state["pass_expired"] is True
        assert state["continuation"] == "c2"
        assert redis.data[sentinel.CURSOR_STATE_KEY] == b"c2", "position advanced"
        assert sentinel.PASS_STATE_KEY not in redis.data, "claim voided"

    @pytest.mark.asyncio
    async def test_a_lost_marker_write_cannot_pair_a_stale_clean_claim_with_an_advanced_cursor(
        self, monkeypatch
    ):
        """CERT-896, the named three-night reproduction.

        The marker and the continuation are two keys and cannot be written
        atomically, and both writes swallow their exceptions. So the pairing
        can come apart in the one direction that is dangerous: the night that
        finds drift advances the cursor, its ``drift_seen: true`` write fails,
        and the store is left holding an ADVANCED position beside a STALE CLEAN
        claim. The next clean tail then reaches the end of the window with
        ``pass_drift_seen`` false — and, before the binding, closed an issue
        whose rows are still wrong.

        Ordering the writes marker-first makes this rarer; only binding the
        marker to the cursor it was written beside makes it detectable.
        """
        redis = _MarkerWriteFailsRedis()

        def window(cursor):
            if cursor is None:
                return _page(has_more=True, next_cursor="c1", eligible=999)
            if cursor == "c1":  # the slice that finds the drift
                return _page(
                    moves=[_move(4242)], has_more=True, next_cursor="c2", eligible=999
                )
            return _page(has_more=False, eligible=999)  # a clean tail

        night_one = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=window,
        )
        assert night_one["continuation"] == "c1"

        redis.fail_pass_writes = True
        night_two = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=window,
        )
        assert night_two["filing"]["red"] is True, "the drift was found and filed"
        assert night_two["continuation"] == "c2"

        # The state the fault leaves behind, asserted directly — without this
        # the test could pass against a store where nothing came apart at all.
        assert redis.data[sentinel.CURSOR_STATE_KEY] == b"c2", "position advanced"
        assert b'"drift_seen": false' in redis.data[sentinel.PASS_STATE_KEY]
        assert b'"cursor": "c1"' in redis.data[sentinel.PASS_STATE_KEY], "claim stale"

        redis.fail_pass_writes = False
        night_three = await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=window,
        )
        assert night_three["moves"] == [], "night three's own slice is clean"
        assert night_three["resumed_from"] == "c2"
        assert night_three["pass_open"] is False, "the claim names c1, the cursor is c2"
        assert night_three["complete"] is False
        assert night_three["filing"] is None, (
            "a lost marker write must never produce a GREEN close — 4242 is "
            "still drifting"
        )

    @pytest.mark.asyncio
    async def test_a_lost_continuation_write_costs_the_close_and_never_the_coverage(
        self, monkeypatch
    ):
        """The OTHER half of the same fault (CERT-898's named follow-up).

        CERT-896 guarded the dangerous direction — the position advances and the
        claim does not. Marker-first ordering makes the MIRROR the likely one:
        the claim lands naming ``c2`` and the position write fails, so the store
        holds ``c1`` beside a marker that says ``c2``. Under the binding that is
        a mismatch, so it reads as a broken chain.

        That is conservative rather than wrong, and this arm says so precisely:
        the fault costs the CLOSE and never the COVERAGE. Night three re-sweeps
        the slice the lost write un-advanced past and re-finds the same drifting
        row — the sweep is read-only and idempotent, so a stale position loses
        nothing. What it loses is the pass, and a later clean tail on the broken
        chain still cannot close.

        **Why this is not "fixed" by resuming ``c1`` as a valid pass.** The two
        divergences are told apart only by ordering the cursors, and the
        ordering has a hole: an exhausted resume restarts the sweep at the
        oldest row mid-run (``restarted_from_exhausted_cursor``), which walks
        the position BACKWARDS. Chain that with a lost marker write on the
        restarting night and a marker that is "ahead" is a stale claim after
        all — drift seen by the restarting night is not in it, and the close
        would be a false GREEN. Strict equality has no such hole. The cost this
        arm pins is the price of that, and it is the right price.
        """
        redis = _ContinuationWriteFailsRedis()

        def window(cursor):
            if cursor is None:
                return _page(has_more=True, next_cursor="c1", eligible=999)
            if cursor == "c1":  # the slice that finds the drift
                return _page(
                    moves=[_move(4242)], has_more=True, next_cursor="c2", eligible=999
                )
            return _page(has_more=False, eligible=999)  # a clean tail

        def night():
            return _run_with_stub_session(
                monkeypatch,
                max_pages=1,
                deadline_seconds=60.0,
                redis=redis,
                page_for=window,
            )

        night_one = await night()
        assert night_one["continuation"] == "c1"

        redis.fail_cursor_writes = True
        night_two = await night()
        assert night_two["filing"]["red"] is True, "the drift was found and filed"
        assert night_two["continuation"] == "c2"

        # The divergence, asserted directly — otherwise this could pass against
        # a store where the two keys never came apart at all.
        assert redis.data[sentinel.CURSOR_STATE_KEY] == b"c1", "position stuck"
        assert b'"drift_seen": true' in redis.data[sentinel.PASS_STATE_KEY]
        assert b'"cursor": "c2"' in redis.data[sentinel.PASS_STATE_KEY], "claim ahead"

        redis.fail_cursor_writes = False
        night_three = await night()
        assert night_three["resumed_from"] == "c1", "the stale position, re-swept"
        assert night_three["pass_open"] is False, "the claim names c2, the cursor is c1"
        assert night_three["complete"] is False
        assert night_three["moves"] != [], (
            "the coverage is NOT lost — the re-swept slice re-finds 4242, which "
            "is what makes the broken chain merely expensive"
        )
        assert night_three["filing"]["red"] is True

        # And the broken chain stays broken: a clean tail arriving on it reaches
        # the end of the window and still cannot close.
        night_four = await night()
        assert night_four["resumed_from"] == "c2"
        assert night_four["reached_window_end"] is True
        assert night_four["pass_open"] is False, "night three cleared the marker"
        assert night_four["complete"] is False
        assert night_four["filing"] is None, (
            "a clean tail on a chain broken by a lost continuation write must "
            "not close either"
        )

    @pytest.mark.asyncio
    async def test_the_claim_is_always_written_before_the_position(self, monkeypatch):
        """Defence in depth for the arm above, and the reason it is rarely
        needed. The binding DETECTS the two keys coming apart; the ordering
        decides which way they come apart when they do. Marker-first leaves a
        claim naming a position the store does not hold — refused on sight.
        Position-first leaves the dangerous pairing the reproduction above is
        about. Asserted rather than described, because a comment about write
        order survives an edit that reverses it."""
        redis = _FakeRedis()
        await _run_with_stub_session(
            monkeypatch,
            max_pages=1,
            deadline_seconds=60.0,
            redis=redis,
            page_for=self._two_page_window(),
        )
        assert redis.write_order.index(
            sentinel.PASS_STATE_KEY
        ) < redis.write_order.index(sentinel.CURSOR_STATE_KEY)

    @pytest.mark.asyncio
    async def test_an_unreadable_marker_is_a_broken_chain_not_a_crash(
        self, monkeypatch
    ):
        """Every marker failure degrades the same way — to "cannot close" —
        without the caller having to reason about which one happened."""
        redis = _FakeRedis()
        redis.setex(sentinel.CURSOR_STATE_KEY, 1, "c1")
        redis.setex(sentinel.PASS_STATE_KEY, 1, "{not json")

        state = await _run_with_stub_session(
            monkeypatch,
            pages=[_page(has_more=False)],
            max_pages=5,
            deadline_seconds=60.0,
            redis=redis,
        )
        assert state["measured"] is True
        assert state["pass_open"] is False
        assert state["filing"] is None


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
    redis: "_FakeRedis | None" = None,
    seen_cursors: list | None = None,
    resume: bool = True,
    page_for=None,
    now: datetime = NOW,
):
    """Drive ``_run_anchor_schedule_sentinel`` with the DB, Redis and GitHub stubbed.

    ``pages`` is consumed in order; once exhausted the last page repeats, which
    is what lets the budget guards run against an endless window.

    Redis is stubbed at the CLIENT, not at ``_load_continuation`` /
    ``_save_continuation`` — so the shipped persistence code is what runs. Pass
    the same ``_FakeRedis`` to two calls to model two consecutive nights.
    """
    import contextlib

    supplied = list(pages or [_page(has_more=True, next_cursor="c", eligible=999)])

    async def fake_reconcile(session, **kwargs):
        if seen_cursors is not None:
            seen_cursors.append(kwargs.get("cursor"))
        if page_for is not None:
            return page_for(kwargs.get("cursor"))
        return supplied.pop(0) if len(supplied) > 1 else supplied[0]

    @contextlib.asynccontextmanager
    async def fake_session():
        yield object()

    def fake_reconcile_issue(**kwargs):
        return dict(kwargs)

    store = redis if redis is not None else _FakeRedis()

    monkeypatch.setattr(sentinel, "reconcile", fake_reconcile)
    monkeypatch.setitem(
        __import__("sys").modules,
        "app.tasks.redis_state",
        type("M", (), {"get_redis_client": staticmethod(lambda: store)}),
    )
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
        now=now,
        resume=resume,
    )
