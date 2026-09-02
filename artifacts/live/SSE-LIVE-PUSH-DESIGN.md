# SSE live push — design (live/034)

PILLAR: TRUTH · SHIP: **on a live match, the number moves by itself — no refresh, no 32-second
wait — and the page says how old it is.**

Ruling (RULINGS-BATCH-2026-08-30, LIVE UPDATES 1+2): push for LIVE events only, SSE, web + iOS
subscribe, non-live keeps polling; animated number (≤1 change/~5s) + "live · Ns ago" pulse +
last-10-min sparkline; illiquidity ring stays; no smoothing.

Status: DESIGN. Nothing built yet. Written 2026-09-01 ~6pm PT.

---

## 1. What already exists (measured, not assumed)

The expensive half of this ship is already built and running. Facts from the tree at `2fd33ed2`
and from production:

| Fact | Where | Value |
|---|---|---|
| A `worker-ws` dyno runs Kalshi + Polymarket CLOB websocket consumers | `Procfile:7`, `tasks/kalshi_ws.py`, `tasks/polymarket_ws.py` | live |
| Those consumers flush buffered prices every **2s** | `kalshi_ws.py:37` `PRICE_FLUSH_SECONDS=2` | 2s |
| After each flush they push the recomputed blend into `Event.win_probability_sources` — the JSONB the card actually renders | `kalshi_ws.py:250`, `polymarket_ws.py:459` (both call `blend_refresher.refresh(...)`) | Q460 |
| The refresher **already throttles to one refresh per event per 5s** | `live_blend_refresh.py:72` `DEFAULT_MIN_REFRESH_INTERVAL_S=5.0` | 5s |
| It re-stamps an unchanged value every 45s so recency decay stays honest | `live_blend_refresh.py:83` | 45s |
| It appends a chart point at most every 25s | `live_blend_refresh.py:90` `DEFAULT_SNAPSHOT_INTERVAL_S=25.0` | 25s |
| Starlette's GZipMiddleware already excludes `text/event-stream` | `main.py:174` (comment is explicit) | safe |
| There is **no** SSE anywhere in the tree today | `grep text/event-stream`, `grep new EventSource` | 0 hits |
| Web client polls `LIVE_REFRESH_INTERVAL = 32000` when live, 120000 otherwise | `frontend/app/events/[id]/page.tsx:90` | 32s |

**The consequence that shapes the whole design:** the ruling's "≤1 update/5s" is not a throttle we
have to write. It is already the refresher's per-event cadence. If we publish at the point where a
stamp actually lands, the cap is satisfied *structurally* — there is no second timer to get wrong,
and no way for the cap and the writer to drift apart.

**What this ship is actually worth.** It does not make the data fresher — the socket is already
2s fresh and the blend already 5s fresh. It removes the **up-to-32-second lag between the data
being fresh and the user seeing it**, and it removes N-viewers × 2 polls/min of load. Today a
live number can be 32s stale on screen while being 3s stale in the database. That gap is the bug
this closes.

## 2. Shape

```
kalshi_ws / polymarket_ws  (worker-ws dyno)
   └─ LiveBlendRefresher._refresh_batch()   ← already throttled to 5s/event
        └─ on a stamp that actually happened:
             PUBLISH redis  "live:event:{id}"  {p, source, updated_at, home, away}
                                     │
                                     │  Redis pub/sub — fire-and-forget, stores nothing
                                     ▼
       GET /api/events/{id}/stream   (web dyno, text/event-stream)
             SUBSCRIBE live:event:{id} → forward → heartbeat every 20s
                                     │
                        ┌────────────┴────────────┐
                        ▼                         ▼
              web: EventSource            iOS: URLSession.bytes
              useLiveEventStream()        LiveEventStream actor
```

### 2.1 Publisher (`live_blend_refresh.py`)

