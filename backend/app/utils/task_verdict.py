"""One pure contract from a task's RETURNED summary to a health verdict.

Queue 300H Item 0. Every scheduled task runs through ``_tracked_run``, which
until now recorded SUCCESS for any invocation that returned without raising.
That is the false-GREEN defect (#1515): three calibration tasks told operators
they were healthy while

* ``compute_time_horizon_calibration`` returned ``{"status": "partial",
  "horizons_done": 0, "total": 4}`` — zero horizons computed, every 6h;
* ``calibration_prices`` returned ``terminal: partial`` with ``stopped_at`` set
  on every deadline-truncated run, against a 70% thrown-failure rate;
* ``coverage_metrics`` swallows its own exception and returns
  ``terminal: "failed"`` — a *returned* failure that raised nothing.

The fix is not per-task success guessing. It is this: a summary either carries
explicit terminal truth, or it proves nothing. The four verdicts are

``complete``
    Every required unit finished AND (where the task publishes something) the
    durable artifact landed. Hard to earn, deliberately.
``partial``
    Real, visible progress that is not a finished run. Not a failure — a
    resumable sweep returning ``partial`` is behaving as designed — but it can
    never read GREEN, because the artifact it exists to produce is not there.
``failed``
    The task itself reported a failed terminal without raising.
``unknown``
    Nothing in the summary proves what happened. Split by ``authoritative``:
    an *authoritative* unknown (the task speaks this vocabulary and told us it
    banked nothing — a skipped/overlap-refused run, a ledger write that failed)
    must not read GREEN. A *non-authoritative* unknown is the legacy case — a
    task that predates the contract and returns a bare counter dict. Its
    invocation is recorded as before, but stamped ``unverified`` so no surface
    can mistake "it returned" for "it did the work".

The module is pure: no Redis, no DB, no imports from ``app.tasks``. It is safe
to call on any object, including a poisoned or partially-decoded summary — a
shape it cannot read is ``unknown``, never an exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# --- Verdicts ---------------------------------------------------------------
COMPLETE = "complete"
PARTIAL = "partial"
FAILED = "failed"
UNKNOWN = "unknown"

#: Verdicts that must never increment a completion-success counter or leave a
#: task's health GREEN. ``complete`` is the only verdict that earns GREEN.
NOT_GREEN = frozenset({PARTIAL, FAILED, UNKNOWN})

# --- Terminal vocabularies already deployed in the tree ----------------------
# app/utils/calibration_phase_ledger.py  (precompute_calibration_main)
# app/utils/task_resumability.py         (coverage_metrics, calibration_prices)
_TERMINAL_COMPLETE = frozenset({"complete", "ok", "success", "succeeded"})
_TERMINAL_PARTIAL = frozenset({"partial", "cancelled", "canceled", "interrupted"})
_TERMINAL_FAILED = frozenset({"failed", "error", "hard_loss"})
#: Terminals that mean "this run deliberately did nothing". Not a failure, but
#: an invocation that banked no work cannot vouch for the task's health.
_TERMINAL_NO_WORK = frozenset({"overlap_refused", "skipped", "noop", "no_work"})

# --- ``status`` vocabularies -------------------------------------------------
_STATUS_COMPLETE = frozenset({"ok", "complete", "completed", "success", "succeeded"})
_STATUS_PARTIAL = frozenset({"partial", "degraded", "interrupted"})
_STATUS_FAILED = frozenset({"failed", "error"})
_STATUS_NO_WORK = frozenset({"skipped", "noop", "no_work", "disabled"})

#: Completed/total unit pairs, named explicitly rather than sniffed. ``done <
#: total`` is partial even when the task's own ``status`` says ok, and
#: ``done == 0`` against a positive total is the checked-zero shape that must
#: never read GREEN (the ``horizons_done: 0, total: 4`` case).
_UNIT_PAIRS: tuple[tuple[str, str], ...] = (
    ("horizons_done", "total"),
    ("horizons", "total"),
    ("completed", "total"),
    ("done", "total"),
    ("chunks_done", "chunks_total"),
)

#: Error collections a task uses to report per-item damage. Only consulted on a
#: summary that already speaks the contract — a legacy dict carrying an
#: ``errors`` counter is left alone, because per-item errors are normal there
#: and downgrading them would be exactly the kind of per-task guessing this
#: contract exists to avoid.
_ERROR_COLLECTIONS: tuple[str, ...] = ("errors", "failed_chunks", "failed_phases")


@dataclass(frozen=True)
class TaskVerdict:
    """What a returned summary proves about the run that produced it."""

    verdict: str
    #: Short machine-readable reason, e.g. ``"terminal:partial"``. Stored on the
    #: task's metrics hash so an operator reading a degraded task sees WHY.
    reason: str
    #: True when the summary carried explicit terminal truth (a recognized
    #: terminal / status / unit pair). False only for the legacy shapes, where
    #: the verdict is a statement about our knowledge, not about the run.
    authoritative: bool

    @property
    def is_green(self) -> bool:
        """Only a complete run earns GREEN."""
        return self.verdict == COMPLETE

    @property
    def blocks_success(self) -> bool:
        """Must this verdict be kept out of the completion-success counter?

        Legacy (non-authoritative) unknowns are exempt: they are recorded as
        before so ~100 pre-contract tasks keep a usable health surface. Their
        run is stamped ``unverified`` instead of claiming proof.
        """
        return self.verdict in NOT_GREEN and (
            self.authoritative or self.verdict != UNKNOWN
        )


_LEGACY = TaskVerdict(UNKNOWN, "no_terminal_fields", authoritative=False)


def _as_str(value: Any) -> str | None:
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def _as_int(value: Any) -> int | None:
    # bool is an int subclass; a boolean unit count is a poisoned shape, not a 0/1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _has_damage(summary: dict) -> str | None:
    """Name of the first non-empty error collection, if any."""
    for key in _ERROR_COLLECTIONS:
        value = summary.get(key)
        if isinstance(value, (list, tuple, set, dict)) and len(value) > 0:
            return key
        count = _as_int(value)
        if count is not None and count > 0:
            return key
    return None


def _unit_verdict(summary: dict) -> TaskVerdict | None:
    """Partial when a named completed/total pair says the run fell short."""
    for done_key, total_key in _UNIT_PAIRS:
        if done_key not in summary or total_key not in summary:
            continue
        done = _as_int(summary.get(done_key))
        total = _as_int(summary.get(total_key))
        if done is None or total is None or total <= 0:
            continue
        if done < total:
            return TaskVerdict(
                PARTIAL, f"units:{done_key}={done}/{total}", authoritative=True
            )
    return None


def _phase_ledger_verdict(ledger: dict) -> TaskVerdict:
    """``precompute_calibration_main``: terminal AND durable generation.

    ``health_for`` in ``calibration_phase_ledger`` already refuses GREEN when
    the ledger write failed or the artifact generation is missing. Consume that
    verdict rather than re-deriving it — a run that completed every phase but
    could not persist its own telemetry is UNKNOWN, never a success.
    """
    terminal = _as_str(ledger.get("terminal"))
    health = _as_str(ledger.get("health"))

    if terminal in _TERMINAL_FAILED or health == "red":
        return TaskVerdict(FAILED, f"ledger:terminal={terminal}", authoritative=True)
    if terminal in _TERMINAL_NO_WORK:
        return TaskVerdict(UNKNOWN, f"ledger:terminal={terminal}", authoritative=True)
    if terminal in _TERMINAL_COMPLETE:
        if health == "green":
            return TaskVerdict(COMPLETE, "ledger:complete+green", authoritative=True)
        # Complete phases, no durable generation (or no ledger write): the
        # build happened, the artifact operators read did not.
        return TaskVerdict(
            UNKNOWN, f"ledger:complete_without_green(health={health})", authoritative=True
        )
    if terminal in _TERMINAL_PARTIAL:
        return TaskVerdict(PARTIAL, f"ledger:terminal={terminal}", authoritative=True)
    return TaskVerdict(UNKNOWN, f"ledger:terminal={terminal}", authoritative=True)


#: Tasks whose returned summary is CONTRACT-BEARING — the explicit
#: compatibility adapters Item 0 requires before a verdict may gate health.
#:
#: Enforcement is opt-in for a reason. A ``status`` key is not a terminal
#: across this codebase: ``espn_sync`` returns ``{"status": "no_live_games"}``
#: on an empty slate, ``data_quality_watchdog`` returns
#: ``{"status": "green"|"amber"|"red"}`` as its FINDING, and half a dozen
#: backfills return ``{"status": "nothing_to_backfill"}`` when there is
#: genuinely nothing to do. Reading those as terminals would trade one false
#: GREEN for thirty false REDs — the same crying-wolf failure the grid health
#: score was retired for. Tasks join this set when their summary has been read
#: and shown to carry real terminal truth.
ENFORCED_TASKS = frozenset({
    "calibration_prices",              # terminal + stopped_at + errors
    "compute_time_horizon_calibration",  # status + horizons_done/total
    "precompute_calibration_main",     # phase_ledger.terminal + .health
    "coverage_metrics",                # terminal + published + failed_chunks
    # CAL-P008 (#683): terminal from `_trade_backfill_terminal`. Added because
    # this task is the exact false-GREEN shape 300H was built for and was not
    # covered: 500 fetched, 500 empty, 0 snapshots, recorded healthy, every 6h
    # for ten weeks while the P0 it serves stayed open.
    "kalshi_trades",                   # terminal + errors
    # #1835 (CAL-P051): terminal from `_precompute_bookmaker_calibration`.
    # Same shape as kalshi_trades above and the same cost: the writer sat behind
    # backfill_winners' first budget guard and never ran, its 24h key expired,
    # and an entire moneyline source vanished from the published curve with no
    # source, no log and no alarm. Enrolled so a starved, empty or unwritten run
    # reads NOT-GREEN instead of being recorded as a bare returning invocation.
    "bookmaker_calibration",           # terminal + published + errors
    # #1586 (queue 355): the cliff drain. Enrolled at birth rather than after
    # an incident, because its failure mode is already known and is the one
    # this module exists for: the cohort it sweeps EXPIRES, so a run that
    # fetched nothing and a run with nothing left to fetch look identical from
    # outside and mean opposite things. Its `terminal` distinguishes them —
    # `complete` only when the window is caught up, `failed` when the watermark
    # could not be persisted (unresumable progress will simply be redone).
    "kalshi_cliff_drain",              # terminal + errors + watermark
    # #1798 / ruling 048 (queue 364). Enrolled FROM BIRTH, per #1884, and this is
    # the task that most needs it: it exists to make an accepted-but-unmeasured
    # cost visible, so a run of it that reads GREEN while reconciling nothing
    # would restore exactly the blindness it was built to end. Its terminal is
    # `no_work` — never `complete` — whenever `reconciled == 0`, and it carries
    # `measured: false` + `terminal: failed` when the census itself could not run,
    # so "there is nothing to drain" and "I could not look" stay distinct.
    "reconcile_unanchored_events",     # terminal + measured + census + errors
    # #1912 (CAL-P065) — the two halves of the Polymarket ownership hole,
    # enrolled TOGETHER because separately each looked fine. The Gamma rail
    # discarded 9,748 markets a run as `unsupported_lookup` to a CLOB rail
    # whose scheduled cohort predicate could not select them; both reported
    # `health: healthy`, `failures_24h: 0`, `last_verdict: unverified`.
    #
    # Enrolment alone would have changed NOTHING, and that is worth stating
    # plainly because it is the trap in this file: neither rail emitted a
    # `terminal`, so `_classify` returned the non-authoritative legacy unknown,
    # whose `blocks_success` is False. They join the set in the same change
    # that gives them terminals — `gamma_terminal` and `clob_terminal` in
    # `app/utils/pm_market_ownership.py`. Registered prediction P-10: both go
    # NOT-GREEN within 24h of deploy with no change to what they do.
    "polymarket_winners",              # terminal + handoff + errors
    "clob_resolve_drain",              # terminal + owned_backlog + errors
    # #1866 (LAT-P067, Option D): the typeahead index builder and its D4
    # sentinel. Both enrolled AT BIRTH, with real terminals, for the same reason
    # kalshi_cliff_drain was: the failure mode is already known and it is this
    # module's founding shape. The builder is a resumable sweep, so "caught up"
    # and "ran out of budget a third of the way through" are indistinguishable
    # from outside — its `terminal` is `complete` only when every family reached
    # its end, `partial` on a budget stop, and `failed` when the cursor could not
    # be persisted (progress made, silently unresumable). The sentinel guards a
    # SECOND COPY OF TRUTH and returns `failed` when drift exceeds threshold, so
    # a drifting index cannot read GREEN; an empty index returns `no_work`
    # (authoritative unknown) rather than 100% drift, because the backfill not
    # having run yet is not drift.
    #
    # Enrolling WITHOUT a terminal would be a no-op — the summary would classify
    # as a non-authoritative unknown and still read GREEN. Both return one.
    "rebuild_typeahead_index",         # terminal + stopped_at + cursor_persisted
    "typeahead_index_sentinel",        # terminal + errors + overall.drift_rate
    # #2007 (CAL-P080): Gate 0's in-dyno twin, enrolled AT BIRTH and — per the
    # trap this file spends thirty lines on — in the same change that gives it a
    # terminal. It is the shape that most needs it: the instrument's ONLY way to
    # lie is to read nothing and report agreement over zero rows, so `terminal`
    # is `complete` for a real `agrees`/`disagrees` and `failed` for every
    # `unmeasurable` — a fold error, an unreadable published payload, or a fold
    # that "succeeded" with zero rows against a population of hundreds of
    # thousands. A gate that cannot measure must not read GREEN.
    "calibration_published_twin",      # terminal + measured + verdict + db_rows
    # UX-P134: the tournament register drift sentinel. Enrolled FROM BIRTH per
    # #1884, because its false-green is already known and is the one this
    # module exists for: a run that compared ZERO registered identities and a
    # run that found no drift both return without error and mean opposite
    # things. Its `terminal` separates them — `no_work` when nothing was
    # watched, `failed` when every watched tournament errored, `complete` only
    # when a comparison actually happened. Finding drift is `complete`: the
    # sentinel's job is to notice, and noticing is success.
    "tournament_register_sentinel",    # terminal + tournaments + errors
    # #2007 (CAL-P084): the beat gauge sampler. Enrolled AT BIRTH with terminals,
    # and it is the purest instance of this module's founding shape yet — a
    # SAMPLER's failure mode is not an error, it is running forever and capturing
    # nothing, which is `kalshi_trades` exactly (500 fetched, 500 empty, GREEN
    # every 6h for ten weeks). Its terminals: `complete` only when the current
    # beat is in the ring, `failed` when the ledger could not be read / a
    # required gauge was absent / the ring could not be written, and `partial`
    # when the ledger reads fine but no beat has landed in over two periods —
    # the sampler working over a producer that has stopped is the one state that
    # would otherwise look identical to health.
    "calibration_beat_gauge_sampler",  # terminal + appended + summary + ledger_age_s
    # #2199: the futures price refresher. Enrolled AT BIRTH with a terminal, and
    # it exists BECAUSE of a false green — two discovery polls reported success
    # for weeks while 900 of the 907 high-value tier-1 open futures markets went
    # uncaptured, including every marquee championship field. A refresher that
    # inherited that blindness would be worse than none: it would look like the
    # fix. So a run that attempted markets and wrote zero snapshots is `failed`,
    # not `complete`; a budget- or error-truncated run that did write is
    # `partial`; and `no_work` covers both "nothing was stale" and "everything
    # stale was already attempted this window", which are opposite states and are
    # given different `reason`s rather than one shared silence.
    "futures_price_refresh",           # terminal + snapshots_written + remaining_stale
    # UX-P143 / CERT C-UX-P139-GRID-REGISTER-1 [P2]: the two rails that keep the
    # tournament hub current. Enrolled in the SAME change that gives them
    # terminals, per the trap thirty lines up — the cert found them calling
    # `_tracked_run` with no terminal at all, so `verdict_for` returned the
    # non-authoritative legacy unknown and both read GREEN by default.
    #
    # They need it more than most, because their failure does not show: a dead
    # price refresh does not blank the grid, it lets every number on it AGE, and
    # a dead results sync does not show a wrong score, it shows none. The page
    # looks the same either way. `tournament_price_refresh` returns `failed` for
    # an unreadable register, a fetch that raised, zero markets returned, a write
    # that raised, and zero snapshots written; `no_work` for a register that pins
    # no Polymarket identity (a retired tournament is honest, and still not
    # GREEN). `tournament_results_sync` returns `failed` when nothing reached the
    # cache and `complete` with a populated `errors` list — hence PARTIAL — when
    # only some tours landed.
    "tournament_price_refresh",        # terminal + reason + snapshots_written
    "tournament_results_sync",         # terminal + reason + written + errors
    # #2077 (queue 419): the nightly settlement-capture sweep. Enrolled AT BIRTH
    # per #1884, and — per the trap this file spends thirty lines on — in the
    # same change that gives it a beat, because the terminal it needs already
    # exists: `settlement_sweep_runner._verdict` was written to separate the
    # FOUR zeros before there was anything to enforce them.
    #
    # Those four are why enrolment matters here rather than being paperwork. A
    # sweep over an expiring population has two different zeros that look
    # identical from outside and mean opposite things: `no_work/all_captured`
    # ("every cohort row is already captured") and `failed/total_loss`
    # ("selected 1,200, captured 0"). A third, `partial`, is the one that would
    # otherwise rot quietly — a budget-capped run is BY DESIGN and returns
    # successfully every night, so a lane reading invocations would see a
    # healthy task while the backlog it exists to drain grew. `partial` is
    # NOT-GREEN here, deliberately: the sweep's job is to finish, and a run that
    # left rows behind has not.
    "settlement_sweep",                # terminal + captured + skipped_by_bucket
    # LAT-P137: the Search page's category-census producer. Enrolled AT BIRTH
    # per #1884, in the same change that gives it a beat, and for the reason
    # this module exists rather than for tidiness: a warmer's failure is
    # INVISIBLE from the surface it protects. The route still answers 200 with a
    # served payload whether or not this task ever ran — it just answers in
    # 1,365 ms instead of 28 ms, to whoever happens to arrive after the mirror
    # passes its serve ceiling. Nothing else on the fleet would notice, which is
    # precisely the arrangement LAT-P122 shipped and this queue is repairing.
    #
    # Its terminal distinguishes the two zeros a warmer can produce: `complete`
    # only when the census reads BACK with a `created_at` this run wrote, and
    # `failed` when the build raised, timed out, or was written into a Redis
    # that did not keep it. "The build returned" is not "the next reader is
    # covered" (gotcha #53).
    "warm_futures_categories",         # terminal + published + created_at
    # LAT-P138 (#1249 follow-up): the team prop-families producer and the
    # per-team rebuild it dispatches. Enrolled AT BIRTH per #1884, in the same
    # change that gives them a beat and a terminal, because a warmer's failure is
    # INVISIBLE FROM THE SURFACE IT PROTECTS — the route answers 200 either way,
    # just 2.6-16.8 s instead of milliseconds, and the only symptom is a slow page
    # nobody is timing.
    #
    # The two zeros this separates: `warm_prop_families` returning
    # `dispatched: 0` because every team was already locked by a reader-triggered
    # rebuild (fine) versus because the reachable-set query failed (`failed`,
    # `selected: 0`). And `refresh_prop_families` returning without writing,
    # which is the one that would otherwise rot: a DEGRADED build (statement
    # timeout) deliberately does not write, so the mirror is exactly as old as
    # before and the pass reads `failed`, never `complete`.
    "warm_prop_families",              # terminal + selected + dispatched
    "refresh_prop_families",           # terminal + rebuilt + degraded
    # LAT-P193: the image-dimension backfill. Enrolled AT BIRTH per #1884, in the
    # same change that gives it a terminal, because it is a bounded sweep over a
    # finite population and therefore has this module's founding shape: a run
    # that sized every URL it selected and a run whose image host was
    # unreachable both return a tidy counter dict and mean opposite things. Its
    # terminal separates them — `no_work` when the population is drained (the
    # steady state, and honestly not GREEN), `complete` when every selected URL
    # was measured, `partial` on a mixed pass, and `failed` when it selected
    # work and measured none of it. The last one is the one that would rot:
    # every consumer treats a NULL dimension as "fall back to the old
    # behaviour", so a permanently failing backfill breaks nothing visible and
    # would simply never finish, quietly, forever.
    "backfill_image_dims",             # terminal + urls + measured + failed
    # CAL-P998 / D47 (#2771): the Kalshi resolution-window sweep, enrolled AT
    # BIRTH and — per the trap this file spends thirty lines on — in the same
    # change that gives it a terminal, because enrolment without one is a no-op.
    #
    # It has this module's founding shape twice over. Its population EXPIRES
    # (Kalshi purges market data at >=74/<86 days), so a batch that resolved
    # nothing at the venue and a batch with nothing left to resolve return the
    # same tidy counter dict and mean opposite things. And its own zero-yield is
    # a normal return value with two meanings: `complete` when the eligible set
    # is genuinely empty, `partial` when rows WERE selected and none could be
    # written — the batch spent its whole slot on rows the venue would not
    # resolve, the population did not move, and the next run selects the same
    # head. `failed` is reserved for every selected row erroring, which is an
    # outage and must not read as a drained population.
    #
    # What would rot without this: the sweep is the only thing that can correct
    # a row Kalshi has already finalized (gotcha #33 — the open-market poll can
    # never re-enumerate one), so a permanently inert beat breaks nothing
    # visible and simply lets dead last-trade prices keep rendering as live.
    "kalshi_resolution_window",        # terminal + candidates + writes_applied
    # #2907 (authority/049). Enrolled in the same change that gives it a
    # terminal, per the trap two entries up: enrolment without one buys nothing.
    #
    # This task ran hourly for its whole life and wrote ZERO rows — measured
    # 2026-09-06, 0 of 2,610 events carried `statpal_injuries`. It asked
    # `v2/soccer/injuries`, which 404s (the v2 name is `injuries-suspensions`),
    # and `_get` turns every 404 into None, which the caller turned into `[]`,
    # which is also what "nobody is hurt today" looks like. A dead endpoint and
    # a quiet day were the same summary, so the health surface had nothing to
    # go on and reported a returning invocation for months.
    #
    # Its terminal is `failed` whenever a SUPPORTED sport could not be read, and
    # `complete` otherwise — including when the venue serves no injury path for
    # a sport at all, which is a fact about the venue and not a failed run.
    "statpal_injuries",                # terminal + fetch_failures
})


def classify_summary(result: Any) -> TaskVerdict:
    """Map a task's returned value to a :class:`TaskVerdict`. Never raises."""
    try:
        return _classify(result)
    except Exception:  # noqa: BLE001 — a contract that can crash a task is worse
        return TaskVerdict(UNKNOWN, "classifier_error", authoritative=False)


