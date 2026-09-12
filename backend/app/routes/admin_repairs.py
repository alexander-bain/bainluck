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
             | statpal-fabricated-ids
             | kalshi-fabricated-loss-census | kalshi-fabricated-loss
             | kalshi-fabricated-loss-restore
             | polymarket-evidence-census | polymarket-evidence
             | pm-never-graded-census | pm-never-graded
             | event-create-from-truth | team-identity-mapping-repair
             | event-espn-id | label-store-converge
             | label-defect-routes
             | polymarket-sport-category-census | polymarket-sport-category
             | polymarket-senate-category | kalshi-nhl-prop-category
             | polymarket-leg-label-census | polymarket-leg-label
             | authority-id-collisions | weather-shelf-disease
             | futures-person-seed-purge | golf-round-closing-line
             | kalshi-empty-book-openings
             | kalshi-empty-book-openings-restore
             | pm-ungraded-loss | pm-ungraded-loss-restore
             | kalshi-series-tag-category }
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
     the commit that registered it. Re-synced again 2026-09-09, lane1b/106,
     adding polymarket-senate-category in the commit that registered it.
     Re-synced again 2026-09-09, lane1b/109, adding kalshi-nhl-prop-category in
     the commit that registered it. Re-synced again 2026-09-09, lane1b/116b,
     adding futures-person-seed-purge — NOT in the commit that registered it,
     which is the whole point: the focused D40 gates for #4578 were green and
     the two registry guards live in files that change was nowhere near, so CI
     is what caught it. The comment above is not decoration and the guard is not
     either. Re-synced again 2026-09-10, CAL-P1081, adding
     golf-round-closing-line in the commit that registered it — this time
     before CI had to say so. Re-synced again 2026-09-10, CAL-P1086, adding the
     two kalshi-empty-book-openings entries in the commit that registered them;
     the restore is its own NAME rather than an `undo_identity` parameter
     because its backup is a table, not a dated receipt, so one call puts the
     whole population back however many pages wrote it. Re-synced again
     2026-09-10, CAL-P1088, adding the two pm-ungraded-loss entries in the
     commit that registered them.)

Repairs whose signature declares ``limit`` / ``sport`` / ``newest_first`` /
``offset`` / ``after_id`` / ``after_date`` / ``plan_hash`` / ``expected_blank`` /
``population`` / ``probe`` / ``undo_identity`` / ``band`` / ``band_as_of`` also accept
those as query params; the dispatcher passes through only what a given repair's
signature names.

``undo_identity`` (lane1/084, D51) names ONE earlier apply's dated undo record
and puts its rows back. It exists because Alex's D51 lets a lane apply a data
repair unattended *provided* it backs up first and ships a one-command restore:
the restore has to be a real, runnable thing, so it is a parameter on the same
rail with the same auth rather than a paragraph in a handoff note. Dry-run
unless ``apply=true``. ``authority-id-collisions``, ``statpal-blank-ids``,
``statpal-fabricated-ids`` and ``futures-person-seed-purge`` declare it today.

``probe`` (queue 375) records ONE identity observation of a reviewed population
and returns, for rails that must PROVE stillness before they may census — ruling
095, a census of a moving population is fiction, and it fails invisibly because
such a census returns rows and digests stably. Separate from the derive because
the proof needs reads spanning >300s, and a 300s request is a rail nobody can run.

