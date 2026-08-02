"""Targeted Celery result retention (Queue 300R Item 1).

The Celery config never set ``result_expires`` or ``task_ignore_result``, so
**every** task run stored a ``celery-task-meta-*`` key for Celery's 24-hour
default. On a 50MB ``allkeys-lru`` instance that is not free storage — it is
eviction pressure, and the thing evicted is whatever was least recently used,
which is how Queue 298 lost sentinel evidence to a cache that was never
supposed to be authoritative.

The fix has to be **targeted**, not a blanket ``task_ignore_result``. Admin
endpoints enqueue tasks and hand the caller a ``task_id`` (``_safe_send_task``
→ ``{"status": "queued", "task_id": ...}``), and 17 admin routes read those ids
back through ``celery_app.AsyncResult``. Suppressing those results would turn a
working status poll into a permanent ``PENDING``.

So the rule implemented here is: **a scheduled beat that nothing can poll does
not need a stored result.** Two facts make that safe on this codebase:

* Task health/observability does NOT come from the result backend. Every beat
  runs through ``_tracked_run``, which writes ``bainluck:task_metrics:<name>``
  independently — the cockpit, ``/api/admin/celery/task-metrics`` and the
  watchdogs all read that hash, not ``AsyncResult``. Ignoring a result costs
  nothing they consume.
* There are no Celery canvas primitives anywhere in this app (no ``chord``,
  ``group``, or ``chain``; the only ``from celery import`` is ``Celery``
  itself), and no task dispatches another task. A chord body reading a
  suppressed header result is the classic way this change breaks a codebase,
  and that shape does not exist here. ``test_celery_result_retention.py``
  guards it so it cannot appear later without failing CI.

Retries are unaffected: ``self.retry()`` round-trips through the *broker*, not
the result backend, so a suppressed task still retries and still records its
failure through ``_tracked_run``.

The drift hazard is real and is guarded rather than trusted: if someone adds an
admin trigger for a task that is currently in the suppressed set, its status
poll would silently never resolve. ``RESULT_CONSUMER_TASKS`` below is the
declared consumer set, and the test suite re-derives the true set by AST-walking
every dispatch site under ``app/routes``, ``app/services`` and ``app/utils``,
failing if the two disagree.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping

logger = logging.getLogger(__name__)

#: How long a *kept* result stays readable. Celery's default is 86400s (24h),
#: which is two orders of magnitude longer than anything here needs: admin
#: status polls happen while the operator is looking at the page. One hour is
#: still generous for a 600s-class grinder plus a slow poll, and it bounds
#: residency for the results we deliberately keep.
RESULT_EXPIRES_S = 3600

#: Tasks that something can read the result of — every task reachable from an
#: HTTP route via ``.delay()``/``.apply_async()``/``_safe_send_task``. Derived
#: by static analysis, not by hand; ``test_result_consumer_set_matches_code``
#: re-derives it and fails on drift, so adding an admin trigger for a
#: currently-suppressed beat is a CI failure rather than a silent dead poll.
RESULT_CONSUMER_TASKS: frozenset[str] = frozenset(
    {
        "app.tasks.audit_canonical_keys",
        "app.tasks.audit_prediction_market_links",
        "app.tasks.audit_related_futures",
        "app.tasks.backfill_box_scores",
        "app.tasks.backfill_canonical_keys",
        "app.tasks.backfill_combat_wps",
        "app.tasks.backfill_espn_win_prob",
        "app.tasks.backfill_game_state",
        "app.tasks.backfill_historical_odds",
        "app.tasks.backfill_kalshi_candlestick",
        "app.tasks.backfill_kalshi_history",
        "app.tasks.backfill_kalshi_settled",
        "app.tasks.backfill_kalshi_trades",
        "app.tasks.backfill_kalshi_volume",
        "app.tasks.backfill_polymarket_history",
        "app.tasks.backfill_polymarket_matchups",
        "app.tasks.backfill_polymarket_win_prob",
        "app.tasks.backfill_polymarket_winners",
        "app.tasks.backfill_team_identities",
        "app.tasks.backfill_team_links",
        "app.tasks.backfill_team_logos",
        "app.tasks.backfill_winners",
        "app.tasks.board_sentinel",
        "app.tasks.calibration_sentinel",
        "app.tasks.canonicalize_entities",
        "app.tasks.categorize_futures",
        "app.tasks.cleanup_crypto",
        "app.tasks.clob_resolve_drain",
        "app.tasks.collapse_snapshots",
        "app.tasks.compute_calibration_prices",
        "app.tasks.compute_matching_metrics",
        "app.tasks.compute_snapshot_distribution",
        "app.tasks.compute_time_horizon_calibration",
        "app.tasks.correct_both_winner_guess_side",
        "app.tasks.create_github_issue_for_bug_report",
        "app.tasks.enrich_market_hooks",
        "app.tasks.enrich_taxonomy_llm",
        "app.tasks.ensure_perf_indexes",
        "app.tasks.fix_outcome_names",
        "app.tasks.flow_sentinel",
        "app.tasks.grid_register_sentinel",
        "app.tasks.grid_sentinel",
        "app.tasks.horizon_sentinel",
        "app.tasks.import_external_curator_ground_truth",
        "app.tasks.lookup_and_backfill_extids",
        "app.tasks.match_prediction_markets",
        "app.tasks.merge_degenerate_combat_events",
        "app.tasks.merge_duplicate_events",
        "app.tasks.null_impossible_both_sides_openings",
        "app.tasks.poll_futures_odds",
        "app.tasks.poll_kalshi_markets",
        "app.tasks.poll_live_prediction_markets",
        "app.tasks.poll_polymarket_markets",
        "app.tasks.precompute_backfill_progress",
        "app.tasks.precompute_backfill_winners_status",
        "app.tasks.precompute_calibration_main",
        "app.tasks.precompute_category_pages",
        "app.tasks.recategorize_other",
        "app.tasks.recover_datagolf_participation",
        "app.tasks.regenerate_tags",
        "app.tasks.regrade_polymarket_under_signflip",
        "app.tasks.seed_entity_registry",
        "app.tasks.send_bug_fixed_email",
        "app.tasks.settled_concept_sentinel",
        "app.tasks.snapshot_coverage_metrics",
        "app.tasks.snapshot_discover_ground_truth_diagnostics",
        "app.tasks.snapshot_discover_label_eval_run",
        "app.tasks.sync_mlb_win_probability",
        "app.tasks.sync_polymarket_resolved",
        "app.tasks.sync_rosters",
        "app.tasks.sync_statpal_injuries",
        "app.tasks.sync_statpal_live_plays",
        "app.tasks.sync_statpal_rosters",
        "app.tasks.sync_statpal_schedules",
        "app.tasks.sync_statpal_standings",
        "app.tasks.sync_statpal_team_stats",
        "app.tasks.turbo_collapse_futures",
        "app.tasks.turbo_collapse_odds",
        "app.tasks.unresolve_datagolf_premature",
    }
)


def beat_only_tasks(
    beat_schedule: Mapping[str, Any] | None,
    consumers: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Beat task names with no result consumer, sorted and de-duplicated.

    Pure: takes the schedule, returns names. A malformed or empty schedule
    yields ``()`` — the fail-safe direction, because the failure mode of
    returning too FEW names is "we keep storing a result we didn't need", while
    returning too many is "an admin poll hangs forever".

    ``consumers`` defaults to :data:`RESULT_CONSUMER_TASKS` resolved at CALL
    time, not at definition time, so the module constant stays the single
    source of truth for an override or a test double.
    """
    if not beat_schedule:
        return ()

    keep = set(RESULT_CONSUMER_TASKS if consumers is None else consumers)
    scheduled: set[str] = set()
    for entry in beat_schedule.values():
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("task")
        if isinstance(name, str) and name:
            scheduled.add(name)
    return tuple(sorted(scheduled - keep))


