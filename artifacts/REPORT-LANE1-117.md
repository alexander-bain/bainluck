# REPORT — lane1/117: the twin did not appear, and the page it would have duplicated has a different bug

**PILLAR: MATCHING. SHIP: the Monday Night Football game stays ONE game** — Dallas Cowboys @
Seattle Seahawks, Dec 7, event `15304746`.

Ran Sat 2026-09-05, 00:10–00:40 PT (07:10–07:40Z). Stamped from `TZ=America/Los_Angeles date`.

---

## Verdict

**The twin has not reproduced.** The queue's §1 reading table returns the middle row: 13 rows,
`external_id` still NULL, 0 snapshots — *not yet exercised, not a finding*. Everything else the
queue asked for is unchanged and green. The window's real yield came from the D48 LOOK, which
found a user-visible probability bug on the ship's own page: **#3117**.

Nothing was merged, nothing was pushed, no cert was staged. No code changed.

---

## 1. The twin test — 13 rows, no twin

```sql
SELECT e.id, e.away_team_name, e.home_team_name, e.commence_time, e.espn_id, e.external_id,
       (SELECT count(*) FROM odds_snapshots o WHERE o.event_id = e.id) AS snaps
FROM events e WHERE e.sport_id = 1
  AND e.commence_time >= '2026-12-06' AND e.commence_time < '2026-12-10'
ORDER BY e.commence_time
```

**13 rows at 2026-09-05 07:10Z** — identical to the 07:00Z baseline. Twelve carry an odds-API
`external_id` with 798–826 snapshots. The thirteenth:

| id | game | espn_id | external_id | snaps |
|---|---|---|---|---|
| 15304746 | Dallas Cowboys @ Seattle Seahawks | 401873108 | **None** | **0** |

### The one number that sharpens it

I widened the same query to the whole season rather than stopping at the queue's three-way table:

```sql
SELECT ... FROM events WHERE sport_id = 1 AND external_id IS NULL
  AND commence_time >= '2026-09-01' AND commence_time < '2027-03-01'
```

→ **1 row.** `15304746` is the only one of **322** NFL events this season without an odds-API
join. The feed has already covered every other December game, so this is *not* a coverage horizon
— which is what I would have assumed without asking.

### What that proves, and what it does not

ESPN created the row at 2026-09-04 18:43:33Z. In the **12.5 h** since, the odds pipeline has
neither joined it nor minted a row beside it — and that pipeline mints on no-match. That leans
toward *the venue does not list the game yet*, so matching has not actually been put to the test.

**That is an inference from silence, and I did not promote it to a finding.** Our tables cannot
separate "the venue doesn't list it" from "the venue lists it and we fail to match" — and notice
26 says that question is answered against the venue's own API. The Odds API `/v4/sports/.../events`
endpoint is unbilled and would settle it in one call, but the key is in Heroku config, there is no
admin route that lists Odds-API events, and building one is unqueued architecture (rider rule).
It is a venue probe, which is measurement-lane work under LANE ROLES.

