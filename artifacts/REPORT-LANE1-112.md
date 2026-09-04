# REPORT — lane1/112

**PILLAR: TRUTH.** **SHIP: a 49ers fan stops seeing their team play twice in Week 1.**
Kickoff Thu 9/10 — **six days.**

Session ran Fri 2026-09-04, **12:16Z → 12:40Z** (05:16–05:40 PT), stamped from `date -u`. Opened
roughly two minutes after 111 restocked, so most inherited state could not have moved — the report
says which things I re-measured anyway and which I did not.

Production moved during the session: `6c6a9277` → **`8e9d816c`** at 12:28Z.

---

## One line

Night two not due; Week 1 still 18 and the line held for the 22nd session; **CERT-911 merged and
deployed at 12:17:46Z and I ran the post-deploy check lane1 owed on it**; and the §3 triage found
that the sweep command itself has been reading page one of 78 open PRs, hiding 28 unmerged lane1
branches from every session since ~101.

---

## 1. Clock — night two NOT due

`date -u` = **2026-09-04T12:16:41Z**. Night two is not readable until Sat 9/5 after ~06:47Z.
Nothing filed.

Confirmed the baseline rather than assuming it —
`GET /api/admin/celery/task-metrics/anchor_schedule_sentinel`:

```
last_started_at = 2026-09-04T06:40:40.341420+00:00
last_result_summary = terminal: partial, complete: False, stopped_by: deadline,
                      resumed_from: None, restarted_from_exhausted_cursor: False,
                      continuation: '2026-11-28T00:00:00+00:00|15197566', applied: False
```

`last_started_at < 2026-09-05T06:40Z` ⇒ still night one. **Baseline, not a finding.** §1.1 of the
brief carries forward to 113 unused and untrimmed.

---

## 2. CERT-911 — MERGED and DEPLOYED, post-deploy check done

Both merge gates re-run at 12:17Z and both still passed (gate 13 `TOKEN GRANTED` present; gate 18
anchored `supersedes: CERT-911` grep empty).

**PR 2900 merged at 2026-09-04T12:17:46Z** — one minute into this session — as merge commit
`a698a539dc1c3ec985b9f82ba916214903ce6577`. Head sha unchanged at
`d12caafa22ad66d094db96b09c40bdfbb18343e2`. Master then took `8e9d816c` (authority/014, CERT-912)
on top.

I did not merge it and did not ask for it. I caught it because PR 2900 was present in a sweep at
12:18Z and absent at 12:20Z.

**Factual note, not a complaint:** the token carried "EXACT CURRENT-MASTER FULL CI REQUIRED BEFORE
MERGE" and the PR base was pinned at `e84e3f4e` while master was `6c6a9277`. The head sha is
unchanged, so the branch was not rebased before the merge. Whether that condition was satisfied
another way is the integrator's judgment and it owns the directive; a deployed merge is never
reverted except by Alex. Recording it only so the trail is complete. Directive
`162-merge-d12caafa….md` was still bare at 12:28Z — the rename lags the merge.

### Post-deploy check (PROCESS-V2: done = on production, checked once by the builder)

Production reached `8e9d816c` at **12:28Z**. lane1/086 is ours, so the check is ours.

