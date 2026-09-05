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
from app.tasks.kalshi_resolution_sweep import next_cursor
from app.utils import task_verdict

NOW = datetime(2026, 9, 3, 22, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _in_memory_cursor(monkeypatch):
    """A working cursor store for every test that is not about the cursor.

    Without it the sweep reaches for real Redis, `_write_cursor` returns False,
    and every terminal test reads `failed` for a reason that has nothing to do
    with what it is asserting. Tests that ARE about Redis behaviour re-patch
    this below; the later monkeypatch wins.
    """
    import app.tasks.redis_state as redis_state

    store: dict = {}

    class _Redis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ex=None):
            store[key] = value

    monkeypatch.setattr(redis_state, "get_async_redis_client", _Redis)
    return store

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
# 5. The rotating cursor — the jam this queue MEASURED
# ---------------------------------------------------------------------------


class TestTheCursorRotatesPastAJam:
    """The first production-shaped run selected 500 rows and wrote zero.

    `pg_stat_statements` settled what happened: `SELECT_SQL` 1 call / 500 rows /
    185 ms, `COUNT_SQL` 1 call, and no matching UPDATE recorded at all. The head
    of the batch says why — `KXTXPRIMARY-31D26`, `commence_time 2027-11-03`
    (equal to the backstop, the poisoned-column shape #2771 named), last touched
    by the poller 2026-06-20. The retention floor is a `commence_time` test, so
    it reads a purged row as recent and admits it; the venue returns no markets;
    the row cannot be written; and a row that is never written never has its
    `updated_at` refreshed, so under `ORDER BY updated_at ASC` it holds the head
    forever.

    #2771's rotation argument is true only of rows that get WRITTEN. These tests
    pin the part that makes it true of the rest.
    """

    def test_a_fully_stranded_batch_advances_the_cursor(self):
        """Without this the beat re-selects the same 500 rows every night."""
        assert next_cursor(
            offset=0, scanned=0, candidates=500, applied=0, eligible_total=5569
        ) == (500, 500)

    def test_it_advances_by_what_stayed_put_not_by_the_batch_size(self):
        """470 of 500 written means 30 rows kept their slot. Advancing a full
        batch would skip 470 rows that just rotated to the back — and advancing
        zero would re-read the 30 forever. Only `candidates - applied` tracks
        the jam itself."""
        assert next_cursor(
            offset=100, scanned=0, candidates=500, applied=470, eligible_total=5569
        ) == (130, 500)

    def test_a_clean_batch_holds_its_offset_instead_of_resetting(self):
        """The correction the offset-500 measurement forced.

        Resetting to 0 on a clean batch is the obvious first implementation and
        it re-enters the jam every other night: measured 2026-09-03, offset 0 is
        500 unwritable rows last touched in June and offset 500 is 500 rows the
        poller touched today, all of which write cleanly. Reset gives
        jam/productive/jam/productive and burns half the nights.

        Holding is also just correct — when 500 rows rotate to the back, the row
        that was at position 1,000 is now at 500, so the same offset already
        points at fresh content.

        🔴 CERT-863: holding is right, AND it is what made the wrap unreachable
        while the offset was the only state. The traversal count must move on
        exactly this batch — `scanned` 0 -> 500 below — which is the assertion
        that stops the fix for that block from being reverted into this one.
        """
        assert next_cursor(
            offset=800, scanned=0, candidates=500, applied=500, eligible_total=5569
        ) == (800, 500)

    def test_the_cursor_wraps_instead_of_walking_off_the_end(self):
        """A monotonic cursor eventually points past the population and the
        sweep goes permanently quiet — the same silent nothing this queue is
        fixing, wearing a different mechanism. Wrapping also re-reaches rows
        that BECAME resolvable: Kalshi publishes `close_time` on finalize, so
        September's unresolvable row is October's necessary write.

        This is the OFFSET wrap, kept beside the traversal wrap: a consistent
        cursor never reaches it (`offset <= scanned` always), but a legacy bare
        offset or a population that shrank under the cursor can, and then this
        is the test that saves the run from selecting nothing forever.
        """
        assert next_cursor(
            offset=5400, scanned=0, candidates=500, applied=0, eligible_total=5569
        ) == (0, 0)

    def test_the_cursor_wraps_once_the_cycle_has_traversed_the_population(self):
        """🔴 THE CERT-863 REPAIR, at the arithmetic.

        The traversal wrap, which the offset could not express. 1,000 rows
        already seen this cycle plus a 500-row batch reaches a 1,500-row
        population, so the cycle closes and BOTH halves return to the head —
        even though this batch is perfectly clean and strands nothing, which is
        the case where the offset does not move at all.
        """
        assert next_cursor(
            offset=500, scanned=1000, candidates=500, applied=500, eligible_total=1500
        ) == (0, 0)

    def test_a_clean_batch_short_of_the_population_keeps_counting(self):
        """The control for the test above: the same clean, non-stranding batch
        one cycle-step earlier does NOT wrap. Without this, "wrap on every clean
        batch" passes the test above and re-enters the jam every other night —
        the reset this class already rejected, arriving through the new half."""
        assert next_cursor(
            offset=500, scanned=500, candidates=500, applied=500, eligible_total=1500
        ) == (500, 1000)

    def test_an_empty_batch_returns_to_the_head(self):
        assert next_cursor(
            offset=900, scanned=0, candidates=0, applied=0, eligible_total=0
        ) == (0, 0)

    def test_run_sweep_starts_from_the_cursor_and_persists_the_next_one(
        self, monkeypatch
    ):
        seen: dict = {}
        _fake_backfill(
            monkeypatch, _report(candidates=500, applied=0, unresolvable=500,
                                 eligible=5569), seen
        )
        written: list = []

        async def _read():
            return 1000, 1000

        async def _write(o, s):
            written.append((o, s))
            return True

        monkeypatch.setattr(sweep, "_read_cursor", _read)
        monkeypatch.setattr(sweep, "_write_cursor", _write)

        out = asyncio.run(sweep.run_sweep())

        assert seen["offset"] == 1000, "the batch must start where the cursor points"
        assert out["next_offset"] == 1500
        assert written == [(1500, 1500)]
        assert out["stranded"] == 500

    def test_an_unreadable_cursor_starts_at_the_head_rather_than_raising(
        self, monkeypatch
    ):
        """A Redis outage must degrade this sweep to its PRE-CURSOR behaviour —
        offset 0 — not take the beat down."""
        import app.tasks.redis_state as redis_state

        class _DeadRedis:
            async def get(self, key):
                raise ConnectionError("Error 111 connecting to rediss://host")

            async def set(self, *a, **kw):
                raise ConnectionError("Error 111 connecting to rediss://host")

        monkeypatch.setattr(redis_state, "get_async_redis_client", _DeadRedis)

        assert asyncio.run(sweep._read_cursor()) == (0, 0)
        assert asyncio.run(sweep._write_cursor(500, 500)) is False

    def test_a_cursor_round_trips_through_redis(self, monkeypatch):
        """The control for the test above: with a working client the cursor is
        actually read and actually written, so `== 0` there is a degradation
        rather than the only thing this code can do."""
        import app.tasks.redis_state as redis_state

        store: dict = {}

        class _LiveRedis:
            async def get(self, key):
                return store.get(key)

            async def set(self, key, value, ex=None):
                store[key] = value
                store[key + ":ttl"] = ex

        monkeypatch.setattr(redis_state, "get_async_redis_client", _LiveRedis)

        assert asyncio.run(sweep._write_cursor(1500, 2000)) is True
        assert asyncio.run(sweep._read_cursor()) == (1500, 2000)
        assert store[sweep.SWEEP_CURSOR_KEY + ":ttl"] == sweep.SWEEP_CURSOR_TTL_S

        # BOTH numbers survive one key. Splitting the pair across two keys lets
        # a half-written cursor claim a cycle is further along than its offset,
        # which skips rows silently — see `SWEEP_CURSOR_KEY`.
        assert store[sweep.SWEEP_CURSOR_KEY] == "1500:2000"

    def test_a_legacy_bare_offset_still_reads_as_an_offset(self, monkeypatch):
        """🔴 CERT-863 deploys ON TOP of a live Redis value written by the
        pre-repair beat, which encoded the offset alone. Read as `(500, 0)`: the
        offset is still true and the cycle count restarts, so the first wrap
        after deploy is at most one cycle late. Crashing here — or reading it as
        0 — would silently re-enter the jam on the night of the deploy."""
        import app.tasks.redis_state as redis_state

        for raw, expected in (("500", (500, 0)), (b"500", (500, 0)), (None, (0, 0))):

            class _Redis:
                async def get(self, key, _v=raw):
                    return _v

                async def set(self, *a, **kw):
                    pass

            monkeypatch.setattr(redis_state, "get_async_redis_client", _Redis)
            assert asyncio.run(sweep._read_cursor()) == expected, raw

    def test_a_cursor_that_did_not_persist_is_failed_not_quietly_fine(
        self, monkeypatch
    ):
        """Progress made and silently unresumable: the next beat re-enters this
        exact batch and the jam returns. Same call the typeahead index builder
        makes for the same reason (#1866)."""
        _fake_backfill(
            monkeypatch,
            _report(candidates=500, applied=0, unresolvable=500, eligible=5569),
            {},
        )

        async def _read():
            return 0, 0

        async def _write(o, s):
            return False

        monkeypatch.setattr(sweep, "_read_cursor", _read)
        monkeypatch.setattr(sweep, "_write_cursor", _write)

        out = asyncio.run(sweep.run_sweep())

        assert out["cursor_persisted"] is False
        assert out["terminal"] == "failed"
        assert not task_verdict.verdict_for(TRACKED_LABEL, out).is_green

    def test_no_write_is_attempted_when_the_cursor_does_not_move(self, monkeypatch):
        """A clean batch's next offset is 0 and the cursor is usually already 0.
        Writing it anyway would turn every healthy run into a Redis round trip
        that can fail and mark the run `failed` for no reason."""
        _fake_backfill(monkeypatch, _report(candidates=10, applied=10, eligible=10), {})
        calls: list = []

        async def _read():
            return 0, 0

        async def _write(o, s):
            calls.append((o, s))
            return False

        monkeypatch.setattr(sweep, "_read_cursor", _read)
        monkeypatch.setattr(sweep, "_write_cursor", _write)

        out = asyncio.run(sweep.run_sweep())

        assert calls == []
        assert out["terminal"] == "complete"


