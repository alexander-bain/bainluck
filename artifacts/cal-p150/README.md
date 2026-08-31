# CAL-P150 — the freeze lifted, all five landed, and cricket's first lead is refuted by the book's own grammar

**TL;DR.** The whole freeze-lift batch is BUILT and committed on
`program/calibration-119` — five commits, in the directive's order, each green at
its own SHA. Nothing is deployed and nothing is certified; the author does not
certify. Two of the five needed a correction that only the full suite could
find, and both are written up rather than quietly folded in. Cricket's first
lead is dead and a better one replaced it.

| item | state |
|---|---|
| 1a D5 dedup join | ✅ built, `67f5a6d3`, PG gate + cricket control, red-first in CI |
| 1b D21 named refusal | ✅ built, `2472b7e8`, red-first 9F/9P exit 1 → 0 |
| 1c D22 diagnostics soft | ✅ built, `4ce014d3`, red-first 8F/8P exit 1 → 0 |
| 1d D13 lost losses | ✅ built, `9c9f7abf`, red-first 10F/31P exit 1 → 41P exit 0 |
| 1e D12 crypto tuple | ✅ built, `fd033079`, 18 new guards |
| board re-measure | ⚠️ **cannot be done before deploy** — §4 |
| 2 cricket | ✅ first lead REFUTED, new lead measured — §5 |
| 3 board | ✅ rebuilt under D15, `board-d15.py` exit 0 — §6 |

**Beat 19 landed and was gauged: CLEAN, and it is the TIGHTEST margin in the
window at 2,691 ms.** 17 gauged, 17 agreements, 0 disagreements. Window stands
19 beats, 16 clean, 3 misses (4=B, 7=C, 15=B, all attributed). Watcher
3016/3019, banker 75909/75911, probe 37525/37527 — all alive at entry and exit,
zero restarts, heartbeats advancing.

---

## 1. What landed, and the one thing to read before splitting the deploy

Five commits on `program/calibration-119`, based on `682c0b37` (the CAL-P147
tip), in the order the directive names. Each was gated at its own SHA, not just
at the tip.

🔴 **ALL FIVE MOVE `_main_input_fingerprint`, SO THEY ARE ONE DEPLOY OR THE
128-UNIT REBUILD IS PAID FIVE TIMES.**

```
base   b18200401ebc91463ff094163ab90afc   <- the digest the LIVE producer is
D5     744c9003ee3aff3b92cc299f9d015b0a      stamping into every beat of the
D21    3f5d2a56e4e35175249f7260977e6d24      current window (window-log beats
D22    6a4f14b43380290ba4d910ed9612ba46      15-19). That match is the check
D13    0a78f60289eabfd0ec569b6cfa6f3d4a      that says this tree's shaping
D12    8aa84de4bc65133252f56f5004900d21      inputs are the deployed ones.
```

The staged futures cursor resets to zero on merge. D22 is in the batch, which is
what makes D13 safe to ship: class B is a flat p=0.146 per beat, D13 forces ~10
extra beats, so D13-alone was a 79% chance of a class-B miss inside its own
rebuild (`artifacts/cal-p144/CLASS-B-ROOT-CAUSE.md`).

---

## 2. 🔴 TWO CORRECTIONS THE FULL SUITE FOUND, AND ONE OF THEM WAS MINE

Both were invisible to every targeted gate and appeared the first time the whole
calibration suite ran. This is the section to read if you read only one.

### 2a. D21's first cut 500'd the public endpoint

`compute_calibration_payload` has TWO callers: the scheduled producer, and
`/api/calibration`'s in-request cold-cache fallback. Refusing on an absent Redis
key for BOTH turned "Redis is unreachable" into a 500 on the public endpoint —
on the very path that exists BECAUSE Redis is unreachable. **95 failures, 55 of
them in `test_route_calibration.py`.**

`refuse` is now keyword-only with no default, and the call site passes
`is_producer_build`, captured before the `runner or NULL_RUNNER` substitution
because after it `runner` can no longer answer the question. The serve path
returns `([], 0, reason)`, logs it, and the reason reaches the payload as
`soccer_2way_filter.bookmaker_curve_degraded`.

### 2b. CAL-P143's D22 pre-build deleted a handler it did not know was there

