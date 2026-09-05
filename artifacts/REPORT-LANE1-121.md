# lane1/121 — the phone was the fourth surface, and its cache outlives the window that made the feed clean

**PILLAR: MATCHING · SHIP: the Monday Night Football game stays ONE game** — Dallas Cowboys @
Seattle Seahawks, Dec 7, event `15304746`.

Session ran Sat 2026-09-05, **08:09Z → 08:35Z / 01:09am → 01:35am PT**. Branch `lane1/099-artifacts`.
Read against `origin/master` @ `6fad010e`.

---

## Verdict in one line

Night three was **not due** for the fifth session running (22.5h out), every standing instrument read
**unchanged for the sixth time**, and the session's contribution is the one surface #2866's
blast-radius list had never checked: **the native client keys its feed dedup on `event_id`, so it
cannot collapse a twin — and unlike the web, it banks page one to disk with no age gate, so ageing
out of the server window does not clear a twin the phone already wrote down.**

---

## 0. The clock — fifth consecutive not-due §1

First command of the session, per the queue's §0:

```
date -u                        →  Sat Sep  5 08:09:45 UTC 2026
TZ=America/Los_Angeles date    →  Sat Sep  5 01:09:45 PDT 2026
```

Night three's window opens **Sun 2026-09-06 06:40Z**. That is **~22.5 hours in the future.**

**§1 was not run. No poll was taken and no absence is reported.** 118, 119, 120 and now 121 have all
been handed a §1 roughly a day ahead of their own start, because each queue is written minutes
before its session begins. Night three is still a **third** data point that nobody has taken.

The queue's own framing is worth keeping: *"If you are the session that finally lands after 06:40Z
on 9/6: this is the reading four sessions have been unable to take."* Make that five.

## 1. §2 — the twin test: 13 rows, sixth consecutive confirmation

```sql
SELECT e.id, e.away_team_name, e.home_team_name, e.commence_time, e.espn_id, e.external_id,
       (SELECT count(*) FROM odds_snapshots o WHERE o.event_id = e.id) AS snaps
FROM events e WHERE e.sport_id = 1
  AND e.commence_time >= '2026-12-06' AND e.commence_time < '2026-12-10'
ORDER BY e.commence_time
```

**Exactly 13 rows**, unchanged from 117 (×2), 118, 119 and 120.

| | |
|---|---|
| `15304746` Dallas Cowboys @ Seattle Seahawks, 2026-12-08 01:15Z | `espn_id 401873108` · **`external_id NULL`** · **0 snaps** |
| the other 12 rows | both ids present · **798–826 snaps** each |

Per the queue's grading table this is row 2: **not yet exercised, not a finding.** The odds-API side
has still never claimed the ship, so the durable-matching path on this event remains *un-exercised*
rather than *proven*. Recorded at **08:09Z** and moved on.

**No 14-row case. The twin did not reproduce in the wild.**

## 2. §10 — the pre-check: 0, fifth consecutive zero

```sql
SELECT count(*) AS contested_ids FROM (
  SELECT espn_id FROM events WHERE espn_id IS NOT NULL
  GROUP BY espn_id HAVING count(*) > 1) t
```

→ **`0`** at 2026-09-05 08:09Z. The index is not merely un-violated but un-*tripped*: five
consecutive readings at zero, and (117/118) zero Sentry issues naming `uq_events_espn_id` at both
24h and 14d. Sentry not re-queried this session — two clean reads at 14d two days ago cover today.

## 3. §3 — the gate: all four sports read, every number identical

`GET /api/admin/statpal/authority-agreement`, `generated_at 2026-09-05T08:10:12Z`. **All four sports
read**, per the queue's warning that the payload serves four and a past session read one and called
it "the gate":

| sport | denom | both | statpal_only | ours_only | pct | ours_covered_pct | governing | gate |
|---|---|---|---|---|---|---|---|---|
| `americanfootball_nfl` | 322 | 321 | 0 | 1 | **99.69** | **99.69** | `pct` + `ours_covered_pct` | **MEETS** |
| `baseball_mlb` | 287 | 157 | 65 | 65 | 54.70 | 70.72 | *(none)* | **PENDING-NO-GOVERNING-NUMBER** |
| `basketball_nba` | 1206 | 41 | 1165 | 0 | 3.40 | **100.00** | `ours_covered_pct` | **MEETS** |
| `icehockey_nhl` | 1404 | 32 | 1372 | 0 | 2.28 | **100.00** | `ours_covered_pct` | **MEETS** |

