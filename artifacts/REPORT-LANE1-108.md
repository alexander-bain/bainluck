# REPORT — lane1/108

**Stamped from `date`:** Fri 2026-09-04, session ran **11:05Z → 11:20Z** (04:05am → 04:20am PT).
**PILLAR: TRUTH. SHIP: a 49ers fan stops seeing their team play twice in Week 1.** Kickoff Thu 9/10 — **six days.**

## Verdict in one line

Night two still not due (held for the **tenth** consecutive session); **PR 3006 merged and deployed** —
master `1175d3ae`, production confirmed on it; **Week 1 is still 18** (line held, **18th** session); LOOK
re-shot on the new sha and the ship is unchanged. Nothing shipped by this lane.

---

## 1. Night two — correctly NOT read

`date -u` at session start: **2026-09-04T11:05:52Z**. Night two is readable from ~06:47Z **Saturday
9/5** — **19h 41m out**. Did not poll `anchor_schedule_sentinel`, did not file, did not touch #2983.

Tenth consecutive session in which the clock-first rule prevented a false finding. §1.1's grading table
is **still unused** and is carried into 109 verbatim.

## 2. PR 3006 — merged, deployed, verified, closed

Merged **11:02:45Z**, 3 minutes before I read it.

| check | result |
|---|---|
| `gh pr view 3006` | `MERGED 2026-09-04T11:02:45Z integrator/156-batch-904-906` → merge commit `1175d3ae` |
| CERT-904 `550b3e58` ancestor of `origin/master` | **ON-MASTER** |
| CERT-906 `047f57ba` ancestor of `origin/master` | **ON-MASTER** |
| directives 157 + 159 | both `.consumed-20260904-1152-…-MERGED-1175d3ae-batched-deployed` |
| ledger | MERGED row banked at `CODEX-CERT-LOG.md:662`, appended not edited (notice 12) |

**Deploy verified by polling, not inferred.** Production served `115dcc07` at 11:07, 11:09 and 11:10Z,
then `1175d3ae` at **11:12:30Z**. The integrator's own row also verifies it via `/api/health`.

I merged nothing and re-staged nothing. Both merge gates (13 + 18) were run twice by the integrator per
its row; I had no merge to run them for.

**Ordered (strictly-ahead) marker acceptance was NOT implemented** — 098's counterexample stands.

## 3. Week 1 — still 18. Destructive line held for the 18th session.

Count query returned **18** rows (branched on `'rows' not in d` first, per the trap). Both phantoms
present and byte-identical to every prior reading:

| id | matchup | espn_id | stored clock | belongs | clock stolen from |
|---|---|---|---|---|---|
| `14780595` | SF @ LA **Chargers** | `401873124` | `2026-09-11 00:35:00+00` | 2026-12-18 | SF@LAR (`14632820`) |
| `14781140` | ARI @ LA **Rams** | `401873004` | `2026-09-13 20:25:00+00` | 2026-10-18 | ARI@LAC (`14780147`) |

Did **not** run the attended repair. Did **not** use the `POST /api/admin/repairs/{name}` bypass. Did
**not** re-run the dry run (100's receipt stands; count unchanged). Did not write a second Alex note —
the ask is `YOUR-TURN.md` DO 1 and it is already there.

## 4. LOOK (D48) — re-shot, because production moved

Production left `115dcc07`, so the shot was owed. `SHOT_W=390`
`https://bainluck.com/sports/americanfootball_nfl` on **`1175d3ae`** → `/tmp/look-1788520366.png`,
780×9052, all 7 bands read plus a crop at `(0, 3650, 780, 4560)`.

**The ship is unchanged. Neither 904 nor 906 altered this page — which is the expected result, so there
is no finding here.**

| slot | real game | phantom directly beside it |
|---|---|---|
| Sep 10 5:35 PM | LA **Rams** v SF 49ers — 65/35, Proj 26-22, Netflix | LA **Chargers** v SF 49ers — 57/43, Proj 25-23, Netflix |
| Sep 13 1:25 PM | LA **Chargers** v Arizona — 82/**18**, Proj 29-18, CBS | LA **Rams** v Arizona — 86/**14**, **no Proj line**, CBS |

### Two corrections to 104's table — carry these, don't re-derive them

1. **104's Sep 13 row had real and phantom swapped.** Its table named LAR v ARI as the real game and
   LAC v ARI as the phantom. The DB is authoritative and says the opposite: `14780147` (ARI @ LA
   **Chargers**, espn_id `401872926`) is the real Week 1 game; `14781140` (ARI @ LA **Rams**, espn_id
   `401873004`) is the phantom that belongs on 2026-10-18. This queue's own §3 table was already correct;
   only the §4 photograph table was wrong. Production matches the DB.
2. **The Sep 13 phantom carries no Proj line** — its footer row is bare except `CBS`. 104's prose said
   every phantom carries "its own distinct win probabilities, Proj line and broadcast tag"; that holds
   for the Sep 10 phantom (Proj 25-23) but not this one. Likely 104 could not see the row under the nav
   overlay. Not a regression, just a detail 109 should not be surprised by.

Probability drift since 104 is ordinary market movement, not a change of state: ARI@LAC 83/17 → 82/18.
The phantom LAR v ARI reads 86/14, identical to 104 and 101.

**No regressions:** crests on every card, every pair sums to 100, no flat or empty cards, broadcast tags
populated (NBC/Netflix/CBS/FOX/ABC), footer intact. Footer reads **"Showing 19 events"** = 18 in-window
+ Bills@Lions Sep 17 (Week 2, outside the query window) — **not a discrepancy**, same as 104.

**Known capture limitation reproduced exactly:** the fixed bottom nav is baked in at y≈4290–4400 and hid
the top team row of the Sep 13 ARI@LAC card. Arizona's 18% and `Proj 29-18 / CBS` are visible and the DB
row names the opponent. Crop `(0, 3650, 780, 4560)`. Don't re-chase it.

## 5. #2869 — stayed silent, eighth consecutive session

Nothing to add that the issue does not already say. "It survived another deploy" is **not** new, and
`1175d3ae` touches nothing on this path. The rail that wrote the false `commence_time_source='espn'`
stamp is still untraced and unowned — and it is **diagnosis**, which LANE ROLES gives to the measurement
lane. Parked, not chased.

## 6. New for 109 — the stamp drift got worse

107 caught the integrator banking a row ~5 minutes fast. **Tonight it was ~40 minutes fast in the
future.** Its MERGED row is stamped `2026-09-04 11:52Z` and its note text says "at 04:50 PDT"; the merge
actually landed at **11:02:45Z** and the deploy at **11:12:30Z**, with the true clock at **11:15Z** when
I read the row. The error is internally consistent (a fast clock, not a PT/UTC conversion slip).

Consequence for 109, and it is the same rule as ever, only sharper: **never use another lane's stamp —
including a banked ledger row's — as a clock.** Read `date` (notice 24). A ledger row stamped in the
future is not evidence of a future event.

## 7. Everything else

Filed-not-refiled, unchanged: #2447 (not lane1's), #2983, #2878, #2978, #2980, #2964, #2957, #2737,
#2693, #2644, #2741, #2869. Don't-rebuild list unchanged. Twin-drain reading unchanged — `contested_ids`
is not a twin count, and the drain was not re-run.

No code written, no branch pushed, no cert staged, no issue commented, no Alex-facing file touched.
