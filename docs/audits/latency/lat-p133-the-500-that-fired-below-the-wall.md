# LAT-P133 — the 500 that fired below the wall

**Cycle 71 · issue #2303 (P131-2) · branch `program/latency-119` · pillar TRUTH**
**Ship: landing on the NFL playoff grid stops showing a bare error.**

---

## 1. The defect, and why the fix that was supposed to prevent it did not

`/api/playoffs/{league_slug}` wraps its build in `asyncio.wait_for(..., timeout=25)`.
#1484 made that wall degrade **truthfully**, and the reason it exists is worth restating
because this cycle is a second instance of the same failure class:

> The old behaviour returned `200 + {"teams": [], "columns": [], "error": "timeout"}` — an
> empty grid that every consumer reads as a successful response describing a league with no
> teams. The Grid Sentinel duly filed "MLB grid returned ZERO teams" plus four "missing
> column" defects — **five REAL defects that were all one timeout wearing a healthy costume.**

#1484's answer: on the wall, serve a *validated* last-good payload labelled
`degraded: true` + `degraded_reason`, and if there is no usable last-good, raise an explicit
**503** whose body says "this is a degraded state, not an empty league".

LAT-P131 measured five cache-bypassing rebuilds of the NFL grid on production, 2026-08-29:

| request | result |
|---|---|
| `?hours=168` | **HTTP 500 at 20.30 s**, no `x-timing-split` header |
| `?top=11` | **HTTP 500 at 20.30 s**, no `x-timing-split` header |
| `?top=11` (later) | 503 at 25.30 s (`unfinished=1`) — the route's own wall, behaving correctly |
| `?top=12` | 200 at 8.65 s |
| `?top=13` | 200 at 14.02 s |

🔴 **20.30 s is not the route's 25 s wall.** The third row is what the wall looks like when it
fires — 25.30 s, a 503, and the honest degradation contract. The 500s fired **five seconds
earlier** and never reached that code at all.

What fires at 20.3 s is Postgres' own `statement_timeout`. It does not arrive as a Python
timeout. The server cancels the running statement, asyncpg raises `QueryCanceledError`,
SQLAlchemy re-raises it wrapped in `DBAPIError`, and the route's `except asyncio.TimeoutError`
never sees it. Nothing else catches it, so it becomes a bare 500 and every line of #1484's
work is bypassed.

**The generalisable sentence:** a route that bounds itself with a wall has bounded itself
against exactly one clock. If a *lower* clock exists — and a database `statement_timeout`
always is one — then the route's degradation contract has a door in it that its own tests
cannot find, because its own tests only ever ring the wall.

---

## 2. What LAT-P131's warm beat did and did not do

LAT-P131 put NFL into `GRID_WARM_LEAGUES`, and that genuinely removes this from most users'
path: the beat builds under a 180 s pass budget, more than seven times the request's 25 s, and
the `:stale` mirror serves 24 h. But the warm beat is a *probability* argument, not a contract.
Whenever both cache keys lapse and a request has to build — a cold deploy, a beat that skipped
the league on budget, a 24 h gap in traffic — the 500 is still there and it is still on a public
route. #2303 exists because "usually warm" is not the reliability bar.

---

## 3. The fix, and the half of it that is a refusal

### 3.1 `app/utils/db_cancellation.py` — `is_query_canceled()`

**The test is SQLSTATE `57014` (`query_canceled`), not the exception's text.** The string form
of an asyncpg error is the server's `ERROR` message and is localisable; the SQLSTATE is defined
by the wire protocol and is the same five characters from every driver — asyncpg exposes it as
`sqlstate`, psycopg2 as `pgcode`. `57014` covers a `statement_timeout`, a client-issued cancel
and `pg_cancel_backend`; all three are "the database stopped this statement", which is exactly
the class a caller wants to degrade on, so no attempt is made to tell them apart.

Three chain links are walked, and they are not the same link:

* `.orig` — SQLAlchemy's wrapper attribute. **This is where production's SQLSTATE actually
  lives**, and a mutant that drops it is the one that would silently restore the 500.
* `__cause__` — an explicit `raise ... from ...`.
* `__context__` — an implicit re-raise inside an `except`.

The walk is depth-bounded (8) and cycle-safe. The bound is **documented in a test rather than
left to be discovered**: a 57014 buried deeper is not found, which is the right trade, because
a missed degrade is still a visible 500 while an unbounded walk on a pathological chain is not
visible at all.

