# CAL-P141 — the board's two duplication instruments are one number over two populations, and the freeze window survived the night's first test

The window is **LIVE and still exactly reachable**: beat #8 published clean, so the
strip is `###B##C#` — **6/8 clean, 0 budget, 16 beats to go**, and 6 + 16 = 22.
Nothing triggered the report condition, so there is no window draft; the classifier
is running and supervised.

The freeze is **NOT lifted** and I took no exception. `precompute_calibration.py`
untouched — `git diff --stat` for this session is `artifacts/` only.

---

## 1. The watcher was already alive, and restarting it would have corrupted the log

The directive said *"Restart it first thing; CAL-P140's copy dies with its
session."* **It did not die.** PID 3019 orphaned to init (PPID 1) and was still
polling in the right cwd at `06:34Z`, 45 minutes after CAL-P140 ended.

That matters because the de-dup on `window-log.jsonl` is *"have I already logged
beat n?"*, evaluated at poll time. Two watchers waking inside the same 7-minute
poll both see beat n unlogged and both append it. The log is the half of the
window that survives a session; corrupting it to satisfy "restart it first thing"
is the worse failure, so I did not.

Instead: `watch-supervisor.sh` — checks every 60 s and starts a watcher **only if
none is running**. It has logged zero restarts, which is the correct outcome.
Beat #8 was classified by the original process at `06:55:25Z`.

| | |
|---|---|
| strip | `###B##C#` |
| clean / budget | **6 of 8, 0 of 2 budget left** |
| beats to go | 16 — every one must publish |
| report trigger | not reached (fires on the next miss, or at ~`22:35Z`) |

---

## 2. 🔴 THE TWO INSTRUMENTS ARE NOT TWO ATTEMPTS AT ONE NUMBER — AND I HAD IT WRONG FIRST

Under `calibration-908` option 1 the legal work is *"the highest-excess cell whose
INSTRUMENT cannot yet score it"*, so I went at the two `CANNOT DECIDE` cells,
20-CAL and 21-CAL. What came back was a problem with the instruments themselves.

The board has two things that both answer *"how many of this cell's rows are
duplicates?"*, they had never been compared, and they disagree by up to 36%:

| basis | instrument | its row count is |
|---|---|---|
| **payload** | `calibration_phantom_curve.py --cell` (CAL-P126, 12 cells) | the rows the curve publishes |
| **replica** | `inflation-census.py`, `outcome-grain-fold.py` (CAL-P139) | `_calibration_population_ctes` |

**My first draft called the cheap one defective and said so in a commit message.**
Then I read `outcome-grain-fold.py`'s schema and found its "exact" n is 41,086
against a payload of 45,240 — the fold is on the replica too. The disagreement is
not accuracy. It is **basis**, and nothing on either side says so.

The proof is arithmetic and `reconcile-duplication.py` re-checks it every run: on
the two cells whose population did not drift between the runs, the payload-basis
row count equals the census's own `payload_n` to **+0.000%**, while the replica
holds far fewer:

```
polymarket/basketball   exact 13,116  ==  census payload_n 13,116   replica holds 8,426
polymarket/hockey       exact  2,281  ==  census payload_n  2,281   replica holds 1,779
```

**Lesson: two instruments that disagree are not necessarily one right and one
wrong. Check what population each one counted before you call either a defect.**
This is CAL-P140's lesson 24 one turn further on — it read a gauge without the
function that resets it; I compared two numbers without the population each was
over.

### What the reconciler reports

```
cell                      payload  replica  basis gap   rowcov  outcov  mode
polymarket/basketball      1.7679   1.1347      35.8%   0.6424  1.0009  REPLICA_SHORT
kalshi/basketball          1.7578   1.4793      15.8%   0.8358  0.9932  REPLICA_SHORT
kalshi/baseball            1.7099   1.3049      23.7%   0.9971  1.3067  DISTINCT_INFLATED
polymarket/hockey          1.3659   1.0608      22.3%   0.7799  1.0042  REPLICA_SHORT
```

`DISTINCT_INFLATED` is the census's own documented caveat — chunking on `fm.id`
drops an identity group below the `>= 3` threshold, collapsing its `vm_id` and
manufacturing distinct outcomes. It shows on exactly one cell, the largest, which
has the most chunk boundaries. `REPLICA_SHORT` is the basis gap and is dominant.

**Why nobody caught it:** on `polymarket/baseball` — the one cell `calibration-911`
folded — the bases nearly coincide (replica short 9.2%), so the fold (1.651×) and
the census (1.654×) agree to 0.15% and both look right. Same instrument, 35.8% out
on the next cell, no warning either way.

The instrument exits **4** when the two bases order any pair of cells differently,
because a lower bound that preserves order is still usable for triage and one that
does not is not. **2 of 6 pairs are discordant.**

---

