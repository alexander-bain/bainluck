# CAL-P168 (#1978) — RANK 1 IS BUILT. `polymarket/baseball`, K′ = R1 + R2 + R3 + M1.

**Published curve on arrival: `mce_closing_line` 1.86 pp →, `generated_at 2026-08-31T04:37:36Z`.**
Unchanged for a **fifth** session. RULE E is still not deployed — re-verified directly: the payload
has no `nonexclusive_bundle_filter` key. The page is stale, not broken.

**PILLAR: TRUTH. SHIP: the calibration page stops scoring ~24,800 baseball prop forecasts on a
price our own writer invented, and says so on the page — naming the defect, counting the rows, and
promising them back.**

## 0. WHAT I DID, IN ONE LINE

Rank 1 — the largest item left on the burn-down board, **78,782 excess-outcomes**, ruled by Alex on
2026-08-28 and unbuilt through five sessions — is **built, guarded, mutation-proved and pushed**, on
a NEW branch, with a prediction recorded before the code.

## 1. STATE OF THE PREDECESSOR — CERT-638 IS GREEN AND STILL UNMERGED

| | |
|---|---|
| `program/calibration-119` @ `4d8373c6` | untouched by this session, still == its remote |
| CERT-638 | **GREEN — TOKEN GRANTED** for `4d8373c6` against `e798ee4b` (cert log line 715) |
| `origin/master` | moved to **`75c5226c`** — the branch is now **9 behind / 13 ahead** |
| merged? | **NO.** The Integrator has not taken it |

🟢 **The economics timebomb looks repaired on master.** `75c5226c` is
*"fix(tests): date-robust CPI and jobs seeds in test_route_economics"* — the inherited
`ECONOMICS-CPI-AUGUST-2026-TIMEBOMB` that was PR #2468's only CI failure. Worth confirming on the
next CI run rather than assuming.

🔴 **I did not commit to `program/calibration-119`,** per directive Item 0. This work is on
**`program/calibration-168-rank1-baseball`, based at `4d8373c6`.** ⚠️ `program/calibration-120`
is NOT free — `program/calibration-120-orm-is-winner-nullable` already exists on the remote — which
is why the branch is numbered 168 and not 120.

**Unit bank moved for the first time in two sessions: 95 → 100 / 128.** Still +5/beat, but this
beat read `5 completed / 1 cancelled` rather than 5/2. Read only via the raw gauges;
`beats_to_publish` reads **2** at 100/128 while the arithmetic says ~6. **Trust the unit count.**

## 2. WHAT WAS BUILT

`git diff 4d8373c6..HEAD` — **12 files**, one new guard file, one new artifact directory.

| arm | predicate | provenance |
|---|---|---|
| **R1** | both legs of a two-leg O/U market open at exactly `ROUND(opening_probability,4) = 0.5000` | ported from `program/calibration-99` |
| **R2** | two-leg O/U, opening pair sums to 1 within `PAIR_SUM_TOLERANCE`, published pair does not | ported |
| **R3** | market name `ILIKE '%player props%'` **and** published sum > **1.15** | built here on RULE E's own constant |
| **M1** | published price in `[0.45,0.55]` having opened >0.25 away | built here |

**Cherry-picked the predicates, never the branch** — `program/calibration-99` is 808 behind and
carries two foreign workstreams (#2212's 15,300-line repair plan, ~1,700 lines of measurement-lane
fold scripts). Nothing from those came across.

🔴 **The tuple is deliberately NOT in `NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS`.** RULE E's predicate on
this cell was measured at **8.35**, and its sum arm alone at **9.02**, against a **4.71** control —
nearly double the error. K′ has its own allowlist, `PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS`. The
two filters share a payload key, a disclosure bullet, and nothing else.

**The user-visible half needed no frontend work.** The page, the type and its 13 jest guards have
been built and green since CAL-P114/P119, gated on `temporary_by_cell` being non-empty. It has
shipped as `{}` ever since. **This is the payload that first fills it.**

## 3. THE PREDICTION, RECORDED BEFORE THE CODE

`artifacts/cal-p168/PREDICTION.md`. Headline: **4.71 → 2.71 pp**, n 41,127 → 17,827,
excess-outcomes **78,782 → 0**, holdout OLD 2.90 / NEW 2.63.

🔴 **Stated up front rather than discovered after deploy: 2.71 against a 3.0 bar is 0.77σ under it.**
A pass, and not a comfortable one. A reading of 2.9–3.1 does **not** refute the design. ≥3.4, or
either holdout half over the bar, does.

