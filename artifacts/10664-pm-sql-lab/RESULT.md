# #10664 Polymarket `write_chunk` SQL lab — RETURN: DEPENDENCY (no timing claimed)

PILLARS: TRUTH / FORMATTING · SHIP: a coherent Polymarket game price reaches the page with fewer database waits.
lane1b · branch `codex/10664-pm-sql-lab` · base master `779da46f8b8e20a7a380db77be259dffaa433b77` · 2026-10-07 00:15 PT (07:15Z)

## Verdict

**Dependency, not a speed result.** The candidate patch and the full parity and timing harness are built. The harness
could not run against PostgreSQL in lane1b's environment: this lane's process sandbox denies System V IPC control,
so a private cluster cannot start. No elapsed-time, lock-window or plan claim is made. The statement-count reduction
below follows from how the code is built, not from a measurement.

**What unblocks it:** run `python3 tools/live-speed-lab/pm-sql-lab.py` from this worktree in an environment where Root's
`price-lock-prototype.py` private-cluster pattern runs, which is the Codex environment. It writes `artifacts/10664-pm-sql-lab/results.json`
and exits 0 only if every parity scenario matches. Its database phases have **never executed**, so expect harness bugs on the
first run. The dry-run phases pass.

## Candidate (`tools/live-speed-lab/pm-sql-candidate.patch`, applies at 779da46f)

The per-outcome `UPDATE … RETURNING` loop in `write_chunk` becomes one statement, `chunk_price_update_stmt(chunk)`:

```sql
WITH locked AS MATERIALIZED (
  SELECT fo.id, given.ord, given.price, given.compared
  FROM unnest($1::INTEGER[], $2::NUMERIC(7,6)[], $3::FLOAT[]) WITH ORDINALITY AS given(id, price, compared, ord)
  JOIN futures_outcomes fo ON fo.id = given.id
  ORDER BY given.ord FOR UPDATE OF fo)
UPDATE futures_outcomes SET current_probability = locked.price, last_updated = now(),
  price_changed_at = CASE WHEN CAST(current_probability AS NUMERIC(7,6)) IS DISTINCT FROM CAST(locked.compared AS NUMERIC(7,6))
                          THEN now() ELSE price_changed_at END
FROM locked WHERE futures_outcomes.id = locked.id
RETURNING locked.ord, id, market_id, last_updated, price_changed_at = last_updated AS quote_moved
```

What it is designed to preserve. Each point is checked by the harness, and none has been run on PostgreSQL yet:

- **Same set clause and binds.** The baseline binds the stored price as `$n::NUMERIC(7,6)` and the change comparison as `$n::FLOAT`
  (compiled under asyncpg). The candidate carries both arrays, so rounding and `price_changed_at` cannot drift. The shared
  `price_changed_at_value` gains one branch to accept a column; its scalar SQL is byte-identical (dry-run control).
- **Same row-lock order.** `ORDER BY ord … FOR UPDATE` locks in chunk (buffer) order, because LockRows sits above Sort, which is
  what the per-row loop did. Harness scenario `held-row-*` probes with NOWAIT while the write waits: positions 0-2 should be
  locked and 4-7 free in both arms.
- **Same coverage.** A vanished id joins nothing and returns nothing, as before. `ord` is returned and rows are walked in chunk
  order, so `queue_market_change` calls, and therefore frames, match the baseline's order.
- **Unchanged:** the rerank statement, commit-then-publish, buffer `== prob` removal (newer input survives), and the
  failure/cancel paths. The dry-run AST check shows `write_chunk` is identical outside the replaced price block.
- **One prepared statement for every chunk size.** It always has 3 array parameters (dry-run control). Do not read that as
  the same cost as `executemany`; no `executemany` claim is made.

Statement count per chunk of N rows, from construction (not timed): baseline N price UPDATEs + 1 rerank, candidate 1 + 1.
BEGIN and COMMIT are the same in both. A full 500-row chunk goes from 501 statement round trips to 2. Whether that
shortens the receipt-to-stamp interval in production, and by how much, is **unmeasured**.

