"""The nightly settlement-capture beat: it fires, it is enforced, and it resumes.

#2077 / queue 419. The sweep RUNNER is certified and unchanged (`CERT-405`,
`C-CAPTURE-AUTH-BACKOFF-1` GREEN on PR #2210; `C-CAPTURE-LIVELOCK-1` GREEN,
`CODEX-CERT-LOG.md:97` and `:105`). What did not exist was a *beat* — the run
fired twice, on 2026-08-25 and 2026-08-26, because a person pasted a
`heroku run:detached` line each time.

These gates are about the WRAPPER only. Every one of them is written so that the
obvious lazy wrapper fails it:

* **G1** the beat entry exists, at ~03:00 PT, with the certified parameters.
* **G2** the label is enrolled in ``ENFORCED_TASKS`` **and** the summary carries a
  real terminal. Either half alone is a no-op — ``task_verdict``'s own docstring
  spends thirty lines on that trap and ``polymarket_winners`` is the incident.
* **G3** the four zeros stay four. A wrapper that flattened them would report the
  total loss and the drained cohort with the same word.
* **G4** the sweep id is **date-derived**, never generated per run. A per-run id
  is what turns "re-running is the intended recovery" into "every run re-probes
  the whole population".
* **G5** the wrapper adds no sweep logic and writes no ``is_winner``.
* **G6** the in-task deadline is strictly inside the soft time limit, so a
  truncated run banks and resumes instead of being SIGKILLed (gotcha: a
  ``task_time_limit`` kill runs no exit path at all).
* **G7** it stays on ``background`` with the rest of the multi-minute backfill
  family, and is DECLARED there rather than left to the default.
* **G8** the fire minute is CLEAR of same-queue co-fires, measured over the FULL
  assembled schedule — interval and sub-hourly entries included, not the daily
  ones alone. Added by CERT-418 [P1]; see the section header for the incident.
"""

import inspect

import pytest

from app.tasks import celery_app


BEAT_KEY = "settlement-capture-sweep-nightly"
TASK_NAME = "app.tasks.run_settlement_sweep"
VERDICT_LABEL = "settlement_sweep"


def _entry():
    return celery_app.conf.beat_schedule[BEAT_KEY]


# ---------------------------------------------------------------------------
# G1 — the beat exists, at the ruled hour, with the certified parameters
# ---------------------------------------------------------------------------

class TestG1BeatEntry:
    def test_the_beat_entry_exists_and_names_the_task(self):
        assert BEAT_KEY in celery_app.conf.beat_schedule, (
            "the settlement sweep has no beat entry — it only runs when a person "
            "pastes a heroku line, which is the whole defect #2077 named"
        )
        assert _entry()["task"] == TASK_NAME

    def test_it_fires_once_a_night_at_about_0300_pacific(self):
        """10:00-10:59 UTC = 03:xx PDT. One fire a night, not an interval."""
        schedule = _entry()["schedule"]
        assert hasattr(schedule, "hour"), (
            f"expected a crontab, got {schedule!r} — an interval schedule would "
            "re-fire the sweep all day"
        )
        assert set(schedule.hour) == {10}, (
            f"expected hour=10 UTC (03:xx PDT / 02:xx PST), got {sorted(schedule.hour)}"
        )
        assert len(set(schedule.minute)) == 1, (
            f"expected a single minute, got {sorted(schedule.minute)}"
        )
        # Daily: the crontab must not narrow to particular days.
        assert len(set(schedule.day_of_week)) == 7
        assert len(set(schedule.day_of_month)) == 31

    def test_it_carries_the_certified_budget_and_concurrency(self):
        """3000 / 4 — the parameters the two live runs used, not new ones."""
        assert _entry()["kwargs"] == {"budget": 3000, "concurrency": 4}

    def test_the_beat_parameters_are_the_runner_defaults_not_a_second_opinion(self):
        """A literal in the beat that drifts from the runner's own constant is
        two sources of truth. They are pinned equal here so a change to either
        has to be a change to both, on purpose."""
        from app.services.settlement_sweep_runner import (
            DEFAULT_BUDGET,
            DEFAULT_CONCURRENCY,
        )

        assert _entry()["kwargs"]["budget"] == DEFAULT_BUDGET
        assert _entry()["kwargs"]["concurrency"] == DEFAULT_CONCURRENCY


