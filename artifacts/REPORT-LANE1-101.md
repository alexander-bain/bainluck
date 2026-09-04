# REPORT — lane1/101

**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1.**
Kickoff Thu 9/10 — **six days.**

Session ran Fri 2026-09-04, 03:22–03:3xam PT (10:22–10:3xZ). Verified with `date -u` before any
clock-dependent judgement.

**Outcome: a verify-and-hold session. Nothing built, nothing merged, nothing filed — all four
checklist items resolved to "someone else owns this" or "not due yet".** The one piece of new
evidence is a D48 mystery-shop that puts both duplicates on the live production page at phone width.

---

## 1. Night two — NOT due. Correctly not read, nothing filed.

`date -u` → `2026-09-04T10:22:48Z`. Night two lands `2026-09-05T06:40Z` — **20 hours out.**
Third session in a row where the clock-first rule prevented a false P1. I did not call the
task-metrics endpoint at all; a reading now could only have returned night one
(`2026-09-04T06:40:40Z`), which is baseline, not a finding.

Note for 102: the 100 brief stamped its own restock "~03:5xam PT", but CERT-906 was graded at
10:04Z = 03:04 PT and this session opened at 03:22 PT. The `~03:5x` stamp was ~30–45 min fast.
Notice 24 again — **read `date` before stamping.** I have stamped this report from `date` output.

## 2. CERT-906 — still merge-queued, integrator healthy. Not touched.

`159-merge-047f57badad1306e99afecc9f78497be5df43e51.md` is present and **bare** — no `.running`,
no `.consumed`. `merge-base --is-ancestor` → **NOT-ON-MASTER**. I did not merge, re-stage, or write
a second directive.

Per the §8 trap ("an item passed over while later items are consumed is not a skip") I read
`runner-logs/integrator-20260904-031445.log` rather than escalate. The integrator is **working, not
wedged**: it consumed 155 at 03:09, is mid-flight on 156 (`.running`), and is currently blocked on
`LANE-integrator.lock` held by ux/1064 for a self-merge (pid alive, claimed 03:11). It is preparing
156's merge in a detached worktree at `/tmp/int156-cert905` while it waits, and has pushed
`integrator/156-cert905-merge` to get CI on the exact tree it intends to push. 159 sits behind
157/158. **Nothing to escalate.**

I did not implement ordered (strictly-ahead) marker acceptance. No grader raised it.

## 3. Week 1 — **18**. Destructive line held for the 11th session.

Branched on `'rows' not in d` first, per the brief. Count is 18, unchanged; the two phantoms are
`14780595` (SF@LAC, carrying SF@LAR's clock) and `14781140` (ARI@LAR, carrying ARI@LAC's clock).

Alex has not run DO 1. **I did not run the repair and did not build around the gate** — the generic
rail `POST /api/admin/repairs/{name}` remains a real bypass (gated on `_check_admin_secret` only) and
remains refused, now by sessions 091–101. I did not write another note and did not edit
`YOUR-TURN.md`.

The dry-run URL corrected by 100 (POST, with `/events/` in the path) was not re-run — 100 verified
the repair is still exactly right (`agrees=18 authority_moves_us=2 teams_disagree=0`) seven minutes
before this session opened, and re-running it would be measurement with no ship waiting on it.

## 4. D48 mystery-shop — **both duplicates are live and user-visible.** (the session's one new thing)

Production moved since 099's LOOK: master `3a1e6c9f` → `75dabbc2`, and `/api/health` confirms
**`75dabbc2` is deployed.** Two merges landed in between, one of them lane1's own (CERT-898,
window-pass marker) plus CERT-902 (economics). A surface in my domain changed underneath me, so the
LOOK was warranted rather than skippable.

`SHOT_W=390 tools/look.sh https://bainluck.com/sports/americanfootball_nfl`
→ `artifacts/lane1-101-nfl-week1-both-la-duplicates-phone.png` (780×9052).

**Both phantoms are on the page, and each is adjacent to the game it stole its clock from:**

| slot | real game | phantom directly beside it |
|---|---|---|
| Sep 10 5:35 PM | LA **Rams** v SF 49ers — 65/35 | LA **Chargers** v SF 49ers — 57/43 |
| Sep 13 1:25 PM | LA **Rams** v Arizona — 86/14 | LA **Chargers** v Arizona — 83/17 |

A 49ers fan scrolling the league page sees their team kick off twice in the same minute. That is the
ship, photographed.

**New corroborating detail:** each phantom carries **its own distinct win probabilities** (65/35 vs
57/43; 86/14 vs 83/17). These are not one row rendered twice — they are two independently scored,
fully-populated events, which is what §5's "real ESPN events with the wrong date" predicts. It also
means the user is shown two different numbers for what looks like the same fixture.

Page count reconciles: header "Upcoming 19" / footer "Showing 19 events" = my 18 in-window rows plus
one Week-2 game (Bills@Lions, Sep 17), which is outside the 9/9–9/16 query window. **No discrepancy.**
Bills and Lions each appearing twice on the page is Week 1 + Week 2, not a duplicate.

No new regressions seen: crests render on every NFL card, probabilities are present and sum to 100,
no empty or flat cards, broadcast tags (NBC/Netflix/CBS/FOX/ABC) populated throughout.

## 5. #2869 — deliberately NOT commented on.

Still **OPEN, p1, `needs-agent`, `matching-symptom`, unassigned**. Held under D35 (file, don't fix,
until #2693 lands). I confirmed its state but added no comment, on judgement:

- lane1/100 commented at **10:15Z, seven minutes before this session opened**, with the dry-run
  receipt; the authority lane confirmed the LOOK at 1:12pm PT 9/3.
- My probability observation **corroborates** the issue body's existing claim ("real ESPN events with
  correct ids and teams and the wrong date") rather than adding to it.

A fourth "still there" comment in 21 hours is noise on an issue whose diagnosis is already complete
and whose only blocker is an attended command. The brief's "do not write another note" applies.
The screenshot is banked here if #2869 ever needs the receipt.

## 6. Not done, and why

- **Did not chase which rail wrote the bad clock.** §5 flags `commence_time_source = 'espn'` as false
  on both phantoms — something copied a sibling's clock and signed ESPN's name. That is untraced and
  unowned, but it is *diagnosis*, which LANE ROLES assigns to the measurement lane, and D35 holds it
  besides. Parked, not dropped.
- **Did not run the anchor drain** (§7). Clearing a contested id only does `SET espn_id = NULL`, which
  converts an `AGREES_TWIN` into an invisible anchorless twin. `contested_ids: 5` still does not mean
  twins are nearly gone.
- **Did not loosen the unique index** (D42) and wrote no second note; `alex-inbox/lane1-059-…` still
  recommends B scoped to the five live ids and still waits on Alex's letter.

## 7. Owed by 101

**Nothing.** Two things in flight, both owned elsewhere: CERT-906's merge (integrator 159) and
DO 1 (Alex).

**Unowned hazard, unchanged and still just noted:** the sentinel is live 06:40Z–~06:46Z and under D45
every master merge cycles `worker-heavy`, killing a running beat. A merge deploying inside that window
kills night two and slides #2978's close by a day. Tell the integrator only if a night comes back
missing.
