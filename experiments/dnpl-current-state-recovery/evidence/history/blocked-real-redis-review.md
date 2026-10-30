# Independent review: real Redis follow-on remains blocked

Reviewed 2026-10-21, after the single supported escalation attempt. This is a boundary and provenance receipt, **not real-runtime acceptance**.

## Result

Official Redis 7.2.16 was acquired at commit `335554f18caf7bbf6b0ac2b3548133d750f00a1b` and compiled workspace-locally. I independently verified that checkout commit, the resulting binary hash, and the frozen Lua hash. The initial owned Redis process exited before serving because private Unix-socket creation returned `Operation not permitted`. The builder's saved escalation receipt reports that the execution wrapper then failed before launching the same Unix-only command because its sessions path was read-only. No alternative transport, security change, or restricted-path access was attempted.

**Zero real Redis Lua, OOM, concurrency, or numeric-boundary cases executed.** There is no `results.json`; the initial harness output is empty, not a test pass. A read-only process inspection found no remaining redis-server process. Temporary-directory removal is recorded by the builder; I did not witness the original cleanup.

## Reviewed scope

The corrected but unexecuted harness declares 21 unique test methods and passes a syntax-only AST check. It is scoped to its own compiled binary, a private temporary Unix socket, port 0, no persistence, and an owned subprocess. It verifies INFO process identity and runtime settings before cases. Maxmemory changes target only that disposable process; no eviction-policy or host setting change is proposed. Cleanup is registered immediately after successful process creation. Explicit subscription ACK and actual unittest outcome accounting replace the original blocked harness's weaknesses.

The corrected test file has not been runtime-validated. Its sampled concurrent schedules are not exhaustive. Explicit DEL controls demonstrate prerequisites under simulated independent key loss, not actual eviction/failover. Caller-provided status controls do not execute SQL transactions. Separate error/pcall microprobes are not exact-candidate OOM evidence. The OOM test records observations rather than asserting model equivalence.

## Remaining source-based concerns

I independently inspected Redis's bundled `LUA_NUMBER_FMT` (`%.14g`) and its `scriptVerifyOOM` / `SCRIPT_WRITE_DIRTY` logic. These support two concrete hypotheses requiring a permitted runtime: large distinct epoch values may collapse when converted with `tostring`; and the legacy script's early DEL may permit subsequent allocation beyond maxmemory rather than produce the fake model's injected HSET error. Neither was observed in Redis here. Prior deterministic Lua-model passes do not resolve either boundary.

The smallest next action is to execute this frozen harness in an already-permitted disposable Redis environment and interpret its actual outcome plus OOM observation fields. No further launch was attempted here after the wrapper failure. The prior atomic packet and implementation remain unchanged; this receipt neither expands their authority nor introduces a timing or deployment claim.

## Verified identifiers

- Redis binary SHA256: `304e1a2ed1bb51bf62592a68d16a81a678d228599bacc039af832a5a6407d5dd`
- Both original and runtime-copy Lua SHA256: `037728b7af695bd6618071277c619e3b05a8f6ca394f12ff14a0f1e9a1fdb35e`
- Corrected unexecuted harness SHA256: `6a0d1320f58fde629503c186bca59b24baaba11744036d2e1b5a70be7a614984`
- Initial server failure log SHA256: `7b2c6f8778b29b2528f90d0cbd0cce231d6707ffe7694a08a0b8de996cdd92eb`
- Builder's escalation receipt SHA256: `f8063eaad2b7a70f0e5a5022db6c246d8a8ef983b3fca5a3a01d6643902cd267`

Evidence is under `atomic-redis-runtime/`: `RUNTIME.json`, `server-blocked.log`, `escalation-failure.txt`, acquisition/build logs, and corrected `tests/test_real_redis.py`. I read those files and source excerpts; I did not independently execute Redis or the escalation.
