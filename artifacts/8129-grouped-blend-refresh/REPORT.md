# #8129 — earlier completed groups publish live-game probabilities

PILLARS: TRUTH / FORMATTING.
SHIP: already-completed earlier groups publish probabilities and release their event-row locks before unrelated later groups finish stamp work.

Application implementation, ordinary author gates only; independent Tier1 exact-commit source/engine acceptance remains unpaid. Existing latency reservation16105. No production/provider read, fleet change, coordination cursor/status edit, merge or deployment.

## Change

Fresh-master base `b15a38e9dc9b6e053ebc4c2be119c95eaac15438`. In `backend/app/tasks/live_blend_refresh.py`, the actual due set after throttle/retry admission chooses the path: <=4 keeps the original single transaction/read path; >4 reads once, deep-copies only scalar column values while the preparation session is open, and passes the call-local map into contiguous ascending groups of four. No instance scratch map or scheduler/queue is introduced. Existing serialized consumer ownership and refresh state remain the ownership boundary.

Each successful group's commit installs existing authoritative last-write cache/slots/stamped bookkeeping, then synchronously records completion and resolves actual staged receipts before the first awaited publication. Cancellation during partial delivery preserves all committed facts; only uncommitted/unattempted work remains stamp debt. Earlier failed groups keep their existing debt/failed hold without a second receipt failure when a later delivery is canceled. Exceptions escaping a future delivery seam cannot requeue an already committed group. Existing delivery contract provides no replay/exactly-once guarantee; receipt stamp facts prove the database assertion, not transport arrival.

`_publish`, `_oriented`, `_maybe_snapshot`, snapshot-slot rollback context, and `run_flush_cadence` are byte-identical to fresh master (retained hashes in `source-boundaries.json`). The accepted PR10681 EVENT publisher is a separate source contribution; this fresh-master branch does not include it. Integrator composition and independent acceptance of that exact composed source remain required. No publisher or cadence hunk is changed here.

Cold unproven orientation deliberately reads the later Event/peer view in the group's write session. It adds a real Event point read absent from the baseline's already-loaded ORM identity. The real-PG control pins that later peer view, real sportsbook odds, boolean verdict caching on new prices, and named-side proof overriding a cached flip. The named corpus's earlier27 SELECT observation does not cover this fallback and is not claimed as whole-branch cost.

## Ordinary gates

- New actual-application PostgreSQL integration gate: **16 passed /0 skipped**, `actual-source-pg.txt`. Real source reader/resolver/orientation/guarded stamp/savepoints/snapshot helper and model-installed revision trigger. Publication is an independent database/cache observer seam, not actual Redis/SSE/browser delivery.
- Actual admitted due counts1/3/4/5/12, including one fresh event plus adopted debt; expected transaction counts1/1/1/3/4. The small path adds no preparation transaction.
- Preparation-session exit failure and cancellation after actual reads, with staged TailReceipts: all eight events owed, prior lock retry immediately due, no phantom cache/stamp/snapshot rows, all owed chains retained.
- Outer pre-COMMIT failure rolls back only events5–8, while1–4 and9–12 survive. Real partial-group cancellation rolls back event5's provisional stamp/snapshot and restores its slot. First-pass `stamped` agrees with actual committed rows/cache/slots; existing snapshot attempt counters are not upgraded to committed-only counters.
- Partial publication cancellation after first group's successful COMMIT sends one frame, preserves all four stored stamps/slots/stamp receipts, and retains only5–12 as stamp debt. Later cancellation after prior failed group does not double-count that group's commit failure.
- Foreign lock on event6: earlier1–4 publish after COMMIT; sibling writer updates committed event1 under its own100ms lock budget and rolls back its probe; only6 remains pending after lock timeout, then real `refresh_pending` succeeds.
- Stale observation refusal preserves sibling's revision/value, writes no snapshot/frame/cache for refused event6. Snapshot-helper failure for6 still permits all eight stamps/frames while only seven snapshot rows exist; its provisional throttle slot retains the existing contract.
- Orientation cost control: one small baseline cold event pays **0 Event point reads +1 odds read**; eight grouped cold unproven events pay **8 Event point reads +8 odds reads** inside actual orientation calls. Publication/snapshot/read-preparation queries excluded from this classification. Warm cached new price changes .3→.2 without another orientation read; named proof then stores .75 and discards the flip. The later peer view stores event2's .1 rather than the prepared view's .9.
- Inherited actual-engine gates: concurrent JSONB stamp/revision13, row-lock/deadlock4, stale poll/socket race4 — **21 passed /0 skipped** (`blend8129_*.txt`). Each file used its own database on the owned private cluster.
- Derived36-file regression set, startup and CI execution-manifest guard: **771 passed /0 skipped**; see `source-gates.txt` and exact `regression-files.txt`.
- Frontend build **exit0**; TypeScript gate **exit0,66 errors==baseline66**. No frontend source changes or dependency install.
- New PG test Black check, YAML/JSON parsing and git diff check passed. CI registration uses the existing shared database integration worker, fails on skips and requires all sixteen cases; ordered execution manifest updated with the same step.

The first broad regression invocation overlapped a formatting edit after pytest imported application code; four inspect.getsource guards then read shifted source offsets (a nested scalar helper), while767 behavior cases passed. The gate was rerun against frozen source; that earlier mixed-source invocation is not acceptance evidence. Earlier PG orientation fixture false starts corrected matchup direction and a Decimal-vs-float assertion, not application behavior.

Both owned PostgreSQL17 clusters used private UNIX sockets, no TCP listener, port55483 and16MB shared buffers. `cluster-lifecycle.json` / `inherited-cluster-lifecycle.json` retain owned data directory/PID and stopped=true; temporary directories removed only after owned server stop. No unrelated service, IPC or cluster was touched.

## Basis and unpaid boundaries

Independent finite implementation disposition: `/Users/bain/bainluck-dev/latency/.worktrees/10666-review/tools/live-speed-lab/reconnect-review-blend-grouped-8129/CANDIDATE-REVIEW.md`, pinned lab73161d9. Earlier groups4 lab timings are retained there and were not rerun or promoted to production benefit. Root's subsequent small-N evidence is separately retained at41f4ec9397. This source gate is bounded correctness work, not another prototype corpus or production census.

Groups of four can still hold healthy siblings in the same group; a waiting first group delays later groups. No unconditional event isolation, optimal group size, performance ceiling or production timing benefit is claimed. Failure injections precede COMMIT and do not establish ambiguous acknowledgement handling. Independent exact-SHA review/canonical acceptance, full hosted CI, accepted publisher/cadence composition, Integrator offer/merge/deploy, and served/browser/phone/reader acceptance remain unpaid.

## Root hosted-CI correction

Hosted run37596353151 isolated job112709999145 ran all fourteen #7594 tests successfully, then failed its accidentally raised sixteen-case guard. The same unrelated edit affected #9588. Root restored only those two existing counts/messages to fourteen; the new #8129 sixteen-case gate and application bytes are unchanged. The startup and cross-tier manifest checks pass27/27. An initial invocation named a nonexistent manifest test and exited4 without executing tests; it is not evidence. The actual corrected command and results are retained in root-ci-count-correction.txt. New exact-head hosted CI and independent acceptance remain required.