## 3. 21-CAL IS ANSWERED, AND IT DISCHARGES INTO 20-CAL RATHER THAN FREEING A CELL

CAL-P128 filed 21-CAL as *"routing note, no decision"* with a stated test: *"a
phantom measurement would say whether it is basketball's cause or a second one."*
Nobody had run it. I ran it — `calibration_phantom_curve.py --cell --source
polymarket --category hockey`, 402 s.

```
polymarket/hockey   2,281 published rows, 1,670 distinct, 611 phantom (26.79%)
                    copies agree: yes
row coverage        0.7799     <- CAL-P128 recorded 0.780
OUTCOME coverage    1.0042
```

**It is basketball's cause.** Both cells are `REPLICA_SHORT` with outcome coverage
at 1.00: the rail sees *every outcome* the payload publishes and simply does not
reproduce the payload's duplicate rows. So CAL-P128's `coverage 0.641` and `0.780`
— the figures that made both cells `CANNOT DECIDE` — are **row** coverages, and
they were read as the rail being unable to see the cell.

🔴 **But this does not free either cell, and it would be easy to claim it does.**
Hockey's ECE and σ are still computed over 26.79%-duplicate rows, exactly the
objection 20-CAL raises against basketball. 21-CAL discharges *into* 20-CAL: two
holds collapse into one question, and that question is the dedup on
`alex-inbox/calibration-911`. **Step 1 still selects the empty set — an eighth
session.** I did not invent a cell.

Disposition map extended with the citation, per the directive. The hold ledger now
credits one question with both cells: **20-CAL 26,340 outcomes, 4th on the question
board**, up from 16,395 and 6th. 21-CAL is removed with a comment saying why, not
silently — a routing note discharges on its measurement, and leaving it up would
show a hold nobody can clear.

---

## 4. `calibration-911` §5 ITEM 1 IS MOSTLY ALREADY DONE — BY MEASUREMENTS NOBODY ASSEMBLED

911's prerequisite 1 is *"extend §3 past one cell"*, and it nominates
`inflation-census.py`. It cannot: it is exact about a population the curve does not
publish. But the payload-basis measurements for twelve cells have been sitting in
`artifacts/cal-p126/` since that session, and adding hockey makes thirteen:

```
13 cells   420,081 published rows -> 266,137 distinct   36.65% phantom   1.5784x
           = 45.4% of the published curve's 925,466
```

Range **0.35%** (`polymarket/weather`) to **47.08%** (`kalshi/hockey`) — a 134×
spread, which is why there is no pooled factor in `payload-basis-table.txt` and why
the remaining 505,385 rows stay unestimated. Appended to 911 rather than filed
separately, per the protocol's one-draft-per-lane rule.

Each CAL-P126 cell is used only after it reproduces its own headline from its own
buckets (`sum(n_ship) == published_rows`, `sum(n_dedup) == distinct_outcomes`); all
thirteen do, and a file that did not would be skipped loudly rather than trusted.

---

## 5. What this queue did NOT do

* **No freeze exception, none requested.** D21 is Alex's and ungranted; §3's
  diagnostics re-order is 912's and was not touched.
* **No rule design banked, no cell worked** — there is still no legal cell.
* **Did not re-file the class-B or 12-CAL asks.** Both stay on 912.
* **Did not restart the watcher**, and §1 is why that was the careful choice.
* **Did not extrapolate the phantom factor** to the 54.6% of the curve nobody has
  measured. A 134× spread admits no pooled number.
* Nothing shipped. Artifacts only.

## 6. Gate

`pytest -k "calibration or bookmaker or ladder"` — **2,964 passed, 24 skipped,
19,249 deselected, 96 warnings in 133.84 s.** Identical to CAL-P136/137/138/139/140,
as it must be with zero backend files changed. Recorded in `gate.txt`.

⚠️ The run was backgrounded so `$?` was not captured, which gotcha #124 warns about.
The verdict here rests on the completed summary line instead: a pytest run that
prints `N passed ... in T` with no `failed` and no `error` ran to completion, which
is precisely what the exit-code rule exists to establish (127/137/143 produce no
summary line at all). Stated rather than glossed.

## Evidence

| file | what |
|---|---|
| `watch-supervisor.sh` / `supervisor.log` | §1 — the start-only-if-absent supervisor; empty log = never absent |
| `reconcile-duplication.py` / `.json` | §2 — the basis proof, the two modes, the ordering test, exit 4 |
| `cell-polymarket-hockey.json` / `phantom-hockey.log` | §3 — 21-CAL's measurement |
| `payload-basis-table.txt` | §4 — 911 §3 extended to 13 cells |
| `hold-ledger.txt` | §3 — 20-CAL at 26,340, 21-CAL discharged, still EXIT 0 |
| `inflation-2021cal.log` | the replica-basis run on both CANNOT-DECIDE cells |
| `scorecard.txt` | the board at `2026-08-30T04:35:25Z` |
