# lane1/110 — the lane was not idle after all: CERT-853's repair was unblocked and nobody had noticed

**Session:** Fri 2026-09-04, 11:26Z → 11:58Z (04:26 → 04:58 PT). Stamped from `date`, twice.
**PILLAR: TRUTH.** **SHIP: a 49ers fan stops seeing their team play twice in Week 1.** Kickoff Thu
9/10 — **six days.**

## TL;DR

Nine consecutive sessions (101–109) correctly concluded "not due / not mine / still 18" and stopped.
This session found that conclusion was **incomplete**: PR **2900 (lane1/086)** has been sitting OPEN
and BLOCKed since 9/3 22:18Z, and **its blocking dependency cleared at 00:32Z this morning**. The
repair is built, gated, CI-green on the exact sha, and staged as **CERT-911** (`repairs: CERT-853`,
so it grades first).

Everything the brief asked for also held: night two not due, Week 1 still 18, the destructive line
held for the 20th session, and a LOOK re-shot because production moved mid-session.

---

## 1. The clock — night two NOT read (twelfth consecutive correct hold)

`date -u` at session start: **2026-09-04 11:26Z**. Night two is readable from ~06:47Z **Sat 9/5** —
**19h 21m out**. §1.1's grading table remains unused and is carried forward verbatim to 111.

Nothing polled, nothing filed, no false finding manufactured from night one's baseline.

## 2. The integrator — live and healthy, and its subject was again not ours

Log `integrator-20260904-041848.log`, mtime **11:25Z** against a session clock of 11:28Z — **3
minutes old**. Tenth consecutive session where "bare directive" looked like a stall and was a healthy
lane.

`d15e9b98…` / **CERT-907** was **self-merged by lane1b/032** while the integrator was still running
its gates; master became `e84e3f4e`. Both integrator directives 157 and 160 are `.consumed`. The
integrator has moved on to 161 (native-007, PR 2990). **Not lane1's; not touched, not gated, not
commented on.**

## 3. THE FINDING — a BLOCKed lane1 ship whose blocker cleared, sitting unclaimed for 13 hours

This is what nine sessions of "the lane is idle" missed, and it is worth stating plainly so 111 does
not repeat the shape of the error.

`gh pr list` surfaced **PR 2900 — lane1/086**, OPEN, head `a3663909`, last touched 9/3 22:07Z, **not
landed**. The ledger explains why:

* **CERT-853 (BLOCK, 2026-09-03 22:18Z)** withheld the token. Its named repair, verbatim: *"pass
  resolved `sport_id` into the direct-ID lookup, scope the StatPal query by `Event.sport_id`, and add
  the cross-sport full-cascade regression plus a same-sport control. **Restage after blocked
  dependency authority/003 is repaired**; ordering does not cure Step 1."*
* **CERT-857 (GREEN)** repaired authority/003 and **merged to master `24f15f1a` at 00:32Z today** —
  and that very row says the production apply *"remains gated on the separately blocked lane1/086
  caller repair."*

So the dependency cleared **eleven hours before this session started**, the repair was precisely
named, the file is explicitly lane1's under D39/D50 — and nobody picked it up. It was not on any
brief's radar because 099–109 were all pointed at night two, Week 1 and CERT-906.

**The lesson for 111, and it is the generalisable one:** "no open directive and no open PR awaiting
merge" is not the same as "no open work." A lane's own BLOCKed branch is invisible to
`gh pr list --author '@me'` triage because every lane shares the account, and invisible to the
integrator because a withheld token means it is not queued. **The only thing that surfaces it is
grepping the ledger for your own lane's BLOCK rows and re-checking whether their stated blockers have
since landed.**

### The defect

`_find_by_source_id` (Step 1 of the registry cascade) read
`WHERE statpal_fixture_id = :id` **across every sport**. Step 1 runs *before* the sport-qualified
anchor key at Step 2 — so an NFL claim for StatPal fixture `280445` was answered by the MLB row
carrying the same token, and `find_or_create_event` returned `created=False` before the qualified key
was ever derived. Qualifying Step 2 bought nothing while Step 1 answered first and answered globally.

### The repair — `d12caafa`

* `_find_by_source_id` takes `sport_id` as a **REQUIRED** argument. Optional would be the same
  dishonest bridge D55 removed from the anchor key: a caller gets the global lookup back by
  forgetting an argument. The two existing test callers were updated.
* The StatPal arm moved to `_find_statpal_row_in_sport`: fetch once → compare sport → **WARN** →
  miss.

**The judgement call, flagged for the grader rather than buried.** The named repair says "scope the
StatPal query by `Event.sport_id`" and I did **not** write `WHERE sport_id = :x`. I fetch and compare
in Python, for three reasons:

1. It is the refusal shape `find_event_by_anchor` **already** uses for this exact collision, so
   Step 1 and Step 2 now report a cross-sport id the same way instead of two different ways.
