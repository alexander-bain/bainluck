# #10664 — exact-head CodeQL refusal correction

PILLARS: TRUTH / FORMATTING. SHIP: coherent Polymarket game quotes reach readers with fewer serialized database waits.

Previous exact head `5e2c80a463d79421126993c99b21024f91dc03bb`; main CI37591713264 completed SUCCESS, but CodeQL check112696188132 refused three new test-file alerts. Root's merge gate correctly remained STOP; no offer entered intake and no merge/deploy occurred. CERT3997 covers the old head only and is not authority for this new commit.

All three annotations were in `backend/tests/integration/test_pm_bulk_price_write_10664_pg.py`:

- L310, failure, assert side effect: the awaited actual write was evaluated only inside assert. The fixture's writes and completion waits now execute outside asserts; assertions check their returned boolean values.
- L21, warning, mutable imported attribute: a direct `get_task_session` import could ignore later module replacement. The fixture imports `app.tasks.base` as a module and reads `task_base.get_task_session` when entering the session, so the current mutable binding is observed.
- L368, notice, no-effect statement: bare `await pending` is replaced with the existing rig's bounded `asyncio.wait_for(pending,2)` cancellation wait, preserving the expected CancelledError and making a hung cancellation fail within the control's budget.

No alerts were dismissed, suppressed, waived or bypassed. No application file changed: all `backend/app/` bytes equal5e2c80a463, with focused polymarket_ws/live_blend_refresh hashes retained in `codeql-correction-boundaries.json`. The candidate's SQL/current-source write_chunk and performance/plan evidence remain unchanged. No new performance corpus or broad scan ran.

Affected gates against frozen corrected source: **47 passed /0 skipped**: all eight actual-source PostgreSQL controls, startup4, and existing CI execution manifest35. Evidence `codeql-correction-pg.txt`. New-test Black check and git diff check passed. Frontend build exit0; typecheck gate readback is retained in `codeql-correction-frontend-typecheck.txt`.

Private PostgreSQL17 cluster used a UNIX-only socket, port55493, shared_buffers16MB. Owned lifecycle/PID/data directory recorded in `codeql-correction-lifecycle.json`; stopped=true and temporary directory removed after owned server stop. No other service, IPC, cluster or data was touched.

Independent exact-commit delta acceptance and full hosted CI/CodeQL for the successor head remain required; the prior successful main CI and prior CERT3997 do not pay them. Root owns routing and fresh merge gate/Integrator offer. Heavy reach remains LOADED as previously recorded; no release/carriage claim changes in this test-only correction. No merge, deploy, production/browser/phone/reader acceptance.
