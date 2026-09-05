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
             | kalshi-fabricated-loss-restore
             | polymarket-evidence-census | polymarket-evidence
             | pm-never-graded-census | pm-never-graded
             | event-create-from-truth | team-identity-mapping-repair
             | event-espn-id | label-store-converge
             | label-defect-routes
             | polymarket-sport-category-census | polymarket-sport-category
             | polymarket-leg-label-census | polymarket-leg-label
             | authority-id-collisions }
    (the registry below is authoritative; this list had already drifted two
     censuses behind it, so a reader who trusted it would have concluded a
     deployed rail did not exist — the same class of error as trusting a
     handoff file over the ref. Re-synced 2026-08-12 with the registry; if you
     add a repair, add it HERE in the same commit — a third drift would prove
     the comment above was decoration. Re-synced again 2026-08-17, CAL-P065,
     adding the two pm-never-graded entries in the commit that registered them.
     Re-synced again 2026-08-18, queue 369, adding event-create-from-truth in the
     commit that registered it. Re-synced again 2026-08-19, queue 373, adding
     team-identity-mapping-repair in the commit that registered it. Re-synced
     again 2026-08-19, queue 375, adding event-espn-id in the commit that
     registered it — and the two guard tests caught the omission before the
     push, which answers whether this comment is decoration. Re-synced again
     2026-08-20, UX-P112, adding label-store-converge in the commit that
     registered it. Re-synced again 2026-08-21, UX-P118, adding
     label-defect-routes in the commit that registered it. Re-synced again
     2026-09-01, Q495, adding the two polymarket-sport-category entries in the
     commit that registered them. Re-synced again 2026-09-01, Q499, adding the
     two polymarket-leg-label entries in the commit that registered them.
     Re-synced again 2026-09-02, lane1/058, adding authority-id-collisions in
     the commit that registered it.)

Repairs whose signature declares ``limit`` / ``sport`` / ``newest_first`` /
``offset`` / ``after_id`` / ``after_date`` / ``plan_hash`` / ``expected_blank`` /
``population`` / ``probe`` / ``undo_identity`` also accept those as query params;
the dispatcher passes through only what a given repair's signature actually names.

``undo_identity`` (lane1/084, D51) names ONE earlier apply's dated undo record
and puts its rows back. It exists because Alex's D51 lets a lane apply a data
repair unattended *provided* it backs up first and ships a one-command restore:
the restore has to be a real, runnable thing, so it is a parameter on the same
rail with the same auth rather than a paragraph in a handoff note. Dry-run
unless ``apply=true``. Only ``authority-id-collisions`` declares it today.

