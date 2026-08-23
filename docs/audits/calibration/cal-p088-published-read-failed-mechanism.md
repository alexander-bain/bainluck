# CAL-P088 item 3 — `published_read_failed` on the ceiling run: the mechanism

**READ-ONLY. Mechanism reported; nothing proposed, per the directive.**
CAL-P088, 2026-08-23. Subject: the SECOND, independent failure on #2076's ceiling run
(`fold_duration_s 1351.95`, `timeout_ms 1350000`, `db_rows 0`,
`payload_error: "published_read_failed: redis call did not complete"`,
artifact `2026-08-21T19:24:23Z`).

The directive asks one question: **is it timeout pressure from the fold's own window, or
independent?**

**Answer: both, and they are separable — but the decisive finding is that the artifact
cannot tell you which one happened, because three different facts produce that identical
string.** The message is a false statement about the call in at least one of them.

---

## The headline

`_read_published_payload` (`app/tasks/calibration_published_twin_worker.py:284`) opens with
a docstring that states the exact distinction it then fails to make:

> *"A miss and a Redis failure are DIFFERENT facts and are named differently — an absent key
> means the producer has not published, which is a real finding about the producer; a failed
> client is a fact about us."*

The code:

```python
res = await _rc.bounded_redis_call(lambda: rc.get(PUBLISHED_MAIN_KEY))
...
if not getattr(res, "is_ok", False):
    return {}, "published_read_failed: redis call did not complete"
if res.value is None:
    return {}, f"published_absent: {PUBLISHED_MAIN_KEY} is not set"
```

`bounded_redis_call` defaults to `treat_none_as_miss=True` and returns `RedisResult(MISS)`
for a nil reply; `is_ok` is `status == OK`, so **MISS is not ok**. The absent-key branch is
therefore never reached.

**Executable proof** (run this window, against the real functions):

```
absent key      -> status=miss    is_ok=False
present key     -> status=ok      is_ok=True
stalled call    -> status=timeout is_ok=False
```

So `published_absent` is **unreachable dead code**, and an absent key reports *"redis call
did not complete"* — which is false: the call completed and returned nil.

---

## The three arms, and which the evidence supports

### Arm A — the key was simply not there. **Independent of the fold. Expected, designed-for, and the codebase already knows it.**

`bainluck:calibration:main` is written with `_MAIN_CACHE_TTL = 7200` — **a 2-hour TTL** —
on a 50 MB `allkeys-lru` Redis. The repo documents the consequence itself, in
`precompute_calibration.py:4688`:

> *"on a 50MB `allkeys-lru` instance `main` (2h TTL) is evicted long before `last_good`
> (7d), and without it the gate would read 'no prior artifact' …"*

Every other consumer therefore reads `main` **and falls back to `last_good`**. The twin
reads `main` **only**, with no fallback. So the twin is the single consumer that treats a
routine — expired *or* LRU-evicted — absence as a failure, **and mislabels it as a
transport fault.**

This arm needs no fold, no latency and no incident. It fires whenever the beat lands more
than 2 h after the last successful publish, or whenever memory pressure evicts the key.

### Arm B — the call genuinely could not complete inside its deadline. **Independent in mechanism, fold-aggravated to near-certainty.**

Two budgets, set by different owners for different purposes, meet here:

