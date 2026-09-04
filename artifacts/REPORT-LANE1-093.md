# REPORT — lane1/093 — read the 06:40Z sentinel, re-count Week 1

Thu 2026-09-03 8:46pm PT (03:46Z Fri). **PILLAR: TRUTH** (items 1–2) / **FORMATTING** (item 3).

## TL;DR

- **Item 1 (090, the sentinel read): NOT DUE.** `date -u` = 03:18Z at session start; the beat fires
  06:40Z. I did not open the file. Restocked to 094 with a hard clock test. This is the correct
  outcome, not a third slip — see §1 for why it kept getting restocked.
- **Item 2 (Week 1): still 18.** Alex has not run it. I did not try to run it. I **verified his
  exact command is still sound** rather than only re-counting, which is new: `authority_moves_us: 2`,
  the same two rows, `teams_disagree: 0`. The escalation is already filed and unanswered; I added no
  third note.
- **Item 3 (the small win): shipped to a PR.** Anna Bondár's missing face was not a coverage gap —
  it was an accent-folding defect in the join I wrote in `6ea3f6e3`. **239 → 243 of 260** US Open
  participants now resolve. PR #2952, CERT-879 staged.
- **Two new findings filed:** #2953 (a rail whose own default always times out) and fresh
  photographic evidence on #2737.

---

## 1. Item one — 090 is NOT due, and the restock loop has a cause

`date -u` at session start: **03:18Z Fri**. The beat is `crontab(minute=40, hour=6)` — **06:40Z**.
Per directive §1 I did not open the file, and I did not guess at its contents.

**Why this has now been restocked three times, which is worth naming rather than repeating:** the
sentinel's code reached production in `0bbcc735`, deployed ~8pm PT Thursday. Sessions 091 (01:35Z),
092 (02:25Z) and 093 (03:18Z) all ran in the window *between the deploy and the first firing*. There
was never a run to read. The first real firing is **06:40Z Fri = 11:40pm PT Thursday**, ~3 hours
after this session ends.

So 094 is the first session that can actually discharge it. I have restocked it with the clock test
intact and the confirmed wiring, so 094 does not re-derive any of it.

## 2. Item two — 18, and the command in front of Alex is verified live

```
COUNT = 18
```

Branch-on-`'rows' not in d` guard used as directed; the query returned a real `rows` key.

Rather than stop at the count, I ran the **dry run**, which is readable with the ordinary admin
secret. This is the part 091/092 could not confirm was still true:

| the game | event_id | espn_id | we say | ESPN says | out by |
|---|---|---|---|---|---|
| LA Chargers v San Francisco 49ers | 14780595 | 401873124 | Sep 11 | **Dec 18** (Wk 15) | 98.03d |
| LA Rams v Arizona Cardinals | 14781140 | 401873004 | Sep 13 | **Oct 18** (Wk 6) | 34.99d |

`by_verdict: {agrees: 18, authority_moves_us: 2, teams_disagree: 0, no_answer: 0, refused_*: 0}`

**Both moves land inside `limit=20`**, which is exactly the bound in the command already sitting in
`alex-inbox/lane1-091-...`. So that command is not stale and does not need paging — it is correct as
written, tonight. That is the useful new fact: the ship is not blocked on a bad command, only on the
command being run.

### I did not run it, and I did not build a way around the gate

`_check_admin_destructive` (`app/routes/admin_utils.py:151`) states its intent in as many words:
*"Agent lanes are issued `ADMIN_TOKEN` and NOT `ADMIN_TOKEN_DESTRUCTIVE`, so a lane physically
cannot run one of these routes no matter what it decides to do."*

I found a route around it and **deliberately did not take it.** The generic repair rail
`POST /api/admin/repairs/{name}` is gated on `_check_admin_secret` **only** — that is the rail lane1
pushed 13 twin-drain batches through tonight. Registering `reconcile_anchor_schedule` in `_REPAIRS`
would have made the Week-1 fix lane-runnable within the hour.

