# LAT-P127 — the page that sorted 189,312 rows to print 256

**Pillar: DISCOVER. Ship: tapping a championship market from Discover — "NFL Super Bowl Winner",
"MLB World Series Winner" — stops taking three to six seconds before anything renders.**

Branch `program/latency-113`, cut from `origin/master` @ `d9b76e9b`. `migration_slot: none`,
`beat_schedule_change: FALSE`, 5 files.

---

## 1. The item this cycle was handed, and why it was not the item

LAT-P126 parked **P126-2**: "the same three-read sweep over the still-free `/api/market-moves`,
`/api/events/ei-rankings`, `/api/sports/hierarchy`." That list was run first, exactly as handed over,
and **all three are dead ends — but for three different reasons, and the distinction is the reusable
part.**

| candidate | three reads | server split | verdict |
|---|---|---|---|
| `/api/market-moves` | 0.58 / 0.79 / 0.85 s | `db=107.6 app=19.3 q=4` | real cache defect, **but zero callers** |
| `/api/events/ei-rankings` | 0.62 / 0.51 / 0.50 s | `db=164.0 app=21.7 q=4` | real db cost, **but zero callers** |
| `/api/sports/hierarchy` | 0.27 / 0.26 / 0.26 s | `db=0.0 app=3.3 q=0` | **at the control floor** — nothing to fix |
| `/health` (control) | 0.26 / 0.27 / 0.26 s | — | the sandbox transport floor |

🔴 **A "STILL-FREE ENDPOINT" IS NOT A CANDIDATE. A STILL-FREE ENDPOINT SOMEBODY CALLS IS.** P126-2's
list was derived by asking which endpoints no unmerged branch had claimed. Two of the three are
`export`ed from `frontend/lib/api.ts` and called from **nowhere**:

```
grep -rn "fetchMarketMoves" frontend/   → frontend/lib/api.ts:1193 (the definition). Nothing else.
grep -rn "fetchEIRankings"  frontend/   → frontend/lib/api.ts:550  (the definition). Nothing else.
```

