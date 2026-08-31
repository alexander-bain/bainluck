# CAL-P135 — `--by mono` cannot read the Polymarket sports book at all, and on the one cell where it can it has the sign upside down

Published number **1.89 pp, FLAT** (twenty-first reading, population still `q268` /
`2026-08-29T00:36:47Z` — unmoved across twenty-one readings and fourteen sessions;
per §6e a re-publish is not a datapoint).

Freeze gate at session start: `2/24 clean, 22 misses, NOT_MET`. The freeze
HOLDS. Unchanged from CAL-P134's hand-off, and still a reading of a broken
producer — the writer fix (`fef05751`) is **still unmerged**, so queue 905 items
2/3/4 could not be started.

---

## 0. WHAT THIS SESSION DID, IN ONE PARAGRAPH

CAL-P134 parked "run `--by mono` on the POLYMARKET cells" as the next move and
named four: baseball (rank 1), esports (rank 3), soccer (rank 4), basketball
(rank 11) — 204,429 excess-outcomes between them. **That item is not runnable as
specified, and running it would have produced a confident all-clear on three
cells and an inverted rule on the fourth.** Three of the four cells are 100%
invisible to the instrument at *two independent sites*; on the fourth the
grammar does bite, and it binds the wrong half of `Over/Under`, filing every
rung with the opposite sign. The inversion is currently masked by the ambiguity
guard, and it detonates the moment anyone applies the obvious fix. This session
measured all of it, fixed the sign, and guarded it. **No rule design is banked.
STILL FIVE, unchanged for eight sessions.**

---

## 1. THE MEASUREMENT

`artifacts/cal-p135/polymarket-name-ladder-census.py`, offline, raw cell, row
pull cached to `rows-polymarket-<cat>.json.gz`. Counts are RAW-CELL (lesson 19).

| cell | markets | O/U-named | parsed by the grammar | carrying a `yes` leg | real multi-rung ladders | shipped-key families | condemned |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseball | 64,889 | 44,839 | **0** | **0** | 17,196 | 35 | 0 |
| soccer | 190,155 | 107,313 | **0** | **2** | 31,050 | 9 | 1 |
| basketball | 25,825 | 13,850 | **0** | **15** | 1,091 | 65 | 0 |
| esports | 102,194 | 25,432 | 19,766 | 17,874 | 2,594 | 51 | 2 |

**51,931 identity-keyed multi-rung O/U ladders across the four cells, and the
instrument can currently reach none of them.** A reader given only the
"shipped-key families / condemned" columns would have written these cells up as
clean. That is gotcha #53 and lesson 16 for the third source running, and the
census now prints the refusal columns next to the finding columns so the next
reader cannot make that mistake.

## 2. THREE INDEPENDENT BLINDNESSES, NOT ONE

**ONE — the grammar.** `NAME_GRAMMARS` was `(parse_threshold, parse_by_date)`.
Neither parses `Mexico vs. Colombia: O/U 160.5`: there is no direction word for
`parse_threshold` to anchor on and no date for `parse_by_date`. Basketball
parsed 152 of 25,825 markets (0.6%) — an all-clear over a book that is 53.6%
O/U by name.

**TWO — the price site, and it is the bigger one.** `MONO_ROWS_SQL` reads the
price off a leg literally named `yes`. Measured directly on the legs of 120
sampled O/U markets per cell:

```
  soccer      Over 120 | Under 120                      <- no Yes leg exists
  baseball    Over 120 | Under 120                      <- no Yes leg exists
  basketball  Over 112 | Under 112 | Yes 8
  esports     Over  73 | Under  73 | Yes 47 | No 47
```

So on soccer and baseball the row is dropped before the grammar is ever
consulted. **Fixing the grammar alone changes nothing on three of the four
cells** — this session proved that by re-running the census with the fix in
place: 107,331 soccer names now parse and the cell still yields **10** families,
because none of them carries a price the pull can see.

**THREE — the sign, and this is the one that would have shipped a wrong rule.**
On esports the grammar *did* bite, 19,766 times. It bound the `Under` half of
the compound:

```
  'Map 1 Total Rounds: Over/Under 24.5'
      ->  key 'map 1 total rounds: over/ <rung>'   direction 'inc'
```

`_NUM` permits only whitespace between the direction word and the number. The
`Over` has a `/` after it and cannot bind; the `Under` is adjacent and can. **The
very tightness that the module added to stop "g-over-nment" binding to "April
30" is what makes it pick the wrong half of "Over/Under".** The rung was then
filed as ascending — the inverse of the truth, since the Over price falls as the
line rises — under a key that had silently swallowed the word `Over`.

### 2a. Why nobody noticed, and why the obvious fix detonates