**Parked**, with the ship named, the method written out, and a spend-by date (before anyone writes
a green receipt on #2693's odds-join path; no later than the week of Dec 1):
`~/bainluck/.claude/handoff/PARKED-MEASUREMENTS.md`.

Receipt: `#2693#issuecomment-5550256314`.

---

## 2. Night three — not due, and night two is byte-identical to its baseline

Night three's window opens **Sun 2026-09-06 06:40Z**, ~23.5 h after this session. It could not be
polled here. The two-poll discipline in queue §2 carries forward to lane1/118 unspent.

`GET /api/admin/celery/task-metrics/anchor_schedule_sentinel` still serves night two, and every
field matches the recorded baseline exactly:

| field | value | vs baseline |
|---|---|---|
| `last_started_at` | 2026-09-05T06:48:45.289031+00:00 | = |
| `terminal` | `partial` | = |
| `complete` | `false` | = |
| `resumed_from` | `2026-11-28T00:00:00+00:00\|15197566` | = |
| `restarted_from_exhausted_cursor` | `false` | = |
| `continuation` | `null` | = |
| `reached_window_end` | `true` | = |
| `pass_open` / `pass_expired` | `false` / `false` | = |
| `pass_drift_seen` | `true` | = |
| `pass_started_at` | `null` | = |
| `pages` / `examined` | 1 / 91 | = |

`successes_24h 1`, `failures_24h 0`, `starts_24h 1`, `consecutive_failures 0`, `health healthy`.
One move filed to #2978 (`14792841`, Ohio State v Michigan, 0.5 d) — the drift-seen path working.

**`hard_kills_24h` now reads 0.** 116 saw it flip 1 → 0 mid-diagnosis and correctly called it a
~24 h-old event aging out of the window rather than a live kill. This reading confirms that: it
stayed at 0.

---

## 3. The authority gate — still MEETS, and this is a re-read of day 1, not day 2

`GET /api/admin/statpal/authority-agreement`, 07:10:47Z:

```
both 321 · statpal_only 0 · ours_only 1 · denominator 322
pct 99.69 · ours_covered_pct 99.69 · bar 99.5 · gate "MEETS"
governing.why: "all governing numbers at or above 99.5%"
read READ-OK · read_failures [] · last_pass_at 06:23:25Z
```

**This is the same calendar day as the queue's day 1 (2026-09-05), so it is a re-read, not a
second row.** The seven-day count is still at day 1; earliest flip remains **Fri 2026-09-11**. The
daily rows are the measurement bus's to bank, not mine.

`ours_only: 1` is row B (`14751059`), unchanged, and §4's point stands: the bar is met *with* row
B counted, so no delete rail is owed. Still filed on #3070.

---

## 4. The re-growth half is holding, and now it is silent as well as zero

`contested_ids = 0` at 07:10Z.

§8 said the signal has moved to Sentry. I checked it — the project slug is `bainluck` under org
`alexander-bain`:

- **Zero** issues matching `uq_events_espn_id`.
- The only open `IntegrityError` is **BAINLUCK-13D**, `win_prob_snapshots_event_id_fkey` from
  `app.tasks.backfill_espn_win_prob` — 3 events lifetime, **last seen 2026-09-01**, which predates
  the index. Different constraint, different table, unrelated.

So the index is not merely un-violated, it is un-*tripped*: no writer has collided with it since
it shipped. That is consistent with, but does not prove, the duplicate writer being dormant.

---

## 5. The LOOK — the ship is healthy, and it is carrying someone else's bug

`tools/look.sh https://www.bainluck.com/events/15304746`, read at 390 px.

**Correct:** Seahawks and Cowboys with the right crests, "Dec 7, 2026 · 8:15 PM EST",
"Starts in 93d 18h". The Win Probability panel degrades gracefully — *"Tracking will begin when
odds are available"* — which is exactly right for a row with zero snapshots. The odds-less state
is not a broken page.

**#2896 (already open, not re-filed):** the hero prints two bare `%` signs with no digits. 116
already dated a specimen, so I added only the **precondition**, which is new: this is the
no-source-*at-all* case, and the hero fails where the chart directly below it succeeds — the same
guard, one component up. `#2896#issuecomment-5550256645`.

### New: #3117 — the PLAYER AWARDS block

Mystery-shopping under D48 turned up a bug the queue did not anticipate, on the ship's own page.
Both team cards print the *identical* award list, and Sam Darnold appears twice — once as
`Will Sam Darn… 45%`, once as `Sam Darnold 3%`.

I did not file from the pixels. Market **479** (`KXNFLSBMVP-26`, `market_type: field`,
`mutually_exclusive: TRUE`, tier 3):

| n | prob_sum | at exactly 0.500 | team_id NULL |
|---|---|---|---|
| 79 | **19.67** | **37** | 4 |

1. **Every outcome name is the whole Kalshi question sentence** —
   `'Will Sam Darnold win the Pro Football Championship Game MVP?'` — so the card truncates to
   `Will Sam Darn…`. The nominee is never extracted.
2. **A mutually-exclusive field sums to 1,967%.** 37 nominees sit at the untraded binary midpoint
   of exactly 0.500 and nothing normalizes them, so the printed numbers are raw Yes-prices, not
   shares of one question. Gotcha #23, on a market that renders on event pages. *The blend is the
   product.*
3. **`team_id` is wrong on untruncated names** — Kenneth Walker III → Kansas City, Coby Bryant →
   Chicago; both are Seattle. #2010's repair is scoped to *truncated* Kalshi names and would miss
   these.

I checked the blast radius before writing the scope: 286 outcomes across 38 open markets match the
question-shaped-name pattern, but **37 of those 38 are legitimate `How many …?` threshold ladders**
whose rungs really are sentences. Market 479 is the only `field` market in the set, so the repair
must be scoped to `market_type: field` — a global pattern fix would corrupt 37 working markets.

Checked against #1012 (calibration-side, not display), #1627 (Additional Markets, different
block), #2165 (Polymarket placeholders), #3061 (My Stuff, different surface) — none cover it.
**Filed, not fixed:** this is futures/formatting, not lane1's matching domain.

---

## 6. What lane1/118 inherits

- **Night three, Sun 2026-09-06 06:40Z — poll at ~06:47Z AND ~06:57Z.** Unspent. Night four
  (Mon 9/7) is still the first night that can close #2978.
- **The twin watch** — one query, same baseline: 13 rows is the number.
- **Day 2 of the authority gate** — 2026-09-06 is the first genuinely new row.
- The parked venue probe, if #2693 ever needs a green receipt on the odds-join path.

## 7. Housekeeping

- Branch `lane1/099-artifacts`, clean, nothing unpushed at session start.
- No merges, no pushes, no cert staged, no code touched. Merge gates 13/18 not reached.
- **115's rollback line stayed unrun**, as 116 instructed — it would now delete the ship.
- The CREATE rail was not invoked. Population 4 remains gate-refused at plan time.
