# REPORT — lane1/116

**Ran:** Sat 2026-09-05, 06:39Z → 07:05Z (11:39pm–12:05am PT, Fri 9/4 → Sat 9/5). Stamped from
`date -u`, not inherited from another lane.

**PILLAR: MATCHING. SHIP: the Monday Night Football game — Dallas Cowboys @ Seattle Seahawks,
Week 13, Dec 8 — is on the site and renders.** Delivered. Not by this lane's rail.

---

## Headline

Three things, in order of how much they matter.

1. **The ship is live.** Event **15304746** exists on production with `sport_id = 1`, and
   `https://www.bainluck.com/events/15304746` renders "Seahawks vs Cowboys, Dec 7, 2026 ·
   8:15 PM EST, Starts in 93d 18h" with both logos. **The CREATE rail did not do it** — the
   ordinary ESPN/StatPal pipeline created the row at 2026-09-04 18:43:33Z, and the rail's gate
   correctly refused at plan time with `TRUTH_ID_SET_DRIFT`. The apply was never called.
2. **NFL authority agreement crossed the bar for the first time: 99.38% → 99.69%, `gate: MEETS`.**
   That was lane1/115's pre-registered prediction and it landed to the decimal. Day 1 of 7.
3. **Night two of the anchor sentinel graded CHAIN-BROKEN — every predicted field matched.** But
   it started **8m05s late** and is **not readable at 06:47Z**, which nearly produced a false
   "it did not run" from me. That poll guidance is the most operationally useful thing in this
   report.

Nothing was applied, nothing was merged, and no production write was made by this lane.

---

## §1 — Night two of `anchor_schedule_sentinel`

`last_started_at: 2026-09-05T06:48:45.289031+00:00` (a new row; night-one baseline was
`2026-09-04T06:40:40.341420Z`). `last_success_at 06:49:38.697Z`, `last_duration_ms 53378`.

| field | predicted (§1.1) | measured | |
|---|---|---|---|
| `resumed_from` | non-null | `'2026-11-28T00:00:00+00:00\|15197566'` | ✅ |
| `restarted_from_exhausted_cursor` | `false` | `False` | ✅ |
| `complete` | `false` | `False` | ✅ |
| `terminal` | `"partial"` | `'partial'` | ✅ |
| `pass_open` | `false` | `False` | ✅ |
| `pass_started_at` | `null` | `None` | ✅ |
| `pass_expired` | `false` | `False` | ✅ |

**Verdict: CHAIN-BROKEN. The repair is working.** `resumed_from` is byte-identical to night one's
banked continuation, so the migration path carried the cursor correctly; the pass then reached
`reached_window_end: True` in one page (`pages 1`, `examined 91`, 53s) and set
`continuation: None`.

**Conjunct named, never read alone** (`complete = reached_window_end and pass_open and not
pass_expired`): `reached_window_end` **True**, `pass_expired` **False** → the conjunct that fired
is **`pass_open: False`**.

None of the three §1.1 finding conditions fired. `pass_drift_seen: True` (with
`by_verdict.authority_moves_us: 1`) does not change the verdict — `green = complete and not
pass_drift_seen` is already false on its first conjunct.

**The five window-pass fields are PRESENT**, so the "did not deploy" escape hatch was neither
needed nor available. Production is `2a1b1d45`, confirmed a **descendant** of `3a1e6c9f` and
`75dabbc2` — never compared against a literal sha.

### The 8-minute late start — flagged, not concluded

At 06:47:56Z `last_started_at` still read the night-one row and `successes_24h` had rolled to 0.
**I read that as "night two did not run" and was wrong.** It had not started yet. Recorded here
because the next two sessions will hit the same trap.

Checked, in the §1 hazard order, before blaming anything:

- **No merge in the window.** Master's newest commit `2a1b1d45` is 18:42Z 9/4 — twelve hours out.
  D45's merge-cycles-`worker-heavy` hazard is **cleared by measurement**, not assumed.
- **No release.** Heroku current v4085, cut 18:51Z 9/4.
- **No dyno restart.** `scheduler.1` up 11.8h (since 18:52:01Z 9/4); `worker-heavy.1` since
  18:51:56Z 9/4. Beat was up across the entire window.
- **One delivery, one start** (`starts_24h 1`, `deliveries 1`, 0 failures, 0 incompletes).
- `/api/admin/celery/schedule-adherence` grades it `on_schedule` (`rate_arm_blind: true`,
  86400s interval over the 43200s counter-TTL ceiling; graded on stamps).

**Correction on the record:** `hard_kills_24h` read `1` at 06:49Z and `0` at 06:55Z. That was a
~24-hour-old artifact of night one rolling off the window, **not** tonight's run. I briefly
inferred tonight's dispatch had been hard-killed; it had not.

I could not separate "beat dispatched late" from "the heavy queue held it 8 minutes" —
`last_started_at` is written at execution, not dispatch. Worth noting the beat comment at
`backend/app/tasks/__init__.py:4790` chose 06:40 *specifically* to dodge heavy-slot contention, so
an 8-minute hold in that slot is the exact risk that comment reasons about.

