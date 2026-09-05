# REPORT — lane1/124

**PILLAR: MATCHING · TRUTH.** **SHIP: the Monday Night Football game stays ONE game** — Dallas
Cowboys @ Seattle Seahawks, Dec 7, event `15304746`. Live and still a single row after **nine**
readings.

Session ran **2026-09-05 08:48Z → ~09:1xZ** (01:48am PT, stamped from `TZ=America/Los_Angeles
date`; notice 24 — the Mac's clock is EDT, PT is `date` minus 3h).

---

## 0. The clock — night three is NOT due, seventh consecutive session

`date -u` → `2026-09-05 08:48:10Z`. Night three's window opens **Sun 2026-09-06 06:40Z** —
**21.87 hours away.** §1 skipped. I did not poll and did not report an absence.

Sessions 118–124 have now *all* been handed a §1 in the future. Note also that **123 ran at 08:36Z
and I ran at 08:48Z — twelve minutes apart.** The restock cadence is far faster than the thing the
queue is waiting on, which is why §5's "liveness" re-read below carries no new information.

## 1. Night three — NOT DUE. No poll taken.

Nothing to report. Night-two baseline unchanged in the queue. Night four (Mon 9/7) is still the
first night that can close #2978.

## 2. The twin test — 13 rows, ninth consecutive confirmation

Exactly **13 rows**, Dec 6–10, `sport_id = 1`. `15304746` Dallas Cowboys @ Seattle Seahawks
`2026-12-08 01:15Z`, `espn_id 401873108`, **`external_id NULL`, 0 snaps**. The other 12 all carry
both ids and 798–826 snapshots.

**Verdict: not yet exercised. Not a finding.** Read at 08:48Z.

## 3. The gate reading — all four sports, day 1 re-read a NINTH time

`GET /api/admin/statpal/authority-agreement`, `generated_at 2026-09-05T08:48:30Z`.

| sport | denom | both | sp_only | ours_only | pct | ours_covered_pct | governing | gate |
|---|---|---|---|---|---|---|---|---|
| `americanfootball_nfl` | 322 | 321 | 0 | 1 | 99.69 | 99.69 | `pct` + `ours_covered_pct` | **MEETS** |
| `baseball_mlb` | 287 | 157 | 65 | 65 | 54.70 | 70.72 | — | **PENDING-NO-GOVERNING-NUMBER** |
| `basketball_nba` | 1206 | 41 | 1165 | 0 | 3.40 | 100.00 | `ours_covered_pct` | **MEETS** |
| `icehockey_nhl` | 1404 | 32 | 1372 | 0 | 2.28 | 100.00 | `ours_covered_pct` | **MEETS** |

All four `READ-OK`, zero `read_failures`. NFL schedule side `within 293 · off_by_hours 26 ·
wrong_day 2` — identical to 123. **Still day 1 of 7; earliest flip Fri 2026-09-11.** Every banked
number reproduced exactly; nothing re-derived.

## 4. Row B — untouched, as ruled

`14751059` still the sole `ours_only` receipt, `column_holds: null`. Not re-measured (§4).

## 5. The two FINAL-0–0 rows — re-read 12 minutes after 123, unchanged

`14781719` LAC@KC and `15184679` MIN@NYJ: both `closed`, both `NULL/NULL` scores, snaps 807/816,
last snaps `08-30 01:09Z` and `09-03 23:39Z` — **byte-identical to 123's read taken 12 minutes
earlier.** `wrong_day` still 2.

**This is not a new data point** and I am not recording it as one. The 24h liveness baseline
belongs to 123; the next meaningful re-read is a session at least a day later.

## 6. THE PRE-CHECK — 0, eighth consecutive zero

`contested_ids = 0` at `2026-09-05 08:48Z`.

---

# THE SESSION'S WORK — the `anchors` block, which §3 has never banked

The queue's §3 tells you to read the gate payload and banks `identity` and `schedule` from it.
**It has never banked the third sub-object the same payload serves: `anchors`.** That was the
unexamined thing sitting inside a file seven sessions had already opened.

| sport | anchored | unanchored | mismatch | polluted_column | pct_of_both |
|---|---|---|---|---|---|
| NFL | 247 | 26 | **0** | **48** | 76.95 |
| MLB | 135 | 0 | **22** | 0 | 85.99 |
| NBA | 41 | 0 | 0 | 0 | 100.00 |
| NHL | 27 | 5 | 0 | 0 | 84.38 |

NFL's `polluted_column: 48` is already **#2963** (the column holds `statpal_live_<away>_<home>`, a
sentence, not an id). Not new.

