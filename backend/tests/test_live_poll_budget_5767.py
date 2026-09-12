"""The live poll finishes on its own terms, stalest first (#5767).

## the ship

A live match page shows a prediction-market price tens of minutes old. Measured
on production 2026-09-12 22:12:48Z, release 4473 (`c3900f68`), live events only:
the average event-level source stamp was **41.7 min (kalshi, 76 events)** and
**32.8 min (polymarket, 29 events)** — on a beat that runs every **two
minutes**. Most of the population was not being reached at all.

## the defect these arms are pointed at

`#5682` stopped one deadlock costing the whole beat, and by surviving it
uncovered the next thing: the pass now runs the WHOLE population, and it does
not fit. `worker-realtime.1`, 22:11:00Z:

    ERROR/MainProcess  Hard time limit (300s) exceeded for
                       app.tasks.poll_live_prediction_markets[323af530-...]

`poll_live_prediction_markets` declares no limit of its own and takes the global
`task_time_limit: 300`. Two consequences, both measured on the shipped sha:

* **the fork is SIGKILLed, so it writes no terminal at all.** `successes_24h`
  30, `failures_24h` 209, `consecutive_failures` 270, `health critical`,
  `last_duration_ms` 19489 — every one frozen at its pre-deploy value while the
  poll was in fact running and committing (726 outcome rows at 22:00Z, 2044 at
  22:05Z). `hard_kills_24h` read 0 throughout. Gotcha #53's silent form: not "it
  returned but did nothing", but "it never returned and nothing said so".
* **the same tail starves every beat.** The population was loaded in one query
  with no ordering, so the rows the kill lands on are the same rows each time.

## what the arms below pin

1. the budget is sized off the bound that is ENFORCED (the 300 s kill), not off
   the 120 s cadence, which enforces nothing — and the mirror of that bound in
   the task module is asserted equal to the celery config, because two records
   of one capability that may drift are how a margin becomes negative;
2. a beat that runs out of clock STOPS and SAYS SO — `terminal: partial` plus
   what stopping cost, never a raise and never a silent kill;
3. the venue-fetch stages cannot spend the stamping stage's share. This is the
   arm that matters most to the reader: the fetch loops refresh
   `futures_outcomes`, the blend loop writes `win_probability_sources`, and a
   budget spent entirely on fetches would leave the rows fresh and the PAGE
   stale — #5682's exact symptom arriving by a second road;
4. the population is ordered stalest-first, so a truncated pass truncates the
   freshest end.
"""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.tasks import prediction_market_matching as pmm

from tests.test_live_poll_commit_boundary_5682 import (  # noqa: E402
    _KalshiService,
    _Session,
    _kalshi_beat,
    _leg,
    _run,
)

# `pytest.ini` runs asyncio in AUTO mode, so the coroutines below need no mark.


def _service(journal, n: int = 3) -> _KalshiService:
    return _KalshiService(
        {f"KXNFLGAME-EVT{i}": [_leg(f"KXNFLGAME-EVT{i}-LAR", f"KXNFLGAME-EVT{i}")]
         for i in range(1, n + 1)},
        journal,
    )


# --------------------------------------------------------------------------
# 1. the budget is sized off the bound that kills the beat
# --------------------------------------------------------------------------


class TestTheBudgetIsSizedOffTheEnforcedBound:
    def test_the_mirrored_hard_kill_is_the_one_celery_enforces(self):
        """Two records of one capability, asserted equal rather than trusted.

        If somebody raises `task_time_limit` and the poll keeps budgeting
        against 300, the beat simply stops early forever and nobody notices;
        if somebody LOWERS it, the margin goes negative and the kill comes
        back — silently, because a SIGKILL writes nothing."""
        from app.tasks import celery_app

        enforced = celery_app.conf.task_time_limit
        assert pmm._LIVE_POLL_HARD_KILL_SECONDS == enforced, (
            "the poll's mirror of the hard kill has drifted from the config "
            f"that enforces it: {pmm._LIVE_POLL_HARD_KILL_SECONDS} vs {enforced}"
        )

    def test_the_poll_still_takes_the_global_limit_and_not_its_own(self):
        """The mirror above is only the right number while this holds.

        Several neighbours (`poll_kalshi_markets`, and the tasks at
        `app/tasks/__init__.py:1283/1311/1340`) declare their own
        `soft_time_limit`/`time_limit`; this one does not, so the global applies.
        The day somebody gives it one, the mirror is measuring the wrong bound
        and this arm says so instead of the margin quietly going negative."""
        from app.tasks import celery_app

        task = celery_app.tasks["app.tasks.poll_live_prediction_markets"]
        assert task.time_limit is None, (
            "the poll now declares its own hard limit "
            f"({task.time_limit}s); the budget must be sized off THAT"
        )

    def test_the_budget_leaves_room_to_finish_and_report(self):
        margin = pmm._LIVE_POLL_HARD_KILL_SECONDS - pmm._LIVE_POLL_BUDGET_SECONDS
        assert margin == pmm._LIVE_POLL_BUDGET_MARGIN_SECONDS, (
            "the budget is no longer derived from the bound it is protecting "
            "against — re-typing it is how a margin goes negative in silence"
        )
        assert margin >= 30, (
            f"only {margin}s between the budget and the kill — the final commit, "
            "the terminal and the log line all have to happen inside it"
        )

    def test_the_fetch_share_leaves_the_stamping_stages_something(self):
        assert 0 < pmm._LIVE_POLL_FETCH_BUDGET_SHARE < 1


