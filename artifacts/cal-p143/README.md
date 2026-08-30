# CAL-P143 — the 12-CAL repair is built and verified against the patched producer, and the reason it has sat for nine sessions is wrong on the second cell

**TL;DR.** Both decisions Fable staged are now *pre-built, applied nowhere, and proved to
work*: `git apply --check` exit 0 on both patches, and a verifier that rebuilds each
patched producer under `/tmp` and runs the shipped guards against it — RED on the live
chain, GREEN on the patched one. Three findings the directive did not know:

1. 🔴 **"The fix makes our number worse" — the sentence that has held 12-CAL since
   CAL-P122 — is cell-dependent.** `kalshi/entertainment` 5.21 → 6.30 (worse). Measured
   this session, `polymarket/economics` 3.90 → **3.68 (better)**. Two cells, two sources,
   opposite signs. The direction is not declarable and the guard now says so.
2. 🔴 **Landing D13 discards the staged futures bank** (`_calibration_population_ctes` is
   hashed into `_main_input_fingerprint`), manufacturing ~10 heavy rebuild beats — exactly
   the condition the class-B diagnostics timeout fires under. **D22 before D13, or both on
   one deploy.** The two asks were filed independently; they are ordered.
3. 🔴 **The freeze window is LOST arithmetically, not probabilistically** — 12 clean + 9
   remaining = **21 < 22** — and class B spent the last of the budget at beat 15.

The freeze is **NOT lifted** and no exception was taken. `precompute_calibration.py` md5 is
unchanged (`b4c10b41…`) and `git diff backend/` is empty; this session's diff is
`artifacts/` plus one citation fix in a prior session's ledger script.

---

## 1. D13 — the lost-losses repair, built and verified without touching the frozen file

`RULE-DESIGN-12CAL-lost-losses.md` is the document; the mechanics are three files:

| file | what |
|---|---|
| `12cal-lost-losses.patch` | the whole change — `clean_vms` + one `vm_stats` column + the census instrument + the CAL-P122 guard, **inverted rather than deleted**. `git apply --check` exit 0 |
| `test_calibration_lost_losses_12cal.py` | 10 guards, lands at `backend/tests/` |
| `verify-12cal-suite.py` | the proof that the guards guard something |

The predicate:

```sql
WHERE eligible >= 1
  AND (  has_winner >= 1
      OR (market_count = 1 AND total_outcomes = 1 AND graded >= 1) )
```

**`graded` is new and it is not the complement of `has_winner`.** `is_winner` is nullable
with a False default, so "not a winner" spans a graded loss and a row nothing ever graded.
Until this arm no predicate in the chain had to tell them apart, because a vm with no
winner never survived to be asked. Measured cost of the conjunct: **0 rows** — 19,127
truth-eligible rows in the newest 1.2 M outcome ids, none with `is_winner IS NULL`. It is
fail-closed defence that is doing no work today, which is the right kind.

### How a pre-build can be verified when the file it patches may not be written

`verify-12cal-suite.py` copies the producer to `/tmp`, applies the patch there, imports the
result under its own module name, and runs the suite's own assertion function against both
chains:

```
  live chain still carries the bare vm-level winner gate
  RED  on the live chain, as it must be
  GREEN on the patched chain
  boundary table: 6 cases
  census arm == producer arm on all 9 (market_count, total_outcomes)
  VERDICT: PRE-BUILD VERIFIED
```

A pre-built regression suite that has never been run against the thing it guards is a
document, not a control. The last line is the one that matters most: the class the
instrument calls `B_lone_claim` and the class the producer would publish are held to **one**
definition, so the measured number stays the number that lands.

## 2. 🔴 The generality run changed the ask

`GENERALITY-12CAL.md`. CAL-P131 found 508 published outcomes on `polymarket/economics`
that could not have lost, named `clean_vms` as the *candidate* clause and wrote *"a lead
for the lane that owns the fix, not a verdict."* Run on the producer's own chain one
predicate earlier: **78 eligible losers, uniquely dropped.** Inference → verdict.

```
  B_lone_claim (UNIQUELY dropped)       78    ECE 39.87   winrate 0.0%
  the class today                      514                       99.6% winners
  the class restored                   592                       86.5% winners
  the CELL today                    12,965    ECE  3.90
  the CELL restored                 13,043    ECE  3.68     <- BETTER
```

And a correction that matters for anyone sizing this repair from CAL-P131: its raw census
(1,817 graded losers among 3,844 single-leg markets) is **not** the repair size. 78 of them
clear every other published condition; ~1,739 do not. **A raw base rate is not a repair
size** — CAL-P141's lesson (two numbers over two populations) in a different costume.

`A_also_no_winner` on this cell is 1,754 rows, **22× the defect**, and is not part of it:
rung 1 owns those and the repair leaves them exactly where rung 1 put them. A census that
printed one number here would have claimed 1,832.

## 3. 🔴 D22 — and the try/except that cannot survive the failure it was written for

`d22-diagnostics-nonblocking.patch` + `test_calibration_soft_stage_d22.py` +
`verify-d22.py` (exit 0, all six checks). The mechanism lives in
`calibration_main_build.py`, which ruling 009 does **not** freeze; the frozen file takes
two call-site lines and a payload branch.