# ---------------------------------------------------------------------------
# G2 — enrolled AND terminal-bearing. Either half alone is a no-op.
# ---------------------------------------------------------------------------

class TestG2EnforcedWithARealTerminal:
    def test_the_label_is_enrolled(self):
        from app.utils.task_verdict import ENFORCED_TASKS

        assert VERDICT_LABEL in ENFORCED_TASKS

    def test_the_task_hands_that_exact_label_to_tracked_run(self):
        """Enrolment keys on the label passed to `_tracked_run`, not on the
        Celery task name. A label typo enrols nothing and still reads GREEN."""
        from app.tasks import run_settlement_sweep

        source = inspect.getsource(run_settlement_sweep)
        assert f'"{VERDICT_LABEL}"' in source, (
            f"the task does not pass {VERDICT_LABEL!r} to _tracked_run — "
            "enrolment would key on a label nothing emits"
        )

    @pytest.mark.parametrize(
        "terminal,expected_authoritative",
        [
            ("complete", True),
            ("partial", True),
            ("failed", True),
            ("no_work", True),
        ],
    )
    def test_every_terminal_the_runner_can_emit_is_authoritative(
        self, terminal, expected_authoritative
    ):
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(VERDICT_LABEL, {"terminal": terminal, "reason": "x"})
        assert verdict.authoritative is expected_authoritative, (
            f"terminal={terminal!r} classified non-authoritatively — enrolment "
            "without terminal truth is the no-op this gate exists to refuse"
        )

    def test_a_summary_with_no_terminal_is_the_kill_control(self):
        """The control that keeps the gate above from passing vacuously: if a
        terminal-less summary ALSO read authoritative, the four assertions above
        would prove nothing about the wrapper."""
        from app.utils.task_verdict import verdict_for

        verdict = verdict_for(VERDICT_LABEL, {"captured": 3000})
        assert not verdict.authoritative

    def test_the_summary_the_wrapper_returns_actually_carries_a_terminal(self):
        """Not "the classifier would like a terminal" — the wrapper's own return
        value has one. `SweepReport.to_dict` is the contract; assert against it."""
        from datetime import datetime, timezone

        from app.services.settlement_sweep_runner import SweepReport

        payload = SweepReport(
            sweep_id="kalshi-2026-08-26",
            source="kalshi",
            started_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
            budget=3000,
            dry_run=False,
        ).to_dict()
        assert "terminal" in payload and "reason" in payload


# ---------------------------------------------------------------------------
# G3 — the four zeros stay four
# ---------------------------------------------------------------------------

class TestG3FourZeros:
    def test_the_four_terminals_are_four_distinct_verdicts(self):
        from app.utils.task_verdict import verdict_for

        verdicts = {
            t: verdict_for(VERDICT_LABEL, {"terminal": t, "reason": "x"}).verdict
            for t in ("complete", "partial", "failed", "no_work")
        }
        assert verdicts["complete"] != verdicts["failed"]
        assert verdicts["partial"] != verdicts["complete"]
        assert verdicts["no_work"] != verdicts["complete"], (
            "a run that found nothing to do must not read the same as a run that "
            "drained the cohort"
        )

    def test_a_total_loss_never_reads_green(self):
        from app.utils.task_verdict import COMPLETE, verdict_for

        verdict = verdict_for(
            VERDICT_LABEL, {"terminal": "failed", "reason": "total_loss"}
        )
        assert verdict.verdict != COMPLETE

    def test_a_budget_capped_run_never_reads_green(self):
        from app.utils.task_verdict import COMPLETE, verdict_for

        verdict = verdict_for(
            VERDICT_LABEL, {"terminal": "partial", "reason": "1200 left"}
        )
        assert verdict.verdict != COMPLETE

    def test_the_wrapper_does_not_rewrite_the_terminal(self):
        """The runner decides the terminal. A wrapper that post-processes it —
        even to be helpful — re-opens the flattening this gate forbids."""
        from app.tasks import settlement_sweep

        source = inspect.getsource(settlement_sweep)
        for forbidden in ('"terminal"', "'terminal'", ".terminal ="):
            assert forbidden not in source, (
                f"the wrapper touches {forbidden} — the terminal is the runner's"
            )


