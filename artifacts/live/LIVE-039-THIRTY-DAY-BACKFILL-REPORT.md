# live/039 — the one-time 30-day chart backfill, and the US Open Polymarket census

**PILLAR: TRUTH** (with a MATCHING rider). **SHIP:** a US Open match page draws the
Polymarket curve it has never once been able to draw, and the last 30 days of
prediction-market-native events stop being a single dot.

Measured on production 2026-09-02. Every number below is measured, not estimated.

---

## TL;DR

1. **The 30-day population is 19,646 events; 18,460 of them are thin and 14,240 hold
   no prediction-market points at all.** The drain that fills them is built, guarded
   and gate-green — but it is **not yet run**, because the code is not deployed
   (see "Why nothing has been backfilled yet").

2. **Alex's addendum turned up a blocker that had to be fixed before a single US Open
   Polymarket curve could ever be drawn.** The Polymarket match-winner market is
   named `US Open ATP: Ben Shelton vs Hubert Hurkacz`. `_CATEGORY_PREFIX_RE` knows
   `US Open:` and `ATP US Open:` but not Polymarket's tournament-then-tour spelling,
   so the prefix never stripped, the matchup never parsed, and
   `resolve_orientation` returned `None` for the whole Polymarket group.
   **188 main-draw US Open match-winner markets, every one unparseable.**

