# LAT-P078 — #1866: the warmer was warming its own output

**Build under measurement:** `ec636bae` / Heroku **v3881**, released 2026-08-20 15:20:56 PT.
**Horizon at read:** **15.6 h** post-deploy — the first ≥6 h window this program has had for a
user-felt read, and the one Fable asked for. It is a *build* horizon; the worker-background
horizon is separate and shorter (see §5).
**Instruments:** `backend/scripts/probe_typeahead_userfelt.py` (new, corrected),
`GET /api/admin/typeahead-warmer/last`, `GET /api/events/search/trending`,
`POST /api/admin/db-query`.

---

## 1. The finding, in one paragraph

`typeahead_warmer.resolve_head` reads the top 40 of the Redis zset `search:trending:24h` to
decide what to warm. `_warm_one` warms by calling `typeahead_search`, and that route's last act
is to `zincrby` the query into **that same zset**. So every pass voted for its own head. At a
~50 s pass that is **~1,700 votes per day per head term**, against ~3/day for a real organic
query. The head was therefore **self-sustaining and closed**: once a term was in the top 40 it
could not fall out, and nothing could break in. Compounding it, `resolve_head` was a strict
first-non-empty **cascade**, and `_head_from_redis` is never empty in production — so the
`search_query_logs` arm below it was **unreachable code**, and the only unpolluted measurement
of real user intent in this system had never selected a single warmed term.

## 2. The evidence, in the order it was taken

### 2.1 The zset's own scores are not a human distribution

`GET /api/events/search/trending`, 2026-08-21:

```
world cup 5414   red sox 5411   celtics 5403   yankees 5400   patriots 5399
```

**A spread of 15 across five terms is a round-robin process.** Real traffic is a power law. The
same 30-day window from `search_query_logs` (`POST /api/admin/db-query`):

```
masters winner 102 · stanley cup 101 · world series 95 · nba champion 90 · world cup 82
ballon d'or 80 · grammys 77 · yankees 77 · red sox 75 · pats 72 · oscars 70 · revs 70
```

### 2.2 The loop is readable in source, not inferred

* `app/tasks/typeahead_warmer.py::resolve_head` → `_head_from_redis` →
  `zrevrange("search:trending:24h", 0, limit-1)`
* `app/tasks/typeahead_warmer.py::_warm_one` → `from app.routes.events import typeahead_search`
* `app/routes/events.py::typeahead_search`, last statement →
  `rc.zincrby("search:trending:24h", 1, normalized)`

### 2.3 A hypothesis registered before the probe, and REFUTED

Before probing I predicted **prefix bias**: since the route counts every keystroke, the head
should be dominated by 2–4 character stems, starving complete phrases. Probed 14 terms:

| term | verdict | time |
|---|---|---|
| `st` / `sta` / `stan` / `stanley` | cold | 7.4 / 8.8 / 5.4 / 5.3 s |
| `nba` / `nba c` | cold | 5.4 / 6.2 s |
| `mas` | cold | 10.3 s |
| **`masters`** | **warm** | **0.222 s** |
| `masters winner` | cold | 4.0 s |
| `ballon` | cold | 5.4 s |
| `yank` | cold | 7.2 s |
| **`yankees`** / **`red sox`** / **`grammys`** | **warm** | 0.227 / 0.233 / 0.231 s |

🔴 **The hypothesis FAILED.** Short prefixes are cold too; single complete words are warm; multi
-word phrases are cold. It is not a prefix/phrase story at all — the zset head is simply a
*different set* from the real head, frozen at whatever won a race at some past moment. Recorded
because a refuted prediction is the cheapest evidence in this program and this one redirected
the diagnosis.

## 3. The user-felt read at horizon — n=75, corrected probe

15 rounds × 5 terms × 95 s spacing (the spacing control LAT-P076 introduced), warm threshold
0.300 s stated as an argument, **all 75 reads HTTP 200, zero empty bodies** — so unlike
LAT-P077's read, no failure is hiding inside a fast number.

| term | rank in real traffic | n | cold | cold % | p50 | max |
|---|---|---|---|---|---|---|
| `world series` | 3 | 15 | 6 | 40 % | **0.268 s** | 7.332 s |
| `world cup` | 5 | 15 | 7 | 47 % | **0.229 s** | 7.955 s |
| `super bowl` | 41 | 15 | 5 | 33 % | **0.230 s** | 3.687 s |
| **`stanley cup`** | **2** | 15 | **14** | **93 %** | **3.291 s** | 6.973 s |
| **`nba champion`** | **4** | 15 | **14** | **93 %** | **3.350 s** | 7.780 s |

Grouped by the only variable that separates them — **membership of the zset head**:

| group | n | cold | p50 | p95 |
|---|---|---|---|---|
| IN the zset head | 45 | 18 (**40 %**) | **0.235 s** | 7.332 s |
| NOT in the zset head | 30 | 28 (**93 %**) | **3.350 s** | 7.776 s |

**A 14× gap in p50, attributable to head membership alone.** `masters winner` — rank 1 in real
traffic — measured 4.032 s in §2.3. #1866's title says 1.16–2.29 s; at horizon the real head
costs **3.3–5.2 s p50**, so the issue title still understates its own subject.

🔴 **Membership is necessary but not sufficient.** In-head terms are still cold 40 % of the
time. That residual is *not* composition — it is the pass-period / cache-expiry defect (§5),
and the fix in this queue cannot touch it. Saying so in advance is the point: if in-head cold
rate improves after deploy, something other than this change moved.