⚠️ **Every number in that document is CAL-P117's, measured 2026-08-28. This session re-measured
nothing** — see §6.

## 4. WHAT THE GATES SAID

| gate | result |
|---|--:|
| `tests/ -k "calibration or precompute or player_props"` | **2,955 passed / 0 failed**, 23 skipped |
| new guard `test_player_props_placeholder_kprime.py` | **23 passed** |
| **mutation battery, 16 cases** | **16 KILLED / 0 survived**, control green |
| frontend `npm run build` (ESLint gate) | **EXIT 0** |
| frontend `npm run typecheck` (TS gate) | **EXIT 0** — 70 errors, baseline 70 |
| jest disclosure guard | **13 passed** |
| `tests/test_startup.py` | **4 passed** |
| Ruff on changed files | clean (the one hit in `test_calibration_field_completeness_257.py` is **pre-existing on HEAD**, verified by running Ruff against `git show HEAD:` of that file) |
| sqlglot parse of the rendered population | OK |
| **full backend suite** (landed, 20:15) | **1 failed / 25,057 passed / 146 skipped / 61 xfailed**, EXIT 1 **by value** |

🟢 **The one failure is the inherited economics timebomb, and it is provably not this ship.** It is
`tests/integration/test_route_economics.py::TestEconomicsSeededInflation::test_cpi_populates_inflation`
— the `ECONOMICS-CPI-AUGUST-2026-TIMEBOMB` CERT-634 recorded. Three facts, each checked rather than
asserted:

* **master already fixed it.** `75c5226c` is *"fix(tests): date-robust CPI and jobs seeds in
  test_route_economics"*, touching that exact file (+20/−8).
* **my base is behind that fix.** This branch is based at `4d8373c6`, 16 behind master, so it still
  carries the pre-fix file — `git diff HEAD origin/master -- <that file>` shows the 28 lines.
* **this ship touches no economics bytes.** `git diff 4d8373c6 HEAD --name-only | grep -i econ` is
  empty.

It disappears on rebase or merge. **Do not hold the merge on it and do not attribute it here.**

## 5. 🔴 TWO REAL DEFECTS IN MY OWN CHANGE, CAUGHT BY EXISTING GUARDS BEFORE DEPLOY

Both are recorded because both would have been silent in production, and because they are the
guards CAL-P162/P164 paid for working exactly as intended.

1. **The two new totals were emitted and declared to nobody.** `fold_unit_rows` raised
   `UndeclaredColumnError` — *"undeclared column(s) in a chunk result:
   player_props_placeholder_excluded, player_props_placeholder_markets"* — and **no generation
   could have banked.** This is CAL-P162's failure reproducing on my change, one deploy later.
   Fixed by declaring both in `DEFAULT_CENSUS_COLUMNS` (and the markets count in
   `DISTINCT_CENSUS_COLUMNS`, since it is a `COUNT(DISTINCT market_id)`).
2. **The totals were dropped by the OUTER aggregate.** The inner scan emitted them; the outer
   `MAX(ls.…)` pass-through did not carry them. That reads as a missing attribute at runtime and a
   silently absent disclosure on the page — **the exclusion failing OPEN**. Caught by p164's
   `test_no_column_is_declared_that_the_statement_never_emits`.

Both are now mutation cases 15 and 16, so the next person to make either mistake meets a red rather
than a production incident.

## 6. 🔴 A GUARD THAT SHIPPED VACUOUS, AND WHY IT MATTERS MORE THAN THE BUG

`test_temporary_by_cell_is_empty_because_no_temporary_cell_shipped` was written by CAL-P162 with an
explicit promise in its docstring: *"When rank 1 lands, this test is the one that must be updated,
and updating it is the reminder that the revert condition has to be named."* The PORT-SCOPE repeated
it twice — *"goes red the moment you add the tuple — deliberately. That red is the design working."*

**Rank 1 landed and the test stayed green.** It asserted `('polymarket','baseball')` was absent from
`NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS` — and the design *forbids* the cell ever joining that tuple, so
the guard was watching the one list the cell was never going to be in. It would have stayed green
forever while the disclosure it protects went unwritten.

> **Generalisable: a guard that names the MECHANISM it expects, rather than the OUTCOME it requires,
> goes vacuous the moment the mechanism is implemented differently — and it goes vacuous silently,
> because a passing test looks the same either way.** The old assertion asked "is the cell in this
> list?"; the ruling requires "if the cell is excluded anywhere, is the promise on the page?"

