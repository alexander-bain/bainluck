# Source audit: canonical integers for the socket-free follow-on

Date: 2026-10-21. Reviewer scope: source inspection only. No Redis server was started, no socket was opened, no transport/settings were changed, and no frozen prototype or evidence packet was edited. This note does not establish Redis runtime, allocator, OOM, admission, isolation, replication, or latency behavior.

## Source identity and conclusion

The inspected Redis source is the local checkout at commit `335554f18caf7bbf6b0ac2b3548133d750f00a1b` (Redis 7.2.16), under `atomic-redis-runtime/redis-source`.

The declared integer domain, `0..9007199254740991` (`2^53 - 1`), is sufficient for exact IEEE binary64 integer values. It is **not** sufficient to make Lua 5.1's default number-to-string conversion injective, or to make `tonumber` validate the original input text. The follow-on needs both an exact decimal wire/storage contract and validation at every authority boundary.

The parent review independently executed a standalone-interpreter reproduction: see [Lua 5.1 output](interpreter-reproduction.txt), [Lua 5.3 comparison](lua53-comparison.txt), and [reproduction source](reproduce_interpreter.lua). Those are interpreter observations, not Redis-server observations. All further examples below are source-derived test oracles unless explicitly identified otherwise.

## Verified conversion paths

| Boundary | Source | Consequence |
| --- | --- | --- |
| Lua numeric representation | [luaconf.h](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/deps/lua/src/luaconf.h), lines 503–504 | Bundled Lua uses `double`. Every integer in the declared domain is exactly representable. |
| `tostring(number)` | [lvm.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/deps/lua/src/lvm.c), lines 47–54; [luaconf.h](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/deps/lua/src/luaconf.h), lines 522–523 | Default `%.14g` loses digits and may emit scientific notation. Distinct safe integers can acquire identical owner/storage strings. |
| `tonumber(text)` | [lbaselib.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/deps/lua/src/lbaselib.c), lines 53–59; [lvm.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/deps/lua/src/lvm.c), lines 35–40; [lobject.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/deps/lua/src/lobject.c), lines 90–99; [luaconf.h](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/deps/lua/src/luaconf.h), line 525 | Uses `strtod`, accepts noncanonical numeric spellings, and can round fractional text to an integral double. The Lua string is passed as a C string with no original length, so an embedded NUL can terminate parsing before trailing bytes. |
| Lua number used directly as a Redis command argument | [script_lua.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/src/script_lua.c), lines 813–835; [util.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/src/util.c), lines 591–618 | Redis explicitly avoids Lua's lossy string conversion: exact integral doubles use `ll2string`, otherwise its floating formatter. This safe path cannot repair a number already converted by `tostring`. A fake command bridge must not conflate these paths. |
| Redis integer command reply to Lua | [script_lua.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/src/script_lua.c), lines 237–250 | Redis's signed 64-bit reply is cast to Lua `double`. Integers outside the chosen domain must not be relied on as exact identities after this conversion. |
| Lua numeric script return to client | [script_lua.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/src/script_lua.c), lines 615–622 | Strings become bulk strings; numeric values are cast to C `long long`. Integral values within the declared domain are exact, but fractional values truncate and out-of-range values are not a supported contract. |
| Explicit decimal formatting | [lstrlib.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/deps/lua/src/lstrlib.c), lines 790–793 | `string.format('%.0f', n)` avoids exponent notation and 14-significant-digit truncation for already validated integral doubles in the declared domain. This is not a substitute for validating original input bytes. |

### Embedded NUL: precise scope

For a Lua string containing bytes `31 00 6a 75 6e 6b` (`1`, NUL, `junk`), `luaV_tonumber` passes `svalue(obj)` to `luaO_str2d`, not its Lua length. The latter accepts immediately when the conversion end pointer points to NUL. Therefore the baseline's `tonumber`-then-range check cannot prove that all input bytes belonged to the integer. A length-aware, anchored canonical decimal check before conversion rejects this case. This is a source deduction, not an executed Redis-server result.

## Minimal correct parsing and encoding contract