The inversion is invisible today because `duplicate_values` marks nearly every
one of these families ambiguous — Polymarket names sub-markets without their
match, so `Map 1 Total Rounds: Over/Under 21.5` is written identically for every
match in the book, and the shipped key merges them all. Measured: **100%** of
esports' name-only O/U keys and **49.2%** of basketball's span more than one
event. The largest single collapsed family is **5,811 markets across 409
events**. Ambiguous families are KEPT, never condemned, so the wrong sign
produced only 2 condemnations and looked like nothing.

The natural fix is to scope the family key to a real event identity, which
Polymarket hands us directly (`group_id` = `polymarket:{event.id}`, `event_id`
as fallback). Measured, with the sign still wrong, that turns 2 condemned
families into **1,296** and drops **13,840 markets** — and they are
disproportionately the ladders behaving CORRECTLY. With the sign fixed the same
scoping gives **814** condemned families and 9,315 markets, a substantially
different and largely disjoint set.

**A guard against a bad key was silently absorbing an entire book and reporting
it as a clean cell.** That is lesson 16 arriving through the safety valve rather
than through the grammar, and it is new.

### 2b. The falsification test for the sign

Names and prices only, so it is leakage-free. Identity-scoped esports families,
14,040 consecutive pairs:

| behaviour | pairs | share |
|---|---:|---:|
| price FALLS as the line rises (Over side, `DEC`) | 3,005 | 21.4% |
| price RISES as the line rises (what `inc` expected) | 1,397 | 10.0% |
| flat | 9,638 | 68.6% |

Among non-flat pairs the Over-side behaviour wins **2.15:1**, and the 3,005
falling pairs are exactly the `violation_pairs` the old direction reported —
i.e. the old rule was condemning the majority, physically-correct behaviour.
⚠️ The 68.6% flat rate is not explained and is worth its own look; a long run of
identical prices across rungs is the signature of placeholder pricing, and under
this module's non-strict law it is never condemned.

## 3. WHAT SHIPPED

* **`app/utils/ladder_monotonicity.py`** — `OVER_UNDER_RE` + `parse_over_under`,
  registered FIRST in `NAME_GRAMMARS`. The span covers the whole `O/U <line>`
  token so `blanked_key` blanks the entire compound; the direction is fixed at
  `DEC` by the containment argument rather than read off a word, which is the
  point, because the word this compound presents last is `Under`.
* **Span-containment suppression in `name_rungs`.** Where one grammar's span
  strictly contains another's, the inner parse is a fragment and is dropped —
  so one O/U line yields one descending rung instead of also yielding the
  ascending `Under 24.5` rung found inside it. Containment rather than overlap
  is deliberate: the two-dimensional valuation grid produces DISJOINT spans and
  must keep contributing to both its threshold and its date family. Guarded.
* **`backend/tests/test_ladder_monotonicity.py` — 116 → 135 guards.** Every name
  in them is copied from a real market in one of the four censused cells.
  Including `test_a_context_free_name_DOES_collapse_across_matches_and_that_is_measured`,
  which pins the collapse as a known limit so the census cannot be re-read as an
  all-clear.
* **`artifacts/cal-p135/`** — the census (which now reports its own refusals
  alongside its findings), both measured JSONs, and the cached row pulls.

Still INERT: `grep -rl ladder_monotonicity backend/app` returns only the file
itself. Every production statement this session ran was a SELECT through
`POST /api/admin/db-query`.

**Gate:** `pytest -k "calibration or bookmaker or ladder"` → **2,944 passed, 24
skipped, 0 failed** (130 s).

## 4. WHAT IS DELIBERATELY NOT DONE

The cells still cannot be folded, and two blockers remain — both measured above,
neither taken, because taking them without a fold to validate would be
architecture ahead of its ship:

1. **The price site.** `MONO_ROWS_SQL` must read the `Over` leg, not `yes`.
   Mechanical, and the leg census in §2 is the evidence it needs.
2. **The identity-scoped family key.** `read_name_ladders` needs an optional
   caller-supplied context so a Polymarket fold keys families by `group_id`.
   ⚠️ It must NOT be landed without the sign fix in this commit — §2a is the
   measurement of what happens if it is.

Only after both can `--by mono` fold these four cells, and lesson 20 says the
verdict is a hypothesis again at full strength until that fold runs: CAL-P133's
positive result at the name site on `polymarket/tech` predicts nothing here.

## 5. LESSON 22 — A SAFETY GUARD CAN SWALLOW THE POPULATION AND REPORT IT AS A CLEAN CELL

Lesson 16 is about a grammar that cannot see a book. This is its sibling one
layer in: the grammar saw 19,766 esports names, the key merged them across
hundreds of unrelated matches, and `duplicate_values` — a guard that is correct,
deliberate and load-bearing — marked almost all of it ambiguous and therefore
untouchable. The census printed "51 families, 2 condemned" for a cell holding
1,776 real ladders. **Every fail-safe is also a place where a population can go
to disappear quietly.** When a guard is doing its job, count what it caught and
publish that count next to the verdict; a guard that fires silently is
indistinguishable from a cell with nothing in it.
