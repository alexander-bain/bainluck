"""Admin repair rail — REPAIRS AS ENDPOINTS, never incantations (Queue #247 Item 5).

Three days of failed detached one-offs (#1220/#1229/#1230) proved the gotcha-#48
class is a pattern, not bad luck: a heroku one-off dyno silently no-ops in the
sandbox, `cd backend` no-ops under PROJECT_PATH=backend, ANY(:ids)/UPDATE…FROM roll
back with no readable stdout, and the only way to know if a repair ran is a
follow-up db-query. This rail replaces the incantation with a single call that is
**executable AND self-verifying**: every repair runs inside the web dyno on a
transactional session and RETURNS its own before/after census in the response body.

    POST /api/admin/repairs/{name}?apply=false   # dry-run: census + plan, no writes
    POST /api/admin/repairs/{name}?apply=true    # commit + return after-census

    name ∈ { season-series | inverted-events | tt-retag | team-identity-merge
             | event-final-scores | resolved-shape-census
             | winner-field-coherence | reachability-census
             | prop-threshold-cliff-census | overlap-trading-census
             | winner-field-repair | event-team-binding
             | kalshi-settlement-status | statpal-blank-ids
             | kalshi-fabricated-loss-census | kalshi-fabricated-loss
             | polymarket-evidence-census | polymarket-evidence }
    (the registry below is authoritative; this list had already drifted two
     censuses behind it, so a reader who trusted it would have concluded a
     deployed rail did not exist — the same class of error as trusting a
     handoff file over the ref. Re-synced 2026-08-12 with the registry; if you
     add a repair, add it HERE in the same commit — a third drift would prove
     the comment above was decoration.)

Repairs whose signature declares ``limit`` / ``sport`` / ``newest_first`` /
``offset`` / ``after_id`` / ``after_date`` / ``plan_hash`` / ``expected_blank``
also accept those as query params; the dispatcher passes through only what a
given repair's signature actually names.

``after_id`` + ``after_date`` are a KEYSET cursor, added in CAL-P058 because a
repair that removes rows from its own population cannot be paged with an offset
— the offset skips as many untouched rows as the last page repaired
(C-CERT-1852). ``plan_hash`` is the content address of a reviewed dry-run: for a
repair that declares it, an ``apply=true`` without it is refused, because a
dispatcher that cannot tell an attended plan from a first-ever call is not a
gate.

Auth: Bearer $ADMIN_TOKEN (or ?secret=). Dry-run is the default — you must pass
apply=true to write. Each repair's core is a session-taking ``repair()``/
``run_*`` shared with its committed CLI script, so the endpoint and the script can
never drift.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db_rw
from app.routes.admin_utils import _check_admin_secret

router = APIRouter()

# name → (module path, callable name). Each callable is ``async fn(session, apply)``.
_REPAIRS = {
    "season-series": ("scripts.repair_season_series_mislinks", "repair"),
    "inverted-events": ("scripts.repair_inverted_completed_at", "repair"),
    "tt-retag": ("scripts.retag_table_tennis", "repair"),
    "team-identity-merge": ("app.utils.team_merge", "run_team_identity_merge"),
    # CAL-P002: settled events frozen on a NON-final score (we held BOS 3-1 where
    # the real final was 6-3). Bounded by (sport, date) GROUPS — re-invoke while
    # ``groups_remaining > 0``. Accepts ?limit=&sport=&newest_first=.
    "event-final-scores": ("scripts.repair_event_final_scores", "repair"),
    # Dry-run-ONLY census of shape drift on resolved markets (#284 Item 2). It
    # never writes — ``apply`` is ignored; a real resolved rewrite is a separate
    # CALIBRATION_POPULATION_VERSION-bumped queue.
    "resolved-shape-census": (
        "app.tasks.backfill_market_shapes",
        "census_resolved_market_shapes",
    ),
    # CAL-P006 (#1527): dry-run-ONLY census of winner-field coherence violations
    # on mutually-exclusive markets (>1 winner, and/or >1 near-certain leg). Walks
    # a bounded market-id WINDOW per call — re-invoke with ?offset=<next_offset>
    # until ``exhausted``. Accepts ?limit=&offset=&newest_first=. Never writes:
    # repairing the standing population is a separate, authority-gated queue.
    "winner-field-coherence": ("app.tasks.census_winner_fields", "census"),
    # CAL-P012 (#1544): dry-run-ONLY count of the reachability tiers CAL-P011
    # named — how much of the ungraded remainder is provably purged upstream
    # versus still recoverable. Walks a bounded outcome-id WINDOW per call
    # (unbounded aggregates over ``futures_outcomes`` time out); re-invoke with
    # ?offset=<next_offset> until ``exhausted``. Accepts ?limit=&offset=.
    # Never writes: ``apply`` is accepted and ignored.
    "reachability-census": ("app.tasks.census_reachability", "census"),
    # CAL-P018 (#1089): dry-run-ONLY per-series cliff census for Kalshi
    # prop-threshold outcomes — predicted vs actual by decile, per series, plus
    # how many rows the CURRENT global bands already exclude. Feeds Alex's
    # "tighten per measured cliff, per series" ruling and its published
    # exclusion counts. Walks a bounded outcome-ROW window per call (the full
    # scan, a single-series scan, and even a bare COUNT(*) all exceed the
    # statement timeout — measured twice, 12h apart); re-invoke with
    # ?offset=<next_offset> until ``exhausted``. Accepts ?limit=&offset=.
    # Never writes: ``apply`` is accepted and ignored.
    "prop-threshold-cliff-census": (
        "app.tasks.census_prop_threshold_cliff",
        "census",
    ),
    # CAL-P027 (#1544): dry-run-ONLY overlap census for ruling 011's ladder —
    # per (source, category, volume_state, density band, move band), how many
    # outcomes, and their snapshot rows / observations / distinct price moves.
    # It measures N ("N is measured, not chosen") rather than applying it;
    # applying the ladder needs a population-version bump and is blocked behind
    # the publish. Walks a bounded outcome-ROW window per call — and this is the
    # only census doing correlated snapshot scans, so its window is a FIFTH of
    # the cliff census's; re-invoke with ?offset=<next_offset> until
    # ``exhausted``. Accepts ?limit=&offset=. Never writes: ``apply`` is
    # accepted and ignored.
    "overlap-trading-census": ("app.tasks.census_overlap_trading", "census"),
    # CAL-P007 (#1527), approved by Alex 2026-08-07 under attended capped-batch
    # discipline: the WRITE half. Re-resolves an incoherent single-winner field
    # from CLOB per-leg authority (each leg is its own condition_id), then nulls
    # the impossible captured prices. Fails closed on anything ambiguous. Writes
    # at most APPLY_MARKET_CAP markets per call — a module constant, not a param,
    # so the cap cannot be dialled off mid-run. Accepts ?limit=&offset=.
    # ATTENDED ONLY: never wire this to a beat.
    "winner-field-repair": ("app.tasks.repair_winner_field", "repair"),
    # #1798: events whose home/away ``team_id`` dereferences to a DIFFERENT club
    # than the row's own ``*_team_name`` (153 sides measured across the 2026 MLB
    # season), or to the right club's ``baseball_mlb_preseason`` twin. Detection
    # joins through the FK — every name-to-name check in the codebase passes on
    # these rows, which is why nothing saw them. Re-derives from the row's own
    # name within its own sport_id, exactly one match required; 0 or >1 goes to
    # ``review`` rather than being guessed. Accepts ?limit=&sport= (``since`` is a
    # module default, not a query param — the dispatcher passes through only the
    # four names it declares).
    "event-team-binding": ("app.tasks.repair_event_team_binding", "repair"),
    # CAL-P049 (#1818): adopt Kalshi's OWN finalized settlement status for markets
    # stuck ``status='open'`` past their resolution date. Venue-declared state —
    # the ruled settlement authority — not our judgment, but still a stored-value
    # change, so dry-run by default and capped at APPLY_MARKET_CAP per call.
    # Bounded by BOTH a row window and a 20s wall clock (one Kalshi fetch per
    # market against the web dyno's 30s HTTP timeout), so a partial page is a
    # normal outcome and reports ``stopped_on_time_budget`` rather than pretending
    # to be exhausted. Re-invoke with ?offset=<next_offset> while ``exhausted`` is
    # false. Accepts ?limit=&offset=. ATTENDED ONLY: never wire this to a beat.
    "kalshi-settlement-status": (
        "scripts.repair_kalshi_settlement_status",
        "repair",
    ),
    # Queue 340: ``events.statpal_fixture_id = ''`` -> NULL. 8,272 rows spell
    # "no StatPal id" as an empty string instead of NULL, so every
    # ``IS NOT NULL`` / ``COUNT(col)`` reader over-reports StatPal coverage and
    # the column can never carry a unique index. Bounded id-RANGE batches with a
    # commit each (``events`` is hot). EXACT-MATCH GATE: refuses to apply unless
    # the live before-census blank count equals ``expected_blank`` (default
    # 8272, measured 2026-08-12) — a drifted census means a different
    # population, so the refusal is returned in the result dict, not raised.
    # A deadline-stopped run must be resumed with the NEW count, which is why
    # ``expected_blank`` is a passthrough param.
    # OUT OF SCOPE: the 8 duplicate real statpal ids (16 rows) are REPORTED with
    # their event ids and never written — clearing them is attended, by-name
    # work, and until it lands the column still cannot be made unique.
    "statpal-blank-ids": ("scripts.repair_statpal_fixture_id_blanks", "repair"),
    # CAL-P056 (#1852): the BACKWARD half of CAL-P053. Dry-run-ONLY census of the
    # standing all-loser population — Kalshi markets (2+ legs) where every
    # outcome carries `api_settlement` and NONE is a winner — split by source x
    # mutually_exclusive x retention band, so ruling 054's exclusions are a
    # published number rather than a silent denominator change. One whole-table
    # aggregate over futures_outcomes; bounded by a statement timeout, and a
    # timeout returns `measured: false` with a reason, NEVER a zero. Never
    # writes: `apply` is accepted and ignored.
    "kalshi-fabricated-loss-census": (
        "app.tasks.repair_kalshi_fabricated_loss",
        "census",
    ),
    # CAL-P056 (#1852): the WRITE half. For each market in that population it
    # asks Kalshi for the per-leg declaration and acts PER LEG: `yes` restores
    # the winner, `no` confirms our loss and is left alone (150 of 152 legs in
    # the live specimen — a per-MARKET repair would have corrupted them),
    # `scalar`/""/no-result retracts the fabricated `api_settlement` loss to
    # `ungradeable_result` so it leaves the published curve, and a leg the venue
    # has no ticker for is the ticker-mismatch mechanism: counted, sampled,
    # NEVER written. Retracting is the one permitted authority downgrade and it
    # is guarded to the exact badge being corrected. Writes no prices. Dry-run by
    # default, capped at APPLY_MARKET_CAP markets per call, bounded by BOTH a row
    # window and a wall clock.
    # CAL-P058 (C-CERT-1852): the dry-run emits a content-addressed PLAN and
    # `apply=true` consumes it — `?plan_hash=` is REQUIRED, nothing is re-derived
    # at apply time, both write forms are compare-and-set on the exact prior row
    # state the plan recorded, and the run's final step EXECUTES the calibration
    # generation invalidation and reports `success: false` if it cannot prove it.
    # Paging is a keyset: `?after_date=&after_id=` from `next_cursor`; `?offset=`
    # is refused BY NAME because this rail deletes from its own population.
    # Accepts ?limit=&sport=&after_id=&after_date=&plan_hash=.
    # ATTENDED ONLY: never wire this to a beat.
    "kalshi-fabricated-loss": (
        "app.tasks.repair_kalshi_fabricated_loss",
        "repair",
    ),
    # CAL-P060 (#1870): the Polymarket trading-evidence hole. Read-only census
    # of FOUR states — not the three #1870 asked for, because the probe found a
    # market class the venue will not address at any URL, and folding that into
    # "confirmed zero" is the exact error being fixed. Never writes.
    "polymarket-evidence-census": (
        "app.tasks.repair_polymarket_evidence",
        "census",
    ),
    # CAL-P060 (#1870): the WRITE half. Fetches trading evidence for the NULL
    # cohort and records a CONFIRMED ZERO (`volume = 0` + a receipt carrying
    # `fetched_at`) when the venue confirms zero trading, so NULL means
    # "never asked" and nothing else. Writes NOTHING on UNADDRESSABLE (clob 404)
    # or INDETERMINATE (429/5xx/timeout) — gotcha #53 and #36 respectively.
    # Addresses `gamma/events/{id}`, NOT `gamma/markets?offset=`, because that
    # pager caps at offset 2000 and its `order=volume` sorts lexicographically.
    # Oldest-first WITHIN a floor (gotcha #41 / CAL-P009): the ~999 rows
    # measured permanently unaddressable sort first and are excluded by the
    # floor, or they would consume every run forever.
    # Paging is a keyset: `?after_date=&after_id=` from `next_cursor`.
    # Accepts ?limit=&after_id=&after_date=.
    # ATTENDED ONLY: never wire this to a beat.
    "polymarket-evidence": (
        "app.tasks.repair_polymarket_evidence",
        "repair",
    ),
}


@router.post("/repairs/{name}")
async def run_repair(
    name: str,
    request: Request,
    secret: str = Query(None),
    apply: bool = Query(False, description="False (default) = dry-run census only; True = commit"),
    limit: int = Query(None, description="Optional bound, for repairs that accept one"),
    sport: str = Query(None, description="Optional sport-key filter, for repairs that accept one"),
    newest_first: bool = Query(None, description="Optional ordering, for repairs that accept it"),
    offset: int = Query(None, description="Optional resume cursor, for repairs that page"),
    after_id: int = Query(
        None,
        description="Keyset resume cursor (id half), for repairs that page over a "
                    "population their own writes remove rows from. Pass WITH after_date.",
    ),
    after_date: str = Query(
        None,
        description="Keyset resume cursor (date half). Half a keyset is a different "
                    "walk, not a resume, so the repair refuses one without the other.",
    ),
    plan_hash: str = Query(
        None,
        description="Content address of the reviewed dry-run plan, for repairs whose "
                    "apply is bound to a plan an operator actually read. An apply "
                    "without it, or with a stale one, is REFUSED.",
    ),
    expected_blank: int = Query(
        None,
        description="Exact-match census gate, for repairs that require one "
                    "(statpal-blank-ids). Omit to use the repair's measured default.",
    ),
    db: AsyncSession = Depends(get_db_rw),
):
    """Run a committed data repair and return its before/after census.

    Dry-run by default. See module docstring for the repair catalog.
    """
    _check_admin_secret(secret, request=request)

    if name not in _REPAIRS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown repair '{name}'. Available: {sorted(_REPAIRS)}",
        )

    module_path, fn_name = _REPAIRS[name]
    import importlib
    import inspect

    module = importlib.import_module(module_path)
    fn = getattr(module, fn_name)

    # Pass the optional bounds through ONLY to repairs whose signature declares
    # them, so adding a param here can never break an existing repair.
    accepted = inspect.signature(fn).parameters
    extra = {
        k: v
        for k, v in (
            ("limit", limit), ("sport", sport),
            ("newest_first", newest_first), ("offset", offset),
            ("after_id", after_id), ("after_date", after_date),
            ("plan_hash", plan_hash),
            ("expected_blank", expected_blank),
        )
        if v is not None and k in accepted
    }

    try:
        result = await fn(db, apply, **extra)
    except Exception as e:
        # Never leave a half-applied repair committed on an error path.
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Repair '{name}' failed: {e}")

    return {"repair": name, "apply": apply, "result": result}


@router.get("/repairs")
async def list_repairs(request: Request, secret: str = Query(None)):
    """List the available repairs (discovery)."""
    _check_admin_secret(secret, request=request)
    return {"repairs": sorted(_REPAIRS)}


@router.post("/ensure-perf-indexes")
async def ensure_indexes(
    request: Request,
    secret: str = Query(None),
    wait: bool = Query(False, description="True runs inline (may hit the 30s HTTP wall); default queues a Celery task"),
):
    """#1197: build the missing team-route event indexes (home/away team_id + name)
    CONCURRENTLY. Queues a Celery worker task by default (CONCURRENTLY on events can
    exceed the 30s HTTP timeout); pass wait=true to run inline and get the per-index
    result. Idempotent (IF NOT EXISTS)."""
    _check_admin_secret(secret, request=request)

    if wait:
        from app.utils.ensure_indexes import ensure_perf_indexes
        return {"indexes": await ensure_perf_indexes()}

    from app.tasks import ensure_perf_indexes as task
    from app.utils.ensure_indexes import PERF_INDEXES

    r = task.delay()
    return {
        "status": "queued",
        "task_id": r.id,
        "building": [n for n, _ in PERF_INDEXES],
        "note": "CONCURRENTLY in the worker; re-measure warm team-route latency in ~1-2 min",
    }
