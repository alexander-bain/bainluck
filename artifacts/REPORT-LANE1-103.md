# REPORT — lane1/103

**Stamped from `date`:** Fri 2026-09-04 **03:36am PT / 10:36Z**.
**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1** (kickoff Thu 9/10 — six days).

**Outcome: held the line. Nothing shipped, nothing filed, nothing escalated.** Fifth consecutive
session where every gate read "not due / not mine / still 18". One genuinely new fact for 104: master
moved during this session.

---

## 1. Clock first — night two is 20 hours out

`date -u` → **2026-09-04T10:35Z**. Night two lands **2026-09-05T06:40Z**. Not due.
**No sentinel poll made. No P1 filed.** Fifth session running where reading the clock first prevented
a false finding.

The §1.1 grading table in the 103 brief is **still unused** and carries forward to 104 intact — including
the point that the deploy escape hatch is closed (see §4 below for the one change to that reasoning).

## 2. CERT-906 — still queued, behind a demonstrably healthy integrator

- Directive `159-merge-047f57ba…md` is **bare** (not `.running`, not `.consumed`) → the integrator owns
  it. **Left alone.** No self-merge, no re-stage, no second directive, no escalation.
- `merge-base --is-ancestor 047f57ba… origin/master` → **NOT-ON-MASTER**.

**Read the integrator's log before judging** (the rule 101 and 102 both proved, and it paid again).
`integrator-20260904-031445.log`, **last written 03:36 — one minute before I read it.** The lane is not
stalled; it is mid-flight and working:

1. was blocked on the lane lock held by ux/1064, and prepared the CERT-905 merge (`d6ed5167`) in
   `/tmp/int156-cert905` while waiting;
2. found PR 2994's merge ref stale against a moved base, so pushed the exact intended tree as
   `integrator/156-cert905-merge` and opened PR 3003 → **15/15 green on the exact tree**;
3. claimed the lock, **re-ran merge gates 13 and 18** immediately before pushing (correct — a token can
   be superseded after the fact), pushed as **`115dcc07`**, and is now waiting on master CI + deploy.

906 sits behind 156/157/158 in a queue that is visibly draining. Nothing to escalate.

⚠ Carried forward: **do not implement ordered (strictly-ahead) marker acceptance** if a grader suggests
it — 098's counterexample is in the arm's docstring (`restarted_from_exhausted_cursor` walks the position
backwards, so a "ahead"-looking marker can be a stale claim missing that night's drift).

## 3. Week 1 — still 18. Destructive line held for the 13th session.

Counted with the `'rows' not in d` branch first (a failed db-query has no `rows` key and would print a
confident `0`). **`COUNT = 18`.** Both phantoms present, unchanged and adjacent to their real twins:

| id | row | commence_time | espn_id |
|---|---|---|---|
| `14632820` | SF 49ers @ **LA Rams** | 2026-09-11 00:35Z | 401872657 |
| **`14780595`** | SF 49ers @ **LA Chargers** ← phantom, belongs 2026-12-18 | 2026-09-11 00:35Z | 401873124 |
| **`14781140`** | Arizona @ **LA Rams** ← phantom, belongs 2026-10-18 | 2026-09-13 20:25Z | 401873004 |
| `14780147` | Arizona @ **LA Chargers** | 2026-09-13 20:25Z | 401872926 |

Each phantom's clock is byte-identical to its correct neighbour's. Both collisions are between the two
Los Angeles clubs. This matches 099/100/101/102 exactly — **the count has not moved.**

**18 means Alex has not run the apply.** Per the brief: did not run it, and did **not** build a way
around the gate. The generic rail `POST /api/admin/repairs/{name}` is gated on `_check_admin_secret`
only and IS a real bypass — **refused again**, as 091–102 refused it. The ask already sits in
`YOUR-TURN.md` DO 1; I did not write another note and did not edit that file.

**Dry run NOT re-run.** 100 ran it at 10:1xZ on 9/4 (`agrees=18 authority_moves_us=2 teams_disagree=0`);
102 confirmed the count unchanged; I confirmed it unchanged again. Re-running is measurement with
nothing waiting to spend it (CLAUDE.md: *a measurement is not progress*).

## 4. D48 — no shot burned, but **master moved and 104 will need one**

`GET /api/health` → **`75dabbc2`**, the same sha 101 photographed, and I shipped nothing → the existing
PNG (`artifacts/lane1-101-nfl-week1-both-la-duplicates-phone.png`) is current evidence. **No shot burned.**

**NEW THIS SESSION:** `origin/master` is now **`115dcc07`** (the integrator's CERT-905 merge, landed
~03:3xam PT while I was reading). Production was still serving `75dabbc2` at 10:36Z with that deploy in
flight. So:

- **104 will very likely find production at `115dcc07` or later** and must re-shoot
  `/sports/americanfootball_nfl` at `SHOT_W=390`, diffing against 101's PNG.
- The §1.1 line "production has been at `75dabbc2` since before 101" is now **superseded**. The
  substance is unchanged — night two still runs the new code, since the five window-pass fields shipped
  in `3a1e6c9f`/`75dabbc2`, both of which are ancestors of `115dcc07`. **The escape hatch is still
  closed;** just confirm the live `commit` before judging rather than expecting the literal string
  `75dabbc2`.
- CERT-905's merge landed at ~10:3xZ, far outside the sentinel's 06:40Z–06:46Z live window, so it poses
  no D45 risk to night two.

## 5. #2869 — not commented on

Nothing to add that the issue does not already say. 099, 100 and the authority lane have each already
recorded "still there"; a fourth would be noise. The untraced question — which rail copied a sibling's
clock and stamped `commence_time_source = 'espn'` on it — is **diagnosis**, which LANE ROLES assigns to
the measurement lane. Parked, not chased.

## 6. Nothing else touched

No issues filed or re-filed (#2447, #2983, #2878, #2978, #2980, #2964, #2957, #2737, #2693, #2644,
#2741, #2869 all unchanged). No cert staged. No drain re-run (§7 of the 103 brief still governs:
clearing a contested id only writes `SET espn_id = NULL`, producing anchorless twins invisible to the
collision repair — `contested_ids: 5` does not mean twins are nearly gone).

**An idle build lane is a signal, not a failure.** No census invented to look busy.

## 7. New trap learned

**A `merge-base --is-ancestor` answer and an integrator log tail are worth more together than either
alone.** NOT-ON-MASTER plus a bare directive looks identical to a stall; the log timestamp (written one
minute earlier) is what distinguishes "wedged" from "working". Check the log's **mtime**, not just its
contents — a healthy lane writes continuously.
