# LAT-P142 — the keystroke that was a table scan

**Pillar: DISCOVER (the Search tab's category browse).**
**Ship: typing in a category's search box stops running a table scan for every letter.**

Issue **#2313**. Branch `program/latency-127`, cut from `origin/master`
`944c466e`. No DDL · no migration · no beat change · no config var · **frontend
only** (plus one un-imported harness script) · zero ios files.

🔴 **NEW BRANCH, NOT `-126`.** `program/latency-126` carries LAT-P141 at
`cbb87fc6` with a `ready_for_integration` token against that exact SHA. A commit
on it would have moved the head and **withdrawn** that token (ruling 085), so
this queue is cut fresh from master. LAT-P141 is untouched and still ready.

---

## 1. The cold path, first

Per ruling 137 this report opens with what a user walks, not with the thing this
queue fixed. Canonical instrument, this session, before any probing:

```
surface        path key          served  cold  p50 wait
Discover open  discover_native        5     0      61.0
               discover_web           5     0      18.0
tab loads      sports_native          5     0      54.0
               sports_web             5     0      13.0
               search_trending        5     0      18.0
               my_stuff_stats         5     5      14.0
cold search    search_cold            6     6     246.0

NEEDLE = 18.0 ms   (median of 7 per-path p50s, all 3 graded surfaces served)
DIAG   = REFUSED — only 2 of 7 member paths went cold (floor 4)
```

**The needle did not move this cycle and is printed unmoved: 18 ms, the same as
the series start.** It could not have moved: `/api/futures/browse` is not a
member of the pool, and nothing this queue changed is on a member path. Saying
so is the point — a lane that only reports the cycles where its dial moves is
reporting a filtered series.

The DIAG refusal is the warmer winning again, which is the standing reason
option-c exists. It is a null, not a fast number.

## 2. Where the finding came from

The organic `latency-stats` census read (taken BEFORE probing, ruling 127) put
`/api/feed`'s miss p50 at 1,066 ms over 60 of 127 samples — which is LAT-P141's
defect, already banked and waiting on the Integrator. The conveyor asks for the
highest-impact cold path **with no banked fix**, and the lane's own parked list
names one twice:

* **P122-2** (LAT-P122) — `/api/futures/browse` is the other half of the
  `/search` surface's cost. Parked because `program/ux-122` was in flight and
  rewrites `browse_futures`' item loop.
* **P141-5** (LAT-P141, yesterday) — "the real defect there is that its
  in-category search box is **undebounced**, so every keystroke issues an
  uncached `%q%` query. Own cycle."

`program/ux-122` is *still* in flight — its most recent commit is
2026-08-29 12:35 PT and its hunk `@@ -696,26 +696,76 @@` sits inside
`browse_futures`. So the backend half is still parked for exactly the reason it
was parked in August, and this queue takes the half that is free: ux-122's only
`CategoryBrowser.tsx` change is a one-line export on `CompactMarketCard`, a
different region from `CategoryMarkets`.

## 3. The measurement

`bainluck.com/search` → a category tile → the "Search politics…" box inside the
panel. `CategoryMarkets` put the raw input value into its SWR key, so typing
`super` issued five requests to `GET /api/futures/browse` — and `handleSearch`
cleared the rendered list on each one, so the panel flashed skeletons on every
letter.

Served, production 2026-08-30, `x-response-time`, `category=politics`, n=2:

```
q='s'    263, 166 ms         q='sup'    26,  18 ms
q='su'    73, 109 ms         q='supe'   17,  19 ms
                             q='super'  33,  17 ms
```

There is a cliff between two and three characters, and it is not noise.
`EXPLAIN (ANALYZE, BUFFERS)` on the statement the route emits, same day:

| `q` | exec | shared blocks | plan |
|---|---|---|---|
| `s` | 132.8 ms | **4,821** | Bitmap Heap Scan on `ix_fm_feed_open_sports`, 898 rows removed |
| `sup` | 16.1 ms | **40** | BitmapAnd on **`ix_futures_name_trgm`** + `ix_fm_open_category` |

`q` reaches the route as an unanchored `FuturesMarket.name.ilike(f"%{q}%")`, and
the GIN trigram index that serves it needs **three characters** before it can
produce a trigram to look up. Below that Postgres has no option but to scan.

**So the first two letters of every search cost ~120x the buffer traffic of the
query that immediately supersedes them, and nobody ever reads their results.**
The endpoint has no cache of any kind, so each one is paid in full, every time,
by every visitor.

### 3.1 Why this was never going to show up as a slow page

The request a person actually waits for is the *last* one — the cheap,
trigram-served one. Every discarded prefix is invisible to a page-load
measurement because no page load is waiting on it. It is real server work with
no user on the other end of it, which is why it survived two cycles that were
looking straight at this surface.

## 4. The fix

A 200 ms debounce between the input and the SWR key. Typing at speed issues
**one** request, for the whole word; the rendered list survives typing instead
of flashing skeletons.

200 ms is `MobileSearchOverlay`'s value — the other input in this app that gates
a network call behind a debounce.

Surveyed rather than assumed: of the user-facing text inputs whose value drives a
**network request**, `SearchBar` (150 ms), `MobileSearchOverlay` (200 ms) and
onboarding's four (location / follow / school / rival) all debounce, and this box
was the only one that did not. `TemperatureMap`'s "Search cities…" is not a
counterexample — it filters an in-memory array and issues nothing. Admin surfaces
(`/admin/*`) have undebounced inputs too and were **not** surveyed; they are not
user-facing and are out of this lane's remit.

The debounce is a shared primitive (`lib/searchDebounce.ts`), framework-agnostic
and timer-injectable, the same shape as `createPrincipalDebouncer` next door and
for the same stated reason: it makes the coalescing a deterministic fake-timer
test rather than a browser exercise.

🔴 **It is deliberately NOT a minimum-length gate.** Refusing to search for `US`
would eliminate the expensive queries outright, and it would also change what a
person SEES — which is a product decision and not this lane's to make. The
results are preserved exactly. A slow typist still gets every prefix they pause
on, and there is a guard asserting that, because cancelling too eagerly would be
a worse bug than the one being fixed (gotcha #43's shape: a search box that
never searches).

**What this does and does not remove**, stated so the post-deploy read is not
over-claimed: it removes the prefixes nobody asked for. It does not remove a
short query someone deliberately types and stops on, and it does not make any
individual query faster. The server-side half that would is parked below.

## 5. Gates — all run on `45314abf`, cut from and gated against `944c466e`

| gate | result |
|---|---|
| `npm run build` (ESLint gate) | ✅ exit 0 |
| `npm run typecheck` (TS deploy gate) | ✅ exit 0 — **70 errors, baseline 70**, no new, count matches |
| `npx jest` full suite | ✅ **4,375 passed, 4 skipped, 234 suites — exit 0** (2.5s) |
| new guards (19: **10** pure + **9** wiring) | ✅ PASS |
| `scripts/lat_p142_mutation_battery.py`, 15 mutants | ✅ **15/15 killed**, 0 survived, 0 harness failures, both targets restored SHA-256 identical |
| `scan_mutation_residue.py` on the commit | ✅ CLEAN — 344 needles, 0 residual mutants |
| `tests/test_startup.py` smoke | ✅ PASS (4) |
| backend suite | **not run — zero backend app files in the diff.** The one Python file added is a harness script nothing imports |
| `merge-tree --write-tree origin/master HEAD` | ✅ exit 0, 0 conflicts |

Suite reconciliation: this branch is **4,375 passed**, and the two new files
contribute **10 + 9 = 19** (measured per-file). That puts the pre-branch tree at
4,356 — **derived by subtraction, not measured**: the full suite was run on this
branch only. Saying so rather than quoting 4,356 as though it were a reading.

## 6. Post-deploy verification

The instrument is the served-time ramp in §3, same shapes, same n:

```bash
source ~/.claude/.env
for q in s su sup supe super; do
  curl -s -o /dev/null -D - "$BAINLUCK_API/api/futures/browse?category=politics&limit=20&offset=0&q=$q" \
    | grep -i x-response-time
done
```

🔴 **That ramp is the CONTROL, not the result, and it will not move.** The
server is unchanged; each individual query costs exactly what it cost before.
What changes is how many of them a browser issues, and the only honest way to
read that is on the client: type `super` into a category box with the network
panel open and count the requests to `/api/futures/browse`. **Five before, one
after.** A latency number quoted for this ship would be measuring the wrong
thing.

Do not take any post-deploy read inside five minutes of a release
(`reference_post_deploy_latency_not_evidence`).

## 7. Parked

**P142-1 — `/api/futures/browse` has no server-side cache, and the policy falls
straight out of §3's plans.** Cache exactly the queries the trigram index
*cannot* serve — `q` absent, or `q` under three alphanumerics — which is
precisely the expensive set (4,821 blocks) and a bounded key space (~42
categories x a few pages, plus the short prefixes actually typed). Leave the
fast trigram-served long tail uncached so Redis never fills with it. The
no-query tile click is the volume case: 43.7 ms of DB inside a 153–305 ms served
request, paid by every visitor on every category open, with no warming between
three consecutive reads. **Blocked on the same thing P122-2 was**: `program/ux-122`
is unmerged and rewrites this function.

**P142-2 — the gap between 43.7 ms of DB and 153–305 ms served on the no-query
tile click is app-side**, and unattributed. `selectinload` on outcomes plus the
item loop is the suspect; the mean browse market has 6.3 outcomes (ux-122's own
measurement). Worth a decomposition before P142-1 assumes a cache is the whole
answer. MEASUREMENT lane.

**P142-3 — `ix_fm_open_category` is load-bearing in the fast plan.** It appears
in the `BitmapAnd` alongside `ix_futures_name_trgm` for `q='sup'`. This is
evidence for **P140-1**, the standing "grade it or drop it" question in
`alex-inbox/latency-006`: on this path it is doing work.

**P142-4 — a minimum-length gate would remove the expensive queries entirely**
and is a product call, not a latency one. Named here so the option is visible to
whoever owns the surface rather than quietly foreclosed: it trades "typing `US`
shows results" for ~4,800 buffer blocks per such query. Not this lane's to make.

Carried unchanged: **P141-1**…**P141-6** (LAT-P141, in flight), **P140-1**
(needs Alex, `alex-inbox/latency-006`), **P140-2**, **P140-3**,
**P129-1**…**P129-5**, **P122-2** (now restated as P142-1 with the plan
evidence).

---

DIAG: latency-build REFUSED @ 2026-08-30T07:28:59+00:00 — only 2 of 7 member paths produced a cold sample (floor 4); only 2 of 3 graded surfaces went cold (missing: Discover open)

NEEDLE: latency 18 ms @ 2026-08-30T07:28:59+00:00
