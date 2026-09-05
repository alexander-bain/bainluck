# REPORT — lane1/123

**Session:** Sat 2026-09-05, 08:36Z / 01:36am PT (stamped from `TZ=America/Los_Angeles date`; notice 24).
**Branch:** `lane1/099-artifacts`. **Pillar:** MATCHING. **Ship:** the Monday Night Football game
(Dallas @ Seattle, Dec 7, event `15304746`) stays ONE game.

## Verdict in one line

Night three was **not due** (22.07h out — sixth consecutive session handed a §1 in the future);
every standing instrument held for the eighth time; and the session's yield came from §12
candidate 2 — **the widget and the watch both key on `event_id`, so neither can collapse a twin**,
which closes #2866's blast-radius list across all six client surfaces. While reading the watch I
re-derived a real defect that turned out to be **already filed as #1739** — caught only by reading
the body, per §11's trap — and added the three facts that change its fix.

---

## §0 Clock

`date -u` → `Sat Sep 5 08:36:08 UTC 2026`. `TZ=America/Los_Angeles date` → `Sat Sep 5 01:36:08 PDT 2026`.

Night three's window opens **Sun 2026-09-06 06:40Z**. That is **22.07h away**. §1 not due; no poll
taken, no absence reported. This is the **sixth** consecutive session (118–123) to be handed a §1 in
the future.

## §1 Night three — NOT DUE, skipped

Not polled. Night three remains the third data point and is still unread. Night four (Mon 9/7) is
still the first night that can close #2978.

## §2 Twin test — 13 rows, EIGHTH consecutive confirmation

`15304746` Dallas Cowboys @ Seattle Seahawks, `2026-12-08 01:15Z`, `espn_id 401873108`,
**`external_id NULL`, 0 snaps**. The other 12 rows all carry both ids and 798–826 snapshots.

Per the queue's table this is **"not yet exercised — not a finding."** Recorded at 08:36Z. No twin.

## §3 StatPal gate — all four sports read, every number matches banked

Payload `generated_at 2026-09-05T08:36:30Z`. Still calendar **day 1** (it is 01:36 PT on 9/5, not
9/6) — this is the **eighth read of day 1**, not a new row. Earliest flip still Fri 2026-09-11.

| sport | read | denom | both | statpal_only | ours_only | pct | ours_covered_pct | governing | gate |
|---|---|---|---|---|---|---|---|---|---|
| `americanfootball_nfl` | READ-OK | 322 | 321 | 0 | 1 | 99.69 | 99.69 | pct + ours_covered_pct | **MEETS** |
| `baseball_mlb` | READ-OK | 287 | 157 | 65 | 65 | 54.70 | 70.72 | (none) | **PENDING-NO-GOVERNING-NUMBER** |
| `basketball_nba` | READ-OK | 1206 | 41 | 1165 | 0 | 3.40 | 100.00 | ours_covered_pct | **MEETS** |
| `icehockey_nhl` | READ-OK | 1404 | 32 | 1372 | 0 | 2.28 | 100.00 | ours_covered_pct | **MEETS** |

Schedule sides: NFL `within 293 / off_by_hours 26 / wrong_day 2` (unchanged from 122), MLB
`157 / 0 / 0`, NBA `41 / 0 / 0`, NHL `27 / 5 / 0`. Identity did not drop below the bar anywhere;
the seven-day count did not restart.

## §10 Pre-check — 0, SEVENTH consecutive zero

`contested_ids = 0` at 08:36Z. No `IntegrityError` hunt triggered.

## §4 Row B — untouched, as instructed

`14751059` is still the single `ours_only` receipt, `column_holds: null`. Not re-measured.

---

## The session's work: §12 candidate 2 — the widget and the watch

121 read the **phone** target only and said so. The widget extension and the watch app are separate
targets with their own models and decoders, so the phone's answer did not transfer.

**Answer: both key on `event_id`. Neither can collapse a twin.** Posted to
`#2866#issuecomment-5550655028`.

- **Widget:** `WidgetAPIClient.swift:92-93` → `WidgetGame(id: event.id, ...)` from a straight
  `compactMap`; `WidgetModels.swift:89-90` `struct WidgetGame: Identifiable { let id: Int }`;
  `LiveGamesWidget.swift:158/347` `ForEach(..., id: \.element.id)`; deep links
  `bainluck://events/\(game.id)`. No dedup pass exists anywhere in the target.
- **Watch:** `WatchFeedModels.swift:59-62` → `WatchFeedItem.id` is `"event-\(e.id)"` /
  `"futures-\(f.id)"` — the same namespaced contract web and the phone use. Every derived row model
  is the event id: `WatchLiveGame(id: e.id)` (`WatchLiveView.swift:173`), `WatchTeamGame`,
  `WatchMarket`, and `WatchTopStory(id: item.id)` (`WatchMarquee.swift:102/125`).

**#2866's blast-radius list is now complete across all six surfaces** — team page, search, feed,
phone, widget, watch. Nothing dedups on any of them; the feed is clean only because the 47 twinned
pairs sit outside its `-6d/+7d` window.

