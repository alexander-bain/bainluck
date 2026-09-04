# lane1/098 — the symmetric write failure, and the accent that finally made it onto a card

**PILLAR: TRUTH.** **SHIP: a 49ers fan stops seeing their team play twice in Week 1.**
Kickoff Thu 9/10 — **six days.** Session ran Fri 2026-09-04, ~01:25–02:00am PT.

Night two of the repaired sentinel was **not readable this session** — it runs 06:40Z Sat 9/5,
roughly 22 hours after this session began. Item 2 of the 097→098 restock is carried forward
verbatim, amendment and all.

---

## 1. Item three — BUILT. `LANE1-096-CONTINUATION-WRITE-FAILURE-REGRESSION` is discharged

`047f57badad1306e99afecc9f78497be5df43e51`, pushed on
`lane1/098-the-symmetric-write-failure-cannot-close` (cut from the granted `69c9ac98`, one commit
on top). **Not yet cert-staged — see §2 for why, and exactly what 099 does.**

### What it guards

CERT-896 guarded the dangerous half of the two-key divergence: the position advances, the claim
does not. Marker-first ordering makes the **mirror** the likely half, and it had no arm at all:

```
the marker lands naming c2, the continuation write fails
  -> store holds cursor c1 beside a claim that says c2
  -> strict-equality binding reads CHAIN-BROKEN
```

`_ContinuationWriteFailsRedis` mirrors `_MarkerWriteFailsRedis` — fails only the cursor write, only
on night two. The arm asserts the divergence is **actually reached** (`cursor == b"c1"` beside a
marker carrying `"cursor": "c2"` and `"drift_seen": true`) before asserting anything follows from
it, then pins the two things that matter:

- **night three re-sweeps and RE-FINDS 4242** — the fault costs the *close*, never the *coverage*,
  because the sweep is read-only and idempotent so a stale position loses nothing;
- **night four's clean tail reaches the window end and still cannot close** — the broken chain
  stays broken.

**Ablation, run and reverted.** Replacing the binding with `open_pass is not None` fails the new
arm on `pass_open is False` **and** fails CERT-896's arm, with both injected `RuntimeError`s
visible in the trace proving the faults fired rather than the test passing vacuously. Source
restored byte-identical (`git diff --stat` empty).

**Gates:** 194 focused tests EXIT 0 (`test_anchor_schedule_sentinel` 32/32, plus
`test_anchor_schedule`, `_undo_d51`, `reconcile_anchor_schedule` ×3, `test_startup`,
`test_tasks_wiring`); black clean; ruff clean; `scan_mutation_residue.py` **CLEAN, 550 needles,
exit 0**. Frontend untouched.

### Item 3.2 — SETTLED, and deliberately NOT built

The restock asked whether the mismatch should instead **resume `c1` as a valid pass**, and said not
to without a guard proving it cannot be reached from the dangerous direction. I worked it and the
answer is **no**. Recording the reasoning because it is the whole value of the question:

The two divergences are told apart only by **ordering** the cursors — marker BEHIND the store is
the CERT-896 direction, marker AHEAD is this one. Ordering is available: `decode_cursor` in
`reconcile_anchor_schedule` reads the keyset cursor as `(commence_time, event_id)`, which advances
monotonically within a pass. So "accept when the marker is strictly ahead" looks provable, and I
nearly built it.

**It has a hole.** `_sweep` can walk the position BACKWARDS: an exhausted resume restarts at the
oldest row mid-run (`restarted_from_exhausted_cursor`, `anchor_schedule_sentinel.py:488-498`), so
monotonicity is not an invariant of the chain. Chain that with a lost marker write on the
restarting night and you get a marker that *looks* ahead but is a stale claim from an earlier
night — and the drift the restarting night saw is not in it. That is a false GREEN, reachable, and
strict equality has no such hole. The counterexample is written into the new arm's docstring so the
next reader meets it before the idea, not after shipping it.

Cost of holding the line, stated honestly: a broken chain is not one lost night. `_clear_pass()`
fires but the continuation is deliberately kept, so the chain stays broken until the sweep reaches
the window end and clears the cursor; a fresh pass starts the night after. Several nights of no
close, never a wrong close. Given the trigger is one `setex` raising between two adjacent calls,
that is the right price.

