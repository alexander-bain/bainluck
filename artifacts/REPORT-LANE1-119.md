# lane1/119 — night three was 23h out AGAIN; the twin held; search is a second blast-radius surface

Session ran **Sat 2026-09-05 07:43Z / 00:43am PT**. Queue 119 was written at 00:42am PT — **one
minute before this session started** — and its §1 was scheduled for **Sun 2026-09-06 06:40Z, ~23
hours in the future.** This is the second consecutive queue to hand its successor a §1 that cannot
be due (118 was handed the same thing). §0 anticipated it, the clock was read first, and no poll
was made and no absence reported.

**PILLAR: MATCHING. SHIP: the Monday Night Football game stays ONE game** — Dallas Cowboys @
Seattle Seahawks, Dec 7, event `15304746`. **Still one row.**

---

## §1 — NOT DUE, not polled

Night three's window opens **2026-09-06 06:40Z**. This session ran at **07:43Z on 9/5**, ~23h
early. No poll of `anchor_schedule_sentinel` was made. **Night three is still the third data
point**, and it is still unread — 118 did not add one either, for the same reason.

Everything in queue 119 §1 carries forward to 120 unchanged, including the two-poll rule
(~06:47Z **and** ~06:57Z; night two started 8m05s after its crontab minute and a single early poll
made 116 briefly conclude it had not run).

## §2 — the twin test: **13 rows**, unchanged

Read 07:43Z. Baseline held for the **fourth** consecutive reading (117 ×2, 118, 119).

```
13 rows, sport_id=1, commence_time [2026-12-06, 2026-12-10)
15304746  Dallas Cowboys @ Seattle Seahawks  2026-12-08 01:15Z
          espn_id 401873108 · external_id NULL · snaps 0
```

The other 12 all carry both ids and 798–826 snapshots. `15304746` is **still `external_id NULL` /
0 snaps** — the odds feed has not yet joined it. Per the queue's own table that is **"not yet
exercised. Not a finding."** Recorded and moved past. **No 14th row. No twin.**

## §3 — the gate: day 1 of 7, read a FOURTH time on the same calendar day

`generated_at 2026-09-05T07:43:49Z · last_pass_at 2026-09-05T07:23:00Z (age 1248s)`

```
NFL: both 321 · statpal_only 0 · ours_only 1 · denominator 322
     pct 99.69 · ours_covered_pct 99.69 · bar 99.5 · gate MEETS · read READ-OK
     schedule: within 293 · off_by_hours 26 · wrong_day 2 · time_missing 0
     excluded: statpal_placeholders 7 · unusable 0/0
     anchors: anchored 247 · unanchored 26 · mismatch 0 · polluted_column 48
```

**Byte-identical to 116's, 117's and 118's reads.** Today is still 9/5, so this is a *fourth
same-day re-read, not day 2*. The count stands at **day 1 of 7; earliest flip Fri 2026-09-11.**
`ours_only 1` is row B, as expected.

### Checked and cleared: the other three sports (no finding — banked so nobody re-derives it)

Three sessions have read this payload and **all three read only the NFL row. It serves four
sports.** Reading the rest turned up an apparent problem worth the paragraph it takes to close:

| sport | both | statpal_only | ours_only | pct | ours_covered_pct | gate |
|---|---|---|---|---|---|---|
| `americanfootball_nfl` | 321 | 0 | 1 | 99.69 | 99.69 | **MEETS** |
| `baseball_mlb` | 157 | 65 | 65 | 54.70 | 70.72 | PENDING-NO-GOVERNING-NUMBER |
| `basketball_nba` | 41 | 1165 | 0 | **3.40** | **100.00** | **MEETS** |
| `icehockey_nhl` | 32 | 1372 | 0 | **2.28** | **100.00** | **MEETS** |

NBA and NHL are accruing streak rows toward a canonical flip while holding 41 of 1,206 and 32 of
1,404 fixtures. That reads alarming, and **it is explicitly ruled, not an oversight.** D63 = A
(Alex, 2026-09-04) scores those two on `ours_covered_pct` alone; `GOVERNING_IDENTITY_NUMBERS` in
`backend/app/utils/authority_agreement.py:152` names the exact 100.00-vs-3.40 asymmetry in its own
comment and states the reason — scoring them on `pct` would hold a flip *unreachable by design*,
which spec rule 5 exists to prevent. MLB's absence from the map is deliberate and reasoned there
too.

My objection was also wrong on its own terms: `ours_covered_pct = both/(both+ours_only)` is *more*
sensitive at a small denominator, not less — a single `ours_only` row would put NBA at 41/42 =
97.6 → **BELOW**. Verified arithmetic against all four served rows.

**Do not re-derive this.** It cost one payload read and one file read; it should cost 120 nothing.

## §9 — the pre-check: **0 contested ids**

`SELECT count(*) … GROUP BY espn_id HAVING count(*) > 1` → **0** at 07:43Z. Unchanged, and the
unique index keeps it there.

---

## THE FINDING — search unions the two namespaces, and #2866 said it didn't

