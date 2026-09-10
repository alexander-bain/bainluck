"""#4655 — a finished game's Kalshi tickers are reached in minutes, not fortnights.

THE DATED SPECIMEN, read at the venue and in our own table in the same pass
(standing notice 26/27), 2026-09-10:

* Kalshi finalized all 842 markets across the NFL opener's 61 event tickers
  (our event ``14780138``, NE @ SEA) at **03:28:38Z** — two minutes after our
  own authority called the game final at 03:26:32Z. Read directly off
  ``GET /trade-api/v2/events/{ticker}?with_nested_markets=true``: 842 markets,
  842 ``finalized``, 0 open, 0 errors. (The top-level payload reads 0 markets;
  the nested list is the real one.)
* Two hours later all 61 of our rows still read ``status='open'`` with
  ``settled_at`` NULL, frozen at ``updated_at = 00:51:04Z`` — 2.5 hours BEFORE
  the final. Repo-wide at that moment: 1,181 Kalshi rows held ``open`` past a
  passed ``commence_time`` over six hours, 737 over a day, 267 over a week.

So the reader saw a live-looking price on a game that was over. That is the
ship: a finished game stops rendering as if it is still being played.

WHY THIS FILE EXECUTES THE PATH INSTEAD OF SCANNING IT. The lane's last repair
arrived with 22 passing tests — source scans, constant checks and assertions
over ``body.index(...)`` file offsets — not one of which called the function.
Running it found two defects immediately. A scan cannot tell a selection that
matches the specimen from one that matches nothing, and ``"e.completed_at" in
SELECT`` holds just as well when the join is wrong. Every test below drives
``run_recent_finals`` end to end against a seeded batch and a faked venue, and
the doubles model REFUSAL honestly: the venue can answer "still trading", and
the write is observed through the parameters actually bound to ``UPDATE_SQL``
rather than through a return count.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.tasks import kalshi_resolution_sweep as sweep
from app.utils import task_verdict

# The specimen's own clock. Fixed, and offset-first so no assertion below can
# branch on the wall clock (gotcha #44).
NOW = datetime(2026, 9, 10, 5, 30, 0, tzinfo=timezone.utc)
OUR_FINAL = datetime(2026, 9, 10, 3, 26, 32, tzinfo=timezone.utc)
VENUE_SETTLED = datetime(2026, 9, 10, 3, 28, 38, tzinfo=timezone.utc)

#: Kalshi's backstop, which is what the specimen actually holds in BOTH date
#: columns: `resolution_date == expiration_time == 2026-09-12 00:20Z`. That
#: equality is why the row is still selectable at all (#2771's provisional test)
#: and why no date-shaped path can reach it.
BACKSTOP = datetime(2026, 9, 12, 0, 20, 0, tzinfo=timezone.utc)

#: One of the opener's 61 legs, in `SELECT_SQL`'s tuple shape.
OPENER_LEG = (
    701, "KXNFLGAME-26SEP09NESEA", BACKSTOP,
    datetime(2026, 9, 10, 3, 20, tzinfo=timezone.utc), 1,
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    """Serves the SELECT and records what the write actually bound.

    It answers `count(*)` separately because the population path really does ask
    for it, and a double that returned the row list there would hand
    `run_backfill` a ticker where it expects an integer. Modelling that branch is
    what lets the paged path be driven through this same fake.
    """

    #: (eligible_total, excluded_purged, never_swept, provisional_recheck)
    TOTALS = (1, 0, 0, 1)

    def __init__(self, recorder, rows):
        self._recorder = recorder
        self._rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self._recorder.append((sql, params))
        if sql.strip().upper().startswith("UPDATE"):
            return _Result([])
        if "count(*)" in sql:
            return _Result([self.TOTALS])
        return _Result(self._rows)

    async def commit(self):
        return None


class _Venue:
    """Kalshi, answering per event ticker.

    ``settled`` is a parameter and not a fixture constant because the honest
    double has to be able to REFUSE: a game our authority called final that the
    venue has not finalized yet is the normal state for the first minutes after
    a whistle, and a double that always settles makes "reached the venue" and
    "wrote the row" indistinguishable.
    """

    def __init__(self, *, settled: bool, markets: int = 2, raises: bool = False):
        self._settled = settled
        self._markets = markets
        self._raises = raises
        self.asked: list[str] = []
        self.closed = False

    async def get_event(self, ticker, with_nested_markets=True):
        self.asked.append(ticker)
        if self._raises:
            raise RuntimeError("venue down")
        iso = (VENUE_SETTLED if self._settled else BACKSTOP).isoformat()
        leg = {
            "ticker": f"{ticker}-LEG",
            "status": "finalized" if self._settled else "active",
            "close_time": iso.replace("+00:00", "Z"),
            "expiration_time": BACKSTOP.isoformat().replace("+00:00", "Z"),
        }
        if self._settled:
            # The grade rides the same payload. This rail must read it and never
            # write it (CAL-P061 / #1852).
            leg["result"] = "yes"
        return {"markets": [dict(leg) for _ in range(self._markets)]}

    async def close(self):
        self.closed = True


def _drive(*, settled=True, rows=(OPENER_LEG,), apply=True, raises=False, limit=200):
    recorder: list = []
    venue = _Venue(settled=settled, raises=raises)

    def maker():
        return _Session(recorder, list(rows))

    report = asyncio.run(
        sweep.run_recent_finals(
            limit=limit,
            apply=apply,
            session_maker=maker,
            client_factory=lambda: venue,
            now=NOW,
        )
    )
    selects = [(s, p) for s, p in recorder if not s.strip().upper().startswith("UPDATE")]
    updates = [p for s, p in recorder if s.strip().upper().startswith("UPDATE")]
    return report, selects, updates, venue


class TestTheSelectionIsKeyedOnTheEventNotThePopulation:
    """The defect is that both existing arms are population sweeps."""

    def test_it_selects_on_our_own_completed_at_within_a_bounded_window(self):
        _, selects, _, _ = _drive()

        assert len(selects) == 1, "one bounded read, not a paged walk"
        sql, params = selects[0]
        assert "e.completed_at >= :final_floor" in sql
        assert params["final_floor"] == NOW - timedelta(
            hours=sweep.RECENT_FINAL_WINDOW_HOURS
        )
        # The specimen sits 2h04m inside a 6h window. If the window were ever
        # tightened below that the opener would fall out of its own guard.
        assert params["final_floor"] < OUR_FINAL, (
            "the specimen's final must be inside the window this arm asks for"
        )

    def test_the_freshest_final_is_first_which_updated_at_asc_cannot_do(self):
        """`updated_at ASC` puts a just-finished game LAST — it was polled until
        minutes ago, so it carries the newest stamp in the population. That is
        why no batch size of the population sweep reaches a fresh final in time,
        and why this arm cannot simply reuse `SELECT_SQL`'s ordering."""
        sql, _ = _drive()[1][0]
        order = sql.split("ORDER BY", 1)[1]
        assert order.index("e.completed_at DESC") < order.index("fm.updated_at ASC")

    def test_it_only_considers_rows_we_still_call_open(self):
        """`status='open'` IS the drain: the write flips a confirmed leg to
        'resolved', so it leaves this selection permanently on the run that
        fixes it. Without that clause the window would re-read settled rows for
        six hours."""
        sql, _ = _drive()[1][0]
        assert "fm.status = 'open'" in sql

    def test_the_batch_is_bounded_by_the_limit_it_was_given(self):
        _, selects, _, _ = _drive(limit=37)
        assert selects[0][1]["limit"] == 37