``probe`` (queue 375) records ONE identity observation of a reviewed population
and returns, for rails that must PROVE stillness before they may census — ruling
095, a census of a moving population is fiction, and it fails invisibly because
such a census returns rows and digests stably. Separate from the derive because
the proof needs reads spanning >300s, and a 300s request is a rail nobody can run.

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
    # published number rather than a silent denominator change. A timeout returns
    # `measured: false` with a reason, NEVER a zero. Never writes: `apply` is
    # accepted and ignored.
    # CAL-P1012 (#3195): it WAS one whole-table aggregate over futures_outcomes
    # and it died at its own bound — measured twice warm against production, so
    # #2528's runbook had no completion test. It is now a WALK over a half-open
    # `market_id` range: one bounded statement per chunk, the width halved on a
    # chunk that trips the bound, accumulated in a durable slot ACROSS calls, and
    # stopped by a wall clock. Read the totals from the call that reports
    # `walk.complete: true`; until then they come back as `partial`, never as
    # `totals`. Resume with ?after_id=<walk.next_after_id> — a cursor that is not
    # the banked one is REFUSED, because a wrong resume double-counts a range.
    # Omitting after_id starts a fresh walk. Accepts ?after_id=.
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
    # CAL-P1008-R (CERT-965): the UNDO for one applied batch of the rail above,
    # as a command rather than a prose SQL sketch. The apply banks the plan's
    # pre-image at a per-plan durable address BEFORE its first UPDATE and
    # refuses to write if it cannot; this reads that receipt back and reverses
    # exactly the leg ids it names. Dry-run by default; ?plan_hash= is REQUIRED
    # and nothing is re-derived — no venue call, no classification, no work SQL.
    # Both arms compare-and-set on the POST-APPLY row state, so a leg something
    # else has changed since (or that the apply itself skipped on drift) fails
    # its predicate, is reported by id and is skipped — never clobbered. Ends by
    # EXECUTING the calibration invalidation and reporting success: false if it
    # cannot prove it. Writes no prices.
    # Accepts ?apply=&plan_hash=.
    # ATTENDED ONLY: never wire this to a beat.
    "kalshi-fabricated-loss-restore": (
        "app.tasks.repair_kalshi_fabricated_loss",
        "restore",
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
    # CAL-P065 (#1912): the 25,264 Polymarket markets NOBODY EVER GRADED. Their
    # `is_winner=false` is the COLUMN DEFAULT, not a verdict — `resolution_source`
    # is NULL on every leg — so a bare zero-winner count cannot tell them from
    # the 3,824 a heuristic actively mis-graded, and the two need OPPOSITE fixes.
    # Read-only census of the WHOLE never-graded population split by category,
    # deliberately not filtered to tennis: 25,264 is tennis ALONE, and promising
    # a drain rate against an unsized population is how the CLOB rail ended up
    # scheduled at 1,200 checks/day against a five-figure backlog. A census
    # timeout returns `measured: false` with a reason, NEVER a zero (gotcha #54).
    "pm-never-graded-census": (
        "app.tasks.repair_pm_never_graded",
        "census",
    ),
    # CAL-P065 (#1912): the WRITE half. Asks the CLOB venue per market and plans
    # ONLY the confident tiers (resolved_direct / resolved_name_match) that also
    # pass the mandatory name-concordance and date-sanity guards; void,
    # ambiguous, integrity-refused and not-at-venue leave with a NAMED verdict
    # and a number (ruling 054 — exclusions are counted, not skipped). The
    # cohort is defined by the ABSENCE of a grade, so the venue's answer is the
    # only thing permitted to crown an outcome: nothing is inferred from a price
    # (gotcha #21). Writes `resolution_source='clob_never_graded'`, a DISTINCT
    # source so the whole cohort is revertible in one predicate. Touches no
    # prices.
    # The dry-run emits a content-addressed PLAN and `apply=true` consumes it —
    # `?plan_hash=` is REQUIRED, nothing is re-derived at apply time, the write
    # is compare-and-set on the exact prior state (`resolution_source IS NULL
    # AND is_winner IS NOT TRUE`), and the calibration invalidation is a
    # PERSISTED DEBT: `success:false` with `legs_written>0` is honest — retry
    # the same plan_hash, do not re-plan (CAL-P062 pattern).
    # Capped at APPLY_MARKET_CAP=40 markets per call, by module constant.
    # ATTENDED ONLY: never wire this to a beat. Ruling 046 — it joins the wave
    # with its OWN read; landing it beside another apply makes both
    # unattributable.
    "pm-never-graded": (
        "app.tasks.repair_pm_never_graded",
        "repair",
    ),
    # Q495 (the drain half of Q493/CERT-663): read-only census of the open
    # Polymarket rows still filed `table_tennis`, split by how many DAYS since
    # ingest last touched them — because staleness IS the argument for the rail.
    # Q493 fixed the classifier and was graded correct on production (44 of the
    # 44 rows the first post-deploy beat re-ingested migrated), but 177 of the
    # 283 rows it did not reach had not been re-ingested in four days, so they
    # cannot self-heal. A census timeout returns `measured: false` with a
    # reason, NEVER a zero (gotcha #54) — a zero here would read as "drained".
    # Never writes: `apply` is accepted and ignored.
    "polymarket-sport-category-census": (
        "app.tasks.repair_polymarket_sport_category",
        "census",
    ),
    # Q495: the WRITE half. Re-asks `gamma/events/{id}` for each mis-filed event
    # and stores the answer of the SHIPPED ingest cascade (`_tags_to_category` +
    # `resolve_event_category`), run byte-for-byte as `_process_event_batch`
    # runs it. It contains NO sport rules of its own — a DB-only rule would be a
    # second classifier free to drift from the poller, and the tags are not
    # persisted, so the venue is the only place the answer exists.
    # Setka/TT-Cup is a CONTROL, not an exclusion: those events ride the same
    # path and the venue's own `Table Tennis` tag keeps them put, landing in
    # `counts["unchanged"]`. A run that changes everything is as suspect as one
    # that changes nothing.
    # Writes `llm_sport_category` (+ `category` on promotion) by Core UPDATE,
    # compare-and-set on the category it selected on, so a concurrent re-ingest
    # is never clobbered. Touches no prices, outcomes or resolution fields.
    # Nothing is written on 429/5xx/timeout (`indeterminate`, #36), on 404
    # (`not_at_venue`), or when the cascade returns None/"other"
    # (`refused_other`) — each is counted, and each zero state gets its OWN
    # terminal rather than one silent success (gotcha #53).
    # Newest-commence-first: gotcha #41's tail-starvation is ACCEPTED and named,
    # because Polymarket EVENT data is durable so the tail cannot rot, and
    # `remaining_events` is reported every call so it is never silent.
    # Paging is a keyset: `?after_date=&after_id=` from `next_cursor`.
    # Accepts ?limit=&after_date=&after_id=.
    # 🔴 Q496: this block used to say `after_commence`, which the dispatcher
    # does not declare. FastAPI drops an unknown query param SILENTLY, so an
    # operator following the comment got an inactive keyset and re-read page ONE
    # forever while the response looked busy. The rail's signature and the
    # forwarding filter always said `after_date`; only the prose was wrong, and
    # no gate covered prose. `tests/test_repair_polymarket_sport_category_q496.py`
    # now fails the build if ANY comment in this file names a param the
    # dispatcher cannot pass.
    # The default `limit` is safe to run as documented: the rail's own budget is
    # derived from the 30s router wall (Q496), so an over-running call returns a
    # partial page WITH its cursor instead of an H12 with no body.
    # Read `scan_exhausted`, NOT `remaining_events`, to know when you are done —
    # the latter counts the suspect category, which legitimately contains the
    # Setka control and so has a positive floor.
    # CERT-667/CERT-670: four terminals mean PAUSED, not finished, and all four
    # hand back a cursor that RETRIES the row rather than stepping over it —
    # `paused_unresolved` (the venue did not answer), `paused_write_timeout` (it
    # answered but the UPDATE did not land inside its budget, almost always a row
    # lock held by the ordinary poller), `paused_target_timeout` (the page
    # SELECT itself did not finish; nothing was examined) and
    # `paused_pool_timeout` (no pooled database connection came free inside the
    # client bound, so the statement never reached PostgreSQL at all — retrying
    # immediately usually just queues behind the same saturation). Re-invoke with
    # `next_cursor` on any of them. None of the four is a verdict on any event.
    # ATTENDED ONLY: never wire this to a beat — it is a drain with an end
    # state, not a standing job.
    "polymarket-sport-category": (
        "app.tasks.repair_polymarket_sport_category",
        "repair",
    ),
    # #1796/#1902 (queue 369): the attended event-CREATE consumer. Alex approved
    # attended CREATE from venue truth as the PATTERN — provider anchors, plan
    # artifact, pre-cert, always attended — and three windows built the plan object
    # while the apply path did not exist on any branch. This is that path.
    # `apply=false&population=1|2` derives from the COMMITTED reviewed truth set
    # (`app/data/event_create_truth_set.json`; handoff is gitignored and therefore
    # absent from the dyno), resolves club anchors 1:1 against `teams` inside the
    # regular-season sport — never through the name->id index, which is the poisoned
    # path (#1918) — runs the live still-missing gate, and persists a
    # content-addressed CreatePlan. `apply=true&plan_hash=` consumes THAT artifact
    # and re-derives nothing.
    # The compare half of the compare-and-set is the EXISTENCE CHECK and it lives
    # INSIDE the INSERT (`WHERE NOT EXISTS`), because a check in front of the write
    # is a read of a world the write then changes. rowcount 0 is a named finding
    # (TRUTH_ID_ALREADY_PRESENT) that retires ONE row and never its siblings — the
    # ordinary pipeline creating a game between review and apply is the system
    # working. Keyed on the provider id throughout, so a doubleheader is two rows.
    # Capped at APPLY_CREATE_CAP=50 rows and a 20s wall clock per call; the gate
    # makes it resumable with the SAME plan_hash, so no cursor is needed.
    # Accepts ?population=&plan_hash=. ATTENDED ONLY: never wire this to a beat.
    "event-create-from-truth": (
        "app.tasks.create_events_from_truth",
        "repair",
    ),
    # #1918 queue 373: the attended MAPPING consumer. Re-points the 130 reviewed
    # `team_identity_mapping` rows whose team_id names a different club than
    # their source_name. Declares `plan_hash`, so apply=true without one is
    # refused. Same contract as event-create-from-truth, one table over.
    "team-identity-mapping-repair": (
        "app.tasks.repair_team_identity_mapping",
        "repair",
    ),
    # #1947 queue 375 (SPEC-Q370): the attended `events.espn_id` CORRECTION
    # consumer. Window 368 found the gap and READY-lane1-369 named it — "population
    # 1 has NO APPLY PATH; no attended consumer writes events.espn_id" — which is
    # the same shape as the CREATE gap window 369 closed, one table over. A rail
    # with no address is a rail nobody can run, so it is registered here in the
    # same commit that builds it.
    #
    # What differs from event-create-from-truth: the BEFORE state EXISTS, so this
    # is an ordinary UPDATE and the compare is the WHERE clause of the writing
    # statement (`AND espn_id = :wrong_espn_id`) rather than a `WHERE NOT EXISTS`
    # inside an INSERT. rowcount 0 is a named finding, and `FOR UPDATE` is what
    # makes it legible — without it, "the id moved" and "the row is gone" are the
    # same zero.
    #
    # ONE COLUMN: espn_id. Not status, not the scores, not completed_at, not
    # commence_time — ruling (a) withdrew those and #1981's writer owns them.
    # commence_time IS inside the plan's content address (it is how a reviewer
    # knows which game a row is) and is never written. No branch deletes a row
    # (ruling 079).
    #
    # RULING 095 IS ENFORCED HERE, not documented: `apply=false` REFUSES with
    # POPULATION_NOT_STILL until `probe=true` has recorded >= 3 identity reads
    # spanning > 300s with nothing moving. #1947's rows are that ruling's charter
    # case — they flap on a ~2-minute cycle. Probe is a separate call rather than
    # a sleep inside the derive, because a 300s request is a rail nobody can run.
    # Accepts ?population=&plan_hash=&probe=. ATTENDED ONLY: never wire to a beat.
    "event-espn-id": (
        "app.tasks.repair_event_espn_id",
        "repair",
    ),
    # #2693 step 2, lane1/058: ONE GAME, ONE AUTHORITY ID. 196 ESPN event ids
    # worn by 430 `events` rows (measured 2026-09-02), which means `espn_sync`
    # writes one game's status, clock and score onto two fixtures. Asks ESPN who
    # each contested id really is, and takes the id OFF every row that is not
    # that game — `espn_id = NULL`, one nullable column, no merge and no DELETE.
    # Two-call: ?apply=false persists a plan and returns its hash; ?apply=true
    # &plan_hash= consumes THAT plan and re-derives nothing. Accepts
    # ?sport=&limit=&plan_hash=. ATTENDED ONLY: never wire to a beat.
    "authority-id-collisions": (
        "app.tasks.repair_authority_id_collisions",
        "repair",
    ),
    # UX-P112 (#1933 bullet 2): the BACKWARD half of the label-store
    # convergence. The forward half is in `label_pass_verdict`, which now writes
    # its gold label as the verdict is given; this converges the 198 gradeable
    # futures verdicts already in `discover_review_decisions` and invisible to
    # every consumer of the gold set since June. Idempotent by
    # `label_metadata -> 'label_origin' ->> 'source_decision_id'`, which both
    # halves stamp, so it is safe to re-invoke after the deploy. Preserves each
    # verdict's original `created_at` (a backdated corpus that all lands today
    # would move every row inside the trailing window the fail-closed flip
    # criterion is measured over). Accepts ?limit=.
    "label-store-converge": (
        "app.tasks.converge_label_stores",
        "repair",
    ),
    # UX-P118 (#2094): route the already-tagged negative judgments into the
    # defect clusters. UX-P117 wired `defect_route()` into both write paths, but
    # forward-only — the 71 rows already tagged bad/kill keep their reasons and
    # still route nowhere, so `/fixable-interest/clusters` has returned an empty
    # list for the life of the store. Never overwrites an existing
    # `fixable_interest` (a human's ReviewTab `fix_type` outranks an inferred
    # one), rewrites no stored tag (canonicalisation happens on read), and does
    # not set `create_issue_candidate`. The dry run PROJECTS the resulting
    # cluster list using the route's own `_cluster_identity`. Accepts ?limit=.
    "label-defect-routes": (
        "app.tasks.backfill_defect_routes",
        "repair",
    ),
    # Q499 (the residual half of Q492): read-only census of the open Polymarket
    # legs whose outcome name has collapsed onto their market's own name, so the
    # card prints a probability that names no side. Split by
    # `llm_sport_category`, because a bare total cannot tell a drain that is
    # working from one that is only reaching the category the poller happens to
    # rotate through — which is exactly how Q492's partial fix came to be read
    # as complete. A census timeout returns `measured: false` with a reason,
    # NEVER a zero (gotcha #54). Never writes: `apply` is accepted and ignored.
    "polymarket-leg-label-census": (
        "app.tasks.repair_polymarket_leg_label",
        "census",
    ),
    # Q499: the WRITE half. Re-asks Gamma for each collapsed leg BY CONDITION ID
    # and stores the answer of the SHIPPED `_leg_label`, imported from the
    # poller rather than restated — this rail contains no label rule of its own,
    # and a guard fails the build if it grows one. The tempting shortcut
    # (splitting "Venue: X vs Y" on " vs ") is the mutant Q492's own guard was
    # written to catch: it cannot tell which side the price belongs to, which is
    # the whole defect.
    # 🔴 The venue read is TWO requests per batch on purpose: Gamma's
    # `condition_ids` read on `/markets` silently applies a `closed=false`
    # filter, and on a 40-id sample from this cohort the default call returned 7
    # of 40 while the closed pass returned the other 33. A drain built on the
    # default read would have called 82% of its own population missing and
    # looked finished. (Written without the `param=` form on purpose — the Q496
    # guard scans this file for documented params the dispatcher cannot forward,
    # and it caught this comment on the first run.)
    # Writes `futures_outcomes.name` and NOTHING else — `last_updated` is a
    # poller touch-stamp another surface reads as liveness (#2024), so a repair
    # that bumped it would forge an observation. Compare-and-set on the exact
    # name the page selected, so a concurrent re-ingest is counted `raced`,
    # never clobbered.
    # Every leg reaches a NAMED verdict and each is counted (ruling 054):
    # relabelled / unchanged / not_at_venue / no_condition_id /
    # refused_collision (two legs of one market would take the same label) /
    # raced. Nothing is written when the venue does not answer.
    # Terminals mean PAUSED, not finished, and all of them hand back a cursor
    # that RETRIES rather than steps over: `paused_deadline`, `paused_venue`,
    # `paused_target_timeout`, `paused_pool_timeout`, `paused_write_timeout`.
    # Paging is a keyset on `futures_outcomes.id`: `?after_id=` from
    # `next_cursor`. Read `scan_exhausted`, not `remaining_legs`.
    # Capped at APPLY_LEG_CAP=120 legs per call, by module constant — the whole
    # 1,153-leg cohort is ten calls. Accepts ?limit=&sport=&after_id=.
    # ATTENDED ONLY: never wire this to a beat — it is a drain with an end
    # state, not a standing job.
    "polymarket-leg-label": (
        "app.tasks.repair_polymarket_leg_label",
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
    since: str = Query(
        None,
        description="Inclusive lower bound on commence_time (YYYY-MM-DD), for repairs "
                    "that scan a date range. Omit to use the repair's own default.",
    ),
    until: str = Query(
        None,
        description="EXCLUSIVE upper bound on commence_time (YYYY-MM-DD), for repairs "
                    "that scan a date range. This is what makes a reviewed population's "
                    "COMPLETED half addressable separately from its LIVE half — an "
                    "apply is bound to a whole plan by content address, so a half that "
                    "cannot be scoped cannot be applied alone (#1798, queue 374).",
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
    probe: bool = Query(
        None,
        description="Record ONE identity observation of a reviewed population and "
                    "return, for repairs that must prove stillness before they may "
                    "census (ruling 095 — a census of a moving population is fiction, "
                    "and it fails invisibly, because such a census returns rows and "
                    "digests stably). Separate from the derive on purpose: the proof "
                    "needs reads spanning >300s, and a 300s request is a rail nobody "
                    "can run.",
    ),
    population: str = Query(
        None,
        description="Which reviewed population a plan-bound repair acts on "
                    "(event-create-from-truth: '1' or '2'). The plan artifact is "
                    "stored per population, so this selects WHICH approval an "
                    "apply is bound to — it is not a filter.",
    ),
    undo_identity: str = Query(
        None,
        description="Put ONE earlier apply's rows back, for repairs that write a "
                    "dated undo record before they write anything else (D51: a "
                    "repair may be applied unattended because it is reversible). "
                    "The identity is returned as `undo_identity` by that apply. "
                    "Dry-run unless apply=true; it reads the stored record and "
                    "re-derives nothing.",
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
            ("since", since), ("until", until),
            ("plan_hash", plan_hash),
            ("expected_blank", expected_blank),
            ("population", population),
            ("probe", probe),
            ("undo_identity", undo_identity),
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