Filed at **`#2866#issuecomment-5550398434`**. #2866 is OPEN, p1, `matching-symptom`.

### How it was found

Queue §11 says: aim this queue's own instrument at the surface Alex is about to use, then widen it
one notch. 118 searched `Broncos Cardinals` and found row B twinned in front of users. **The notch:
ask the same question about the ship's own matchup.**

`/api/events/search?q=Cowboys%20Seahawks` returns **3 results** with facets `NFL (2) ·
NFL Preseason (1)`.

### What a fan sees — production, phone width 390×844

```
Results for "Cowboys Seahawks"
13 results · 3 games · 10 markets
[ All ]  [ NFL (2) ]  [ NFL Preseason (1) ]

GAMES (3)
  NFL             Dec 7 8:15 PM      Seattle Seahawks  -   / Dallas Cowboys  -
  NFL             Aug 15  FINAL      7 SEAHAWKS  –  17 COWBOYS
  NFL PRESEASON   Aug 15  FINAL      7 SEAHAWKS  –  17 COWBOYS
```

**Three cards, two real games**, and the header itself miscounts (`3 games`). Shot:
`artifacts/lane1-119-search-three-games-two-real.png`.

### Why it is provably one game

| id | sport_id | espn_id | external_id | score | completed_at | created_at | snaps |
|---|---|---|---|---|---|---|---|
| 14780590 | 1 | `401873279` | `0db4646c…` | 17–7 | 08-16 03:01:06Z | 05-15 | 809 |
| 15191808 | 190411 | **NULL** | `a82bf41c…` | 17–7 | 08-16 03:06:58Z | 08-08 | 628 |

Same `commence_time` 2026-08-16T00:00:00Z (renders `Aug 15` local). **Same final score 17–7** —
new to the issue, which had recorded these pairs only as same-teams-same-kickoff. An identical
settled score removes the last reading under which a pair could be two events. Both sides carry
odds snapshots, so it was *tracked* twice, not merely listed twice.

### Why the 9/3 measurement missed it

The blast-radius section concluded **"the team page … is the only surface found that unions the two
namespaces"**, and it *did* check search — but it read the **`teams` block** with a **team-name**
query (`q=Chicago Bears`) and found one clean entity. A matchup query lands in the **`results`**
block instead. Right endpoint, wrong block, wrong query shape.

This is 118's lesson one turn further on. 118: *the gate half and the user half are different
questions.* 119: **the `teams` block and the `results` block are different questions, and a scope
claim inherits the shape of the query that tested it.**

### It is the class, not one pair

Every pair already documented in #2866 returns both rows to a matchup query — `Bears Titans` (2
results), `Rams Chargers` (3), `49ers Raiders` (3), each pair sharing `commence_time` to the
second. With **47 of 50** preseason rows twinned, all 47 are reachable this way.

Surfaces that union the namespaces are now **two**: `/api/teams/{slug}` → `recent_events` (known)
and `/api/events/search?q=<matchup>` → `results` (**new**).

### Not fixed, and one note for the drain

D35 — filed, the data half stays with #2693, not claimed. Noted on the issue: unlike the team page,
**search has no league context to gate on** — the user is explicitly shown both leagues as facets —
so the render-side mitigation that worked for the G1/G2 chips (`ccfdc461`) has no analogue here.
This surface needs the data half.

**The ship is NOT compromised.** `15304746` is one row. The duplicate is a *different* game (Aug 15
preseason) between the same two teams, sharing the ship's search page.

## §5 exposure re-check — Dec 27 has NOT entered the league page

`/api/leagues/americanfootball_nfl`: `upcoming_games` n=8, `upcoming_games_has_more: true`, window
runs **Sep 10 → Sep 13 only**. Row B (`14751059`, Dec 27) absent; the ship (`15304746`, Dec 7)
absent. No escalation. Re-check in December-adjacent sessions, per 118.

## What was NOT done, deliberately

No cert staged, no merge, no push, no data write — this session made **production reads only**.
Nothing in §8's do-not-rebuild list was touched. 115's rollback line was not run. The CREATE rail
stays un-invoked. Row B was not re-measured (118 characterised it completely) and 118's season-wide
pair scan was not re-run.

## New traps for 120

- **`/api/events/search` results live under `results`, not `events`**, and the row dicts return
  `away_team_name: None` / `home_team_name: None` — the names render from elsewhere. A reader
  checking for duplicates on team-name fields sees `None @ None` and concludes nothing. Match on
  `id` + `commence_time`, and read `pagination.total_results` and the `sports` facet counts.
- **A team-name query and a matchup query hit different blocks of the same search endpoint.** A
  scope claim is only as wide as the query shape that tested it. Ask both.
- **`grep -rn … --include=*.py` unquoted fails in zsh** (`no matches found`) — quote it as
  `--include="*.py"`. The failure looks like "no results", not like a shell error.
- **This worktree's `backend/` is behind master.** `ours_covered_pct` greps to zero files locally
  and exists on master; use `git grep <pat> origin/master -- backend/` after a `git fetch`.
- The gate payload serves **four** sports. Read all four or say you read one.