🔴 **`asyncio.CancelledError` is refused whatever its chain holds.** This is the one guard that
looks defensive and is not. asyncpg cancels the running statement when its task is cancelled,
so a `CancelledError` *routinely* carries a real 57014 in `__context__`. Following it would read
a client hang-up as a database timeout and answer a degraded payload to a request nobody is
listening to any more. (Separately, the route's `except Exception` cannot see `CancelledError`
at all — it is a `BaseException` — so the route is safe twice over. The guard earns its line
for every *other* caller of the predicate.)

### 3.2 The route: one degradation path, not two that agree today

`_serve_grid_degraded(league_slug, cache_key, cache_eligible, reason)` is now the single
function both failures go through. The wall path and the DB-cancel path therefore produce the
same 503 body and the same last-good labelling **by construction**, rather than by two branches
that were written to match. A duplicated degradation path is a path that drifts, and the drift
is invisible until the rarer branch fires.

The one thing that differs is `degraded_reason`: `timeout` vs `db_query_canceled`. That is
deliberate. The Grid Sentinel prints `degraded_reason` verbatim into a critical finding, and
`precompute_category_pages` logs it — "the route's wall fired" and "Postgres cancelled the
statement" send an operator to different places, so collapsing them would cost real diagnosis
to buy an equivalence nobody asked for. Same **shape**, different **cause**, both stated.

### 3.3 🔴 The refusal is the load-bearing half

```python
    except Exception as exc:
        if not is_query_canceled(exc):
            raise
```

**This is not a widened `except`.** Only SQLSTATE 57014 is contained. A syntax error in our own
SQL, an undefined column, a dead connection, `too_many_connections`, a constraint violation and
an admin shutdown all re-raise here and still become a 500, where they stay visible in Sentry
and someone chases them. A 503 that says "degraded, try later" about a query bug is a lie, and
it is the *same* defect #1484 removed — a failure wearing a costume — rebuilt facing the other
way. Containment that cannot say no is a catch-all with better manners.

The contained case is logged with `exc_info=True` on purpose: containing this must not make it
invisible, and the only reason #2303 was findable at all is that the 500s were in Sentry.

---

## 4. The guards, and the mutant that was right

**44 new tests** in `tests/test_grid_db_cancel_degradation_lat_p133.py`, plus #1484's **27
existing tests passing unchanged** — the behavioural proof that extracting `_serve_grid_degraded`
changed no answers on the path that already worked.

What the new suite pins that a thinner one would not:

* **The refusal sweep is ten SQLSTATEs, not a sample** — and `57P01` / `57P02` / `57P03` are in
  it on purpose. They share SQLSTATE **class 57** with `query_canceled`, so a predicate matching
  on the class prefix passes every other case in the file and is still wrong.
* **SQLSTATE and class-name matching are isolated from each other.** `DriverError("57014")` is
  not named `QueryCanceledError`, so only the SQLSTATE branch can match it; a class named
  `QueryCanceledError` with no `sqlstate` attribute can only be matched by the subordinate
  branch. Deleting either branch fails exactly one test and nowhere else.
* **The driver fakes deliberately do not import asyncpg.** The predicate's whole claim is that
  it identifies the error without depending on the driver, and a test that imports asyncpg to
  build its input cannot observe that.
* **Shape equivalence is asserted by comparing the two paths to EACH OTHER** — `set(wall) ==
  set(cancel)`, and `{k for k in wall if wall[k] != cancel[k]} == {"degraded_reason",
  "stale_reason"}`. Two copied literal assertions would drift together silently, which is the
  precise thing this test exists to prevent.
* **A cancellation carrying a real 57014 is refused**, constructed as the driver actually
  produces it (`raise CancelledError` from inside an `except QueryCanceledError`).
* **The landmine:** every declared `GRID_FAILURE_*` constant must have a phrase in
  `_GRID_FAILURE_PHRASE`. A third failure mode added without one would print a 503 body with no
  cause, and nobody would notice until an operator read one.

**Mutation battery: 18/18 killed, exit 0, restore SHA-256 identical on both targets.** The
mutants pull in *both* directions — eight narrow the predicate until the 500 returns, three
widen it until a query bug is served as "try later", seven attack the route's degradation
itself (`M-CATCH-ALL`, `M-NOT-DEGRADED`, `M-LAUNDER-UNUSABLE`, `M-500-NOT-503`). A battery that
only pulled one way would wave through the catch-all, which is how this class of defect gets
rewritten as a worse one.

