# lane1/114 — the espn_id unique index is on production, and Week 1 is 16

**PILLAR: TRUTH.** **SHIP: a 49ers fan stops seeing their team play twice in Week 1, and one game
can never again be stored under another game's ESPN id.** Both halves are live as of today.

Session: Fri 2026-09-04, 10:11am–11:2xam PT (17:11Z–18:2xZ), stamped from `date`.
Directive consumed: `runner-inbox/lane1/114-the-index-is-armed-and-waiting-on-one-word.md`.

---

## 0. One line

Alex said "go 2776" at 10:11am; the branch was rebased (master had moved and the new master
carried the exact hazard class that failed this branch once already), full CI re-run green, merged
at `cf4dba68` under the four-line attended release, and **`uq_events_espn_id` is verified present
on production from the database's own catalog** — not from the deploy's exit code, which #2741
makes worthless. Week 1 is **16 games, every franchise exactly once**.

## 1. The clock said skip §1

`date -u` → `2026-09-04T17:11Z`. Night two of the anchor-schedule sentinel is not readable until
Sat 9/5 after ~06:47Z. **Nothing filed about it.** The night-one baseline
(`2026-09-04T06:40:40.341420+00:00`, `terminal: partial`, `stopped_by: deadline`) is unchanged and
is not a finding. §1.1 of directive 114 carries forward to 115+ verbatim — it has now gone
unused by sessions 101 through 114 and must not be trimmed on that account.

## 2. The GO, and what it authorised

`.claude/handoff/ALEX-GO-2776.md`, Alex in Cowork/Fable-5, 10:11am PT. Verbatim: *"I think I'm
supposed to say 'go 2776'"*, taken as go under D42=A's Friday clause. It authorises **lane1** —
not the integrator — to merge #2776 and run its own release, because the release is not a push:
it is a four-step dance around the background beat that a conveyor merge would not know to do.

Merge gate 13 (`grep <sha> CODEX-CERT-LOG.md | grep -q 'TOKEN GRANTED'`) returns **nothing for
2776** — this sha never went to the bus. That is correct and not a bypass: D45 puts
migration-class shas under Alex's attendance *instead of* the bus, and the GO file is the token.
Recorded here explicitly so a later reader does not have to reconstruct why the ledger is silent.

## 3. The rebase — the part that was not in the plan, and was the real work

Directive 114 §2 said "re-check it is still green before any merge — master moves." It had moved
further than a re-check covers.

Graded sha `fdd5e354` sat on base `b53a8224`. Master was at `e1a0de7c` — **19 commits ahead**, and
the diff carried **six new backend test files**. That is precisely the class that failed this
branch's first CI run: `test_anchor_schedule_sentinel.py`'s fixture helper gave every row
`espn_id="401"`, and the index this branch installs turns that into an `IntegrityError`. A test
file written while a branch is parked cannot be found by local focused tests.

So: rebase, not a re-check.

| check on the new master | result |
|---|---|
| `backend/alembic/` files changed since `b53a8224` | **0** → single head preserved |
| `alembic heads` after rebase | `uq_event_espn_id (head)`, single |
| new test files mentioning `espn_id` | **0 of 7** |
| `models.py` touched by master | no → no conflict with this diff |

Rebased 7 commits cleanly → `a12e803a`. Focused gates locally (D40 — CI is the suite of record):
`test_uq_event_espn_id_migration.py` + `test_anchor_schedule_sentinel.py` + `test_startup.py`,
**59 passed, exit 0**. Residue scan **CLEAN, 0 residual mutants** (550 needles, 1688 broad checks).
Force-pushed with `--force-with-lease`.

**Full CI green at `a12e803a`:** 4/4 backend shards, `frontend-build`, `search-recall`,
`shard-completeness`, browser-audit fixtures, CodeQL (both analyses), gitleaks, Vercel.
`deploy` SKIPPED — correct on a PR. `mergeStateStatus: CLEAN`.

Then master moved **again** while I waited for the lock (four more integrator merges,
`e1a0de7c` → `f1f55d30`, 16 commits). I did **not** re-rebase. The judgment, written down because
it is the kind of call that should be auditable: the gate protects against exactly three
interactions, all checkable in seconds, and all three were clean — **0 alembic changes**, **0 of
the newly-merged test files mention `espn_id`**, **no `models.py` conflict**. Re-rebasing would
have cost another ~11-minute CI cycle and handed the lock back to a conveyor that had 177 queued,
i.e. an unbounded treadmill. The green at `a12e803a` covers the risk the gate exists for.

## 4. The lock — 27 minutes of waiting, and the one thing that made it safe

`LANE-integrator.lock` was **HELD** by `integrator-172-27311`, owner pid 9191, taken 10:14 PDT for
a four-branch batch. Ruling 008 pid-alive test: **alive** (started 10:12). Not a dead claim, not a
takeover candidate. So: wait.

