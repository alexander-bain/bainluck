# CAL-P125 — the whole-virtual-market rail: two blocked board cells, measured

**Verdict: THE RAIL IS REPAIRED, AND THE REPAIR IS PROVED ON BOTH ENDS OF THE RANGE.**

`polymarket/basketball` — the cell CAL-P124 declared UNMEASURED — now reproduces the published
payload to **−0.14%**. The id-range rail reproduced it to **−35.85%**.

| rail | n | ECE | gap | delta vs payload |
|---|--:|--:|--:|--:|
| published payload (`q268`) | 13,135 | 4.24 | +2.96 | — |
| id-range rail (CAL-P124) | 8,426 | 4.14 | +3.51 | **−4,709 (−35.85%)**, ECE −0.10, gap +0.55 |
| **whole-vm rail (this)** | **13,116** | **4.25** | **+2.96** | **−19 (−0.14%)**, ECE **+0.01**, gap **+0.00** |

The control moves the right way too. `polymarket/cricket` was the id-range rail's *best* cell at
−0.18%, and it is the one place a rebuild could plausibly regress:

| cell | id-range rail | **whole-vm rail** |
|---|--:|--:|
| `polymarket/cricket` | −0.18% | **+0.00% — exact, n=3,252 / ECE 8.11 / gap −4.61 both sides** |
| `polymarket/basketball` | −35.85% | **−0.14%** |

Two independent runs of the basketball fold returned byte-identical self-checks
(13,116 / 4.25 / +2.96), so the number is deterministic rather than a lucky partition.

---

## 1. What was actually wrong, in the producer's own words

`calibration_cell_exact` chunks on `fm.id` and re-derives `virtual_market` **inside every chunk**.
`precompute_calibration._virtual_market_ctes` documents why that cannot work, and it was written
before this rail existed:

> group and event sizes are counted over `market_info`, so re-deriving them from a FILTERED
> `market_info` silently changes them ... a chunk holding fewer than 3 would see the event collapse
> below the gate entirely, silently re-assigning every one of its markets to `m:` — a different
> question identity, a different representative, a different bucket.

`polymarket/basketball` is **82% grouped** (21,240 of 26,007 markets carry a `g:` virtual question)
and its largest virtual question spans **120 markets**. An id-range chunk cuts those apart, the
`>= 3` gate fails on the pieces, and the pieces take a different branch of `ranked_outcomes`. That
is the 4,709 rows.

`polymarket/cricket`, by contrast, has a largest virtual question of **9 markets** — which is
exactly why the id-range rail scored −0.18% there and why cricket could never have revealed the
defect.

## 2. The fix is the producer's own, not a new idea

The staged build solved this in production (Queue 300D Item 0). This rail drives that same code
from the read rail:

* **Stage A — freeze the generation.** Derive `virtual_market` ONCE for the cell and read the
  roster out. Nothing below `virtual_market` is referenced, so PostgreSQL plans the rest of the
  chain away — `_futures_generation_sql`'s own argument, reused rather than restated.
* **Stage B — replay it.** Per unit, call `_calibration_population_ctes(frozen_vm_roster=True,
  market_info_extra=VM_ROSTER_MARKET_INFO_EXTRA)` — the same call `_main_futures_sql(frozen=True)`
  makes — and cut the units with the producer's own planner, `plan_units`, which guarantees a
  `vm_id` is never split.

So a chunk is a **replay of one coherent global derivation**, not a re-derivation over a subset.
Correct by construction, not by measurement.

## 3. The two chunking problems, and why neither is an id range

**Stage A cannot be read in one request.** CAL-P124 measured the unscoped global chain blowing the
Heroku router timeout (`Application Error` at 103 s). So the CTEs are scoped to the cell and the
READ is chunked on `ABS(HASHTEXT(vm_id)::bigint) % N` — a filter on the OUTER select that never
touches `market_info` and therefore cannot move a group or event size.