# --------------------------------------------------------------------------
# 2. out of clock: stop, and say what it cost
# --------------------------------------------------------------------------


class TestABeatOutOfClockReportsItself:
    async def test_it_stops_before_the_first_fetch_and_returns_partial(
        self, monkeypatch
    ):
        """Budget 0 — the whole pass is out of time before it starts.

        No raise, no kill: the beat returns, and the return says `partial` and
        names what it skipped. Against the pre-repair function this arm fails
        on `terminal == "complete"` with three fetches in the journal."""
        monkeypatch.setattr(pmm, "_LIVE_POLL_BUDGET_SECONDS", 0)
        journal = []
        beat = _kalshi_beat(3)
        session = _Session([beat, beat], journal=journal)

        stats = await _run(monkeypatch, session, kalshi=_service(journal))

        assert stats["terminal"] == "partial"
        assert stats["budget_stops"]["kalshi_fetch"] == 3, stats["budget_stops"]
        assert [t for kind, t in journal if kind == "fetch"] == [], (
            "the beat fetched after its clock ran out"
        )
        assert stats["budget_seconds"] == 0
        assert "elapsed_seconds" in stats

    async def test_a_stopped_beat_is_never_green(self, monkeypatch):
        """`partial` even with zero recoveries — a short beat is not a clean one."""
        monkeypatch.setattr(pmm, "_LIVE_POLL_BUDGET_SECONDS", 0)
        journal = []
        beat = _kalshi_beat(2)
        session = _Session([beat, beat], journal=journal)

        stats = await _run(monkeypatch, session, kalshi=_service(journal, 2))

        assert stats["session_recoveries"] == 0
        assert stats["terminal"] == "partial"

    async def test_every_stage_reports_its_own_cost(self, monkeypatch):
        """The four loops are four line items, not one boolean.

        A beat that stopped 40 markets short and one that stopped 2 short are
        different facts, and `partial` alone cannot tell them apart."""
        monkeypatch.setattr(pmm, "_LIVE_POLL_BUDGET_SECONDS", 0)
        journal = []
        beat = _kalshi_beat(3)
        session = _Session([beat, beat], journal=journal)

        stats = await _run(monkeypatch, session, kalshi=_service(journal))

        assert set(stats["budget_stops"]) == {
            "kalshi_fetch", "blend_stamp", "pregame_mark",
        }, stats["budget_stops"]
        assert all(v > 0 for v in stats["budget_stops"].values())

    async def test_a_beat_that_fits_reports_complete_and_no_stops(self, monkeypatch):
        """The control. Without it every arm above passes on a broken budget."""
        journal = []
        beat = _kalshi_beat(3)
        session = _Session([beat, beat], journal=journal)

        stats = await _run(monkeypatch, session, kalshi=_service(journal))

        assert stats["terminal"] == "complete"
        assert "budget_stops" not in stats
        assert len([t for kind, t in journal if kind == "fetch"]) == 3


# --------------------------------------------------------------------------
# 3. the fetch stages cannot eat the stamp stage's share
# --------------------------------------------------------------------------