Caching either one ships nothing a person can see. The freeness check (gotcha #155) answers "will
this collide?"; it does not answer "does this endpoint gate a first paint?" **Both questions have to
be asked, and the caller check is the cheaper one — run it first.** Thirty seconds of `grep` would
have saved P126-2 from being staged at all.

### The candidate list that replaced it

Rather than probe endpoints, enumerate the fetchers a page actually calls and probe those:

```bash
for f in $(grep -oE "^export async function fetch[A-Za-z0-9_]+" lib/api.ts | awk '{print $4}'); do
  n=$(grep -rl "\b$f\b" app components hooks | wc -l)
  [ "$n" != "0" ] && echo "$n $f"
done | sort -rn
```

46 fetchers with at least one caller, ranked by how many surfaces reach them. That list is the
candidate pool. Everything below came out of it.

---

## 2. The defect

Three reads in a row on each candidate, plus the `/health` control on the same connection path.
LAT-P124's rule reads the verdict straight off the table: **a second read as slow as the first is a
CACHE defect; a first read much slower than the second is a WARMER defect.**

| endpoint | r1 | r2 | r3 | server split | verdict |
|---|---|---|---|---|---|
| **`/api/futures/86832`** | **5.97 s** | **3.76 s** | **3.73 s** | `db=3376-5621 q=5` | **CACHE — no cache of any kind** |
| **`/api/futures/1`** | **3.21 s** | **2.39 s** | **2.72 s** | `db=2369-2861 q=5` | **CACHE** |
| `/api/futures/55674287` | 0.28 s | 0.45 s | 0.27 s | `db=3-44 q=3` | fine |
| `/api/events/{id}/related-futures` | **19.85 s** | 0.42 s | 0.42 s | `db=19275 → q=0` | WARMER (cache exists, cold) |
| `/api/futures/browse` | 0.79 s | 0.86 s | 0.76 s | `db=408-514 q=3` | CACHE — **but claimed, see §6** |
| `/api/leagues/americanfootball_nfl` | 0.57 s | 0.57 s | 0.58 s | `db=0.0 q=0` | already cached; 187 KB of transfer |
| `/api/politics` · `/api/economics` · `/api/entertainment` | — | — | — | `db=0.0 q=0` | already cached by earlier cycles |

86832 is **"NFL Super Bowl Winner"** and 1 is **"MLB World Series Winner"** — both were on page one
of `/api/feed?limit=10` at the time of measurement. This is not a corner of the product.

### Why the third row is fast, and the first two are not

```sql
SELECT o.market_id, count(DISTINCT o.id) AS n_outcomes, count(s.id) AS n_snapshots,
       count(DISTINCT s.bookmaker) AS n_books
FROM futures_outcomes o LEFT JOIN futures_odds_snapshots s ON s.outcome_id = o.id
WHERE o.market_id IN (1, 86832, 55674287) GROUP BY o.market_id
```

| market | outcomes | snapshot rows | books |
|---|---|---|---|
| 86832 NFL Super Bowl Winner | 32 | **189,312** | 8 |
| 1 MLB World Series Winner | 30 | **131,807** | 5 |
| 55674287 Will Stripe acquire PayPal | 1 | 5 | 1 |

`get_futures_market` ran **two full scans of that row set on every request**:

```python
bookmakers_result = await db.execute(          # scan 1
    select(FuturesOddsSnapshot.bookmaker)
    .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
    .distinct().order_by(FuturesOddsSnapshot.bookmaker)
)
bookmakers = [row[0] for row in bookmakers_result.all()]
if len(bookmakers) > 1:
    source_breakdown = await _get_source_breakdown(db, outcome_ids)   # scan 2
```

Scan 2 is a `row_number() OVER (PARTITION BY outcome_id, bookmaker ORDER BY captured_at DESC)` with
**no time bound at all**, kept where `rn = 1`. For 86832 that sorts 189,312 rows to keep 256 of them
— 32 outcomes × 8 books — and then throws away 99.86 % of the work it just did. Scan 1 sorts the
same 189,312 rows to return eight strings.

`q=5` versus `q=3` on the fast market is the two scans, visible in the timing header. `db` is
94-98 % of `wall` on every slow read: this is entirely database time, not serialization, not
transport.

**The size dependence is the whole shape of the defect.** The endpoint is fine for small binary
markets and catastrophic for exactly the multi-outcome championship fields that Discover promotes
hardest. A census that sampled endpoints uniformly would have read this as a 300 ms endpoint.

---

## 3. Half one: the second scan was free all along

`bookmaker` is `NOT NULL` in production (`information_schema`, checked, not assumed). Therefore:

> a bookmaker appears in scan 1's `DISTINCT` **iff** it has at least one snapshot row **iff** it has
> an `rn = 1` row for at least one outcome **iff** it appears in scan 2's breakdown.

The two answers are the same set by construction, and `_get_source_breakdown` already sorts by
source, which is the ordering `ORDER BY bookmaker` produced. So scan 1 is deleted and `bookmakers`
is derived:

```python
source_breakdown = await _get_source_breakdown(db, outcome_ids)
bookmakers = [s["source"] for s in source_breakdown]
```

⚠️ **Two consequences that had to be handled rather than noticed later.**

1. The breakdown now runs for **single-bookmaker** markets, where it previously did not run at all.
   That costs exactly the scan it replaced — one either way — so it is free, not a regression.
2. The `> 1 book` condition therefore has to move. It used to gate whether the breakdown was
   **computed**; it now gates whether it is **attached**:
   `if len(bookmakers) > 1 and source_breakdown:`. Miss this and every single-book market grows a
   `source_breakdown` field it never had. Mutant **M-GATE** exists for precisely this.

The existing contract test `test_mocked_market_detail_contract` enumerated the queries as a
`side_effect` list of three; it is now two, with the `body["bookmakers"] == ["Kalshi", "Polymarket"]`
assertion left untouched — **that unchanged assertion is what proves the derivation agrees with the
query it replaced.**

---

## 4. Half two: cache the provenance, never the price

The P126 lesson, in a different key. **What makes a TTL safe is not the number — it is what goes in
the cache.**

- **Not cached:** the market row and its outcomes. Read fresh on every request, formatted by
  `_format_market_detail` from those rows. The hero probability, the outcome ladder, the 24 h
  movement — **this cache cannot serve any of them stale, because none of them was ever in it.**
- **Cached, 300 s:** `{bookmakers, source_breakdown}` — which books contributed and their latest
  price per outcome. This is the entire cost of the endpoint.

### The honesty argument, which is the part worth reusing

`source_breakdown` is a **deliberate source-comparison surface** — the one kind of surface the
standing "the blend is the product" ruling permits to show divergence. Caching a comparison surface
sounds like it should be forbidden: a five-minute-old per-book price sitting next to a live blend
reads as a disagreement that is not real.

It is safe here for a specific, checkable reason: **every row carries its own `captured_at` and its
own `stale` flag, both computed from the snapshot's own timestamp.** A cached row can be up to the
TTL old, but it **cannot misreport how old it is** — freshness is a *field in the payload*, not a
property of the cache. Mutants **M-STALE**, **M-CAPTURED** and **M-CUTOFF** all attack that one
property, and all three die.

### Why 300 s, and why that is NOT #901's rule

#901's rule — *a TTL must outlive the cadence that refills it* — is about a **warmed** key going cold
in the gap between warms. **Nothing warms this key.** There is no warmer, no new beat entry, no
change to the beat schedule. This is a pure on-demand cache, so the only thing the TTL buys is a
staleness budget, and a *short* one is the safe direction.

The data underneath moves on the cadence of `poll-futures-every-4h` and
`refresh-stale-futures-prices-hourly` — **1 to 4 hours**. 300 s is 12-48× faster than the thing it
caches. Mutant **M-TTL** (300 → 14400) dies.

A future sweep will find a `MARKET_SOURCES_TTL_S` and a `GOLF_SCHEDULE_TTL_S` in the same codebase
with TTLs an order of magnitude apart and both correct. **The question to ask a TTL is not "is it
long enough" — it is "is anything warming this, and what is the write cadence underneath".**

### #1587's class, in the one place it applies here

`_get_source_breakdown` keys `outcomes` by `outcome_id` — an **int** — and `json.dumps` stringifies
every dict key. FastAPI stringifies int keys as well, so a cache hit and a cache miss would have
shipped **byte-identical HTTP** and no route-level test could ever have caught the difference. The
cache would nonetheless have been storing something that is not what it serves, and the next
in-process reader — a warmer, a diff harness, an `assert hit == miss` — would have found a
divergence with no visible origin. `_restore_source_breakdown` puts the ints back; the guard compares
**objects**, not JSON. Mutant **M-INT** dies only because of that assertion.

Redis is best-effort in both directions: an unreachable client, a failing `get`, a failing `set` and
a corrupt entry all degrade to computing the answer. Mutants **M-REDIS**, **M-SETRAISE** die.

---

## 5. The battery, and the two survivors that were the fixture's fault

**17/17 killed, exit 0**, denominator printed first, baseline green, no NOT-APPLIED, no double
anchor. Harness: `backend/scripts/evals/futures_detail_sources_cache_mutations.py`.

🔴 **THE FIRST RUN WAS 14/16 WITH TWO SURVIVORS, AND THE SUITE WAS RIGHT — THE FIXTURE WAS WRONG.**
Every fixture row carried **one identical fresh timestamp, one row per bookmaker**. That made two
properties simultaneously untestable:

- with nothing old, `stale is False` holds whether the flag is **computed or hard-coded** → M-STALE
  survived;
- with one row per bookmaker, the "a newer row replaces the kept one" branch in
  `_get_source_breakdown` **never executes** → the captured_at mutant was unreachable.

The fixture now spans three ages and gives two bookmakers two rows each: kalshi's arrive
oldest-first (exercises the overwrite branch), draftkings' newest-first (exercises the keep-first
branch), polymarket has a single 30-day-old row (the only `stale = True`).