| | value | where | intended for |
|---|---|---|---|
| wrapper deadline | **600 ms** | `REDIS_OP_DEADLINE_MS`, `request_cache.py:59` | the **request path** — "well under the 30 s Heroku router H12 cutoff" |
| socket connect timeout | **5,000 ms** | `get_async_redis_client`, `redis_state.py:157` | a **background** client that must survive TLS churn |
| retry policy | `Retry(EqualJitterBackoff(cap=1.0, base=0.05), 3)` on `[ConnectionError, TimeoutError]` | same | transparently reconnecting an idle-reaped connection (#1197) |
| health check | `health_check_interval=25` s | same | PING-on-checkout for a connection idle > 25 s |

A reconnect is budgeted at up to **3 × (5 s connect + ≤1 s backoff) ≈ 18 s**. It is wrapped
in `asyncio.wait_for(..., 0.6 s)`.

**So the client's own recovery path is up to ~30× larger than the deadline it runs under.
Any operation that needs even one reconnect cannot complete inside the wrapper. That is
deterministic, not probabilistic** — the retry machinery #1197 added specifically so a
handshake blip "degrades into a sub-second reconnect" is, at this call site, guaranteed to
be cut off before it can finish.

**Where the fold comes in — and it is not what it looks like.** The fold does *not* starve
this call of CPU, and the `statement_timeout` is unrelated. The coupling is purely
**elapsed idle time**:

* `run_published_twin` calls `read_served_disclosure()` **before** the fold — and that goes
  to `read_snapshot_standalone`, i.e. **Postgres durable snapshots, not Redis**. Verified.
* So `_read_published_payload`, called **after** `_fold`, is the **first Redis touch in the
  whole run**.
* The fold ran **1,351.95 s** — **54× the 25 s `health_check_interval`**, and far past
  Heroku Redis's idle reap.

A pooled connection is therefore near-certain to be dead on checkout → health-check PING
raises `ConnectionError` → the retry policy engages → the 600 ms wrapper fires first.

**Fold-independent in mechanism; fold-converted from "sometimes" to "essentially always".**

### Arm C — transfer time. **RULED OUT, measured.**

The hypothesis that a large payload cannot cross the wire in 600 ms does not survive
measurement. `GET /api/calibration` this window:

```
pass1 http=200 bytes=433174 ttfb=0.294s total=0.616s
pass2 http=200 bytes=433547 ttfb=0.469s total=0.738s
```

**~423 KiB.** A local Redis `GET` of that is single-digit milliseconds. Payload size is not
the cause, and any fix aimed at it would be aimed at nothing.

---

## Why the record cannot currently distinguish them

This is the part that matters more than any individual arm.

Arm A (key absent — a fact about the **producer**) and Arm B (call cut off — a fact about
**us**) produce **byte-identical** `payload_error` strings. There is no status code, no
`RedisResult.status` passthrough, no elapsed-time field, and no second signal on the
artifact. The twin also does not read `last_good`, so it cannot even distinguish "nothing
was ever published" from "the fresh copy aged out while the durable one sits right there".

That is **gotcha #53 exactly** — an absence and a failure reaching the reader in the same
bytes — occurring inside the function whose own docstring promises the opposite, in a
module written to stop Gate 0 reporting agreement it cannot justify.

**Consequence for #2076:** the ceiling run's second blocker is currently **unattributable
from the record**. It cannot be called "timeout pressure from the fold" on the evidence in
hand, and it cannot be called independent either. What *can* be said, on structure alone
and without a rerun:

1. Arm A is live on every beat that lands > 2 h after a publish, fold or no fold.
2. Arm B is live on **every** run whose fold exceeds ~25 s of Redis idle — i.e. on every
   ceiling run by construction, and on essentially every real fold.
3. Both were true simultaneously on 2026-08-21T19:24. Neither can be excluded.

## What is NOT proposed here

Per the directive — *"Read-only first … Report mechanism before proposing anything"* —
this document proposes no change. It records four facts a fix would have to answer to:

* the MISS/failure conflation and the unreachable `published_absent` branch;
* a **request-path** availability constant (600 ms) governing a **background** worker whose
  own client is provisioned for a 5 s connect and a 3-attempt retry;
* the ordering that makes the post-fold read the process's first Redis touch;
* the twin being the only `main` consumer with no `last_good` fallback.

## Provenance

All read-only. Two production GETs (`/api/calibration`, warm second pass), source reads on
`program/calibration-85`, and one local executable proof against the real
`bounded_redis_call`. No writes, no dynos, no enqueues; the freeze is untouched.