# ---------------------------------------------------------------------------
# 6. End to end, against a fake venue — the sealed row is actually corrected
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
        # Never `is_winner`, never a price — CAL-P061's constraint. A wrong date
        # and a wrong grade are different defects with different blast radii and
        # moving both at once is how #1852 happened. `venue_settled` joined the
        # parameter set under #2722 and is a STATUS bind, not a grade: it is the
        # venue's own word about whether the market is over, and this fixture's
        # payload does not say it is.
        assert set(updates[0]) == {
            "id", "resolution_date", "expiration_time", "venue_settled",
            "updated_at",
        }
        assert updates[0]["venue_settled"] is False
    else:
        assert updates == [], "a dry run must prepare writes and issue none"


# ---------------------------------------------------------------------------
# 7. 🔴 CERT-863 — the jam is REVISITED, proven over consecutive nights
#
# The BLOCK: `next_offset` advanced by `candidates - applied`, so a clean batch
# advanced by zero and the cursor stuck at 500 forever. The cert's exact-head
# reproduction printed `0 -> 500 -> 500 -> 500 -> 500` on a stable 1,500-row
# population with a 500-row stranded prefix. The prefix was then unreachable
# until the 30-day Redis TTL expired, so a market that Kalshi finalizes in
# October keeps rendering its dead last-trade price for up to a month — the
# exact user-visible failure this beat claims to end.
#
# Everything below drives the REAL `run_sweep` over consecutive runs against a
# simulated population that rotates the way the database does. An arithmetic
# test of `next_cursor` alone cannot see this defect: every individual value the
# old function returned was defensible, and only the SEQUENCE is wrong.
# ---------------------------------------------------------------------------