⚠️ **AND ONE MUTANT TURNED OUT TO BE GENUINELY EQUIVALENT — SHOWN, NOT DELETED.** The first M-CAPTURED
nulled `captured_at` in the dict **initialiser**. No fixture can kill it: the `existing is None` arm
of the overwrite branch immediately below repairs the value on the next line. It was replaced by a
mutation of the **overwrite branch itself**, which is observable, plus M-CUTOFF attacking the same
honesty property from the other side. The harness docstring records the equivalence. **A mutant that
cannot be killed is not a hole in the suite — but it has to be shown to be equivalent, not quietly
dropped.**

⚠️ **NO CLOCK LITERALS.** `_get_source_breakdown` compares against `now() - SOURCE_STALENESS_DAYS`, a
real clock, so a literal fixture date would be fresh today and stale in a fortnight and the `stale`
assertions would flip on their own (gotcha #44). Every fixture timestamp is an offset from a single
`_ANCHOR` taken **once at import** — once, so that a fixture built in a test and one built in the
code under test are the same instant to the microsecond; offsets, so nothing rots. `grep -c
"datetime(2026"` → **0**.

---

## 6. Parked, with the measurement attached so the next cycle spends nothing re-deriving

- **P127-1 — `/api/futures/browse`, `db=408-514 ms`, three slow reads, no cache. BLOCKED, not free.**
  `program/latency-109` (LAT-P123, unmerged, READY) rewrites `browse_futures`'s query to add a
  `func.count().over()` window for the category-count consistency fix, and `program/latency-111`
  (which **must not merge**) touches it too. Worse than a textual collision: -109's new `total` is
  rendered beside `/categories`' counts, and caching one of two integers that must agree is the
  defect -111's own comment warns about. **Take this the cycle after -109 lands, not before.**
- **P127-2 — `/api/events/{id}/related-futures` is a WARMER defect: 19.85 s cold, 0.42 s warm,
  `q=23 → q=0`.** The cache exists and works; the first visitor after each expiry waits nineteen
  seconds. Different fix from this one (a warmer, or a shorter build), and it wants its own cycle.
- **P127-3 — an index on `futures_odds_snapshots (outcome_id, bookmaker, captured_at DESC)`** would
  fix the 3.4 s **cold** miss this cycle only papers over. **Needs Alex**: gotcha #31 forbids
  `CREATE INDEX CONCURRENTLY` in Alembic (Heroku's ~5 min release timeout), the table has ≥189 K rows
  for a single market, and `psql`/TCP 5432 egress is blocked from this sandbox. → `YOUR-TURN.md`.
- **P127-4 — `/api/leagues/{sport_key}` ships 187 KB** (`db=0.0`, already cached, `app=45 ms`). Not a
  latency defect at the server; a payload question for a UX cycle.
- **P127-5 — two dead exports in `frontend/lib/api.ts`** (`fetchMarketMoves`, `fetchEIRankings`) and
  the live backend routes behind them. Deleting them is not a latency ship; it is what stops the
  next census re-nominating them. Filed as cleanup.
- Inherited and still parked: **P126-1** · **P125-A** (now also a keep-both hunk, see §7) · **P125-1**
  · **P125-2** · **P124-1**…**P124-5** · **P122-5** (option b/c, **THIRTEENTH** consecutive cycle —
  already escalated to `YOUR-TURN.md`).

---

## 7. Collision surface

`merge-tree --write-tree` against every branch that could meet this one:

| vs | exit | note |
|---|---|---|
| `origin/master` | **0** (tree `69920e4a`) | |
| `program/latency-109` | **0** | despite both touching `futures.py` — different functions, 1400 lines apart |
| `program/latency-110` | **0** | |
| `program/latency-112` | **0** | LAT-P126 |
| `program/calibration-118` | **0** | |
| `program/latency-108` | 1 | **`scan_mutation_residue.py` only — `futures.py` AUTO-MERGES.** Both add one `SHAPES` entry at the same alphabetical anchor (`futures_categories_census_mutations` sorts before `futures_detail_sources_cache_mutations`). **KEEP BOTH**, -108's first. This is the hunk that file's own comment predicts. |
| `program/latency-111` | 1 | same `SHAPES` hunk. **This branch must not merge** (LAT-P125). |
| `program/ux-122` | 1 | `frontend/components/FeedCard.tsx`. **Not this branch's** — `ux-122` is already exit 1 against `origin/master` alone, and LAT-P127 touches **zero** frontend files. |

---

## 8. Gates

| gate | result |
|---|---|
| new suite | **22 passed, exit 0** · 0 clock literals |
| new suite + the contract test it changed | **28 passed, exit 0** |
| mutation battery | **17/17 killed, exit 0**, 0 survived, 0 harness failures |
| residue scan **on a commit** | **CLEAN exit 0** — 233 needles, 840 broad checks; same two pre-existing `typeahead_warmer` drifts as master |
| ruff, changed paths | branch **2** vs master's measured **2** on the same paths → **net 0** (both pre-existing) |
| full backend suite | see `.claude/handoff/REPORT-LAT-P127.md` |
| frontend build (ESLint gate) / typecheck (TS gate) | see report — **zero frontend files changed** |
| `merge-tree` | §7 |
