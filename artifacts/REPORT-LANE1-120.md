# REPORT — lane1/120

**PILLAR: MATCHING · SHIP: the Monday Night Football game stays ONE game** (Dallas Cowboys @
Seattle Seahawks, Dec 7, event `15304746`).

Session **2026-09-05 07:55Z → 08:25Z** (00:55–01:25am PT Sat). Stamps from
`TZ=America/Los_Angeles date`; PT is `date` minus 3h (notice 24).

**Production reads only.** No cert, no merge, no push, no data write, no code change.

---

## §0 — the clock caught a third consecutive session

`date -u` → **2026-09-05 07:55:00Z**. The queue header stamps itself **08:05Z**, ten minutes in my
future. Night three's window opens **2026-09-06 06:40Z**, ~22h45m out.

**§1 not due. Did not poll. Did not report an absence.** Night three is still the third data point
and remains unmeasured; night four (Mon 9/7) is still the first night that can close #2978.

## §2 — the twin test: 13 rows, a fifth consecutive confirmation

| | |
|---|---|
| rows, NFL, `commence_time` in `[2026-12-06, 2026-12-10)` | **13** |
| `15304746` Dallas @ Seattle, Dec 8 01:15Z | `espn_id 401873108` · **`external_id NULL`** · **0 snaps** |
| the other 12 | both ids present · **798–826** snaps |

The "not yet exercised" branch, unchanged. **Not a finding.** No 14th row; the twin has not
reproduced in the wild. Read at 07:56Z.

## §10 — pre-check

```
contested_ids = 0   (2026-09-05 07:56Z)
```

Fourth consecutive zero. The index holds and remains un-tripped.

## §3 — the gate, all four sports (the trap says read all four)

`generated_at 2026-09-05T07:55:34Z`. Day 1 of 7 — this is the **fifth** read of the same calendar
day, not a new row. Earliest flip **Fri 2026-09-11**.

| sport | denom | both | statpal_only | ours_only | governing → gate |
|---|---|---|---|---|---|
| **NFL** | 322 | 321 | 0 | **1** | `pct` 99.69 + `ours_covered_pct` 99.69 vs 99.5 → **MEETS** |
| MLB | 287 | 157 | 65 | 65 | **PENDING-NO-GOVERNING-NUMBER** (deliberate) |
| NBA | 1206 | 41 | 1165 | 0 | `ours_covered_pct` 100.0 → **MEETS** |
| NHL | 1404 | 32 | 1372 | 0 | `ours_covered_pct` 100.0 → **MEETS** |

Every NFL field byte-identical to the banked day-1 row. `ours_only 1` is row B. NFL schedule side
(reported, gates nothing): `within 293 · off_by_hours 26 · wrong_day 2`. `read: READ-OK`,
`read_failures: []` on all four. **D63 not re-litigated.**

---

## The assigned §12 candidate — `/api/feed` checked, and #2866's blast-radius list closes

Posted to **`#2866#issuecomment-5550471729`**. Two independent methods, both clean.

**Structural.** The feed's event candidate window is **`now − 6d` → `now + 7d`**
(`routes/feed.py:5898`, and the `commence_time < now - timedelta(days=6)` drops at `:4331` / `:6799`).
The 47 twinned pairs are **mid-August preseason**, ~20 days old — outside by a factor of three.
Measured, not inferred: across 72 event cards, `OLDEST commence_time 2026-09-04T15:06Z`,
`NEWEST 2026-09-05T19:30Z`.

**Empirical.** 72 event cards over 8 sport-filtered feeds, fingerprinted on
`(commence_time, away_team, home_team)`: **56 distinct fingerprints, 0 carrying more than one
distinct `event_id`.** `?sport=nfl` → 59 items, 0 event cards; `?sport=americanfootball_nfl` → 1
item, 0 event cards.

**The caveat, stated on the issue:** the feed is clean because these duplicates **aged out**, not
because the feed path dedups. The 47 preseason pairs are permanently unreachable there — closed.
But a twin on a *future* game is feed-reachable inside `now+7d`; were `15304746` ever to twin, it
enters the feed window around **Nov 30**. A date, not a risk assessment.

---

## What the shop turned up on the way — and why it is NOT a new bug

Checking the feed for twins surfaced something bigger, which I chased to ground **before** writing a
word, because it would otherwise have been a false alarm.

**The default Discover feed serves ZERO game cards of 99.** The entire payload contains no
`"away_team"`, `"home_team"` or `"event_id"` at any depth, including inside the 11 bundles (whose 33
sub-items are all `futures`). Types: futures 70 · concept 14 · bundle 11 · tournament 4.
LOOK reproduced it at phone width: `artifacts/lane1-120-discover-zero-game-cards.png`.