`NullPhaseRunner.soft_stage` was a bare `yield` — no savepoint AND no handler —
on the reasoning that the null runner has "no live session to protect". The
first half is right. The second is not: `read:date_range` was **already** wrapped
in `try: ... except Exception: logger.warning`, and moving it into a soft stage
that does not catch removed that. **38 failures**, every one `AttributeError:
'NoneType' object has no attribute 'lo'` — the exact exception the old `except`
swallowed.

The null runner now catches. It still does not open a savepoint (a request
session must not have its transaction structure changed under the caller), so a
real statement timeout on the serve path still poisons later reads in that
request — which was true before D22 too. Carried forward, not introduced, and
said out loud.

**The lesson both share:** a fix scoped by reading the code is scoped by reading
ONE caller. The suite is what knows how many there are.

---

## 3. Two tripwires moved, in opposite directions, and both are flagged

* `uncovered_sql_shaping` **21 → 22** (RAISED). The new entry is
  `BOOKMAKER_CURVE_REDIS_KEY`, named in the refusal message that exists to tell
  an operator which key is missing. The detector counts any module constant
  interpolated by f-string, `+` **or** `%` (CAL-P032 widened it past f-strings on
  purpose), so there is no way to put the key in that message it will not see —
  `.join` or a local alias would HIDE it, which is gaming a tripwire rather than
  satisfying one. Argued in the guard's own docstring. **Raising a tripwire is as
  serious as lowering one.**
* `covered_by_value` **3 → 4**, and this one is a hole CLOSED.
  `NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS` is interpolated into the emitted SQL, but
  `inspect.getsource(_calibration_population_ctes)` hashes the f-string
  TEMPLATE, not the substituted value — so adding or removing a ruled cell would
  have changed the published rows while leaving the digest identical, and a
  cursor banked under one exclusion list would have stayed resumable by code
  with another. Fourth instance of the hole that function's docstring keeps
  describing. Found by asking what a change to the value would do.

Two defect-pinning guards were INVERTED rather than deleted, the way 12-CAL's
census guard was: `test_the_fan_out_join_is_still_on_two_of_five_columns` (it
existed to fire the day D5 landed; it fired) and the missing-loser census guard.

---

## 4. ⚠️ THE BOARD RE-MEASURE CANNOT BE DONE FROM HERE, AND SAYING SO IS THE ANSWER

The directive says *"Then re-measure the whole board and publish the honest
headline."* **Nothing in this batch is deployed**, so the board still measures
the old population — the live headline is **1.88 pp on q268**, unchanged, and
every cell reading in §6 is pre-lift. A re-measure taken now would be a
re-reading of the defect, published as if it were the repair.

What IS known, and it is not a prediction of the composite:

* **D5 alone**: Alex's ruling records 1.89 → **~2.31**. It rests on 13 cells
  folded exactly on the payload basis — 420,081 published rows against 266,137
  distinct, 36.65% phantom over 45.4% of the curve.
* **D13**: the headline gets WORSE by an unmeasured amount. Two of the four cells
  measured exactly move the wrong way (`kalshi/entertainment` 5.21 → 6.30).
* **D12**: removes 4,563 rows at ECE 7.61, above the headline, so it pulls DOWN
  slightly.
* **D21/D22**: no population change.

🔴 **Do not add these.** CAL-P100's rule: mechanisms can flag the same row, and a
sum of deltas is not a measurement. The composite is ONE post-deploy reading of
`/api/calibration`, and the needle definition (cells-at-bar) recomputes on the
new population at the same moment. That reading is OWED and it is the first
thing the next session should take.

---

## 5. CRICKET — the first lead is dead, and what replaced it is ours

Under D14 (*"Markets aren't wrong; calculations are"*), presumption = our bug.
The directive names the order: wrong-leg class, then staleness, then leg-mapping.

### 5a. The wrong-leg class has ZERO rows in cricket, and it is a true zero

CAL-P138's published leg-swap fold, run on `polymarket/cricket`: 6,264 rows
cached, 1,969 priced, **0 families**. Normally that reading is instrument
blindness (CAL-P134's lesson: a check by one grammar reports its own blindness as
an all-clear), so it was checked against the book rather than accepted. The
names Polymarket actually writes for cricket:

