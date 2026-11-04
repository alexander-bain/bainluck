# Live settings — what production runs, and where each value lives

The settings freeze of 2026-11-02 (#10090). From Oct 28 to Nov 1 the Speed window tuned production with Heroku config
vars and fast deploys from a branch. This page is the one record of every var it set, changed or unset on `bainluck`
and `bainluck-heavy` in that time, read back from `heroku config` on Nov 1 (names and non-secret values only). Its
starting list is Fable's ledger, Appendix C of the Nov plan (`docs/live-settings-ledger-2026-11-01.md`).

**Decisions:**
- **Default:** the value is now the code default and the var is unset.
- **Switch:** the code default is unchanged, and the var stays as a documented switch.
- **Removed:** the knob is deleted from the code.

A new setting change from here on is a PR against this page and the code, never a bare `config:set`.

`bainluck-heavy` carried none of these vars. It ran each setting's old code default, so a value that became a default
here also reaches heavy. Each row says whether heavy runs the code it governs.

## The vars set since Oct 28

| Var | Production value | What it does | Decision | Heavy |
| --- | --- | --- | --- | --- |
| `SPEED_SWITCH_TODAY_PREVIEW_AT_RECEIPT` | `1` | Display before save: a held page shows a venue's price at receipt, before the database write (DNPL). Ledger row 1. | Default: `preview_at_receipt` today = 1 in `speed_switches.SPECS`; a trial can still turn it off for half the games | no (worker-ws) |
| `PREVIEW_AT_RECEIPT_VENUES` | `all` | Which venues' receipts preview. | Default `all` (`PREVIEW_AT_RECEIPT_VENUES=polymarket` or `kalshi` narrows it) | no |
| `POLYMARKET_WS_OPEN_SCOPE` | `slate` | The open-contract stream carries today's slate (~900 assets), not every open contract (~3.9k); PM loop CPU 0.95 → 0.47. Row 2. | Default `slate` (`all` restores the full arm) | no |
| `VENUE_POLL_30S_ENABLED` | `polymarket` | The 30-second refresh of every shown market off the sockets. Kalshi drew a 429 at `all`. Row 3. | Default `polymarket` (`0` off; Kalshi returns only with batching or a slower cadence) | no (realtime queue) |
| `VENUE_POLL_30S_PM_SOURCE` | `clob` | The 30-second poll reads the CLOB (~30 s fresh), not Gamma's ~12-minute rotation. Row 4. | Default `clob` (`gamma` restores the first build) | no |
| `PM_WS_REPEAT_SKIP_MS` | `3000` | A repeated Polymarket top of book inside the window is skipped but still feeds "confirmed at"; no displayed number changes. Row 5, decided by data: Polymarket's per-minute worst wait, p90 874 ms and 79 % of minutes under 0.5 s at 3000 (11/01 17:08Z on), against 1,434 ms and 71 % at 250 (00:34–08:53Z). Other changes landed in between, so this shows no rise, not a gain. | Default 3000 (`0` off) | no |
| `PM_WS_UPCOMING_HOURS` | `1` | The Polymarket game socket subscribes live games plus games within 1 h; 1–6 h out are on the 30-second CLOB poll, and a game a reader opens asks for the socket (`watch_held_presence`, slate scope). Row 6: both conditions hold. | Default 1 (clamped 1..6) | no |
| `PM_WS_PROPS_TO_POLL` | `1` | Props of games nobody holds move from the socket to the 30-second poll; held games, Discover and the 200 busiest props stay live. Row 7. | Default on (`0` off) | no |
| `KALSHI_WS_UPCOMING_HOURS` | unset (tried `2` for 23 min on 11/01) | The Kalshi socket's upcoming window. The 2 h trial drew Kalshi 429s. Row 8. | Removed: the window is the literal 6 h it always was | no |
| `STAMP_HELD_OWED_FRESH` | `1` | A held game's owed stamp takes the fresh path. Row 9. | Default on (`0` off) | no |
| `ADMITTED_LIVE_BATCH` | `4` | Four live events of one cohort per stamp transaction; events/min +11–13 %, shed-class p90 72 s vs 128 s. Row 10. | Default 4 (1..8) | no |
| `SPEED_SWITCH_TODAY_HANDOVER_FRESH` | `1` | A catalog handover's carried cohort is stamped fresh. Row 10. | Default: `handover_fresh` today = 1 | no |
| `ADMITTED_STAMP_BATCH` | `4` | Up to four queued non-live events of one cohort per stamp transaction. | Default 4 (1..8) | no |
| `FRESH_FLUSH_PENDING_ATTEMPTS` | `3` | Old stamps a fresh-bearing flush attempts. A trial at 1 was restored to 3 on Oct 29. | Default 3 (1..32) | no |
| `SPEED_SWITCH_TODAY_OWED_PAST_WITHDRAWAL` | `1` | An owed stamp may pass a buffered withdrawal (decision 41 B). Row 16. | Default: `owed_past_withdrawal` today = 1 | no |
| `SPEED_SWITCH_TRIALS` | `1` | The runtime trial layer: per-game (`ab`) and alternating trials, each capped at 30 min by the server, set with `tools/speed/switch.sh`. | Default on (`0` off) | no |
| `STAMP_WRITE_UNDER_QUEUED` | `9` | A game whose stamp is queued (not running) may still take its price write, for the next 9 picks per queue. G4F23 arm B. Row 11. | Default 9 (`0` restores the full fence); re-measure at the next database-busy peak | no |
| `FEED_SPORTS_METADATA_REUSE` | `1` | Sports feed market metadata is reused across workers through the shared, fingerprinted cache. Reuse fires; cache-miss service time unchanged (~2.3 s); kept for database reads. Row 11. | Default on (`0` off) | **yes**: heavy's feed prewarm now reuses too |
| `BUSY_DB_DEFER_HEAVY_SCANS` | `1` (bainluck only) | Heavy background scans skip runs during the busy window (15–05Z). | **Switch, set on bainluck only.** The scans it defers include `matching_reconciliation` and the Polymarket resolved-market sweep, which run on `bainluck-heavy`, where the var was never set. Making it a default would newly hold that sweep, and so settled results, 14 hours a day | yes (unset there; unchanged) |
| `WS_CONSUMER_POOL_PRE_PING` | `0` | No per-checkout pre-ping on the worker-ws engine; user-visible max 4–7 s → 1.7–1.9 s. Row 13. | Default off (`1` on) | no |
| `PM_WS_BLEND_FLOOR_SECONDS` | `5` | The Polymarket blend stamp runs at most every 5 s; receipt previews do not wait for it. Row 14. | Default 5 s (`PM_WS_BLEND_FLOOR_DEFAULT_S`) | no |
| `LIVE_BLEND_PREVIEW_RESERVATIONS` | `96,48,192,128,448,112` | Preview ledger slots by league tier (v2 policy, cap 1024); Alex, decision 36: "A in perpetuity". Row 15. | Default (same bytes, same v2 fingerprint, so the running ledger is unchanged) | no |
| `LIVE_BLEND_PREVIEW_MAX_UNCOMMITTED_S` | `180` | How long one uncommitted value may stay on a reader's screen; Alex's decision D of Nov 1. | Default 180 s | no |
| `LIVE_BLEND_ABANDON_OPTIONAL_DB` | unset (on for 8 h on Oct 29) | An optional read past its deadline is abandoned, not cancelled. Lost its trial. | Removed with its `abandon_optional_db` trial switch | no |
| `COLLECTIONS_ENABLED` | `true` (set Nov 2, 11:25 AM PT, after the publication) | The Midterms 2026 collection page and its Discover/Politics pin (#11853). | Switch (a feature gate, not a speed setting) | no (web) |
| `CONTAINER_COLLECTIONS_ENABLED` | `true` (set Nov 2 with it) | The Midterms gate's second half; also the hourly NFL-week / MLB-postseason assembly pass, which writes membership and never publishes. | Switch | no (the pass runs on bainluck's background queue) |

## Settings added since the freeze

Each came with its own PR, against this page and the code.

| Var | Production value | What it does | Decision | Heavy |
| --- | --- | --- | --- | --- |
| `MARKET_PREVIEW_PUBLISH` | unset (on) | A Discover futures/prop card in view shows its venue's move at arrival: the Kalshi and Polymarket sockets publish a held market's buffered price on `live:market:<id>` as a provisional `market_preview` frame (`backend/app/utils/market_preview.py`), before the flush writes it. Held markets only (`PUBSUB CHANNELS`, read in the background every 2 s), change-only, at most one frame per market per 250 ms, never a settled or graded leg; no database read or write. A Polymarket open contract the admission cannot pair (`markets_unpaired`) gets none. | Switch: default on; `0` turns it off at the next worker-ws restart (the committed invalidation and re-read are unchanged either way) | no (worker-ws) |
| `STREAM_HISTORY_POINTS` | unset (off) | #11929 cause 2: a streamed futures/prop leg's chart gains points from the socket, not only from the polls. The Kalshi and Polymarket flushes write one `futures_odds_snapshots` row for a leg whose committed price moved at least 1 point since its last stream point, or 5 minutes after it at a different price; at most 24 rows per market per minute (the rest stay due); one INSERT per flush, in the flush's own transaction, `captured_at` = the row's stored `last_updated`; never from a preview, never for a graded or settled leg or a resolved market (`backend/app/utils/stream_history_points.py`). Counters `history_points` / `history_capped` / `history_skipped` / `history_refused` / `history_errors` on each socket's minute line. | Switch: default off. Measured Nov 4 05:02–05:04Z: about 1,200–1,500 Kalshi legs a minute would be due, roughly 1,000–1,300 rows a minute after the cap (estimated), against about 3,860 snapshot rows a minute today (25–35 %). Polymarket would add up to about 1,000 more, mostly beside the 30-second poll's own points (about 90 % of moving Polymarket legs already had a point that minute). Values: `kalshi`, `polymarket`, `1`/`all`; read at the next worker-ws restart. Turn on `kalshi` first, with the database meter before and after | no (worker-ws; the rows land on the shared Postgres) |
| `VENUE_GAP_BACKFILL_ENABLED` | unset (off) | #11929 PR-A: settled futures markets keep the price journey Kalshi recorded, past its 47–86 day purge. Every 15 minutes (:01/:16/:31/:46, `heavy` queue) `backfill_venue_history_gaps` takes Kalshi markets settled in the last 45 days (`CAPTURE_PLANNING_AGE_DAYS`), oldest settlement first, and stores their chart legs' hourly candles (top 10 by probability plus the winner) in the new `venue_history_points` table (`backend/app/tasks/venue_history_backfill.py`). Nothing reads that table yet; charts are unchanged until PR-B. A 429 stops the run. Verdict line `venue_history_backfill verdict=…` per run. | Switch: default off. `1`/`true`/`on`/`yes`/`kalshi` turns it on at the next run (read every run, no restart). Unset is the whole revert. Needs migration `venue_history_points_11929` applied first | **yes**: set it on `bainluck-heavy`, which runs the `heavy` queue. On `bainluck` it does nothing |
| `VENUE_GAP_BACKFILL_ROWS_PER_MIN` | unset (1000) | The backfill's write rate into `venue_history_points`: after each insert of up to 500 rows the run sleeps until its rows fit the rate. | Switch: default 1000 (clamped 1..20000), read every run | **yes** (`bainluck-heavy`) |
| `VENUE_GAP_BACKFILL_MARKETS_PER_RUN` | unset (50) | Markets the backfill selects per run. | Switch: default 50 (clamped 1..500), read every run | **yes** (`bainluck-heavy`) |
| `VENUE_GAP_BACKFILL_WALL_S` | unset (600) | The backfill's wall budget per run, in seconds. A run holds one of heavy's two slots for up to this long every 15 minutes; a pause or request that would cross it ends the run. | Switch: default 600 (clamped 30..720), read every run | **yes** (`bainluck-heavy`) |

**Do not make `BUSY_DB_DEFER_HEAVY_SCANS` a code default:** it would start deferring the resolved-market sweep on `bainluck-heavy`, which has never run it, and settled results would wait up to 14 hours.

## Live settings older than Oct 28, unchanged

`KALSHI_WS_DIRECT_BOOK=1`, `KALSHI_WS_PRICE_FLUSH_SECONDS=0.25`, `PM_WS_PRICE_FLUSH_SECONDS=0.25`,
`CONTAINERS_READ_ENABLED=true` and `CONTAINER_DISCOVERY_ENABLED=true` were set before Oct 28 and were not touched in the
race. They stay as they are, outside this freeze.

## Trial switches that lost their trials

Deleted from the code on 2026-11-02, after the Midterms collection went live and Monday Night Football was checked:
- `preview_from_commit`: trialled Oct 31, with p90 worse in all three pairs (ledger row 17). The read-graph cache it
  shared stays, for `preview_at_receipt`.
- `abandon_optional_db`, the trial for `LIVE_BLEND_ABANDON_OPTIONAL_DB`: an optional read past its deadline is
  cancelled, as production always ran it.

## Switches deleted from the code

- Default-on rollback switches that shipped with fast deploys and were never flipped. Each behavior stays; only its
  off branch is gone:
  - `STAMP_READER_FIRST`
  - `PM_HANDOVER_SHED_QUEUED`, `PM_SCAN_PREFILTER`, `PM_PACK_PREVIEW_COHORTS`, `PM_FUSE_PRICE_TIMEOUT_SETS` (row 30)
- `KALSHI_WS_UPCOMING_HOURS`, as listed above.
- Kept: `STAMP_READ_JSON_ONCE`, because its off path (one read per row) is the real-Postgres test's equivalence check
  for the on path. `FRESH_STAMP_WORKERS` and `PM_WS_STABLE_RETRY_BASE_S`, because they are numbers, not switches.
  `PM_WS_BLEND_FLOOR_SECONDS` stays its own setting, separate from the receipt floor.

## Changes that were code from the start (ledger rows 19–27)

These need no var and stay as they are:
- The receipt-previewed stamp floor is 20 s (`LIVE_BLEND_RECEIPT_STAMP_FLOOR_S`). The EKG beats on receipt, not on
  the stamp.
- The pre-game stamp floor is 15 s.
- Kalshi persists every 5 s after a receipt preview.
- Finished events retire once per 30 s.
- The receipt interval is 0.1 s.
- The event-page headline pair and chart tip show tenths of a point; cards and the feed keep whole numbers.
- "Seconds ago" counts from the markets' last confirmation.
- The EKG replaces the signal bars on the event page.
- Decision D: in live play, Kalshi and Polymarket carry the betting base weight. It is written into
  `docs/PRODUCT-BRAIN.md`.

## Database changes (row 28)

The duplicate trigram indexes were dropped, and the events GINs run `fastupdate = off` (decisions 26 and 34). Both are
permanent and were done attended. Nothing to do.

## Both apps run one tree

`bainluck-heavy` deploys the commit `bainluck` serves, through `.github/workflows/heavy-sync.yml` after each master CI
run (with an hourly backstop). From Day 0 every deploy is a master merge, so production and master no longer diverge.
