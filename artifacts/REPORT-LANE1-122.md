# lane1/122 — the ship holds a seventh time; two real NFL games are on the site marked FINAL 0–0

**PILLAR: MATCHING. SHIP: the Monday Night Football game stays ONE game** — Dallas Cowboys @
Seattle Seahawks, Dec 7, event `15304746`.

Session ran **2026-09-05 08:19Z → 08:5xZ** (01:19am PT). Stamped from `TZ=America/Los_Angeles date`
per notice 24.

---

## 0. The clock, first — night three is still not due

`date -u` → `Sat Sep 5 08:19:14 UTC 2026`. Night three's window opens **Sun 2026-09-06 06:40Z**,
which is **22.3 hours out**. §1 was not run, and no absence is reported.

This is the **fifth consecutive session** (118, 119, 120, 121, 122) handed a §1 roughly a day in
the future. Night four (Mon 9/7) is still the first night that can close #2978.

## 1. Night three — NOT DUE, not polled

No data point added. Night two's baseline remains the third-and-latest reading, unchanged and
byte-identical across 116/117/118.

## 2. The twin test — 13 rows, **seventh** confirmation

Unchanged. `15304746` Dallas Cowboys @ Seattle Seahawks, `2026-12-08 01:15:00+00:00`,
`espn_id 401873108`, **`external_id NULL`, 0 snapshots**. The other 12 rows carry both ids and
798–826 snapshots. Still not exercised — **not a finding**, per the queue's own grading table.

## 3. The daily gate — day 1 of 7, read for the **seventh** time on one calendar day

`GET /api/admin/statpal/authority-agreement`, `generated_at 2026-09-05T08:19:36Z`. **All four
sports read.**

| sport | denom | both | statpal_only | ours_only | pct | ours_covered_pct | governing | gate |
|---|---|---|---|---|---|---|---|---|
| `americanfootball_nfl` | 322 | 321 | 0 | 1 | **99.69** | 99.69 | pct + ours_covered_pct | **MEETS** |
| `baseball_mlb` | 287 | 157 | 65 | 65 | 54.70 | 70.72 | — | PENDING-NO-GOVERNING-NUMBER |
| `basketball_nba` | 1206 | 41 | 1165 | 0 | 3.40 | 100.00 | ours_covered_pct | MEETS |
| `icehockey_nhl` | 1404 | 32 | 1372 | 0 | 2.28 | 100.00 | ours_covered_pct | MEETS |

Every banked value reproduces exactly. `read: READ-OK` on all four, `read_failures: []`.
Earliest flip remains **Fri 2026-09-11**.

**NFL schedule side has MOVED** (see §5): `within 293 · off_by_hours 26 · wrong_day 2 ·
time_missing 0`. #2869's 9/4 measurement was `290 / 26 / 4`.

## 4. The pre-check — 0, **sixth** consecutive zero

`contested_ids = 0` at 2026-09-05 08:2xZ. The index remains un-violated and un-tripped.

---

## 5. WHAT THIS SESSION FOUND — two real NFL games render as FINAL 0–0, and the repair cannot reach them

Both filed. Two comments posted, no code touched (D35: matching symptoms are filed, not fixed,
until lane1/057 lands).

### (a) The green half — #2869's headline symptom is GONE

`#2869#issuecomment-5550597036`. The attended `reconcile-anchor-schedule` apply has run since 9/4:

| row | was | is now | `statpal_fixture_id` |
|---|---|---|---|
| `14780595` SF @ LA **Chargers** | 2026-09-11 00:35Z | **2026-12-18 01:15Z** | **`280730`** |
| `14781140` ARI @ LA **Rams** | 2026-09-13 20:25Z | **2026-10-18 20:05Z** | **`280610`** |

Both landed on exactly the date #2869 predicted and both now hold the StatPal contest id it named.
`GET /api/leagues/americanfootball_nfl` returns 8 `upcoming_games` and **neither phantom is among
them**; the only 00:35 row is `14632820`, the real SF @ LA Rams. The adjacent-cards symptom
photographed three times on 9/3 no longer reproduces. Dry run agrees:
`examined=30/244 · agrees=30 · authority_moves_us=0` where page one previously carried 2.

Wrong-day bucket: **5 → 4 → 2**.

### (b) The red half — the residue is two rows stamped into the preseason window

| id | espn_id | ours | authority | status | scores | odds snapshots |
|---|---|---|---|---|---|---|
| `14781719` LAC @ KC | `401873006` | 2026-08-15 20:00Z | **2026-10-18 20:25Z** (Wk 6) | `closed` | **NULL/NULL** | 807, last 08-30 |
| `15184679` MIN @ NYJ | `401873163` | 2026-08-15 17:00Z | **2027-01-03 18:00Z** (Wk 17) | `closed` | **NULL/NULL** | 816, last **09-03** |

Two StatPal-free confirmations, either of which stands alone:

1. **ESPN's id ordering places them exactly.** The NFL regular-season `espn_id` band is monotonic
   in kickoff date. `401873005` → Oct 18 20:25 · **`401873006` → Aug 15** · `401873007` → Oct 19.
   `401873162` → Jan 3 · **`401873163` → Aug 15** · `401873164` → Jan 3. Each is the single hole in
   its own slate (Oct 18 holds 10 rows; Jan 3 holds 12 across `…157`–`…169`). A whole-band scan for
   date-vs-id order violations returns **exactly these two** above the 2–4 day noise floor that
   ESPN's own Thu/Mon slot interleaving produces.