class _RotatingPopulation:
    """The measured shape: an unwritable prefix in front of a rotating suffix.

    Ordered by `updated_at ASC`, sliced by LIMIT/OFFSET, and a write bumps the
    stamp so the row rotates to the back — which is the whole reason the offset
    may hold. Rows stay ELIGIBLE after a write: this models the
    `provisional_recheck` half of the population, which the module's own
    docstring says "refills every time a market is swept before it settles". It
    is also the only shape that traps the cursor, so it is the shape to guard.
    """

    def __init__(self, *, stranded: int = 500, writable: int = 1000):
        base = NOW - timedelta(days=90)
        self.rows = [
            {"id": i, "ticker": f"KXJAM-{i}", "stamp": base + timedelta(seconds=i)}
            for i in range(stranded)
        ] + [
            {
                "id": 100000 + i,
                "ticker": f"KXOK-{i}",
                "stamp": base + timedelta(days=30, seconds=i),
            }
            for i in range(writable)
        ]
        self.writes_by_ticker: dict[str, int] = {}

    def ordered(self):
        return sorted(self.rows, key=lambda r: r["stamp"])

    def select(self, *, limit, offset):
        window = self.ordered()[offset : offset + limit]
        return [
            (r["id"], r["ticker"], NOW + timedelta(days=30), NOW - timedelta(days=6), 1)
            for r in window
        ]

    def apply(self, params):
        for r in self.rows:
            if r["id"] == params["id"]:
                # The write refreshes the stamp; that IS the rotation.
                r["stamp"] = params["updated_at"] + timedelta(
                    microseconds=len(self.writes_by_ticker)
                )
                self.writes_by_ticker[r["ticker"]] = (
                    self.writes_by_ticker.get(r["ticker"], 0) + 1
                )
                return

    def session_maker(self):
        population = self

        class _S:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def execute(self, statement, params=None):
                sql = str(statement).strip().upper()

                class _R:
                    def __init__(self, rows=None, totals=None):
                        self._rows, self._totals = rows or [], totals

                    def all(self):
                        return self._rows

                    def first(self):
                        return self._totals

                if sql.startswith("SELECT ID"):
                    return _R(
                        rows=population.select(
                            limit=params["limit"], offset=params["offset"]
                        )
                    )
                if sql.startswith("SELECT"):
                    return _R(totals=(len(population.rows), 0, 0, len(population.rows)))
                if sql.startswith("UPDATE"):
                    population.apply(params)
                return _R()

            async def commit(self):
                return None

        return _S()


