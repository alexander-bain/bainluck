# Post-Fable diffs audit — 2026-07-02

**Scope:** every commit on `master` after Fable's last session artifacts (2026-06-18) through 2026-07-01.
That is: 7 commits on 06-19, the 28-commit burst on 06-24/25, and the automated Manus sweeps
(06-19 → 07-01, verified to touch only `Manus/audit_results/` — no site code).
CI ran green on every commit through the 06-25 tip (verified via Actions API).

**Method:** four parallel code-review passes over themed commit groups (calibration/resolver,
ESPN score/chart backfills, feed/display/entertainment, WS-shadow/rage-shake), each checking diffs
against current tree state and the CLAUDE.md gotcha catalog, cross-referenced with the Manus
live-site audits (06-22 → 07-01) and open issues #984–#990.

**Bottom line: nothing needs a revert.** The post-Fable work is solid — genuinely good outage
fixes (#984/#969/#985), gotcha-#21-safe calibration work (#940/#762), and clean display fixes
(#974/#976/#979/#964). What it needs is: 2 urgent production actions, 1 must-fix code bug,
a handful of small tweaks, and 2 rethinks before shadow flags get flipped.

---

## 1. Urgent production actions (not code reverts — data/ops)

### 1a. Run the deferred #922 residual cleanup — likely the direct fix for the MLB chart mess
Manus timing health went 98/100 (06-22) → 52/100 (06-29) → **−92/100 (07-01)**, with 6.5-hour
x-axis distortions on MLB pages. The 6.5h signature is exactly the pre-fix #922 bug
(`commence + i*30s` stamping put last points at commence+6.6h). The #922 fix (4f16ea4) was
forward-only: its backfill query (`espn_sync.py:1388-1398`) targets only events with `<10` ESPN
snapshots, so **already-polluted events (≥10 snapshots) are permanently excluded**, and the
commit message deferred the residual-row DELETE to "a separate ops cleanup" that has no trace
in git. Those residual rows feed `computeSharedChartDomain`'s `GAME_END_SOURCES`
(`frontend/lib/eventKeyStats.ts:452-496`), stretching completed-MLB x-domains.

Action: `DELETE FROM win_prob_snapshots WHERE source='espn' AND game_state->>'backfilled'='true'
AND captured_at > <commence + sport window>` (then optionally reset those events for re-backfill).

Also from the timeline: the Score Differential total render failure on 07-01 appeared on a
**frozen codebase** (zero code commits 06-26 → 07-01) — it is data-side (missing
`espn_history`/`score_history` on late-June MLB events), not a frontend regression, and none of
the June commits write those tables. #922 made it *more visible* (WP chart now always renders
synthetically while score-diff has nothing). Separate investigation: why late-June MLB games
lack ESPN/StatPal live-coverage rows.

### 1b. #990 — `futures_markets.volume` int32 overflow (probably already firing)
Filed 06-26 by the ops lane, still open, `needs-user`. "World Cup Winner" was at 2,145,191,238
of the 2,147,483,647 cap — within 0.1%, monotonically rising. Once crossed, the upsert raises
`NumericValueOutOfRange` and volume writes fail for the highest-signal markets. Fix is a small
Alembic migration (`ALTER COLUMN volume TYPE bigint`, same for `volume_24h`; in-place safe,
no CONCURRENTLY needed). Six days have passed — check Sentry for `NumericValueOutOfRange` first.

### 1c. The handoff queue has been idle since 06-26
Issues #989 (curve-exclude + score-recover ~17.6K poly props, poly MCE 7.95→4.78pp), #986,
#987 are scoped, some labeled `in-progress`, but nothing has landed since 06-25. Only Manus
sweeps ran. The queue needs an owner again.

---

## 2. Must-fix code bug (TWEAK, high priority)

### #982 anti-thrash marker wedge (b06bdcc) — events can get stuck 0-0 forever
`scores_checked_at` is stamped on **every** successful ESPN response (`espn_sync.py:1052-1058`),
even when ESPN says the game is not final. Combined with #983's (correct) no-write-when-not-final
gate: an event prematurely marked completed while still in progress gets no score written + marker
stamped → permanently excluded from the re-feed branch (`espn_sync.py:960-973` requires the marker
to be absent) → stuck at 0-0 forever. The `repaired_bogus_completed` net only rescues events with
`completed_at IS NULL` and commence within 12h — partial mitigation only.

Fix: stamp `scores_checked_at` only when `scores.get("is_final")` is true. Add the regression test
(not-final response must NOT stamp the marker).

---

## 3. Tweaks (small, worth doing)

| # | Commit | Issue | Fix |
|---|--------|-------|-----|
| 1 | 4f16ea4 (#922) | Future-commence clamp bypass: when `commence > now`, `_wp_backfill_snap_time` returns the **unclamped future** `commence` for every point (`espn_sync.py:1349-1350`) — the docstring's "hard-clamped to now()" is false for exactly the broken-commence events most likely to hit it | `return min(commence, now)` + test |
| 2 | 4f16ea4 (#922) | Uniform 3.5h synthetic MLB window ignores real game length (gotcha #22) → built-in 45-60min stale tail on every newly backfilled game | Cap window at last real cross-source snapshot when one exists |
| 3 | d37b642 (#977) | `min(max(candidates), now)` only clips future-at-run-time; past-but-bogus timestamps (odds snapshots after game end, residual bad ESPN rows) still win (`game_state_backfill.py:536-556`) | Also clamp to `commence + per-sport duration`; prefer game-end sources over odds snapshots |
| 4 | 1d44f47 (#871) | Line-move attribution takes the chronologically **last play of the whole game** and stamps it 0.85-confidence as cause of the largest move (`line_movement.py:641`), with **no temporal or direction link** — and the result is permanently cached for completed events. Also `_team_matches` last-token equality makes Red Sox match White Sox (`line_movement.py:604`) | Pass `captured_at` through play dicts, require last-play-before-window + team-direction consistency (or use the existing-but-unused `_rank_scoring_plays`); ≥2-token team match |
| 5 | 4716209 (#985) | The "one-time" dead-cid purge flag is `setex(..., 86400*30)` (`backfill_winners.py:3747`) → the entire dead set is purged and re-fetched **every 30 days**, re-burning Gamma quota | Persistent flag (no TTL) |
| 6 | 8c97491 (#985) | Circuit-breaker can't fire before the soft wall in the scenario it was built for: a fully-429'd 200-cid batch ≈ 2,000s under Semaphore(3) with in-semaphore backoff sleeps, vs 540/840s walls; breaker + budget guard only run between batches | Thread a `deadline` into `_fetch_market` (mirror the #969 `get_events` pattern) and/or shrink batch to ~30. Also: commit message's "retry next run via cursor" is wrong — cursor advances pre-fetch, so throttled cids wait a full wrap-around |
| 7 | b951ce1 (#984) | Settled-sports pass shares the 420s budget and always runs last — if the main scan chronically exhausts the budget (it did pre-fix), the settled pass (feeds calibration coverage) **never runs**; gotcha-#34 flavor | Reserve a slice (cap main scan ~340s) or run settled pass first every Nth run |
| 8 | 47db4fb (#882 s1) | TMDB task limit-window starvation: `.limit(50)` applies before the Python-side already-marked skip (`enrich_tmdb.py:191-198`) — once the top-50 by volume are marked, the task does zero work forever | Move the `market_metadata->'tmdb'` exclusion into the SQL WHERE |
| 9 | da6a2d1 (#975) | Bug-report fingerprint = page+category+7-bucket root-cause with catch-all — two distinct same-page bugs can collapse onto one issue; hard 7-day digest window orphans a missed Monday run; owner FRs can dedupe onto the digest issue | Add severity/description-token to fingerprint; drop the 7d cutoff (NULL backlog_ref already bounds); exempt owner reports from digest-ref dedup |
| 10 | 5a27d81 (#836) | Shadow verdict Redis hash TTL refreshed on every write, fields never pruned → unbounded while flag on; flag only checked at consumer start (OFF doesn't stop a connected shadow until dyno restart) | Per-field pruning / rolling key; re-check flag in the reconnect loop |
| 11 | 2f9ada8 (#940) | Test file imports a non-existent symbol in dead helper (`test_metric_honesty_940.py:13`) — any future use ImportErrors; one tautological assert | Delete the dead helper; tighten the assert |
| 12 | b05330d adjacent | `_end_phase("fix_categories")` has no matching `_start_phase` (from June 10 commit 9806107) — duration silently never recorded | Add `_start_phase("fix_categories")` |

Watch item (no action yet): #976's `_PLACEHOLDER_TEAM_RE` includes `winner of|loser of` and is
applied to already-linked markets (gotcha #15 says trust linked). No current Kalshi/Polymarket
naming collides — but if a legit game market ever vanishes from an event page, check this regex first.

---

## 4. Rethink before enabling

### #837 Polymarket WS shadow (9458735) — do not flip the flag as-is
The code comment claims "NO asset_ids → settlement trickle, not the price firehose." Wrong about
wire traffic: no `asset_ids` subscribes to **the entire Polymarket CLOB**
(`services/polymarket_ws.py:67-77`), and every message is `json.loads`-ed before being discarded.
Enabling the flag adds a full-firehose parse load on the same `worker-ws` dyno/event loop as the
authoritative live consumers. Deploy-dark today so no immediate risk — but fix before flag-on
(substring pre-filter for `"market_resolved"` before parsing, or subscribe narrowly).
The Kalshi shadow (#836) does not have this problem (lifecycle channel only).

### Test-quality pattern across the burst
Many of the new "tests" are `inspect.getsource` string-greps — they prevent deletion of machinery
but cannot catch logic inversions (e.g., swapping the definitive/transient branch in the #985
dead-cid consumer would pass every test). The genuinely behavioral ones (the two `get_events`
deadline tests, `outcome_is_calibration_void` predicate tests, ESPN FINAL-gate tests) are good.
Worth a standing rule: source-grep tests don't count as coverage for resolution-pipeline code.
Highest-value missing tests: (a) non-definitive result must NOT sadd the dead key (fake Redis);
(b) #982 not-final must NOT stamp `scores_checked_at`; (c) backfilled WP timeline ends near real
game end; (d) seeded-DB #940 bucket counts.

---

## 5. Verified clean (KEEP, no action)

- **#984/#969/#898 outage fixes** — budget math sane everywhere (420 vs 540/900 walls checked);
  `statement_timeout`/`lock_timeout` safely scoped via throwaway engine (`tasks/base.py:42-57`);
  rotating cursors correct, no page permanently skipped; drain-first reorder has no double execution.
- **#940 metric honesty + #762 void_filter** — genuinely count-only/read-side (gotcha #21 verified:
  zero UPDATEs in the diffs); bucket partition exact.
- **#985 dead-cid core fix** — no path caches a 429 as dead (gotcha #36 fixed properly).
- **#974/#976/#979 display filters** — shared 0.005 floor consistent feed↔event-page; ladder
  collapse can't hide the main line; regression tests real.
- **#983 FINAL gate, #980 0-0 correction** — conservative, correct, well-tested; box_score_data
  wrapper handled correctly (gotcha #37).
- **#882 slices 3/4** — no request-path network calls (verified `GET /api/feed` reads only Redis);
  boost bounded, `pre_blend+15` cap intact; no beat entries added where none needed (gotcha #12 clean).
- **#951/#978 golf grouping/rounds panel** — backend/frontend shapes match field-for-field; hooks
  order correct; all 3 GA4 hooks present; no dark: classes.
- **#964 crash fix** — complete, zero remaining `FuturesMarket.url` references.
- **#836 Kalshi WS shadow** — truly deploy-dark: Redis-only writes, own `worker-ws` dyno, does not
  touch the Celery realtime queue; sane backoff.
- **#885 rage-shake v2** — anonymous submission intact (gotcha #29); digest renders no user emails.
- **Manus sweeps (06-19 → 07-01)** — report files only, no site code.

---

## 6. Not verifiable from this environment

- Prod DB state (residual #922 rows, current max(volume), 07-01 sampled events) — no
  `~/.claude/.env` in this container.
- Sentry (needs interactive OAuth approval this session) — check `NumericValueOutOfRange`,
  poll_polymarket recovery, and whether the #985 breaker has fired.
- Whether `TMDB_*` creds / `ADMIN_USER_EMAILS` / shadow flags are set on Heroku.
- Actual production run times (does poll_polymarket chronically exhaust its 420s budget?).
- Test execution (no pytest in sandbox) — resting on CI green through 2f9ada8.