Rewritten as `test_every_temporary_cell_is_excluded_and_every_excluded_cell_is_declared`, binding in
both directions over both allowlists, plus
`test_the_two_allowlists_are_disjoint_so_no_row_is_counted_twice` (the payload sums two rules into
one total, so a cell in both lists would overstate the disclosure while every individual number
still looked self-consistent). Both are mutation-proved.

## 7. THE FINGERPRINT — SIX HOLES CLOSED, ONE COUNTED, ONE MISCOUNT REFUSED

K′ adds nine inputs. Rather than let the tripwire absorb them:

* **Six closed by value** in `_main_input_fingerprint` on the deploy that created them — the
  allowlist, R1's 0.5000, R3's pattern, M1's two band edges and its drift floor. Each is
  interpolated into emitted SQL by a helper `inspect.getsource` cannot see through, and each decides
  which rows the curve publishes. `covered_by_value` 5 → 11.
* **One counted honestly**: `PAIR_SUM_TOLERANCE`. It *is* hashed by value, but `derive_declared`
  only credits names defined in the build module, so a cross-module input can never read as
  covered. `uncovered_sql_shaping` 21 → **22**, and the cross-module tier goes **5 → 6** — the first
  time that tier has moved in the file's history. Recorded by name in both pins.
* **One miscount refused.** Writing the payload's rule sentence as `A + " " + B` moved
  `NONEXCLUSIVE_BUNDLE_FILTER_RULE_TEXT` — a prose sentence — into `uncovered_sql_shaping`, because
  the detector flags any name beside a string constant in a `+`. That would have made the pin 23.
  The prose is `" ".join(...)`ed instead. **This is deliberately distinguished from D21's
  `BOOKMAKER_CURVE_REDIS_KEY`**, which was COUNTED and where `.join` was called out as hiding: there
  the name had to reach an operator message and the value really can move the population. Here it is
  two sentences of documentation and the value shapes nothing.

Derived map regenerated, never hand-merged.

## 8. 🔴 WHAT I DID NOT DO, AND WHY — I DID NOT FOLD THE CELL

PORT-SCOPE §6 says "R1 → guard → fingerprint regen → **measure**". **I did not measure**, and that
is a ruling, not an omission. **LANE ROLES (Alex, 2026-08-25): build lanes BUILD — their only
permitted measurement is their own gates.** Folding the published cell through
`calibration_cell_exact.py` is a heavy production query and belongs to the measurement lane
(ruling 134).

So the design's numbers are **transplanted, not reproduced**, and the grading mechanism is the
prediction doc against the next published curve. **Anyone reading §3 should read it as CAL-P117's
measurement from 2026-08-28, four sessions stale, not as this session's.**

⚠️ **One honest divergence from what was measured, and it is the only place this port is not
like-for-like.** R3's sum uses `bundle_price_sum` (the shipped per-market published sum, and the
quantity RULE E's 1.15 is defined against). The design's rail summed `adj_opening_probability` over
`deduped` — post-dedup, post-normalization — which **cannot be referenced from here without a cycle**,
since `deduped` is downstream of this very flag. The bases genuinely differ. What bounds it is the
margin: a props container's measured sum is **15–19** against a threshold of **1.15**, so no
plausible basis change moves a container across it. That reasoning is pinned in
`test_r3_sums_over_the_shipped_published_sum_and_says_so` rather than left in a comment.

⚠️ Also carried, unresolved: **R1's shipped form on `calibration-99` is scoped to
`market_type = 'quantity'`; the fold that measured K′ was not.** I transplanted **what was
measured** (no `market_type` conjunct), because the design's numbers are the fold's. This means K′'s
R1 is slightly WIDER than `calibration-99`'s R1. Named here so a reader does not discover it as a
discrepancy.

## 9. WHAT A USER CAN SEE OR DO NOW THAT THEY COULD NOT BEFORE

**Nothing yet — and that is the fifth session in a row that sentence has been true.**

The curve on https://bainluck.com/calibration still reads **1.86 pp** from **2026-08-31T04:37:36Z**.
Nothing in this session reaches a user until the branch merges, the bank fills, and the curve
republishes. The ship is **built and gated**, not delivered.

What is *queued* for a reader, and what to check the moment the curve moves:

> **Part of this is temporary by design.** polymarket/baseball — returns when the Polymarket
> player-prop writer stops overwriting the market's own quote with a near-0.50 placeholder…

That sentence has never rendered. A reader meeting it learns that ~24,800 of their forecasts were
set aside **because we wrote the price wrong, not because the market did**, and learns the condition
under which they come back.
