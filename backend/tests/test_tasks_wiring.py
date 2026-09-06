"""Smoke tests for tasks/ package wiring.

Verifies that:
1. All task modules import without errors
2. Every beat schedule entry references a registered task
3. All re-exported symbols are accessible from `app.tasks`
4. Task names match the expected "app.tasks.*" pattern
"""

import pytest

from app.tasks import celery_app


class TestBeatScheduleWiring:
    """Every beat schedule entry must reference a registered Celery task."""

    def test_all_beat_entries_reference_registered_tasks(self):
        registered = set(celery_app.tasks.keys())
        for schedule_name, entry in celery_app.conf.beat_schedule.items():
            task_name = entry["task"]
            assert task_name in registered, (
                f"Beat schedule entry '{schedule_name}' references "
                f"unregistered task '{task_name}'"
            )

    def test_all_task_names_use_pinned_prefix(self):
        """All our tasks must use 'app.tasks.*' naming for backward compat."""
        for schedule_name, entry in celery_app.conf.beat_schedule.items():
            task_name = entry["task"]
            assert task_name.startswith("app.tasks."), (
                f"Beat schedule entry '{schedule_name}' has task name "
                f"'{task_name}' — must start with 'app.tasks.'"
            )

    def test_llm_batch_tasks_have_soft_time_limit(self):
        """#966/#967: tasks that make a batch of sequential OpenAI calls routinely
        exceed the global 300s HARD task_time_limit. A hard-limit overrun is a
        SIGKILL — NOT a catchable exception — so _tracked_run records neither
        success nor failure (the task sits at no_data indefinitely). Each MUST
        carry a SOFT limit (which raises a catchable SoftTimeLimitExceeded) so
        overruns surface as failures and free the worker slot. Guard the whole
        class so it can't silently regress to the bare global limit.
        """
        llm_batch_tasks = [
            "app.tasks.enrich_discover_llm_metadata",  # #966
            "app.tasks.enrich_market_hooks",           # #967
            "app.tasks.enrich_cu_v2_profiles",         # the original working sibling
        ]
        for name in llm_batch_tasks:
            task = celery_app.tasks[name]
            assert task.soft_time_limit is not None, (
                f"{name} has no soft_time_limit — a >300s LLM batch will be "
                f"SIGKILLed (untracked no_data), not recorded as a failure"
            )
            assert task.time_limit is not None and task.time_limit > task.soft_time_limit, name
            # must clear the global 300s hard limit so the batch has room to finish
            assert task.soft_time_limit >= 300, name


class TestModuleImports:
    """Every task submodule must import without errors."""

    def test_import_config(self):
        from app.tasks.config import ESPN_SPORT_MAPPING, SPORT_MAX_DURATIONS
        assert isinstance(ESPN_SPORT_MAPPING, dict)
        assert isinstance(SPORT_MAX_DURATIONS, dict)

    def test_import_base(self):
        from app.tasks.base import run_async, get_task_session
        assert callable(run_async)

    def test_import_redis_state(self):
        from app.tasks.redis_state import should_poll_now, get_redis_client
        assert callable(should_poll_now)

    def test_import_odds_polling(self):
        from app.tasks.odds_polling import (
            _poll_all_odds,
            _poll_sport_odds,
            _create_or_update_snapshot,
            _create_or_update_win_prob_snapshot,
            _maybe_set_opening_odds,
        )
        assert callable(_poll_all_odds)

    def test_import_excitement_index(self):
        from app.tasks.excitement_index import (
            _compute_ei_for_event,
            _compute_ei_batch,
            _compute_ei_percentiles,
        )
        assert callable(_compute_ei_for_event)

    def test_import_futures(self):
        from app.tasks.futures import _poll_futures_odds, _infer_base_sport
        assert callable(_poll_futures_odds)
        assert callable(_infer_base_sport)

    def test_import_kalshi(self):
        from app.tasks.kalshi import _poll_kalshi_markets
        assert callable(_poll_kalshi_markets)

    def test_import_polymarket(self):
        from app.tasks.polymarket import _poll_polymarket_markets
        assert callable(_poll_polymarket_markets)

    def test_import_espn_sync(self):
        from app.tasks.espn_sync import (
            _enrich_events_metadata,
            _sync_espn_live_events,
            _backfill_team_logos,
        )
        assert callable(_enrich_events_metadata)

    def test_import_sports(self):
        from app.tasks.sports import _sync_sports, _discover_events
        assert callable(_sync_sports)

    def test_import_retention(self):
        from app.tasks.retention import (
            _collapse_snapshots_impl,
            _collapse_partition_sql,
        )
        assert callable(_collapse_snapshots_impl)
        assert callable(_collapse_partition_sql)

    def test_import_roster_sync(self):
        from app.tasks.roster_sync import _sync_rosters
        assert callable(_sync_rosters)