# ---------------------------------------------------------------------------
# G4 — date-derived sweep id: re-running is the recovery
# ---------------------------------------------------------------------------

class TestG4Idempotency:
    def test_the_wrapper_passes_no_sweep_id(self):
        """`run_sweep` defaults to `default_sweep_id(now, source)` = the DATE.
        Passing anything at all — including a uuid, a task id, or a timestamp —
        makes each nightly run a fresh population and deletes resumability."""
        from app.tasks import settlement_sweep

        source = inspect.getsource(settlement_sweep)
        assert "sweep_id" not in source, (
            "the wrapper names sweep_id — the only correct value is the one it "
            "does not pass"
        )

    def test_the_default_sweep_id_is_stable_within_a_day(self):
        from datetime import datetime, timezone

        from app.utils.settlement_sweep_query import default_sweep_id

        morning = datetime(2026, 8, 26, 3, 0, tzinfo=timezone.utc)
        evening = datetime(2026, 8, 26, 23, 59, tzinfo=timezone.utc)
        next_day = datetime(2026, 8, 27, 3, 0, tzinfo=timezone.utc)

        assert default_sweep_id(morning, "kalshi") == default_sweep_id(evening, "kalshi")
        assert default_sweep_id(next_day, "kalshi") != default_sweep_id(morning, "kalshi")

    def test_a_second_fire_on_the_same_night_resumes_rather_than_re_probes(self):
        """The beat fires once a night, but a retry, a redeploy or an operator
        re-run must land on the same id. Proven through the wrapper's own call,
        not through the runner's docstring."""
        import asyncio
        from datetime import datetime, timezone

        from app.tasks import settlement_sweep

        seen = []

        async def fake_run_sweep(session, **kwargs):
            seen.append(kwargs)

            class _R:
                def to_dict(self):
                    return {"terminal": "no_work", "reason": "stub"}

            return _R()

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        asyncio.run(
            _drive(settlement_sweep, fake_run_sweep, _Session)
        )
        asyncio.run(
            _drive(settlement_sweep, fake_run_sweep, _Session)
        )

        assert len(seen) == 2
        for kwargs in seen:
            assert kwargs.get("sweep_id") is None, (
                f"the wrapper pinned a sweep_id: {kwargs.get('sweep_id')!r}"
            )
        # And the date-derived id both runs land on is the same one.
        now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
        from app.utils.settlement_sweep_query import default_sweep_id

        assert default_sweep_id(now, "kalshi") == default_sweep_id(now, "kalshi")


async def _drive(module, fake_run_sweep, session_cls):
    """Call the wrapper with the runner and the session both stubbed."""
    import contextlib

    real_run = module.run_sweep
    real_session = module.get_task_session

    @contextlib.asynccontextmanager
    async def fake_session():
        yield session_cls()

    module.run_sweep = fake_run_sweep
    module.get_task_session = fake_session
    try:
        return await module._run_settlement_sweep(budget=3000, concurrency=4)
    finally:
        module.run_sweep = real_run
        module.get_task_session = real_session


# ---------------------------------------------------------------------------
# G5 — no new sweep logic, and is_winner is untouched
# ---------------------------------------------------------------------------