class TestTheSpecimenActuallyGetsWritten:
    """Red-then-green on the opener's own leg."""

    def test_a_finished_game_the_venue_has_settled_is_written_resolved(self):
        report, _, updates, venue = _drive(settled=True)

        assert venue.asked == ["KXNFLGAME-26SEP09NESEA"], (
            "the venue is asked for the specimen's own event ticker"
        )
        assert len(updates) == 1, "the leg reaches the write"
        assert updates[0]["id"] == 701
        assert updates[0]["venue_settled"] is True, (
            "RED ANCHOR: this is the parameter UPDATE_SQL switches both "
            "status->'resolved' and settled_at on. False here means the row "
            "keeps reading `open` — the whole defect, rebuilt inside the fix."
        )
        assert report["stats"]["venue_settled"] == 1
        assert report["stats"]["writes_applied"] == 1
        assert report["terminal"] == "complete"

    def test_the_write_carries_no_grade_and_no_price(self):
        """CAL-P061 / #1852, inherited unchanged. The venue payload above
        carries `result: yes`; it must not reach a column."""
        _, _, updates, _ = _drive(settled=True)
        bound = set(updates[0])
        assert not bound & {"is_winner", "result", "probability", "last_price"}
        assert bound == {
            "id", "resolution_date", "expiration_time", "venue_settled", "updated_at",
        }

    def test_a_dry_run_reaches_the_venue_and_writes_nothing(self):
        report, _, updates, venue = _drive(settled=True, apply=False)
        assert venue.asked, "a dry run still measures"
        assert updates == []
        assert report["stats"]["writes_prepared"] == 1
        assert report["stats"]["writes_applied"] == 0

    def test_the_venue_client_is_closed_even_though_it_has_no_context_manager(self):
        _, _, _, venue = _drive(settled=True)
        assert venue.closed is True