Two things found while building it:

* **`date_range` is already wrapped in `try:` and it is false comfort.** A statement timeout
  aborts the whole transaction, so the `except` catches the error and the phase's own
  commit raises anyway. `soft_stage` opens a savepoint, which is what makes the rest of the
  beat reachable.
* **The one-line version of this fix introduces a worse bug.** Setting
  `truth_by_class = {}` on failure makes every `.get` default zero and
  `contract_ok` returns **True on no evidence at all**. So the degraded value is `None`,
  the payload carries `census_observed` and `contract_status`, and a violation the
  aggregate DID find still outranks "unobserved" — verified in both directions.

## 4. The freeze window — `WINDOW-REPORT.md`

```
  12/15 clean   (3 misses; -1 of 2 budget left)   ###?##C#######B
  12 clean + 9 remaining = 21   <   22 required
```

Beat #15 (`13:42:18Z`) is `B_DIAGNOSTICS_TRUTH_CENSUS` — a `QueryCanceledError` on the
statement D22 is about. Beat #4 may have been the same class and cannot be recovered
(`last_error` is overwritten by the next failure). The shepherd kept classifying and
`pid 3019` logged throughout with zero restarts: a lost window is still the only
measurement of the producer that will exist when D22 is answered.

**The next window cannot start clean while the class is live**, so the sequencing is
answer D22 → land it → *then* re-baseline. A window opened before the repair measures the
defect, not the producer.

## 5. The four refused cells, and the one the ledger cannot see

`refusal-register.py` / `.txt` (exit 0). The ledger is keyed on the BOARD; the register is
keyed on the REFUSAL, and that inversion is the finding:

```
  kalshi/entertainment   CAL-P129  holdout                  rank 7
  polymarket/golf        CAL-P130  retention                rank 12
  polymarket/economics   CAL-P131  no structural dimension  rank 15
  polymarket/tech        CAL-P132  exhaustive lattice       OFF THE BOARD
```

**A hold that leaves the board is resolved; a refusal that leaves the board is still a
refusal** — it is a durable finding, and the next session to reach that cell needs to know
the 2^k lattice was already searched at `--min-rows 1`. Also fixed: two of the ledger's
three refusals cited the string `"refused with measurement"` — a disposition wearing a
citation's clothes, while the documents sat in `cal-p130/` and `cal-p131/` unreferenced.
`artifacts/cal-p140/hold-ledger.py` now cites them; its numbers are unchanged (exit 0).

## 6. Inherited: the uncommitted CAL-P142 window

`artifacts/cal-p142/` was on disk untracked when this session opened — a window that ran
`07:12–09:12Z` and ended without committing or writing a README. It is committed here
**as inherited, in its own commit**, per gotcha #52 (no orphan WIP; never reconstruct by
archaeology). What it contains, read rather than vouched for: `polymarket/baseball` added
to the payload-basis table (14 cells, 465,321 rows, 50.3% of the published curve), a
re-run reconciler, row-path floor-cost passes, and a `polymarket/soccer` fold that **failed**
— `RuntimeError: Stage A residue 131101 mod 524288 irreducible at depth 13`. Nothing in
CAL-P143 rests on any of it.

## 7. What this queue did NOT do

* **Landed nothing.** Both patches are artifacts. No freeze exception requested or taken.
* **Did not answer D13 or D22** — they are Alex's, and the pre-build exists so the answer
  is cheap, not so the answer is assumed.
* **Did not extrapolate the repair board-wide.** Two cells measured, 45 unmeasured and
  PARKED (CAL-P122-1). Two cells with opposite signs are not a direction.
* **Did not re-baseline the freeze window**, and §4 is why that would have been the wrong
  move today.
* **Did not finish `polymarket/esports`** — the census was still sweeping at hand-off
  (chunk 34 of 60 after 25 min; `kalshi/economics` queued behind it). Logs are in this
  directory and either resumes with one command.

## 8. Gate

`pytest -k "calibration or bookmaker or ladder"` — see `gate.txt`, which records the exit
code on its own line rather than relying on a summary line (gotcha #124). Zero backend
files changed, so the expected result is byte-identical to CAL-P136…P141.

`python3 -m ruff check artifacts/cal-p143/*.py` — **All checks passed**; `py_compile` OK on
all five new scripts.

## Evidence

| file | what |
|---|---|
| `RULE-DESIGN-12CAL-lost-losses.md` | §1 — the D13 design, the landing cost, the fabricated-loss blind spot |
| `12cal-lost-losses.patch` / `land-12cal.sh` | the change and the landing procedure |
| `test_calibration_lost_losses_12cal.py` / `verify-12cal-suite.py` / `suite-verification.txt` | the regression controls and the proof they are red-then-green |
| `GENERALITY-12CAL.md` / `missing-losers-polymarket-economics.json` / `census-poly-economics.log` | §2 — the second cell |
| `d22-diagnostics-nonblocking.patch` / `test_calibration_soft_stage_d22.py` / `verify-d22.py` / `d22-verification.txt` | §3 |
| `WINDOW-REPORT.md` / `window-log-snapshot.jsonl` | §4 |
| `refusal-register.py` / `.txt`, `hold-ledger.txt` | §5 |
| `gate.txt` | §8 |
