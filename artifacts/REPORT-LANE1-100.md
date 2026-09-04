# lane1/100 — CERT-906 graded GREEN and merge-queued; night two is not due yet; Week 1 still 18

Session: Fri 2026-09-04, 03:04–03:5xam PT (10:04–10:5xZ). **PILLAR: TRUTH.**
**SHIP: a 49ers fan stops seeing their team play twice in Week 1.** Kickoff Thu 9/10 — six days.

Predecessor: `artifacts/REPORT-LANE1-099.md`. Every numbered section of the 100 brief is discharged.
**Nothing was built this session and nothing needed to be** — the one buildable item was already
owned by the integrator, and the ship's remaining step is an attended command only Alex may run.

---

## 1. Night two — NOT due. Nothing filed. (brief §1)

`date -u` at session start: **2026-09-04 10:04Z**. Night two begins **2026-09-05 06:40Z** — a little
over 20 hours out. Per §1 the visible sentinel run is still **night one** and is the baseline, not a
finding. I did not fetch the task-metrics endpoint, because the clock already settled the question
and a read could only have tempted a false reading.

This is the second session in a row to start ~1 minute after its predecessor's restock (099 restocked
~03:05am PT; this session began 03:04am PT). **The clock-first rule in §1 is what stopped a false P1
for the second time.** It stays at the top of the 101 brief.

**Relevant to grading night two, and new:** production has now caught up to master head.
`GET /api/health` read `7720bacd` at 10:04Z and **`3a1e6c9f` by 10:2xZ**. So night two will run the
new five-field code, and the "fields absent ⇒ did not deploy" escape hatch in §1.1 should NOT apply.
If the five fields are absent on night two, that is a finding, not a deploy artifact.

## 2. CERT-906 — GREEN, both merge gates pass, full CI green, integrator owns the merge (brief §2)

Graded while this session was running: **banked 10:04Z**, first presentation, strike zero.

> `CERT-906 -- LANE1-096-CONTINUATION-WRITE-FAILURE-REGRESSION` … **GREEN -- TOKEN GRANTED;
> EXACT-SHA FULL CI REQUIRED BEFORE MERGE** … Token granted for `047f57bada…`.

Merge gates, run with the anchored grep §7 warns about:

| gate | result |
|---|---|
| 13 — `grep <sha> … \| grep -q 'TOKEN GRANTED'` | **PASS** |
| 18 — `grep -inE 'supersedes:?[[:space:]]*\`?CERT-906\b'` | **PASS** (empty) |

The cert's condition is **satisfied**: `gh pr checks 3001` is green on the exact sha —
backend-tests shards 1–4, shard-completeness, frontend-build, CodeQL (both analyses), gitleaks,
search-recall, browser-audit fixtures. `deploy` shows `skipping`, which is normal for a PR.

**I did not merge, and should not have.** The integrator/105 watcher had already written
`runner-inbox/integrator/159-merge-047f57bada….md` at 03:09 PDT. Item 159 is pending behind 156
(`.running`), 157 and 158. One owner per merge — leaving it.

### A misread I caught, worth carrying forward

`git diff --stat 3a1e6c9f..047f57ba` prints **69 files / 357 insertions / 10,495 deletions** — it
looks like the branch rips out the tournament hub, the esports repair scripts and the NFL StatPal
stamper. It does not. The branch is **behind** master, and a **two-dot diff is a TREE comparison**,
so master's newer work is rendered as deletions on the branch side.

What the branch actually adds:

```
git diff --stat 3a1e6c9f...047f57ba          # three-dot, from the merge-base
 backend/tests/test_anchor_schedule_sentinel.py | 106 +++++++++++++++++++++++++
 1 file changed, 106 insertions(+)
```

One file, tests only, zero source lines — exactly what the cert describes. `git merge-tree` from the
merge-base projects **0 conflict markers**. This is the existing "two-dot TREE" hazard biting on a
*behind-master* branch rather than a rebased one; the fix is the same — **three dots, always**.

## 3. Week 1 — still 18. The line held, and the repair is verified still-correct. (brief §3)

Counted with the `if 'rows' not in d` branch first, per §3:

**18 rows.** Alex has not run the attended command. Per §3 I did not run it and did not route around
`_check_admin_destructive`. Confirmed from source that the gate is real and correctly placed:
`admin_events.py:606-608` calls `_check_admin_secret` always and `_check_admin_destructive` **only
when `apply=true`**, so the dry run is legitimately available to a lane and the write is not.

