# LAT-P121 — the cache that thirty entries could not hold

**Pillar: DISCOVER. Ships: the markets on an event page stop being rebuilt from scratch for almost
every visitor** (#1587) — the second request of the page where the probability a person came for
actually lives, and one of the four north-star tasks.

Branch `program/latency-106` @ `77871d24`, cut from **CURRENT master `e15c2aa4`** (which is master *after*
`program/latency-104` merged mid-session — see "master moved" below). `migration_slot: none`,
`beat_schedule_change: FALSE`, no config var, no DDL, no frontend, no native. Six files.

---

## The issue said the build was slow. The build is not what a person pays for.

#1587 measured `GET /api/events/{id}/game-markets` on production at **2,250 ms for 8.5 KB** and
drew the right conclusion from the ratio — small payload, slow response, so the cost is query and
not transfer — and then pointed at the roster queries. That is a true statement about the build.

It is not the reason a person waits, because **almost nobody was ever getting a cached answer.**
The tier's only cache was, in full:

```python
_game_markets_cache: dict[int, tuple[float, str, dict]] = {}   # event_id → (ts, status, response)
_GAME_MARKETS_LIVE_TTL = 30
_GAME_MARKETS_MAX_SIZE = 30
```

A process-global dict of thirty entries. Three properties follow from that, and each of them
independently makes a hit unlikely:

* **It is per PROCESS.** `WEB_CONCURRENCY=2` puts two Uvicorn workers on every dyno, and there is
  more than one dyno. Two people opening the same game a second apart routinely land on different
  workers and both pay full price. The hit rate is divided by the fleet.
* **It holds THIRTY events**, evicted oldest-first, for a site whose feed shows dozens of games at
  once. On a busy evening the entry for the game you are about to open has already been evicted by
  the games somebody else opened.
* **It dies with the process.** Every deploy, every dyno cycle, every restart empties it.

So the tier had no shared cache at all. And — the part that actually costs the wait — **it had no
mirror**: a miss has never had anything to serve except a full rebuild.

That is the same shape LAT-P021 fixed for `/api/event/{key}` (#1107) and that #1651 records, still
open, for `hub.py`. The sentence from #1651 is the one that applies here without modification:
*while a miss costs a build, a slow enough build has no exit via user traffic.*

## 🔴 The serve-stale helper this needed was already in the file, forty lines above the dict

`_serve_stale_and_refresh` — strong task refs, in-flight single-flight, a `_STALE_SERVE_CEILING`,
its own session for the rebuild — was shipped by LAT-P116 into `routes/events.py` and sits at line
2026. `_game_markets_cache` is declared at line 2066. **Forty lines apart, and the tier between them
had none of it.**

This is LAT-P099's finding arriving again in the same file: a fix scoped to the surface that
surfaced the bug is how a class survives its own repair. LAT-P116 fixed the two caches it was
looking at (`_ei_cache`, `_team_cache`), wrote a long comment about why serve-stale beats a warmer,
and left the cache in the next paragraph alone.

## What shipped

`backend/app/utils/game_markets_cache.py` — the tier's policy, out of the route under ruling 005
(extract-on-touch), converted to the cache envelope on the way through
(`docs/contracts/cache-envelope.md`), and testable without a web request.

1. **A SHARED slot in Redis.** The second person to open a game *anywhere on the fleet* gets what
   the first one built. The in-memory dict stays in front of it as an L1 — it is faster than a
   Redis round trip and it was never the defect.
2. **A 24h mirror that is a first-class SERVE path**, not an error handler. On a primary expiry the
   reader gets the mirror and exactly one rebuild is scheduled behind it, through
   `_serve_stale_and_refresh`.
3. **The five envelope fields on the stored artifact**, so a served payload discloses when its
   content was computed, how far into reality the build had got, and whether it is live or stale.
   Additive on the wire: `set(served) - set(old_body) == {"cache"}`, asserted.

`cache_keys(key, prefix=...)` took its `prefix` parameter for exactly this — its docstring names
#1651's hub as the second customer that must not have to move its keys. This is the second customer
to actually arrive.

## 🔴 The mirror is age-bounded by status, and that is not decoration

This payload is a function of the **clock** as well as of the database: it filters player props
through `prop_window_closed(...)` and it publishes `served_event_status(...)`. A 24h-old mirror of a
LIVE game would show prop windows that closed hours ago.

That is a formatting lie arriving through a latency fix — and it would ship as a **win**, because
every latency number improves. So the mirror is served only while it is younger than
`STALE_SERVE_CEILING x fresh_ttl(status)`: **150 s for a game in progress, 5 h for a finished one.**
Past that the reader blocks and rebuilds, which is the pre-LAT-P121 behaviour. A permanently-failing
refresh degrades to slow, never to wrong.

The multiple is 5x — `_STALE_SERVE_CEILING`, LAT-P116's, from the same file. Deliberately: two
serve-stale ceilings in one route that disagreed would make which one a reader got a coin flip.

And the default when the stored status is missing is **not-final**, i.e. the SHORTER ceiling. The
failure mode of a missing field has to be a rebuild; if it were `completed`, a four-hour-old mirror
of a game in progress would be served. That is mutant **M2**, and it is killed.

## 🔴 The tier's codec is lossy, and the writer swallows its own failures

`encode_payload` is `json.dumps(payload, default=str)`. Any value that is not natively JSON survives
the Redis round trip as `str(value)` — a datetime comes back `"2026-08-29 09:00:00+00:00"` where
FastAPI's own encoder writes `"2026-08-29T09:00:00+00:00"`. So the **first** reader of a game would
get one shape and every reader after them another, in exactly the values nobody looks at. And
because `write_payload` swallows its own exceptions and logs, a genuinely unencodable value would
disable this cache **silently** — a latency fix that quietly does nothing is worse than no fix,
because nobody goes back to look.

Fixed by running `jsonable_encoder` before the store. That is what FastAPI was going to apply to
whatever this route returned anyway, so nothing on the wire changes, and it makes the codec lossless
by construction: **what is stored, what is served now, and what is served an hour from now are one
dict.** Mutant **M15** removes it and the guard kills it on a datetime.

## The freshness rule is carried across verbatim, and a test says so

`FRESH_TTL_LIVE == _GAME_MARKETS_LIVE_TTL` is asserted, not just written. This ship changes *who can
see a cached copy and what a miss costs*; if it also moved *how fresh a live hit is*, no later reader
could attribute a latency delta to either one. The finished-game TTL is the one number that changes:
the dict cached those for the life of the process, which was never a decision — it is what a dict
with no expiry does — and 3600 s is strictly tighter than unbounded, chosen against the 6-hourly
winner backfill so a payload cannot go on claiming a prop is ungraded long after it was graded.

## Gates

* `tests/test_game_markets_shared_cache.py` — **35 tests**, all asserting shape, TTL or CALL COUNT,
  none asserting wall clock, so they are deterministic in CI.
* Scoped: **172 passed, exit 0** (the new file plus the three pre-existing game-markets suites plus
  `test_mutation_guard.py`).
* **15/15 mutants killed**, 0 survived, 0 harness failures — and the battery prints its
  **denominator before the first verdict**, which is LAT-P120's finding paid forward: that cycle's
  battery reported `11/11 killed` over a table a third of whose entries had silently failed to
  append.
* Residue scanner **CLEAN, exit 0**.
* `ruff`: the two new Python files clean; `events.py` **44 = master's own 44, measured** (`ruff` on
  `git show origin/master:...` piped to `--stdin-filename`), so **+0**.
* Full backend suite: **21,475 passed / 0 failed / 124 skipped / 61 xfailed, 913.49 s, EXIT CODE 0
  READ BY VALUE**. 21,475 + 124 + 61 = **21,660**, and master `e15c2aa4`'s own collect is
  **21,625, MEASURED** in a throwaway worktree -> **21,660 = 21,625 + 35, exactly**. Backend delta
  **+35**, all of it this cycle's one new test file, enumerated AND measured.
* No frontend or native file is touched, so neither client gate is claimed.

## ⚠️ Master moved mid-session, and the branch was re-cut rather than rebased

The session opened with `origin/master` at `5e6c7419` and the work started in the `latency` worktree,
which was still on `program/latency-105` (unmerged). The directive forbids stacking on an unmerged
latency-8x/10x branch, so before the first commit the diff was lifted, `events.py` reverted, and
`program/latency-106` cut from `origin/master`. A `git fetch` at that moment showed master had
already moved again to **`e15c2aa4`** — `program/latency-104` had merged. The branch is cut from
`e15c2aa4`.

⚠️ One full-suite run was killed **by pid** on purpose (44495/44486) when that re-cut meant the tree
under it was about to change; never `pkill -f`, and no sibling lane's pytest was in `ps` at the time.
Its launcher exited 144, which is the launcher's own exit and not a verdict — the run produced no
verdict line at all, which is the tell.

## Not done, named so each is a decision

* **The build is not made faster.** #1587's 2.25 s is untouched; what changes is how many people pay
  it. Whether the ILIKE/roster arms of section 3 can be cheapened is a real question and it needs a
  production plan on a live tree, not a guess — parked **P121-1**.
* **No negative caching.** `cache_keys` carries a `negative` slot and this tier does not use it: a
  404 here means the event id does not exist, which is not a load-bearing cost, and a negative slot
  outliving an event's creation would be a new bug for no measured win.
* **No warmer.** Serve-stale needs no schedule to fail (LAT-P116's note): the rebuild is triggered
  BY the request that would otherwise have paid for it.
* **The 30-entry L1 bound is left alone** — parked **P121-2**. It is one of the three reasons the
  dict never hit, and the shared slot is what removes its importance; raising it is a memory
  decision on the web dyno and wants a number, not a guess.
* **`hub.py` (#1651) is still open** and is now the THIRD tier with this shape and the second
  customer this module was written for. Parked **P121-3**.

## Parked

* **P121-1** — cheapen the game-markets build itself (#1587's own diagnosis; measurement-lane ask).
* **P121-2** — `_GAME_MARKETS_MAX_SIZE`, and whether the L1 is worth keeping at all now.
* **P121-3** — `hub.py` / #1651: the third tier with the mirror-only-on-empty shape.
* **P121-4** — the gotcha: *a serve-stale helper forty lines above a cache that does not use it.*
* **P121-5** — the needle harness in the tree is **option c**; the directive still names **option
  b**. Seventh consecutive cycle to flag it (P116-6 → P117 → P118-5 → P119-5 → P120-5 → P121-5).