| check | result |
|---|---|
| `a698a539` is an ancestor of `origin/master` | **yes** (`git merge-base --is-ancestor`) |
| app booted | `status: ok`, `db: true`, `redis: true`, uptime 70s, `web.1` |
| dyno import safety | proven by the release phase completing (Procfile validates `from app.main import app` before Alembic) |
| **NFL Week 1 count after the registry change** | **still 18** — the Step-1 sport scoping created no new rows |
| Sentry, 24h | 10 unresolved; the nine `Cron failure: *` issues are all **0 events in 24h** (lifetime counts, gotcha #49). The one live issue is `calibration main build ended cancelled after 740165ms`, 22 events — calibration's, and it is the documented D45 effect: the 12:27 merge cycled `worker-heavy` and killed a running beat. Not ours, already on record. |

The Week 1 recount is the meaningful arm here: CERT-911 changes `find_or_create_event` Step 1, so a
regression would have shown up as extra NFL rows. It did not.

---

## 3. §3 triage — the sweep command was measuring a page, not a population

**This is the session's real find.** The brief's §3 sweep is:

```bash
gh pr list --state open --json number,headRefName --template '...' | grep lane1/
```

`gh pr list` defaults to **30 items**. There are **78 open PRs**. So the sweep has been reading the
newest 30 across all lanes — 4–5 of them lane1 — and reporting that as lane1's complete picture.
Sessions 101–111 each carried a three-PR watchlist (2669, 2640, 2613) and a note that they would
cross D52's 7-day line "around 9/9".

With `--limit 300` the real figure is **33 open lane1 PRs**. I classified every one of them with
`git merge-base --is-ancestor <head> origin/master`: **all 33 are UNMERGED**, none already landed.
**Six are already past the D52 line** (updated 8/21–8/26; oldest created **2026-08-12**), and 26
more cross it between 9/5 and 9/10 — straight through kickoff week.

I caught it by accident: PR 2613 was in the brief's table but absent from my first sweep, so I
checked it directly and found it OPEN. The truncation was the explanation, not a state change.

Filed as **#3021** with the full aged table. Under D52 the rescue sweep is the **integrator's**, so
lane1 flagged and deliberately touched no branch. Two called out as do-not-sweep: **2776**
(deliberately parked until the contested-id pre-check hits 0 — not stale, a gate; D42 says do not
loosen the index) and **2228** (the only one of the 33 still `mergeStateStatus: CLEAN`).

Same class as the known `gh issue list --limit` truncation. Any sweep without `--limit` is reading
a page.

### The other §3 arm — lane1 BLOCK rows

Eight lane1 `BLOCK -- TOKEN WITHHELD` rows. The only one newer than CERT-853 is **CERT-870**
(lane1/088, #2919), which 111 already triaged as resolved via merge train PR 2945. I did not
re-chase it, but I did chase its **two FOLLOW-UPs**, because #2919 closed at 04:48Z today and a
follow-up whose only home is prose in a ledger row on a closed issue is exactly the orphan class
111 generalized. Both turned out to be **already closed by the landed code**:

- `LANE1-088-VALIDATE-IMAGE-ON-READ` — `participant_images.py:218` now calls
  `validate_player_image` on read, pinned by `test_participant_images_1052.py:62`.
- `LANE1-088-REGISTER-COVERAGE-CLAIM` — the landed frontend CONTROL arm names both uncovered
  players by name (`feedCardParticipantImage.test.tsx:133`, "the two players we have nothing for
  (Joel Schwaerzler, Tomas Barrios)") and proves they degrade to initials rather than rendering
  broken.

Searched substance as well as the ALL-CAPS token, per the brief's own trap note. **The check came
back clean — that is the check working.**

---

## 4. Week 1 — still 18, line held for the 22nd session

Counted twice, before the deploy (12:22Z) and after it (12:29Z). **18 both times.** Alex has not
run the repair. I did not run it and did not route around the gate.

Both phantoms re-confirmed byte-for-byte:

| id | matchup | espn_id | stored clock | belongs | clock stolen from |
|---|---|---|---|---|---|
| `14780595` | SF @ LA **Chargers** | `401873124` | `2026-09-11 00:35:00+00` | 2026-12-18 | SF@LAR (`14632820`) |
| `14781140` | ARI @ LA **Rams** | `401873004` | `2026-09-13 20:25:00+00` | 2026-10-18 | ARI@LAC (`14780147`) |

Driven from a python file, not an inline `curl -d`, and branched on `'rows' not in d` first.

---

## 5. D48 LOOK on `8e9d816c` — and a baseline correction

Production sha moved, so the shot was owed. `SHOT_W=390`, `/sports/americanfootball_nfl`. No
regressions: crests on every card, probabilities sum to 100, real games carry Proj lines, header
"Upcoming 19" / footer "Showing 19 events" = 18 in-window + Bills@Lions Sep 17 (Week 2), as
expected.

**§5's baseline was wrong on one row and I corrected it rather than filing a false regression.**
The shot showed the Sep 10 phantom carrying `Proj 25-23`, where §5 said "**no Proj**". Before
claiming a change I checked the older reports: **session 108 recorded `Proj 25-23` on that card.**
110 dropped the field from its table and 111 hardened the omission into an explicit negative, which
propagated forward. Verified twice at `8e9d816c` — cropped at 2× (`Proj 25-23`, unambiguous) and in
the served payload (`projected_home_score: 25.0`, `projected_away_score: 22.5`).

Corrected table for 113:

| slot | real | phantom |
|---|---|---|
| Sep 10 5:35 PM | LA **Rams** v SF — 65/35, `Proj 26-22`, Netflix | LA **Chargers** v SF — 57/43, **`Proj 25-23`**, Netflix |
| Sep 13 1:25 PM | LA **Chargers** v ARI — 82/**18**, `Proj 29-18`, CBS | LA **Rams** v ARI — 86/**14**, **no Proj**, CBS |

Sep 13 real/phantom assignment now confirmed a **fifth** time (108, 109, 110, 111, 112). 104's table
had it swapped; do not "correct" it back.

Nav offset moved again, fourth data point: this shot it occluded the Sep 13 phantom's header and
"Los Angeles Rams" line. Never reuse a prior session's crop.

---

## 6. #2869 — commented, with something it did not already say

Eleven consecutive sessions correctly stayed silent. **This one had new material**, verified from
data rather than pixels: `#2869#issuecomment-5540546849`.

From `GET /api/events?sport=americanfootball_nfl&days=14` — the endpoint `/sports/[key]` actually
renders from (`page.tsx:42`), *not* `/api/leagues`, which carries no odds at all:

| id | role | `bookmaker_count` | odds `captured_at` | `win_probability_sources` |
|---|---|---|---|---|
| `14632820` | Sep 10 **real** | **20** | 2026-09-04T08:36:29Z | kalshi, betting, betting_book_count |
| `14780595` | Sep 10 **phantom** | **2** | **2026-08-30T23:36:40Z** | betting_book_count only |
| `14781140` | Sep 13 **phantom** | **2** | **2026-09-01T18:37:14Z** | betting_book_count only |
| `14780147` | Sep 13 **real** | **20** | 2026-09-04T11:06:59Z | kalshi, betting, betting_book_count |

Both real rows: 20 books, captured today, a published `betting` source and `kalshi`. Both phantoms:
exactly 2 books, a capture days stale, and **no `betting` and no `kalshi` entry at all**. The odds
rail stopped writing to the phantoms days ago while refreshing their correctly-dated neighbours
hourly.

Two things follow. First, the user-visible one: `14780595` still renders `Proj 25-23` from an
**Aug 30** capture with no staleness treatment, so on the phone-width page it is
*indistinguishable* from the real game — crest, split, projected score, `Netflix` tag. A five-day-old
line shown as current. Second, it is a cheap ESPN-independent instrument that independently agrees
these two rows are the outliers — useful precisely because it does not need ESPN or StatPal to be
reachable.

Nothing built. Filed under D35 while #2693 is open. Did not diagnose which rail wrote
`commence_time_source = 'espn'` — still untraced and unowned, still the measurement lane's.

---

## 7. What I did NOT do

- Did not read night two. Not due.
- Did not merge anything, did not rebase anything, did not touch any of the 33 stale branches.
- Did not run the schedule repair or the generic `POST /api/admin/repairs/{name}` bypass.
- Did not re-run the dry-run just to re-confirm. 100 ran it; 102–112 all agree the count is 18.
- Did not re-file the CERT-911 follow-up (111 gave it a home on #2879) and did not build it.
- Did not write YOUR-TURN.md or an alex-inbox note — the Week 1 ask is already DO 1 and unchanged.
- Did not run the full suite locally (D40) and pushed no code.

---

## 8. New traps for 113

- **`gh pr list` / `gh issue list` without `--limit` read a 30-item page.** The §3 sweep has been
  wrong since ~101 because of it. Always pass `--limit`.
- **A LOOK observation degrades across sessions.** 108 saw `Proj 25-23`; 110 omitted it; 111 turned
  the omission into an asserted negative; the brief then carried the negative as baseline. An
  omission in one session's table is not evidence of absence in the next. Before filing "X changed",
  grep the *older* reports, not just the immediately preceding one.
- **`/api/leagues/{sport_key}` carries no odds and only 8 `upcoming_games`.** `/sports/[key]` renders
  from `/api/events?sport=…&days=14`. Its event objects use `current_odds`, not `odds`, and the
  team-name keys are `home_team` / `home_team_data`, not `home_team_name`. Reading the wrong one
  returns a confident row of `None`.
- **`events` has no `predicted_*_score` column** — `undefined_column`. Projections come from the
  odds join, surfaced as `current_odds.projected_home_score`.
- **A PR vanishing between two sweeps may mean it merged, not that it was truncated — and vice
  versa.** Check both. I hit both cases in one session: 2613 vanished from truncation, 2900 vanished
  from a real merge.
- **`grep --include=*.py` unquoted is a zsh glob error**, not a no-match. Quote the pattern.
- Cropping a `look.sh` PNG with PIL at 2× is the reliable way to settle a small-text reading; do it
  before asserting a rendered value changed.

Everything else in 111's §9 trap list still holds and carries forward.