One insertion point, inside `_refresh_batch`, on the branch where `_should_write` returned true and
the stamp committed. Publishes the value it just wrote. Never raises — same contract as
`_maybe_snapshot`: the push is downstream of the number, and a failed publish must not cost a
stamp that already succeeded. Counted in `self.stats` as `published` / `publish_errors` so a dead
publisher is *visible*, not quiet (gotcha #53 — "it returned" is not "it worked").

Redis **pub/sub**, deliberately not a list or a stream: pub/sub stores nothing, so this adds zero
bytes to the 100MB LRU that Celery shares. Routed through `get_redis_client()` — a sync client with
no socket timeout can freeze an async task (gotcha #39).

### 2.2 Server (`routes/event_stream.py`, new file)

`GET /api/events/{event_id}/stream` → `StreamingResponse(media_type="text/event-stream")`.

- **Live gate.** One indexed lookup at connect: if `status != 'live'`, emit a single
  `event: not-live` frame and close. The client then polls. This is the ruling's "non-live keeps
  polling", enforced server-side so a client bug cannot open a stream on a settled match.
- **No per-connection DB work after connect.** Initial state is the REST payload the page already
  fetches; the stream carries deltas only. This matters because the web dyno runs
  `WEB_CONCURRENCY=2` uvicorn workers and those same two event loops serve `/api/feed`. An SSE
  handler that touched the DB per tick would put feed latency behind stream fanout.
- **Heartbeat every 20s** (`: ping\n\n`). Heroku's router kills a connection after ~55s idle;
  20s gives two chances to miss before that fires.
- **Hard connection lifetime ~15 min**, then a clean close with a `retry:` hint. Bounds any leak
  and makes reconnect a tested path rather than an incident path.
- **Concurrency cap** per worker (env-tunable, start at 200). Over the cap → `503` immediately;
  the client polls. Refusing loudly beats degrading `/api/feed` silently.

### 2.3 Web client

`useLiveEventStream(eventId, enabled)` — wraps `EventSource`, and on each frame calls SWR
`mutate()` on the existing event key. One source of truth: the stream updates the same cache the
poller writes, so every component downstream is unchanged.

- Stream connected → set the event SWR `refreshInterval` to `0`. That *is* the polling replacement.
- Stream errored, refused, closed, or **silent for >60s** → restore the 32s interval. A push path
  that dies must degrade to the old behaviour, never to a frozen number. The silence detector is
  the important one: a TCP connection that is open but dead looks exactly like a quiet market.
- Non-live event → hook never opens a connection.

### 2.4 UI (ruling 2)

- **Animated number** — tween between previous and new value. Cadence is already ≤1/5s upstream,
  so no client throttle; the animation is presentation only and must never interpolate a value the
  server did not send (**no smoothing** — ruling).
- **"live · Ns ago"** — derived from the stamped `updated_at`, not from receive time. If the socket
  is quiet the age must keep counting up honestly rather than resetting on a heartbeat.
- **Last-10-min sparkline** — from the existing snapshot series at 25s cadence → ~24 points. Raw
  points, no smoothing.
- Illiquidity ring unchanged.

### 2.5 iOS (second ship, certed separately)

`URLSession.bytes(for:)` gives an `AsyncSequence` of lines; SSE framing is parsed in a small
actor. Same live gate, same 60s-silence fallback to the existing poll. Ships after web is certed
green, per WIP 2.

## 3. Risks, named

| # | Risk | Mitigation |
|---|---|---|
| R1 | SSE shares the 2 uvicorn loops with `/api/feed` | zero DB/CPU per tick; connection cap; soak with `/api/feed` p95 measured before/after |
| R2 | Heroku router 55s idle kill | 20s heartbeat |
| R3 | Pub/sub is fire-and-forget — a dropped frame is a skipped tick | self-heals on the next tick, and the 45s unchanged-re-stamp guarantees a floor; stated, not hidden |
| R4 | `worker-ws` is a single dyno — if it dies, no ticks at all | client 60s-silence → poll fallback; publisher stats surface a dead publisher |
| R5 | A stream open on an event that goes final | `status` transition publishes a terminal frame; client closes and refetches once |

## 4. Ship order — BUILT 2026-09-01, PR #2617, cert owed

| | what | state |
|---|---|---|
| **S1** | publisher + `/api/events/{id}/stream` + 49 guards | **built**, `88b0e2a2` |
| **S2** | web client, poll suspension, "live · Ns ago" | **built**, `2c88a094` |
| **S2b** | animated number | **built**, `afab053f` |
| **S3** | iOS `AsyncStream` client | **built**, `1211ceb5` — compile NOT verified, see below |
| **S2c** | last-10-min sparkline | **NOT BUILT** — the one piece of ruling 2 still owed |

**Two design flaws the build caught, both fixed:**

1. `publish_frame` swallows its own failure and returns `False`, so the batch-level `except` never
   saw a dead client. The poisoned connection would have been reused for the life of the consumer,
   publishing nothing while only ticking a counter. A batch where nothing goes out now drops the
   client.
2. The heartbeat was a conventional `: ping` SSE comment — which fires **no handler** in
   `EventSource`. The client's silence watchdog would then have been measuring "is this market
   moving" rather than "is this server alive", and on a quiet market it would have torn down a
   perfectly healthy stream. The heartbeat is now a named, observable event, guarded by a test.

**Verification owed.** `xcodebuild` cannot resolve the Firebase SPM binaries in this sandbox (exit
74, proxy-blind), so S3 was never compiled. All three Swift files parse clean and
`LiveEventStream.swift` typechecks clean in isolation including under
`-strict-concurrency=complete`, but the two files importing app types could not be typechecked
alone. A real Xcode build is owed before S3 is certed. S1/S2 are fully gated.

**Deploy is blocked regardless:** `NOTICE-2026-09-01-HARD-DEPLOY-FREEZE` is active — `/api/calibration`
`generated_at` was still 2026-08-31 (44.4 h stale) at 18:15 PT.

## 5. Assumption stated, not asked

The live gate keys off `Event.status == 'live'`. Measured tonight, that is real but partial: 11 of
the US Open matches carry `status='live'`, while others — including Faria/Alcaraz, mid-match with
a Kalshi price 60s old — sit at `status='scheduled'` with the midnight stand-in `commence_time`
(00:00Z), so the page renders "Pregame" and never enters the live path *at all*, poll or push.

**That is a pre-existing event-graph defect, not an SSE defect, and D27 says the event graph
outranks card freshness.** This design does not paper over it: SSE inherits whatever `status='live'`
means. Every match the status writer gets right, push serves. Every match it gets wrong was already
broken before this ship and stays broken after it — visibly, in the same place. Widening the gate
here (e.g. "live if a source stamped inside 2 min") would hide an event-graph bug behind a UI
feature, which is exactly the trade D27 forbids. Filed as its own thread.
