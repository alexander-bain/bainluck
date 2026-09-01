# CAL-P170 (#1978) — CERT-647's block repaired: the temporary promise now covers only the rows that come back

**Session:** calibration lane, 2026-09-01 ~04:1x–05:xxZ (2026-08-31 ~9:1x pm PT onward)
**Directive:** `935-burndown-conveyor.md` (self-staged by CAL-P169)
**Pillar:** TRUTH · **Ship:** the calibration page stops telling a reader that ~1,284 excluded
baseball rows are coming back when most of them are not.
**Branch:** `program/calibration-168-rank1-baseball` · **Base for this work:** `0d5edbb0`
**Issue:** #1978

---

## 0. WHAT THIS SESSION FOUND ON ARRIVAL, AND WHY IT DID NOT DO WHAT IT WAS TOLD

Directive `935` Item 3 step 1 said: read the beat ledger's `outcome{}` first, and if the publish
gate is still `not_evaluated`, **say so plainly rather than opening a build**.

That was done first, and the answer is unchanged (§4). But **the bus had moved three minutes before
the read**: `CERT-647` came back **BLOCK — TOKEN WITHHELD** at `2026-09-01 04:07Z`, against this
lane's own rank-1 branch. That is not a fourth ship and it is not measurement — it is the repair of
a defect a cert found in cargo this lane already built, and it *shortens* the queue rather than
lengthening it. The directive's "do not open a build" clause is about starting new work while the
page cannot publish; it does not park a cert block.

So: the stall is reported, unchanged and undiagnosed (§4), and the block is repaired (§1-§3).

## 1. THE BLOCK

> **[P1]** K-prime's `is_player_props_placeholder` flag is the union of R1, R2, R3 and M1, and
> `player_props_placeholder_excluded` counts that whole union. The payload publishes that full value
> as `temporary_excluded` and always emits `temporary_by_cell["polymarket/baseball"]` from a
> constant. The branch's own design says R1/R2 are historical residue expected to stay after the
> writer is fixed (1,258 of 1,284 rows are OLD); only M1/R3 are expected to fall. Nevertheless the
> page places the full per-cell count beside "Part of this is temporary", says those rows re-enter,
> and promises "this exclusion empties itself."

🔴 **The cert is right, and the branch already knew.** The constants block above
`PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL` said in prose *"R1 and R2 … are expected to STAY. What
empties is the M1/R3 population."* The payload said the opposite. A comment that contradicts the
code it sits on is worth less than no comment.

Two consequences, and the second is the one that would have outlived the first:

1. `temporary_excluded`'s **name was false** — it said "this many rows are coming back" over a
   population whose majority is not.
2. `temporary_by_cell` was a **constant**, so clause 3 of the disclosure's own design ("when the
   backend stops emitting the cell the sentence leaves the page") and clause 4 ("🔴 THE FALSIFIER:
   if the writer fix lands and this exclusion does NOT empty, the diagnosis was wrong") were
   **unreachable by construction**. A constant never stops being emitted. The falsifier could not
   fire. They were intentions written in the imperative.

## 2. THE REPAIR

**"Temporary" now means held ONLY by arms that end.**

| arm | ends with the writer repair? | cohort |
|---|---|---|
| R1 — both O/U legs open at exactly `0.5000` | no | historical |
| R2 — opening pair sums to 1, published pair does not | no | historical |
| R3 — `%player props%` container, published sum > 1.15 | **yes** | temporary |
| M1 — published into `[0.45,0.55]` from an open >0.25 away | **yes** | temporary |

```
is_player_props_placeholder_temporary
    = (R3 OR M1) AND NOT (R1 OR R2)
```

🔴 **The `AND NOT` is load-bearing, not tidying.** A row held by R3 or M1 *and also* by R1 or R2
does not come back: the temporary arms release it and the historical arms keep holding it. Counting
it as temporary would promise a return that never happens — CERT-647's own finding, one level down.

**Backend** (`backend/app/tasks/precompute_calibration.py`)

* `player_props_placeholder_markets` CTE now carries `ppp_historical_arm` / `ppp_temporary_arm`.
  Each predicate is evaluated **exactly once**, in an inner SELECT, with membership filtered
  outside it — repeating them in a `WHERE` would have put R3's sum test in the CTE twice, which is
  the shape `test_the_props_cte_never_tests_the_bundle_shape` reads as RULE E leaking in by the back
  door. **Membership is unchanged**: `COALESCE` only turns a NULL into false, and a NULL never
  matched the original `WHERE` either.