1. External numeric argument strings and persisted authority numbers use only `0` or `[1-9][0-9]*`, in ASCII. Reject empty strings, leading zeros, signs including `+1` and `-0`, whitespace, decimal points, exponents, hexadecimal, non-ASCII digits, NUL, and trailing bytes. Enforce the string contract at these boundaries. Redis ARGV/HMGET/GET values are strings or the documented missing sentinel; a fake must preserve that distinction.
2. Bound input length to at most 16 digits, then reject equal-length strings lexically above `9007199254740991`, **before** calling `tonumber`. A Lua pattern must use an explicit zero branch (`s == '0' or s:match('^[1-9][0-9]*$')`); Lua patterns do not implement regex alternation. A bytewise bound comparison avoids any dependency on locale collation.
3. Retain validated original decimal bytes when no arithmetic is required. For a computed value, use one checked exact formatter such as `string.format('%.0f', n)`. Its input must already be finite, integral, nonnegative, and at most MAX. Do not use `tostring`, implicit concatenation of numbers, `%.14g`, or a fixed-width integer formatter whose C integer width has not been established.
4. Cover **every** identity/storage path: claim owner, replay marker, owner comparisons in normal and read-error/uncached paths, retained sequence/base/expiry, commit floor, snapshot floor rewrites, and any computed values returned as strings. Fixing only the claim return or only HSET leaves other lossy paths.
5. Numeric replies such as INCR are a separate boundary: validate finite/integral/range. Explicitly checking actual numeric type and the expected increment makes the synthetic bridge contract stronger. A shared helper may handle strings and numbers if the numeric branch is used only for documented numeric replies; it cannot prove a canonical original spelling for arbitrary caller-supplied numbers.
6. Keep the response schema explicit. Returning validated Lua numbers for seq/floor/remaining preserves the baseline RESP integer shape safely within MAX. Returning canonical strings is also exact but changes that schema; tests and consumers must consciously account for it. Returning a fractional or unbounded computed number is not acceptable merely because the client displays an integer.
7. The Python adapter already requires `type(value) is int`, excluding bool and float, and bounds by the same MAX: [adapter.py](../../atomic-retention/adapter.py), lines 12–17. Serialize validated ints to canonical decimal bytes at the EVAL boundary. Do not loosen the adapter to accept `"1e3"`, floats, or booleans. Its ordinary integer arguments do not make the Lua script safe against noncanonical persisted data or direct EVAL calls.

## INCR and exhaustion

The baseline calls INCR before checking its result: [authority.lua](../../evidence/negative-controls/authority-unsafe-serialization.txt), lines 44–52. Redis INCR parses signed 64-bit integers and checks signed-64 overflow, not the application's MAX: [t_string.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/src/t_string.c), lines 601–633; [object.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/src/object.c), lines 876–906; [util.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/src/util.c), lines 430–501.

- Read the counter as exact bytes before incrementing, inside the same serialized authority operation. Explicitly distinguish a missing counter (the existing initialization policy uses zero) from wrong type/read error, negative, noncanonical, or out-of-domain content.
- If current counter is MAX, return the defined exhaustion/error result **without issuing INCR**. Preserve the counter and prior owner. Whether the replay marker is cleared on failed claim should remain explicit; the frozen prototype clears it before any claim attempt.
- Current `MAX - 1` may increment once to MAX; the canonical owner must be exactly `9007199254740991`. Its next claim must not consume MAX+1, round, wrap, reset, or reuse an identity.
- Redis's signed-64 overflow error is insufficient: INCR at application MAX succeeds at the Redis level and mutates the counter to MAX+1 before the old script rejects it. Repeated rejected claims can continue consuming signed-64 state.
- After the bounded pre-read, a successful INCR response must equal `prior + 1` within MAX. A later owner-write failure may leave a skipped epoch; do not undo/reset the counter to avoid a gap. Numeric fixes cannot prove recovery after independent counter loss, rollback, or failover.

## Sequence, floor, owner, and chain-cap integrity

| Boundary | Frozen source | Required behavior |
| --- | --- | --- |
| Owner/marker | [authority.lua](../../evidence/negative-controls/authority-unsafe-serialization.txt), lines 54–80, 89–99 | Only canonical current owner identities may authorize retention/replay. Equal noncanonical owner/marker strings are not proof of a valid owner. Preserve the intentional old-owner revoke live-delivery rule without allowing it to mutate current storage. |
| Current-owner sequence | Same file, lines 111–113 and 126–132 | Preserve exact seq and reject duplicate/older records. A present malformed seq must fail replay closed, not bypass the duplicate guard and admit an arbitrarily lower incoming record. A present zero seq is inconsistent with the nonzero offer contract even though zero is a valid general uint. |
| Same-chain expiry cap | Same file, lines 115–117 and 125–132 | Preserve the exact minimum cap, including across revoke. If an existing current-owner/same-chain cap is malformed or unexpectedly absent, do not silently skip it and retain a newly extended expiry. Publish live-only/fail closed according to the existing delivery contract. |
| Commit floor | Same file, lines 146–155, 163–174 | Distinguish an absent floor (initial zero) from present malformed floor. `uint(value) or 0` after canonical rejection can erase a previously positive floor and reopen older state. Never lower the floor. |
| Base/floor comparison | Same file, lines 177–188 | Exact persisted base and exact fresh-DB coverage are necessary for `coverage_behind_preview_base` and `newer_commit`; parsing rounded stored strings cannot recover discarded digits. |

