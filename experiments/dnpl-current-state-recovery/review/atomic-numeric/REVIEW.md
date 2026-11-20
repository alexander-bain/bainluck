# Independent review: socket-free numeric encoding follow-on

Reviewed 2026-10-21. **The isolated candidate corrects the demonstrated Lua 5.1 integer-encoding defects within its declared unsigned safe-integer domain. This is not real Redis integration approval.** No Redis server/socket launch, OOM experiment, production change, browser run, or prior-packet edit was performed in this review.

## Useful finding

Redis 7.2.16's vendored Lua 5.1.5 interpreter reproduced two distinct integers, 100000000000001 and 100000000000002, both becoming `1e+14` through ordinary `tostring`. The same standalone comparison retained their distinct strings under Lua 5.3. Both interpreters also rounded the noninteger text `9007199254740991.4` to an apparently integral allowed value. Replacing serialization alone would therefore be insufficient.

Using the same deterministic command model for both frozen baseline and candidate, independent paired probes reproduced two harmful baseline ordering outcomes:

1. Sequence 100000000000004 followed by delayed 100000000000003 replaced retained NEW with OLD after the first sequence rounded down.
2. Preview sequence 100000000000006 followed by newer revoke 100000000000007 left the preview retained after its stored sequence rounded up.

The candidate kept NEW in the first case and retained the revoke in the second. These prove interpreter/model-level branch failures and their correction, not that deployed counters have reached these large values or that a deployed incident occurred.

## Candidate assessment

The candidate validates canonical ASCII decimal text and its lexical bound before conversion, then uses exact decimal formatting for stored/comparable authority integers. It preflights the counter before INCR, so exhaustion at MAX does not increment or reuse an owner and disables replay. It refuses malformed present stored epoch/sequence/base/expiry/floor instead of silently replacing an ordering barrier with zero. Healthy accepted live delivery remains available when retention-only metadata is invalid; malformed ownership does not bypass the source owner fence, and independent committed publication remains separate.

Supported integer domain is 0 through 9007199254740991, subject to existing operation constraints such as nonzero sequence and ttl <=60000. This is not arbitrary signed-64-bit support. Existing malformed/scientific-format authority is refused, not repaired or migrated. The tested time boundary assumes a trusted nonnegative Redis TIME value whose resulting milliseconds remain within the domain; the patch does not add arbitrary malformed-clock handling. The current issued+ttl comparison is not a demonstrated overflow over-admission bug when expiry is independently bounded by MAX.

The modeled bridge preserves incoming decimal bytes and models Redis's separate exact numeric-command-argument conversion and numeric INCR reply. It remains a model: actual Redis allocator/OOM admission, command errors, concurrency, persistence, failover, independent key loss, and SQL-to-Redis status/commit gaps remain outside this evidence. The blocked-runtime receipt remains unchanged and separate.

## Independently executed checks

- 14 focused Lua cases passed in the official vendored Lua 5.1 interpreter, and the same 14 passed under Lua 5.3. Cases include exact MAX owner/sequence/expiry, counter exhaustion without INCR, delayed older payload, commit-floor advancement, malformed arguments across operations, corrupt stored fences, retention-only fail-open delivery, and superseded-owner revoke handling.
- Four Python adapter / installed redis-py encoder checks passed without constructing a client or opening any connection. MAX epoch, sequence, base, committed floor and coverage floor encode as exact decimal bytes; unsafe/noninteger ordering is rejected before encoding; invalid expiry stays live-only.
- Both paired old/new ordering regressions passed their expected baseline-failure and candidate-correction assertions.
- All nine pinned inputs were verified unchanged before and after the final run. Pinned application source remains clean.

Builder-reported additional suites are 38 numeric cases, 43 inherited authority cases, 39 inherited race/negative-control cases, and 15 unchanged adapter cases. I inspected their saved passing summaries; these are not additional tests I independently ran. Neither those suites nor mine are real Redis-server tests.

## Reproduction

From the shared experiment root:

    atomic-redis-runtime/redis-source/deps/lua/src/lua review/atomic-numeric/test_independent.lua
    atomic-redis-runtime/redis-source/deps/lua/src/lua review/atomic-numeric/probe_ordering_regression.lua
    luatex --luaonly review/atomic-numeric/test_independent.lua
    venv/bin/python review/atomic-numeric/test_adapter_boundary.py

The interpreter source is official Redis release 7.2.16 at commit `335554f18caf7bbf6b0ac2b3548133d750f00a1b`. The standalone executable does not start Redis.

## Pinned identities and evidence

- Candidate authority.lua SHA256: `5b762702f38792028eb13887b9684711e4026839b9a4c6ae808971b538e3a4ca`
- Modeled bridge SHA256: `f0bf9a8966585fec9168afbc6b911e1611670c2d23c8f6fc651f3da237115969`
- Unchanged adapter.py SHA256: `28048285a63c374b29c99a93862e7d73ec08b5b81f2486fc5183b4b128767427`
- Vendored standalone Lua executable SHA256: `3693eb260b9225d6529c7c969085aa3b426daceec25d12df1f61221ed2d00fd2`
- Frozen prior authority.lua SHA256: `037728b7af695bd6618071277c619e3b05a8f6ca394f12ff14a0f1e9a1fdb35e`

This directory contains `final-inputs.json`, `independent-results-final.txt`, `independent-results-lua53.txt`, `adapter-results-final.txt`, `ordering-regression.txt`, standalone interpreter comparisons, their scripts, and the source-linked `source-boundary-audit.md`.

No blocking numeric defect remains in the inspected paths and declared domain. The concrete remaining acceptance gap is real Redis execution in an already-permitted environment, not another browser benchmark or a claim that the prior server restriction has been resolved.