```
<League>: <A> vs <B>                       the match winner
<League>: <A> vs <B> - Most Sixes
<League>: <A> vs <B> - Team Top Batter
<League>: <A> vs <B> - Toss Match Double
<League>: <A> vs <B> - Who wins the toss?
```

There is no `O/U <number>` anywhere in it. A class defined as "the Over leg is
stored on the Under side" has nothing to act on. **Refuted, not unmeasured.**

### 5b. 🔴 TWO MARKET FAMILIES ARE MISSING A GRADED WINNER ON ~TWO THIRDS OF THEIR MARKETS

`cricket-shape-fold.py`, raw tables, id-chunked with adaptive halving:

| family | mkts | n | mean price | realized | winners found | winners expected |
|---|--:|--:|--:|--:|--:|--:|
| match_winner | 1,341 | 2,968 | 0.509 | 0.445 | 1,320 | 1,341 |
| team top batter | 557 | 1,602 | 0.504 | 0.327 | 524 | 557 |
| toss match double | 507 | 1,468 | 0.495 | 0.328 | 482 | 507 |
| most sixes | 499 | 1,458 | 0.501 | 0.326 | 475 | 499 |
| **who wins the toss?** | **647** | **1,230** | **0.500** | **0.181** | **223** | **647** |
| **completed match?** | **630** | **1,202** | **0.507** | **0.198** | **238** | **630** |

*(winners expected = one per market, which is what a single-winner question
resolves to by definition.)*

**A coin toss cannot realize 18%.** "Who wins the toss?" is priced at 0.4997 —
the venue has it exactly right, to four decimals, which is the strongest possible
evidence for D14's premise — and **424 of its 647 markets have no winner recorded
at all**. "Completed match?" is the same shape: 392 of 630.

And `ungraded` is **0** on every row. `is_winner` is not NULL on those outcomes,
it is **FALSE** — so nothing downstream can tell "we never graded this" from "we
graded it a loss". That is exactly the ambiguity 12-CAL/D13 is about, one layer
up: D13 handles the lone-claim case, and this is the ≥2-outcome case that
`no_winner_markets` is supposed to catch.

### 5c. What is NOT claimed, and the next step

🔴 **This is a raw-table fold and it does NOT reproduce the published cell.** Raw
n is 10,100 against the payload's 3,258, and — the tell — every family's gap here
is POSITIVE (over-prediction) while the published cell's gap is **−4.51**
(under-prediction). The sign flips between the two populations, so the published
miss is being carried by a subset this cut cannot see. Lesson 19: a cell census
is not a published-population census. Nothing above may be quoted as a cause of
the cell's ECE until it is re-derived through `_calibration_population_ctes`.

**The next step is one fold, and it is named:** run these six families through
the producer's own chain and answer which of them reach `deduped`. If the
no-winner families are already excluded, the published miss is elsewhere and
staleness is next. If they reach it, the cell's number is measuring our grading.

**"The venue is bad at cricket" is not supportable and no such label ships** —
a book that prices a coin flip at 0.4997 is not the broken component.

---

## 6. The board, rebuilt under D15

`board-d15.py` — exit 0, every ruled cell present and placed. 32 cells over bar:
**10 established, 22 thin-miss** (ranked below, NOT removed), 8 restored by
today's batch, 2 parked.

D15's doctrine retires the reason nine cells were taken off, because "not
established" IS the clustering argument wearing a σ. So the script encodes the
ORDERING rule, not a list.

🔴 **And it caught the board reading a different quantity than anyone assumes.**
The six CAL-P120 cells have NO `sigma_measured` ledger entry, so the render falls
back to a binomial estimate over BOOK ROWS — and 10–18 bookmakers quote one game,
so that unit is wrong by construction. On the render alone all six print as
**established**:

```
odds_api_bookmaker/basketball_nba          board 5.41 -> per-game 1.28  (573 games, 17.8x)
odds_api_bookmaker/baseball_mlb_preseason  board 6.55 -> per-game 1.69  (217 games, 15.0x)
odds_api_bookmaker/icehockey_nhl           board 2.59 -> per-game 0.62  (495 games, 17.5x)
odds_api_bookmaker/basketball_wncaab       board 4.13 -> per-game 1.72  (583 games,  5.8x)
odds_api_bookmaker/basketball_wnba         board 3.02 -> per-game 0.80  (300 games, 10.4x)
odds_api_bookmaker/basketball_euroleague   board 2.43 -> per-game 0.74  (162 games, 10.9x)
```