**MLB's `mismatch: 22` is the only non-zero mismatch on any sport, and it is misfiled.**

## FINDING 1 — the agreement row files namespace rows as matching errors

`backend/app/utils/authority_agreement.py:596-604` has exactly four outcomes: `polluted`
(non-digit), `anchored` (string-equal), `mismatch` (digit, not equal), `unanchored` (empty). There
is no foreign-id-space bucket, so any digit id that is not string-equal to the paired fixture ref
falls into `mismatch`.

The stamper reading **the same column** has that bucket —
`backend/app/tasks/stamp_v1_statpal_fixtures.py:368-389`, `VERDICT_FOREIGN_ID_SPACE`, whose comment
is explicit:

> Separated from `CONTRADICTION` because the two are different bugs with different owners, and
> **folding them would file 85 namespace rows as matching errors.** … MLB is why it exists.

All 22 MLB `anchor_mismatch` receipts hold a `1329…` value — every one of them the `livescores.id`
space documented in **#3094**. So the endpoint a human reads reports #3094's authority-lane defect
as a matching contradiction, i.e. lane1's. This is precisely the mis-attribution the stamper's
comment was written to prevent, reappearing one layer up.

**#3094's own "Notable" paragraph is wrong in an instructive way.** It says the agreement row
`reads clean` over this because `polluted_column: 0`. It does not read clean — it reads
*misattributed*, in a different and non-zero bucket. And the repair it proposes ("widen the
pollution check") would be wrong too: that folds namespace rows into the *sentence* bucket and
loses them a second way. The right shape is the stamper's fourth bucket, computed as a
**dereference** against the fixture refs that pass actually read (already in scope at that loop as
`by_key_f`) — never a digit count, which is the whole of D55.

Filed: `#3094#issuecomment-5550714976`. **Not claimed** — authority lane's under D50.

## FINDING 2 — the proposed repoint collides, and it collides on the twins

#3094 says *"the correct 6-digit space has zero collisions."* True today. A blanket repoint would
end that. **5 of the 22 target `season-schedule` ids are already held by another event row, and in
all 5 the holder is the same game's twin:**

| game (UTC) | holds the *correct* id | holds `livescores.id` | scores |
|---|---|---|---|
| Athletics @ Rangers 09-01 00:05 | `15291459` `355457` closed | `15298222` `1329192534` completed | **0–7 vs 1–8** |
| White Sox @ Astros 09-01 00:10 | `15291460` `355453` closed | `15298223` `1329192535` completed | **2–3 vs 3–6** |
| Yankees @ Angels 09-01 01:38 | `15291547` `355454` closed | `15298227` `1329192539` completed | **1–4 vs 1–10** |
| Phillies @ D-backs 09-01 01:40 | `15291548` `355448` closed | `15298229` `1329192540` completed | 2–1 vs 2–1 |
| Nationals @ Dodgers 09-05 02:10 | `15295439` `362160` suspended | `15303442` `1329192594` completed | 3–5 vs 3–5 |

The correct-id half carries **no `espn_id` and no `external_id`** in all 5 — the #2476/#3093 orphan
shape. The other 17 targets are held by nothing and repoint cleanly.

Also: the `1329%` population is **336** today against #3094's **322** on 2026-09-04 (+14, same
query shape); 307 of the 336 also carry an `espn_id`. `events` has no `updated_at`, so this is a
count delta and **not** proof the live path wrote in the last day — stated that way in the comment.