def verdict_for(task_name: str, result: Any) -> TaskVerdict:
    """The verdict ``_tracked_run`` acts on, for this task label.

    Outside :data:`ENFORCED_TASKS` the classification is still computed and
    carried in the reason (so an operator can see what the contract WOULD have
    said, and adding the task to the set is a one-line change), but the verdict
    is non-authoritative ``unknown`` — the pre-300H recording, unchanged.
    """
    verdict = classify_summary(result)
    if task_name in ENFORCED_TASKS:
        return verdict
    return TaskVerdict(
        UNKNOWN, f"not_enforced({verdict.verdict}:{verdict.reason})", authoritative=False
    )


def _classify(result: Any) -> TaskVerdict:
    if not isinstance(result, dict):
        # Includes None and the ``{"result": "..."}`` shim _tracked_run wraps a
        # scalar return in. An invocation that returned is not proof of work.
        return TaskVerdict(UNKNOWN, "non_dict_return", authoritative=False)

    # --- adapter: durable phase ledger (precompute_calibration_main) ---------
    ledger = result.get("phase_ledger")
    if isinstance(ledger, dict) and ("terminal" in ledger or "health" in ledger):
        return _phase_ledger_verdict(ledger)

    terminal = _as_str(result.get("terminal"))
    status = _as_str(result.get("status"))

    if terminal is None and status is None:
        return _LEGACY

    # Unit pairs are only read on a summary that already speaks the vocabulary.
    # A legacy dict carrying ``{"completed": 5, "total": 12.4}`` (seconds, in at
    # least one task) must not be reinterpreted as a shortfall.
    units = _unit_verdict(result)

    # --- explicit failure wins over everything ------------------------------
    if terminal in _TERMINAL_FAILED:
        return TaskVerdict(FAILED, f"terminal:{terminal}", authoritative=True)
    if terminal is None and status in _STATUS_FAILED:
        return TaskVerdict(FAILED, f"status:{status}", authoritative=True)

    # --- a run that banked nothing proves nothing ---------------------------
    if terminal in _TERMINAL_NO_WORK:
        return TaskVerdict(UNKNOWN, f"terminal:{terminal}", authoritative=True)
    if terminal is None and status in _STATUS_NO_WORK:
        return TaskVerdict(UNKNOWN, f"status:{status}", authoritative=True)

    # --- shortfall in named units beats an optimistic status ----------------
    if units is not None:
        return units

    if terminal in _TERMINAL_PARTIAL:
        return TaskVerdict(PARTIAL, f"terminal:{terminal}", authoritative=True)
    if terminal is None and status in _STATUS_PARTIAL:
        return TaskVerdict(PARTIAL, f"status:{status}", authoritative=True)

    complete = terminal in _TERMINAL_COMPLETE or (
        terminal is None and status in _STATUS_COMPLETE
    )
    if not complete:
        # Speaks the vocabulary, but with a word we do not know. Do not guess.
        label = f"terminal:{terminal}" if terminal else f"status:{status}"
        return TaskVerdict(UNKNOWN, f"unrecognised:{label}", authoritative=True)

    # --- a complete terminal still has to survive its own caveats -----------
    damage = _has_damage(result)
    if damage:
        return TaskVerdict(PARTIAL, f"complete_with:{damage}", authoritative=True)
    if result.get("stopped_at"):
        return TaskVerdict(
            PARTIAL, f"complete_but_stopped_at:{result['stopped_at']}", authoritative=True
        )
    # ``published`` is only consulted when the task reports it. A task that
    # publishes an artifact and says it did not is not complete, whatever its
    # terminal says.
    if "published" in result and not result.get("published"):
        return TaskVerdict(PARTIAL, "complete_without_publish", authoritative=True)

    return TaskVerdict(COMPLETE, f"terminal:{terminal or status}", authoritative=True)