Filed to `#2983#issuecomment-5550146235`.

**Night four (Mon 9/7) remains the first night that can close #2978.**

---

## §2 — PR #3090 / CERT-947: merged and deployed before this session began

- CERT-947 banked **GREEN — TOKEN GRANTED** at 2026-09-04 18:27Z (ledger line 777).
- **Merge gate 13:** `89eb6642` greps to a `TOKEN GRANTED` row. ✅
- **Merge gate 18:** no later ledger row names CERT-947 after the word `supersedes`. ✅
- Merged to master as **`8e167fb9`** (18:33Z 9/4); `89eb6642` confirmed an ancestor of
  `origin/master`. Deployed Heroku v4084, and production now runs `2a1b1d45` (v4085), a
  descendant. `/api/health` → `commit: 2a1b1d45, db: true, redis: true`.
- CI at `89eb6642` was fully green (4/4 backend shards, frontend-build, search-recall,
  shard-completeness, browser-audit fixtures, CodeQL ×2, gitleaks ×2, Vercel; `deploy` SKIPPED,
  correct on a PR).

Nothing for this lane to do. The NamedTuple sweep concern did not materialise — CI was green.

---

## §3 — The apply: correctly refused, ship delivered anyway

Dry run (call 1) against production, `population=4`:

```
plan_hash    ff6b0e518447e3f3a4e383383184b0ff   (matches 115's locally-derived hash)
plan_rows    1        schema  event-create-from-truth-plan/v3
census       reviewed 1 | still_missing 0 | already_present 1 | clubs_anchored 2
gate.passes  false
reason_code  TRUTH_ID_SET_DRIFT
no_longer_missing  ["401873108"]
```

**The apply (call 2) was never issued.** The gate's own rule — "apply may proceed only when a
re-derivation at apply time produces a MISSING id set whose intersection with THIS set is THIS
set" — is not satisfied, because the id is no longer missing.

This is the anticipated outcome class arriving one step earlier than the queue expected: not a
`rowcount 0` / `TRUTH_ID_PRESENT` at apply time, but a **named refusal at plan time**. Better
failure mode — it never got near a write.

### Verified from production, not from the response

```sql
SELECT id, away_team_name, home_team_name, commence_time, espn_id, sport_id, status,
       statpal_fixture_id, created_at FROM events WHERE espn_id = '401873108'
```

| id | away | home | commence_time | espn_id | sport_id | status | statpal_fixture_id | created_at |
|---|---|---|---|---|---|---|---|---|
| 15304746 | Dallas Cowboys | Seattle Seahawks | 2026-12-08 01:15:00+00 | 401873108 | **1** | scheduled | 280714 | 2026-09-04 18:43:33Z |

Exactly one row. **`sport_id = 1`, not 53232** — the defect #3090 existed to fix is absent from the
row that actually landed, though a different writer made it. Created 18:43:33Z, ~9 minutes
*before* the v4085 deploy, so under no reading is this row our code's doing.

**Rollback is not owed and must not be run.** `DELETE FROM events WHERE espn_id = '401873108'`
would now delete the ship. Population 4 stays committed and reviewed; its gate will refuse
permanently, which is the correct resting state for a reviewed set whose subject arrived by
another road.

---

## §4 — The gate: the prediction landed to the decimal

`GET /api/admin/statpal/authority-agreement`, `generated_at 2026-09-05T06:40:49Z`:

```
denominator 322 | read READ-OK | read_failures []
excluded    statpal_placeholders 7 | statpal_unusable_names 0 | our_unusable_names 0
identity    both 321 | statpal_only 0 | ours_only 1 | pct 99.69 | governs true
            ours_covered_pct 99.69
governing   bar_pct 99.5 | gate "MEETS" | why "all governing numbers at or above 99.5%"
```

Was `both 320, statpal_only 1, ours_only 1, pct 99.38` → **BELOW**. Predicted `99.69` / `99.69`
→ **MEETS**. Measured `99.69` / `99.69` → **MEETS**. `statpal_only` went **1 → 0** and the delta
is exactly event 15304746.

**`governing` is no longer null — `7f5b49a1` (D63) has deployed**, so the verdict is served rather
than hand-derived. The queue expected to have to derive it; it did not.

The surviving `ours_only: 1` is row B (event 14751059, Denver Broncos / Arizona Cardinals,
2026-12-27T18:00Z) — the already-filed stale `odds_api` listing. It does **not** hold the bar
down; 99.69 clears 99.5 with it counted.

**Day 1 of 7.** Under D50 a flip needs 7 consecutive daily rows plus a YOUR-TURN entry Alex has
seen. Banking those rows is the measurement bus's job, not a build lane's (CLAUDE.md LANE ROLES).
Earliest possible flip if every day also MEETS: **2026-09-11**. Nothing flipped; nothing
user-visible changed.

Reported-but-gating-nothing: `schedule within 293 / off_by_hours 26 / wrong_day 2`;
`anchors anchored 247 / unanchored 26 / mismatch 0 / polluted_column 48`.

Filed to `#2867#issuecomment-5550162096`.

---

