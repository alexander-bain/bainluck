# #10664 Polymarket bulk price writes

Pillars: **TRUTH / FORMATTING**. Ship: coherent Polymarket game quotes reach readers with fewer serialized database waits.

## Source and boundary

Base and freshly fetched origin/master: `f2c1b5f05e46228e8e5bd6b3c0b9588567190e55`. Root confirmed issue transfer to In Progress/root/Building before application edits. This contribution uses existing latency reservation session 16105.

Replaces only the price-writing block of `write_chunk` with the independently reviewed single-statement array/ordinality candidate. Stored NUMERIC(7,6), FLOAT comparison through the shared change-stamp helper, transaction-clock timestamps, ordered MATERIALIZED row locks, vanished-row coverage, and returned-row invalidation ordering remain the candidate's. Rerank, outer transaction, post-commit publication, latest-buffer preservation, error/requeue, and cancellation paths remain unchanged.

`candidate-currentness.json` proves the helper, write_chunk, and shared stamp helper are AST-equivalent to reviewed candidate patch `85b41876e7a852057b073a040697d0496c9abf82de7f6db9073a5d0859854f51` (formatting/documentation differ only). Scalar stamp SQL matches frozen source for None, 0, .3, .0512345678, and 10. Relevant application dependencies are unchanged between frozen base `779da46f8b8e20a7a380db77be259dffaa433b77` and fresh master.

There is no settlement guard on the existing PM price update. This candidate preserves that coverage; the new settled-row control deliberately proves the same overwrite. Withdrawal's separate guard is unchanged.

`quotes_unchanged` now counts unchanged observations returned by completed atomic price statements. Overflow returns no rows and adds zero, versus prior per-row observations before later failure. It is not generally committed-only: post-price rerank/commit failures may still leave increments. New gates pin zero on atomic overflow and one on later rollback. No claim of complete stats parity.

## Gates

- Derived current 49-file affected set: **1,033 passed / 4 skipped**, exit 0. `regression-files.txt` lists exact suites. This set includes every retained failure family and direct price-stamp/publisher references; the earlier lab did not retain its exact 40-file command. Four skips are pre-existing opt-in disposable Redis-server gates, explicitly listed in `regression.txt`.
- Converted authoritative real-transaction fixtures, inherited binary/complement/book-snapshot cases, and new bulk controls: **134 passed / 0 skipped**, exit 0 on private PostgreSQL17.
- Final new actual-engine controls after narrowing lock observation to the exact backend PID: **8 passed / 0 skipped**, exit 0. Cover stored rounding, NULL, unchanged/moved timestamps, vanished id, settled coverage compatibility, numeric overflow atomicity, post-price SQL rerank failure, actual outer commit-event failure, newer ticks on rollback and successful writes, concurrent deletion under a held row, real lock-wait cancellation, and publication with independent post-commit readback.
- Startup: **4 passed**, exit 0.
- Frontend build: exit 0. Typecheck: exit 0, **66 == baseline 66**.
- New test files Black-check passed; changed application regions formatted; diff-check passed; CI YAML parsed.

Recording-only fake sessions use one scalar/array price-bind decoder and still return no fabricated database rows. Existing deliberate failures, missing rows, retry/newer-input orchestration, and actual Session events/independent publication readback are preserved. No application SQLite fallback was added. AST timestamp guards follow the called module statement builder while retaining both assertions.

Root explicitly approved one narrow shared database-integration CI step for the converted rigs/inherited cases/new bulk controls. It fails on any skip; no workflow, scheduler, or fleet setting was added.

Own private PG17 cluster: PID 16761, data `/tmp/pm10664-pg-guard/data`, socket `/tmp/pm10664-pg-guard/s`, port 55473. Zero scratch schemas remained. Own cluster stopped and its data directory removed; lifecycle receipt retained. Other PostgreSQL services were untouched.

## Retained performance / plan evidence

Reused Root's corrected lab at `/Users/bain/bainluck-dev/lane1b/.worktrees/10664-pm-sql-lab`, retained harness/artifact commit `77b6d119d7`. Independent candidate review at `/Users/bain/bainluck-dev/latency/.worktrees/10666-review/tools/live-speed-lab/reconnect-review-pm-sql-10664/CANDIDATE-REVIEW.md`.

The accepted lab has 240k rows, 40 observations (five alternating matched pairs at 1/32/128/500 rows), actual extracted source chunks and actual publisher with recording Redis. Baseline→candidate median milliseconds: 1 row: 1.689→1.525; 32 rows: 17.408→8.066; 128 rows: 58.226→37.602; 500 rows: 256.189→129.735. Generic prepared plan uses PK indexes, not a full futures_outcomes sequential scan. These are retained local UNIX-socket synthetic observations only. The performance corpus was not rerun. Candidate AST fidelity ties this application's unchanged SQL to those retained plan receipts.

## Remaining owner gates

Draft PR, exact-SHA CI, Tier 1 independent source + engine review, then owner-controlled integration/release. This report is the author's source-gate handoff, not an independent cert. No merge, deploy, production collection, browser acceptance, or phone acceptance is claimed.
