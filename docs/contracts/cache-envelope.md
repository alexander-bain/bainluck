# CONTRACT — the cache envelope

Status: **the contract for any cache tier being touched.** Not a migration.
Authority: ruling 005 (`docs/rulings/005-extract-on-touch.md`), second clause.
Date: 2026-08-09

> **Apply this to the tier you are already in.** A defect fix that opens a cache tier converts
> that tier to the envelope on its way through. There is no bulk-migration queue, and there never
> will be one — a broad cache migration is a refactor queue in different clothes: large,
> invisible, and riskiest exactly where it is hardest to test.

## The five fields

Every cached artifact carries all five. A tier that cannot populate one must say so explicitly
rather than omit it, because **an absent field and a null field read identically to a consumer,
and that ambiguity is the bug this envelope exists to remove** (gotcha #53: an empty 200 is a
response shape, not an absence).

| field | type | means | why it is here |
|---|---|---|---|
| `generation` | int or version string | which producer version built this | A payload built by code that is no longer deployed must be refusable. This is what made the calibration page dark in the 2026-08-02 incident and what makes a `CALIBRATION_POPULATION_VERSION` bump safe to reason about: a consumer can tell "stale" from "built by a different product". |
| `created_at` | UTC ISO-8601 | when the CONTENT was computed | Not when it was written to the tier, and not when it was fetched. Those diverge on every re-write of an unchanged payload, and reporting the write time makes an ancient payload look fresh. |
| `quality` | enum | `full` \| `partial` \| `degraded` | A partial answer that renders as a whole one is the class behind fabricated winners (ruling 003) and blend-hidden source disagreement. The producer knows; the consumer cannot infer it. |
| `availability` | enum | `live` \| `stale_ok` \| `unavailable` | The serve decision, made by the producer and published, not re-derived per consumer. Ruling 003: clients format, never adjudicate. `stale_ok` is a real, honest state — it is what `/api/calibration` serves today under `durable_over_age`. |
| `lifecycle_watermark` | UTC ISO-8601 | the newest upstream fact this payload reflects | The one field that answers "is this payload missing something that already happened". `created_at` says when we computed; the watermark says how far into reality we had got when we did. A payload recomputed hourly from a source that stopped updating yesterday has a fresh `created_at` and a day-old watermark — and only the watermark makes that visible. |

## Rules

1. **The producer sets all five. The consumer reads them.** A consumer that computes availability
   from `created_at` has re-derived a decision — ruling 003 forbids it, and the two derivations
   drift the moment either side changes.
2. **`unavailable` is a first-class success.** Publishing "I cannot answer" is a correct outcome,
   and it is strictly better than a 503 or an empty 200, both of which force the consumer to
   guess which failure occurred.
3. **Never infer a fact from the emptier reading.** If a tier cannot distinguish "never existed"
   from "purged", it says so in `quality`; it does not pick the convenient one (gotcha #53, and
   the ten weeks #683 spent looking like a success).
4. **Freshness is `lifecycle_watermark` versus now — not `created_at` versus now.** Recomputation
   is not information.
5. **A tier converted to the envelope keeps its old read path working** until every consumer is
   moved. Extract-on-touch means incremental by construction, so partial adoption is the normal
   state, not a defect.

## What "touching a tier" means

Opening the file to change caching behaviour: the TTL, the key, the serve/refuse decision, the
fallback, the write path. It does **not** mean any edit to a file that happens to contain a cache
call. The trigger is a change to caching *policy* — which is the same trigger extract-on-touch
uses for pulling policy into a pure module, and deliberately so: the envelope conversion and the
extraction are one piece of work, done once, paid for by the defect fix that opened the file.

## First customers

Whichever tier the next cache-policy defect lands in. The live candidates, in the order they are
likely to be touched: the `/api/event/{key}` concept cache (#1107 — Codex C224 already found a
malformed-primary path that skips a healthy stale mirror, a stampede on the cold build, recovery
that writes stale only, and a 24h fallback with **no age or status disclosure**, which is
literally three of these five fields missing), then the calibration durable copy, which already
publishes `cache.status` and `cache.reason` and is the closest thing to a working prototype.
