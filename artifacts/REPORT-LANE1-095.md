# lane1/095 — CERT-890 landed, the sentinel's close path can't fire, and the US Open twin measured

**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1.** Kickoff Thu 9/10.

Session: Fri 2026-09-04, 07:04Z → 07:40Z (12:04am → 12:40am PT). Worktree `~/bainluck-dev/lane1`,
branch `lane1/094b-artifacts`.

---

## 1. ITEM ONE — CERT-890 landed on master mid-session

**Status at session start (07:05Z):** `07ca1622` not on master; integrator lock **HELD** by
integrator/135, **pid 96453 alive** (started 22:42 PT, actively draining); the sha already queued as
`runner-inbox/integrator/143-merge-07ca1622….md`. Both merge gates run and pass:

- **Gate 13** — `grep 07ca1622… CODEX-CERT-LOG.md | grep -q 'TOKEN GRANTED'` → **PASS** (row 601,
  `CERT-890 -- lane1-094-the-clock-not-the-row-count`, 2026-09-04 05:48Z, GREEN — TOKEN GRANTED).
- **Gate 18** — strict `supersedes:?\s*CERT-890` scan of the whole ledger → **zero rows, PASS**.

Per §1 of the restock, a live lock-holder with the sha already queued means **wait**, and I did.
That was the right call: **the integrator merged it during the session.**

```
f22dc37a Merge lane1/094-the-clock-not-the-row-count @ 07ca1622… (CERT-890, #2953) into master
```

`git merge-base --is-ancestor 07ca1622 origin/master` → **true** at 07:32Z. Master then moved on to
`abc35bfa` (three further merges batched on top — CERT-891, CERT-892, CERT-875).

### The owed post-deploy check — DISCHARGED

The release landed 360s into a bounded poll (`/tmp/l1_deploy_poll.sh`, terminal condition =
`merge-base --is-ancestor`, **not** "health returned something" — the 093 watcher trap).
`/api/health` → `commit: abc35bfa`, and `git merge-base --is-ancestor 07ca1622 abc35bfa` is **true**
(object fetched first; an unfetched descendant reads as not-deployed).

The exact call CERT-890 required — **no `limit` parameter**, the call that returned a bare Heroku
HTML 500 with no reason and no correlation_id before #2953:

```
POST /api/admin/events/reconcile-anchor-schedule?sport=americanfootball_nfl
→ HTTP 200, examined: 25, next_cursor: "2026-09-20T17:00:00+00:00|14782151", 13.87s wall
   stopped_by: null · terminal: partial · has_more: true · eligible: 239 · applied: false
```

**25 examined and a resumable cursor — both required values met**, in 13.87s against Heroku's 30s
router (the pre-fix default was ~59s of fetching). `stopped_by: null` means the row limit is the
bound at 25 and the 18s deadline did not need to fire — the designed shape.

**Third independent derivation of the Week-1 ship**, unasked-for, on page one:

```
14780595  espn 401873124  ours 2026-09-11T00:35Z  ESPN 2026-12-18T01:15Z  delta 98.03d
14781140  espn 401873004  ours 2026-09-13T20:25Z  ESPN 2026-10-18T20:05Z  delta 34.99d
agrees: 23 · teams_disagree: 0 · no_answer: 0 · applied: false
```

Banked as a new append-only ledger row `CERT-890 -- POST-DEPLOY DISCHARGED` (2026-09-04 07:50Z). The
graded row at line 601 is **unedited** (notice 12). That row is explicitly *not* a merge note — the
merge was integrator/135's and its note is theirs to append.

**`143-merge-07ca1622….md` was still un-suffixed at session end** — the integrator had not marked it
`.consumed`. That is the integrator's to do, not lane1's. Do not rename it.

**The 094 branch is now unfrozen.** The token named `07ca1622` and it is merged, so
`lane1/094-the-clock-not-the-row-count` no longer needs to be held at that sha. The two named
follow-ups can now be built:
`LANE1-094-OPENAPI-COST-DESCRIPTION`, `LANE1-094-BUDGET-TAIL-COUNT-COPY`.

---

## 2. ITEM TWO — night two is 23h out, so I pre-flighted it instead, and found a real defect

The second firing is **06:40Z Sat 9/5**, ~23.6h after this session. Not readable now. Rather than
leave the item untouched I read the mechanism it is supposed to prove.

### The resume path itself is sound