class TestTheStampingStageKeepsItsShare:
    async def test_the_fetches_stop_and_the_event_stamp_still_happens(
        self, monkeypatch
    ):
        """Share 0 — the fetch loops are out of time, the beat is not.

        The reader's number lives in `win_probability_sources`, written by the
        blend loop. If the fetch loops could spend the whole budget, every beat
        would refresh `futures_outcomes` and never stamp the event: rows fresh,
        page stale, which is the #5682 symptom this must not recreate."""
        monkeypatch.setattr(pmm, "_LIVE_POLL_FETCH_BUDGET_SHARE", 0.0)
        journal = []
        beat = _kalshi_beat(3)
        stamped: list[int] = []

        from app.utils.live_blend import BlendReading

        def _primary(group):
            return group[0] if group else None

        def _compute(group, home, away):
            entry = group[0]
            outcome = entry.outcomes[0] if entry.outcomes else None
            if outcome is None:
                return None
            return BlendReading(
                home_probability=0.61,
                market=entry.market,
                outcome=outcome,
                yes_probability=0.61,
                devigged=False,
                eligibility=None,
            )

        async def _inversion(session_, event_id, home_prob, source):
            return home_prob

        async def _snapshot(session_, **kwargs):
            stamped.append(kwargs["event_id"])
            return object(), True

        monkeypatch.setattr(
            "app.tasks.snapshots._create_or_update_win_prob_snapshot", _snapshot
        )
        monkeypatch.setattr(pmm, "_check_and_fix_inversion", _inversion)

        session = _Session([beat, beat], journal=journal)
        stats = await _run(
            monkeypatch,
            session,
            kalshi=_service(journal),
            blend={
                "_select_primary_market": _primary,
                "_compute_source_home_probability": _compute,
            },
        )

        assert [t for kind, t in journal if kind == "fetch"] == [], (
            "the fetch loop ran past a deadline it had already passed"
        )
        assert stamped == [101, 102, 103], (
            f"the stamping stage was starved by the fetch stages: {stamped}"
        )
        assert stats["budget_stops"] == {"kalshi_fetch": 3}, stats["budget_stops"]
        assert stats["terminal"] == "partial"


# --------------------------------------------------------------------------
# 4. stalest first
# --------------------------------------------------------------------------


class TestThePopulationIsOrderedStalestFirst:
    async def test_the_population_query_orders_on_the_event_stamp(self, monkeypatch):
        """The ordering is asserted on the SQL the session is handed.

        Not on the source text, and not on a hand-ordered fake: the fake cannot
        sort, so the only honest place to read this is the statement itself."""
        captured: dict = {}
        journal = []
        beat = _kalshi_beat(2)

        def _capture(kind, n, stmt):
            if kind == "population" and "sql" not in captured:
                captured["sql"] = str(
                    stmt.compile(
                        dialect=postgresql.dialect(),
                        compile_kwargs={"literal_binds": True},
                    )
                )
            return None

        session = _Session([beat, beat], journal=journal, on_execute=_capture)
        await _run(monkeypatch, session, kalshi=_service(journal, 2))

        sql = " ".join(captured["sql"].split())
        assert "ORDER BY" in sql, sql
        order_by = sql.split("ORDER BY", 1)[1]
        assert "jsonb_extract_path_text" in order_by, order_by
        assert "win_probability_sources" in order_by, order_by
        assert "updated_at" in order_by, order_by
        # NULLS FIRST is the half that matters most: a leg never written at all
        # is the stalest row there is, and Postgres would sort it LAST by
        # default on an ASC order — exactly backwards.
        assert "NULLS FIRST" in order_by.upper(), order_by

    async def test_the_sort_is_not_cast_to_a_timestamp(self, monkeypatch):
        """A malformed stamp must cost a tiebreak, never the whole query.

        Every writer of this key uses `datetime.now(timezone.utc).isoformat()`,
        so the text sorts chronologically; a cast would order identically and
        would raise the population read on one bad row."""
        captured: dict = {}
        journal = []
        beat = _kalshi_beat(2)

        def _capture(kind, n, stmt):
            if kind == "population" and "sql" not in captured:
                captured["sql"] = str(
                    stmt.compile(
                        dialect=postgresql.dialect(),
                        compile_kwargs={"literal_binds": True},
                    )
                )
            return None

        session = _Session([beat, beat], journal=journal, on_execute=_capture)
        await _run(monkeypatch, session, kalshi=_service(journal, 2))

        order_by = " ".join(captured["sql"].split()).split("ORDER BY", 1)[1]
        assert "CAST" not in order_by.upper(), order_by