class TestReExports:
    """Symbols re-exported from app.tasks must be importable."""

    def test_celery_app(self):
        from app.tasks import celery_app
        assert celery_app.main == "bainluck"

    def test_infer_base_sport(self):
        from app.tasks import _infer_base_sport
        assert callable(_infer_base_sport)

    def test_create_or_update_win_prob_snapshot(self):
        from app.tasks import _create_or_update_win_prob_snapshot
        assert callable(_create_or_update_win_prob_snapshot)

    def test_task_functions(self):
        """All task wrapper functions should be importable from app.tasks."""
        from app.tasks import (
            sync_sports,
            discover_events,
            poll_all_odds,
            poll_sport_odds,
            compute_gei_for_event,
            compute_gei_batch,
            compute_gei_percentiles,
            poll_futures_odds,
            poll_kalshi_markets,
            poll_polymarket_markets,
            enrich_events_metadata,
            sync_espn_live_events,
            backfill_team_logos,
            collapse_snapshots,
            heartbeat,
            sync_rosters,
        )
        # All should be Celery task objects
        assert hasattr(sync_sports, 'delay')
        assert hasattr(collapse_snapshots, 'delay')
        assert hasattr(heartbeat, 'delay')
        assert hasattr(sync_rosters, 'delay')


class TestBeatScheduleCompleteness:
    """Catch missing or extra beat schedule entries."""

    EXPECTED_ENTRIES = {
        "poll-odds-adaptive",
        "poll-mlb-pregame",
        "sync-sports-hourly",
        "discover-new-events",
        "compute-gei-batch",
        "compute-gei-percentiles-hourly",
        "poll-futures-every-4h",
        "poll-kalshi",
        "check-kalshi-freshness-daily",
        "run-freshness-watchdog",
        "poll-polymarket-hourly",
        "refresh-stale-futures-prices-hourly",
        "enrich-events-hourly",
        "sync-espn-live",
        "sync-tennis-from-espn",
        "backfill-team-logos",
        "backfill-team-links",
        "match-prediction-markets",
        "matching-reconciliation",
        "poll-live-prediction-markets",  # restored: WS not yet deployed, REST polling needed for pre-game snapshots
        "heartbeat",
        "collapse-odds-snapshots-daily",
        "collapse-winprob-snapshots-daily",
        "collapse-futures-snapshots-daily",
        "sync-rosters-daily",
        "sync-mlb-win-probability",
        "compute-game-moments",
        "recategorize-other-daily",
        "backfill-canonical-keys-daily",
        "backfill-market-shapes",
        "audit-canonical-keys-daily",
        "audit-prediction-market-links-daily",
        "audit-related-futures-daily",
        "sync-statpal-schedules-nba",
        "sync-statpal-schedules-nhl",
        "sync-statpal-schedules-mlb",
        "sync-statpal-schedules-nfl",
        "sync-statpal-injuries",
        "sync-statpal-live-plays",
        "sync-statpal-livescores",
        # #2867 / D59 — the forward half of the tennis link (realtime, 10 min).
        "link-tennis-statpal-fixtures-10min",
        # #2867 / D50 — NFL shadow stamps, dark (background, hourly).
        "stamp-nfl-statpal-fixtures-hourly",
        # #2867 / D50 step 3 — NBA and NHL shadow stamps, dark (background,
        # hourly, :17 and :19 by minute census).
        "stamp-nba-statpal-fixtures-hourly",
        "stamp-nhl-statpal-fixtures-hourly",
        # #2867 / D50 step 5 — MLB shadow stamp, dark (background, hourly, :21
        # by the same census). The only one of the four whose season is in
        # progress, so the only one whose `livescores` read does work today.
        "stamp-mlb-statpal-fixtures-hourly",
        "sync-statpal-rosters-daily",
        "sync-statpal-team-stats-weekly",
        "sync-statpal-standings-daily",
        "mark-resolved-futures",
        "backfill-winners",
        # "sync-mm-bracket",  # Disabled — March Madness is over
        "matching-metrics-daily",
        "check-data-quality-daily",
        "turbo-collapse-futures",
        "turbo-collapse-odds",
        "transition-event-statuses",
        "track-statpal-usage",
        "snapshot-golf-leaderboard-daily",
        "enrich-market-hooks",
        "enrich-discover-llm-metadata",
        "enrich-snippet-angles",
        "enrich-cu-v2-profiles",
        "generate-discover-comparison-candidates",
        "evaluate-discover-with-llm-daily",
        "snapshot-discover-ground-truth-diagnostics-daily",
        "snapshot-discover-label-eval-run-daily",
        "snapshot-discover-candidate-pool-daily",
        "import-external-curator-ground-truth-daily",
        "check-ground-truth-health-daily",
        "capture-featured-markets-daily",
        "enrich-market-images",
        "enrich-tmdb-images",
        "backfill-image-dimensions",
        "merge-duplicate-events",
        "reconcile-unanchored-events",
        "merge-degenerate-combat-events",
        "canonicalize-entities-daily",
        "precompute-interestingness",
        "check-aggregation-quality",
        "check-tier1-coverage",
        "daily-digest",
        "backfill-polymarket-price-history",
        "backfill-kalshi-price-history",
        "kalshi-cliff-drain",
        "backfill-polymarket-open-sparse",
        "backfill-kalshi-open-sparse",
        "backfill-box-scores",
        "backfill-espn-ids",
        "backfill-historical-links",
        "update-max-movement",
        "export-engagement-nightly",
        "daily-challenge-push",
        "big-move-alerts",
        "morning-digest-daily",
        "precompute-calibration-main",
        # CAL-P084 (#2007) — the beat gauge sampler. :05 and :45, deliberately
        # outside the producer's :15-:35 window.
        "calibration-beat-gauge-sampler",
        "compute-time-horizon-calibration",
        "compute-fair-fight-comparison",
        "precompute-source-intelligence",
        "precompute-category-pages",
        "warm-event-concepts",
        # LAT-P137 — the producer for the Search page's category census, which
        # LAT-P122 cached and left with nothing to rebuild it. Gotcha #12: this
        # allowlist is the reason a new beat entry cannot land silently.
        "warm-futures-categories",
        "warm-prop-families",
        "warm-typeahead",
        # Option D (#1866, LAT-P067) — the typeahead index builder + its D4
        # sentinel. Gotcha #12: this allowlist is the reason a new beat entry
        # cannot land silently.
        "rebuild-typeahead-index",
        "typeahead-index-sentinel",
        # LAT-P090 (#2211) — the `/search` response-cache head warmer. Gotcha
        # #12: this allowlist is the reason a new beat entry cannot land
        # silently.
        "warm-search-head",
        # LAT-P109 (#2255) — the trigram GIN pending-list flush that keeps cold
        # `/api/events/search` off the 4 MB sawtooth. Gotcha #12: this allowlist
        # is the reason a new beat entry cannot land silently.
        "flush-search-gin-pending-lists",
        "precompute-discover-candidate-base",
        # #2236 — the narrow republisher for live-containing feed shapes, whose
        # 60 s stale ceiling the 120 s beat above structurally cannot cover.
        "prewarm-live-feed-shapes",
        "precompute-admin-audit-all",
        "precompute-admin-link-rate",
        "precompute-admin-matured-linkage",
        "precompute-backfill-winners-status",
        "precompute-backfill-progress",
        "backfill-combat-wps",
        "data-quality-watchdog",
        "calibration-sentinel-weekly",
        "mlb-schedule-coverage-daily",
        "flow-sentinel-daily",
        "grid-sentinel-daily",
        "grid-register-sentinel-daily",
        "tournament-register-sentinel-daily",
        # UX-P139 — targeted re-price of register-pinned tournament markets.
        # The scanning poll cannot reach them reliably under Gamma's
        # offset-2000 cap, and they are the whole bracket grid.
        "refresh-registered-tournament-prices",
        # UX-P139 item 9 — ESPN tennis results into Redis, so the hub route
        # never makes a third-party call inside a GET.
        "sync-tournament-results",
        "link-tournament-matchups",
        "schedule-sentinel-daily",
        "horizon-sentinel-daily",
        "settled-concept-sentinel-daily",
        "board-sentinel-daily",
        # #2853 — the anchor-schedule rail's nightly read-only driver. Gotcha
        # #12: this allowlist is the reason a new beat entry cannot land
        # silently.
        "anchor-schedule-sentinel-daily",
        "sentry-snapshot-15min",
        "backfill-kalshi-settled-events",
        # CAL-P998 / D47 (#2771): the resolution-window sweep stops being
        # attended. Daily 04:20 UTC, one bounded batch of 500.
        "sweep-kalshi-resolution-window",
        "backfill-kalshi-trade-history",
        "backfill-settled-gap-creation",
        "backfill-polymarket-matchups",
        "recover-datagolf-participation",
        "poll-datagolf-inplay",
        "refresh-open-commentary",
        "regrade-polymarket-under-signflip",
        "unresolve-datagolf-premature",
        "null-impossible-both-sides-openings",
        "correct-both-winner-guess-side",
        "compute-calibration-prices",
        "precompute-bookmaker-calibration",
        "sync-polymarket-resolved-status",
        "backfill-espn-win-prob",
        "backfill-espn-win-prob-oldest",
        "backfill-polymarket-winners",
        "clob-resolve-drain",
        # #2077 (queue 419) — the nightly settlement-capture sweep. Gotcha #12:
        # this allowlist is the reason a new beat entry cannot land silently.
        "settlement-capture-sweep-nightly",
        "snapshot-coverage-metrics-daily",
        # "resolve-winners",  # RETIRED 2026-07-06 (#991) — redundant with backfill_winners
        "digest-external-feature-requests-weekly",
        "compare-ws-shadow",
        # live/035 — the nightly event-chart completeness sweep. Gotcha #12:
        # this allowlist is the reason a new beat entry cannot land silently.
        "backfill-thin-event-charts",
        # live/059 — the outright chart's venue-history warmer.
        "fill-futures-chart-series",
    }

    def test_no_missing_entries(self):
        actual = set(celery_app.conf.beat_schedule.keys())
        missing = self.EXPECTED_ENTRIES - actual
        assert not missing, f"Missing beat schedule entries: {missing}"

    def test_no_unexpected_entries(self):
        actual = set(celery_app.conf.beat_schedule.keys())
        unexpected = actual - self.EXPECTED_ENTRIES
        assert not unexpected, (
            f"Unexpected beat schedule entries: {unexpected}. "
            f"If these are intentional, add them to EXPECTED_ENTRIES in this test."
        )

    def test_no_odds_api_historical_backfill_in_beat(self):
        """The Odds API historical endpoint is expensive and must stay manual."""
        historical_tasks = {
            "app.tasks.check_snapshot_sparsity",
            "app.tasks.backfill_historical_odds",
            "app.tasks.lookup_and_backfill_extids",
        }
        scheduled = {
            entry["task"] for entry in celery_app.conf.beat_schedule.values()
        }
        assert historical_tasks.isdisjoint(scheduled)