`_load_continuation` / `_save_continuation` (`anchor_schedule_sentinel.py:154-198`) use Redis key
`anchor_schedule_sentinel:continuation`, `setex` with a 7-day TTL, and **delete** rather than write
an empty string on a finished sweep. A Redis fault degrades to `None` (full restart) rather than
raising. The exhausted-cursor restart (`:311-323`) fires only when a resumed page examines zero rows
and only once per run, so a moving window cannot cause a permanent silent stall. No defect found here.

### But the sentinel can file and can never close — FILED AS #2983

`:371` `complete = stopped_by is None and not resumed`, and the file/close gate at `:497` is
`if file_issues and (red or state["complete"])`. So a GREEN close needs **one unresumed run to cover
the whole window inside its budget**. Two independent reasons it cannot:

1. **The budget is smaller than the population.** `DEFAULT_DEADLINE_SECONDS = 300.0`;
   `SWEEP_PAGE_LIMIT = 100`; `DEFAULT_MAX_PAGES = 12` (1200 rows — slack, the deadline binds).
   Night one measured **600 of 685 examined**, `stopped_by: deadline`, 6 pages. Six pages of 100
   exceeded 300s, so observed cost is **> 0.50 s/row** and 685 rows needs **> 343s**. A fresh sweep
   is about one page short — and the population grows as NFL Week 1 lands.
2. **`not resumed` blocks the other arm.** On the night the sweep *does* reach the window end, it
   gets there **by resuming**, so `complete` is False anyway.

Steady state: fresh(600) → resumed(85, reaches end, still `complete: false`) → fresh(600) → …
**Coverage is fine** — that is exactly what CERT-843's continuation bought. What is broken is that
nothing records the *union*, so the rail can never reach its own verdict. #2978 will stay open
forever even after every drift in it is repaired.

Quieter second consequence: on a resumed night with no drift in its slice, `red` is False and
`complete` is False, so gate `:497` fires **neither** branch — #2978 is not even re-pointed at a
current observation and silently goes stale. **The restock's expectation that night two re-points
#2978 is therefore probably wrong**, and that is not a dedupe failure.

### Preregistered prediction for night two (written before the run, in #2983)

- `resumed_from: "2026-11-28T00:00:00+00:00|15197566"` — **not** `null`
- `restarted_from_exhausted_cursor: false`
- `examined` ≈ **85**, `eligible` ≈ 685, `pages: 1`
- `stopped_by: null` **and yet** `complete: false`, `terminal: "partial"`
- `continuation: null`

`complete: true` falsifies #2983 — close it. `resumed_from: null` or
`restarted_from_exhausted_cursor: true` is a **different and worse** bug (the CERT-843 blind spot
reopening) and gets its own issue.

I did **not** probe Redis for the saved cursor. Night two's own `resumed_from` answers it, I could
not act on an early answer, and a probe with no decision hanging on it is a parked measurement.

---

## 3. ITEM THREE — Week 1 is still 18. The line held.

Counted first, branching on `if 'rows' not in d` before touching `rows`:

**`WEEK1_COUNT = 18`** at 07:06Z. Both movers still present at the same slot:

```
14632820  San Francisco 49ers @ Los Angeles Rams      2026-09-11 00:35Z  espn 401872657
14780595  San Francisco 49ers @ Los Angeles Chargers  2026-09-11 00:35Z  espn 401873124   <-- moves
14780147  Arizona Cardinals   @ Los Angeles Chargers  2026-09-13 20:25Z  espn 401872926
14781140  Arizona Cardinals   @ Los Angeles Rams      2026-09-13 20:25Z  espn 401873004   <-- moves
```

**Alex has not run the repair.** I did not run it and did not build a way around the gate — the
generic repair rail `POST /api/admin/repairs/{name}` remains a real bypass of
`_check_admin_destructive` and remains refused, as in 091/092/093/094. That is now **six** sessions
holding the same line.

`YOUR-TURN.md` **DO 1** is live and substantively correct. One staleness note, not acted on because
lanes never edit that file: it reads *"Kickoff is in seven days"* — as of today it is **six**.

---

## 4. The US Open twin, measured at the DB layer — #2878

Chased from a wrong turn: `/event/15304374` renders "Event not found", which is **not a bug** —
the route is `/event/[domain]/[slug]`, so my URL was malformed. But the lookup exposed that
`15304374` is a `tennis_wta` row named "Eala v Jovic" at a **midnight placeholder**, while the same
players' US Open matches live under `tennis_wta_us_open` with full names and real times.