# =============================================================================
# Worker shutdown — CAL-P081 (#2052, #2007)
# =============================================================================
#
# A ``SystemExit`` reaching a task is never the task's fault. Nothing in
# ``app/`` raises one (verified by grep across the package); it arrives from the
# runtime, and in a Celery prefork worker on Heroku that means the child is
# being torn down — a deploy, a dyno cycle, a manual restart.
#
# Recording it as a thrown FAILURE is the same defect as #2052's cancelled unit,
# one layer up: ``consecutive_failures`` climbs against a build that was working
# and was interrupted. On 2026-08-20 ``precompute_calibration_main`` carried
# ``consecutive_failures: 2`` and ``last_error: "-241"`` — a bare ``str(exc)``,
# ambiguous between ``KeyError(-241)``, ``Exception(-241)`` and an exit code, on
# a task that had been killed by a deploy.
#
# NAMING IT COST A MANUAL CROSS-REFERENCE AGAINST ``heroku releases``, TWICE.
# The correlation is unambiguous once you have both halves — the failure at
# 19:35:48Z against release v3877 at 19:35:24Z (+24s), and the earlier one at
# 16:16:18Z against v3873 at 16:16:02Z (+16s) — and neither half was in the
# record. Heroku already exports ``HEROKU_RELEASE_VERSION`` and
# ``HEROKU_RELEASE_CREATED_AT`` into the dyno's environment, so the second half
# can simply be written down at the moment it is true. A release seconds old at
# the instant of a shutdown IS the attribution.