🔴 **`M-NO-CAUSE` SURVIVED the first pass, and the MUTANT was right — the guard was weak.** The
test had been written the obvious way, `raise RuntimeError(...) from inner` inside an `except`
block; Python sets `__context__` as well as `__cause__` there, so the assertion passed with
`__cause__` deleted from the walk. The test now raises **outside** a handler and asserts
`outer.__context__ is None` before asserting the predicate. Recorded here rather than quietly
re-run into a green number: this is the second consecutive latency cycle where the first battery
pass found something, and both times it was found because the battery ran before the report was
written, not after.

---

## 5. Gates, every exit code read by value

| gate | result |
|---|---|
| full backend suite | see §6 — reconciled to branch collect |
| new suite + #1484's suite | **71 passed, exit 0** (44 new + 27 existing) |
| mutation battery | **18/18 killed, exit 0**, restore SHA-256 identical, 0 harness failures |
| residue scan (on a commit) | **CLEAN exit 0** — 289 needles verified, 844 broad checks; the same two pre-existing `typeahead_warmer` needle drifts master carries |
| smoke (`test_startup.py`) | 4 passed, exit 0 |
| ruff | **net 0** — `playoffs.py` 10 → 10 (all pre-existing, none in the changed region); the three new files **clean** |
| frontend `npm run build` (ESLint gate) | exit 0 |
| frontend `npm run typecheck` (TS gate) | exit 0, **70 = baseline 70** |
| `merge-tree` vs `origin/master` | exit 0, re-derived at the final head |

⚠️ **The branch was REBASED mid-cycle and every gate above was re-run on the rebased tree.**
It was cut from `eeb32617`; `origin/master` advanced to `8ca1e2ed` while the first full-suite
run was in flight, and the move **merged `-116` (LAT-P130) and `-117` (LAT-P131)** — one of
which edits `playoffs.py`, the same file. The first suite run was **killed, not quoted**. The
lane has a same-week worked example of why this is not paranoia: INT-151 saw git auto-merge
`sport_keys.py` with no conflict and silently drop a function a queue depended on. `merge-tree`
exit 0 is a statement about text; the suites on the rebased tree are the statement about
behaviour.

---

## 6. Owed after deploy

Nothing post-deploy is claimed here. What the next cycle should read:

1. **Re-run the two 500s.** `/api/playoffs/nfl?hours=168` and `?top=11` against the recorded
   `HTTP 500 at 20.30 s`. The expected shape is a 503 with `degraded state, not an empty
   league`, or a 200 carrying `degraded_reason: db_query_canceled`.
2. **Read the Sentry group.** `DBAPIError ... canceling statement due to statement timeout`
   should stop producing 500s and start producing the contained `logger.error`. Read the **24 h
   stats buckets, not `count`** (gotcha #49) — `count` is lifetime.
3. **Watch the Grid Sentinel** for `grid_degraded` findings carrying the new
   `db_query_canceled` reason. A rise there is not a regression; it is the defect becoming
   *visible*, which is the point.

---

## 7. Parked

* **P133-1** — `backfill_winners._is_statement_timeout` (line ~7008) is a second, weaker
  implementation of the same predicate: it matches on class-name prefix and on the message
  text, which is what §3.1 argues against. It should become a caller of
  `app.utils.db_cancellation.is_query_canceled`. **Not taken here on purpose**: it is a pure
  refactor of a 7,000-line hot file with no ship attached, and the rider rule says architecture
  rides a queued ship rather than being the cargo. It rides the next cycle that touches
  `backfill_winners` for a user-visible reason.
* **P133-2** — the same lower-clock exposure is untested on every *other* route that wraps a
  build in `asyncio.wait_for`. `/api/feed` has its own budget machinery; the golf schedule and
  the futures category pages have walls. **Measurement, not build**: a census of
  `wait_for`-bounded routes and which of them can see a `statement_timeout` below their wall,
  staged to `PARKED-MEASUREMENTS.md`.
* **P133-3** — nothing in the repo pins what production's `statement_timeout` actually is. It
  was *inferred* at ≈20 s from two matching 500s, which is a sample of two. The route's 25 s
  wall is chosen against a number nobody has read. Measurement lane.
* Carried forward: **P132-1** · **P132-2** · **P132-3** · **P132-4** · **P132-5** ·
  **P131-3** · **P131-4** · **P130-1** · **P130-2** · **P130-3** · **P129-1** · **P129-2** ·
  **P129-3** · **P129-5** · **P128-1** · **P127-1** (**UNBLOCKED — `-109` merged**) ·
  **P127-3** (NEEDS ALEX) · **P127-4** · **P127-5** · **P126-1** · **P125-A** · **P125-1** ·
  **P125-2** · **P124-1**–**P124-5** · **P110-4** · **P122-5**.
* **P131-2 is DISCHARGED by this queue.**
