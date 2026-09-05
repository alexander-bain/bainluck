# REPORT — lane1/126

**PILLAR: MATCHING · TRUTH.** **SHIP: the Monday Night Football game stays ONE game** —
Dallas Cowboys @ Seattle Seahawks, Dec 7, event `15304746`. Live, and still a single row after an
**eleventh** reading.

Session ran Sat 2026-09-05, **09:22Z → 09:5xZ** (02:22 → 02:5x PT; PT = `date` minus 3h, notice 24).

---

## 0. The clock, first — night three is STILL not due (9th consecutive session)

```
date -u                       → Sat Sep  5 09:22:49 UTC 2026
TZ=America/Los_Angeles date   → Sat Sep  5 02:22:49 PDT 2026
```

Night three's window opens **Sun 2026-09-06 06:40Z**. That was **21.3 hours** away. §1 was not due,
I did not poll it, and I report no absence. Sessions 118–126 have now all been handed a §1 in the
future.

125 finished at 09:04Z — **18 minutes** before this session started. Per §13 I did not treat any
re-read of its dated baselines as a data point.

## 1. Liveness (not data points — 18 minutes after 125 read the same rows)

| instrument | reading | vs 125 |
|---|---|---|
| §2 twin window, `sport_id = 1`, Dec 6–10 | **13 rows**; `15304746` `external_id NULL`, 0 snaps | unchanged (11th) |
| §15 contested `espn_id` | **0** | unchanged (10th) |
| §15 `statpal_fixture_id` duplicate census | mlb 5 · nba 2 · nhl 3 · nfl 0 | unchanged |

**Not yet exercised. Not a finding.** §3's authority-agreement payload was not re-read: 125 banked
every sub-object 18 minutes earlier and day 2 does not start until 9/6.

---

## 2. Candidate 2, taken at last — and the queue's framing of it was wrong

The queue has carried this as the "strongest unexplored candidate" for three sessions: *"What
#2693's `reachable` comments actually claim. 4 occurrences of 'reachable' and 6 of `15304746`
across 24 comments."*

Read all of them (25 comments now, ~46k chars). **The word is being used in two unrelated senses,
and only one instance is about the ship.**

| comment | sense |
|---|---|
| C8, C14 | "the id-anchored **drain** is unreachable" — gotcha #32 / `NO_ANCHOR_CHANNEL` |
| C9 | "#2803's `target: 0` is unreachable by construction" — a metric |
| C18 | "why each is unreachable **by this rail**" — 5 residual authority ids |
| C25 | "feed-**reachable** around Nov 30 … stays reachable through kickoff" — lane1/121's own calendar note, the only ship-sense use |

So four of the five uses mean *the repair cannot reach the row*, and one means *a user can reach the
card*. There is no unread claim about the ship hiding in them. **Candidate 2 is closed; do not
re-queue it.**

**One real correction fell out of C24.** It says `15304746` is "the only one of **322** NFL events
this entire season" without an odds-API join. The events-table count for that exact window
(`sport_id = 1`, `commence_time` in `[2026-09-01, 2027-03-01)`) is **271**. 322 is the NFL
*denominator* in the authority-agreement payload (§3) — a different population with a different
window. The "only 1" is right; the N is not.

---

## 3. What the ship's own population looks like — the watched transition has no precedent

Nobody had asked how the other twelve Week 13 rows got their ids. Gap between `events.created_at`
and the row's **first** `odds_snapshots.captured_at`:

```
14780587 GB @ NO        created 2026-05-15 00:53:07   first snap +0.02h
14780588 SF @ NYG       created 2026-05-15 00:53:07   first snap +0.02h
14780589 HOU @ PIT      created 2026-05-15 00:53:07   first snap +0.02h
15176006 JAX @ CHI      created 2026-07-20 13:09:59   first snap +0.02h
15176007 CIN @ CLE      created 2026-07-20 13:09:59   first snap +0.02h
15184635..15184641      created 2026-07-29 04:35:00   first snap +0.02h   (7 rows)
15304746 DAL @ SEA      created 2026-09-04 18:43:33   NO SNAPSHOT, external_id NULL
```

**All twelve are odds-API-first** — created in three discovery waves and priced ~72 seconds later.
Not one is an ESPN-first row that the odds API later joined.

Widened to the whole NFL season (271 rows, by creation day):

```
2026-05-07  1 |  05-11  1 |  05-12  5 |  05-13  7 |  05-14  2 |  05-15 134
2026-06-22  4 |  06-26  3 |  06-30 29 |  07-20 15 |  07-21 18 |  07-29  51
2026-09-04  1   <-- 15304746, the ONLY row with external_id NULL
```

**270 of 271 NFL season rows were created in odds-API discovery waves and carry both ids. Exactly
one was created outside them, and it is the ship.**

So the transition the watch is waiting on — a row that exists *without* an odds-API `external_id`,
waiting to be claimed — has **one instance in the entire NFL season**. There is no historical case
to learn from, in either direction. "Un-exercised" is weaker than it sounded: it is un-exercised
because the population is of size one.

---

## 4. The main finding: every duplicate detector this lane runs is blind to #2866's 47 groups

Reproduced #2866's population from `events` (the issue measured it off the search surface). Exact
`(away_team_name, home_team_name, commence_time)` groups, NFL-family sport ids,
`commence_time >= 2026-01-01`:

```
cross-sport duplicate groups   47   (94 rows)     all of them  americanfootball_nfl + americanfootball_nfl_preseason
same-sport  duplicate groups   11   (23 rows)
```

**81% of NFL-family exact twins straddle a sport boundary.** Detector reach over those 47:

| detector | sees | why |
|---|---|---|
| `uq_events_espn_id` | **0 / 47** | 0 groups have two non-null `espn_id`s |
| contested-`espn_id` census (§15) | **0 / 47** | same |
| duplicate-`statpal_fixture_id` census (§15) | **0 / 47** | 0 groups have two fixture ids — **and it groups by `(fid, sport_id)`, so the partition key is inside the grouping key** |
| `live.duplicate_ids` (§4) | **0 / 47** | keyed on `statpal_fixture_id` |
| `external_id` | 1 / 47 has two — **and they differ**, so no equality test fires |

Every count is zero. **The nine consecutive green pre-checks were never evidence about this
population**, and never could have been.

Checked whether this is hiding a twin of the ship: the Dec 6–10 window with `sport_id <> 1` across
the football family returns **0 rows**. So the 13-row reading stands; the scoping is a latent blind
spot, not an active miss.

Also corrected #2866's anatomy paragraph. It says "the regular row has an `espn_id` and no
`external_id`" — its own C5 table shows `14780590` carrying `espn_id` **and** `external_id` **and**
`statpal_fixture_id`. What holds across all 47 is one-sided: **the preseason row never has an
`espn_id`** (0/47).

Filed as a comment on **#2866**, not a new issue.

## 4b. What I did NOT file, and why

Three candidate findings this session were already filed. Checked before writing, all three:

* the 47 cross-sport groups → **#2866's title**;
* the Cowboys @ Seahawks Aug 16 twin (`14780590` / `15191808`, 17–7 both sides) → **#2866 C5**,
  documented 90 minutes earlier by lane1/119 with the same anatomy table;
* the `americanfootball_other` ghost cohort → **#2819** and **#2321**.

The trap "a 'new' bug in a defect class you just characterised is the MOST likely duplicate" paid out
three times in one session.

---

## 5. The `americanfootball_other` cohort is user-visible, recurs, and 203 rows are not teams

Found while chasing a third football sport key (`52556`, 4,677 rows since Jan 1 — 93× the preseason
key). It is #2819's population, but three things are new.

**(a) A fan searching one college football game gets fifty cards.**
`https://www.bainluck.com/search?q=LSU%20Ole%20Miss`, phone 390×844, production:

```
60 results · 50 games · 10 markets
[ All ]  [ americanfootball_other (24) ]  [ NCAAF (1) ]
GAMES (50)
  OTHER  Aug 31  FINAL   Ole Miss / LSU
  OTHER  Aug 10  FINAL   Ole Miss / LSU
  OTHER  Aug 27  FINAL   Ole Miss / LSU by 4 or more points     <-- badge "LB"
  OTHER  Aug 27  FINAL   Ole Miss / LSU
```

`artifacts/lane1-126-search-lsu-fifty-cards.png`. Every card is FINAL with no score; the dates are
ingest instants, so one fixture scatters across Aug 10 / 27 / 31.

**(b) It recurs per pass.** `LSU` v `Ole Miss` = **29 event rows**, Aug 1 → Sep 4. `Oklahoma` v
`Texas` = 19. Sized honestly: 2,798 rows over 2,591 distinct pairs in 36 days, so recurrence is
**7.4%** — a concentrated tail, but it is exactly the tail a marquee-fixture search lands on.

**(c) "These rows carry the right team names" is false for 203 of them.** `away_team_name` values
like `LSU by 4 or more points`, `Oklahoma by 15 or more points`, `Seahawks - Highest Scoring
Quarter` — market outcome strings promoted to event rows. That sentence carries #2819's decoy
argument, so the exception matters: for those 203 there is no game to be a decoy *for*.

Anchoring: **4,673 of 4,677 (99.91%) carry no id channel at all**, zero `espn_id` across the whole
key. Same structural position as `soccer_other` (#2778) — it cannot shrink on its own.

Filed as a comment on **#2819**. Soccer contamination in the key is **#2321**, not re-filed.

## 6. NEW ISSUE: #3165 — the facet chip prints a raw sport key

Separable from the ghosts and unfiled. On the same screen: the filter chip says
**`americanfootball_other`** while every card under it says **`OTHER`**.

`frontend/app/search/page.tsx:476` renders `{sport.name}` — the backend column — instead of
`getLeagueDisplay(sport.key)`. The page already imports that helper (line 8) and uses it at line 92.
`getLeagueDisplay` (`frontend/lib/sportCategories.ts:796-810`) already returns the right answer for
unmapped keys via its generated branch → `OTHER`, which is why the cards are correct. `LEAGUE_DISPLAY`
stops at `_nfl`/`_ncaaf`/`_cfl`/`_xfl`/`_ufl` (lines 376-380). One-line fix; **not fixed** (frontend
is not lane1's).

Same leak applies to `americanfootball_nfl_preseason` and `soccer_other`.

---

## 7. Artifacts

* **#3165** — new, `type:bug` `priority:p2` `area:frontend`.
* **#2819** — `issuecomment-5550917154` (render + recurrence + two body corrections).
* **#2866** — `issuecomment-5550921113` (detector blindness + anatomy correction).
* `artifacts/lane1-126-search-lsu-fifty-cards.png`.

Nothing fixed, nothing merged, no code touched. D35 throughout.

## 8. For 127

Traps worth carrying:

* **A census that groups by `(id, partition)` cannot detect a duplicate that crosses the
  partition** — the partition key is inside the grouping key. Ask what a census's `GROUP BY`
  makes impossible before reading its zero.
* **Read the population's creation history before calling a watch "un-exercised".** 270 of 271
  rows took a different path; the watched transition has a population of one.
* **A queue's own framing of a candidate can be the thing that is wrong.** "4 occurrences of
  'reachable'" was really two different words spelled the same.
* **Three duplicate-checks in one session all hit.** Search the issue *bodies* before writing; the
  best finding of the session was the one that survived that check.
