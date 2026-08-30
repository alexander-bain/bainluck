# LAT-P156 — the third copy of a side-picker, and a guard that watched a variable name

**NEEDLE: latency 19 ms @ 2026-08-30T22:33:44Z — ⬆️ up 1 ms from LAT-P155's 18 ms, inside the
18–23 ms band the pool has held for two days.**
DIAG: latency-build **REFUSED** (2 of 7 member paths cold, floor 4; 2 of 3 graded surfaces). A
null, published as a null. The pool still cannot see this conveyor, and this cycle it could not
have: the ship is a Celery grader, not an HTTP path.

Pillar: **TRUTH**. Ship: a settled spread prop stops showing the wrong team's result.

---

## What this cycle did, in one line

`#2352` — the spread grader handed every away leg of a shared-city matchup the **home** team's
margin. Measured at **39 wrong `is_winner` rows** out of 17,064, fixed, and — unlike #2351 — the
historical rows **repair themselves**, because this cohort has a live re-grade rail and the fix
widens it to reach all 39.

Branch `program/latency-155` @ `9aca2310`, stacked on `program/latency-154` (CERT-501 GREEN,
unmerged).

---

## Why this and not a ring entry

Step 0 (`grep -B2 -A6 'BLOCK — token withheld' CERT-QUEUE.md`) came up empty — LAT-P152 and
LAT-P153 cleared the last two blocked branches and CERT-501 came back GREEN at 22:04Z. Step 1 came
up empty too, for the second cycle running. The ring, re-measured at 22:0xZ over 500 entries
(newest 1.5 h, spanning 147 h):

```
 62  p50  8,479  /api/events/typeahead              LANDED (-128), decaying
 47  p50  7,426  /api/events/{id}/related-futures   LANDED (-129)
 36  p50 12,080  /api/teams/{id}/prop-families      LANDED (-130)
 12  p50  7,919  /api/feed                          LANDED (-126) — still all cache misses; Red (~20 ux/lane1 branches)
 11  p50 12,120  /api/futures                       🚫 NO CALLER — and 6 of those 11 are LAT-P155's own probes
 11  p50  9,724  /api/playoffs/{league_slug}        silent 23 h — already fixed
  9  p50 18,637  /api/event/{key}                   LANDED (-131)
  9  p50 12,782  /api/events/search-suggestions     LANDED (-151)
  8  p50  9,445  /api/tournaments/{slug}            LANDED (-132)
  5  p50  7,377  /api/futures/{market_id}           LANDED (-148)
  4  p50 12,337  /api/events                        🚫 NO CALLER in the slow shape
```

`/api/futures` climbing from 5 to 11 is a worked example of LAT-P151's rule: on a quiet endpoint
most of the "slow requests" are us. LAT-P155 probed it fifteen times in twenty minutes and those
probes are the entire delta. It still has no caller.

So the cycle took LAT-P155's step 0c. It is not a latency ship and this report does not pretend
otherwise — but #2350 stands unresolved (no movement on the issue since 20:44Z), which means
ranking the ring against a saturated box is still ranking noise, and the only user-visible
correctness defect on the board had its remedy already written.

---

## The defect

```python
if team_tokens & home_tokens:      margin = home_score - away_score
elif team_tokens & away_tokens:    margin = away_score - home_score
```

Where the two clubs share a token, the shared token alone satisfies the first branch. Every away
ladder is graded off the home margin.

The repository already catalogues this class — `SHARED_CITY_DIFFERENT_CLUB` in
`test_names_match_authority_2046.py` — and it is broader than "shared city". NCAAMB carried 17 of
the 39 wrong rows because **`UC` is a shared token across the whole University of California
system**: `UC Davis wins by over 3.5 Points` in UC Irvine 79 – UC Davis 69 read the Anteaters' +10
and returned True. So did `Utah` (Southern Utah vs Utah Tech) and `Virginia` (Virginia vs Virginia
Tech).

## The census, and why it is per-row

**39 wrong of 17,064.** Measured by importing the shipped `_spread_outcome_is_winner` and comparing
its verdict to the stored `is_winner` for every production row, against the linked final score.

LAT-P155's two rules were followed literally, because they were expensive to learn:

* **a shape consistent with a bug is not a count of the bug.** 546 rows sit in matchups whose clubs
  share a token — that is the population at risk, not the damage. The damage is 39.
* **a corruption count is a function of the identity code**, so it was computed with the helper as
  it will ship, not with a re-implementation.

Breakdown: 27 of the 39 are directly attributable to the collision (the old side-picker and the new
one disagree, and the stored value matches the old one). The other 12 are legacy rows from before
#939's complementary-flip fix — the new grader repairs those too.

## The repair rail — the part that makes this different from #2351

`game_score` is not in `OVERWRITABLE_WINNER_SOURCES_SQL`, so the main resolver's candidate scan
will never pull these markets again. #2351's 507 wrong rows are locked for exactly this reason and
their cleanup is still ungranted.

Spreads are luckier: `_regrade_kalshi_nhl_spread_inversions` is a live, write-on-change re-grade
that runs every `backfill_winners` cycle and rewrites `is_winner` **without** touching
`resolution_source`. It was scoped `^KX(NHL|NBA|MLB)SPREAD` and could reach only **21 of the 39**.
The other 18 — 17 NCAAMB, 1 MLS — were unreachable, and NCAAMB is both the largest family (6,972
rows) and the one the catalogue names twice.