That is a security-shaped change whose entire effect is to exempt me from a gate built to exclude
me, made unilaterally, at night, against a deadline. 091 refused the `heroku config` path, 092
refused the direct-Celery path, and I refuse this one. Recording the asymmetry because it is the
real mechanism behind the stall and Fable-5 will need it to rule:

| rail | auth | lane can run it |
|---|---|---|
| `POST /api/admin/repairs/{name}` (twin drain) | `_check_admin_secret` | **yes** — 13 batches tonight |
| `POST /api/admin/events/reconcile-anchor-schedule?apply=true` (Week 1) | `_check_admin_destructive` | **no** |

Alex's D51 and `YOUR-TURN.md` §1 both say the Week-1 fix is lane1's. The mechanism says it is not.
Those are unreconciled, 092 filed exactly that in
`NOTE-TO-FABLE-FROM-LANE1-092-...` with three options and a recommendation, and it is **unanswered**.
Per directive §2 I did not write a third identical note. This paragraph is the one line.

## 3. Item three — the small win, and it was a bigger class than one player

Directive §3 offered Bondár as "thin register, not a rebuild". **It was neither** — the register is
perfect and nothing needed registering.

`data/tournament_registers/us-open-2026.json` holds her with a **verified face** *and*
`hun.png`, `verified_subject: true`. The join missed her. `participant_image()` looked up
`slugify(name)`, and `slugify`'s `[^a-z0-9\s-]` class **deletes** every character `str.lower()`
could not fold — so an accented letter survives as *nothing*, not as its base letter:

```
Anna Bondár   -> anna-bondr      (register keys her anna-bondar)
Iva Jović     -> iva-jovi
Federico Cinà -> federico-cin
```

A miss and "we looked and there is no photo of this person" are the **same `None`**. That is why
this looked like coverage: the 376/378 number I shipped in `d3d0b80f` was *true*, and the card still
drew initials.

A second, independent disagreement fell out of the measurement: `entity_key` makes punctuation a
**separator** (`J.J. Wolf -> j-j-wolf`), `slugify` **deletes** it (`JJ Wolf -> jj-wolf`).

**Measured against the 260 distinct US Open participants in `events`:**

| | |
|---|---|
| resolve before | 239 / 260 (91.9%) |
| resolve after | **243 / 260 (93.5%)** |
| recovered | Anna Bondár, Iva Jović (faces), Federico Cinà (flag — he has no face), JJ Wolf |
| collisions under the fold | **0** of 378 |
| still unresolved | 18, genuinely absent from the register — a coverage question, not this fix |

Strictly additive: NFKD-then-drop-combining is identity on ASCII, so every name that resolved before
resolves to the identical key. That is asserted as a test, not claimed in prose.

**My first draft had a hole and its own guard caught it.** I kept an early
`all(alias in owner) -> skip`, which is precisely how a collision between two *different* players
goes silent — the second player's aliases are all claimed, so the loop that distinguishes "same
person re-listed" from "two people, one key" never runs. That is the **D55 violation the change
claims to close**. The skip is gone; a cross-player collision now logs WARNING, first still wins.

Guards proven red by two ablations before commit: revert the fold → **6 failed**; drop the
`display_name` alias → **3 failed**. Against the real committed register, not invented spellings.

Gates: focused **283 passed / 0 failed**, `test_startup.py` green, ruff clean on both files,
mutation residue **CLEAN** (550 needles). Frontend untouched — `d3d0b80f` already consumes the
fields. Full suite is CI's under D40.

**PR #2952 · sha `70f5f930` · CERT-879 staged.** Backend/data path, so bus-graded, not Tier A.

## 4. D48 mystery-shop — what I actually saw

Production `/sports`, `tools/look.sh`, read and judged.

**Good news, and it is my own prior ship confirmed live:** tennis cards are drawing real faces —
Halys/Zverev, Starodubtseva/Sakkari, de Minaur/van de Zandschulp all render headshots beside the
soccer crests. `d3d0b80f` is working in production.

**Bad news: #2737 is on screen, in its worst possible form.** Two cards for one game, **adjacent in
Live Now on the same render**:

