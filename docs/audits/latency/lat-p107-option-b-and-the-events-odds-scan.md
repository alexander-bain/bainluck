# LAT-P107 — the needle becomes option b, and the league page stops re-reading every odds snapshot it ever took

**NEEDLE: latency 940 ms @ 2026-08-28T18:34:40+00:00** (first point under the new
definition; series 882 → 873 → **940**.)

Two items, both closed. Item 1 is Alex's option-b ruling applied to the instrument.
Item 2 is a build, deliberately rooted on current master so the integrator's five-deep
stack does not grow while it waits.

---

## The cold path a user walks (ruling 137 opens every report with these)

Production slug `bddb5f3f`, uptime 5,037 s (warm). Sandbox transport wall floor
236.5 ms; every number below is SERVER time (`x-response-time`), not wall.

```
surface        path key          graded  cold  cold%  p50 cold
Discover open  discover_native        5     5   100%   1,636.0
               discover_web           5     1    20%   1,267.0
tab loads      sports_native          5     5   100%     612.0
               sports_web             5     1    20%   1,771.0
               search_trending        5     0     0%         —
               my_stuff_stats         5     5   100%      11.0
cold search    search_cold            6     6   100%     379.0
               Browse                 —     —      —         —   (no request on appear)

EQUAL-WEIGHTED COLD p50 = 939.5 ms   (median of 6 per-path cold medians, 6/7 paths,
                                      all 3 graded surfaces represented)
demoted cross-check: RAW POOLED cold p50 = 576.0 ms over n=23, max 10,214.0 ms
```

Organic `/api/admin/latency-stats` taken **before** the run (`--stats-before`,
ruling 127): `/api/feed` n=90, p50 35.6 ms, p95 1,757.8 ms.