They stay ON the board — that is the ruling — and they rank below the established
cells, which is what the doctrine asks for instead of deletion. `kalshi/golf`
(17-CAL) returns at rank 13 on measured σ 1.52; **17-CAL is answered NO by D15
and should be closed.** `polymarket/basketball` and `polymarket/hockey` are
PARKED (D16 + 20-CAL, one mechanism), not refused — parked needs a date, refused
needs a new argument.

**D4 was already staged** as `M-20260830-J` on the measurement bus before this
session started. Not duplicated. An addendum was appended giving the population's
address (`NOTE-TO-CALIBRATION-FROM-LANE1-Q436.md` §4 — ~57,000 resolved markets,
19 cells, four named) and the derivation for the other fifteen, plus the warning
that `19` is the note's count and has not been re-derived.

---

## 7. What this session did NOT do

* **Deployed nothing, certified nothing, pushed no master.** The author does not
  certify; five cert subjects are staged for lane 4.
* **Did not re-measure the board.** §4 — it is not measurable before deploy, and
  a pre-lift reading published as the honest headline would be the defect
  wearing the repair's name.
* **Did not re-derive E2's scope.** D13's ruling requires it AFTER the filter
  fix, and the fix is built but undeployed, so the population it must be
  re-derived on does not exist yet.
* **Did not redesign D13's pre-built arm**, though one thing is flagged to the
  cert: `market_count`/`total_outcomes` are per-VARIANT counts, so the arm can
  fire for a market alone in its variant inside a grouped vm, which its docstring
  calls "ungrouped". Pre-existing, not introduced by D5, and Alex-ruled — so
  reported, not changed.
* **Did not rename the `esports_multi_bundles` CTE** now that it carries a second
  cell. The payload key is a public contract and the exception was for one tuple.
  Flagged in the SQL.
* **Did not touch the retention admin button.** It is the hazard, not the fix.
* **Did not restart any of the three watchers.** Zero restarts.

## 8. Gates

| gate | result |
|---|---|
| `-k "calibration or bookmaker or ladder"` at the tip | **3,019 passed / 27 skipped / 0 failed — EXIT 0** (131.26 s) |
| the same gate at each of the five SHAs | green at each, with the two known cross-commit exceptions recorded in their commit messages |
| `test_startup.py` | 4 passed EXIT 0 |
| ruff, all changed files | clean, EXIT 0 |
| `pg_gate_seed_completeness` | 6 passed EXIT 0 — the new PG gate's INSERTs are complete |
| full backend suite | see `full-suite.txt` |
| red-first, D21 | 9 failed EXIT **1** at base → 9 passed EXIT 0 |
| red-first, D22 | 8 failed EXIT **1** at base → 8 passed EXIT 0 |
| red-first, D13 | 10 failed / 31 passed EXIT **1** at base → 41 passed EXIT 0 |
| red-first, D5 | executed IN CI by the gate itself (two-armed), not locally — no Postgres in the sandbox |

⚠️ **Both CAL-P143 verifiers exit 1 on this tree and it is the harness, not a
result.** `verify-d22.py` and `verify-12cal-suite.py` copy the repo files to
/tmp and apply their patch to the copies; against an already-patched tree
`patch --batch` detects a reversed patch and assumes `-R`, so they verify an
UNPATCHED module. Confirmed by inspection (`census_observed` count 0 in the
scratch copy, a `.orig` beside it). They are PRE-APPLY instruments; their
pre-apply runs are banked in `artifacts/cal-p143/`. The post-apply proofs are the
suites, which import the real modules.

## Evidence

| file | what |
|---|---|
| `board-d15.py` / `.json` / `.txt` | §6 — the rebuilt board, exit 0 |
| `cricket-shape-fold.py` / `.json` / `.txt` | §5b — the family fold, adaptive halving |
| `legswap-cricket-log.txt` | §5a — the fold that returned 0 families. Banked as `.txt` because `.gitignore:79` is `*.log`, so the `.log` beside it is untracked and would have vanished with the worktree |
| `../cal-p138/published-legswap-cricket.json` | §5a — its banked output |
| `full-suite.txt` | §8 |