---

## 2. Item one — the merge did NOT land. Do not merge it yourself either

`69c9ac98` is **still not an ancestor of origin/master** as of 02:00am PT.

- `runner-inbox/integrator/152-merge-69c9ac988f7191c6bb5ff74202626c10a03909da.md` is **queued and
  untouched**, behind `150-merge-native-006-us-open-faces.md` and `151-merge-5a36edba…`; `153`
  arrived at 01:27.
- `.claude/handoff/LANE-integrator.lock` reads **`status: HELD` — 2026-09-04T01:23 PDT,
  integrator/149+150**. Item 149 went `.running` at 01:14 and is now consumed.
- **The integrator is alive, not stuck.** Master moved twice during this session —
  `b2474390` (native-006 US Open faces) and `629c8092` (`fix(ci): the sports warm-shape guards pin
  the request, not the call's punctuation`, which reads exactly like an integrator unblocking a red
  gate mid-batch).

So waiting was right for the **third** session running. The lock being HELD by another identity
also settles it under ruling 017: a lane may not push master without it.

**What 099 does, in order:**

```bash
git -C ~/bainluck-dev/lane1 fetch origin master -q
git -C ~/bainluck-dev/lane1 merge-base --is-ancestor 69c9ac98 origin/master && echo LANDED || echo NOT-YET
```

- **LANDED, and `69c9ac98` is a parent verbatim** → **no rebase needed.**
  `lane1/098-the-symmetric-write-failure-cannot-close` is `69c9ac98` + one commit, so once the
  granted sha is on master the branch's only new content is `047f57ba`. Stage a cert for
  `047f57ba` with `~/bainluck/tools/stage-cert.sh` — never a hand-picked id.
- **LANDED but the integrator REBASED instead of merging verbatim** → rebase the branch onto
  `origin/master`, re-run the gate set in §1, and stage the **new** sha. Do not stage the old one.
- **NOT-YET and the lock is still HELD** → wait again. Do not rename 152, do not write its merge
  note, do not merge in `~/bainluck` (dirty, stale sha).
- **NOT-YET, lock RELEASED, no live integrator** → gates 13 + 18 first (both passed at 096's end
  and nothing has changed them: `TOKEN GRANTED` present for `69c9ac98`, zero rows naming CERT-898
  after `supersedes`), then merge `--no-ff` from a detached worktree so the granted sha is a parent
  **verbatim**.

⚠ Tier: `047f57ba` is `backend/tests/` only, zero source lines. That is **not** Tier A (notice 10
is frontend-only), so it is **bus-graded**.

---

## 3. Item two — night two, carried forward unchanged

Runs **06:40Z Sat 9/5**. Everything in the 097→098 restock §2 still stands and is not restated
here except the two things easiest to get wrong:

- **Read `#2983#issuecomment-5537445111` first.** 096 amended the preregistered prediction in
  writing before the run, because the original was written against the pre-`69c9ac98` code.
- **Which code night two runs now depends on §2.** If `69c9ac98` deploys before 06:40Z Sat, night
  two is the new code and should carry `pass_open: false`, `pass_started_at: null`,
  `pass_expired: false` — the legacy bare cursor reading as `CHAIN-BROKEN`. If it has **not**
  deployed, night two is the old code and those fields will be absent; that is not a finding.