## 4. The fix, and the predictions it must be graded against

Two halves of one change; neither works alone.

* **`_suppress_trending_write`** (a `ContextVar`, deliberately not a route parameter — FastAPI
  turns a plain-defaulted parameter into a public query param, which would let anyone opt their
  searches out of the count). The warmer keeps running the route's own code path, which is what
  makes the warmed body byte-identical to the served one. It just stops voting.
* **`_QUERY_LOG_SHARE = 0.5`** — `search_query_logs` gets a guaranteed half of the 40-term
  budget. It is a **floor with backfill**, so a short source never leaves the budget unspent.

Breaking the loop alone would leave the accumulated ~5,400 all-time scores frozen, because the
route re-`expire`s the key on every write so it never rolls — filed as **#2072**, not fixed here.

### Registered predictions, to be graded post-deploy at a ≥6 h horizon

| # | prediction | today's value |
|---|---|---|
| **P1** | `stanley cup` + `nba champion` cold rate falls 93 % → ≤ 50 %, p50 falls 3.3 s → ≤ 0.35 s | 93 %, 3.29/3.35 s |
| **P2** | *control* — the three already-in-head terms do **not** materially move | 33–47 %, p50 0.23–0.27 s |
| **P3** | the in-head residual cold rate does **NOT** go to zero; ~40 % persists, because it is §5's defect and not composition | 40 % |
| **P4** | 🔴 *the risk* — `walls_over_response_ttl` does not rise, and wall p95 stays < 65 s | p95 **60.9 s**, max **66.365 s**, `walls_over_response_ttl` **1** |

🔴 **P4 is where this change can do harm, and the margin is already gone.** The head keeps 40
slots, so 20 log-derived terms **displace** 20 zset terms; the incoming terms are longer phrases
and at least one, `ballon d'or` (rank 6), is the known no-trigram seq-scan of **#1619**, measured
at 1.0–12.1 s. Against `PER_QUERY_TIMEOUT_SECONDS = 10` and `WARM_CONCURRENCY = 4` (10 terms per
lane), one pathological term can add ~10 s to its lane. The wall is **already** over its budget
before this change: max **66.365 s** against `RESPONSE_CACHE_TTL_S = 65`, with
`walls_over_response_ttl` reading **1**. A pass that outlasts the TTL cannot keep anything warm.

**The instrument for P4 already exists and needs no new code** — `walls_over_response_ttl` and
the wall distribution are both in the ring payload. **If P4 fails, the mitigation is
`DEFAULT_HEAD_SIZE` or `_QUERY_LOG_SHARE`, not a revert of the loop-break**: the loop-break is
strictly correct and costs nothing.

### And a constant that is now wrong, reported not touched

`typeahead_beat_budget.MEASURED_WALL_MAX_S = 53.920` against a measured max of **66.365 s** — a
**12.4 s underestimate**, and the *fourth* consecutive cycle in which a sampled maximum proved a
prior sampled maximum too low. Not corrected here: it feeds the beat-budget verdict, changing it
is a second intervention, and this window already has one. **Owed.**

## 5. R2 at horizon, and a methodological problem with ruling 110's own predictions

`GET /api/admin/typeahead-warmer/last`, same read:

| | LAT-P077 @ ~10.5–11.6 h, v3872 | **LAT-P078 @ 15.6 h build, v3881** |
|---|---|---|
| period p50 | 51.3 s | **50.3 s** |
| period p95 | **292.7 s** | **90.6 s** |
| period max | 330.6 s | 268.5 s |
| passes with loss | 6/25 (24 %) | **6/32 (19 %)** |

🔴 **Two of ruling 110's four registered predictions are already satisfied by the PRE-MOVE
system.** P1 was "period p95 < 200 s" — it reads **90.6 s** with the routing change *not
deployed*. P2 was "loss < 20 %" — it reads **19 %**, likewise pre-move. Had the move shipped and
this read been taken afterwards, both would have been credited to it. That is precisely the
misattribution class that produced LAT-P076's withdrawn 80 % → 0 % headline, and here it is in
this lane's own predictions. **P1 and P2 cannot discriminate the intervention and should be
re-derived against a null measured at the same horizon before the falsifier is graded.**

⚠️ **Caveat, stated because it is the whole difficulty of this measurement:** the two reads do
not share a horizon *clock*. LAT-P077's was ~10.5–11.6 h into a worker-background uptime;
`worker-background.1` restarted **2026-08-21 04:03:36 PT** and was only **~3.2 h** up at this
read, while the *build* was 15.6 h old. For a queue-contention metric the worker's clock is the
governing one, so **R2 at a true ≥6 h worker horizon is still not taken.** A sampler
(`/tmp/lat78-ring-series.jsonl`, 10-minute cadence) was started to capture the crossing at
~10:03 PT rather than wait for it.

## 6. What is owed

* **P1–P4 above**, post-deploy, at a ≥6 h horizon, with the corrected probe.
* **Ruling 110's falsifier read** — still impossible: `program/latency-70` is unmerged,
  `origin/master` is its own base `ec636bae`, and `GET /api/admin/heavy-move/falsifier` is
  **HTTP 404**. Amended in the ruling file.
* **`MEASURED_WALL_MAX_S`** re-derivation (§4).
* **#2072** (the zset is not 24 h) and **#2071** (the falsifier under-reports its coverage).