Observed, unchanged by the candidate: the `write_chunk` price UPDATE has **no settlement guard**. A settled row (`is_winner`
or `resolution_source` set) is written if its outcome id is buffered. The withdrawal path does guard. The harness keeps settled
rows in the corpus so both arms are shown to behave the same; whether the price write *should* refuse is a separate question.

## Harness (`tools/live-speed-lab/pm-sql-lab.py`)

- Private PostgreSQL 17: `initdb`/`pg_ctl` in a temp dir, own socket and port 55464, stopped on exit. Schema comes from the
  models (`create_all`) plus the psql- and migration-only indexes (rank, last_updated, (market_id, probability_change_24h), trigram on name).
  The futures_outcomes table has no user triggers. The table holds 240k rows: 100k binary markets, 2k twenty-leg fields and 50 settled markets.
- Both arms run the **exact** `write_chunk` lifted by AST from source: baseline at the base sha, candidate at base + patch.
  Both use the real `get_task_session` (lent engine), real `queue_market_change`, real rerank, and the real `publish_committed_market_changes`
  over a recording Redis stand-in. Each published frame is checked visible from a *different* session, as post-commit proof.
- Parity scenarios. Each runs on its own template copy per arm with identical inputs, and compares full rows (timestamps
  normalised to unchanged / k-th write clock), frames, return values, stats and the remaining buffer:
  `corpus-{1,32,128,500}` (moved, unchanged, precision-equal and half-way-rounding prices, vanished ids, settled rows, a field
  market, two successive writes), `rollback-32` (numeric overflow mid-chunk), `held-row-newer-input` (a concurrent committed
  write of the held row at the chunk's own price, which must not count as a move, plus newer buffered prices that must survive),
  and `held-row-cancel` (a recycle cancels the flush while it is blocked).
- Timing runs only if all parity scenarios match. After warm-up, 5 alternating pairs per size are timed, with every
  observation kept: wall time, statements, price SQL ms, rerank ms, lock window (first price statement to first publish),
  `pg_stat_statements` server exec/plan totals, and an `EXPLAIN ANALYZE` of the 500-row candidate plus `EXPLAIN (GENERIC_PLAN)`.
  The generic plan matters: a prepared statement switches to it after 5 runs, and the patch must be rejected if that plan
  seq-scans `futures_outcomes`. Unix-socket timings understate network round trips and must not be quoted as production latency.

## Gate: focused tests (`focused-tests.json`)

40 test files that reference the PM consumer, plus the stamp and push tests. Base: 832 passed, 29 skipped. With the patch:
**62 failed** / 770 passed. Grouped by test harness, none is a demonstrated semantic regression and none is ruled out either:

| group | tests | cause | composition cost |
|---|---|---|---|
| SQLite-backed consumer suites (`…open_contract_prices_9484` + importers, `…market_change_hooks_9484`) | 25 | SQLite cannot parse `unnest … WITH ORDINALITY` | a dialect fallback (per-row on SQLite, which leaves the production path untested there) or porting to PostgreSQL rigs |
| fake sessions decoding one UPDATE per outcome (q491, q489, 8403, q490, q500, 9934, 2471, 837; 9733/9913 importers) | 35 | read `params["id_1"]` / `["current_probability"]` | a shared decoder that also zips `chunk_ids` / `chunk_prices` |
| static write-path AST guard (`test_ws_fast_lane_wiring`) | 2 | the set clause now lives in a module-level helper outside the scanned path | nest the builder in the consumer, or follow module helpers |

So, even if the PostgreSQL parity passes, landing this is not a one-file change: about 60 tests across 15 files need their
harnesses adapted. That cost should be weighed against a saving nobody has measured yet.

## Environment incident (lane1b's fault, Alex-ask filed)

Diagnosing why the cluster would not start, three probes left System V IPC objects behind that this sandbox cannot
remove (`shmctl`/`semctl` are denied): shared-memory segments **65541** and **65542** (56 bytes each) and semaphore set
**65569**. The machine's shared-memory ID table now reads full. Removal needs an unsandboxed terminal:
`ipcrm -m 65541 -m 65542 -s 65569`. A reboot also clears them. The shim tried along the way was deleted. No PostgreSQL
process was left running.