class _VenueThatFinalizesTheJamLater:
    """Unresolvable for `KXJAM-*` until :meth:`finalize_the_jam` is called.

    That flip is the fact the wrap exists for. Kalshi publishes `close_time` on
    finalize, so a row the venue would not resolve in September is precisely the
    row that must be written in October — and it can only be written if the
    sweep comes back to it.
    """

    jam_is_finalized = False

    async def get_event(self, ticker, with_nested_markets=True):
        if ticker.startswith("KXJAM-") and not type(self).jam_is_finalized:
            # 200 with no markets — the purged/unresolvable shape that strands
            # the row without erroring, so it keeps its slot under `updated_at`.
            return {"markets": []}
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

    @classmethod
    def finalize_the_jam(cls):
        cls.jam_is_finalized = True


def _run_nights(population, *, nights, limit=500):
    """Consecutive unattended runs through the REAL cursor, as the beat does."""
    out = []
    for _ in range(nights):
        out.append(
            asyncio.run(
                sweep.run_sweep(
                    limit=limit,
                    apply=True,
                    session_maker=population.session_maker,
                    client_factory=_VenueThatFinalizesTheJamLater,
                )
            )
        )
    return out


@pytest.fixture(autouse=True)
def _jam_starts_unresolved():
    _VenueThatFinalizesTheJamLater.jam_is_finalized = False
    yield
    _VenueThatFinalizesTheJamLater.jam_is_finalized = False


