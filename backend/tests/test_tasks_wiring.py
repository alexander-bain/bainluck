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
        "enrich-events-hourly",
        "sync-espn-live",
        "backfill-team-logos",
        "backfill-team-links",
        "match-prediction-markets",
        "poll-live-prediction-markets",  # restored: WS not yet deployed, REST polling needed for pre-game snapshots
        "heartbeat",
        "collapse-odds-snapshots-daily",
        "collapse-winprob-snapshots-daily",
        "collapse-futures-snapshots-daily",
        "sync-rosters-daily",
        "sync-mlb-win-probability",
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
        "merge-duplicate-events",
        "merge-degenerate-combat-events",
        "canonicalize-entities-daily",
        "precompute-interestingness",
        "check-aggregation-quality",
        "check-tier1-coverage",
        "daily-digest",
        "backfill-polymarket-price-history",
        "backfill-kalshi-price-history",
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
        "compute-time-horizon-calibration",
        "compute-fair-fight-comparison",
        "precompute-source-intelligence",
        "precompute-category-pages",
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
        "horizon-sentinel-daily",
        "settled-concept-sentinel-daily",
        "sentry-snapshot-15min",
        "backfill-kalshi-settled-events",
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
        "sync-polymarket-resolved-status",
        "backfill-espn-win-prob",
        "backfill-espn-win-prob-oldest",
        "backfill-polymarket-winners",
        "clob-resolve-drain",
        "snapshot-coverage-metrics-daily",
        # "resolve-winners",  # RETIRED 2026-07-06 (#991) — redundant with backfill_winners
        "digest-external-feature-requests-weekly",
        "compare-ws-shadow",
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
        """The pipeline drivers and alarms must NOT be on heavy — they must fire
        promptly and never queue behind a 10-minute backfill."""
        from app.tasks import HEAVY_TASKS, _HEAVY_KEEP_ON_BACKGROUND, celery_app as app
        overlap = HEAVY_TASKS & _HEAVY_KEEP_ON_BACKGROUND
        assert not overlap, f"tasks in BOTH heavy and keep-on-background: {overlap}"
        routes = app.conf.task_routes
        leaked = [
            t for t in _HEAVY_KEEP_ON_BACKGROUND
            if routes.get(t, {}).get("queue") == "heavy"
        ]
        assert not leaked, f"latency-sensitive tasks leaked onto heavy: {leaked}"

    def test_all_heavy_tasks_registered(self):
        from app.tasks import HEAVY_TASKS, celery_app as app
        registered = set(app.tasks.keys())
        unregistered = [t for t in HEAVY_TASKS if t not in registered]
        assert not unregistered, f"HEAVY_TASKS references unregistered tasks: {unregistered}"

    def test_sentinels_route_to_heavy(self):
        """#233: the 5 sentinels moved off the congested 2-slot `background`
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