- Poll no earlier than ~06:47Z (#2980), and compare `last_started_at` against the 840s soft limit
  before believing any health string.
- **Night four (Mon 9/7) is the first that can close.** Night three's `complete: false` is the
  repair working, not failing.

---

## 4. Item four — Week 1 is **18**. The line held for the eighth session

Measured 08:35Z on production, branching on `'rows' not in d` first.

The two movers are unchanged and still adjacent above the fold on
`/sports/americanfootball_nfl`, photographed again this session:

| | |
|---|---|
| `Sep 10 5:35 PM` | Los Angeles **Rams** 65% / **San Francisco 49ers** 35% |
| `Sep 10 5:35 PM` | Los Angeles **Chargers** 57% / **San Francisco 49ers** 43% |

`14780595` (SF @ LAC) and `14781140` (ARI @ LAR). I did **not** run the reconcile and did not build
a way around the gate. `_check_admin_destructive` (`app/routes/admin_utils.py:151`) says in as many
words that lanes are not issued `ADMIN_TOKEN_DESTRUCTIVE` *so that a lane physically cannot run
these routes*; the generic repair rail `POST /api/admin/repairs/{name}` is gated on
`_check_admin_secret` only and IS a real bypass, refused by 091–098. The ask is already
`YOUR-TURN.md` DO 1 and I wrote no second note about it.

---

## 5. The owed check `LANE1-093-BONDAR-CARD-LOOK` — **DISCHARGED**

094 left it one leg short and named the leg precisely: *"the path is proven live, the four names
are proven at the resolver and at the CDN, and the two are not joined by one screenshot."* 095
proved the offered close does not work — Jović is stored accent-stripped as `Jovic` in Postgres and
in `/api/events/search`. The restock predicted the cheapest close was a `tennis_*_us_open` card,
which carries full names. **That was right.**

`artifacts/lane1-098-usopen-wta-league-initials-no-faces-phone.png` —
`https://www.bainluck.com/sports/tennis_wta_us_open`, phone width, 09:00Z, backend `6714d33b`,
frontend `b2474390`:

> **Iva Jović  55%** · Alexandra Eala 45%

The accent renders correctly on a live production **card**, not just an event page. An accented,
newly-resolved player is on screen. Leg joined; the check is closed.

Both accented names are in the live league payload (`Iva Jović` upcoming, `Anna Bondár` in Finished
with Keys 2–1), so this is reproducible, not a one-frame fluke.

---

## 6. What the shop found on the way — evidence added to #2447, not a new issue

Same screenshot, the other half: **every one of the 16 upcoming WTA US Open cards draws a
two-letter initials badge. No player photograph anywhere on the page.** Jović is `IJ`.

The contrast that makes it a defect rather than a component with no imagery slot —
`artifacts/lane1-098-nfl-league-same-card-draws-logos-phone.png`,
`/sports/americanfootball_nfl`, **same component, same width, same minute**: every row draws its
club logo. And the photos exist and are served — 094 *fetched* them (Bondár 200 `image/jpeg`
42,529 B, Jović 38,894 B, JJ Wolf 59,796 B), and a `/sports` Live Now US Open card drew both
players' faces on 9/4 at 04:24Z.

| surface | tennis | NFL |
|---|---|---|
| `/sports` Live Now card | photographs ✅ | — |
| `/sports/{league}` game card | **initials ❌** | club logos ✅ |
| `/events/{id}` event page | **initials ❌** | — |

This is open **p1 #2447** ("Event page shows initials where the tournament page has player photos",
`program:ux`, *"one resolver should serve both"*). Per notice 6 I did **not** file a duplicate and
did **not** claim it — I added the league-page surface as a comment
(`#2447#issuecomment-5538012189`) with both served commits read first, as that issue's own
acceptance criteria demand. It stays with `program:ux`.