## §5 — Row B: still filed, still not built

Unchanged. No DELETE rail exists (ruling 079), building one for a single stale listing remains
disproportionate, and §4 proves the point empirically: **the bar is met with row B still counted.**
The case for touching it is now weaker than when 115 filed it.

---

## §6 — LOOK (D48)

`https://www.bainluck.com/events/15304746`, 390px, photographed and read
(`/tmp/lane1-116-mnf-event.png`).

**Good:** Seahawks vs Cowboys hero with both team logos and 0-0 records; **"Dec 7, 2026 · 8:15 PM
EST"** and **"Starts in 93d 18h"** — the kickoff converts correctly from 2026-12-08 01:15Z;
"NFL Championship Grid" link; MORE FOOTBALL rail populated with real percentages; footer intact;
no layout break at phone width.

**Also reachable from search** — `/api/events/search?q=Cowboys Seahawks` returns 15304746 first.

**The league page does not show it, and that is the window, not the game.**
`/api/leagues/americanfootball_nfl` returns 8 upcoming games with
`upcoming_games_has_more: true`, spanning Sep 10-13. Week 13 is far outside it. Per §6's warning,
I found the surface that renders December before claiming anything about absence.

**Two honest gaps in the shot, neither caused by this ship** — both routed to existing issues
rather than re-filed (notice 6):

1. **The hero prints two bare `%` signs with no digits**, over a chart that honestly says
   "Tracking will begin when odds are available". Already open as **#2896**; I added a dated
   specimen plus the measurement of *why* (below) at `#2896#issuecomment-5550158812`.
2. **The game has no odds at all** — see §7.

---

## §7 — The thing worth handing forward: a live twin test

Week 13 has 13 rows. Twelve carry an odds-API `external_id` and 798-826 `odds_snapshots`.
The thirteenth — ours — has **`external_id: NULL` and 0 snapshots**.

| id | game | external_id | snaps |
|---|---|---|---|
| 15304746 | Dallas Cowboys @ Seattle Seahawks | **None** | **0** |

So the empty hero is not a far-horizon artifact: The Odds API is already pricing this entire week
(and every week out to Nov 29). This one row simply has no pricing linkage yet.

That sets up a **falsifiable test with a known clean starting state**, which #2693 has never had:

1. The odds-API pass structured-matches 15304746 and stamps `external_id` → durable matching
   works; or
2. it creates a **second** row → a twin, reproduced in the wild.

**`uq_events_espn_id` cannot catch outcome 2.** It is partial on non-null `espn_id`, and an
odds-API-created row carries a NULL `espn_id`. This is exactly the half of #2693 the index did not
close, now with a dated single-row specimen instead of an argument.

Filed to `#2693#issuecomment-5550158980` with the one query that settles it. **Filed, not fixed**
(D35).

---

## §9 — The pre-check

```
contested_ids = 0
```

Holding at 0, and the database now refuses to let it rise. Signal has moved to Sentry
`IntegrityError` naming `uq_events_espn_id`; none observed this session.

---

## Incidental, already-known, not re-filed

The two other Cowboys @ Seahawks rows that search surfaces (14780590 and 15191808, both
2026-08-16T00:00Z, both completed) are **not** a new twin: they split across `sport_id` 1 and
`sport_id` 190411 (preseason). That is the known #2866 shape — the same trap 115 recorded, and it
caught me too until I checked the anchor.

14780590 also carries `statpal_fixture_id = 'statpal_live_Seattle Seahawks_Dallas Cowboys'` — a
synthetic string in a numeric-id column. That is one of the 48 the agreement payload already
reports as `anchors.polluted_column`; counted, not re-filed.

---

## Traps this session (for §10 of the next queue)

- **A sentinel window has a start time, not a readable time.** The run began 8m05s after its
  crontab minute. Polling once at the documented `start + duration` produced a confident false
  negative that survived seven minutes. **Poll twice, ~9 minutes apart, before believing an
  absence.**
- **A rolling counter can roll off mid-diagnosis and invert your story.** `hard_kills_24h` went
  1 → 0 in six minutes because a ~24h-old event aged out. A counter read once during an incident
  is a snapshot of a *window*, not of an event; re-read it before building a cause on it.
- **The gate can refuse before the apply, and that is the good version.** A plan-time
  `TRUTH_ID_SET_DRIFT` beats an apply-time `rowcount 0` — the write is never attempted. When a
  queue names the expected failure code, also ask which *stage* it fires at.
- **A rollback line goes stale the moment someone else ships your row.** 115's
  `DELETE FROM events WHERE espn_id = '401873108'` was correct when written and would now delete
  the ship. Re-derive an undo against current state before running it, never copy it forward.
- **The absence of a game from a list page is usually the page's window.** Read
  `*_has_more` before reading absence as a finding.
- **`heroku -a bainluck-api` is not the app; it is `bainluck`.** `Couldn't find that app` is a
  name error, not an auth or egress failure.
- Carried and re-confirmed: the db-query payload goes through a python file, branching on
  `'rows' not in d` first; the league API's shape is `upcoming_games`/`sections`, not `events`.