2. **The odds rail never agreed the games happened.** Both are `closed` with a `completed_at` ~3.5h
   after the fake kickoff and **no score on either side**, yet snapshots kept arriving for weeks —
   `15184679`'s most recent is **2026-09-03**, nineteen days after it was marked final.

gotcha #46 is **not** violated (`completed_at >= commence_time` holds), so that guard cannot catch
this class.

### (c) The mechanism — the repair is blind exactly where the defect went furthest

Not a paging limit. Raising `limit` cannot help: these rows are not in `eligible` at all
(`eligible = 244` of 322 NFL fixtures). `_window()` at
`backend/app/tasks/reconcile_anchor_schedule.py:284-289` excludes them **three times over**:

```python
Event.completed_at.is_(None),                    # both rows have one
Event.status.notin_(tuple(SETTLED_STATUSES)),    # frozenset({"completed","closed"}); both are 'closed'
Event.commence_time >= now - lookback,           # DEFAULT_LOOKBACK = 1 day; both sit 21d back
```

Each predicate is **a consequence of the defect the rail exists to repair**: the corruption moved
the kickoff into the past → behind the lookback → a settlement pass stamped `completed_at` and
flipped `status` to `closed` → the other two trip. An operator reading
`examined=30/244 · authority_moves_us=0` would reasonably conclude NFL scheduling is done.

No widening proposed — a 21-day lookback over settled rows is a far bigger blast radius than this
ship needs, and the remedy is lane1/057's call.

### (d) LOOK (D48, phone width 390px, production, 2026-09-05)

Both event pages state the game was played and finished **with no score**:

- `/events/14781719` — `Final · NFL Net · Aug 15, 2026 · 4:00 PM EDT`; **Chiefs 0-0**,
  **Chargers 0-0**, **FINAL** pill; Win Probability draws a full Q1–F axis over 4:00–8:08 PM and
  closes at "Chiefs 57% — Chargers 43%". Shot: `/tmp/l122-lac-kc.png`.
- `/events/15184679` — `Final · ESPN Unlmtd · Aug 15, 2026 · 1:00 PM EDT`; **Jets 0-0**,
  **Vikings 0-0**, **FINAL**, dead-flat probability line. Shot: `/tmp/l122-min-nyj.png`.

So the site says a Week 6 game and a Week 17 game were played on August 15 and ended 0–0, while
both are absent from the dates they are actually played on. That is "settled means settled"
inverted — settled language on a game that has not happened.

### (e) #2969's premise is falsified, and its proposed rule would delete two real games

`#2969#issuecomment-5550599296`. **This is the finding that mattered most.**

#2969 names four "duplicate pairs" where one row has the wrong franchise (a Los Angeles / New York
city collision), to be adjudicated by `statpal_fixture_id IS NULL`. That reading does not survive:

- **Pairs 1 and 2 were never phantoms.** Both now carry StatPal fixture ids (§5a). They are the
  real Week 15 SF @ Chargers and Week 6 ARI @ Rams. The 49ers play the Rams in Week 1 *and* the
  Chargers in Week 15; Arizona plays the Chargers in Week 1 *and* the Rams in Week 6. Fixing the
  kickoff dissolved the "duplicate" — nothing was merged or deleted.
- **Pairs 3 and 4 are the same shape.** The Vikings play the Giants in preseason *and* the Jets in
  Week 17; Kansas City hosts the Rams in preseason *and* the Chargers in Week 6. All four rows name
  a real fixture with the correct franchise. The preseason rows hold real final scores (13–10,
  20–12) and **zero** odds snapshots; the "phantom" rows hold correctly-positioned ESPN ids and
  807/816 snapshots.
- **Applied to pairs 3 and 4, the discriminator selects the row that should be kept.** Week 6
  LAC @ KC and Week 17 MIN @ NYJ exist in our database **only** as those two rows. Discard them and
  both games vanish, while `receipts.ours_only` drops and reads as a win.

The general lesson, which is why this is worth writing down: the stamper matches on **team names
plus kickoff ±1h**, so these rows' `statpal_fixture_id` is NULL *because of the defect*. **A field
whose emptiness is a downstream effect of the bug cannot be used to adjudicate the bug.** Saved to
memory as `r_discriminator_nulled_by_the_defect`, with `r_repair_window_excludes_the_worst_cases`
for §5c.

Suggested (lane1's call, not taken): pairs 1 and 2 struck; pairs 3 and 4 folded into #2869; #2969
closed as empty. **No labels, state or ownership changed** — one owner per issue.

---

## 6. What was NOT done, deliberately

- Night three not polled (not due, §0).
- Nothing fixed. D35 holds: matching symptoms are filed until #2693/lane1/057 lands.
- Row B (#3070) not re-measured — 118 characterised it completely.
- The other three sports' banked values not re-derived, only re-read and confirmed.
- No issue opened against the iOS client (121 §5a: mechanism recorded, no defect reachable).
- The zero-game Discover feed not touched (#2957, not lane1's).
- #2896 and #3117 not re-filed — both already carry specimens.

## 7. Housekeeping

`MEMORY.md` was at 20.6KB, over the compaction threshold. Compacted to **16.7KB** by moving two
coherent clusters into new topic files following the established pattern:
`INDEX-performance-measurement.md` (44 entries) and `INDEX-sandbox-and-evidence-rails.md`
(26 entries). No entry was dropped.
