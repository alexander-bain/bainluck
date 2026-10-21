# #1529 plan-only binding

PILLAR: TRUTH. SHIP: across sports, game pages put full-game winners in Game lines and preserve player and segment questions in the correct sections.

This tool can EXPLAIN exactly four frozen statements, once, under a separately reviewed fresh admission: the four 30-day phase-A statements of `scripts/capture_census.py --phase a --window 30` (games, markets, source split, fixture days). It exists so Root can see their estimated plans before deciding whether the census itself may run. **Nothing in this directory authorizes running it, and a plan is not a census.** Green tests, a merged PR or this README grant no production connection, and four plans pay no part of #1529's acceptance.

## The mechanism is plan847's, unchanged

`supervisor.py` and `child.py` are `tools/plan847/`'s files with name-only substitutions (`plan847` → `plan1529`, `#847` → `#1529`, and two prose phrases that said "both plans"). `backend/tests/test_plan1529_binding.py::TestMechanismIsPlan847` applies those exact substitutions to plan847's bytes and requires byte equality, so any other change fails. Everything plan847's README says about the wall, the ledger, the owner, the child's pre-charged budget, cleanup and its limits holds here word for word. The rebind exists so the two tools never share a module-cache key (`plan847_contract`), a receipt directory or a receipt schema name.

## What is bound

- `packet/` holds the sealed four-statement packet: `SEAL.json` (sha256 `a7774e43…e1c8`), `MANIFEST.json` (`7995faca…3577`) and four plan-only files. Source pin `7e60a65a`; `backend/app/utils/capture_census.py` blob `f56c31c1`, `backend/scripts/capture_census.py` blob `d6cb6c95`. `contract.packet()` refuses any changed byte.
- Each statement is `EXPLAIN (FORMAT JSON)\n` plus the library's own output for `window=30`, stripped of surrounding whitespace and its one trailing `;`. No other byte differs; `TestSourceEquality` proves it against today's library and fails if the library drifts. All four must begin with the same game CTE, carry one `INTERVAL`, and contain no `LIMIT`, `OFFSET`, `FETCH`, `TABLESAMPLE`, `ANALYZE` or write verb.
- Per plan: `BEGIN TRANSACTION READ ONLY`, `SET LOCAL statement_timeout = '2s'`, `SET LOCAL lock_timeout = '500ms'`, the guard check (`on / 2s / 500ms`), `EXPLAIN (FORMAT JSON)`, `ROLLBACK`. Never ANALYZE. Execution order is the CLI's (games, markets, source split, fixture days); the first failure stops everything, and all four plans are required or the attempt is `NO_RESULT`.
- One monotonic **15 s** wall from the first line of `run_attempt` to its return, cleanup inside it; one cumulative **524,288-byte** ledger over child output, receipts and owner metadata. One attempt per admission (`O_EXCL` marker).
- The admission window may not touch `:14–:47` UTC of any hour: the accuracy rebuild (`precompute_calibration_main`, :15, 1560 s hard limit) and the backfill status cache (`precompute_backfill_winners_status`, :35, 660 s). That leaves `:47–:14`. The weekly calibration sentinel that runs these same four statements (Monday 06:20) falls inside the excluded band.

## Entry (inert placeholders; do not fill from history)

```python
supervisor.run_attempt(
    credential=<FRESH_SEPARATELY_AUTHORIZED_PRIVATE_IN_MEMORY_DSN>,
    admission=<ROOT_REVIEWED_FRESH_ADMISSION_DICT>,   # exact keys: contract.ADMISSION_KEYS
    owner=<THE_ADMITTED_MEASUREMENT_CONTROLLER_SESSION>,
)
# then, and only then:
contract.accept(<that return value>, <bytes of its receipt_path>)
```

There is no CLI. `python3 supervisor.py` exits 2 and does nothing; importing does nothing. The admission binds `binding_sha256`, the seal, the manifest, all four SQL hashes, the exact limits, the owner, a ≤600 s window and five declared (not verified) prerequisite receipts (`main_carrier`, `heavy_carrier`, `source_equality`, `quiet_window`, `measurement_owner`), each observed no more than 900 s before the window opens.

## What this tool cannot do

Everything listed under the same heading in `tools/plan847/README.md`, unchanged. In particular: the wall starts at `run_attempt`, so it does **not** cover admission work, credential setup or anything the caller does before the call; the ledger does **not** cap libpq's internal or wire buffers; an owner stall inside `close`/`kill`/`waitpid` can make a `NO_RESULT` return late (never a late success); it uses `os.fork` and needs a single-threaded caller. Also:

- It cannot run the census. EXPLAIN without ANALYZE shows estimated rows and costs, not actual cost, actual rows or spill. The census reads (`market_rows` returns one row per linked market) are a separate admission with their own budget.
- It cannot verify the prerequisites, the database role, TLS provenance or the controller's ownership; they are declarations copied into the receipt.

Tests: `backend/tests/test_plan1529_binding.py`. They run the real supervisor, worker and child against plan847's fake driver (statements re-keyed for these four), on a virtual clock, plus one real-time 15 s wall test. No network or database.