Meanwhile the ±24h window holds `NCAAF scheduled 71` · `MLB scheduled 30` · `Tennis Atp scheduled
51` · `soccer_other live 16` · US Open ATP/WTA 8 scheduled + 8 completed each.

**But it is designed behaviour, not a defect** — verified from source, not guessed:

- `feed.py:1984-1993` — Discover mode is entered only when **`sport is None`** (plus `mode !=
  "sports"`, no tags, not my-teams, include_events, include_futures), setting `event_pct = 0.15`.
- `feed.py:1365` — `event_pct < 0.3` runs `_demote_non_exceptional_discover_events` (the cap at 35
  that #2957 already found).
- `feed.py:1373` — `event_pct < 0.2` takes the branch that **explicitly skips
  `_ensure_feed_diversity`**: `pass  # Discover mode: let scores decide, no artificial event
  promotion`.
- `feed.py:9100` — the skipped function is the one holding the floor:
  `min_event_slots = max(3, int(target_size * event_pct))` — **at least 3 game slots, 40%** — under
  the docstring *"The feed should lead with real games when available."*
- Both call sites gate it identically (`:1377` and `:4892` both need `>= 0.2`). At 0.15 **neither
  runs.**

So the score-35 cap is not a handicap games lose gracefully to; it is the whole ranking, and the
floor that would undo it is bypassed on the one surface that reaches it. **That is the intended
design as written.** I did not file it as a bug.

**Already filed as #2957** ("Discover serves 1 game card in 99 items during a Grand Slam", lane1/094,
9/4 04:49Z, zero comments). I added a comment — **`#2957#issuecomment-5550468724`** — carrying three
things it did not have:

1. **The count moved 1 → 0**, a second dated reading 27h later. One point is not a trend and I said so.
2. **A same-endpoint control**: `?sport=mlb` → **12** event cards, `?sport=baseball_mlb` → **16**,
   same minute. Stronger than #2957's `db-query`/`/sports` availability proof, because the only
   difference is one param — and that param is literally the switch at `:1987`.
3. **The mechanism above.** #2957 had the cap; it did not have the skipped floor.

I also sharpened #2957's own #1091 point: the comment at `feed.py:1978-1982` cites #1091 by name and
leaves content-scoped requests raw precisely so *"demoting/removing its events would empty the live
tab"*. The protection went to the scoped requests. **The main Discover feed is the one that emptied.**

Whether zero is intended at `event_pct=0.15` is a product call for the ranking owner, not mine — the
design says "only truly exceptional events keep their score", and today that set was empty on a
Saturday carrying Ohio State @ Texas (event `416569`, 19:30Z) and the US Open. Not lane1's to
answer; unclaimed, and left unclaimed.

## What was NOT done, deliberately

No §1 poll (not due). Nothing in §9's do-not-rebuild list touched. 115's rollback line **not run**.
The CREATE rail stays un-invoked. Row B not re-measured (118 characterised it fully). 118's
season-wide pair scan not re-run. 117's `1 of 322` not re-derived. D63 not re-litigated. `#3117`,
`#2896`, `#3070` not re-filed. No new issue opened — the finding had an owner already.

## New traps for 121

- **A duplicate check against the unfiltered `/api/feed` proves nothing right now**, because it
  serves zero game cards at all (#2957). Game cards are only reachable on that endpoint with a
  `sport=` param, since `sport is None` is one of the conditions that switches on Discover mode.
  The unfiltered feed returns a confident, meaningless "clean". Same shape as the 9/3 search miss:
  right endpoint, wrong query shape — **third time this class has bitten.**
- **Feed items nest their payload under `data`**, not at the item root. An item is
  `{type, headline, reason, score, data}`. A fingerprint keyed at the item root finds zero
  game-shaped items and reads like an answer. Read `data`, and unpack `type: "bundle"` items —
  their members are under `data.items`.
- **Sport filters are `ILIKE '%…%'` on `Sport.key`**, so `?sport=mlb` (67 items) and
  `?sport=baseball_mlb` (17) return **different pools**, and `?sport=football` sweeps NCAAF + CFL.
  `?sport=nfl` matched 59 items and 0 of them were games.
- **`?tab=games` and `?type=event` are silently ignored** — both returned the identical unfiltered
  99-item Discover payload. An unrecognised param does not error; it hands you the default and
  looks like a filtered answer.
- **A "bug" found while shopping may be a documented design decision.** Grep the source for the
  mechanism before writing it up: the zero-game feed had an explicit `pass  # …no artificial event
  promotion` behind it. Ten minutes of grep turned a false alarm into a real contribution to an
  existing issue.
