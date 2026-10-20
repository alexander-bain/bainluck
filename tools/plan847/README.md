# #847 plan-only binding

PILLAR: TRUTH. SHIP: operators see the full stored guess-family count without losing the winner-coverage cache to an unreviewed expensive query.

This tool can EXPLAIN exactly two frozen statements, once, under a separately reviewed fresh admission: the producer's current winner-coverage query (`query3`) and the proposed full-family replacement (`candidateC`). It exists so Root can see both estimated plans before choosing whether candidate C may replace query3. **Nothing in this directory authorizes running it.** Green tests, a merged PR or this README grant no production connection.

## What is bound

- `packet/` holds byte copies of the sealed #847 admission packet: `SEAL.json` (sha256 `f3f2f3fd…6657f8`), `MANIFEST.json` (`34d0e506…eaf5c`), `query3.plan-only.sql` (`bd54471e…cfc72`), `candidateC.plan-only.sql` (`7d5f57e5…5a1a`). Source pin `0c544ac1`; producer blob `ed6a7a11`, authority blob `e0ce5f93`. `contract.packet()` refuses any changed byte.
- Executed statements are verbatim substrings of the sealed files: per plan `BEGIN TRANSACTION READ ONLY`, the two `SET LOCAL` timeouts, one fixed guard check (the database must report `on / 2s / 500ms`), `EXPLAIN (FORMAT JSON)` and `ROLLBACK`. Never ANALYZE. query3 runs first, and the first failure stops everything.
- One monotonic **15 s** wall covers everything from the first line of `run_attempt` to its return, with cleanup reserved inside it. One cumulative **524,288-byte** ledger covers child stdout and stderr, every receipt byte (temp files included) and the owner-return metadata.
- The child's share of that ledger is fixed before it starts and handed to it as `output_budget`. The child charges every byte it writes to its parent against that one budget **before** the write: its records, its refusal record (whose size is held back from the start), and everything written to its fd 2 from `child.py`'s first statement on. fd 2 is pointed at a private pipe that the child drains and forwards within the budget at each record and before it exits. So bytes the worker has not read yet are still inside the ledger. Once the child is gone, the worker drains both pipes to EOF, so `received_bytes` is every byte the child wrote, not what was read before a refusal.
- Each admission allows one attempt: an `O_EXCL` marker is created before anything spawns.

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

There is no CLI, no SQL, subject, cap or timeout argument, and no credential retrieval. `python3 supervisor.py` exits 2 and does nothing, and importing the modules does nothing. The credential reaches the child on stdin only. It never appears in argv, the environment, output or receipts. The DSN supplies the target, and the tool forces `sslmode=require`.

The admission binds: `binding_sha256` (`contract.binding_sha256()` over `contract.py`, `child.py`, `supervisor.py`), the seal, the manifest, both SQL hashes, the exact limits, `admission_owner`, `controller_session` (must equal `owner`), and a window of at most 600 s. The window must contain the entire 15 s attempt and must not touch `:34–:47` UTC (the producer's hourly `:35` run plus its hard limit). It also needs five prerequisite receipts (`main_carrier`, `heavy_carrier`, `source_equality`, `quiet_window`, `measurement_owner`), each `{ref, sha256, observed_unix}`, observed no more than 900 s before the window opens.

## What this tool cannot do

- It cannot verify that the declared prerequisites are true. It refuses booleans and digest-less names and copies the declarations into the receipt as `prerequisites_declared_not_verified`. Fresh main/Heavy carrier identity, source equality, overlap and ownership have to be established outside the tool.
- The byte ledger bounds what this tool serializes. It does **not** cap libpq's internal or wire buffers: the driver holds each full result before the child sees it.
- Two kinds of child output cannot be charged before they are written: what the Python interpreter itself writes to stderr before `child.py`'s first statement (the ledger holds 4,096 bytes for it), and a library writing straight to fd 1 instead of through the child's records (libpq writes nothing there). The worker still drains both to EOF and counts every byte, and any such byte refuses the attempt. If they carry the total past the cap, `combined_output_bytes` reports the overrun above 524,288 instead of hiding it. That is a detected overrun, not an enforced bound.
- If something writes more to the child's fd 2 between two of its records than the private pipe holds, that writer blocks, nothing reaches the parent, and the wall ends the attempt as `NO_RESULT`.
- A disk receipt alone is never a result. A late summary, a stall, a stderr byte, an exit other than 0, malformed or truncated output, or any uncertain cleanup all return `NO_RESULT`. There is no retry.
- The owner releases everything it owns (worker group, pipe, selector) BEFORE success is eligible and before it stamps `elapsed_seconds`, so its own finalization is inside the one wall. Once the worker exists, any owner exception, a failed release, or a release that ends past 15 s returns `NO_RESULT` (`OWNER_SETUP_FAILED`, `OWNER_READ_FAILED`, `OWNER_CLEANUP_FAILED`, `OWNER_FINALIZATION_LATE`). The first failure is the reason, and a later one never replaces it.
- It cannot force a hard return if the owner process itself stalls inside the OS (a `close`, `kill` or `waitpid` that does not come back). Python cannot interrupt that, so the return may come late. A late return is still measured and still `NO_RESULT`, and `contract.accept` refuses it. It is never a late success. An asynchronous signal (for example Ctrl-C) landing between `fork()` returning and the owner's cleanup block is also outside what Python code can cover.
- It uses `os.fork`. Call it from a single-threaded process.

Tests: `backend/tests/test_plan847_binding.py`. They run the real supervisor, worker and child against a fake driver (`lib_plan847_fake_driver.py`) on a virtual clock, plus one real-time 15 s wall test. They make no network or database calls.
