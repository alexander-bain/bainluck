# LAT-P123 — the same scan, run twice, and a mutation battery that was blind on its first pass

**Pillar: DISCOVER. Ships: tapping a category in the Search tab stops paying for the same table
scan twice** (#2284).

Branch `program/latency-109`, cut from **current master `d9b76e9b`** — not stacked on
`program/latency-108` (LAT-P122, unmerged), per the inbox directive.

---

## The measurement came first, and it corrected the number it inherited

LAT-P122 parked this as **P122-2** with a headline of *"`browse`'s `COUNT(*)`, 2,038 ms of a
2,424 ms request, endpoint p50 3,796.8 ms"*, blocked on `program/ux-122`. Both halves of that
needed re-deriving before any code was written, and both moved.

**The magnitude is parameter-dependent, and the parked note quoted only one parameterisation.**
Timed from the sandbox against a measured `/api/health` transport floor of **0.28 s**:

| call | pass 1 | pass 2 | pass 3 | `total` |
|---|---:|---:|---:|---:|
| `category=politics&limit=50` | 1.04 s | 1.36 s | 1.07 s | 6,611 |
| `category=economics&limit=50` | 0.75 s | 0.88 s | 0.65 s | 2,901 |
| `category=entertainment&limit=50` | 0.56 s | 0.65 s | 0.51 s | 1,927 |
| `limit=50`, **no category** | 2.83 s | 3.83 s | — | 21,432 |

So the 2,424 ms / p50 3,796.8 ms figure is the **uncategorised** call, and the categorised call —
the one `CategoryBrowser` actually issues, because `CategoryMarkets` always passes a `category` —
is three to seven times cheaper. Quoting the parked number for the tap-through would have been
quoting a different request.

## What the plans say, and it is the same scan twice

`EXPLAIN (ANALYZE, BUFFERS)` through `/api/admin/db-query`, production, slug `d9b76e9b`:

| call | statement | node shape | shared blocks | actual |
|---|---|---|---:|---:|
| `category=politics` | `COUNT` | Aggregate → Bitmap Heap Scan | 8,410 | 209.6 ms |
| | page | Limit → Sort → Bitmap Heap Scan | 8,410 | 222.6 ms |
| | **window** | Limit → Sort → **WindowAgg** → same scan | **8,410** | **138.3 ms** |
| no category | `COUNT` | Aggregate → Bitmap Heap Scan | 38,990 (~305 MB) | 1,270.5 ms |
| | page | Limit → Sort → Bitmap Heap Scan | 39,002 | 445.6 ms |
| | **window** | Limit → Sort → **WindowAgg** → same scan | **39,002** | **801.7 ms** |

Read the **blocks**, not the milliseconds. The timings move with buffer warmth run to run — the
politics scan alone reported 105.7 ms, 220.9 ms and 222.6 ms across three reads of the identical
statement. The block count does not move, and it is the thing this ship changes: **`2N` → `N`,
exactly, per request.**

The reason it is the same scan is one clause. `ORDER BY resolution_date ASC NULLS LAST` means
Postgres must read every matching row before it can take fifty; the `Sort` node above the scan
already has all 6,611 politics rows in hand. The `COUNT` then reads those same 6,611 rows again to
answer a question the first statement had already made answerable.

`count(*) OVER ()` is evaluated in a window step, which sits **above the scan and below the
LIMIT**. It rides work that was being paid for anyway: the WindowAgg node cost 4.2 ms over the bare
scan (105.7 → 109.9 ms on the politics read) and deleted a whole statement.

## 🔴 A cheaper count here could have shipped a formatting lie, and it would have graded as a win

The counts on this surface are **printed**. `CategoryBrowser.tsx:179` renders `({data.total})`
beside the category header, and line 229 renders `Load more ({data.total - allItems.length}
remaining)`. Every cheap approximation available — a sampled estimate, `reltuples`, a cached
per-category count, `limit + 1` with `total` dropped — makes one of those two strings wrong, on a
surface where the number is the content.

So the design constraint was fixed before the mechanism was chosen: **`total` must be the same
integer it is today.** `count(*) OVER ()` satisfies it by construction, because the window is
evaluated before `LIMIT`/`OFFSET` — it counts the population, not the page. This is a cost change
and not a precision change, and the distinction is the whole reason this mechanism and not a
cheaper one.

It is also LAT-P122's own trap on a different surface, one cycle later: that cycle age-bounded its
mirror at 5 × 300 s precisely because *"6,614" beside Politics* is a number a reader can reproduce
by tapping the tile. Same numbers, same obligation.

## The one case a single scan cannot answer

An `offset` past the end of the population returns no rows, so the window function never ran and
has nothing to report. Reporting `0` there would tell a reader who hand-typed an offset that a
6,611-market category is empty — a wrong printed number, which is the exact class the mechanism was
chosen to avoid. So that branch pays for the explicit `COUNT`.

It is off the hot path by construction: `has_more` is `(offset + limit) < total`, so the UI never
offers a "Load more" that would land past the end. An empty page at `offset == 0` needs no query at
all — an empty first page *is* an empty population, and paying for a `COUNT` to confirm it would
put the second scan back on the commonest cold path of all.

## 🔴 The mutation battery was blind on its first run, and that is what it caught

`scripts/evals/browse_single_scan_mutations.py` reported **10/13 on its first pass**. All three
findings were defects in the harness, not in the route — which is the outcome a battery is for, and
the one a kill count alone would have hidden.

**M10 — `list(...)` dropped, SURVIVED.** The oracle's fake returned a real Python list, so removing
`list(...)` from the route changed nothing observable. The hazard is real and lives one level down:
the repo's shared fixture (`tests/integration/conftest.py::_make_mock_result`) does **not** stub
`.unique()`, so `result.unique().all()` is an auto-`MagicMock` — truthy, and subscriptable into
more MagicMocks. Without `list(...)` the empty-population path takes the `if rows:` branch and
`int(rows[0][1])` returns **1**, because `MagicMock.__int__` defaults to 1. Not a 500. A silently
wrong printed count on an empty category. The repaired oracle reproduces the shared fixture's shape
rather than a convenient one.

**M13 — `ORDER BY` dropped, SURVIVED.** No oracle checked ordering, because ordering did not look
like a latency property. It is: without a deterministic order, Postgres may return a different row
order per statement, so "Load more" repeats some markets and skips others — while `total` stays
reassuringly exact and every timing improves. A latency harness that cannot see that is grading the
wrong half.

**M11 — anchor matched three times, NOT APPLIED.** `"outcome_count": len(real_outcomes),` occurs at
three places in `routes/futures.py`. The battery refused to mutate an arbitrary one and reported it
as a separate, fatal outcome rather than a skip, which is the only reason it was noticed at all: a
mutant that changed nothing would otherwise have been counted as a kill.

After the three repairs: **13/13 killed, 0 survived, 0 not applied, control green, exit 0**, with
the denominator printed before the first verdict.

## Ordering against `program/ux-122` — discharged by measurement, not by avoidance

LAT-P122 deliberately left this surface alone because `program/ux-122` also edits
`backend/app/routes/futures.py` inside `browse_futures`. That caution was right at the time and it
is now testable rather than assumed.

ux-122's hunk in that file is `@@ -696,26 +696,76 @@`, covering master lines 696–721. This change
lives at lines 749–800. Twenty-eight lines apart, well outside three-line merge context.

`git merge-tree --write-tree program/ux-122 program/latency-109` reports **`Auto-merging
backend/app/routes/futures.py`** with no conflict. It does surface a conflict in
`frontend/components/FeedCard.tsx` — and the control run,
`git merge-tree --write-tree origin/master program/ux-122` **without this branch involved at all**,
produces the identical conflict on the identical blobs. It is a pre-existing ux-122 ↔ master
conflict and this ship neither causes nor worsens it. This branch touches no frontend file.

## Gates

| Gate | Result |
|---|---|
| new suite `tests/integration/test_route_futures_browse_single_scan_p123.py` | **16 passed, exit 0** — every assertion on SQL shape, statement COUNT or a rendered value; none reads a clock (gotcha #44) |
| scoped (`browse` route + mutation guard) | **64 passed, exit 0** |
| `tests/test_mutation_guard.py` | **9 passed, exit 0** |
| mutants | **13/13 killed, exit 0**, control green, denominator printed BEFORE the first verdict |
| residue scanner | **CLEAN exit 0 ON A COMMIT** — 216 needles, 770 broad checks across the 5 changed files |
| `ruff` | branch **2** on the touched paths = master `d9b76e9b`'s own **2 measured on the same paths** → **+0** (both pre-existing `F401`s; no Python lint gate in CI) |
| collect delta | base `d9b76e9b` **21,690 MEASURED** in a throwaway worktree; branch **21,706** → **+16, exactly the new file** |
| merge-tree vs `origin/master` `d9b76e9b` | **exit 0**, tree `b9c13872`, 0 conflicts |
| merge-tree vs `program/ux-122` | `routes/futures.py` **auto-merged**; the one conflict is pre-existing and reproduced by the control without this branch |
| frontend / native | **not claimed** — no file of either kind is touched, and the response shape is byte-identical |
| full backend suite | see the READY token |

## Parked

- **P123-1** — the uncategorised `/api/futures/browse` call is **2.8–3.8 s** and still 39,002
  blocks after this ship. No frontend surface issues it (`CategoryMarkets` always passes a
  `category`, `/categories/[slug]` uses `fetchFeed`), yet production shows a real p50 for it.
  **Find the caller before optimising it further** — an endpoint p50 with no identified client is a
  fact about traffic, not about a person waiting.
- **P123-2** — the two negated `ILIKE`s are why the scan is 305 MB in the first place. DDL, ruling
  080, already parked as P122-4. Halving `2N` does not make `N` cheap.
- **P123-3** — `serve_stale_and_refresh`-style caching of this route. Deliberately NOT done here:
  the shared helper lives only on `program/latency-108`, and the directive forbids stacking on it.
  Re-derive once `-108` merges; the printed counts make it an age-bounded mirror, not a free one.
- **P123-4** — the same two-statement shape almost certainly recurs elsewhere in
  `routes/futures.py` (`func.count` appears at lines 254, 684, 750, 849, 972, 1153, 3754, 3771).
  A census belongs to the measurement lane, not to a build lane.
- **P122-5** — option b vs option c, now the **NINTH** consecutive cycle.

## Issues

**#2284 filed and left OPEN** — nothing has deployed, and closure needs measured production
evidence (`shared_blks_hit` per call in `pg_stat_statements`, halved).