**Contamination declared:** 30 `/api/feed`, 20 other read-only tab requests, 6
`search_query_logs` rows from cold search (#1916), 6 non-voting typeahead, 4
`/api/health`. Plus item 2's own probing, declared in its section below.

### Reading the move honestly

873 → 940 ms is **+7.7 % with nothing deployed between the two readings** — same slug
`bddb5f3f` both times. It is not a regression and it is not a win; it is the first
estimate of the new statistic's own run-to-run noise, and the number to keep is that
the noise band is now single-digit percent rather than the raw pool's 25 %. The member
set is comparable (6/7 both times; `search_trending` was the absentee in both).

Per the convention, the attribution check: `discover_native` 1,739 → 1,636 ms,
`sports_native` 707 → 612 ms, `search_cold` 563 → 379 ms — three members got faster;
`discover_web` 2,190 → 1,267 ms. The median rose anyway because `sports_web`
contributed 1,771 ms this time (it contributed 1,057 ms before) and it now sits at the
median position. That is a one-cold-sample member moving the median — a thinness
effect, not a product change. **No claim of a move in either direction is made.**

🔴 **Worth Alex's eye, independent of the metric.** The pool max was **10,214 ms** on
`discover_native`, against `DiscoverViewModel.retryBudget = 6,000 ms`. LAT-P106 flagged
a 5,802 ms max as "~200 ms from the point where the native client gives up and paints
disk last-good". This one is past it. One sample is one sample, but it is the second
consecutive reading in which the worst cold Discover open approached or crossed the
client's abandon threshold.

---

## Item 1 — the needle is now the equal-weighted cold p50 (Alex, option b)

LAT-P106 published the raw pooled median, measured it moving **711 → 536 ms (−25 %)**
on identical code ten minutes apart while Discover's own cold open got twice as *slow*,
and put the choice to Alex. Alex ruled **option b**.

**Shipped:** `needle_ms` is the median of the per-member-path cold medians — each of
the pool's seven paths counted once — and that is what the `NEEDLE:` line carries. The
raw pool is still computed and printed every run, demoted to a cross-check, because it
is the composition signal. JSON schema bumped to `latency-needle/2`.

**The series restarts at 882 → 873.** Those are LAT-P106's own equal-weighted readings.
Its 711 and 536 are a different statistic and are now fenced off in three places: the
script's docstring, `README.md` §2, and a superseded-statistic banner at the top of
`lat-p106-the-needle.md`. Ruling 127's clause is the reason — a delta of instruments
must not be readable as a delta of latency, and here the two differ by ~370 ms on the
same run.

### The part that was not in the ruling, and had to be

Equal weighting fixes *how often* a path missed. It does **not** fix *whether* it
missed: a member with no cold sample is absent from the median rather than counted
slow, and **the median of one surviving 11 ms member is 11 ms.** LAT-P106's own
self-poisoning read — 6 of 7 members with zero cold samples and a single 11 ms sample
on the seventh — would therefore have published `11 ms` under a naive option-b swap,
because the old floor only counted total samples and the old floor was the only thing
that stopped it the first time.

So the refusal is re-expressed in the new statistic's own terms. Three floors, and the
run prints which ones fired rather than one generic message:

| floor | value | what it stops |
|---|---:|---|
| `MIN_POOL_N` | 8 cold samples | inherited — a median over nothing |
| `MIN_COLD_MEMBERS` | 4 of 7 member paths | a median describing a minority of the pool |
| `MIN_SURFACES` | 3 of 3 graded surfaces | a line claiming "across the three graded surfaces" while describing one |

**Which "surface" is weighted once is written down so it cannot drift.** The unit is
the MEMBER PATH (seven), not the three surface GROUPS. That is what produced 882 and
873, and 882/873 is what Alex ruled on. The group-weighted reading is a different
number; taking it would be a silent re-base and needs another ruling, not an edit. The
docstring says so at the top.

### Gates (item 1)

- `backend/tests/test_needle_latency.py` — **13 passed**, exit 0 (was 10).
- RED-FIRST, three mutations, each applied alone from a `cp` pristine backup with the
  restore verified by `filecmp` before the next; the harness refuses any pattern that
  matches other than exactly once, so a no-op cannot read as a pass.

  | | mutation | result |
  |---|---|---:|
  | M5 | revert the line to the raw pool | **1 fail** |
  | M6 | drop `MIN_COLD_MEMBERS` | **1 fail** |
  | M7 | drop `MIN_SURFACES` | **2 fail** |

- The two new floor tests are written so each drives its floor **in isolation** — the
  other two floors are asserted satisfied inside the test — so a test cannot pass for
  the wrong reason.
- ruff clean, black clean.

---

## Item 2 — #1605: the MLB league page takes **17.8 seconds** to list its games

**Ship, in user-visible terms: a league page stops waiting on a scan of every odds
snapshot it has ever recorded.** `/sports/mlb` calls
`GET /api/events?sport=baseball_mlb&days=14`. Measured on production today, slug
`bddb5f3f`, with `/api/health` interleaved as a control:

| pass | `/api/events?sport=baseball_mlb&days=14` | control `/api/health` |
|---|---:|---:|
| round 1 pass 1 | **17,897 ms** | — |
| round 1 pass 2 | 1,914 ms | — |
| round 2 pass 1 | **17,824 ms** | 233 ms |
| round 2 pass 2 | 756 ms | 236 ms |
| round 2 pass 3 | 1,090 ms | 238 ms |

131 events in that response, every pass. `americanfootball_nfl`: 8,991 ms then 555 ms.
`basketball_nba`, **out of season**: 274 ms and 245 ms — at the control's floor.

The in-season/out-of-season split is the whole diagnosis in one line: the cost tracks
**how much snapshot history the page's events carry**, not how many events there are or
how big the response is. Two 17.8 s passes ~30 s apart says the fast passes are a warm
Postgres buffer cache on one dyno, not a response cache — there is none on this route.

### What the route was doing

`list_events` carried the exact shape LAT-P013 then LAT-P030 retired from
`/api/events/search`:

```python
row_number() OVER (PARTITION BY event_id, bookmaker ORDER BY captured_at DESC)
```

over **every snapshot of every event on the page**, joined back to `odds_snapshots` by
id, to keep one row per bookmaker. It reads O(SNAPSHOT DEPTH) to return O(BOOKMAKERS),
and Tier-1 sports poll every 32 s, so depth is the part that grows. Measured today via
`db-query`: one pre-game MLB event carries **750 snapshots across 18 bookmakers**. Times
131 events, that is ~98,000 rows read, sorted and windowed to return ~2,350.

Corroborating the volume the way the issue did: `SELECT event_id, count(*) … GROUP BY
event_id` over events commencing in the last two days **exceeded the 10 s admin
statement timeout**. The counting query cannot finish; the route does the same read on
every request.

### The fix

One line per site: delegate to `latest_odds_per_bookmaker_query`, the module-level
helper LAT-P030 extracted precisely so this would be a call and not a copy. It
enumerates the distinct bookmakers with a recursive loose index scan off
`ix_odds_snapshots_bookmaker_closing` and fetches exactly one row per
`(event, bookmaker)`. On the sibling route that measured **6,724 ms → 185 ms (36x),
78,800 rows read → 947, byte-identical output.**

**Two sites converted, not one.** The issue asks to check whether any other route
repeats the shape before closing, so all three `row_number()` odds windows in
`routes/events.py` were surveyed:

| site | route | verdict |
|---|---|---|
| `list_events` | `GET /api/events` | **converted** — the issue's named target |
| `get_event` | `GET /api/events/{id}` | **converted** — same window over ONE event, plus a second round trip to re-fetch by id, now one query |
| `search_suggestions` | `GET /api/events/search-suggestions` | **surveyed, deliberately left** |

The third is a *related* shape, not the same one: it partitions by `event_id` alone
under a fixed `bookmaker == "aggregate"`, so the helper — whose entire mechanism is
enumerating the distinct bookmakers — does not fit and cannot be reused. It carries the
same underlying cost but needs its own top-1-per-event helper and its own equivalence
proof. Bolting an unproven second rewrite onto a latency queue is the LAT-P010 failure
this module's history records. It is a separate, smaller ship on a non-graded surface,
and the code says so at the site.

### What is claimed for the detail route, and what is NOT

`get_event` is called once per pinned event by My Stuff and Preferences
(`fetchEventsByIds` → `Promise.allSettled` of N `fetchEvent` calls), so the fan-out is
real. But **it is not currently slow and this report does not claim a win there.**
Measured today: five events including the 750-snapshot MLB one all returned in
215–241 ms against a 233–285 ms control — at the floor. The window form bounded MEMORY
(it returned ~19 rows, not 750) but not WORK, and at 750 rows the work is cheap.

So the detail conversion removes a **latent** cost that scales into a live Tier-1 game
(the issue records 13,522 snapshots on one measured Red Sox event) and saves one round
trip. That is a real improvement and an honest one; it is not a measured user-visible
speedup today, and calling it one would be the thing this lane keeps a scar about.

### Correctness — the part a shape assertion cannot establish

Set-identical by construction, and proven by execution rather than argument.
`tests/integration/test_search_odds_enrichment_equivalence.py` already runs the helper
against real Postgres and diffs its rows against the shape LAT-P030 replaced. That
oracle is the `DISTINCT ON` form — which **these two routes never ran**. Diffing
against it would prove agreement with a shape they never had, so both original windows
are reconstructed and diffed against directly:

- the page window (`PARTITION BY event_id, bookmaker`, join back by id)
- the detail window (`PARTITION BY bookmaker` under `WHERE event_id = :id`, ids
  projected for a second fetch)

The oracles are given an `id DESC` that production did **not** have. That is deliberate
and is the one accepted behavioural difference of the rewrite, already ratified:
`row_number()` left the choice among equal `captured_at` arbitrary, so an oracle without
the tiebreak would make a coin flip look like a disagreement. The tie is then asserted
on its own terms against the **untiebroken** window — what production actually ran —
where the property that must hold is cardinality: exactly one row, never two (a doubled
book in the aggregate) and never zero (a dropped book).

Four new equivalence tests: page-shape identity across the seeded set, detail-shape
identity on the deep event, zero rows for an event with no snapshots (the walk must not
emit its NULL terminator as a snapshot), and the tie cardinality.

### Gates (item 2)

- `backend/tests/test_events_odds_enrichment_shape.py` — **6 passed**, new file.
  Asserts the *delegation* rather than re-asserting the helper's internals per site:
  `test_search_latency_contract.py` already pins those (loose index scan present,
  `LIMIT 1`, strict `>` advance, `id DESC`, no `row_number()`, no `DISTINCT ON`), and
  making all three routes delegate is what puts all three under those existing gates.
  Comments are stripped before matching — both call sites now quote the anti-pattern
  they replaced, including the literal `row_number()`, so a naive substring check would
  match the explanation and pass.
- A **two-directional census guard**: `routes/events.py` must contain exactly **one**
  remaining `func.row_number()` (the surveyed `/search-suggestions` one). UP catches a
  fourth site or a revert; DOWN catches the surveyed one changing without its
  equivalence proof. Both directions fail, and the fix is to update the constant *with
  the reason*.
- `test_search_latency_contract.py` — **91 passed**, unchanged, still green.
- 🟡 **The four new equivalence tests could not be run in this window.** They are
  real-Postgres-only (`SEARCH_TEST_DATABASE_URL`) and there is no local Postgres in
  this sandbox — `initdb` dies on `shmget`. They collect cleanly (9 skipped, exit 0)
  and all three new query builders were **compiled to Postgres SQL offline** to prove
  the SQLAlchemy is valid, but their first real execution is the `search-recall` CI
  job. They live in the file that job already invokes, so no workflow change is needed
  and they cannot be a test nobody runs. **This is stated as a gap, not glossed.**
- `python3 -c "from app.main import app"` — import OK.
- **Full backend suite: 20,574 passed, 116 skipped, 61 xfailed, 0 failed — exit code
  0, 841.32 s**, on code tree `d3c6f728`. Read by VALUE.

### Two things the suite did that a green line would hide

**The first run of it was RED — 30 failures.** Every one surfaced as
`TypeError: '>=' not supported between MagicMock and datetime` inside the staleness
filter, about thirty frames from the cause. `_make_event_detail_session`'s
`mock_execute` routes by SQL *text* and tested `"events" in stmt_str` first; the
helper's recursive bookmaker walk **seeds from `events`**, so its SQL names both
tables and matched the event arm — the double handed the route an Event object where
it expected snapshots. The old `row_number()` query named only `odds_snapshots`, which
is the only reason the old ordering ever worked. Not a production bug: a test double
that could not express the new statement. Fixed by testing `odds_snapshots` first,
which is strictly the more specific test.

**Found while bisecting that: two test files are order-dependent.**
`event_detail_client` clears `_game_markets_cache` but not `_event_detail_cache`, and
its event is id=1 — the same id every specimen in
`test_event_detail_duel_percents_2085` uses. Run those two files in the other order
and three seeded tests read a **0.505** hero probability out of the duel file's last
specimen and fail asserting 0.65. They pass in CI only because `integration/` sorts
before `test_e…`. That is luck, not isolation, and it cost real time here — three
residual failures read as a regression they were not. Fixed and proven
order-independent in both directions. Pre-existing on master; found because this queue
happened to run the two files together.

**An earlier suite run was killed mid-flight** and left a truncated file at 10 % with
no verdict line — no failures, no traceback. It was read as "still slow" for several
minutes before `ps` showed the pid was gone. A pytest that stops writing at a
percentage is a dead gate, not a slow one (gotcha #54's shape, one level out: the tell
is the MISSING verdict line). The result above is from a clean re-run.

### Contamination declared by item 2's probing

19 `GET /api/events` requests (3 shapes), 11 `GET /api/events/{id}`, 9 `/api/health`
controls, 2 `POST /api/admin/db-query` (one of which timed out and is therefore absent
from `pg_stat_statements`, which never records errored statements). No writes.

### Owed after deploy — pre-registered here, unrun

1. Re-run the MLB league-page shape (`?sport=baseball_mlb&days=14`), 5 passes, control
   interleaved, **past the 5-minute post-deploy window** — a fresh slug reads as a
   regression. Compare against the 17,897 / 17,824 ms cold passes above. Expect the
   cold pass to fall to low seconds or below; a cold pass still in double-digit seconds
   means the enrichment was not the binding cost and this report is wrong.
2. `basketball_nba` (out of season, 274 ms today) as the negative control: it must NOT
   move. If it does, something other than the enrichment changed.
3. Confirm the payload is unchanged on a sampled set of event ids — `count` and the
   per-event bookmaker sets — against a capture taken before the deploy.

---

## What is NOT claimed

- **No needle move.** 873 → 940 ms with nothing deployed. The reading is published
  because the convention says publish it, not because it means anything yet.
- **Item 2 will not move the needle either, and that is expected.** `/api/events` is
  not a graded surface — Browse issues zero requests on appear — so the league page's
  17.8 s is invisible to the pool. It is a real user-visible latency ship on a route
  the needle does not cover. Both facts belong in the same sentence.
- **No production measurement of the fix.** The branch is unmerged and undeployed; the
  36x is the *sibling* route's number and the shape is provably the same, but the
  traffic is not. The post-deploy checks above are owed.
- **The detail route is not currently slow** (215–241 ms at the floor, 750-snapshot
  event included). Latent cost removed, not a measured win.
- **`/search-suggestions` still carries the third window.** Surveyed, understood,
  deliberately left, and pinned by a census guard so it cannot be forgotten.

NEEDLE: latency 940 ms @ 2026-08-28T18:34:40+00:00