All `READ-OK`, no read failures. NFL schedule side (reported, gates nothing): `within 293 ·
off_by_hours 26 · wrong_day 2 · time_missing 0`. `ours_only 1` is row B (`14751059`, the phantom
Broncos @ Cardinals) — exactly as characterised, `column_holds: null`.

**Every NFL field is byte-identical to the value 116–120 read.** Today is still **2026-09-05**, so
this is the **sixth read of calendar day 1**, not a new row. **Day 1 of 7 · earliest flip Fri
2026-09-11.** Nothing below the bar, so nothing to say out loud.

D63 not re-litigated — NBA and NHL scoring `MEETS` on `ours_covered_pct` alone is the ruling working
as designed, and MLB's `PENDING` is deliberate. Read, reported, not re-derived.

## 4. The contribution — the native client, #2866's last unchecked surface

The queue's §12 named this as the candidate: *"does the native client key on `sport_key` or on
`event_id`?"* — answerable by reading the Swift decode path, no simulator. It is answerable, and the
answer came with something extra.

Source read against `origin/master` @ `6fad010e`. **No device build, no simulator** — stated as a
mechanism claim, not an observation, in the comment itself.

### (a) The client cannot collapse a twin

`DiscoverViewModel.itemKey` (`ViewModels/DiscoverViewModel.swift:1071`) returns
`"event-\(event.id)"`, and the only dedup on the path is `:980-981`:

```swift
let loadedIds = Set(items.map(Self.itemKey))
let fresh = renderable.filter { !loadedIds.contains(Self.itemKey($0)) }
```

Two rows for one game are two distinct `event.id`s → two distinct keys → **both survive**. There is
no teams+time fingerprint anywhere; `FeedItem.id` (`Models/FeedModels.swift:194`) is the same
identity. **The answer is `event_id`, and nothing else.** The phone is exactly as exposed as the web
feed while the pair is in the served payload — neither more nor less.

### (b) …and its cache outlives the window that made the feed clean

This is the part 120's closure does not cover, and the reason the finding was worth writing.

120 closed the feed half of #2866 on the ground that the twinned pairs **aged out** of the server's
`now − 6d → now + 7d` candidate window (`routes/feed.py:5898`). That is a statement about the
*server*. On iOS, ageing out of the server window does not remove a card the device already wrote
down:

- The offset-0 page is persisted as last-good (#1465) and re-served at the next cold launch's first
  paint.
- **`DiscoverFeedCache.load` (`Services/DiscoverFeedCache.swift:85`) enforces no expiry.** It
  returns whatever is on disk. The type's own header is explicit that this is deliberate:
  *"`storedAt` and `ttlSeconds` are metadata only"* … *"Advisory metadata for telemetry/honesty —
  never a local freshness policy."*
- The only age filter is the render-time gate, `DiscoverView.isStaleItem`
  (`Views/DiscoverView.swift:186`), and for an **event** it fires **only** when
  `status == "completed" || status == "closed"` **and** `now - commence_time > 8h`.

**A scheduled future game is never dropped by age.** So on iOS the exposure is not *"is the pair
inside the ±window now?"* but ***"was it ever inside it, and has the game since completed +8h?"***

Two narrowings, both stated on the issue so nobody over-reads it:

- **Only page one is banked** — pagination pages stay transient, so the pair must land in the
  offset-0 slice to be written at all.
- **A successful revalidate replaces the page wholesale** — online, the stale pair is on screen for
  one paint. It persists across launches only while revalidation keeps failing, which is what
  last-good is *for*. That is the cache working with twinned data in it, not a cache bug.

**Filed:** `#2866#issuecomment-5550521193`. Grepped first (§11) — the issue had **0** occurrences of
`iOS`, `native`, `last-good`, `Swift`, `itemKey`, `widget` or `device` across body + 6 comments. The
addition is genuinely new. **Nothing filed against the native client itself** — no twin is reachable
on any surface today, so there is no defect to open, only a mechanism to record.

**Also filed:** `#2693#issuecomment-5550523644` — §12's second candidate, the dated Nov 30 edge, now
carrying the iOS consequence. If `15304746` ever twins it enters the feed window ~**Nov 30** (Dec 8
− 7d); a banked twin would then keep painting on a device until **Dec 8 09:15Z**, independent of the
server window. #2693 had 0 hits for `Nov 30`, `November`, `last-good` or `iOS`.

**The blast-radius list is now complete: team page → search → feed → native.**

## 5. LOOK (D48) — the ship photographed, and a filed issue re-confirmed

`SHOT_W=390 SHOT_H=844 ./tools/look.sh https://www.bainluck.com/events/15304746`, run from
`~/bainluck`, 780×4340 full-page capture, read.

**The ship holds visually: ONE game.** Seahawks vs Cowboys, "Dec 7, 2026 · 8:15 PM EST", "Starts in
93d 17h". One hero, one page, no doubled row.

Three things in the frame, **all already filed, none re-filed**:

- **The hero prints two bare `%` signs** with empty bars and `0-0` under each crest → **#2896**, the
  no-source-at-all case. 116 added a dated specimen and 117 the precondition. Holds, unchanged.
- **"Tracking will begin when odds are available"** on the Win Probability panel → correct for an
  event with 0 odds snapshots (queue §7). Not an empty chart.
- **PLAYER AWARDS lists the same seven players under both crests** — Dak Prescott and CeeDee Lamb
  appear under *Seahawks*, Sam Darnold under *Cowboys*, names truncated to `Will Sam Darn…`.

That third one looked new for about a minute. It is not: **#3117**'s title is *"Event page PLAYER
AWARDS: Super Bowl MVP field stores the whole question as the nominee name, sums to 1,967%, and
renders identically under both team crests"* — 117 filed all three defects (question-as-name,
1,967% sum, cross-crest duplication) with the same seven-row specimen from the same page. Grepping
the issue before writing (§11) is the only reason this session did not post a duplicate. **Confirmed
still reproducing at 2026-09-05 08:1xZ; nothing added, since a re-confirmation of an unchanged p2 is
not worth a comment.**