``band`` (#3257, CAL-P1015) is a PAGING selector for a rail whose population
expires: two ages in days, youngest first, naming which slice of the existing
sort to walk first. It is deliberately not a filter and not a floor — it excludes
no row, changes no verdict, and leaves the measured retention constants alone —
so a rail that accepts it must report band exhaustion and population exhaustion
as two different answers, or a banded drain reads as a finished one.

``band_as_of`` (CERT-1935, CAL-P1018) is the other half of that selector, and the
reason it is a parameter at all is that a band's bounds belong to the WALK while
a page is one request. Two ages are two dates only once you say when from; left
to ``NOW()`` they slide forward on every call while the keyset stays put, and the
rows sharing the cursor's own timestamp end up after the cursor and older than
the new edge — selectable by no page of that walk, and reported as the band being
exhausted. Page one mints the anchor and returns it INSIDE ``next_cursor``; a
banded resume that omits it is refused rather than re-anchored to today.

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
    # D51 (#2963): declares ``undo_identity``. The receipt is written empty
    # before the first write and CO-COMMITTED with each batch, so a partial run
    # is exactly reversible; the restore refuses any row that has since been
    # given a real StatPal id, which is the outcome NULLing it was for.
    "statpal-blank-ids": ("scripts.repair_statpal_fixture_id_blanks", "repair"),
    # #2963, the OTHER half of the same column. `statpal-blank-ids` drains the
    # rows that hold `''`; this one drains the 48 that hold a string we
    # INVENTED — `statpal_live_<home>_<away>`, written by a live-score fallback
    # that CERT-2081 has since closed. A SIBLING and not a parameter on the
    # blanks rail, and the reason is the UNDO, not the predicate: every blank
    # row held the same value, so that restore writes back one constant; these
    # 48 each hold a different string, so this record carries (event_id,
    # prior_value) pairs and its restore writes per row.
    # Membership is `not is_statpal_contest_id(value)`, IMPORTED from
    # `stamp_nfl_statpal_fixtures` — the same predicate that makes the stamper
    # call a row POLLUTED and refuse to write it. One rule, one copy: the rows
    # this clears are exactly the rows that stamper is stuck behind, and
    # clearing them is what lets it write the REAL StatPal id.
    # Gated on ``plan_hash``, not a count: the rows are not interchangeable, so
    # a cardinality gate cannot tell 48 rows from 48 DIFFERENT rows.
    # D51: declares ``undo_identity``; the receipt is written empty before the
    # first write and CO-COMMITTED per row.
    "statpal-fabricated-ids": ("app.tasks.repair_statpal_fabricated_ids", "repair"),
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
    # CAL-P1014 (#3262): a venue 429 is a BUDGET STOP, not a verdict. The page
    # stops there, the refused market is not counted as examined and the cursor
    # does not advance past it, so the resume asks it again — before this, 15 of
    # every 40 markets were recorded `unknown` and stepped over for good. Read
    # `stopped_on_venue_rate_limit`; if it is true on every call, lower `?limit=`
    # (measured 2026-09-05: limit=10 drew no refusals, 20 drew 6, 40 drew 15).
    # CAL-P1015 (#3257): `?band=MIN-MAX` (ages in days, youngest first) pages one
    # slice of the sort first. Measured 2026-09-05: the venue answers NOTHING
    # from 70 to 86 days and everything by 54, so an unbanded drain spends its
    # first ~15 pages on 597 markets that are already purged before reaching the
    # 552-market at-risk tail behind them. `?band=47-67` drains that tail — the
    # only cohort with a deadline — first. It EXCLUDES nothing: `exhausted` is
    # then scoped to the band and `population_exhausted` is reported separately.
    # CAL-P1018 (CERT-1935): a band is two AGES, so its two dates move with the
    # clock while the keyset cursor does not, and a page-two re-measure strands
    # every row sharing the cursor's timestamp between the cursor and the edge
    # that has just passed it. Page one now MINTS a `band_as_of` and hands it
    # back inside `next_cursor`; a banded resume without it is REFUSED rather
    # than silently re-anchored. Paste the whole next_cursor.
    # CAL-P1124 (#3617 item C): the population is now selected AT THE LEG — a
    # Kalshi market holding at least one api_settlement loss — instead of by the
    # three market-shape conjuncts that reached 225 markets and left 1,965
    # behind. ?min_harm= drains the worst-priced cohort first (arm B; it is a
    # threshold and not a re-sort, because sorting on a per-market aggregate
    # re-introduces the #2528 timeout). CAL-P1125 (CERT-2705): ?min_harm= is a
    # COHORT selector exactly as ?band= is, so it scopes the two completion keys
    # the same way — `exhausted_scope` names every selector in force
    # ("min_harm", or "band+min_harm" for both) and `population_exhausted` can
    # only be true when neither is. A drained 90%+ slice is not a drained
    # population, and the attended run must not halt as though it were.
    # Mutually-exclusive markets holding
    # exactly one winner are EXCLUDED by design — their remaining legs lost by
    # exclusion, so retracting them would delete correct rows from the curve.
    # Unlike every earlier version of this rail, the retraction arm now MOVES the
    # published curve, downward, and that is the ship.
    # Accepts ?limit=&sport=&band=&band_as_of=&min_harm=&after_id=&after_date=&plan_hash=.
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
    # #4229 (lane1b/106): the POLYMARKET half of the senate/hockey defect, which
    # the Kalshi backfill at `edf9fe13` does not touch and no poll will ever
    # reach. Six enumerated Polymarket EVENT ids — the "Fed Chair" card #4229 was
    # filed about among them — re-asked at `gamma/events/{id}` and moved to
    # whatever the SHIPPED cascade says, via the sibling rail's own
    # `classify_event_payload`. It has no sport rules of its own.
    #
    # 🔴 Why it is enumerated rather than a category drain like its sibling: the
    # suspect category here would be `hockey`, i.e. tens of thousands of real NHL
    # rows and one venue call each, to move six events. The bound was measured
    # against the VENUE (notice 26), not our mirror: all 74 senate-named
    # Polymarket events stored under a sport were re-asked on 2026-09-09 and 68
    # came back `hockey` — genuinely Ottawa/Belleville. Those 68 are not an
    # exclusion list; the gate refused them on the venue's own answer, which is
    # how this rail proves it is safe instead of asserting it.
    #
    # Includes four RESOLVED events beyond the two the issue names, found by
    # censusing what the rule matches rather than what the defect occupies. Safe
    # because `llm_sport_category` is a taxonomy badge, never a result: no price,
    # outcome, `is_winner` or resolution field is read or written, so "settled
    # means settled" is untouched.
    #
    # Writes `llm_sport_category` ONLY, by Core UPDATE, compare-and-set on the
    # value read. Deliberately NOT `category`: the poller's own `update_set` does
    # not contain it (INSERT-time only), so writing it would make this rail do
    # something ingest never does. Nothing is written on 429/5xx/timeout
    # (`indeterminate`, #36), on 404 (`not_at_venue`), when the cascade returns
    # None/"other" (`refused_other`), or when the venue agrees (`venue_agrees`).
    # D51: every planned row carries its `before` and the payload carries a
    # runnable `restore_sql`, on the dry run as well as the apply.
    # Takes no bounds — the population is the frozen list. ATTENDED ONLY: never
    # wire this to a beat; it is a terminating repair, not a standing job.
    "polymarket-senate-category": (
        "app.tasks.repair_polymarket_senate_category",
        "repair",
    ),
    # #4365 part 2 (lane1b/109): two Kalshi NHL game props stored `basketball`.
    # Same two-gate shape as the certed `repair_kalshi_senate_category` — frozen
    # id bound AND the SHIPPED `_categorize_kalshi_market` independently agreeing
    # per row — with `hockey` as the target, which is why it is a sibling module
    # and not a widening of that one (its `TARGET_CATEGORY` is pinned by a guard
    # forbidding every sport token in its literals).
    #
    # 🔴 The issue called this class "latent, blast radius 0 stored rows". It is
    # 2. `_STAT_TO_SPORT` maps `points` and `assists` to basketball despite both
    # being core NHL stats, and in April 2026 that answered FIRST: `97862989`
    # ("ticker before name rules", 2026-04-22 17:34 -0700) postdates the rows'
    # 2026-04-22 16:45 UTC ingest by ~8h. The ticker was in the map since
    # 2026-03-30 (`2e2b2dba`); it just did not get to speak first. #1888's
    # `coalesce(nullif(existing,'other'), new)` has frozen them since. So the
    # bound is the residue of a closed ordering bug, not of a live one.
    #
    # Measured, not assumed: all 1,609 rows matching the game-prop shape
    # `^.+ (at|vs\.?|@) .+: *(points|assists)` and stored `basketball` were
    # replayed through the shipped classifier; it disagreed on exactly these 2
    # and agreed on the other 1,607, which gate 2 therefore refuses.
    #
    # Reader-visible: `frontend/app/futures/[id]/page.tsx:958-965` builds the
    # end-of-page rail's heading AND its contents from `llm_sport_category`, so
    # both pages currently end in a MORE BASKETBALL rail of college-basketball
    # championships under a settled Penguins/Flyers prop.
    #
    # Writes `llm_sport_category` ONLY. Safe against "settled means settled": a
    # taxonomy badge is never a result, and no price, outcome, `is_winner` or
    # resolution field is read or written. D51: every planned row carries its
    # `before` and the payload carries a runnable `restore_sql`, on the dry run
    # as well as the apply. Takes no bounds — the population is the frozen list.
    # ATTENDED ONLY: never wire this to a beat; it is a terminating repair.
    "kalshi-nhl-prop-category": (
        "app.tasks.repair_kalshi_nhl_prop_category",
        "repair",
    ),
    # #5637 (authority/157, the repair CERT-2737 required): the rows #5637's
    # classifier fix cannot reach. Step 1b sorts an UNMAPPED Kalshi series by the
    # sport tag the venue publishes, which stops the defect being MINTED — but
    # #1888's `coalesce(nullif(existing,'other'), new)` means a row already
    # stamped with a WRONG sport keeps it forever. Measured on production
    # 2026-09-12 over the five families #5637 censused: 28 open rows wrong and
    # frozen (17 basketball incl. 14 NFL "Fantasy Points" and 3 CFL totals,
    # 9 tennis on AFC Wimbledon fixtures, 1 baseball, 1 motorsports), every one
    # a game played 9/12-9/17. 74 more are `other` and converge by themselves.
    #
    # 🔴 PREDICATE, NOT A FROZEN ID LIST — unlike its two enumerated siblings,
    # and for a reason about this defect: the classifier fix is merged but lives
    # in a HEAVY_TASKS path, so it mints nothing until `bainluck-heavy` carries
    # it (notice 48). The population is still GROWING, and an id list measured
    # today would be silently incomplete by apply time. The gate the id lists
    # exist to protect is kept: the SHIPPED cascade must independently agree,
    # per row, at run time.
    #
    # No sport vocabulary of its own — no target category, no ticker literal, no
    # name regex. It cannot know what it will write until the venue answers, and
    # a guard pins that absence. Nothing is written on a venue failure
    # (`indeterminate`, #36 — and the cursor does not advance past it), on a tag
    # we do not model (`no_usable_tag`), when the cascade disagrees
    # (`cascade_disagrees`), on a mapped ticker (`mapped_ticker`, no call made),
    # or when the row is already right (`already_correct`).
    #
    # TWO ARMS. (a) `futures_markets.llm_sport_category`, compare-and-set on the
    # value read. (b) the ghost EVENT the wrong category already minted — CERT-2744
    # blocked the first cut for scoping this out, correctly: search serves EVENTS,
    # so correcting the badge alone leaves `q=Redblacks` returning the game twice.
    # An event is retired (`status='voided'`, never deleted) only on proof it is a
    # duplicate: minted by us (no external_id, kalshi commence source, both team ids
    # NULL, kalshi-only markets), in the WRONG sport, and a real counterpart exists
    # with BOTH team ids bound, same teams either orientation, within 36h, IN the
    # venue's sport. Measured 2026-09-12: 13 candidates, only 4 pass — the other 9
    # are the only row we hold for that match and retiring one would remove the game,
    # not a duplicate. Its markets are then unhooked (`event_id` NULL) so they can
    # reach the real fixture (gotcha #15). Ceiling refuses, never trims.
    # No price, outcome, `is_winner` or resolution field is read or written.
    # D51: every planned row carries its `before` and the payload carries a
    # runnable `restore_sql`, on the dry run as well as the apply.
    # Accepts ?after_date=&after_id= for keyset resumption; page until
    # `scan_exhausted`. ATTENDED ONLY: never wire this to a beat.
    "kalshi-series-tag-category": (
        "app.tasks.repair_kalshi_series_tag_category",
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
    # #4264 / CERT-2358: the disease markets stranded on the `weather` shelf.
    # #4264 widened `misfiled_subject` so the epidemiology arm may correct
    # `weather`, which fixes the CLASSIFIER; it cannot fix a row the ingest never
    # rewrites. Measured 2026-09-09: of the 22 affected open markets, 16 were
    # touched within the hour and converge on the next poll, and 6 have not been
    # re-seen in 1-83 days — including `16630403`, "Hantavirus pandemic in 2026?",
    # page one slot 5, wearing a sun-and-cloud chip. This is that half.
    # Carries NO classification rules: it replays the shipped Polymarket cascade
    # (`_tags_to_category` + `resolve_event_category`) against each row's STORED
    # `category_tags`, so it cannot drift from the poller. It reads stored tags
    # rather than re-asking Gamma (which is what Q495's rail does) precisely
    # because these rows are stale — a venue fetch is the most likely thing to
    # fail here, and a 404 would leave the page-one card wrong under a clean
    # terminal.
    # Parents are classified from their own tags; tagless CHILD sub-markets
    # INHERIT their group parent's answer and are never classified alone, because
    # `_tags_to_category([])` would drop them into the table-tennis and
    # title-fallback arms with a `group_names` list this repair cannot rebuild.
    # D51: the undo record is written to the durable rail BEFORE any row is
    # touched and nothing is written if it does not persist; every write is a
    # compare-and-set on the exact prior state, so a concurrent poll is never
    # clobbered. Restore with `?undo_identity=<id>&apply=true`.
    # Capped at APPLY_CAP=60 by module constant. ATTENDED-OPTIONAL: never wire
    # this to a beat — it is a drain with an end state, not a standing job.
    "weather-shelf-disease": (
        "app.tasks.repair_weather_shelf_disease",
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
    # #4578 (lane1b/116): the BACKWARD half of #4458. Deletes the market legs
    # `seed_persons_from_futures_fields` minted as `kind='person'` — margin
    # ladders ("1+ strokes"), head-to-head legs ("Jon Rahm beats McIlroy and
    # Spieth"), scoring placeholders — 4,913 of 7,471 measured 2026-09-10. The
    # reader harm is alias collapse: 1,450 share the derived alias `strokes`
    # and 1,124 share `round`, and `resolve_alias` picks one arbitrarily.
    # Membership is decided by the SHIPPED `is_plausible_person_name`, imported
    # from `entity_registry`, never by SQL restating its rules — the filing's
    # SQL proxy says 65.8% and the predicate says 67.2%, and a repair that
    # deletes a different set than the guard refuses is one nobody can restore
    # confidently. Two-call: ?apply=false returns a census and a plan_hash;
    # ?apply=true&plan_hash= consumes THAT plan and refuses a stale one.
    # D51: the undo receipt carries every deleted `entities` row, every
    # `entity_aliases` row CASCADE would take, and every `event_participants`
    # .entity_id cleared — staged in the SAME transaction as the delete.
    # Restore with `?undo_identity=<id>&apply=true`; every apply prints the
    # command. Capped at 1,500 rows per call and keyset-paged on entities.id —
    # read `scan_exhausted`, not a remaining count. ATTENDED ONLY: never wire
    # this to a beat — it is a drain with an end state.
    "futures-person-seed-purge": (
        "app.tasks.repair_futures_person_seed",
        "repair",
    ),
    # CAL-P1081 (#938 bug (a), #997): the 286 round-scoped Kalshi golf markets
    # publish their OPENING stamp as a closing line. `KXDPWORLDTOURR1LEAD-HEIO26`
    # prices twenty-three golfers at 0.990 while the venue's own last quote
    # before the round reads 0.070 / 0.350 / 0.380 — the real numbers were in
    # `futures_odds_snapshots` the whole time. Measured 2026-09-10: 2,035
    # outcomes in that state, 1,937 of them inside the published curve, and the
    # `…LEAD` arm's win rate is ~1% at EVERY price decile from 0.03 to 0.95.
    #
    # 🔴 IT INVENTS NO PRICE RULE. `backfill_winners` Part A2 already owns this
    # exact correction (reset where cal = opening and the pre-commence snapshot
    # differs; refill from that snapshot); both halves are budget-gated and the
    # pipeline has been stopping early for weeks (CAL-P1080 measured
    # `partial_budget_guard`, `stopped_before: bookmaker_closing`, 757.8s of an
    # 840s limit). These are not rows A2 judges differently — they are rows it
    # never reached. A guard fails the build if this rail grows a threshold of
    # its own, and a second guard parses the SET clause per assignment.
    # ONE COLUMN: `calibration_probability`. Never `is_winner`,
    # `opening_probability` or `resolution_source` (gotcha #21), and never
    # `last_updated` — the poller's touch-stamp is read elsewhere as liveness
    # (#2024). The closing selector is strictly BEFORE commence_time (ruling
    # 103). Tournament-scoped golf is OUT by an ANCHORED ticker pattern: it
    # measures 2.12/2.42 ECE against these arms' 14.86/8.58, and #938's title
    # wrongly groups the two.
    # D51: every planned row carries its `before` on the dry run as well as the
    # apply, and `restore_sql` is ONE statement — exact because a planned row is
    # by definition one where cal = opening, so restoring from the opening
    # column restores each row's own value. Takes no bounds.
    # ATTENDED-OPTIONAL, and TERMINATING: never wire this to a beat. The durable
    # fix is Part A2 finishing; this drains the backlog it left.
    "golf-round-closing-line": (
        "app.tasks.repair_golf_round_closing_line",
        "repair",
    ),
    # #4745 (CAL-P1086, #997): the accuracy page publishes ~16,960 Kalshi legs
    # at a mean 0.904 that came true 13.1% of the time, because Phase 0c-repair
    # promoted an opening off a book of bid 0.00 / ask 0.98 with no trade —
    # an offer nobody took. `ece46743` put the shipped write guard on the
    # promotion; CERT-2508 BLOCKed it because the already-promoted rows are
    # non-null and a guard keyed on `IS NULL` cannot reach them. This is the
    # reach.
    #
    # 🔴 IT IS MOSTLY A WITHDRAWAL, NOT A REPRICING, and the directive that
    # staged it said the opposite. Measured 1-in-20 on production: of the 848
    # sampled legs whose CURVE PRICE is the discredited number, 778 have no
    # honest snapshot anywhere in their history and are removed (~15,560), 70
    # get a real price (~1,400). The "half and half" split in the filing is the
    # whole cohort, whose correctable half is almost entirely rows carrying an
    # independent `calibration_probability` — repaired here too, but invisible
    # to a reader, because the curve price is COALESCE(cal, opening).
    #
    # PROVENANCE IS THE SAFETY GATE: a row is in scope only when its stored
    # opening EQUALS the discredited snapshot's probability, so the only number
    # this rail overwrites is one it can prove came from that book. Never
    # `is_winner` or `resolution_source` (gotcha #21), never `last_updated`
    # (#2024), and no price threshold of its own — a guard fails the build if
    # one appears.
    #
    # ORDERING IS LOAD-BEARING: it must not run before `ece46743` is live, or
    # Phase 0c re-promotes every nulled row inside one 6-hour cycle. With the
    # guard live the result is a FIXED POINT of Phase 0c, which is why this is a
    # one-off rail and not a re-deriving phase (261,976 rows carry
    # `opening_source='first_snapshot'`; re-deriving them every cycle does not
    # fit an 840s budget that CAL-P1080 measured exhausting at 757.8s).
    #
    # D51: backup into `bak_4745_empty_book_openings` in the SAME transaction as
    # the write, refused unless the copy covers every planned id; undo is one
    # call to the `-restore` name below. Keyset-paged on `fo.id` — read
    # `scan_exhausted`, never a remaining count. ATTENDED-OPTIONAL and
    # TERMINATING: never wire either name to a beat.
    "kalshi-empty-book-openings": (
        "app.tasks.repair_kalshi_empty_book_openings",
        "repair",
    ),
    "kalshi-empty-book-openings-restore": (
        "app.tasks.repair_kalshi_empty_book_openings",
        "restore",
    ),
    # CAL-P1088 (#4788): 574,832 legs across 277,519 resolved Polymarket markets
    # carry `is_winner = false` with `resolution_source IS NULL` — the COLUMN
    # DEFAULT, not a verdict — and `OutcomeRow.tsx` prints every one of them as
    # a red `Lost · 0% · Settled`. This rail WITHDRAWS the verdict (sets NULL);
    # it never crowns anybody, so it needs no venue call: "we never graded this"
    # is a fact about our own row.
    # GATED AT THE MARKET, WRITTEN AT THE LEG. A `false` leg on a market whose
    # winner IS crowned genuinely lost and is merely un-badged; nulling it would
    # manufacture the opposite defect. 854 such markets are excluded by an
    # anti-join asserted equivalent to `pm-never-graded`'s cohort HAVING.
    # Does NOT compete with `pm-never-graded` (#1912), which grades the same
    # cohort from the CLOB venue at 40 markets/call: its cohort predicate and
    # its compare-and-set both still match a withdrawn (NULL) leg, and a real-
    # Postgres gate asserts it. Grading remains the durable fix; this stops the
    # lie in the meantime.
    # D51: backup + one-command restore. Keyset-paged on `after_id`.
    # ATTENDED ONLY: never wire this to a beat.
    "pm-ungraded-loss": (
        "app.tasks.repair_pm_ungraded_loss",
        "repair",
    ),
    "pm-ungraded-loss-restore": (
        "app.tasks.repair_pm_ungraded_loss",
        "restore",
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
    band: str = Query(
        None,
        description="Which AGE SLICE of a keyset walk to page first, as two ages "
                    "in days written youngest-first (e.g. band=47-67), for repairs "
                    "whose population expires. It is a paging selector, never a "
                    "filter: it excludes nothing and changes no verdict, and the "
                    "response says so and reports band exhaustion separately from "
                    "population exhaustion. Refused on apply=true, which selects "
                    "nothing.",
    ),
    band_as_of: str = Query(
        None,
        description="The instant a ?band='s two ages are measured FROM, as the "
                    "ISO timestamp the rail returned inside next_cursor. A band "
                    "is two AGES, so its two dates move with the clock while a "
                    "keyset cursor does not; re-measuring them on page two "
                    "strands every row sharing the cursor's timestamp behind an "
                    "old edge that has passed them (CERT-1935). Page one mints "
                    "it and hands it back; a banded resume without it is "
                    "REFUSED, not re-anchored. Refused with no ?band= and on "
                    "apply=true, both of which select nothing.",
    ),
    min_harm: float = Query(
        None,
        description="Drain the WORST-PRICED cohort of a keyset walk first, as a "
                    "probability on the curve's own price for a leg "
                    "(COALESCE(calibration_probability, opening_probability)); "
                    "min_harm=0.9 selects markets holding a graded loss we still "
                    "price at 90%+. Like ?band= it is a cohort selector, not a "
                    "verdict: it excludes no market from the population and "
                    "changes no judgment, and it is REFUSED rather than clamped "
                    "outside (0,1) because both clamps lie — a percentage like "
                    "90 would select nothing and read as a drained cohort. "
                    "Refused on apply=true, which selects nothing. NOTE that "
                    "`exhausted` under a threshold means the COHORT is drained "
                    "and says nothing about rows beneath it.",
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
            ("band", band), ("band_as_of", band_as_of),
            ("min_harm", min_harm),
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
