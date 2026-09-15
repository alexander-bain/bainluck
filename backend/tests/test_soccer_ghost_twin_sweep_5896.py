"""#5896 — the soccer ghost fold runs on a clock, and its zeros do not share a verdict.

THE SHIP THESE GUARD: a La Liga match that finished on Wednesday stops being
advertised as tonight's 19:00 kick-off. Ten such rows were live on production on
2026-09-13 and the read side that hides them — `not_a_proven_duplicate`, already
on the league, team, search and feed rails — had no writer for this class.

These do NOT pin the judgement; `test_soccer_ghost_twins_5896.py` does that.
They pin the four things around it:

    Part A   the sweep is SCHEDULED, on a cadence that cannot collide with its
             tennis sibling on the two-slot background worker
    Part B   the verdict contract, and specifically the ONE place this task must
             differ from that sibling — soccer ghosts are episodic, so an empty
             plan over a healthy population is GREEN here and RED there
    Part C   the write rail: banked before appended, and a write that silently
             does not land is `partial`, never `complete`
    Part D   the deploy-order guard — no fold, no tags

🔴 Part B is the one with teeth, in both directions. Copying the sibling's plan
floor would make this task red on most days of the year, which teaches everyone
to ignore it; dropping the floor entirely would let a renamed sport key record
GREEN forever while every ghost went untagged. The floor therefore moved onto
the population the sweep READ, and the tests below fail on both mistakes.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tasks import soccer_ghost_twin_sweep as sweep  # noqa: E402
from app.utils.soccer_ghost_twins import GhostPlan, GhostTag  # noqa: E402
from app.utils.task_verdict import ENFORCED_TASKS  # noqa: E402

GHOST_ID = 15298125
CANON_ID = 15298233

#: Offsets, never literal dates: the sweep reads the real clock, so an anchor
#: built from fixed stamps decides its own answer on one day of the year and
#: silently stops exercising the code on every other (gotcha #44).
NOW = datetime.now(timezone.utc)
CANON_AT = NOW - timedelta(hours=26)
GHOST_AT = NOW + timedelta(hours=4)


class _Row:
    """A `load_rows` row — a SQLAlchemy Row, not an ORM object.

    Field names are exactly what the module's SELECT projects, so renaming a
    column in that query breaks these tests. That is the point.
    """

    def __init__(
        self,
        *,
        id,
        sport_key="soccer_spain_la_liga",
        home,
        away,
        at,
        status="scheduled",
        home_score=None,
        away_score=None,
        espn_id=None,
        statpal_fixture_id=None,
        tags=None,
        kalshi_tickers=None,
        market_count=0,
    ):
        self.id = id
        self.sport_key = sport_key
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = at
        self.status = status
        self.home_score = home_score
        self.away_score = away_score
        self.espn_id = espn_id
        self.statpal_fixture_id = statpal_fixture_id
        self.tags_text = tags or "[]"
        #: `string_agg` of this row's Kalshi market tickers, or None when it
        #: holds none — the column `build_plan` turns into the third pass's
        #: `ticker_sport_key`. Named here so dropping it from the SELECT breaks
        #: these tests rather than silently making that pass inert.
        self.kalshi_tickers = kalshi_tickers
        #: How many markets of ANY source hang off this row — the column
        #: `build_plan` turns into the fourth pass's `market_count`. Here for
        #: the same reason as `kalshi_tickers`: drop it from the SELECT and
        #: these tests fail, rather than the stranded pass quietly finding
        #: every played row market-less and every copy market-free.
        self.market_count = market_count


def ghost(**kw):
    """The production specimen's ghost: 15298125, Sevilla v Valencia, tonight.

    Carries no score and no fixture id — but note it is NOT an empty row: the
    real 15298075 holds eleven resolved Polymarket markets, which is why the
    fold has to be live before anything is tagged.
    """
    base = dict(id=GHOST_ID, home="Sevilla", away="Valencia", at=GHOST_AT)
    return _Row(**{**base, **kw})


def canonical(**kw):
    """The row that was actually played: 1-0 on the 11th, ESPN 401882878."""
    base = dict(
        id=CANON_ID,
        home="Sevilla",
        away="Valencia",
        at=CANON_AT,
        status="completed",
        home_score=1,
        away_score=0,
        espn_id="401882878",
        statpal_fixture_id="9544351",
    )
    return _Row(**{**base, **kw})


def _filler(n):
    """`n` inert soccer rows, so a population can clear BOTH read floors.

    The floors are on the READ here, not on the plan, so any test about the
    verdict needs a realistic backdrop of ordinary fixtures or it trips a floor
    instead of testing what it meant to. Names are unique per row so the
    backdrop can never pair with itself and quietly change a plan size.

    Each row also carries its OWN Kalshi event ticker since #6358 added
    `MIN_EXPECTED_TICKER_ROWS`, for two reasons. The floor is real — a backdrop
    of 1,200 rows holding no venue ticker at all is not a population the fifth
    pass can be said to have reached — and the ticker is unique per row, so the
    backdrop lands in 1,200 single-row blocks that are never classified and the
    plan is unchanged. A SHARED ticker here would silently pair the whole
    backdrop into one block.
    """
    return [
        _Row(
            id=900000 + i,
            home=f"Club Aa{i}",
            away=f"Club Bb{i}",
            at=GHOST_AT + timedelta(minutes=i),
            # Digits spelled as letters: the event-ticker grammar this is read
            # under ends `[A-Z]+`, so `…FIL12` is not an event key at all and a
            # backdrop built with one would clear no floor while looking as if
            # it did.
            kalshi_tickers="KXEPLGAME-26SEP12FIL"
            + "".join(chr(ord("A") + int(d)) for d in str(i)),
        )
        for i in range(n)
    ]


def _healthy_backdrop():
    """A backdrop comfortably above whatever the floor currently is.

    Derived from `MIN_EXPECTED_ROWS` rather than the literal 400 these tests
    carried while the floor was 200. The literal was never the point — "clears
    the floor with room" was — and when the window widened to -45d and the floor
    rose with it (both on 2026-09-15), every one of these tests failed on its
    backdrop instead of on its subject. The one test that is ABOUT the floor's
    exact value parametrizes `MIN_EXPECTED_ROWS - 1` directly and is unaffected.
    """
    return _filler(sweep.MIN_EXPECTED_ROWS + 200)


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self._rows = list(rows)
        self.rowcount = rowcount

    def all(self):
        return self._rows


class _Id:
    def __init__(self, id):
        self.id = id


class _FakeSession:
    """Dispatches on the SQL text so the real task body runs end to end.

    Deliberately not a mock of the sweep's helpers: the ordering this has to
    prove — that the backup lands BEFORE the first append — is only observable
    if the real function issues the real statements. `calls` records every
    statement in order for exactly that assertion.
    """

    def __init__(
        self,
        rows,
        *,
        read_raises=False,
        write_fails=False,
        write_silently_noops=False,
    ):
        self.rows = list(rows)
        self.read_raises = read_raises
        self.write_fails = write_fails
        self.write_silently_noops = write_silently_noops
        self.calls: list[str] = []
        self.tagged: set[int] = {
            r.id for r in self.rows if "duplicate-of" in (r.tags_text or "")
        }
        self.banked: list[tuple[int, int, str]] = []

    async def execute(self, clause, params=None):
        sql = " ".join(str(clause).split())
        params = params or {}
        if "FROM events e" in sql:
            self.calls.append("population")
            if self.read_raises:
                raise RuntimeError("connection reset by peer")
            if params.get("cursor", 0):
                return _Result([])
            return _Result(self.rows)
        if sql.startswith("CREATE TABLE IF NOT EXISTS"):
            self.calls.append("create_backup_table")
            return _Result()
        if sql.startswith("INSERT INTO bak_"):
            self.calls.append("bank")
            self.banked.append((params["eid"], params["cid"], params["old"]))
            return _Result(rowcount=1)
        if sql.startswith("UPDATE events"):
            self.calls.append("append_tag")
            if self.write_fails:
                raise RuntimeError("deadlock detected")
            if not self.write_silently_noops:
                self.tagged.add(params["eid"])
            return _Result(rowcount=0 if self.write_silently_noops else 1)
        if sql.startswith("SELECT id FROM events"):
            self.calls.append("verify")
            return _Result([_Id(i) for i in params["ids"] if i in self.tagged])
        raise AssertionError(f"unexpected SQL: {sql[:120]}")

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _run(rows, monkeypatch, *, apply=True, fold_live=True, **kw):
    """Run the real sweep against a fake session; returns (summary, session)."""
    session = _FakeSession(rows, **kw)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.base as base

    monkeypatch.setattr(base, "get_task_session", _fake_session)
    monkeypatch.setattr(sweep, "fold_is_live", lambda: fold_live)
    monkeypatch.setattr(sweep.asyncio, "sleep", _no_sleep)
    summary = asyncio.run(sweep.run_soccer_ghost_twin_sweep(apply=apply))
    return summary, session


async def _no_sleep(_seconds):
    """The retry backoff, without the wall-clock cost."""
    return None


# ════════════════════════════════════════════════════════════════════════════
# Part A — it is actually scheduled, and it cannot collide with its sibling
# ════════════════════════════════════════════════════════════════════════════


class TestTheSweepRunsWithoutAHuman:
    def _schedule(self):
        from app.tasks import celery_app

        return celery_app.conf.beat_schedule

    def test_the_beat_entry_points_at_the_registered_task(self):
        from app.tasks import celery_app

        entry = self._schedule()["soccer-ghost-twin-sweep"]
        assert entry["task"] == "app.tasks.soccer_ghost_twin_sweep"
        assert (
            entry["task"] in celery_app.tasks
        ), "the beat names a task nobody registered — it would fire into the void"

    def test_it_applies_rather_than_dry_running(self):
        """A dry-run schedule measures the defect every half hour and leaves the
        page advertising Wednesday's game. D51 permits the write: reversible
        label, no deleter, prior value banked first."""
        entry = self._schedule()["soccer-ghost-twin-sweep"]
        assert entry["kwargs"]["apply"] is True

    def test_it_runs_on_the_background_worker(self):
        entry = self._schedule()["soccer-ghost-twin-sweep"]
        assert entry["options"]["queue"] == "background"

    def test_its_cadence_never_lands_on_its_tennis_siblings(self):
        """Two label-writing sweeps on a two-slot worker must not contend, and
        the rest of the beat file must not land on this minute either."""
        soccer = self._schedule()["soccer-ghost-twin-sweep"]["schedule"]
        tennis = self._schedule()["tennis-twin-sweep"]["schedule"]

        assert soccer.minute.isdisjoint(tennis.minute)
        for minute in soccer.minute:
            assert minute % 2 == 1, "an odd minute cannot collide with a */2 family"
            assert minute % 5 != 0, "a non-multiple of 5 dodges */5, */10, */15, */30"

    def test_the_window_covers_the_whole_decidable_population(self):
        """The lookback has to reach at least as far back as the widest lag the
        judgement will accept, or the sweep can plan a pair it never read.

        Asserted on the MODULE constants, not on the beat kwargs it used to
        read. The entry pinned `lookback: 5` of its own, which made it a second
        copy of the window and left `DEFAULT_LOOKBACK_DAYS` read by nothing that
        runs (#3813); the entry now passes neither and the task resolves both.
        The assertion is unchanged — only where the effective value lives.
        `test_the_beat_entry_pins_no_window_of_its_own` guards the other half.
        """
        from app.tasks.soccer_ghost_twin_sweep import (
            DEFAULT_LOOKAHEAD_DAYS,
            DEFAULT_LOOKBACK_DAYS,
        )
        from app.utils.soccer_ghost_twins import MAX_GHOST_LAG

        assert DEFAULT_LOOKBACK_DAYS >= MAX_GHOST_LAG.days
        assert DEFAULT_LOOKAHEAD_DAYS >= 1


def test_it_is_enrolled_in_enforced_tasks():
    """From birth (#1884). The failure this guards against is a clean zero, and
    an unenrolled task's terminal is nobody's alarm."""
    assert "soccer_ghost_twin_sweep" in ENFORCED_TASKS


def test_the_task_delegates_the_judgement_to_the_pure_planner(monkeypatch):
    """One implementation of the decision, in the module that has no database."""
    seen = {}

    def _spy(rows, *, now, **kw):
        seen["rows"] = rows
        return GhostPlan(rows_considered=len(rows))

    monkeypatch.setattr(sweep, "plan_ghost_tags", _spy)
    sweep.build_plan([ghost(), canonical()], now=NOW)

    assert len(seen["rows"]) == 2
    assert {r.event_id for r in seen["rows"]} == {GHOST_ID, CANON_ID}


# ════════════════════════════════════════════════════════════════════════════
# Part B — the verdict contract
# ════════════════════════════════════════════════════════════════════════════


class TestTheTwoZerosDoNotShareAVerdict:
    def test_a_quiet_matchday_with_no_ghosts_reads_green(self, monkeypatch):
        """🔴 The difference from the tennis sibling, and the reason this task
        does not inherit its plan floor.

        Measured on production: ten pairs on 2026-09-13, ZERO in the preceding
        thirty days. A plan floor would make the healthy state red on most days
        of the year.
        """
        summary, _ = _run(_healthy_backdrop(), monkeypatch)

        assert summary["terminal"] == "complete"
        assert summary["pairs_found"] == 0
        assert summary["written"] == 0

    def test_a_population_that_collapses_is_failed_not_complete(self, monkeypatch):
        """The same zero, for the opposite reason: a renamed sport key or a
        broken join leaves a handful of rows and decides nothing. Without this
        the task would record GREEN forever while every ghost stayed visible."""
        summary, _ = _run(_filler(5), monkeypatch)

        assert summary["terminal"] == "failed"
        assert summary["written"] == 0
        assert "below the floor" in summary["reason"]

    def test_the_floor_is_not_waived_by_having_found_a_pair(self, monkeypatch):
        """A thin window that happens to contain one decidable pair is still a
        thin window. `untagged` earns no veto over the band — that waiver is the
        hole CERT-2193 found in the sibling."""
        summary, session = _run([ghost(), canonical(), *_filler(5)], monkeypatch)

        assert summary["terminal"] == "failed"
        assert summary["written"] == 0
        assert "append_tag" not in session.calls

    def test_a_plan_above_the_ceiling_is_refused(self, monkeypatch):
        """A pairing regression labels far more rows than anyone has measured,
        and a sweep never gets to ratify its own surprise."""
        rows = _healthy_backdrop()
        for i in range(sweep.MAX_EXPECTED_TAGS + 1):
            rows.append(_Row(id=800000 + i, home=f"Cc{i}", away=f"Dd{i}", at=GHOST_AT))
            rows.append(
                _Row(
                    id=810000 + i,
                    home=f"Cc{i}",
                    away=f"Dd{i}",
                    at=CANON_AT,
                    status="completed",
                    home_score=1,
                    away_score=0,
                    espn_id=str(810000 + i),
                )
            )

        summary, session = _run(rows, monkeypatch)

        assert summary["terminal"] == "failed"
        assert "above the ceiling" in summary["reason"]
        assert "append_tag" not in session.calls

    def test_a_read_that_raises_is_failed_and_unmeasured(self, monkeypatch):
        """ "I could not look" is not "there was nothing to do" (gotcha #53)."""
        summary, _ = _run(_healthy_backdrop(), monkeypatch, read_raises=True)

        assert summary["terminal"] == "failed"
        assert summary["measured"] is False

    def test_an_empty_window_is_no_work_not_complete(self, monkeypatch):
        summary, _ = _run([], monkeypatch)

        assert summary["terminal"] == "no_work"
        assert summary["rows_read"] == 0

    def test_a_dry_run_withholds_and_says_so(self, monkeypatch):
        summary, session = _run(
            [ghost(), canonical(), *_healthy_backdrop()], monkeypatch, apply=False
        )

        assert summary["terminal"] == "no_work"
        assert summary["tags_to_write"] == 1
        assert "append_tag" not in session.calls

    def test_an_already_labelled_ghost_is_left_alone(self, monkeypatch):
        """The idempotent re-run — ninety-six times a day once a matchday's
        ghosts are tagged. It writes nothing and it is GREEN."""
        rows = [
            ghost(tags=f'["provenance:duplicate-of:{CANON_ID}"]'),
            canonical(),
            *_healthy_backdrop(),
        ]

        summary, session = _run(rows, monkeypatch)

        assert summary["terminal"] == "complete"
        assert summary["written"] == 0
        assert summary["already_tagged"] == 1
        assert "append_tag" not in session.calls


# ════════════════════════════════════════════════════════════════════════════
# Part C — the write rail
# ════════════════════════════════════════════════════════════════════════════


class TestTheWriteRail:
    def test_the_specimen_is_tagged_on_a_healthy_population(self, monkeypatch):
        summary, session = _run(
            [ghost(), canonical(), *_healthy_backdrop()], monkeypatch
        )

        assert summary["terminal"] == "complete"
        assert summary["written"] == 1
        assert GHOST_ID in session.tagged
        assert CANON_ID not in session.tagged, "the played row must keep printing"

    def test_the_backup_is_banked_before_the_first_append(self, monkeypatch):
        """D51: the undo must exist before the change does. Asserted on the
        real statement order, not on a helper being called."""
        _, session = _run([ghost(), canonical(), *_healthy_backdrop()], monkeypatch)

        assert session.calls.index("bank") < session.calls.index("append_tag")
        assert session.banked == [(GHOST_ID, CANON_ID, "[]")]

    def test_a_write_that_silently_does_not_land_is_partial(self, monkeypatch):
        """`rowcount` 0 means either "already tagged" or "did not land", and only
        a read back tells them apart (gotcha #53)."""
        summary, _ = _run(
            [ghost(), canonical(), *_healthy_backdrop()],
            monkeypatch,
            write_silently_noops=True,
        )

        assert summary["terminal"] == "partial"
        assert summary["still_untagged"] == [GHOST_ID]

    def test_a_write_that_raises_is_partial_and_names_the_row(self, monkeypatch):
        summary, _ = _run(
            [ghost(), canonical(), *_healthy_backdrop()], monkeypatch, write_fails=True
        )

        assert summary["terminal"] == "partial"
        assert summary["failed_ids"] == [GHOST_ID]

    def test_the_summary_carries_the_one_command_undo(self, monkeypatch):
        summary, _ = _run([ghost(), canonical(), *_healthy_backdrop()], monkeypatch)

        assert "restore_5896_soccer_ghost_tags.py --apply" in summary["undo"]

    def test_the_summary_reports_the_second_pass_on_its_own_numbers(self):
        """#5896/#3813: the two passes reach different populations, so a single
        total cannot say which of them stopped reaching its own.

        Gwangju: the narrow key sees two blocks of one ("Gwangju" against
        "Gwangju FC") and decides nothing; the second pass decides it. If these
        two counters are ever folded into `blocks_examined`/`pairs_found`, the
        first pass could go silently blind behind the second's numbers.
        """
        rows = [
            _Row(
                id=15307681,
                sport_key="soccer_other",
                home="Gwangju",
                away="FC Anyang",
                at=GHOST_AT,
                status="suspended",
            ),
            _Row(
                id=15306857,
                sport_key="soccer_korea_kleague1",
                home="Gwangju FC",
                away="FC Anyang",
                at=CANON_AT,
                status="completed",
                home_score=1,
                away_score=1,
                statpal_fixture_id="9540001",
            ),
            *_healthy_backdrop(),
        ]

        plan = sweep.build_plan(rows, now=NOW)

        assert plan.blocks_examined == 0, "the narrow key must not see this pair"
        assert plan.residual_blocks_examined == 1
        assert plan.residual_tags == 1
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (15307681, 15306857)
        ]

    def test_the_third_pass_reads_the_tickers_the_query_projects(self):
        """#5896/#3813 — Mallorca v Sabadell, the stranded specimen, end to end.

        The la_liga row's own markets are `KXLALIGA2` contracts, which is
        Kalshi's name for the Segunda; the canonical is the played Segunda row.
        Two block coordinates differ at once, so nothing but the third pass
        reaches them. This goes through `build_plan` rather than the planner so
        the column → `ticker_sport_key` wiring is what is being asserted: drop
        `kalshi_tickers` from the SELECT and this is the test that fails.
        """
        rows = [
            _Row(
                id=15308726,
                sport_key="soccer_spain_la_liga",
                home="Mallorca",
                away="Sabadell",
                at=GHOST_AT,
                status="suspended",
                kalshi_tickers="KXLALIGA2GAME-26SEP13MALSAB",
            ),
            _Row(
                id=15306010,
                sport_key="soccer_spain_segunda_division",
                home="Mallorca",
                away="Sabadell FC",
                at=CANON_AT,
                status="completed",
                home_score=2,
                away_score=0,
                statpal_fixture_id="9545042",
            ),
            *_healthy_backdrop(),
        ]

        plan = sweep.build_plan(rows, now=NOW)

        assert plan.blocks_examined == 0, "the narrow key must not see this pair"
        assert plan.residual_blocks_examined == 0, "nor may the loose-name key"
        assert plan.ticker_blocks_examined == 1
        assert plan.ticker_tags == 1
        assert [(t.ghost_id, t.canonical_id) for t in plan.tags] == [
            (15308726, 15306010)
        ]

    def test_a_row_with_no_kalshi_markets_reads_as_no_opinion(self):
        """The aggregate is NULL for a row holding none, and `None.split` raises.

        Most of the window is this row, so a crash here is the whole sweep.
        """
        plan = sweep.build_plan([ghost(), canonical(), *_healthy_backdrop()], now=NOW)

        assert plan.ticker_tags == 0
        assert [t.ghost_id for t in plan.tags] == [GHOST_ID]

    def test_the_undo_reads_the_table_the_sweep_banks_into(self):
        """One constant, imported, not two strings that agree today."""
        import scripts.restore_5896_soccer_ghost_tags as undo

        assert undo.BAK_TABLE is sweep.BAK_TABLE
        assert (
            undo.BAK_TABLE != "bak_2878_twin_ghost_tags"
        ), "sharing the tennis sweep's table would make the two undos inseparable"


# ════════════════════════════════════════════════════════════════════════════
# Part D — the deploy-order guard
# ════════════════════════════════════════════════════════════════════════════


class TestNoFoldNoTags:
    def test_the_fold_is_live_today(self):
        """`_build_game_markets` calls `folded_event_ids`. If this ever fails,
        the read side has been unwired and this sweep must stop writing."""
        assert sweep.fold_is_live() is True

    def test_it_detects_the_fold_being_unwired(self, monkeypatch):
        import app.routes.events as events

        def _no_fold(*a, **kw):  # pragma: no cover - never called
            return None

        monkeypatch.setattr(events, "_build_game_markets", _no_fold)
        assert sweep.fold_is_live() is False

    def test_tags_are_withheld_loudly_when_the_fold_is_gone(self, monkeypatch):
        """A ghost is not an empty row — 15298075 carries eleven resolved
        markets. Tagging without the fold moves those out of reach instead of
        removing a duplicate card, so the run fails rather than reporting a
        clean small write."""
        summary, session = _run(
            [ghost(), canonical(), *_healthy_backdrop()], monkeypatch, fold_live=False
        )

        assert summary["terminal"] == "failed"
        assert summary["written"] == 0
        assert "append_tag" not in session.calls
        assert "folded_event_ids" in summary["reason"]

    def test_a_quiet_day_is_still_green_without_the_fold(self, monkeypatch):
        """The gate is on the WRITE, not on the run: with nothing to tag there
        is nothing the missing fold can damage."""
        summary, _ = _run(_healthy_backdrop(), monkeypatch, fold_live=False)

        assert summary["terminal"] == "complete"


# ════════════════════════════════════════════════════════════════════════════
# The band, read directly
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "soccer_rows,ticker_rows,tags,expected_substring",
    [
        (sweep.MIN_EXPECTED_ROWS - 1, sweep.MIN_EXPECTED_TICKER_ROWS, 0, "soccer row"),
        (
            sweep.MIN_EXPECTED_ROWS,
            sweep.MIN_EXPECTED_TICKER_ROWS - 1,
            0,
            "event ticker",
        ),
        (sweep.MIN_EXPECTED_ROWS, sweep.MIN_EXPECTED_TICKER_ROWS, 0, None),
        (
            sweep.MIN_EXPECTED_ROWS,
            sweep.MIN_EXPECTED_TICKER_ROWS,
            sweep.MAX_EXPECTED_TAGS,
            None,
        ),
        (
            sweep.MIN_EXPECTED_ROWS,
            sweep.MIN_EXPECTED_TICKER_ROWS,
            sweep.MAX_EXPECTED_TAGS + 1,
            "above the ceiling",
        ),
    ],
)
def test_the_band_boundaries(soccer_rows, ticker_rows, tags, expected_substring):
    """Both floors, each at its own boundary and each with the OTHER one healthy.

    Parametrized as two independent rows rather than one combined "read" number,
    because that is the property #6358 needs: the soccer join and the Kalshi
    ticker rail die separately, and a floor that only fires when BOTH collapse
    would pass every single-sided failure it exists to catch.
    """
    plan = GhostPlan(
        tags=[
            GhostTag(ghost_id=i, canonical_id=i + 1, reason="x") for i in range(tags)
        ],
        rows_considered=soccer_rows + ticker_rows,
        soccer_rows_considered=soccer_rows,
        ticker_rows_considered=ticker_rows,
    )

    reason = sweep.band_refusal_reason(plan)

    if expected_substring is None:
        assert reason is None
    else:
        assert reason is not None and expected_substring in reason