class TestHeavyQueueRouting:
    """#224: the 600s-class grinders (calibration precompute family + backfills)
    must land on the dedicated `heavy` worker, not the 2-slot `background` worker.
    This is the structural fix for the recurring background-queue starvation
    (cal_price #183 → time_horizon → precompute_calibration_main #223). A beat
    entry's `options["queue"]` OVERRIDES task_routes, so BOTH must agree — guard
    both, in both directions, so a future edit can't silently re-starve the class.
    """

    def test_heavy_queue_exists(self):
        from app.tasks import celery_app as app
        qnames = {q.name for q in app.conf.task_queues}
        assert "heavy" in qnames, f"heavy queue missing from {qnames}"

    def test_heavy_tasks_route_to_heavy_in_task_routes(self):
        from app.tasks import HEAVY_TASKS, celery_app as app
        routes = app.conf.task_routes
        misrouted = {
            t: routes.get(t, {}).get("queue") for t in HEAVY_TASKS
            if routes.get(t, {}).get("queue") != "heavy"
        }
        assert not misrouted, f"HEAVY tasks not routed to heavy in task_routes: {misrouted}"

    def test_heavy_beat_entries_pin_heavy_queue(self):
        """Beat options override task_routes — every HEAVY task's beat entry must
        pin queue=heavy, else it silently reverts to background."""
        from app.tasks import HEAVY_TASKS, celery_app as app
        bad = {
            name: entry.get("options", {}).get("queue")
            for name, entry in app.conf.beat_schedule.items()
            if entry["task"] in HEAVY_TASKS
            and entry.get("options", {}).get("queue") != "heavy"
        }
        assert not bad, f"HEAVY beat entries not pinned to heavy: {bad}"

    def test_latency_sensitive_tasks_stay_on_background(self):
        """The two routing sets must never disagree.

        AMENDED #1609 / LAT-P065: the old rationale here was "pipeline drivers
        must not be on heavy". That is no longer the rule and the docstring is
        corrected rather than left to mislead — `match_prediction_markets` IS a
        pipeline driver and it is now on heavy ON PURPOSE, because at 337.4s p50
        on a queue with ~one effective slot it was the measured cause of the
        `warm_typeahead` dispatch holes. What survives is the 600-960s BACKFILL
        class (guarded explicitly below) and the structural invariant: a task in
        both sets is a contradiction whichever way the argument goes.
        """
        from app.tasks import HEAVY_TASKS, _HEAVY_KEEP_ON_BACKGROUND, celery_app as app
        overlap = HEAVY_TASKS & _HEAVY_KEEP_ON_BACKGROUND
        assert not overlap, f"tasks in BOTH heavy and keep-on-background: {overlap}"
        routes = app.conf.task_routes
        leaked = [
            t for t in _HEAVY_KEEP_ON_BACKGROUND
            if routes.get(t, {}).get("queue") == "heavy"
        ]
        assert not leaked, f"keep-on-background tasks leaked onto heavy: {leaked}"

    def test_1609_multi_minute_residents_are_off_background(self):
        """#1609: the three multi-minute residents route to `heavy`, both arms.

        Background is a 2-slot Standard-1X on which `warm_typeahead` (36.3s p50
        against a 30s floor) is approximately one permanently-occupied slot — so
        the queue has ~ONE effective slot for ~40 beats. These three held it for
        minutes at a time and were measured starving the warmer (five holes in
        55.8 probe-free minutes; warmer not running 30.0% of wall-clock).

        Guards BOTH arms because they can disagree silently: beat
        `options["queue"]` overrides `task_routes` at dispatch time, so a task
        can be correct in one and wrong in the other and still be misrouted.
        """
        from app.tasks import HEAVY_TASKS, celery_app as app

        moved = {
            "app.tasks.match_prediction_markets",
            "app.tasks.poll_kalshi_markets",
            "app.tasks.precompute_admin_link_rate",
        }
        assert moved <= HEAVY_TASKS, f"#1609 residents missing from HEAVY_TASKS: {moved - HEAVY_TASKS}"

        routes = app.conf.task_routes
        misrouted = {
            t: routes.get(t, {}).get("queue") for t in moved
            if routes.get(t, {}).get("queue") != "heavy"
        }
        assert not misrouted, f"#1609 residents not on heavy in task_routes: {misrouted}"

        bad_beat = {
            name: entry.get("options", {}).get("queue")
            for name, entry in app.conf.beat_schedule.items()
            if entry["task"] in moved
            and entry.get("options", {}).get("queue") != "heavy"
        }
        assert not bad_beat, f"#1609 residents' beat entries not pinned to heavy: {bad_beat}"

    def test_big_backfills_stay_off_heavy(self):
        """The part of the #224 finding that SURVIVES #1609.

        #1609 moved the 300s class to heavy. It did NOT move the 600-960s
        backfill class, and that distinction is the whole reason the move is
        safe: two ten-minute backfills would fill both heavy slots and delay the
        hourly /calibration warmer, which is what #224 observed live. Without
        this guard, "#1609 moved grinders to heavy" reads as a licence to move
        the rest.
        """
        from app.tasks import HEAVY_TASKS, celery_app as app

        backfills = {
            "app.tasks.backfill_winners",
            "app.tasks.backfill_kalshi_candlestick",
            "app.tasks.backfill_kalshi_history",
            "app.tasks.backfill_kalshi_settled",
            "app.tasks.backfill_kalshi_trades",
            "app.tasks.backfill_kalshi_volume",
            "app.tasks.backfill_polymarket_history",
            "app.tasks.backfill_polymarket_winners",
            "app.tasks.backfill_espn_win_prob",
            "app.tasks.backfill_team_identities",
            "app.tasks.kalshi_cliff_drain",
        }
        on_heavy = backfills & HEAVY_TASKS
        assert not on_heavy, (
            f"600-960s backfills must stay on background (#224, upheld by #1609): {on_heavy}"
        )
        routes = app.conf.task_routes
        leaked = {
            t: routes.get(t, {}).get("queue") for t in backfills
            if routes.get(t, {}).get("queue") == "heavy"
        }
        assert not leaked, f"backfills leaked onto heavy: {leaked}"

    def test_1609_warmer_beats_carry_an_expires_bound(self):
        """#1609 hygiene: every listed cache-warmer beat has `expires` <= its period.

        HYGIENE, NOT THE CURE — the registered control E3 predicts warmer hole
        frequency is UNCHANGED by this alone. Guarded anyway because the failure
        mode is silent: with no `expires`, a 10 s beat published 8,640
        messages/day against ~2,530 real starts and the surplus arrived later in
        bursts. An `expires` LONGER than the period would re-admit exactly that.
        """
        from app.tasks import _EXPIRING_WARMER_BEATS, celery_app as app

        missing = set(_EXPIRING_WARMER_BEATS) - set(app.conf.beat_schedule)
        assert not missing, (
            f"_EXPIRING_WARMER_BEATS names beats that do not exist (renamed?): {missing}"
        )

        unbounded = {
            name: app.conf.beat_schedule[name].get("options", {}).get("expires")
            for name in _EXPIRING_WARMER_BEATS
            if app.conf.beat_schedule[name].get("options", {}).get("expires")
            != _EXPIRING_WARMER_BEATS[name]
        }
        assert not unbounded, f"warmer beats missing their expires bound: {unbounded}"

    #: Beats whose task WALL exceeds their beat period, so the flat
    #: `expires <= period` rule does not apply to them. See the derivation in
    #: `app/utils/typeahead_beat_budget.derive_message_expiry_s`. Membership is
    #: declared rather than inferred, so adding a beat here is a visible act.
    _WALL_EXCEEDS_PERIOD_BEATS = {"warm-typeahead"}

    #: Beats exempt for the OTHER reason a held-off fire is not superseded: the
    #: message cannot reach a slot inside one beat period, so the flat
    #: `expires <= period` rule discards the only start opportunities the task
    #: gets. The quantity is DELIVERY LATENCY, not the task's wall — the
    #: distinction #3364 is about. Membership is declared, so adding a beat here
    #: is a visible act. See `search_head_warmer.derive_message_expiry_s`.
    _DELIVERY_BOUND_BEATS = {"warm-search-head"}

    def test_1609_expires_never_exceeds_the_beat_period(self):
        """`expires` longer than the period cannot discard a superseded message.

        ⚠️ **AMENDED, LAT-P075 — the flat rule was right about the wrong task.**
        The original assertion was `expires <= period` for every listed beat, and
        the reasoning behind it is still correct *for a task whose wall is shorter
        than its beat period*: there, the next fire always executes, so a message
        outliving its own replacement is pure lapping.

        `warm_typeahead` is the case that reasoning does not cover. Its wall is
        39.3-61.3 s against a **10 s** beat, so the fires landing during a pass
        are not superseded messages — they are the only start opportunities that
        exist, all of them held off by the run lock until the pass ends. The flat
        rule expired them at one beat period and destroyed every one except those
        published in the pass's final 10 s: a measured **30.5 %** of fires
        executing at all, against **32.7 %** predicted by the arithmetic.

        So the rule is now derived per beat, and the two arms are asserted
        separately below.

        **What this gate would have to SEE to go red** (Fable's standing rule of
        2026-08-19 — naming the failing input, not just claiming coverage):

        * a short-wall beat given an `expires` above its period — e.g.
          `warm-event-concepts` moved 300 -> 400 against a 300 s schedule. That is
          the original lapping defect and arm 1 fires on it.
        * `warm-typeahead` returned to an `expires` at or below its 10 s beat, or
          otherwise below the measured worst wall plus margin — i.e. the exact
          regression this cycle repaired. Arm 2 fires on it, and it is the input
          that matters, because reinstating 10 here is a one-character edit that
          would look like tidying.
        * `_LOCK_TTL_SECONDS` lowered under the measured worst wall, which would
          make the lock expire under a live pass. `derive_message_expiry_s` raises
          rather than returning a smaller number, and arm 2 propagates that raise.
        """
        from app.tasks import _EXPIRING_WARMER_BEATS, celery_app as app
        from app.utils.typeahead_beat_budget import (
            RING_WALL_MAX_S,
            SAFETY_MARGIN_S,
            derive_message_expiry_s,
        )

        def _period_s(name):
            schedule = app.conf.beat_schedule[name]["schedule"]
            if isinstance(schedule, (int, float)):
                return float(schedule)
            # crontab(minute="*/N") -> N minutes. Derive it; do not hardcode.
            minutes = sorted(schedule.minute)
            return (minutes[1] - minutes[0]) * 60.0 if len(minutes) > 1 else 3600.0

        # --- arm 1: the flat rule, still in force for every short-wall beat ---
        too_long = {}
        exempt = self._WALL_EXCEEDS_PERIOD_BEATS | self._DELIVERY_BOUND_BEATS
        for name, expires_s in _EXPIRING_WARMER_BEATS.items():
            if name in exempt:
                continue
            period_s = _period_s(name)
            if expires_s > period_s:
                too_long[name] = (expires_s, period_s)
        assert not too_long, (
            f"expires exceeds beat period (cannot discard a superseded message): {too_long}"
        )

        # --- arm 2: the derived rule, for beats whose wall outlasts the period ---
        assert self._WALL_EXCEEDS_PERIOD_BEATS <= set(_EXPIRING_WARMER_BEATS), (
            "a beat declared long-walled is no longer in _EXPIRING_WARMER_BEATS"
        )
        wired = _EXPIRING_WARMER_BEATS["warm-typeahead"]
        derived = derive_message_expiry_s()
        assert wired == derived, (
            f"warm-typeahead expires is {wired}s but derives to {derived}s — the "
            f"period regression this value repairs is #1866/#2014; do not restore "
            f"the flat rule here without reading derive_message_expiry_s"
        )
        # The bound must actually clear the thing it exists to survive.
        assert wired >= RING_WALL_MAX_S + SAFETY_MARGIN_S, (
            f"expires {wired}s does not outlive the measured worst pass wall "
            f"({RING_WALL_MAX_S}s) plus margin ({SAFETY_MARGIN_S}s), so a message "
            f"published during a pass still cannot survive to the lock release"
        )
        # And it must be strictly above the beat period, or arm 1 covered it and
        # this beat does not belong in the declared set.
        assert wired > _period_s("warm-typeahead")

        # --- arm 3: the delivery-latency rule (#3364) ---
        #
        # WHAT THIS ARM WOULD HAVE TO SEE TO GO RED (Fable's standing rule —
        # name the failing input, do not claim coverage):
        #
        # * `warm-search-head` returned to an `expires` at or below its 20 s
        #   beat. That is the exact regression #3364 repairs, it is a
        #   two-character edit, and it would look like restoring the flat rule.
        #   Production measured the defect at `matched_emitted` 30 /
        #   `matched_delivered` 0 in one 600 s bucket and 102 starts against
        #   2,949 expected fires over 16.4 h.
        # * `_LOCK_TTL_SECONDS` raised far enough that the broker would hold more
        #   than `MAX_LIVE_MESSAGES` of this beat's messages at once.
        #   `derive_message_expiry_s` raises rather than returning a capped
        #   value, and this arm propagates that raise.
        # * The beat period changed in the schedule without
        #   `BEAT_PERIOD_SECONDS` following it — the mirror assertion below is
        #   the only thing keeping the derivation's input honest.
        from app.tasks.search_head_warmer import (
            BEAT_PERIOD_SECONDS,
            derive_message_expiry_s as derive_search_head_expiry_s,
        )

        assert self._DELIVERY_BOUND_BEATS <= set(_EXPIRING_WARMER_BEATS), (
            "a beat declared delivery-bound is no longer in _EXPIRING_WARMER_BEATS"
        )
        assert BEAT_PERIOD_SECONDS == _period_s("warm-search-head"), (
            f"search_head_warmer.BEAT_PERIOD_SECONDS is {BEAT_PERIOD_SECONDS}s but "
            f"the beat schedules {_period_s('warm-search-head')}s — the mirror has "
            f"drifted and derive_message_expiry_s is deriving from a fiction"
        )
        wired_sh = _EXPIRING_WARMER_BEATS["warm-search-head"]
        derived_sh = derive_search_head_expiry_s()
        assert wired_sh == derived_sh, (
            f"warm-search-head expires is {wired_sh}s but derives to {derived_sh}s — "
            f"the delivery deficit this value repairs is #3364 (0.03 of schedule "
            f"delivered); do not restore the flat rule without reading "
            f"search_head_warmer.derive_message_expiry_s"
        )
        # It must be strictly above the beat period, or arm 1 covered it and this
        # beat does not belong in the declared set.
        assert wired_sh > _period_s("warm-search-head")

    def test_heavy_beat_literals_match_their_effective_queue(self):
        """Every HEAVY beat entry must SAY heavy in the source, not just dispatch there.

        THE GUARD `test_heavy_beat_entries_pin_heavy_queue` CANNOT CATCH THIS,
        and that is the entire reason this one exists. That test imports the
        module and reads `options["queue"]` — by which time the post-schedule
        loop at the bottom of `app/tasks/__init__.py` has already flipped every
        HEAVY_TASKS entry to `heavy`. It therefore passes unconditionally, for
        any literal whatsoever. It has been passing over NINE wrong literals.

        What that cost, measured rather than asserted (LAT-P066/P067): seven
        calibration/precompute warmers sat in the file literally reading
        `"queue": "background"`, plus `poll-kalshi` and
        `match-prediction-markets` carrying no `options` at all after #1609
        moved them. The effective routing was correct the whole time — and the
        SOURCE read as evidence for "the calibration family is starving the
        background queue", which is false, and which is exactly the question
        #1609 spent multiple windows investigating.

        A backstop that silently corrects text makes the text lie. So this reads
        the source, with the loop's own body excluded (it necessarily contains
        the string `heavy`).
        """
        import ast
        import inspect

        from app.tasks import HEAVY_TASKS
        import app.tasks as tasks_module

        source = inspect.getsource(tasks_module)
        tree = ast.parse(source)

        # Locate the `celery_app.conf.beat_schedule = {...}` assignment and read
        # its literal dict, so this reflects what is WRITTEN, never what ran.
        schedule_node = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == "beat_schedule"
                    and isinstance(node.value, ast.Dict)
                ):
                    schedule_node = node.value
        assert schedule_node is not None, "could not locate the beat_schedule literal"

        mismatched = {}
        for key_node, value_node in zip(schedule_node.keys, schedule_node.values):
            if not isinstance(key_node, ast.Constant) or not isinstance(value_node, ast.Dict):
                continue
            entry = {}
            for k, v in zip(value_node.keys, value_node.values):
                if isinstance(k, ast.Constant):
                    entry[k.value] = v
            task_node = entry.get("task")
            if not isinstance(task_node, ast.Constant) or task_node.value not in HEAVY_TASKS:
                continue
            options = entry.get("options")
            literal_queue = None
            if isinstance(options, ast.Dict):
                for ok, ov in zip(options.keys, options.values):
                    if isinstance(ok, ast.Constant) and ok.value == "queue":
                        literal_queue = ov.value if isinstance(ov, ast.Constant) else "<computed>"
            if literal_queue != "heavy":
                mismatched[key_node.value] = literal_queue or "<no options key>"

        assert not mismatched, (
            "HEAVY beat entries whose SOURCE LITERAL disagrees with where they "
            f"actually dispatch: {mismatched}. The post-schedule loop will route "
            "them to heavy anyway — which is precisely the problem: the file then "
            "documents a routing that is not real."
        )

    def test_all_heavy_tasks_registered(self):
        from app.tasks import HEAVY_TASKS, celery_app as app
        registered = set(app.tasks.keys())
        unregistered = [t for t in HEAVY_TASKS if t not in registered]
        assert not unregistered, f"HEAVY_TASKS references unregistered tasks: {unregistered}"

    def test_sentinels_route_to_heavy(self):
        """#233: the sentinels moved off the congested 2-slot `background`
        queue (their morning 07:10-07:45 UTC fires were dying as no_run_cached)
        onto `heavy`, which guarantees a free slot. Guard BOTH task_routes and
        beat options so a future edit can't silently re-starve the alarms."""
        from app.tasks import HEAVY_TASKS, celery_app as app
        sentinels = {
            "app.tasks.flow_sentinel",
            "app.tasks.grid_sentinel",
            "app.tasks.horizon_sentinel",
            "app.tasks.settled_concept_sentinel",
            "app.tasks.calibration_sentinel",
            "app.tasks.board_sentinel",
        }
        assert sentinels <= HEAVY_TASKS, (
            f"sentinels missing from HEAVY_TASKS: {sentinels - HEAVY_TASKS}"
        )
        routes = app.conf.task_routes
        misrouted = {
            t: routes.get(t, {}).get("queue") for t in sentinels
            if routes.get(t, {}).get("queue") != "heavy"
        }
        assert not misrouted, f"sentinels not routed to heavy in task_routes: {misrouted}"
        bad_beat = {
            name: entry.get("options", {}).get("queue")
            for name, entry in app.conf.beat_schedule.items()
            if entry["task"] in sentinels
            and entry.get("options", {}).get("queue") != "heavy"
        }
        assert not bad_beat, f"sentinel beat entries not pinned to heavy: {bad_beat}"