def _release_facts(now: float | None = None) -> dict[str, Any]:
    """What release this dyno is running, and how old it was just now.

    Every field is either read from the environment or omitted. ``None`` where a
    variable is absent is deliberate: outside Heroku (CI, a laptop) there is no
    release to name, and inventing "unknown" would let a local run look like a
    dyno that failed to report.
    """
    import os
    from datetime import datetime, timezone

    facts: dict[str, Any] = {
        "release_version": os.getenv("HEROKU_RELEASE_VERSION"),
        "slug_commit": (os.getenv("HEROKU_SLUG_COMMIT") or "")[:8] or None,
        "dyno": os.getenv("DYNO"),
    }
    created = os.getenv("HEROKU_RELEASE_CREATED_AT")
    if created:
        facts["release_created_at"] = created
        try:
            stamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
            reference = (
                datetime.fromtimestamp(now, tz=timezone.utc)
                if now is not None
                else datetime.now(timezone.utc)
            )
            facts["release_age_s"] = int((reference - stamp).total_seconds())
        except (ValueError, TypeError):
            # A malformed stamp is reported as unparseable rather than dropped —
            # "we could not read the release time" and "there is no release
            # time" are different facts (ruling 075, second clause).
            facts["release_age_reason"] = "unparseable"
    return facts


def describe_worker_shutdown(exc: BaseException, *, now: float | None = None) -> dict[str, Any]:
    """The terminal for a task the runtime interrupted. Facts only.

    Returns the ``result_summary`` for :func:`record_task_incomplete`. It states
    the exception class, its code, and the release this dyno is running — and it
    stops there. It does NOT conclude "a deploy killed this", because a dyno also
    restarts for a manual bounce, a platform migration and a memory quota, and a
    summary that names the cause it happens to expect is how the next unfamiliar
    cause gets read as the familiar one. ``release_age_s`` is the number that
    settles it, and a reader can settle it in one glance instead of two tools.
    """
    code = getattr(exc, "code", None)
    return {
        "terminal": "interrupted",
        "reason": f"{type(exc).__name__}({code!r})",
        "exception_class": type(exc).__name__,
        "exit_code": code,
        **_release_facts(now=now),
        "note": (
            "The worker was torn down mid-task. This is NOT a task failure and "
            "does not advance consecutive_failures. A release_age_s in the low "
            "tens of seconds means the teardown was this release; a large one "
            "means it was not, and the cause is elsewhere (dyno cycle, quota, "
            "manual restart)."
        ),
    }