Worth flagging for whoever takes it: the league page is a **tournament-wide** miss rather than a
per-event one, so it is probably the cheapest place to prove the shared resolver actually works.
Note also that the native-006 merge that landed mid-session (*"a US Open card shows the player's
face"*) is **Tier A iOS-only** — it does not touch this.

---

## 7. D42 — the "no second row" index. The note Alex reads was two days stale; it is now current

The restock said: if D42 is pressed, the answer is a plain-English alex-inbox note naming the five,
**not** a loosened index. D42 was due today. The note already existed —
`alex-inbox/lane1-059-the-unique-index-that-stops-this-coming-back.md` — and it asked for a letter
on **8** groups while telling Alex *"production is still at 196 contested ids / 430 rows."* A
person acting on it this morning would have been acting on Wednesday's numbers.

So I **appended a dated update rather than filing a 260th inbox file**, with the set measured live:

**5 contested ids, 11 rows.** And each is now legible in one line, which turns one blind letter
into five quick calls:

| ESPN id | the rows | what it needs |
|---|---|---|
| `401504210` | two **identical** rows — Toronto Argonauts @ Winnipeg Blue Bombers, same kickoff, Nov 2022 | nothing to judge; ESPN no longer answers for a 2022 CFL game |
| `401873756` | 3 rows on one Oklahoma NCAA baseball game — two same fixture at different times, one with a different away team (Gonzaga) | which away team |
| `401856258` | Cal State Fullerton @ UC **Riverside** vs Cal State Fullerton @ UC **Irvine** | which home team |
| `401869643` | Arkansas-Little Rock @ Eastern Illinois vs Eastern Illinois @ **TBD** | the TBD row is a placeholder |
| `748503` | Oviedo @ Real Madrid **May 14** vs the same fixture **May 3** | which date |

This matches the restock's classification exactly: three `NO_ROW_AGREES` (`748503`, `401856258`,
`401869643`) and two stable `AUTHORITY_UNAVAILABLE` (`401504210`, `401873756`). My recommendation
in the note is **B scoped to these five only** — un-anchor 11 rows so the index can install, then
re-anchor whatever ESPN will confirm; reversible, nothing deleted. Option A was "leave them, the
index lands in a few days"; those days have passed, and two of the five structurally cannot clear
themselves.

**The note leads its warning in Alex's language**, because this is the thing most likely to be
misread: **"5" does not mean the double-listings are nearly gone.** The drain's only write is
`SET espn_id = NULL`, so every id it cleared left an *anchorless* duplicate row that is invisible
to this count by construction. Cardinals and Dodgers still render twice. Removing the second row is
#2693 step two (#2737, #2914, #2866, #2736) and is not what that note asks about.

---

## 8. Filed / not re-filed

- **#2447** — league-page evidence added. Not claimed. `program:ux`.
- **#2983** — carries the amended night-two prediction and the night-four table. Untouched.
- **#2878**, **#2978**, **#2980**, **#2964**, **#2957**, **#2737**, **#2693**, **#2644**, **#2741**
  — unchanged, not re-filed. #2878 stays **FILED, NOT FIXED** under D35 while #2693 is open.

## 9. Traps this session added

- **`git checkout -b <new> origin/master` reverts your working tree to master's copy of files your
  unpushed branch had changed.** Harmless here — the commit was already on a pushed ref — but if
  the work had been uncommitted it would have vanished silently. Push the branch *before*
  switching, which is what saved it.
- **`string_agg(..., ' ;; ')` is refused by db-query as `Multi-statement queries not allowed`.**
  The separator is a literal inside the SQL and the guard does not care. Use ` ~~ `.
- **Do not `grep status` the integrator lock file.** It is an append-only ledger of every historic
  release note; that grep returned ~15k characters of 2026-08 history. The live header is the first
  five lines — `head -5`.
- **A cert-granted sha freezes its branch, but a fresh branch cut from that sha does not strand
  the token** — the granted sha stays a parent verbatim, and once master merges it `--no-ff` the
  child branch's only new content is your commit. No rebase needed. That is why item 3 could be
  built during the wait instead of after it.
- **`look.sh` at `SHOT_W=390` still returns a 780px-wide image** (2× DPR) and here 13,800px tall.
  Crop with PIL before `Read`, and crop in bands — the card you want is rarely in the first band.
- Standing and still true: `cd backend && …` persists into later Bash calls; `search_files` MCP
  fails on this repo, use `grep`; `mkdir` for a new artifacts subdirectory is silently virtualized,
  so write into `artifacts/` root with a prefixed name; a fresh worktree has no `node_modules` so
  `npm run build` exits 127 — take frontend gates from CI; run `scan_mutation_residue.py` from
  `backend/` before every push.

## 10. Don't rebuild these

Unchanged from 096 §9, and one addition inside the sentinel: **do not implement ordered
(strictly-ahead) marker acceptance** — §1 has the reachable counterexample. Also still: do not
touch `_load_continuation` / `_save_continuation`; do not clear the continuation on pass expiry;
do not weaken `green = complete and not pass_drift_seen`; do not re-add the replay fallback;
`publish_snapshot_in_txn` must never commit or roll back; `UNDO_SCHEMA` is not bumped.