Already owned as **#2878** (p1, `needs-agent`, `matching-symptom`, unassigned) and **#2964**. Under
D35 with #2693 still open these are **filed, not fixed**. I added measured evidence the two prior
UI-level confirmations lacked. Window `[2026-09-04, 2026-09-07)`, all `tennis%` keys, 56 rows:

| | count |
|---|---|
| ghost rows (generic key, `espn_id IS NULL`) | **23** |
| ...on the `00:00:00+00:00` midnight placeholder | **23 / 23** |
| ghosts pairing to a `tennis_*_us_open` row | **19** |
| ghosts with no tournament row yet | 4 |

The pair is mechanically derivable — the tournament row's name tokens are a superset of both ghost
surnames on the same tournament day. `15302922`/`15302923` are **adjacent ids**: two writers mint the
same match seconds apart and the registry never links them. 19/23 is a floor; the 4 unpaired are the
semi-final slate not yet minted under the tournament key.

**The symptom has degraded since the 9/3 pass.** D48 LOOK, `/sport/tennis/wta` at 390px: every card
under **"UPCOMING GAMES"** now reads **`Sep 3 5:00 PM`** — a date in the **past**. `00:00 UTC Sep 4`
is `5:00 PM PT Sep 3`, so once the clock passed 5pm PT the placeholder stopped reading as "today"
(what 9/3 recorded) and started reading as yesterday. Swiatek v Bouzkova is actually Sep 5 15:00Z.
The ghost cards also render **letter-tile avatars, no faces**, because the row carries a surname only.
Evidence: `artifacts/lane1-095-wta-tour-ghost-cards-sep3-past-date-phone.png`. (Note: `mkdir` for a
new artifacts subdirectory is silently virtualized in this sandbox — `ls` showed the directory while
every write into it failed `ENOENT`. Writes only land in directories that existed at session start.)

Posted an acceptance test for the #2693 fix, guarding both directions (the ghost must not merely be
hidden from the tour page while the duplicate row survives — that would leave #2964 broken).

---

## 5. Owed — `LANE1-093-BONDAR-CARD-LOOK` is still one leg short, and this fixture cannot close it

The restock offered Iva Jović (`15304374`, Sat 00:00Z) as a 60-second close. **It does not close it.**
Our data spells her **"Jovic", no accent** — `away_team_name` in Postgres and `home_team` in
`/api/events/search` both. The owed leg needs a *newly-resolved accented* player on screen; a row
with the accent stripped cannot prove the accent renders.

Worse for the leg: the generic-key ghost rows carry **surname only and no face at all** (letter
tiles, §4). A newly-resolved face will never render on the tour-page card for these rows while
#2878 stands. **The leg stays owed and its cheapest close is now a `tennis_*_us_open` card**, which
carries full names — not a tour-page card.

---

## 6. Filed this session

- **#2983** (new) — the sentinel can file but can never close. `type:bug`, `priority:p2`,
  `area:admin-ops`, `needs-agent`. Carries the preregistered night-two prediction.
- **#2978** — comment cross-linking #2983: do not read its staying open as unrepaired drift.
- **#2878** — comment with the measured 23/23/19/4 pairing, the degraded `Sep 3 5:00 PM` symptom,
  and an acceptance test.

Not re-filed: #2980, #2953 (merged), #2737, #2693, #2919, #2957, #2964.

---

## 7. Traps hit this session

- **A live lock-holder with your sha already queued means wait.** It merged 25 minutes later without
  my intervention. Waiting was the action.
- **`/event/{id}` is not a route** — it is `/event/[domain]/[slug]`. A 404 from a malformed URL is
  not a finding. I nearly filed it.
- **A fixture offered as an accent proof may have the accent stripped in our own data.** Check the
  payload spelling before spending a screenshot on it.
- **A `limit=10` probe of the anchor rail returned in 1.9s, not the 5.66s CERT-890 measured** — per-row
  cost is heterogeneous (7 of 10 were `no_answer`, which is cheap). **Do not extrapolate a flat
  s/row from the front page**; #2983's arithmetic deliberately uses the sentinel's own night-one
  measurement over its own tennis-excluded population instead.
- **`git merge-base --is-ancestor` needs the object present locally** — fetch before asserting, or a
  descendant sha reads as "not deployed".
- Standing traps that held: `look.sh` output was **11,508px** tall, cropped with PIL before `Read`.
  `area:matching` is not a label (`gh label list` first).