Incidental, recorded but **not filed**: `WatchFeedItem.init(from:)`
(`WatchFeedModels.swift:80-97`) never throws — every field is `try?` with a fallback — so
`WatchFeedResponse`'s array-level skip loop can never fire for a shape reason. A
`concept`/`tournament`/`bundle` item is admitted with `event: nil, futures: nil` rather than
skipped (confirmed live: a `concept` item sits at rank 1 of the watch's own URL right now). Harmless
because every consumer guards (`WatchLiveView:164`, `WatchGlancesView:154`, `WatchGuessPool:55`).

## The near-miss: #1739 was already filed, and reading the body is what caught it

While reading `WatchLiveView.swift` I found `if !newGames.isEmpty || games.isEmpty { games = newGames }`
(186-188) — an unbounded last-good retention — with `lastUpdated` re-stamped **outside** the guard
(189-191), on a 30s auto-refresh loop (59-61). It looked like a clean new finding in the same family
as 121's phone-cache observation.

It is **row 3 of #1739**, filed 2026-08-11 against `2cac82a9`, cited to the exact same three lines.
Row 1 is the `lastUpdated` half. `gh issue list --search "watch live stale"` surfaced it by title;
only reading the body proved it was the same defect. **Second session running that §11's read-the-body
rule converted a duplicate into real work.**

Rather than re-file, I posted a liveness comment (`#1739#issuecomment-5550653391` — the issue had
**0 comments** in 25 days) with three facts it did not have:

1. **The zero-game window does not need forcing — it is the resting state.** #1739's verification
   says "force a zero-game window". The Live tab calls `/api/feed?limit=8&event_pct=0.3`
   (`WatchAPIClient.swift:44` — note it *explicitly overrides* the 0.15 default that makes the
   unfiltered feed serve zero game cards, so game cards genuinely do reach this surface). Measured
   against production at 08:36Z: 8 items, 4 of type `event`, **every one `status: completed`, zero
   `live`** → `newGames == []` → row 3's guard fires on **every** 30s tick overnight and on every
   non-slate day, while row 1 re-stamps "Just now" over the retained dead games.
2. **The correct pattern already exists two files over.** Live is the only one of the three watch
   surfaces with a retention guard: `WatchGlancesView:153` assigns unconditionally and
   `WatchHomeView:312/318` clears to `[]`. The view even has a correct empty state
   (`WatchLiveView:31`) that is unreachable once `games` is populated once. Row 3 is a one-line
   conformance fix, not a design question.
3. **The guard test is greenfield.** No file under `BainLuckTests/` names `WatchLiveViewModel`,
   `WatchLiveGame` or `newGames`.

All three rows of #1739 reproduce on current master; line numbers drifted (299→296, 190-199→189-191,
63-67→62-68) and the comment gives current ones.

## §12 candidate 1 — the two FINAL 0-0 rows: dated liveness, no drift

Posted to `#2869#issuecomment-5550666618`.

| id | status | scores | completed_at | statpal_fixture_id | snaps | last snap |
|---|---|---|---|---|---|---|
| `14781719` LAC@KC | `closed` | NULL / NULL | 2026-08-16 00:08:51Z | NULL | 807 | 2026-08-30 01:09:48Z |
| `15184679` MIN@NYJ | `closed` | NULL / NULL | 2026-08-15 20:40:30Z | NULL | 816 | 2026-09-03 23:39:09Z |

`wrong_day` is still **2**, same two receipts, same deltas (3385.0h and 1536.42h). **No writer
touched either row in 24h** — the bucket did not drain on its own, which is what the `_window()`
analysis predicts and is worth having as a measurement rather than an inference.

## LOOK (D48) — production, phone width 390, 2026-09-05

`/events/14781719` renders `Final - Aug 15, 2026 - 4:00 PM EDT`, **Chiefs 0-0 / Chargers 0-0,
FINAL**. One refinement on 122's description: the Win Probability panel is not a flat line, it is
**empty** — a single point at ~50% pinned to the right edge of a full Q1/Q2/Q3/Q4 axis, no series
drawn. A game that has not been played, rendered as a completed game with no story.

## What I did NOT do

No code changed, no push, no merge, no cert staged, no labels/state/ownership touched. No fixes
(D35: matching symptoms are filed, not fixed, until lane1/057 lands). Did not widen `_window()`,
did not touch the unique index, did not re-measure row B, did not re-litigate MLB/NBA/NHL beyond
reading them, did not file against the iOS client, did not touch the zero-game Discover feed.

## New traps for 124

- **Reading the body beat the title search a second time.** `gh issue list --search` ranked #1739
  eleventh-ish by title relevance and it was the exact defect. The habit is now two-for-two.
- **A "new" client bug in a family you just characterised is the most likely duplicate of all.**
  121 found unbounded last-good caching on the phone; the watch version *felt* new precisely because
  the family was fresh in mind. Familiarity with the class is a reason to search harder, not less.
- **An override in a client URL is load-bearing context.** `event_pct=0.3` on the watch's feed call
  is the single fact that separates "this guard fires constantly" from "this surface never gets game
  cards at all". §11's unfiltered-`/api/feed` trap has a mirror: check whether the *client* opted out
  of the default before applying a server-side finding to it.
- **A tolerant array decoder is dead code when the element decoder cannot throw.** `WatchFeedResponse`
  has a textbook skip-loop that can never fire, because `WatchFeedItem.init` wraps every field in
  `try?`. Two layers of tolerance compose to *admit* malformed items, not reject them.