3. **This is the same symptom CERT-730 blocked live/035 on — "the Polymarket curve
   remains blank" — with a second, independent root cause that the live/035 fix
   never reached.** Proven against the real Shelton v Hurkacz market group:

   ```
   WITHOUT parser fix (HEAD)    -> resolve_orientation = None   *** CURVE BLANK ***
   WITH parser fix (live/039)   -> market #9 'US Open ATP: Ben Shelton vs Hubert Hurkacz'
                                   outcome=Yes yes_is_home=True
   ```

   The CERT-730 fix (`f9e0122c`, "the empty Polymarket parent stops vetoing its
   child") made `resolve_orientation` try every market in the group instead of only
   the primary. That is necessary and it is not sufficient: iterating all nine
   markets does not help when none of the nine can be parsed.

---

## Alex's three questions — US Open, today (09-02) + yesterday (09-01)

Scope: 160 event rows on `tennis_atp`, `tennis_wta`, `tennis_atp_us_open`,
`tennis_wta_us_open` with `commence_time` in 2026-09-01..09-02. Of those, 12 are
US Open doubles rows, 26 are European Challenger singles (08:00–12:40 UTC, not the
US Open), and **122 are US Open singles rows — which collapse to 94 distinct
matches.**

| | matches |
|---|---|
| **Have a Polymarket match-winner market attached** | **16** |
| Have a Kalshi match market attached | 86 |
| **Have none on either venue** | **5** |
| Chart is thin (<20 points across every row) | 52 |

### Question 2 — on Polymarket but NOT attached (→ lane1)

Counting from the Polymarket side, main-draw singles with market `commence_time`
in 08-31..09-03: **60 distinct match-winner matches, 37 attached, 23 orphaned.**

**All 23 orphans already have an event row.** None is a "we never created the
event" gap; every one is a pure **link** gap. Full list in
`/tmp/lane1.json`, reproduced here:

```
Jaime Faria vs Carlos Alcaraz                 events=[15299547]
Kimberly Birrell vs Ekaterina Alexandrova     events=[15299432, 15299478]
Lilli Tagger vs Amanda Anisimova              events=[15299545]
Katie Boulter vs Karolina Muchova             events=[15299369, 15299378]
Harriet Dart vs Marie Bouzkova                events=[15299434]
Cristina Bucsa vs Himeno Sakatsume            events=[15299433]
Juan Manuel Cerundolo vs Arthur Gea           events=[15297974, 15297970]
Mananchaya Sawangkaew vs Leylah Fernandez     events=[15299421]
Aryna Sabalenka vs Polina Iatcenko            events=[15299435, 15299512]
Xinyu Wang vs Anna Kalinskaya                 events=[15299548, 15299609]
Jessica Pegula vs Sofia Kenin                 events=[15298812, 15298819]
Jiri Lehecka vs Toby Samuel                   events=[15298537, 15298557]
Valentin Vacherot vs Kamil Majchrzak          events=[15299439, 15299464]
Emma Navarro vs Caty McNally                  events=[15299597, 15299610]
Jaume Munar vs Arthur Rinderknech             events=[15298538, 15298555]
Lanlana Tararudee vs Linda Noskova            events=[15299591]
Naomi Osaka vs Katerina Siniakova             events=[15299767]
Jasmine Paolini vs Lucrezia Stefanini         events=[15298331, 15298728]
Dino Prizmic vs Tommy Paul                    events=[15298328]
Karolina Pliskova vs Diana Shnaider           events=[15299595, 15299611]
Taylor Townsend vs Taylah Preston             events=[15299546, 15299613]
Oksana Selekhmeteva vs Kamilla Rakhimova      events=[15299436, 15299480]
Denis Shapovalov vs Luca Van Assche           events=[15298539, 15298556]
```

Plus, entirely unlinked on the Polymarket side:

* **353 US Open Qualification match-winner markets** (`US Open, Qualification ATP:`
  / `... WTA:`) — **0 attached to any event.**
* **32 WTA doubles match-winner markets** — **0 attached**, against 12 doubles event
  rows we do hold.

**The parser fix in this queue is a prerequisite for lane1 fixing any of these.**
Those 445 market names could not be parsed into a matchup at all, so the matching
task had nothing to match on. With the fix they parse; whether they then *link* is
lane1's question, not this queue's.

### 🔴 The split-row finding — 28 US Open matches exist TWICE

13 of the 23 orphans above show two event ids, and the pattern generalises: **28 of
the 94 US Open singles matches on 09-01/09-02 are represented by two separate event
rows.**

```
bublik / mannarino    15299437[atp] K=1 P=0 pts=20    15299463[atp_us_open] K=0 P=12 pts=0
hurkacz / shelton     15299688[atp] K=1 P=1 pts=20    15299858[atp_us_open] K=0 P=14 pts=0
sakamoto / tiafoe     15299799[atp] K=1 P=1 pts=16    15299861[atp_us_open] K=0 P=16 pts=0
gorzny / medvedev     15299549[atp] K=1 P=0 pts=55    15299606[atp_us_open] K=0 P=5  pts=0
...                                                   (28 pairs total)
```

One row is Kalshi-native — plain `tennis_atp`/`tennis_wta`, a ticker-derived midnight
`commence_time` (gotcha #14) — and the other is Polymarket-native on the
tournament key with **zero** win-prob points. Each holds half the story, and the
reader lands on whichever one the slate links.

This is ruling 048's shape exactly: an id-less claim never absorbs, so the
Polymarket claim creates a second event instead of joining the Kalshi one. The
structural fix is the `event_provider_anchors` channel (#1946), and per the
2026-08-20 amendment these are `NO_ANCHOR_CHANNEL`, not `AWAITING_ANCHOR`. **This is
lane1's, and it is the single biggest thing standing between the US Open and a
complete chart** — even a perfect backfill fills two half-events rather than one
whole one.

---

## The 30-day population

| | events |
|---|---|
| `commence_time` in the last 30d with ≥1 attached Kalshi/Polymarket market | **19,646** |
| … holding fewer than 20 Kalshi/Polymarket points | **18,460** |
| … holding **none** | **14,240** |
| … thin across *all* sources | 18,186 |

13,591 of the 19,646 are `soccer_other` (7,488), `esports` (3,879) and
`americanfootball_other` (2,224) — the half live/036 called "February soccer".
That is why the drain is **tiered** rather than chronological: a drain that
delivers the US Open in its first hour beats one that delivers everything in its
eighth.

| tier | population | why |
|---|---|---|
| `us_open` | 2,612 attached / **2,571 fillable** (measured, 0.47s) | Alex's addendum |
| `reachable` | live/036's reader-reachable sports | the rest of what a reader reaches |
| `remainder` | the bulk | nobody is waiting on it |

---

## What was built

**`backend/app/utils/prediction_market_matching.py`** — `_CATEGORY_PREFIX_RE` gains a
closed-set draw qualifier so a tournament may be followed by `ATP`/`WTA`,
`, Qualification`, and a `(Doubles)`/`(Singles)` parenthetical. Deliberately anchored
to the existing tournament alternatives, and deliberately a closed set rather than
`[^:]*` — an open-ended qualifier would strip the first half of any
`<Tournament> <anything>:` name and take a team name with it.

**`backend/app/tasks/chart_backfill_thirty_day.py`** — the drain. Reuses live/035's
`backfill_event_chart` engine wholesale; what is new is selection, priority order and
the checkpoint. Per-tier keyset cursor on `(commence_time, event_id)` in Redis,
per-event commit, 0.25s inter-event politeness, abort after 25 consecutive failures,
and a verdict that says `drained` only when every tier in scope says so.

**`backend/app/tasks/__init__.py`** — `app.tasks.backfill_thirty_day_charts`.
Deliberately **not** on the beat schedule: it is a one-off bite, re-triggered until
`drained`.

**`backend/app/routes/admin_data_quality.py`** — `POST /api/admin/backfill-30d-charts`,
queued by default, with `only_tier`, `dry_run`, `min_period_minutes` and `reset`.

### Granularity — a deliberate deviation from the queue

The queue asked for a flat hourly fill ("12h if the venue coarsens"). The drain uses
live/035's existing age-derived `granularity_floor_minutes` instead: hourly past 7
days, 1-minute inside it. Same cost bound where it matters, finer where a reader
benefits — a two-day-old US Open match drawn as 48 hourly dots loses exactly the
in-match swing the chart is opened for. `min_period_minutes` forces the cheap pass.

Also worth recording: **12h is not available at Kalshi.** `period_interval` accepts
only `(1, 60, 1440)`; 5 and 15 return nonsense rather than an error (live/035
measured 4 candles for a window that yields 1,134 at 1-minute). The coarse step
above hourly is daily, not 12-hourly.

---

## Evidence

**Replay, parse-before vs parse-after, over 14,769 real production market names**
(two arms, two *processes* — one interpreter would share
`sys.modules['app.utils.prediction_market_matching']` and silently grade the same
code twice):

```
ADDED 445   LOST 0   CHANGED 0

ADDED by prefix:
   113  'US Open, Qualification WTA'
   112  'US Open, Qualification ATP'
    94  'US Open ATP'
    94  'US Open WTA'
    32  'US Open WTA (Doubles)'

CONTROL — AFC Wimbledon (the football club): 40 names, 0 changed
```

The control matters: `Wimbledon` is both a prefix literal and a London football
club, and `Wimbledon vs Newport` must keep parsing to `('Wimbledon', 'Newport')`.

**Red-first**, the same three names against HEAD and the branch:

```
HEAD (before)    parses=[False, False, False]  -> guard would be RED
branch (after)   parses=[True, True, True]     -> guard would be GREEN
```

**The safety property.** A Polymarket prop has the *same* two-outcome Yes/No shape as
the match winner, and `is_game_winner_market` gates Kalshi only — it returns `False`
for every Polymarket row, so `select_primary_market` falls through to "lowest market
id", which is "oldest row". Nothing downstream would catch a Set Handicap curve:
on the favourite it ends on the correct side, so even `contradicts_known_winner`
passes it. The only thing standing between a reader and a confidently-wrong chart is
that prop names do not parse into a matchup — so that is asserted explicitly, for
all seven real prop shapes, and it is the test to watch:

```
[OK] refuse  Set Handicap: Shelton (-1.5) vs Hurkacz (+1.5)
[OK] refuse  Set Handicap: Shelton (-2.5) vs Hurkacz (+2.5)
[OK] refuse  Set 1 Winner: Shelton vs Hurkacz
[OK] refuse  Set 2 Winner: Shelton vs Hurkacz
[OK] refuse  Game Spread: Shelton (-3.5) vs Hurkacz (+3.5)
[OK] refuse  Shelton vs. Hurkacz: Match O/U 36.5
[OK] refuse  Ben Shelton vs. Hubert Hurkacz: Total Sets O/U 3.5
[OK] orient  US Open ATP: Ben Shelton vs Hubert Hurkacz -> Yes, yes_is_home=True
```

**Gates.** **Full backend suite: 26,134 passed, 158 skipped, 61 xfailed, 0 failed
(20:46).** SQL binds compile clean against the postgresql dialect with zero phantom
binds. Selection query measured 0.47s over the US Open tier on production. No
frontend change, so no build/typecheck delta.

The first full run ended **1 failed / 26,133 passed**, and the failure was a guard
doing its job:

```
these tasks are dispatched from an HTTP route but are not declared as result
consumers — their status polls would hang: ['app.tasks.backfill_thirty_day_charts']
```

`POST /admin/backfill-30d-charts` queues by *default* — the drain cannot fit inside
a request — so the caller always holds a task id to poll, and without the
`RESULT_CONSUMER_TASKS` entry the result is reaped and the poll never resolves.
Fixed in `797a0ab2`; the 26,134-pass run above is the re-run after that fix.

**A tier-predicate bug caught and fixed in flight.** `"us_open" in key` matches
`tennis_atp_aus_open_singles` — `us_open` is a substring of `aus_open` — and
`golf_us_open_winner`. Both are real rows in the sports table and neither is Alex's
cohort. The predicate is now segment-aware and both are regression-tested.

---

## Why nothing has been backfilled yet

**The code is not deployed.** `POST /api/admin/backfill-event-chart` (live/035) and
`POST /api/admin/backfill-30d-charts` (live/039) both return **404** on production —
live/035, live/036 and live/039 are all still on this branch, 7 commits ahead of
`origin/master` and 56 behind.

**I did not push, and should not.** Two independent reasons:

1. `.claude/handoff/LANE-integrator.lock` is **HELD** — integrator/072, merge-on-green
   for CERT-743/744/747/750, since 07:30 PDT. Ruling 017 reserves the master push to
   the Integrator.
2. The queue's premise — *"after CERT-748 merges"* — has not happened, and cannot as
   written. **CERT-730 BLOCKED the chain at strike three and CERT-745 refused to
   grade a fourth presentation, escalating to Fable.** The cert bus recorded the
   later CERT-748 block as a duplicate of subject `df3c5d4a`, already banked as
   CERT-745. So live/039 is stacked on a chain that is stopped pending a Fable/Alex
   decision, not on one that merged.

That decision is Alex's, not mine, so it is in the inbox rather than acted on. The
one thing I can say that is new: **CERT-730's first named defect — "the Polymarket
curve remains blank" — is still true on the current branch head**, for a reason
CERT-730 did not identify and `f9e0122c` did not fix. That fix is in this queue, with
the reproduction above. Whatever is decided about the three-strike stop, the chain
should not be re-presented without it.

---

## Handoffs

**lane1 (resolver gaps, all US Open, all measured today):**
* 23 Polymarket main-draw singles match-winners unattached to an event that exists.
* 353 Qualification match-winners, 0 attached.
* 32 WTA doubles match-winners, 0 attached, against 12 doubles event rows.
* 28 split event-row pairs — ruling 048 / `event_provider_anchors` (#1946).
* Separately, outside the US Open: `tennis_other` on 09-01 holds ITF/Challenger
  Polymarket events duplicated **3–5×** per matchup (e.g. "Shu Muto v Hugo
  Hashimoto" = 5 event rows). Different bug, same family.

**Parked measurement:** none. Every measurement here served the named ship.