## FINDING 3 — the score disagreement is user-visible, and the losing row is a frozen prefix

**LOOK, D48, production, phone width 390×844, 2026-09-05.** #3093 asserts the disagreement *"is
user-visible"* as an inference from a table, with no rendered page. It is now measured.

`/events/15291547` and `/events/15298227` are **both** reachable, both fully chromed, both headed
`Final · Aug 31, 2026 · 9:38 PM EDT`, both chipped **Angels WON** — and they print
**Angels 4 — Yankees 1** and **Angels 10 — Yankees 1**.

The losing row is not a rival result. Its chart domain (10:00 PM → **11:07 PM**) sits strictly
inside the winner's (9:38 PM → **12:51 AM**), the Yankees are on 1 in both, and 4–1 is a consistent
prefix of a game ending 10–1. It is **one game captured partway and closed** (`status='closed'` vs
`completed`). Same shape on every pair: the `closed` half is always earlier and lower. **That makes
the survivor unambiguous on all four score-disagreeing pairs — the `completed`/`espn_id` row.**

Also corrected there: #3093's body prints its score column home–away under an away-@-home heading,
so "Athletics @ Texas Rangers — 7–0" reads as an Athletics win when they were shut out 0–7.
Flagged only so nobody picks a survivor off that table.

Filed: `#3093#issuecomment-5550741352`. **Not claimed** — #2693 owns the repair (D35).

## FINDING 4 — a settled chart draws nothing over 633 real snapshots (NEW ISSUE #3151)

Both twin pages render a Win Probability card with axes, a correct game-length x-axis, **inning
markers `B4 B5 T8 T9 F` drawn inside the plot**, a `Lead changes (7)` chip and an endpoint dot —
and **no series**.

```
win_prob_snapshots:  15291547 → 101      15298227 → 633      14781719 → (no row)
```

**633 snapshots behind an empty plot.** The domain and the annotations are derived from that series,
so the component demonstrably read it, computed the extent, and drew no line.

`14781719` is the control that keeps this from being filed with #2869: that NFL page shows the same
visual emptiness and there it is **honest** — zero snapshots. And it is not **#2896**, which is the
honest no-odds case where the card says *"Tracking will begin when odds are available."* Here the
card claims a journey and omits it.

Caveat stated in the issue: the default `Since Start` tab was the only one exercised (`look.sh`
cannot click), so if `All` draws the line the defect is the default tab rather than the series.

**Filed as #3151** (`type:bug`, `priority:p2`, `area:frontend`). **Not claimed — not lane1's.**

---

## What I did NOT do

- No poll of the sentinel (not due).
- Did not re-measure row B, the 26 `off_by_hours` rows, Week 1, Sentry, the feed, the phone, the
  widget or the watch — all banked.
- Did not widen `_window()`, did not touch the unique index, did not fix anything under D35.
- Did not re-file #2896, #1739, #2969, #2957 or #3117.

## Method note for the next session

The queue's own §12 method paid out an eighth time, with a new variant worth naming:

> **A file you have already opened seven times can still hold an unread section.** §3 says "the gate
> payload serves FOUR sports — read all four or say which one you read," and 119–123 all did. But
> the payload serves four sports × **three** sub-objects, and only two of the three were ever
> banked. The scope discipline was applied on one axis and not the other.

Second, smaller: **an issue's own self-assessment is a claim, not a measurement.** #3094 says the
agreement row "reads clean" over its defect. Reading the row showed it does not — it reads wrong,
in a bucket that hands the work to a different lane. Both of this session's issue comments are
corrections to a sentence the issue's own author wrote about a surface they did not open.