class TestTheStrandedPrefixIsRevisitedWithinACycle:
    def test_the_cursor_does_not_stick_at_500_forever(self):
        """🔴 THE REPRODUCTION FROM THE BLOCK, inverted into a guard.

        The cert printed `0 -> 500 -> 500 -> 500 -> 500` at the blocked head.
        The repair must return to 0 — that is the difference between a jam
        re-read every few nights and one re-read when Redis forgets.
        """
        pop = _RotatingPopulation(stranded=500, writable=1000)
        offsets = [r["offset"] for r in _run_nights(pop, nights=5)]

        assert offsets != [0, 500, 500, 500, 500], (
            "this is the exact sequence CERT-863 measured at the blocked head; "
            "seeing it again means the cursor is stuck in the clean suffix"
        )
        assert offsets == [0, 500, 500, 0, 500], offsets
        assert offsets.count(0) >= 2, (
            "the cycle must return to the head at least once in five nights"
        )

    def test_the_prefix_is_written_once_the_venue_finalizes_it(self):
        """THE SHIP, over time. Three nights of the jam being unresolvable, then
        Kalshi finalizes it, and the very next cycle must write those rows."""
        pop = _RotatingPopulation(stranded=500, writable=1000)

        _run_nights(pop, nights=3)
        jam_writes = [t for t in pop.writes_by_ticker if t.startswith("KXJAM-")]
        assert jam_writes == [], (
            "control: while the venue will not resolve them, the prefix rows are "
            "selected and correctly written zero times"
        )

        _VenueThatFinalizesTheJamLater.finalize_the_jam()
        _run_nights(pop, nights=1)

        jam_writes = [t for t in pop.writes_by_ticker if t.startswith("KXJAM-")]
        assert len(jam_writes) == 500, (
            f"the whole point of the wrap: all 500 newly-finalized prefix rows "
            f"must be revisited and written, got {len(jam_writes)}"
        )

    def test_the_revisit_happens_in_nights_not_in_a_month(self):
        """The BOUND, counted from the finalize and stated against the TTL.

        Before the repair the only path back to the head was expiry of the Redis
        key — 30 days. The cycle must close in `ceil(eligible / limit)` runs.

        THE CURSOR IS ADVANCED PAST THE JAM BEFORE THE VENUE FINALIZES IT, and
        that ordering is the test. Finalizing first lets night one write the
        prefix off the initial offset of 0, which proves nothing about coming
        BACK to it — the guard passes under the blocked implementation. Measured:
        with the finalize moved to the front this test is green on the CERT-863
        head, so the two nights below are the whole assertion.
        """
        pop = _RotatingPopulation(stranded=500, writable=1000)

        _run_nights(pop, nights=2)
        assert not any(t.startswith("KXJAM-") for t in pop.writes_by_ticker), (
            "setup: the cursor must be past the prefix with the prefix unwritten"
        )

        _VenueThatFinalizesTheJamLater.finalize_the_jam()

        nights_after_finalize = None
        for night in range(1, 31):
            _run_nights(pop, nights=1)
            if any(t.startswith("KXJAM-") for t in pop.writes_by_ticker):
                nights_after_finalize = night
                break

        assert nights_after_finalize is not None, "never came back to the prefix"
        ttl_days = sweep.SWEEP_CURSOR_TTL_S / 86400
        assert nights_after_finalize == 2, nights_after_finalize
        assert nights_after_finalize < ttl_days, (
            f"revisit took {nights_after_finalize} nights against a "
            f"{ttl_days:.0f}-day TTL — the backstop must not be the mechanism"
        )

    def test_the_wrap_is_reported_on_the_summary_not_silent(self):
        """A cursor that returns to 0 and a cursor that was LOST look identical
        from outside. The run that closes a cycle says so."""
        pop = _RotatingPopulation(stranded=500, writable=1000)
        runs = _run_nights(pop, nights=4)

        assert [r["cycle_wrapped"] for r in runs] == [False, False, True, False]
        assert runs[2]["next_offset"] == 0 and runs[2]["next_scanned"] == 0

    def test_the_suffix_is_still_swept_while_the_cycle_runs(self):
        """The control that stops "wrap to 0 every night" from passing the class.

        Resetting each night would revisit the prefix constantly and re-enter the
        jam every night, sweeping nothing else — the failure the offset-holding
        rule already rejected. Over four nights the rotating suffix must actually
        be covered.
        """
        pop = _RotatingPopulation(stranded=500, writable=1000)
        _run_nights(pop, nights=4)

        ok_written = {t for t in pop.writes_by_ticker if t.startswith("KXOK-")}
        assert len(ok_written) == 1000, (
            f"the whole writable suffix must be swept within the cycle, "
            f"got {len(ok_written)}"
        )