class TestTheZeroesAreToldApart:
    """This arm's ordinary healthy return is zero writes, so the zeroes have to
    be distinguishable or the surface is useless (#1515)."""

    def test_no_game_finished_is_complete_and_never_reaches_the_venue(self):
        report, _, updates, venue = _drive(rows=())
        assert venue.asked == [] and updates == []
        assert report["terminal"] == "complete"
        assert report["zero_yield"] is True
        assert "no rows supplied" in report["zero_yield_reason"], (
            "a supplied batch has no population denominator; the inherited "
            "sentence would print four -1s as a diagnosis"
        )

    def test_a_game_the_venue_has_not_finalized_yet_is_partial_not_complete(self):
        """The normal state for the first minutes after a whistle. It must not
        read GREEN — nothing the reader can see was fixed — and it must not read
        FAILED, because the venue is behaving correctly.

        THE TRAP THIS PINS, and it was found by running the thing rather than
        reading it. An unsettled leg DOES produce a write: the derivation
        re-derives the same backstop date off the venue's `close_time` and
        returns a row, so `writes_applied` is 1. Grading on `writes_applied` —
        which is the population sweep's correct rule — reads that as `complete`.
        A date was refreshed; the row is still `open` and the reader is still
        looking at a live price on a finished game. That is #4655 itself,
        graded GREEN from inside its own fix."""
        report, _, updates, venue = _drive(settled=False)

        assert venue.asked, "we did ask"
        assert len(updates) == 1, "a date write happens — this is the trap"
        assert updates[0]["venue_settled"] is False, (
            "and it does NOT close the row, which is the only thing that "
            "removes the live-looking price"
        )
        assert report["stats"]["writes_applied"] == 1
        assert report["stats"]["venue_settled"] == 0
        assert report["terminal"] == "partial", (
            "graded on venue_settled, not on writes_applied"
        )

    def test_a_venue_outage_is_failed_not_a_quiet_window(self):
        report, _, updates, _ = _drive(raises=True)
        assert report["terminal"] == "failed"
        assert report["stats"]["errors"] == 1
        assert updates == []

    def test_a_saturated_batch_says_so(self):
        """A full batch means finals are arriving faster than one run drains
        them, so the 30-minute bar is at risk on the NEXT run."""
        rows = tuple(
            (900 + i, f"KXNFLGAME-26SEP09T{i:02d}", BACKSTOP, NOW, 1) for i in range(3)
        )
        assert _drive(rows=rows, limit=3)[0]["batch_saturated"] is True
        assert _drive(rows=rows, limit=9)[0]["batch_saturated"] is False