| | left | right |
|---|---|---|
| status | `Bottom 5th` | `LIVE` |
| score | **2 - 1** | **none** |
| St. Louis | `St. Louis Cardinals` **48%** | `St.Louis Cardinals` **54%** |
| LA | `Los Angeles Dodgers` **52%** | `Los Angeles Dodgers` **46%** |

The favourite is **flipped between two cards the eye takes in together**, and the `St.Louis` (no
space) `teams` cleave is visible as the literal rendered string — on the row that has no score and
no opener, i.e. the market-created ghost. Evidence added to #2737 as a comment; no new issue.

A second pass at **phone width** (`SHOT_W=390 SHOT_H=844`, which is what D48 actually asks for)
caught the same pair live a few minutes later at **54/46 and 57/43** — still contradicting, still
one with the score and one without, but now *separated by another card*. So on a phone the user
does not see them side by side; they meet the same game twice while scrolling, seconds apart, with
different numbers. Both widths are worth taking: the desktop shot makes the contradiction legible in
one frame, the phone shot shows the shape a real user actually hits.

This is also the live proof of §4 of the 092 directive: the drain took contested ids 163 → 5 and
**this is still on screen**, because the rail's only write is `SET espn_id = NULL`, so a cleared
twin becomes an *anchorless* twin that the collision repair cannot see. `contested_ids: 5` is not
"twins are nearly gone."

## 5. Filed tonight

- **#2953** (new) — `reconcile_anchor_schedule.DEFAULT_LIMIT = 100` against a measured **~0.57s/row**
  (the docstring claims ~0.2s) is ~57s into a 30s router timeout, so **omitting `limit` always
  returns a bare Heroku error page** — no JSON, no `reason`, no `correlation_id`. The route's own
  docstring advises exactly the thing that always fails. Not blocking Week 1 (Alex's command pins
  `limit=20`); a trap for the next operator. Filed, not fixed.
- **#2737** — comment with the two-card photograph above.
- **#2919** — the open one-liner is what PR #2952 closes.

## 6. Traps hit tonight (new ones only)

- **`limit=200` and the bare default both 500 the anchor-schedule route** — that is #2953. My first
  two dry-run attempts died on it before I thought to time the thing.
- **`cd backend && ...` persists the working directory into later Bash calls.** Two calls later a
  bare `cd backend` failed with `no such file or directory`. Absolute paths only.
- **`look.sh` defaults to 1280 wide (2560 retina), not phone width.** `SHOT_W=390 SHOT_H=844` is
  documented on line 3 of the script and is what D48 actually asks for. The desktop shot was still
  worth having — the duplicate was legible because two cards sat side by side.
- **`gh issue create --label area:matching` fails** — that label does not exist. `area:admin-ops`,
  `area:sports`, `area:event-details` do. `gh label list` before filing.
- Confirmed still true: crop the `look.sh` PNG with PIL before `Read` (7,848px tall tonight); use
  `www.` (apex 307s).

## 7. State at session end

- **`d9dde1c2` is on master** (`91e64cfe..d9dde1c2`), master CI running at hand-off.
  CERT-879 came back **GREEN — TOKEN GRANTED** at 03:50Z for `70f5f930`, ~20 minutes after staging.
  PR #2952 CI: 15 pass / 0 fail on the exact tree; master was unmoved at `91e64cfe` so the branch
  was fast-forwardable. Merged in a detached worktree (never in the dirty shared tree), re-gated
  there — 57 passed, mutation residue CLEAN — and pushed.
- **Merge gates both run and recorded:** gate 13 — `TOKEN GRANTED` present for `70f5f930`; gate 18 —
  no later ledger row names CERT-879 after "supersedes" (it is the last row). I did not edit the
  graded row; the ledger is append-only.
- **⚠ OWED post-deploy check, handed to 094: `LANE1-093-BONDAR-CARD-LOOK`.** The token was granted
  with it. I could not discharge it tonight — Bondár is in the draw but had no fixture on screen.
- Integrator lock: **claimed** for the push via `scripts/claim_lane_lock.py` (ruling 017), released
  after deploy verification.
- Week 1: **18**. Twin drain: untouched tonight (correctly — it is at its floor of 5).
- 090 restocked into 094, still pending, now genuinely readable.
