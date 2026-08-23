# LAT-P082 — the composition read (LAT-P080 item 3), and the third recycle point

Two carried reads, both discharged 2026-08-23 against production `a13239f1` / **v3884**
(unchanged since 2026-08-21 11:37:18 PDT — the deploy freeze holds, verified from
`heroku releases`, not quoted).

---

## 1. Composition — LAT-P080 item 3

### The prediction, registered 2026-08-21, two days before this read

From `PROGRAM-LATENCY-NEXT.md` @ LAT-P080 item 3, verbatim and unedited since:

> With the self-vote suppressed, ~24 h of organic traffic should make the query-log arm's terms
> diverge from the frozen machine signature, and the blended head should track real intent more
> closely than it did at LAT-P079's read.

Registered before the read, in a committed file, by a different window. That is the pre-
registration; nothing was written this window to stand in for it.

### The measurement

`GET /api/admin/typeahead-warmer/last`, 32 recorded passes spanning 1,507 s:

```
head_source : "db:search_query_logs:30d"     ON ALL 32 PASSES
head_n      : 40      terminal: complete     warmed: 40      errors: 0
head[0:12]  : masters winner · stanley cup · world series · nba champion · world cup ·
              grammys · red sox · ballon d'or · oscars · pats · revs · fed
```

Against LAT-P079 and LAT-P081, both of which read `blend:query_log+trending:24/40_from_log`.

| question (item 3) | answer |
|---|---|
| 1. `head_source` and its split | **40/40 from the log.** Was 24/40. The trending arm contributes ZERO |
| 2. head membership vs the machine signature | **Diverged.** Old: `world cup 5414 · red sox 5411 · celtics 5403 · yankees 5400 · patriots 5399` (a spread of 15 across five terms — a machine). Now led by `masters winner · stanley cup · world series · nba champion`; `celtics` and `yankees` are out of the top 12 |
| 3. trending zset score spread | **N/A — the zset is EMPTY.** Read directly: `GET /api/events/search/trending` → `{"trending":[]}` |
| 4. cold-rate on the head | unchanged from LAT-P081's read; not re-measured, and not needed for the above |

**The prediction is CONFIRMED, and by a mechanism stronger than it supposed.** The head did not
diverge because organic votes accumulated. It diverged because the machine that produced the old
signature was switched off and nothing replaced it, so the trending arm went empty and
`resolve_head` fell through to the query-log branch — the arm that had never selected a term
before #1866.

### Why the zset is empty, with a paired control

`resolve_head` returns `db:search_query_logs:30d` on ONE branch, reached only when `zset_head` is
falsy. Three live probes settle the cause:

| query | in the warmed head? | cache | latency | recorded in trending? |
|---|---|---|---|---|
| `stanley cup` | yes | HIT | fast | ❌ **no** |
| `zzq obscure probe lat82` | no | MISS | 1.345 s | ✅ yes, count 1 |
| `qqx another probe` | no | MISS | 1.256 s | ✅ yes, count 1 |

The trending write sits immediately before `return result` in `typeahead_search`, so **a cached
response returns before it.** Warming a term therefore makes that term uncountable — the mirror
image of #1866's loop, and the reason the key ran out its 24 h TTL once `-71` stopped the warmer's
self-vote at 2026-08-21 10:19 PDT.

Filed as **#2117**.

### Consequence for grading #2072

`program/latency-73`'s hour-bucket rewrite of `_head_from_redis` will read empty for the same
reason, because the reason is upstream of which key layout is read. **Do not grade #2072 by
"did the blend come back".**

### ⚠️ Contamination I caused

Two synthetic terms are now in `search:trending:24h` — `zzq obscure probe lat82` and
`qqx another probe`, score 1 each, written ~09:2x PDT 2026-08-23. There is no admin Redis
write/delete endpoint (`/api/admin/redis-read` is read-only), so they cannot be removed; they
expire with the key's 24 h TTL. While they live, the zset is otherwise empty, so **they are the
entire trending distribution** and the warmer will take them into 2 of its 40 slots.

**A non-empty `search:trending:24h` before ~09:2x PDT 2026-08-24 is probably these probes, not
recovery. Read the member names.** Full accounting in #2117.

The probe was necessary — the discriminating fact is *a cache-hit query does not record while a
cache-miss query does*, which cannot be obtained read-only, and without it the empty key was
equally consistent with "no organic typeahead traffic at all". Two wasted warm slots for under a
day, stated rather than left for someone to trip over.

---

## 2. `worker-background` — the third recycle point, and a period can now be claimed

LAT-P081 recorded two points and correctly refused to call it a period: *"not confirmed, two
points imply a period rather than establishing one."*

| point | timestamp (PDT) | source |
|---|---|---|
| P1 | 2026-08-21 16:03:08 | LAT-P081 notice |
| P2 | 2026-08-22 04:03:43 | LAT-P081 notice |
| **P3** | **2026-08-23 04:03:30** | **this window, `heroku ps`** |

| gap | measured | as a multiple of 12 h | residual |
|---|---|---|---|
| P1 → P2 | 12 h 00 m 35 s | 1.0008 × | **+35 s** |
| P2 → P3 | 23 h 59 m 47 s | 1.9997 × | **−13 s** |

**A 24-hour period is REFUTED by the first gap** — a 24 h cycle from 08-21 16:03 lands on 08-22
16:03, not 08-22 04:03. **A 12-hour period fits all three points to within 35 s over 36 hours**
(drift < 0.1 %), with the 08-22 16:03 restart simply unsampled. Both observed phases (04:03 and
16:03) sit at `HH:03:xx`, which a 24 h cycle cannot produce without a phase shift.

Two controls that make this attributable:

* **No deploy in the window.** The last release is v3884 at 2026-08-21 11:37:18 PDT, so none of
  the three restarts is deploy-driven.
* **No other dyno shares the phase.** Every other dyno restarted once, together, at
  2026-08-22 11:4x–11:5x — `web.1` 11:52:17, `scheduler.1` 11:55:55, `worker-heavy.1` 11:57:30,
  `worker-realtime.1` 11:42:13, `worker-ws.1` 11:59:16. That is one fleet-wide event ~24 h after
  v3884 (Heroku's daily cycling), on a different phase, and `worker-background` is **the only
  dyno out of step with it**.

**Verdict: `worker-background.1` recycles on a 12-hour period at ~`HH:03`, independent of both
deploys and the fleet-wide daily cycle.** This contradicts the freeze file's "one-off" note.

⚠️ **What it is NOT, and this matters for anyone chasing the cause:** it is not
`--max-memory-per-child=200000`. That recycles the celery CHILD process, which does not change the
dyno's start time and would not be visible in `heroku ps` at all — nor would it be clock-aligned.

**What it costs this program:** every `worker-background` horizon read has a hard ceiling of 12
hours. The ≥6 h reads this lane has been defeated on five times are reachable; anything longer is
not, and no deploy freeze can buy it. That is worth knowing before a sixth window is scheduled
around a horizon the dyno cannot hold.