Migration must be explicit: old scientific-notation or rounded storage cannot be made trustworthy just by accepting its numeric value. Different original integers may already have collapsed to the same string. For the socket-free candidate, reject such retained authority state and exercise the existing replay-disabled path rather than inventing a backward-compatible reconstruction.

Source-derived harmful examples for independent candidate tests:

- Claim counters `100000000000001` and `100000000000002` both stringify to `1e+14` under the baseline's formatter. This collision is also directly reproduced in the parent interpreter artifacts.
- Retaining seq `100000000000004`, then receiving delayed seq `100000000000003`, can admit the delayed value because the first stored seq rounds down to `100000000000000` before the duplicate test. Inspect payload/trace, not just the equal rounded stored strings.
- Rounding seq `100000000000006` up to `100000000000010` can suppress an actually newer seq/revoke `100000000000007` from retention.
- A rounded-down commit floor can admit a stale base/fresh-DB pair that should be behind the true floor; a rounded-up floor can reject valid newer state. Test exact floor preservation, not merely nondecrease of already-rounded values.

## Expiry arithmetic: defects versus hardening

The present-wall-clock timestamp magnitude is **not** a demonstrated numeric failure. TIME is emitted as two bulk integer strings by [server.c](https://github.com/redis/redis/blob/335554f18caf7bbf6b0ac2b3548133d750f00a1b/src/server.c), lines 4545–4548. The baseline converts seconds to milliseconds in [authority.lua](../../evidence/negative-controls/authority-unsafe-serialization.txt), lines 20–22, checks `expiry > issued + ttl` at line 91, and computes remaining time at line 186.

- Exact expiry storage matters throughout the declared domain. Default `tostring` can round an expiry upward and extend its cap, or downward and expire too early, at sufficiently large values. This is distinct from a claim about today's normal epoch-millisecond values.
- With canonical `expiry` and `issued` each within MAX and `ttl <= 60000`, `expiry <= issued + ttl` is logically safe even if the sum leaves the exact-integer domain: if the exact sum exceeds MAX, every permitted expiry is already below it; otherwise the integer sum is exactly representable. Do not report this as a proven over-admission defect.
- The equivalent check `expiry > issued and expiry - issued > ttl` keeps the relevant arithmetic within the exact domain without changing acceptance. Rejecting all `issued + ttl > MAX` would instead narrow the contract and differ from the Python adapter's exact-integer comparison.
- Do not add `expiry >= issued` unless intentionally changing semantics: an already-expired original lease is currently allowed and then yields no replay.
- For a claimed full-domain standalone model, specify TIME shape and bounds: seconds and microseconds are canonical nonnegative integer strings; microseconds are at most 999999; the resulting milliseconds must be at most MAX. A direct safe bound is seconds at most 9007199254740, and when equal the millisecond component at most 991. Then `seconds*1000 + floor(micros/1000)` is exact for accepted values. Invalid time must cause replay to fail closed rather than be used in comparisons.
- Subtracting two validated nonnegative integer milliseconds each at most MAX yields a result within `[-MAX, MAX]`, so expiry-minus-now is exact. Clamping to zero and returning an integral remaining value preserves the numeric reply contract.

## Boundary matrix for candidate acceptance

These are requirements/oracles, not tests executed by this reviewer.

| Group | Cases | Expected |
| --- | --- | --- |
| General uint | `0`, `1`, `99999999999999`, `100000000000000`, `100000000000001`, `100000000000002`, MAX-1, MAX | Parse and reproduce exactly, including stored bytes and replies. Seq/claimed epoch have their separate nonzero constraints. |
| Overflow | MAX+1, MAX+2, `9223372036854775807`, `9223372036854775808`, very long digits | Reject before floating conversion and before identity mutation. |
| Alternate spellings | `00`, `01`, `+1`, `-0`, `-1`, `1.0`, `1e3`, `1E+3`, `0x10`, `0X10`, leading/trailing spaces or newline | Reject, even if tonumber would yield an in-range integer. |
| Fractional rounding | `9007199254740991.4`, `9007199254740990.9`, near-zero exponent/fraction underflow | Reject original bytes; never accept because the rounded double looks integral. |
| Malformed/type | Empty, `nan`, `inf`, `1junk`, `1\0junk`, only NUL, Unicode digits, nil/false/table/number passed to string parser | Reject without exception or partial-prefix acceptance. |
| Claim | Missing counter; zero; MAX-1; MAX; corrupt/canonical-out-of-range counter; signed-64 maximum | Initialize by stated policy; issue final exact MAX once; never INCR on exhausted/corrupt/out-of-domain state; no owner reuse. |
| Sequence | Adjacent values around 14-digit formatting threshold and MAX; duplicate; delayed lower; next higher revoke | Preserve exact storage; delayed/duplicate cannot replace payload; later revoke remains effective. |
| Commit floor | Exact high floor; equal/lower/higher committed value; fresh coverage below/equal/above; malformed present versus absent floor | Never lower or collapse the floor; corrupted present floor disables replay rather than becoming zero. |
| Expiry | ttl 0/60000/60001; exact equal cap; +1 past cap; issued in future; prior same-chain smaller cap; large exact expiry; simulated TIME boundary | Enforce TTL/cap/future rules exactly; no renewal through formatting or corrupt-cap fallback; distinguish arithmetic hardening from behavior changes. |
| Replies/bridge | All retained fields; owner comparisons; INCR numeric reply; snapshot numeric fields; raw expiry string | Canonical storage; validated bounded numeric returns; fake reproduces Redis's separate string/numeric conversion paths and reports its limits. |

## Remaining evidence limit

A vendored Lua 5.1 runner with a fake Redis bridge can establish interpreter-specific parsing/formatting and model-level branch behavior. It cannot establish real Redis command admission or failure ordering. The candidate should remain a separate, clearly labeled artifact; frozen evidence and original prototype remain unchanged. Independent candidate tests are owned by the parent reviewer to avoid duplication.

## Frozen candidate source follow-through

Inspected after the parent reported readiness; no candidate files or tests were changed by this reviewer:

- [Candidate authority](../../atomic-numeric-encoding/authority.lua): SHA-256 `5b762702f38792028eb13887b9684711e4026839b9a4c6ae808971b538e3a4ca`.
- [Fake bridge](../../atomic-numeric-encoding/fake_redis.lua): SHA-256 `f0bf9a8966585fec9168afbc6b911e1611670c2d23c8f6fc651f3da237115969`.

The candidate replaces lossy authority formatting with `%.0f`, rejects noncanonical string spellings before conversion, checks the global counter before INCR, checks owner canonicality, and rejects present malformed numeric retained fields before the old `or 0` fallback can erase a malformed floor. No remaining `tostring` path for authority integer writes/comparisons was found. This supports the narrow safe-integer/interpreter correction, not a general authority or Redis-runtime approval.

The parent also reported paired executed model probes in [ordering-regression.txt](ordering-regression.txt) for delayed `...004` to `...003` overwrite and newer `...007` revoke suppression after `...006`; consult that artifact for the execution evidence. This reviewer did not rerun or duplicate those tests.

Important limits are retained rather than silently counted as covered:

- Candidate `uint` accepts numeric inputs as well as canonical strings to handle INCR. Real Redis's ARGV/GET/HMGET string types make the decimal grammar effective at those boundaries; the fake must not inject numeric retained fields and claim it tested real Redis wire shape.
- Candidate TIME handling remains the baseline trusted-normal-range implementation, not the full synthetic-boundary validation proposed above. The unchanged `issued + ttl` comparison is not a demonstrated over-admission flaw under bounded operands.
- Candidate detects malformed present numbers and missing seq beside a present record epoch, but does not newly solve independent field loss. For example, an absent same-chain expiry can bypass the old cap, and an independently deleted floor is indistinguishable from initial absence. Those are preexisting data-retention prerequisites, not fixed by canonical integer encoding. It also does not newly reject stored seq zero as structurally impossible.
- INCR's expected result is guaranteed by the trusted serialized Redis command semantics after the bounded pre-read, rather than independently compared with `prior + 1` in this candidate. The fake uses floating increment and is not a general signed-64 parser/overflow oracle. The candidate's preflight must prevent out-of-domain calls from reaching that fake operation.
- The fake models exact integral command-argument encoding only within this experiment's supported domain, not all Redis numeric conversion behavior, RESP conversion, or fault semantics.