class TestTheWiring:
    """Every trap this lane has actually been caught by."""

    def test_the_label_is_enrolled_so_the_terminal_is_authoritative(self):
        """Enrolment without a terminal is a no-op; a terminal without enrolment
        is worse — computed, carried, then discarded while the run records
        GREEN. This arm's healthy return is zero writes, so unenrolled it would
        report GREEN straight through a venue outage."""
        assert "kalshi_recent_finals" in task_verdict.ENFORCED_TASKS

    def test_the_task_is_registered_and_runs_this_function(self):
        from app.tasks import celery_app

        assert "app.tasks.settle_kalshi_recent_finals" in celery_app.tasks

    def test_the_beat_exists_and_meets_the_thirty_minute_bar(self):
        """#4655's bar is 30 minutes from the venue settling, so the WORST gap
        between two firings has to be under it — a period at or above the bar
        cannot meet it even when everything else works.

        Measured on the crontab's own parsed fields, NOT on
        `remaining_estimate`. That helper reads Celery's internal clock rather
        than a `now` you hand it, so an assertion built on it is a clock branch
        (gotcha #44) — and it is: a mutation from `*/10` to hourly survived it,
        because the answer depended on what minute the suite happened to run."""
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["settle-kalshi-recent-finals"]
        assert entry["task"] == "app.tasks.settle_kalshi_recent_finals"

        schedule = entry["schedule"]
        assert len(schedule.hour) == 24, "every hour, not a nightly slot"
        minutes = sorted(schedule.minute)
        # Cyclic, so the wrap from the last firing of one hour to the first of
        # the next is a real gap and is the one an hourly beat fails on.
        gaps = [b - a for a, b in zip(minutes, minutes[1:])]
        gaps.append(60 - minutes[-1] + minutes[0])
        assert max(gaps) <= 30, (
            f"worst gap between firings is {max(gaps)}min, over the 30min bar"
        )

    def test_it_is_not_on_the_queue_whose_messages_die_on_a_release(self):
        """`background` is --concurrency=2 against 57 beats with
        task_acks_late=False, so a reserved message is acked before it executes
        and a release destroys it leaving no trace — which is the state
        `sweep_kalshi_resolution_window` is in (registered, last observed firing
        2026-09-05, and holding no task-metrics key inside the 48h TTL despite
        two scheduled firings)."""
        from app.tasks import celery_app, _HEAVY_KEEP_ON_BACKGROUND

        entry = celery_app.conf.beat_schedule["settle-kalshi-recent-finals"]
        assert entry["options"]["queue"] == "realtime"
        assert "app.tasks.settle_kalshi_recent_finals" not in _HEAVY_KEEP_ON_BACKGROUND

    def test_the_message_expires_within_one_period_instead_of_lapping(self):
        """#1609's rule. The next fire selects the same freshest-final head, so
        an undelivered run is duplicate venue cost, not lost work."""
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["settle-kalshi-recent-finals"]
        assert entry["options"]["expires"] <= 600

    def test_the_two_kalshi_venue_sweeps_never_contend_for_one_worker(self):
        """`*/10` lands on :20 every hour, so this arm WILL coincide with the
        population sweep's 04:20Z slot. That is fine and the separation is the
        queue, not the minute — so assert the thing that is actually true rather
        than a minute comparison that would have to be weakened to pass."""
        from app.tasks import celery_app

        mine = celery_app.conf.beat_schedule["settle-kalshi-recent-finals"]
        other = celery_app.conf.beat_schedule["sweep-kalshi-resolution-window"]
        assert mine["options"]["queue"] != other["options"]["queue"]

    def test_the_rows_override_did_not_disturb_the_paged_path(self):
        """`run_backfill` still selects and still counts when no rows are
        supplied — the override is an extra door, not a replacement."""
        recorder: list = []

        def maker():
            return _Session(recorder, [OPENER_LEG])

        asyncio.run(
            sweep.run_backfill(
                session_maker=maker,
                client_factory=lambda: _Venue(settled=True),
                limit=500,
                apply=False,
                now=NOW,
            )
        )
        sql = [s for s, _ in recorder]
        assert any("ORDER BY" in s and "futures_markets" in s for s in sql), (
            "the paged SELECT still runs"
        )
        assert any("count(*)" in s for s in sql), "and so does the population COUNT"

    def test_the_window_is_wide_enough_for_the_specimens_own_venue_lag(self):
        """Kalshi settled the opener 2m06s after our final. The window is the
        re-ask budget, so it has to be comfortably larger than that lag or a
        venue that settles slowly falls out before we reach it."""
        lag = VENUE_SETTLED - OUR_FINAL
        assert timedelta(hours=sweep.RECENT_FINAL_WINDOW_HOURS) > lag * 100

    def test_the_batch_limit_is_bounded_and_under_the_measured_population(self):
        """603 open legs across 29 events in six hours, measured on production
        2026-09-10. A limit at or above that would make every run a full-window
        re-read; well under it, with freshest-final ordering, is what keeps the
        newest game inside the first batch."""
        assert 0 < sweep.RECENT_FINAL_BATCH_LIMIT < 603