class TestG5NoNewLogic:
    def test_the_wrapper_calls_the_certified_runner(self):
        from app.tasks import settlement_sweep
        from app.services import settlement_sweep_runner

        assert settlement_sweep.run_sweep is settlement_sweep_runner.run_sweep

    def test_the_wrapper_writes_no_sql_and_no_is_winner(self):
        """The sweep never writes `is_winner` — it writes `settlement_captures`.
        A wrapper that reached for the winner column would turn a capture rail
        into a grader, which is a different authority (ruling: the resolution
        authority ladder)."""
        from app.tasks import settlement_sweep

        source = inspect.getsource(settlement_sweep)
        for forbidden in ("is_winner", "UPDATE ", "INSERT ", "text("):
            assert forbidden not in source, (
                f"the wrapper contains {forbidden!r} — it must add no sweep logic"
            )

    def test_the_wrapper_is_small(self):
        """A size bound is a crude proxy and it is deliberate: 'no new sweep
        logic' is the acceptance, and the cheapest way to violate it is to grow
        the wrapper until nobody re-reads it."""
        from app.tasks import settlement_sweep

        body = inspect.getsource(settlement_sweep._run_settlement_sweep)
        code_lines = [
            ln for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        assert len(code_lines) < 30, f"wrapper grew to {len(code_lines)} lines"


# ---------------------------------------------------------------------------
# G6 — the deadline is inside the soft limit
# ---------------------------------------------------------------------------

class TestG6DeadlineInsideTheSoftLimit:
    def test_the_task_declares_both_limits(self):
        from app.tasks import run_settlement_sweep

        assert run_settlement_sweep.soft_time_limit, (
            "no soft_time_limit — the Celery default hard limit runs no exit "
            "path, so a long sweep is SIGKILLed with its progress unbanked"
        )
        assert run_settlement_sweep.time_limit > run_settlement_sweep.soft_time_limit

    def test_the_in_task_deadline_is_strictly_inside_the_soft_limit(self):
        """`run_sweep(deadline_s=...)` bounds the probe phase. If it were >= the
        soft limit the deadline would never bind and the sweep would die at the
        limit instead of returning a resumable `partial`."""
        from app.tasks import run_settlement_sweep
        from app.tasks.settlement_sweep import SWEEP_DEADLINE_S

        assert SWEEP_DEADLINE_S < run_settlement_sweep.soft_time_limit
        margin = run_settlement_sweep.soft_time_limit - SWEEP_DEADLINE_S
        assert margin >= 60, (
            f"only {margin}s between the deadline and the soft limit — the "
            "report still has to be built and returned after the probes stop"
        )

    def test_the_deadline_reaches_the_wrapper(self):
        """A constant nothing passes is a comment. Assert it arrives."""
        import asyncio

        from app.tasks import settlement_sweep
        from app.tasks.settlement_sweep import SWEEP_DEADLINE_S

        seen = []

        async def fake_run_sweep(session, **kwargs):
            seen.append(kwargs)

            class _R:
                def to_dict(self):
                    return {"terminal": "no_work", "reason": "stub"}

            return _R()

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        asyncio.run(_drive(settlement_sweep, fake_run_sweep, _Session))
        assert seen[0]["deadline_s"] == SWEEP_DEADLINE_S


# ---------------------------------------------------------------------------
# G7 — background, declared, not defaulted
# ---------------------------------------------------------------------------

class TestG7Routing:
    def test_the_beat_declares_the_background_queue(self):
        """Beat `options["queue"]` overrides `task_routes` at dispatch, so the
        two can disagree silently. Both arms are asserted."""
        assert _entry()["options"]["queue"] == "background"

    def test_it_is_declared_in_keep_on_background(self):
        from app.tasks import _HEAVY_KEEP_ON_BACKGROUND

        assert TASK_NAME in _HEAVY_KEEP_ON_BACKGROUND, (
            "a multi-minute network sweep that is not declared here can be "
            "moved onto `heavy` by the next person who reads the routing block "
            "and sees no objection"
        )

    def test_it_is_not_on_heavy(self):
        from app.tasks import HEAVY_TASKS, celery_app as app

        assert TASK_NAME not in HEAVY_TASKS
        assert app.conf.task_routes.get(TASK_NAME, {}).get("queue") != "heavy"


# ---------------------------------------------------------------------------
# G8 — the fire minute is clear ON ITS OWN QUEUE, measured over the FULL
#      assembled schedule
# ---------------------------------------------------------------------------
#
# 🔴 THIS SECTION EXISTS BECAUSE OF A BLOCK. CERT-418 [P1] rejected the first
# choice of fire minute. The beat was placed at `crontab(minute=10, hour=10)`
# under a comment that read ":10 is the only clear minute in that hour". That
# sentence was true of the entries the author had read — hour 10's *daily*
# beats, which sit at :00 and :05 — and false of the schedule that actually
# runs. Four further background beats fire at :10 every hour of every day:
# `precompute-discover-candidate-base` (every even minute), `warm-event-concepts`
# (every 5), `run_freshness_watchdog` and `update_max_movement` (every 10). The
# sweep was therefore timed to land on top of the exact cache and freshness work
# the offset was chosen to protect.
#
# The defect is not the minute. The defect is that the enumeration was done by
# reading a file for entries that *looked* daily, and nothing executable
# checked it. So the remedy is an enumeration over `conf.beat_schedule` as
# assembled, resolving each entry's queue the way Celery resolves it, and
# admitting every cadence — daily, hourly, sub-hourly and interval.
#
# Two honesty constraints this section is written to respect:
#
#   1. **"Zero co-fires" is not achievable and must not be claimed.** Three
#      background beats are pure intervals (10 s, 20 s, 180 s). They fire during
#      every minute of every hour and no choice of minute avoids them. They are
#      named in `BACKGROUND_INTERVAL_FLOOR` and asserted not to have grown,
#      rather than quietly filtered out — a filter is how the next unavoidable
#      thing becomes invisible.
#   2. **The gate is clock-independent** (gotcha #44). It reads the crontab's
#      own `hour`/`minute` sets. Nothing here constructs "now", so it cannot
#      pass or fail depending on when CI runs.

#: The background beats that fire on a fixed period rather than a wall-clock
#: minute. Every minute of the day carries all of them; the sweep shares its
#: slot with them wherever it is placed. Asserted as an exact set so that a NEW
#: interval beat arriving on `background` goes red here and has to be argued
#: about, instead of being absorbed into "unavoidable anyway".
#:
#: 🔴 THE GUARD FIRED AS DESIGNED AT INTEGRATION (INT-139, 2026-08-27). It went
#: red on the merged tree because the ux-122 fold — certified separately, merged
#: an hour earlier — added `sync-tournament-results` at every 180 s. That is the
#: fourth interval beat this set exists to catch, so it is ARGUED here rather
#: than absorbed: 180 s is the same period as the incumbent
#: `refresh-open-commentary`, it is two ESPN scoreboard reads (bounded, no
#: third-party call inside a GET), and it is a continuous floor by the same
#: reasoning that admits the other three. The `period <= 180.0` assertion below
#: is what keeps that from being a blanket welcome: a slower beat is not a floor
#: and would still have to be reasoned about as a co-fire.
#:
#: 🔴 THE GUARD FIRED AS DESIGNED AGAIN (LAT-P109, 2026-08-28) on the FIFTH
#: interval beat, `flush-search-gin-pending-lists` at 120 s. ARGUED, not
#: absorbed, on three counts:
#:
#:   1. **What it costs the shared slot is bounded and small.** Seven
#:      `gin_clean_pending_list()` calls, each merging roughly one beat-period's
#:      accumulation (~100 index pages at the measured refill rates). No table
#:      scan, no third-party call, no application work — and the merge itself is
#:      work an inserting backend would otherwise do at the 4 MB limit, so this
#:      moves the cost rather than adding it.
#:   2. **It cannot pile up behind THIS sweep.** The entry carries
#:      `expires: 110`, under its own 120 s period, so the ~7 minutes the sweep
#:      holds the slot drop their stale fires instead of queueing three or four
#:      flushes to run back to back the moment the sweep releases. Exactly one
#:      runs after it. The cost of that window is that the pending lists grow
#:      unflushed for seven minutes once a night, which is the state every minute
#:      of every day was in before this beat existed.
#:   3. **120 s is inside the floor's own rule**, not an exception to it — see
#:      the `period <= 180.0` assertion below.
#:
#: Why `background` and not elsewhere: `realtime` carries the 2-minute live
#: price poll and maintenance must not contend with it; `heavy` is the
#: calibration/precompute family, whose 25-minute passes would make a 2-minute
#: beat meaningless. The full measurement is
#: `docs/audits/latency/lat-p109-the-gin-pending-list-sawtooth.md` (#2255).
BACKGROUND_INTERVAL_FLOOR = frozenset(
    {
        "flush-search-gin-pending-lists",
        "refresh-open-commentary",
        "sync-tournament-results",
        "warm-search-head",
        "warm-typeahead",
    }
)

#: Discrete background crontab fires inside the sweep's own run window, measured
#: over `[minute, minute + ceil(SWEEP_DEADLINE_S / 60)]`. RE-DERIVED by running
#: the census below over the assembled schedule, never adjusted by a delta
#: (#1910). Asserted as a CEILING rather than an equality — a reduction is not a
#: regression, and hour 10 is shared with lanes that have no reason to know this
#: constant exists.
#:
#: 🔴 RE-DERIVED AT INTEGRATION (INT-139, 2026-08-27): 12 -> **13**. The ux-122
#: fold added `refresh-registered-tournament-prices` (`*/10`), which puts one
#: extra fire in this window. Re-derived by RUNNING the census over the merged
#: schedule, not by incrementing — the guard's own failure message asks for
#: exactly that, and the alternative it offers (move the sweep) was evaluated
#: and REJECTED on the numbers rather than waved off:
#:
#:   Full enumeration over the MERGED hour-10 schedule — 22 of 60 minutes carry
#:   zero co-fire at the instant, and ranked by 13-minute window load the top
#:   four are :31 -> 13, :33 -> 18, :41 -> 18, :43 -> 19. **:31 is still rank 1
#:   of 22**, and by a wider margin than before. CERT-419's placement argument
#:   survives its own inputs changing; only the declared number moved.
#:
#: The 13, by beat: 7x `precompute-discover-candidate-base` (one per even
#: minute, which the floor argument above already covers), 2x
#: `warm-event-concepts`, and one each of `discover-new-events`,
#: `refresh-registered-tournament-prices`, `run-freshness-watchdog`,
#: `update-max-movement`.
#: 🔴 RE-DERIVED AGAIN (Q426, 2026-08-28): 13 -> **14**. `link-tournament-matchups`
#: (`*/10`, background) puts one extra fire in this window, at 10:40.
#: RE-DERIVED BY RUNNING THE CENSUS over the assembled schedule, three ways, not
#: by incrementing (#1910): baseline with the beat removed = **13**, with `*/10`
#: = **14**, with `*/5` = **15**.
#:
#: The guard's alternative — a cheaper cadence — was taken rather than waved
#: off, and it is why this reads 14 and not 15. The beat was authored at `*/5`;
#: the census said that costs the sweep two fires inside its own run window
#: instead of one, and five minutes of latency buys a reader nothing (main-draw
#: match markets list hours ahead of the match). So the cadence moved to `*/10`
#: BECAUSE of this number, which is the entire point of asserting it.
#:
#: The other alternative the failure message offers — moving the sweep — was NOT
#: evaluated and is not this queue's to take: :31 was chosen by CERT-419 on a
#: full enumeration and re-confirmed at INT-139, and one lane trading somebody
#: else's placement for its own beat is how that argument gets lost.
#:
#: 🔴 RE-DERIVED AGAIN (LAT-P137, 2026-08-30): 14 -> **16**. `warm-futures-categories`
#: (`*/5`, background) puts TWO extra fires in this window, at 10:35 and 10:40.
#: RE-DERIVED BY RUNNING THE CENSUS over the assembled schedule, three ways, not
#: by incrementing (#1910): baseline with the beat removed = **14**, with `*/10`
#: = **15**, with `*/5` = **16**. The 16, by beat: 7x
#: `precompute-discover-candidate-base`, 2x `warm-event-concepts`, 2x
#: `warm-futures-categories`, and one each of `discover-new-events`,
#: `link-tournament-matchups`, `refresh-registered-tournament-prices`,
#: `run-freshness-watchdog`, `update-max-movement`.
#:
#: 🔴 THE CHEAPER CADENCE WAS EVALUATED — Q426's move, above, is the precedent —
#: AND REFUSED, WITH THE ARITHMETIC. This period is not a taste: it is
#: `stale_serve_ceiling_seconds() // (MISSED_DELIVERY_ALLOWANCE + 1)` over the
#: census tier's own 1,500 s mirror ceiling, and the beat spells `*/N`, so N must
#: divide 60. 1500/5 = 300 s is the ONLY whole-minute period that divides an hour
#: under an allowance above one: 1500/2 = 750 s, /3 = 500 s and /6 = 250 s are all
#: fractional minutes. `*/10` is therefore not a cheaper spelling of the same
#: contract — it is an allowance of one missed delivery, on the queue LAT-P112
#: measured delivering p50 138-152 s against a declared 120 s. Q426 could move
#: because five minutes of latency bought its reader nothing; here the cadence IS
#: the coverage.
#:
#: COST OF THE TWO FIRES, stated rather than waved: the added task is one census
#: build, measured 1.37-1.59 s, so it takes ~2.8 s of one slot inside a 780 s
#: window on a two-slot queue — ~0.36 % of one slot for the window, against a
#: sweep whose own deadline is the 780. If a later queue needs this window back,
#: the lever is this beat's allowance, and it is one constant with a test on it.
#: 🔴 **RE-DERIVED at lane1/057 STEP 0 (2026-09-02): 16 -> 17.** The tennis ESPN
#: anchor (`sync-tennis-from-espn`) joined the window with **one** fire, the same
#: contribution as `link-tournament-matchups` and
#: `refresh-registered-tournament-prices` — the two sibling tournament-upkeep
#: beats it deliberately shares a `*/10` cadence with. Obtained by running the
#: census in `test_the_run_window_does_not_sit_under_a_growing_pile` over the
#: assembled schedule and printing the total, never by adding one (#1910):
#:
#:     10:31 +13m  TOTAL 17
#:       7  precompute-discover-candidate-base
#:       2  warm-event-concepts        2  warm-futures-categories
#:       1  discover-new-events        1  link-tournament-matchups
#:       1  refresh-registered-tournament-prices
#:       1  run-freshness-watchdog     1  sync-tennis-from-espn
#:       1  update-max-movement
#:
#: COST OF THE ONE FIRE: two ESPN scoreboard fetches (~1.3 MB each, measured
#: 1.5-3 s together) plus one indexed query bounded to the tournament buckets on
#: today's board — 194 rows for the US Open, not the 2,904 tennis rows in the
#: window. ~3 s of one slot inside a 780 s window on a two-slot queue.
#:
#: It is a CRONTAB precisely so it stays here, as a countable co-fire, rather
#: than in `BACKGROUND_INTERVAL_FLOOR` where a 180 s interval would have put it.
SWEEP_WINDOW_COFIRE_CEILING = 17


def _effective_queue(entry):
    """The queue this beat entry actually dispatches to.

    Three layers in the order Celery applies them: the entry's own
    ``options["queue"]``, then ``task_routes``, then ``task_default_queue``.
    Reading only the first layer is how 45 beats came to sit on `background`
    without anyone choosing it — see
    `test_the_background_queue_carries_103_beats_and_45_are_fall_through`.
    """
    conf = celery_app.conf
    return (
        (entry.get("options") or {}).get("queue")
        or (conf.task_routes.get(entry.get("task")) or {}).get("queue")
        or conf.task_default_queue
    )


def _is_crontab(schedule):
    return hasattr(schedule, "hour") and hasattr(schedule, "minute")


def _interval_seconds(schedule):
    """Period of a non-crontab schedule, in seconds.

    Celery accepts a bare number, a ``timedelta``, or a ``schedule`` object
    wrapping one; all three appear in this config's history.
    """
    run_every = getattr(schedule, "run_every", schedule)
    total = getattr(run_every, "total_seconds", None)
    return total() if callable(total) else float(run_every)


def _background_crontab_beats():
    """``(name, hours, minutes)`` for every crontab beat on `background`."""
    out = []
    for name, entry in celery_app.conf.beat_schedule.items():
        schedule = entry.get("schedule")
        if _effective_queue(entry) == "background" and _is_crontab(schedule):
            out.append(
                (name, {int(h) for h in schedule.hour}, {int(m) for m in schedule.minute})
            )
    return out


def _background_interval_beats():
    """``(name, period_s)`` for every non-crontab beat on `background`."""
    return [
        (name, _interval_seconds(entry.get("schedule")))
        for name, entry in celery_app.conf.beat_schedule.items()
        if _effective_queue(entry) == "background"
        and not _is_crontab(entry.get("schedule"))
    ]


def _background_cofires_at(hour, minute):
    """Background crontab beats — other than the sweep — that CAN fire at
    ``hour:minute``.

    Day-of-week and day-of-month are deliberately ignored: a beat that collides
    only on Mondays is still a collision, and the conservative reading is the
    one that keeps the gate honest.
    """
    return sorted(
        name
        for name, hours, minutes in _background_crontab_beats()
        if name != BEAT_KEY and hour in hours and minute in minutes
    )


class TestG8TheFireMinuteIsClearOnItsOwnQueue:
    def test_no_other_background_beat_fires_at_the_sweeps_minute(self):
        """THE gate CERT-418 asked for. Enumerated, not read off a comment."""
        schedule = _entry()["schedule"]
        (hour,) = set(schedule.hour)
        (minute,) = set(schedule.minute)

        cofires = _background_cofires_at(hour, minute)
        assert cofires == [], (
            f"{hour:02d}:{minute:02d} UTC is not clear — {len(cofires)} other "
            f"background beat(s) fire on it: {cofires}. `background` runs about "
            "one effective slot and this sweep holds it for ~7 minutes (780 s "
            "bounded), so a co-fire here queues behind the sweep. Pick a minute "
            "with no entry in this list; the enumeration is over the assembled "
            "schedule, so hourly and sub-hourly cadences count."
        )

    def test_a_daily_only_enumeration_would_have_called_1010_clear(self):
        """The defect itself, kept executable.

        This is the control that stops the gate above from being decorative. If
        someone reimplements the enumeration and it silently reverts to reading
        daily entries only, the first assertion here still passes — and the
        second one fails, because a daily-only reading of 10:10 genuinely is
        empty. That emptiness is exactly what the original comment saw.
        """
        daily_only_at_1010 = [
            name
            for name, hours, minutes in _background_crontab_beats()
            if name != BEAT_KEY
            and len(hours) == 1
            and len(minutes) == 1
            and hours == {10}
            and minutes == {10}
        ]
        assert daily_only_at_1010 == [], (
            "premise moved: a daily beat now sits at 10:10, so this test no "
            "longer reproduces the reading that produced the BLOCK"
        )

        full = set(_background_cofires_at(10, 10))
        assert full >= {
            "precompute-discover-candidate-base",
            "warm-event-concepts",
            "run-freshness-watchdog",
            "update-max-movement",
        }, (
            "the enumeration no longer sees sub-hourly cadences at 10:10 — it "
            f"returned {sorted(full)}. That is the CERT-418 defect back: an "
            "enumerator blind to */2, */5 and */10 entries reports any minute "
            "as clear."
        )

    def test_the_unavoidable_background_floor_is_named_and_has_not_grown(self):
        """No minute avoids an interval beat, so they are declared, not filtered.

        A fourth interval beat on `background` means the floor the sweep shares
        its slot with got heavier. That is a real cost and it should be argued
        in a report, not discovered later inside a filter nobody re-reads.
        """
        floor = dict(_background_interval_beats())
        assert set(floor) == BACKGROUND_INTERVAL_FLOOR, (
            f"the background interval floor moved: {sorted(floor)} vs "
            f"{sorted(BACKGROUND_INTERVAL_FLOOR)}"
        )
        assert all(period <= 180.0 for period in floor.values()), (
            f"an interval beat slower than 180 s is no longer a continuous "
            f"floor and should be reasoned about as a co-fire: {floor}"
        )

    def test_the_run_window_does_not_sit_under_a_growing_pile(self):
        """The minute being clear is necessary, not sufficient.

        The sweep holds its slot for the whole deadline, so what matters
        operationally is the window, not the instant. Asserted as a ceiling: it
        catches the pile growing, and stays quiet when it shrinks.
        """
        import math

        from app.tasks.settlement_sweep import SWEEP_DEADLINE_S

        schedule = _entry()["schedule"]
        (hour,) = set(schedule.hour)
        (minute,) = set(schedule.minute)
        span = math.ceil(SWEEP_DEADLINE_S / 60)

        total = 0
        for offset in range(span + 1):
            absolute = minute + offset
            total += len(_background_cofires_at((hour + absolute // 60) % 24, absolute % 60))

        assert total <= SWEEP_WINDOW_COFIRE_CEILING, (
            f"{total} background crontab fires inside {hour:02d}:{minute:02d}"
            f"+{span}m, over a declared ceiling of {SWEEP_WINDOW_COFIRE_CEILING}. "
            "Re-derive the ceiling by running this census and stating the new "
            "number — do not increment it (#1910) — or move the sweep."
        )