* New row flag `is_player_props_placeholder_temporary`, a strict subset of the union flag.
* New census columns `player_props_placeholder_temporary_excluded` / `_markets`, **declared in the
  same commit that emits them** (CAL-P162's `UndeclaredColumnError` lesson), including
  `DISTINCT_CENSUS_COLUMNS` membership for the `COUNT(DISTINCT market_id)` one.
* Payload: `temporary_excluded` is the M1/R3 cohort; `historical_excluded` is its complement; the
  two sum to K′'s per-cell total, so the bullet still adds up. `temporary_by_cell` is **gated on
  `temporary_excluded > 0`** — so it empties on its own and clauses 3 and 4 became true statements.
* `player_props_placeholder_markets` is no longer read into the payload (it *was* the value
  published as `temporary_excluded_markets`). The column stays emitted and declared — it is banked
  census, and dropping it would change the declared set and invalidate every banked unit.

**Frontend** (`frontend/app/calibration/page.tsx`, `frontend/lib/api.ts`)

* The temporary sentence now renders **its own count** — *"N of the rows above are coming back"* —
  instead of leaving the reader to bind the promise to the per-cell total printed immediately above
  it, which is exactly what CERT-647 caught.
* *"this exclusion empties itself"* → *"this sentence disappears from the page"*.
* A new clause names what stays: *"The other N are not: they are the same defect already written
  into the back catalogue … They stay excluded until they are separately repaired or separately
  ruled on, and we are not going to describe them as temporary to make the number smaller."*

**Not changed: which rows the published curve contains.** This is a disclosure repair, not a Tier 1
population change. `test_the_temporary_flag_gates_no_curve_row_of_its_own` pins that the temporary
flag appears in no gate and the union flag still appears in exactly the three
(`deduped` + both field-completeness filters).

## 3. GATES

| gate | result |
|---|--:|
| `tests/test_player_props_placeholder_kprime.py` | **33 passed** (23 → 33) |
| **mutation battery, 3 cases, rsync copy** | **3/3 KILLED** — see below |
| frontend jest mutation, 3 cases, in-place + verified restore | **3/3 KILLED** |
| `tests/ -k "calibration or precompute or player_props"` | **2,965 passed / 0 failed** (was 2,955) |
| census contract + fold + fingerprint + RULE E + startup | **82 passed** |
| `npm run build` (ESLint gate) | **EXIT 0** |
| `npm run typecheck` (TS ratchet) | **EXIT 0** — 70 errors, baseline 70 |
| full `TZ=UTC npx jest` | **5,425 passed / 6 skipped**, 302 suites |
| `tests/test_startup.py` | 4 passed |
| Ruff on changed files | clean (one pre-existing `F401` in `test_calibration_field_completeness_257.py`, present at `0d5edbb0`, untouched) |
| full backend suite | **§3a** |

**Mutation battery — every guard was proved to kill its own defect, not merely to pass.**
Run in an rsync copy at `/tmp/mut647` (never the live tree), all three applied in one pass with
anchor assertions so a silently-unapplied mutation could not read as a survivor:

| mutation | guard that fired |
|---|---|
| A — `temporary_by_cell` back to the unconditional constant | `test_the_temporary_sentence_disappears_when_nothing_is_temporary` |
| B — `temporary_excluded` back to the union | `..._counts_the_temporary_cohort_not_the_union`, `..._historical_rows_are_still_excluded_in_that_same_specimen`, `..._the_two_cohorts_sum_to_the_exclusion_total` |
| C — drop `AND NOT COALESCE(ppp.ppp_historical_arm, false)` | `..._the_temporary_flag_releases_nothing_the_historical_arms_still_hold` |

Frontend, same method on the page (restore verified green afterwards, diff re-checked):
removing the count, restoring "empties itself", and deleting the historical clause each killed a
distinct one of the three new jest guards.

**The guards RUN the shipped expression rather than pattern-matching it.** `_eval_entry` extracts
the payload expression's real source with `ast` and `eval`s it against a specimen, with the
temporary and total counts bound to **different** numbers so an expression reaching for the wrong
variable produces the wrong value instead of an accidental match. The helper raises on a key it
cannot find — a disclosure guard that quietly grades nothing is the failure mode the section exists
to catch.

**🔴 The cert's explicitly requested specimen exists:**
`test_the_temporary_sentence_disappears_when_nothing_is_temporary` (zero temporary, 1,284
historical → `temporary_by_cell == {}`), paired with
`test_the_historical_rows_are_still_excluded_in_that_same_specimen` (same specimen →
`historical_excluded == 1,284`, `temporary_excluded == 0`). The sentence disappears **without
re-admitting R1/R2**.

**Fingerprint coverage did not move.** The derived-map fixture was regenerated twice (the file's
sha256 is part of it). Both times the **only** differing key was `source_sha256`:
`input_count` 65, `uncovered_count` 54, `uncovered_sql_shaping` **22**, `hashed_roots` and
`covered_by_value` deltas empty. This repair introduces no new unguarded value that shapes the
population predicate.

### 3a. FULL BACKEND SUITE

**`1 failed / 25,067 passed / 146 skipped / 61 xfailed`** in 20:20. **EXIT 1 by value** — read
the value, not the colour (gotcha #124): `1` is a result, and this is the result.

🟢 **The one failure is the INHERITED economics timebomb and is provably not this ship:**

* the failing test is `tests/integration/test_route_economics.py::TestEconomicsSeededInflation::test_cpi_populates_inflation`;
* **this session changed no economics byte** — `git status --short | grep -i econ` is EMPTY;
* **this branch has never touched that file** — `git diff 4d8373c6 HEAD --name-only | grep -i econ`
  is EMPTY since CERT-638's GREEN base;
* **master already fixed it** in `75c5226c` *"fix(tests): date-robust CPI and jobs seeds in
  test_route_economics"*, and this branch is behind that commit;
* CERT-647 recorded the identical failure against `0d5edbb0` and explicitly ruled *"Do not attribute
  it here."*

The delta against the branch's previously recorded gate is exactly the guards added:
**25,057 → 25,067 passed = +10**, failures unchanged at 1.

## 4. THE PUBLISH STALL — REPORTED, NOT DIAGNOSED (ruling 134)

Re-measured this session from `observations[]`, not inherited:

| | |
|---|---|
| last beat that PUBLISHED | **2026-08-31T04:37:37Z** (`published: true`, `gate: pass`) |
| live payload `generated_at` | **2026-08-31T04:37:36Z** — the same beat |
| beats since | **22** — 21 `cancelled` + 1 `failed`/`refuse` (the last pre-seam beat) |
| `outcome.gate` | `not_evaluated` — **21/21** on the cancelled beats |
| hours since a publish | **23.9** |
| unit bank | **105 / 128**, +5 exactly, for 21 consecutive beats |

**CAL-P169's three corrections all hold and none needed revising.** The bank is not the publish
gate; `beats_to_publish` is a capacity projection and was libelled by three directives; the gate is
not failing, it is **not being asked**.

**One measured observation, which fell out of the directive's own mandated step-1 read and is NOT a
new probe:** `elapsed_ms` tracks `5 × unit_ms_mean + ~300-330s` across the whole post-seam run —
626s at a mean of 83,420 ms, 1,351s at 217,588 ms. A beat that ran out of clock mid-unit would
complete a *varying* number of units as unit cost swung 2.6×. It completes exactly 5 every time.
**That distinguishes a quantized cap from a deadline** — and it is as far as a build lane goes.
The cause stays parked (`PARKED-MEASUREMENTS.md` item 5) with the pre-seam/post-seam stage-map diff
that would settle it. **Do not let the next session re-describe this as "stale".**

`artifact_generated_at` was `2026-09-01T03:45:32Z` on both reads this session, an hour apart, with
no new observation — noted for the measurement lane, not chased here.

## 5. WHAT THIS SESSION DID NOT DO

* **Did not grade either prediction.** `artifacts/cal-p162/PREDICTION.md` and
  `artifacts/cal-p168/PREDICTION.md` remain ungraded and ungradeable: the payload has not moved
  since 04:37Z 8/31, and both ships publish together so grading must be at CELL level anyway.
* **Did not rewrite the pre-registered prediction.** §6 of `cal-p168/PREDICTION.md` contradicts
  itself ("this exclusion must empty itself" vs "R1 and R2 are expected to stay"). It keeps its
  registered shape; a dated **§8 amendment** records which half was right and gives the falsifier a
  field that can actually falsify it (`temporary_excluded` → 0, not `excluded_by_cell` → 0, which
  was untestable).
* **Did not diagnose the publish stall** (ruling 134, measurement lane).
* **Did not open a fourth ship**, touch the frozen file, or resolve the add/add conflict — CAL-P169
  determined that resolution by execution and it remains the Integrator's to apply
  (`READY-…md` §6a/§6b).
* **Did not merge or push master.** No production write.