### The dry run reproduces the brief's expectation exactly — six days out

```
POST /api/admin/events/reconcile-anchor-schedule?sport=americanfootball_nfl&limit=20&apply=false

agrees=18  authority_moves_us=2  teams_disagree=0  no_answer=0
refused_completed=0 refused_settled=0 refused_statpal=0
examined=20/239  truncated=true  next_cursor=2026-09-20T17:00:00+00:00|14781131
```

| event_id | espn_id | ours | authority | delta |
|---|---|---|---|---|
| 14780595 | 401873124 | 2026-09-11T00:35Z | **2026-12-18T01:15Z** | 98.0 d |
| 14781140 | 401873004 | 2026-09-13T20:25Z | **2026-10-18T20:05Z** | 35.0 d |

Two things this settles for whoever watches Alex run it:

1. **`teams_disagree=0`** — the apply writes `commence_time` only. No identity column moves. It is
   the narrow fix, not a merge.
2. **`limit=20` is sufficient for the ship despite `truncated=true`.** The window is walked
   oldest-kickoff-first and page one already reaches 2026-09-20, so all of Week 1 is inside it. The
   219 unexamined rows are later kickoffs. **Do not read `truncated=true` as "the Week-1 fix is
   partial."** It isn't.

### ⚠ The brief's dry-run URL was wrong — Alex's is right

The 100 brief §3 gives `…/reconcile-anchor-schedule?sport=…` as a GET. That **404s**. The real route
is a **POST** at `/api/admin/**events**/reconcile-anchor-schedule` (`admin_events.py:550`).

I checked whether this had leaked into the Alex-facing ask, since a 404 on 9/9 would cost the ship.
**It has not.** `alex-inbox/lane1-091-…` line 41 carries the correct path and both commands are
POSTs. No note was written (§3 forbids a second one) and `YOUR-TURN.md` was not touched.
The corrected URL is in the 101 brief so the next session does not re-lose the minute.

## 4. #2869 — the cause is unowned; filed, not fixed (D35)

`#2869` (p1, `needs-agent`, `matching-symptom`, **unclaimed** — no CLAIMED comment) is the issue
behind this queue's ship, and it reframes the problem: **these are not duplicate rows.** Both
phantoms are real ESPN events with correct ids and correct teams, stamped with the wrong *date*.
ESPN and StatPal both agree our row is the outlier.

Filed to the issue as `#2869#issuecomment-5539017715` — the dry-run receipt above plus one new
observation. I did **not** claim it and did **not** build: D35 keeps matching symptoms filed while
#2693 is open, and the brief applies that same hold to this class.

**New evidence.** Each phantom's clock is *byte-identical* to its correct neighbour's, not merely
near it:

- `14780595` SF@**LAC** → `2026-09-11 00:35:00` = `14632820` SF@**LAR**'s kickoff exactly
- `14781140` ARI@**LAR** → `2026-09-13 20:25:00` = `14780147` ARI@**LAC**'s kickoff exactly

Both collisions are between the two Los Angeles clubs, and **all six rows carry
`commence_time_source = 'espn'`** — so on the phantoms that provenance stamp is **false**: ESPN's own
summary for those ids says December and October. Something took the clock from the *sibling* and
signed ESPN's name to it. That is a sharper form of the issue's own open question.

**A theory I checked and discarded — do not re-chase it.** I expected these rows to be permanently
unfixable under the parity rule in `commence_time_write_authorized` (`event_registry.py:82`: "a tie
loses", and `same_record` defaults to False, fail-closed). They are not.
`event_registry.py:376` does compute `claim_is_same_record(event, identity.claim)` and pass it, so an
exact-id ESPN claim **is** authorized to revise its own record. The freeze theory is wrong. I did not
trace which rail wrote the bad clock; that remains open and unowned.

## 5. D48 — deliberately not re-shot

The brief says explicitly: *"Do not re-shoot the NFL page just to confirm."* 099's LOOK is one hour
old (`#2737#issuecomment-5538273860`) and nothing shipped this session that could change a pixel.
Re-shooting would have been ritual, not evidence.

## 6. What is owed

**Nothing from this session.** Two things are in flight and both are owned elsewhere:

- **CERT-906's merge** — integrator item 159, pending. Not lane1's.
- **DO 1** — Alex's attended command. Verified still correct today.

The unique index (D42) still waits on Alex's letter; per §4 no second note was written.