Waiting blind for an unknown duration is how a session dies holding nothing, so before polling I
wrote `runner-inbox/integrator/178-yield-the-lock-lane1-has-an-attended-migration.md` — the
authorization, the sha, the four steps, why a merge landing *inside* the window is dangerous (it
cycles `worker-heavy` under D45 and #2782 already turned a clean `LockNotAvailable` into a fatal
`DeadlockDetected` once), and the full runnable sequence in case my window ended first.

**The integrator honoured it.** They released at 10:40 and marked 178
`consumed-…-honored-never-claimed`, holding off 177 until I was done. Worth recording as a working
pattern: a lane that needs the integrator's lock for an attended operation should write the inbox
note *before* it starts polling, not after it gives up.

Claimed 10:41 via `scripts/claim_lane_lock.py claim` (ruling 022's only sanctioned primitive),
identity `lane1-114-69312`. Released 10:59. **Held 18 minutes.**

## 5. The release — four steps, each with its own evidence

| Zulu | step | evidence |
|---|---|---|
| 17:41 | pre-check re-run | `CONTESTED espn_ids: 0` |
| 17:41 | formation recorded before touching it | `scheduler=1`, `worker-heavy=1` |
| 17:42 | `heroku ps:scale scheduler=0 worker-heavy=0 -a bainluck` | *"now running scheduler at 0, worker-heavy at 0"* |
| 17:43 | wait 75s, then `events` lock check | **0** non-`AccessShareLock` locks |
| 17:44 | merge | `cf4dba68` |
| 17:57 | master CI `deploy` job | success (all 8 jobs + deploy) |
| 17:57 | **the index is really there** | see §6 |
| 17:58 | `heroku ps:scale scheduler=1 worker-heavy=1` | scheduler.1 + worker-heavy.1 up |

**The beat was down 16 minutes, not the ~2 I predicted to the integrator.** Cause: on Heroku the
migration runs in the *release phase*, which is gated behind the serialized `deploy` job, which is
gated behind 4 backend shards — so "merge" to "migration applied" is a full CI cycle, and the beat
must stay down across all of it. Anyone planning this dance again should budget **~15 minutes of
beat-down, not two**, and say so up front. `web` stayed up throughout; the site served normally.

**One snag, worth 30 seconds of anyone's time:** `gh pr merge` refused with
`GraphQL: Pull Request is still a draft`. #2776 had been left in draft while it waited for Alex.
`gh pr ready 2776` first, then merge. The scale-down had already happened, so the draft state cost
20 seconds of beat-down for nothing — **take a PR out of draft before you stop the writers.**

## 6. The verification that actually matters

#2741: `backend/Procfile` wraps `alembic upgrade heads` in `|| echo`. A raising migration is
swallowed and the deploy reports success. **`deploy: completed/success` is therefore not evidence
that the migration ran.** Asked the database instead:

```
uq_events_espn_id | CREATE UNIQUE INDEX uq_events_espn_id ON public.events
                    USING btree (espn_id) WHERE (espn_id IS NOT NULL)
pg_index          | indisunique = True, indpred IS NOT NULL = True
alembic_version   | uq_event_espn_id
ix_events_espn_id | ABSENT
contested espn_ids| 0
```

Four independent things, each of which would have caught a different failure:

- the **index exists** and is `UNIQUE` — the invariant is enforced, not merely intended;
- it is **partial** on `espn_id IS NOT NULL` — the shape the migration specifies, and **not
  loosened**. D42 is intact: the answer to a non-zero pre-check is to find the writer, never to
  widen the index with a `WHERE`;
- `alembic_version` is **stamped** `uq_event_espn_id` — a swallowed raise would leave the previous
  revision, so this is the direct refutation of the #2741 failure mode;
- `ix_events_espn_id` is **gone**, dropped in the same step as designed — two btrees over one
  column would be one write amplification too many and would let a future reader conclude the
  column is unconstrained.

Memory says `exists ≠ usable` for indexes; here `indisunique`/`indpred` read from `pg_index`
settle the *constraint* question, which is the whole point of this index — it is installed to
refuse writes, not to speed reads.

## 7. Week 1 — the ship's user-visible half

Alex applied the phantom fix himself at 10:00am (Chargers–49ers → Dec 17, Rams–Cardinals → Oct 18;
`undo_identity repair:anchor_schedule:undo:20260904T165810.169Z:8a0fbbe5e643:92435e9fb6a9`).

**Counted from production, 17:2xZ: 16 rows.** All 16 `espn_id`s distinct, `401872656`–`401872931`.
Every one of the 32 franchises appears **exactly once**. `14780595` and `14781140` — the two
phantoms this lane has been counting since session 099 — are out of the window.

**LOOK, phone-shot before (17:2xZ) and after (18:0xZ) the ship**, per D48:

- header **"Upcoming 17"** / footer **"Showing 17 events"** = 16 Week-1 + Bills@Lions Sep 17
  (Week 2). Down from 19. **This is the §5 baseline arithmetic still holding, not a discrepancy** —
  the +1 is Week 2 and has been there all along.
- Sep 10 5:35 PM now holds **one** card: LA Rams 65% / SF 49ers 35%, Proj 26-22 (`14632820`, the
  real one). The phantom — LA Chargers 57% / SF 43% — is gone.
- Sep 13 1:25 PM now holds **one** Chargers card: LA Chargers 83% / ARI 17%, Proj 29-18
  (`14780147`, the real one). The phantom — LA Rams 86% / ARI 14%, no Proj — is gone.
  (Baseline said 82/18; it reads 83/17 today. Odds refreshed on the same event, not a different
  row. The Proj line is byte-identical.)
- **before vs after the ship: identical.** Same 17 cards, same probabilities, same Proj lines. The
  only difference is column ordering among same-kickoff games, which shuffles between renders.
  **Zero visible change is the correct outcome** — this ship is a database rule, and Alex was told
  nothing would look different.

The §5 note that 104 had the Sep 13 real/phantom swapped remains correct as written. Do not swap
it back. It is now moot for Week 1 but the discriminator (a phantom carries no Proj line) is the
reusable part.

## 8. What this closes and, more importantly, what it does not

**Closes the re-growth half of the ship.** The matcher can no longer mint a second row under a
live game's ESPN id — it gets an `IntegrityError` instead of quietly duplicating. That was the
whole point: the repair rail drained 196 contested ids down to 0 over three weeks, and without the
index the same matcher makes the same collisions again next week and the repair becomes a chore
instead of a fix.

**Does not close #2693** (durable matching: receipts, invariants, golden set) — receipt at
`#2693#issuecomment-5544521254`. Still open, still P1.

**Does not touch #2869.** The wrong-date phantoms are a different failure entirely: right id,
right teams, *wrong `commence_time`*. A unique index on `espn_id` is blind to it by construction.
Alex's manual fix moved those two rows; the mechanism that created them is unaddressed and stays
held under D35 until #2693 lands. **File, do not build.**

**Does not touch the two-rows-per-game population** — that is the merge work (#2737, #2914, #2866,
#2736), and #2866's data half is still unowned (32/32 NFL franchises have 2 `teams` rows, exactly
1 slugged).

**Residue, on record:** 11 rows / 5 groups that ESPN refused to adjudicate were unstamped under
D42's Friday clause and D51=B(b) rather than resolved. All finished fixtures, newest kicked off
2026-05-29. Backup and one-command restore: `artifacts/LANE1-113-UNSTAMP-BACKUP-2769.md`. Those 11
old finished games no longer link back to ESPN; nothing on the site shows it.

## 9. New traps

- **A graded sha rebased is a sha that must be re-graded against what it landed on, not just
  re-checked.** 113 left this branch green at `fdd5e354`; by the time Alex said go, master carried
  six new backend test files. The three interactions worth checking before deciding whether a
  rebase needs a full re-run: **alembic files** (head count), **new tests touching your column**,
  **your own changed files** (conflict). All three are one `git diff --name-only` and one grep.
- **Take the PR out of draft before you stop the writers.** `gh pr merge` refuses a draft with a
  GraphQL error, and by then the beat is already down.
- **"Merge" to "migration applied" is a full CI cycle on Heroku, ~13 minutes**, because the release
  phase is gated behind the serialized `deploy` job which is gated behind the shards. Budget
  **~15 minutes of beat-down** for a migration release, not the two the four-line recipe implies.
- **Write the integrator an inbox note BEFORE you start polling their lock, not after you give
  up.** It cost one file and the integrator yielded the lane and held their next merge. A note
  written after the window closes is archaeology; one written before is coordination.
- **A `heroku ps:scale` down is not complete until you have recorded what it was.** `heroku ps`
  first — the restore line has to come from a reading, not from memory of the usual formation.
- **`deploy: completed/success` proves the dyno restarted, never that the migration applied**
  (#2741). Read `alembic_version` and the catalog. Both, not either.

## 10. Carried forward unchanged

Everything in directive 114 §§1.1, 5, 6, 7, 8, 9 stands. Specifically still true and still not to
be redone: the sentinel night-two grading table; the LOOK baseline discriminator; #2869's "these
are not duplicate rows"; the do-not-rebuild list; and the whole trap list, of which the
still-load-bearing ones this session used again were *shell quoting mangles the db-query payload —
use a python file and branch on `'rows' not in d` first* (used four times today), *`gh` without
`--limit` reads 30 items silently*, and *`cd <path> && …` in one Bash call scopes every later git
command* (avoided by `git -C` and explicit `cd` in its own call).

**§3's pre-check is now enforced by the database.** It does not stop being worth running — the
index refuses new collisions, but a session should still know the number, and a **failure** to
insert is now the loud signal where a duplicate used to be the silent one. Watch for
`IntegrityError` on `uq_events_espn_id` in Sentry: that is a writer meeting the rule, and it names
the writer #2693 has been trying to find.