## 6. What was NOT done, deliberately

§1 not polled (not due, 22.5h out). Sentry not re-queried (two clean 14d reads on 9/4 stand). Row B
not re-measured — 118 characterised it completely and there is no DELETE rail by ruling 079; it
stays filed on **#3070**. Week 1 not re-verified (clean, 16 games, both ids, 32 franchises). The
league page not re-read for Dec 27 (119 read it: window Sep 10 → Sep 13 only). D63 not
re-litigated. The CREATE rail stays un-invoked at `TRUTH_ID_SET_DRIFT`. `#3117`, `#2896`, `#3070`,
`#2957` not re-filed. No new issue opened — both findings had owners already. No code changed, no
push, no merge, no cert staged.

## 7. New traps for 122

- **Grepping the issue before filing caught a duplicate this session, on the third check of four.**
  #2866 and #2693 were both genuinely clean; **#3117 was not** — the cross-crest PLAYER AWARDS
  duplication is in its *title*, and the shot would have produced a confident duplicate filing. The
  habit is not overhead; it is the thing that makes mystery-shopping safe to do every session.
- **A source read can answer a "which surfaces" question that a query cannot.** #2866's blast-radius
  list had three surfaces measured against production and one that no query could reach, because
  the native client's exposure lives in a decode path, not in a payload. Twenty minutes of
  `git show origin/master:<swift file>` closed it. When a surface has no endpoint, read its code.
- **A closure can be true of the server and false of a client that caches.** "Clean because it aged
  out" is a statement about a candidate window; any client with an unexpired local store has a
  *different* exposure interval. Before inheriting a closure onto a new surface, ask what that
  surface keeps.
- **`git show origin/master:"<path with spaces>"` needs the quotes** — every iOS path in this repo
  contains `Bain Luck`, and an unquoted `git show` splits it into two refs.
- **This worktree's iOS tree is also behind master** (4 files, incl. deleted test files). Same rule
  as `backend/`: read `origin/master`, not the working tree.

## 8. Standing state at session end

- **Twin test: 13 rows, 6th consecutive.** `15304746` `external_id NULL` / 0 snaps — un-exercised.
- **Pre-check: 0 contested espn_ids, 5th consecutive.** Index un-tripped.
- **Gate: NFL 99.69 MEETS, day 1 of 7** (6th read of day 1). Earliest flip **Fri 2026-09-11**.
- **Night three: NOT DUE**, window opens **2026-09-06 06:40Z**. Night four (Mon 9/7) is still the
  first night that can close **#2978**.
- **NFL kickoff Thu 9/10 — five days.** Week 1 verified clean (§6 of the 121 queue).
- **#2866's blast-radius list: COMPLETE.** Team page, search, feed, native — all four characterised.