Widened to every full-game Kalshi spread family. Replayed over the exact cohort it will scan
(20,632 rows pulled complete, no truncation):

```
17,064  reaches the python loop
17,008  already correct — no write
    39  FLIPPED          <- all 39, and nothing else
    17  unresolved
 3,568  excluded by the SQL ticker predicate
```

Measured cost of the widening: **2,576 ms → 2,678 ms**. Negligible against #1887's budget guard,
which LAT-P154 left with ~6 s of headroom.

### The hazard the widening creates, and the two filters that close it

`_SPREAD_RE` matches `"Detroit wins the 1H by over 9.5 points"` **on purpose** — the main resolver
detects `1h` in the ticker and grades it against a reconstructed halftime score. The re-grade rail
holds only the full-time score. An unfiltered widening would have pulled `KXNBA1HSPREAD` and
`KXNCAAMB1HSPREAD` — **3,098 production rows** — and written permanently wrong `game_score`
winners into them. That would have been a bigger defect than the one being fixed.

Closed twice, deliberately:

1. a SQL ticker predicate `!~ '[0-9](H|Q|HALF)SPREAD'`, which excludes the eight period families
   while keeping `KXLIGUE1SPREAD` (a digit before SPREAD, but a full-game market);
2. a **name** test in the Python loop, which cannot be fooled by a Kalshi family we have not seen.

Filter 2 catches **zero** rows today — the replay proves filter 1 is complete for the current
population. That is the honest statement: it is defence against the next family, not live work.

Empirically verified rather than reasoned from the regex: of the 13 distinct period shapes in
production, exactly the two `wins the 1H` families match `_SPREAD_RE`. `wins 1H`, `wins 2H` and
`wins nQ` do not.

## The third copy the issue did not name

`#2352` named two call sites, both of which are the same function. Grepping for the **problem**
rather than the remedy found a third: `_resolve_kalshi_period_props` carried its own inline
home-first intersection **and** matched on raw `.lower().split()` instead of `normalize_team_name`,
so it had the collision plus #939's accent bug ("Montréal" never matched).

Production damage: **zero**. No `scoring_plays` row has ever been written for a spread outcome —
the source does not appear in the cohort at all. So this is prevention, and it is stated as
prevention. Converting it leaves this module with **one** side-picker instead of three.

## The 17 refusals — the other half of the ledger

Ambiguity now returns `None` and the leg is skipped. A skipped leg keeps whatever it holds
**forever**, so "we refuse it" is only safe if what is sitting there is right. Checked both
readings of all 17:

* **16** — both readings agree, and the stored value matches. The ambiguity is harmless.
* **1** — `Virginia wins by over 3.5 Points` in Virginia 76 – Virginia Tech 72. Home reading True,
  away reading False, stored True. It is correct, by the luck of the old home-first bias.

Forward, 17 in 17,064 is 0.1% recall for a coin flip avoided, and `Virginia Tech wins by over 3.5`
in the same market still grades. Both refusal paths are now **counted** (`unresolved`,
`spread_unresolved_team`) — CERT-499's lesson, applied before a cert had to find it.

---

## Guards

54 guards, **17 mutants, 17 killed**. Nothing asserts via `inspect.getsource`.

M0 is a whole-file revert to the exact bytes CERT-501 graded (`git checkout 5d1a026c -- …`, per
LAT-P153's rule that a partial revert masks the defect). It dies at **import**, so the behavioural
proof for the side-picker is **M1's 21 red**, not M0 — saying so because "17/17 killed" would
otherwise overstate what M0 proved.

### The guard that was watching a variable name

`test_period_spread_uses_team_matching` read `inspect.getsource(_resolve_kalshi_period_props)` and
asserted the literal strings `"home_tokens"` and `"away_tokens"` appeared in the spread section.
Its docstring says *"must match the specific team, not either team"*. It asserted neither thing:

* it **passed for the entire life of the defect it claimed to guard** — the broken code contained
  those two names, which is precisely how the bug was written; and
* it went red only when the side-picker moved into a helper and the locals were inlined, i.e. it
  failed on a strict improvement.

Replaced, not deleted, with the behavioural property: the two sides must get different verdicts
from the same score. This is the third cycle running that a source-text guard in this module has
been found watching the wrong thing (LAT-P154's `getsource` vs its own docstring, LAT-P155's
fifteen guards, now this). **A guard that reads source text in a module whose docstrings quote its
own SQL is a guard on prose.**

## What this cycle did NOT do

* **#2351's 507 wrong rows are still not repaired.** Different cohort, no rail, cleanup ungranted.
* **`/api/feed` cold build is still open** — the default landing page, 12 slow requests in 24 h,
  every one a cache miss, p50 7,919 ms against a 6 s client budget. Red: ~20 branches from `lane1/`
  and `program/ux-*` touch `routes/feed.py`. Prefer a stage outside that file.
* **#2350 is unresolved** and nothing here bears on it.
* **#1887 stays open.** This branch does not touch the latency ship bar.
