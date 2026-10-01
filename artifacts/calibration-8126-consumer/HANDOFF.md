# #8126 — protocol-2 capture consumer: source handoff

PILLAR: TRUTH
SHIP: A settled Kalshi board whose venue declared each leg stops showing a blank result because its captured verdict reaches `futures_outcomes.is_winner`.

**State: source built and gated locally. NOT applied to production. #8126 stays open.**

## Files (all new)

| file | what |
|---|---|
| `backend/app/utils/settlement_capture_consumer.py` | pure: validate a protocol-2 capture, fold re-probes, plan per-leg writes |
| `backend/scripts/apply_settlement_capture_verdicts_8126.py` | bounded selection; dry run by default; `--apply` = lock, bank, compare-and-swap write, one transaction |
| `backend/scripts/restore_settlement_capture_verdicts_8126.py` | undo one `run_id` from its backup; drift refuses; `--restore-undrifted` leaves drifted rows standing |
| `backend/tests/test_settlement_capture_consumer_8126.py` | 64 tests; captures PRODUCED via `classify_kalshi` → `_capture_row` |
| `backend/tests/test_settlement_capture_verdicts_repair_8126.py` | 34 server-less guards (prod-app refusal, bounds, two-column write surface, purity) |
| `artifacts/calibration-8126-consumer/test_settlement_capture_verdicts_repair_8126_pg.py` | 12 real-Postgres tests: apply/bank/re-run/undo/drift/race/lock — **staged, not wired into CI** |

## What writes, what never does

- Writes `is_winner` + `resolution_source='api_settlement'` ONLY for a leg whose own disposition is `settled` with a bool verdict, joined by exact `external_id` to exactly one outcome of the capture's own Kalshi market, where `resolution_source IS NULL`.
- Never written or cleared: `settled_no_verdict` legs (an existing grade on one is reported as `no_verdict_but_graded`), open legs, unmatched / ambiguous / non-Kalshi legs, legs already graded (agreeing = skip; disagreeing = `conflicts_existing_grade`, never overwritten), legs where re-probes disagree.
- Refused whole: v1 captures, any `winning_outcome` in the non-verdict vocabulary (v1 `scalar` is the control), malformed or duplicated legs, a `settled_per_leg` board carrying an open leg.

## Gates (exact exit codes)

- consumer + repair units: `98 passed`, exit 0
- real Postgres 14 (`SEARCH_TEST_DATABASE_URL`, private schema): `12 passed`, **0 skipped**, exit 0
- implicated scanner guards + producer/authority tests (43 files): `1897 passed, 2 skipped`, exit 0
- `tests/test_startup.py`: `4 passed`, exit 0; ruff clean
- mutants killed: 10/10 consumer, 9/10 SQL (survivor: the restore's compare-and-swap, a second layer behind its own row lock — killable only with the lock removed, which is killed), 6/6 server-less guards
- `--help` on both scripts: exit 0 (no DB touched)

## Scope extension requested (coordinator)

To make the real-Postgres gate run in CI instead of only locally: move the staged file to `backend/tests/integration/test_settlement_capture_verdicts_repair_8126_pg.py` and touch three existing files — a `ci.yml` step in the search-recall `shared` group (same skip-detection pattern as #9850), its name in `.github/ci-postgres-groups.json`, and `COVERED` in `tests/test_pg_gate_seed_completeness.py`. It cannot go under `tests/integration` without those (`test_pg_gated_tests_are_named_in_ci.py` would red, correctly).

## Guarded apply and undo (for the LATER attended session — not authorized now)

```
heroku run:detached -a bainluck -- python3 scripts/apply_settlement_capture_verdicts_8126.py --capture-id 107429            # dry run; read the tallies
heroku run:detached -a bainluck -- python3 scripts/apply_settlement_capture_verdicts_8126.py --capture-id 107429 --apply    # backup + write; prints UNDO line
heroku run:detached -a bainluck -- python3 scripts/restore_settlement_capture_verdicts_8126.py --run-id <RUN_ID> --apply     # undo
```

Window mode: `--since 2026-09-27T10:40Z --limit 50` (max 500 captures, `--max-writes` 5000). Runtime DDL (`backup_8126_capture_verdicts`), attended invocation only — notice 47(c). D51(b): the undo line goes in the report and an alex-inbox note the same session.

## Remaining acceptance (from #8126, unpaid)

1. A settled multi-leg board serves its winner through the real API/page path — after an attended apply, on a named specimen.
2. A `settled_no_verdict` board is priced down and never graded — the "never graded" half is proven here; the price-down is the existing #7987 path, unchanged.
3. A v1 `scalar` capture is refused — proven (unit + real PG).
4. Backup exists and the one-command restore is proven before the apply — proven locally on real PG; the production backup exists only after the attended apply.