A class that truncates or times out is split `(N, k) -> (2N, k), (2N, k+N)`, an **exact
refinement**: `x % 2N in {k, k+N}` iff `x % N == k`. The split fires on the server's own
`truncated` flag, never on a row-count heuristic (gotcha #53).

Two details that are not decoration:
* `::bigint` before `ABS` — `hashtext` returns int4 and `abs(-2147483648)` overflows, which would
  error one class in billions and read as an empty range.
* `hashtext` is absent from `sql_read_guard`'s pure-function allowlist. That list governs the
  ANALYZE path; the row path accepts it, and that was probed before a line was written.

**Stage B cannot split a unit** — splitting a `vm_id` is the whole defect. An over-budget unit is
**re-planned at `2 x buckets`**, which is an exact refinement for the same modular reason
(`bucket_of(v, 2B) % B == bucket_of(v, B)`, since `bucket_of` is SHA-256 mod B). Both refinements
fired in production during the basketball run.

A single `vm_id` that alone exceeds the statement budget is raised **BY NAME**. It is the one thing
this rail cannot do, and an instrument that cannot measure something has to say so.

## 4. CAL-P124-2 is measured, and it explains the residual it left

Stage A is scoped to `(source, category)`. The **source** half is exactly free — `group_sizes` and
`event_sizes` are already `GROUP BY ..., source`, so restricting `market_info` to one source removes
only rows that could never have joined. The **category** half is not free: a group or event whose
markets carry two `llm_sport_category` values is counted short and can fall below the `>= 3` gate.

`--bound` measures it per cell instead of assuming it. Measured 2026-08-29 against `q268`:

| cell | spanning groups (mkts) | spanning events (mkts) | upper bound | of cell |
|---|--:|--:|--:|--:|
| `polymarket/basketball` | 11 (12) | 10 (15) | **<= 27 markets** | 26,007 (0.10%) |
| `polymarket/hockey` | 0 (0) | 1 (8) | <= 8 | — |
| `polymarket/baseball` | 298 (312) | 204 (230) | <= 542 | 64,558 (0.84%) |
| `polymarket/cricket` | 0 (0) | 0 (0) | **0 — exact** | 6,607 |
| `polymarket/economics` | 8 (12) | 0 (0) | <= 12 | — |

These are UPPER bounds and loose ones — a group with five in-cell members and two outside spans
categories but clears `>= 3` both ways, so it re-assigns nothing. Where the exact figure was
computed directly (`baseball`: **325 of 64,558 markets, 0.50%**) it came in ~40% under its
542-market bound.

**The bound predicts the residual on both cells that were folded.** Cricket's bound is zero and
cricket reproduces at +0.00%. Basketball's bound is <= 27 markets and basketball's residual is 19
rows. That is the residual explaining itself rather than being waved at.

## 5. What it costs

| | Stage A | Stage B | total |
|---|--:|--:|--:|
| `cricket` (6,607 markets, 16+16) | 26 s | 19 s | **45 s** (id-range rail: ~225 s) |
| `basketball` (26,007 markets, 64+64) | 199–395 s | 92–113 s | **291–508 s** |
| `basketball`, cached roster | 0 s | ~92 s | **~100 s** |

Stage A is ~78% of a cold fold and does not depend on `--by`, so `--roster-cache` turns the second
and later dimensions on a cell into ~100 s. The cache is **keyed on source/category and refused by
name on a mismatch**, and its age is printed on every reuse — a roster is a claim about which
markets are eligible, and markets resolve into a cell continuously.

## 6. What this rail still does not do

It inherits one omission from `calibration_cell_exact` rather than adding it: a cross-source
`e:<event_id>` virtual question sees only THIS source's markets, because `market_info` is scoped to
the roster. Per ruling 125 the mode-price and dedup keys are `(vm_id, source)`, so the only
source-blind key left is the representative window — read only on the non-multi branch, which a
cross-source `e:` never takes. Stated rather than silently inherited.

`--by ladder` is refused by name: it is an id-RANGE dimension handed `lo`/`hi`, and this rail has no
id ranges. Running it would silently fold an empty arm.

## 7. Guards

`backend/tests/test_calibration_whole_vm_fold_p125.py` — **63 tests**, organised around the four
structural premises rather than around the functions, because every one of them can be broken by an
edit that leaves the instrument printing a complete, plausible, well-formed table:

1. **Stage B is on the frozen path.** `frozen_vm_roster AS (` present; `group_sizes AS (` and
   `event_sizes AS (` absent — plus the **differential**, which asserts the id-range rail *does*
   contain them. Without the differential the first assertion could pass on both rails.
2. **The Stage A hash filter is on the OUTER select**, `market_info`'s WHERE carries only source and
   category, and Stage A selects only from `virtual_market`.
3. **Both refinements are exact**, asserted arithmetically over every residue and 400 `vm_id`s.
4. **A `vm_id` is never split**, an oversized unit is re-planned, and a single oversized question
   raises by name.

Plus: the three roster arrays are parallel and market-ordered (`unnest` zips positionally, so a
mis-order silently assigns one market's identity to another); a reply at the row cap is a failure
not an answer; `truncated` is read, not only `row_count`; the residual aggregate chunks on the
GROUPING key, not `fm.id` (chunking it on `fm.id` would cut groups apart and report a zero residual
with total confidence); this file registers **zero** new dimensions and leaves no sibling in
`sys.modules`; and the caps and arithmetic are **reused** from the rail rather than copied
(CAL-P115: an equal copy drifts on the next edit).

## 8. Reproduce

```bash
source ~/.claude/.env
# the residual bound alone, ~15 s
python3 backend/scripts/calibration_whole_vm_fold.py \
    --source polymarket --category basketball --bound
# the control: must stay at +0.00%
python3 backend/scripts/calibration_whole_vm_fold.py \
    --source polymarket --category cricket --roster-buckets 16 --buckets 16 --by none
# the repair
python3 backend/scripts/calibration_whole_vm_fold.py \
    --source polymarket --category basketball --roster-buckets 64 --buckets 64 --by none \
    --roster-cache artifacts/cal-p125/roster-basketball.json
```

Artifacts: `artifacts/cal-p125/whole-vm-{cricket,basketball}-*.json`.

## 9. What a reviewer should push on

* **The category-scoping residual is an UPPER bound, not the exact figure.** It is stated as a
  bound everywhere it appears, and on the one cell where both were computed the bound over-stated
  by ~40%. But `basketball`'s 19-row shortfall is *consistent with* the <= 27-market bound rather
  than *derived from* it — nobody has matched the 19 rows to specific markets.
* **`hashtext` is an internal PostgreSQL function with no stability contract across major
  versions.** It is used only to PARTITION a read, never to identify anything, so a change of hash
  would re-shuffle the residue classes and change nothing about the answer. Worth checking that
  reasoning rather than taking it.
* **Stage A's cost is measured on two cells only** (6,607 and 26,007 markets). `polymarket/baseball`
  at 64,558 is 2.5x the largest measured point and its planner behaviour is not established here.
