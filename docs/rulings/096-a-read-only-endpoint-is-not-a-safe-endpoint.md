# RULING 096 — A read-only endpoint is not a safe endpoint; the measurement is load

date: 2026-08-19
author: latency lane (LAT-P071), self-reported
issues: #1545 #1609

## The ruling

**"Read-only" bounds what an endpoint can CORRUPT. It says nothing about what it can CONSUME**, and
on a single-event-loop web dyno the thing worth protecting is the loop, not the data.

Four obligations, and they are the whole ruling:

1. **Blocking work never runs inline in an `async def`.** Not "rarely", not "only on an admin
   route". A broadcast, a synchronous socket read, a large C-level parse — off the loop, or the
   handler is an availability defect regardless of what it returns.
2. **An endpoint a human or a script will POLL needs a memo, not just a timeout.** A timeout bounds
   one request. Cadence is the load, and only a cache bounds cadence.
3. **A window that polls production owns the load it creates, and must name it in its own
   evidence.** Every reading taken during self-inflicted load carries that in its provenance or is
   discarded.
4. **When an instrument and its subject share a resource, say so before quoting the instrument.**
   Measuring why work cannot get a slot, using a request that occupies the only loop, is not a
   neutral observation.

## Why — the occasion, which is this lane's own outage

2026-08-19, 05:00–05:03Z, extending to roughly ten minutes of degradation.

Two **read-only** samplers polled `GET /api/admin/celery-debug` — one every 20 s, one every 8 s —
while measuring the background queue for the "beats that never start" question. The **entire API**
went to HTTP 503 at the 30 s H12 ceiling. `/api/health` included. Not the admin surface: everything.

`heroku ps` reported `web.1: up` throughout, and `uptime_seconds` climbed unbroken 683 → 759 across
the recovery. **Nothing crashed. Nothing restarted. Nothing was corrupted.** The dyno was healthy by
every check the platform offers, and the site was down.

The handler made **four** `celery_app.control.inspect(timeout=5)` calls, inline, inside an
`async def`. `inspect` is a *broadcast*: publish to a control exchange, block until every worker
replies or the timeout expires. Four of them is up to twenty seconds of blocking work per request.
A poller faster than that guarantees the single uvicorn loop is never free.

The recovery is the proof, and it is unambiguous. Killing the two pollers — **by pid, never
`pkill -f`, which would have hit every other lane's processes** — restored p50 to **0.227 / 0.235 /
0.229 / 0.240 s**, four consecutive calls, within 25 seconds, with no restart.

## What makes it a ruling rather than a bug report

**Nothing about the endpoint signalled danger.** It is read-only. It has no writes. It is not behind
the destructive-secret guard, because it destroys nothing. Every review heuristic this repo applies
to "is this safe" returns yes, and the endpoint was one auto-refreshing dashboard tab — or two
operators with the page open — away from blacking out production. It had been that way for as long
as it has existed.

The repo already knows this shape and had not generalised it. **Gotcha #39** is the same defect in
the other direction: *"a sync Redis client with no socket timeout can freeze an async task — the
frozen thread IS the event loop, so nothing can fire."* That was written about `tasks/`, and it is
enforced there by a CI guard. Nobody carried it across to `routes/`, where the loop being frozen is
not a task that fails to fire but **every user's request**.

So the clause is not "celery inspect is slow". It is that **the safety review asked what the
endpoint writes when it should have asked what it occupies.**

## The three-way fix, because one of them alone is not enough

Shipped in `c6f9a571` on `program/latency-64`:

* **Off-loop** (`run_in_threadpool`). A broadcast is socket I/O plus pure-Python message assembly,
  both of which release the GIL, so a thread genuinely helps — unlike **gotcha #38**'s C-level
  `json.loads`, which holds the GIL for the entire parse and defeats `to_thread` completely. That
  distinction is now written in the code, because assuming it either way is how both mistakes get
  made.
* **Single-flight.** Off-loop alone only relocates the pile-up into the threadpool, where exhausting
  the 40 default threads stalls every other route that needs one.
* **Memoised, 5 s, with the cache state disclosed in the payload.** This is the one that would
  actually have prevented the outage, because the load was **cadence, not concurrency**. Disclosed
  rather than silent: a debug endpoint that quietly serves a stale snapshot invites conclusions
  about a moment that has passed.

Plus a guard that outlives the fix: a test asserts no handler calls `control.inspect(` outside the
sanctioned threadpool body. A reintroduction will look exactly as harmless as this one did.

## The uncomfortable half, recorded on purpose

Six mutations were run against the new tests. **The first round caught one of five.** The
availability suite — written immediately after the outage, by the person who had just watched it —
was very nearly inert:

* the loop-block test counted heartbeat ticks against a **fixed 10-iteration loop**, so it capped at
  10 and read identically blocked or not;
* rewritten to measure inter-tick **gaps**, it still failed to catch it, and probing showed why: a
  blocked loop produces **no gap**, because the heartbeat does not tick during the block and is
  cancelled before it can tick after. Measured: off-loop 44 ticks / max gap 0.024 s; on-loop 5 ticks
  / max gap 0.011 s. **The gap assertion passed in both worlds.**
* an **uncontended `asyncio.Lock`** takes a fast path without yielding, so the snapshot ran
  start-to-finish before the heartbeat task was ever scheduled;
* the TTL test aged the cache by `TTL + 1`, which self-adjusts — setting the TTL to a billion
  seconds still "expired".

Tick **rate** separates the two worlds ~9×, and that is what it asserts now. All six caught on
re-run. This is ruling 081's clause paying out again inside its own banking window: **run the
mutant, because the author's conviction is not evidence.**

## Standing operational rule until this deploys

The fix rides `program/latency-64`, behind the 2026-08-19T17:01Z T5 fence. **Until then: do not poll
`/api/admin/celery-debug` or `/api/admin/celery/inspect` faster than once per 30 seconds**, and do
not leave either open in an auto-refreshing tab.
