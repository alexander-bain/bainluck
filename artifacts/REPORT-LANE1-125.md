# lane1/125 — night three still not due (8th session); the `live` sub-object was never opened, and it holds a twin detector

**PILLAR: MATCHING · TRUTH.** **SHIP: the Monday Night Football game stays ONE game** — Dallas
Cowboys @ Seattle Seahawks, Dec 7, event `15304746`. Live and still a single row after **ten**
readings.

Ran Sat 2026-09-05, **09:04Z / 02:04am PT** (`TZ=America/Los_Angeles date`; notice 24).

---

## 0. Clock — §1 NOT due, for the eighth consecutive session

`date -u` = `2026-09-05 09:04:38Z`. Night three's window opens **Sun 2026-09-06 06:40Z** —
**21.6h out.** I did not poll and did not report an absence.

124 ran at 08:48Z, **sixteen minutes** before me. Per its own §5 trap I did not re-read its dated
baselines (§7's liveness table, the day-1 identity/schedule numbers) and call the result a
confirmation.

**Night four (Mon 9/7) is still the first night that can close #2978.**

## 1. §2 twin test — 13 rows, TENTH hold

Exactly 13 rows Dec 6–10, `sport_id = 1`. `15304746` still `external_id NULL` / **0 snaps**; the
other 12 carry both ids and 798–826 snaps. Not yet exercised; **not a finding**.

## 2. §14 pre-check — 0 contested `espn_id`, NINTH consecutive zero

And this session found out **why that zero has been so easy to get.**

---

## 3. THE FINDING — `live.duplicate_ids` is a second twin detector, on a second id space, and it is non-zero

### What was never read

§3 of queue 124 corrected 119–123 for reading two of the gate payload's three sub-objects. The
payload is larger than that again. Each sport row carries **six** keys —
`agreement`, `live`, `stamper`, `sport_key`, `last_pass_at`, `pass_age_seconds` — and `agreement`
carries **twelve**, including a `receipts` object with **six** buckets. Only `identity`,
`schedule` and (since 124) `anchors` had ever been opened.

**`live` had never been opened by any session.** It publishes:

| sport | anchors | column_agrees | half_links | **duplicate_ids** |
|---|---|---|---|---|
| NFL | 247 | 247 | 0 | **0** |
| MLB | 80 | 80 | 0 | **5** |
| NBA | 41 | 41 | 0 | **2** |
| NHL | 27 | 27 | 0 | **3** |

`admin_providers.py:1888` says exactly what it counts:

> *"Two of our rows holding one StatPal id. The unique anchor index already makes this impossible
> for two ANCHORED rows, so a hit here is a row whose column was written by something that did not
> write an anchor."*

That is a **twin detector**, published daily, keyed on `statpal_fixture_id`.

### Why nine sessions of the pre-check could not see it

lane1's standing pre-check groups on `espn_id`. In **all ten** groups the two rows carry
**different or NULL** `espn_id`s. The contested-`espn_id` zero and the ten contested-fixture-id
groups are both true simultaneously — the pre-check is blind to this class **by construction**,
not by luck.

### The ten groups, and the two classes inside them

| sport | fid | id_a | id_b | gap | matchup | all 3 gates pass? |
|---|---|---|---|---|---|---|
| nhl | 637987 | 6032536 | 14631266 | 0.00h | False | no |
| nhl | 627215 | 11962575 | 13437248 | 0.00h | False | no |
| mlb | 1329190569 | 12405461 | 12542856 | 0.02h | True | yes (correct — one game) |
| mlb | 1329200227 | 12908267 | 12939909 | 2.48h | True | yes (correct — same score 5-6) |
| **mlb** | **1329192512** | **15295964** | **15296101** | **6.00h** | **True** | **YES — TWO REAL GAMES** |
| mlb | 1329192500 | 15295242 | 15295413 | 6.17h | True | no (by 600s) |
| mlb | 1329190539 | 12257614 | 12257615 | 17.48h | True | no |
| nba | 1027792 | 14275110 | 14276969 | 23.83h | True | no |
| nba | 1027790 | 14271392 | 14276967 | 24.17h | True | no |
| nhl | 637968 | 14623538 | 14627433 | 47.00h | True | no |

### The boundary defect (filed #3154, p1)

`MAX_ABSORPTION_SEPARATION_SECONDS = 21600`, and **both** Python guards refuse only on `gap > `:

- `event_merge_invariant.corroboration_reason`
- `espn_candidate_selection.py:260`

`1329192512` is a **real doubleheader at exactly 21600.00s** — D-backs @ Giants, distinct ESPN ids
`401816744` / `401816729`, scores 7-1 and 2-7. Arm A passes (shared fid), `matchup_agrees` is True
(identical raw names, both `*_normalized` NULL), the separation arm does not fire.
`corroboration_reason()` returns **`None`**.

**Nothing deletes it today only because every SQL caller admits `ABS(Δ) < 21600` strictly** and so
never selects the pair. That is precisely the accidental safety #1947 exists to remove — the module
docstring says the corroboration moved into the guard so *"a caller that drops its window no longer
drops the safety with it"*, and at the boundary it did not move.

**The margin sentence is also wrong.** The comment above the constant reasons from *"the tightest
true-series pair measured in 60 days is 42.0h"*. That was measured over `espn_id` pairs. Over
`statpal_fixture_id` pairs the tightest genuine two-games pair is **6.00h — the cap itself**; the
next is 6.17h, refused by 600 seconds.

**The guard is wrong in the other direction too.** `627215` and `637987` are single games (same
kickoff to the second; `637987` has the **same final score on both rows**) and are **refused**
because `matchup_agrees` compares raw names while `*_team_normalized` is NULL: "Vancouver" vs
"Vancouver Canucks", "Colorado" vs "Colorado Avalanche". The short-named row is Kalshi-created in
both cases.

### #1947's measurement is falsified

#1947 records, for the 60 days to 2026-08-17: *"`external_id` and **`statpal_fixture_id` have zero
such pairs**"*. Today: **ten**. Commented on #1947.

---

## 4. LOOK (D48) — the slot is user-visible, and one page is a second #3151

`/events/14877917` and `/events/15295242` both render, both headed
`Final · MLB.TV, MLB Net, YES · Aug 29, 2026 · 1:05 PM EDT`, both **Sox WON**:

| page | hero | chart domain | lead changes | curve? |
|---|---|---|---|---|
| `14877917` | **Sox 2 – Yankees 0** | 1:30 → 2:32 PM | 4 | yes |
| `15295242` | **Sox 6 – Yankees 0** | 1:05 → 4:04 PM | 1 | **empty** |

Loser's domain sits strictly inside the winner's — the §6 frozen-prefix shape, on a **new** pair
(not #3093's `15291547`/`15298227`). Survivor is the `completed` row, consistent with the
established rule.

**Two things worth carrying forward:**

- **`14877917` renders "Sox 2" while its columns hold `away_score = 0, home_score = 0`.** The hero
  is not reading those columns. Anyone reading a FINAL-0-0 row off the DB (#2869) must not assume
  the page shows 0-0.
- **`15295242` draws an empty plot over 893 real `win_prob_snapshots`** — a second #3151, and a
  better one than the first, because **its twin renders a curve fine**. Same game, same tab, one
  plots and one does not, so the empty plot is not a property of "settled MLB game".

## 5. The Aug 29 slot has THREE rows for two games

| id | commence | status | score | espn_id | fid |
|---|---|---|---|---|---|
| `15295242` | 08-29 17:05 | completed | 6-0 | **401874913** | 1329192500 |
| `14877917` | 08-29 17:05 | closed | 0-0 | 401815659 | 354351 |
| `15295413` | 08-29 23:15 | completed | 2-9 | 401816717 | 1329192500 |

`401874913` is the **only** MLB row in the entire `4018749xx` band; every other id on that slate is
`4018167xx`, and that ladder is 1:1 monotonic with a distinct fid per game
(`1329192493`…`1329192512`). MLB's column holds **1,624 six-digit** (350658..364956) and
**336 ten-digit** (1329190500..1329202658) ids — the dual namespace of #3094.

## 6. The soccer 8,272 are the EMPTY STRING, not `statpal_live_*` (commented on #2963)

`statpal_fixture_id`: NULL **220,348** · `''` **8,272** · real **3,238** · total 231,858.

#2963's table files the soccer 8,272 and the NFL 48 both as "synthetic". Only the NFL 48 are
`statpal_live_<home>_<away>`; the soccer 8,272 are `''`. Both read as "already linked" to an
`IS NULL` guard, but only one would build a team-name anchor.

**A repair for the `''` half already exists and has not drained** — `admin_repairs.py:175`
registers Queue 340's `repair_statpal_fixture_id_blanks`, and the population is still exactly
8,272. Not a new finding; a built, unrun rail.

## 7. Filed this session

- **#3154** (NEW, p1, `matching-symptom`) — the zero-margin boundary, the ten-group census, both
  guard-direction errors, the three-row slot. **Filed, not fixed** (D35).
- **#1947** — comment: the 2026-08-17 "zero such pairs" measurement is now ten; the 42.0h margin
  needs re-deriving across all of `PROVIDER_ID_COLUMNS`.
- **#2963** — comment: `''` vs `statpal_live_*`; Queue 340's repair exists and has not drained;
  MLB 6-digit 1,609→1,624 and 10-digit 321→336 (count delta only — `events` has no `updated_at`).
- **#3151** — comment: second specimen, with a twin that renders correctly as the control.

Nothing built, nothing merged, no cert staged. No repo code changed.

## 8. Traps earned this session

- **A queue that tells you to be exhaustive on one axis can still be under-counting the axes.**
  124 found `agreement` had three sub-objects where two were read. The sport row has **six** keys
  and `agreement` has **twelve**; `live` had never been opened at all. Enumerate the container
  before trusting any "read all N" instruction — including this report's.
- **Two green pre-checks on two id spaces are not one green pre-check.** Nine zeros on `espn_id`
  said nothing about `statpal_fixture_id`, and the pairs are disjoint by construction.
- **A guard with a measured margin can have zero margin in a space nobody measured.** The 42.0h
  floor was real — for `espn_id`. Ask which population a safety constant was measured over.
- **`>` and `<` disagree about the boundary.** The SQL callers exclude 21600; the Python guards
  admit it. A production row sits on exactly that value.
- **A twin whose rows both render is stronger evidence than either page alone** — `15295242`'s
  empty chart is only diagnosable because `14877917` draws one for the same game.
- **The rendered hero can disagree with the score columns** (`14877917`: DB 0-0, page 2-0).
- **Grep the repo for a repair before filing a population you just counted** — `admin_repairs.py`
  already owned the 8,272.