2. **D55 requires a collision to raise or tag and never to silently no-op.** A scoped predicate fixes
   the absorption and makes the incumbent row invisible in the same stroke — which is exactly how a
   twin nobody can see becomes a twin nobody fixes (the #2869 failure class).
3. It retires a latent crash: once NFL rows carry StatPal ids, an unscoped `scalar_one_or_none()`
   over a colliding token raises `MultipleResultsFound` on the registry's hot path.

Cost is one query either way. The cert block invites the bus to attack this specifically and says
what I would want a block to name if it disagrees.

**Only StatPal is scoped, deliberately.** ESPN and odds_api ids are single global id spaces; scoping
them would buy nothing and would turn a mis-sported row into a silent second create.
`test_espn_step_1_is_deliberately_not_sport_scoped` pins the asymmetry as a decision.

### The red arm, executed

Reverting **only** the Step 1 dispatch line — source restored afterwards and the marker's **absence
verified by grep, not assumed** — takes the new class to **2 failed / 10 passed at exit 1**, on
behaviour:

* `assert created` → `created=False` with the MLB row. CERT-853's exact reproduction.
* `assert len(receipts) == 1` → `0`. No D55 receipt at all.

**Both controls stayed GREEN in that arm** (gotcha #43): the owning sport still finds its row, ESPN
untouched. A repair that "passed" by breaking Step 1 outright would fail those two.

### The double had to change, and that is part of the finding

`_FakeRegistrySession`'s source-id branch returned **one row, always**. A cross-sport control written
against it **could not fail** — the identical defect CERT-853 itself named in `_AnchorSession`. Its
`source_matches` values now accept a list and it feeds `.scalars()`.

### Gates on the exact rebased sha `d12caafa`

* **364 passed / 58 xfailed, exit 0** across all 14 files importing `event_registry` plus the 2879
  namespace suite and startup. CERT-853's baseline was 360/58 — the four new tests are the delta.
* `compileall` exit 0. Mutation residue scan **CLEAN**, 0 residual mutants.
* Ruff: 3 F401s, all **pre-existing and byte-identical on master** (verified by running ruff against
  `origin/master`'s own copies) and deliberately left alone.
* **Full CI GREEN on `d12caafa`**: backend-tests 1–4, frontend-build, search-recall,
  shard-completeness, browser-audit fixtures, gitleaks ×2, CodeQL (python + js-ts), Vercel. `deploy`
  SKIPPED, correct for a PR.
* **Not migration-class**: zero `backend/alembic/` files; single head `link_change_history`.
* Rebased onto `e84e3f4e`, **0 behind**; `git merge-tree` returns 0 conflict markers.

Staged as **CERT-911** with `repairs: CERT-853` (grades first, notice 8b). Block verified to have
landed well-formed at the file end, no id collision. Repair note posted to PR 2900.

**Not merged.** Token not yet granted; gates 13 + 18 unrun because there is nothing to merge yet.

## 4. Week 1 — still 18, line held for the 20th session

Count query returned **18**. Alex has not run the apply. **Not run here, and no bypass used** — the
generic rail `POST /api/admin/repairs/{name}` remains a real bypass (gated on `_check_admin_secret`
only) and remains refused, now by 091–110. The ask stays `YOUR-TURN.md` DO 1; no second note written.

Both phantoms re-confirmed byte-for-byte, and the DB again corroborates §4's **corrected** assignment:

| id | matchup | espn_id | stored clock | belongs |
|---|---|---|---|---|
| `14780595` | SF @ LA **Chargers** | `401873124` | `2026-09-11 00:35:00+00` | 2026-12-18 |
| `14781140` | ARI @ LA **Rams** | `401873004` | `2026-09-13 20:25:00+00` | 2026-10-18 |

Each phantom's clock is byte-identical to its correct neighbour's (`14632820` SF@LAR and `14780147`
ARI@LAC). Dry run **not** re-run — the count is unchanged and 100's plan stands.

## 5. D48 LOOK — re-shot, because production moved mid-session

Production was `1175d3ae` at 11:26Z and **`e84e3f4e` at 11:54Z** (lane1b's CERT-907 deploy landing).
108's photograph went stale during the session, so a shot was owed and taken:
`/sports/americanfootball_nfl` at `SHOT_W=390`, 780×9052.

Both duplicates are still live and unchanged on the new sha:

| slot | real game | phantom directly beside it |
|---|---|---|
| Sep 10 5:35 PM | LA **Rams** v SF 49ers — 65/35, Proj 26-22, Netflix | LA **Chargers** v SF 49ers — 57/43, Netflix |
| Sep 13 1:25 PM | LA **Chargers** v Arizona — 82/**18**, Proj 29-18, CBS | LA **Rams** v Arizona — **14%**, **no Proj line**, CBS |

**§4's corrected assignment is confirmed a second time, independently** — the real Sep 13 card reads
`Los Angeles Chargers 82% / Arizona Cardinals 18%, Proj 29-18, CBS`, matching DB row `14780147`. 104's
table had these swapped; do not restore it.

No regressions: crests on every card, probabilities sum to 100, Proj lines present on real games,
broadcast tags populated, footer intact, header reads "Upcoming 19" (18 in-window + Bills@Lions
Sep 17 — not a discrepancy).

**Capture note, slightly different from the brief's:** the baked-in bottom nav sat at a *different* y
on this shot than on 108's, hiding the Sep 13 phantom's top row rather than the real card's. The crop
`(0, 3650, 780, 4560)` no longer frames it — `(0, 4520, 780, 5450)` is where the real ARI@LAC card
landed here. **The nav's y offset is not stable between shots; find it, don't assume it.**

## 6. #2869 — tenth consecutive correct silence

Still p1, `needs-agent`, `matching-symptom`, unassigned, OPEN, 4 comments. Nothing new to say: "it
survived another deploy" is still not new, even though a real deploy to a new sha happened *during*
this session. Held under D35. Not commented on.

## 7. What was NOT done, and why

* Night two: not due (§1).
* CERT-907 / lane1b's merge: not ours (§2).
* The Week 1 apply: Alex's, gated, refused (§4).
* Tracing which rail wrote the phantom clocks: diagnosis, which LANE ROLES gives to the measurement
  lane. Parked, not chased.
* PR **2776** (lane1/065, "DO NOT MERGE YET") left alone — still correctly parked on the unique-index
  pre-check reaching 0.
* The 3 pre-existing ruff F401s: left alone rather than widening a graded diff.