def apply_result_suppression(
    app: Any, consumers: Iterable[str] | None = None
) -> tuple[str, ...]:
    """Set ``ignore_result`` on every beat-only task registered on ``app``.

    Returns the names actually suppressed (registered ∩ beat-only), so callers
    and tests can assert on the real effect rather than the intent. A name in
    the schedule that is not registered on this app is skipped rather than
    raising: an import-order surprise must never take the worker down over a
    cache optimisation.

    The attribute is set on the bound task instance instead of going through
    ``task_annotations`` because the beat schedule is defined *after* the task
    decorators run, and annotations are resolved at decoration time. Celery's
    tracer reads ``task.ignore_result`` when it builds the tracer at worker
    startup, which is after all modules are imported — so a post-definition
    assignment is what actually takes effect.
    """
    try:
        schedule = app.conf.beat_schedule
    except Exception as exc:  # noqa: BLE001 — defensive: never block worker boot
        logger.warning("result suppression skipped (no beat schedule): %s", exc)
        return ()

    suppressed: list[str] = []
    for name in beat_only_tasks(schedule, consumers):
        task = app.tasks.get(name)
        if task is None:
            logger.debug("result suppression: %s not registered here — skipping", name)
            continue
        task.ignore_result = True
        suppressed.append(name)

    logger.info(
        "Celery result retention: %d beat-only tasks suppressed, "
        "%d consumer tasks keep results (expires=%ds)",
        len(suppressed),
        len(RESULT_CONSUMER_TASKS),
        RESULT_EXPIRES_S,
    )
    return tuple(suppressed)
