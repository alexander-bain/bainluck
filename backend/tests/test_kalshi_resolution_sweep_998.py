"""CAL-P998 / D47 — the Kalshi resolution-window sweep stops being attended (#2771).

#2771 shipped the predicate and left one acceptance line open:

    > **The sweep is scheduled, not attended.** The population refills daily; a
    > one-off cannot hold it. That half is NOT in this branch.

Measured on production while this queue ran: **5,143** sealed rows at
2026-09-03 05:00Z and **5,137** at 22:0xZ — a repair that exists, is correct,
and is not running. Every one of those rows renders a dead last-trade price as
a live probability the moment Kalshi finalizes it, and nothing else in the
system can correct it: the open-market poll never re-enumerates a finalized
market (gotcha #33).

The reason it could not be scheduled is mechanical and it is the first thing
pinned here: the repair lived in ``scripts/``, and a Celery task cannot import
from ``scripts/`` — it is not on the dyno's path. So this file guards the move
AND the wiring AND the terminal, because any one of them missing leaves a beat
that is scheduled and inert, which is worse than none: it looks like the fix.

The 19 pre-existing guards in ``test_kalshi_resolution_backfill_script_989.py``
are the control for the move. They drive the module's real ``SELECT_SQL`` and
``run_backfill`` through the script's name and must stay green — if they red,
the move changed the repair rather than relocating it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.tasks import kalshi_resolution_sweep as sweep
from app.utils import task_verdict

NOW = datetime(2026, 9, 3, 22, 0, tzinfo=timezone.utc)

BEAT_ENTRY = "sweep-kalshi-resolution-window"
TASK_NAME = "app.tasks.sweep_kalshi_resolution_window"
#: The label `_tracked_run` records under, and the key `ENFORCED_TASKS` matches.
TRACKED_LABEL = "kalshi_resolution_window"


# ---------------------------------------------------------------------------
# 1. The move — why the beat was impossible before it
# ---------------------------------------------------------------------------


class TestTheRepairIsReachableFromATask:
    def test_the_sweep_lives_under_app_not_under_scripts(self):
        """The mechanical fact the whole item turns on.

        `scripts/` is not on the dyno's path, so while the predicate lived there
        the ONLY way to run this repair was for a human to run it — and the
        sealed-row count says nobody did.
        """
        here = Path(sweep.__file__).resolve()
        assert here.parent.name == "tasks"
        assert here.parents[1].name == "app"

    def test_the_module_imports_nothing_from_scripts(self):
        """A task that reaches back into `scripts/` boots fine locally and
        ImportErrors on the dyno, which is the worst possible place to find out."""
        src = Path(sweep.__file__).read_text()
        offenders = [
            ln for ln in src.splitlines()
            if ln.startswith(("import scripts", "from scripts"))
        ]
        assert offenders == []

    def test_the_cli_and_the_beat_run_the_same_sql(self):
        """Identity, not equality.

        Two copies of `SELECT_SQL` that read the same today are precisely the
        state this move removes: an attended run and a nightly beat scoring
        different rows, with nothing to notice it.
        """
        import scripts.backfill_kalshi_resolution_window as cli

        assert cli.SELECT_SQL is sweep.SELECT_SQL
        assert cli.COUNT_SQL is sweep.COUNT_SQL
        assert cli.UPDATE_SQL is sweep.UPDATE_SQL
        assert cli.run_backfill is sweep.run_backfill

    def test_the_predicate_still_selects_on_provenance(self):
        """CONTROL — green before this queue and after it. The move must not
        have touched what CAL-P992 ratified."""
        assert "resolution_date >= expiration_time" in sweep.SELECT_SQL
        assert "ORDER BY updated_at ASC" in sweep.SELECT_SQL


# ---------------------------------------------------------------------------
# 2. The wiring
# ---------------------------------------------------------------------------


class TestTheBeat:
    def test_the_task_is_registered_under_its_name(self):
        from app.tasks import celery_app

        assert TASK_NAME in celery_app.tasks

    def test_the_beat_entry_exists_and_points_at_it(self):
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule[BEAT_ENTRY]
        assert entry["task"] == TASK_NAME

    def test_the_beat_runs_daily_not_once(self):
        """The whole point of D47's half: the population REFILLS. A one-off
        cannot hold it, so a schedule that fires once would be the same defect
        wearing a beat entry."""
        from app.tasks import celery_app

        schedule = celery_app.conf.beat_schedule[BEAT_ENTRY]["schedule"]
        assert getattr(schedule, "hour", None), "not a crontab — a daily beat is required"
        # A crontab whose day/month fields are pinned would fire once a year.
        assert schedule.day_of_month == set(range(1, 32))
        assert schedule.month_of_year == set(range(1, 13))

    def test_it_does_not_overlap_the_other_kalshi_venue_sweep(self):
        """Two concurrent venue sweeps is a rate-limit experiment run in
        production at 4am. `backfill-kalshi-open-sparse` holds 03:45."""
        from app.tasks import celery_app

        ours = celery_app.conf.beat_schedule[BEAT_ENTRY]["schedule"]
        theirs = celery_app.conf.beat_schedule["backfill-kalshi-open-sparse"]["schedule"]
        assert not (ours.hour & theirs.hour) or not (ours.minute & theirs.minute)

    def test_it_is_routed_to_background_not_heavy(self):
        """`heavy` holds 2 slots for the calibration lane; a multi-minute date
        sweep there can starve the hourly /calibration warmer."""
        from app.tasks import celery_app

        assert (
            celery_app.conf.beat_schedule[BEAT_ENTRY]["options"]["queue"] == "background"
        )

    def test_the_beat_batch_matches_the_measured_default(self):
        from app.tasks import celery_app

        kwargs = celery_app.conf.beat_schedule[BEAT_ENTRY].get("kwargs") or {}
        assert kwargs.get("limit") == sweep.SWEEP_BATCH_LIMIT


# ---------------------------------------------------------------------------
# 3. A scheduled sweep that writes nothing is the failure this replaces
# ---------------------------------------------------------------------------


def _fake_backfill(monkeypatch, report, seen: dict):
    async def _run(**kwargs):
        seen.update(kwargs)
        return report

    monkeypatch.setattr(sweep, "run_backfill", _run)


def _report(*, candidates, applied, errors=0, unresolvable=0, eligible=None):
    return {
        "mode": "APPLY",
        "zero_yield": applied == 0,
        "stats": {
            "eligible_total": eligible if eligible is not None else candidates,
            "candidates": candidates,
            "writes_applied": applied,
            "errors": errors,
            "unresolvable_at_venue": unresolvable,
        },
    }


class TestTheBeatActuallyWrites:
    def test_run_sweep_applies_by_default(self, monkeypatch):
        """RED-FIRST ANCHOR. `run_backfill`'s default is `apply=False` and that
        is right for a CLI a human types. Inheriting it here would give a beat
        that runs every night, reads the venue 500 times, and writes nothing —
        scheduled and inert, indistinguishable from working."""
        seen: dict = {}
        _fake_backfill(monkeypatch, _report(candidates=3, applied=3), seen)

        asyncio.run(sweep.run_sweep())

        assert seen["apply"] is True

    def test_the_cli_default_is_still_the_harmless_one(self):
        """The other half of the same claim: a human typing the command must
        still get a dry run."""
        import inspect

        sig = inspect.signature(sweep.run_backfill)
        assert sig.parameters["apply"].default is False

    def test_it_passes_the_bounded_batch_through(self, monkeypatch):
        seen: dict = {}
        _fake_backfill(monkeypatch, _report(candidates=1, applied=1), seen)

        asyncio.run(sweep.run_sweep(limit=17, concurrency=2))

        assert seen["limit"] == 17
        assert seen["concurrency"] == 2
        # A beat must never carry an offset: the ordering rotates, and a pinned
        # offset would skip the head it is supposed to be draining.
        assert seen["offset"] == 0


# ---------------------------------------------------------------------------
# 4. Terminal truth — the three zeros are not the same zero
# ---------------------------------------------------------------------------


class TestTheTerminal:
    def test_a_batch_that_wrote_is_complete_and_green(self, monkeypatch):
        _fake_backfill(monkeypatch, _report(candidates=40, applied=31), {})

        out = asyncio.run(sweep.run_sweep())

        assert out["terminal"] == "complete"
        assert task_verdict.verdict_for(TRACKED_LABEL, out).is_green

    def test_a_drained_population_is_complete(self, monkeypatch):
        """Nothing eligible is a finished sweep, not a broken one."""
        _fake_backfill(monkeypatch, _report(candidates=0, applied=0, eligible=0), {})

        out = asyncio.run(sweep.run_sweep())

        assert out["terminal"] == "complete"

    def test_selected_but_unwritable_is_partial_and_never_green(self, monkeypatch):
        """The batch spent its whole slot on rows the venue would not resolve.
        The population did not move and the next run selects the same head —
        the CERT-766 starvation shape. It must not read as a clean run."""
        _fake_backfill(
            monkeypatch,
            _report(candidates=500, applied=0, unresolvable=500, eligible=6302),
            {},
        )

        out = asyncio.run(sweep.run_sweep())

        assert out["terminal"] == "partial"
        verdict = task_verdict.verdict_for(TRACKED_LABEL, out)
        assert not verdict.is_green
        assert verdict.authoritative

    def test_a_venue_outage_is_failed_not_drained(self, monkeypatch):
        """Every selected row errored. That is an outage; reporting it as
        `partial` or `complete` would let a dark venue read as progress."""
        _fake_backfill(
            monkeypatch, _report(candidates=500, applied=0, errors=500), {}
        )

        out = asyncio.run(sweep.run_sweep())

        assert out["terminal"] == "failed"
        assert task_verdict.verdict_for(TRACKED_LABEL, out).verdict == "failed"

    def test_the_label_is_enrolled_so_the_terminal_is_authoritative(self):
        """Enrolment without a terminal is a no-op; a terminal without
        enrolment is worse — computed, carried, and then discarded as
        non-authoritative while the run records GREEN."""
        assert TRACKED_LABEL in task_verdict.ENFORCED_TASKS

    def test_a_bounded_batch_reports_what_it_did_not_reach(self, monkeypatch):
        """6,302 eligible, 500 written: a sweep that printed only its own batch
        would read as a finished job every single night."""
        _fake_backfill(
            monkeypatch, _report(candidates=500, applied=500, eligible=6302), {}
        )

        out = asyncio.run(sweep.run_sweep())

        assert out["remaining_after_batch"] == 5802


# ---------------------------------------------------------------------------
# 5. End to end, against a fake venue — the sealed row is actually corrected
# ---------------------------------------------------------------------------


class _FakeSession:
    """Records every statement; returns the seeded rows for the SELECT."""

    def __init__(self, recorder, rows, totals):
        self.recorder = recorder
        self._rows = rows
        self._totals = totals

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.recorder.append((sql, params))
        head = sql.strip().upper()

        class _R:
            def __init__(self, rows, totals):
                self._rows, self._totals = rows, totals

            def all(self):
                return self._rows

            def first(self):
                return self._totals

        if head.startswith("SELECT ID"):
            return _R(self._rows, None)
        if head.startswith("SELECT"):
            return _R([], self._totals)
        return _R([], None)

    async def commit(self):
        self.recorder.append(("COMMIT", None))


class _FinalizedVenue:
    """One finalized event: `close_time` five days back, backstop ten days out."""

    async def get_event(self, ticker, with_nested_markets=True):
        return {
            "markets": [
                {
                    "close_time": "2026-08-28T23:29:00Z",
                    "expiration_time": "2026-09-13T15:00:00Z",
                }
            ]
        }

    async def close(self):
        return None


#: The card #2660 was filed on, as a row: sealed on its backstop, finalized at
#: the venue five days ago, still `status='open'` here.
SEALED_ROW = (
    59700136,
    "KXLPGAR2LEAD-FMC26",
    datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc),
    NOW - timedelta(days=6),
    1,
)


@pytest.mark.parametrize("apply_writes", [True, False])
def test_the_sealed_card_converges_onto_the_venue_close_time(apply_writes):
    recorder: list = []

    def maker():
        return _FakeSession(recorder, [SEALED_ROW], (1, 0, 0, 1))

    out = asyncio.run(
        sweep.run_sweep(
            apply=apply_writes,
            limit=500,
            session_maker=maker,
            client_factory=_FinalizedVenue,
        )
    )

    assert out["stats"]["moved_earlier"] == 1
    assert out["stats"]["newly_past"] == 1, (
        "the whole ship: the stored date is in the FUTURE and the venue's real "
        "one is in the past, so this row stops rendering as live"
    )

    updates = [p for s, p in recorder if s.strip().upper().startswith("UPDATE")]
    if apply_writes:
        assert len(updates) == 1
        assert updates[0]["id"] == 59700136
        assert updates[0]["resolution_date"] == datetime(
            2026, 8, 28, 23, 29, tzinfo=timezone.utc
        )
        # Never `status`, never `is_winner`, never a price — CAL-P061's
        # constraint. A wrong date and a wrong grade are different defects with
        # different blast radii and moving both at once is how #1852 happened.
        assert set(updates[0]) == {
            "id", "resolution_date", "expiration_time", "updated_at",
        }
    else:
        assert updates == [], "a dry run must prepare writes and issue none"
