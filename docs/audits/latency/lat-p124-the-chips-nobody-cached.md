# LAT-P124 — the chips nobody cached, and the sort nobody could reach

**Cycle 96 · branch `program/latency-110` · base `origin/master` `d9b76e9b` · issues #2285 (ship),
#2286 (finding)**

**Pillar: DISCOVER. Ships: the `/search` zero-state suggestion chips stop making every visitor
wait ten seconds.**

---

## 1. What a person waits for

`/search` renders `SearchPage`, and its first act on mount is `fetchSearchSuggestions()` →
`GET /api/events/search-suggestions` (`frontend/app/search/page.tsx:313`). Until that answers, the
page renders **"Loading suggestions..."** (`page.tsx:345-347`). The chips are the zero-state — the
thing a person looks at while deciding what to type.

Measured from the sandbox against a measured `/api/health` transport floor of **0.32 s**, three
consecutive reads two seconds apart, production slug `d9b76e9b`:

```
/api/events/search-suggestions   wall=12.218s   http=200
/api/events/search-suggestions   wall=14.536s   http=200
/api/events/search-suggestions   wall= 7.465s   http=200
```

🔴 **The second read is as slow as the first, and so is the third.** The route's last statement is a
`setex` with a 60 s TTL. A 60 s cache that worked would have made reads two and three free. No cache
at all is the only shape that fits — and that turned out to be exactly the shape.

## 2. The first defect: a cache that never wrote, and never read

```python
    _response = {"suggestions": suggestions[:8]}
    try:
        _rc = get_redis_client()
        _rc.setex(_cache_key, 60, _json.dumps(_response, default=str))
    except Exception:
        pass
    return _response
```

**Neither `_cache_key` nor `_json` nor `get_redis_client` was bound anywhere in that function.** The
block is a copy of `team_progression`'s WRITE half without its HEAD half — the head is where the
import, the key and the READ live — and the bare `except Exception: pass` turned the resulting
`NameError` into silence.

A reviewer cannot see this by reading. The block is **byte-identical** to a working one 3,800 lines
away in the same file, and that identity is precisely why it looked right.

🔴 **`ruff` on master reports it, and has been reporting it the whole time.** Measured in a throwaway
worktree at `d9b76e9b`:

```
app/routes/events.py:5855:15: F821 Undefined name `get_redis_client`
app/routes/events.py:5856:19: F821 Undefined name `_cache_key`
app/routes/events.py:5856:35: F821 Undefined name `_json`
```

There is no Python lint gate in CI, so nobody read it. The branch's F821 count on that file is
**0**, and the branch/master ruff totals on the two shared changed paths are **41 vs 44 — a delta of
exactly these three**.

### The TTL is a constraint, not a dial

`label` is a countdown **baked at build time**: `"Tips off in 12 min"`, `"Starts in 2h"`. A mirror
older than a minute prints a minute count that is wrong. So the 60 s the original (dead) write chose
is **kept, not widened** — widening it would buy latency with a formatting lie, which is LAT-P122's
and LAT-P123's trap on the surface next door. Pinned by
`test_the_ttl_is_sixty_seconds_and_that_is_a_constraint`, whose failure message says what has to
change first if anyone ever wants a longer one.

The key is **shared and unparameterised**: the endpoint takes no argument and reads no principal, so
one slot serves the fleet. A per-process key is mutant M14.

## 3. The second defect: 99.5% of the request is a sort for five rows that cannot reach the page

`EXPLAIN (ANALYZE, BUFFERS)` on each statement the route emits, production, slug `d9b76e9b`:

| § | statement | shared blocks | exec | rows |
|---|---|---:|---:|---:|
| 1 | live events | 94 | 5.8 ms | 46 |
| 2 | starting soon | 272 | 7.2 ms | 2 |
| **3** | **futures movers** | **146,437** | **13,099 ms** | **5** |
| 4 | recent upsets | 346 | 2.3 ms | 20 |
| 5 | championship markets | — | never runs (§5 below) | — |

Section 3's plan:

```
Limit                                             1,821 ms
  Nested Loop
    Gather Merge
      Sort   Key: abs(probability_change_24h) DESC
        Sort Method: quicksort 6,571 kB / worker: EXTERNAL MERGE 4,352 kB to DISK
        parallel Seq Scan on futures_outcomes
          Filter: probability_change_24h IS NOT NULL AND abs(...) > 0.02
          Rows Removed by Filter: 1,808,454      rows kept: 116,462
146,437 shared blocks (13,645 hit + 132,807 read) ≈ 1.14 GB
```

No index can serve it. The only index on `futures_outcomes` that mentions the column,
`ix_fo_market_movement`, is `(market_id, probability_change_24h) WHERE probability_change_24h IS NOT
NULL` — its leading column is `market_id`, so it cannot answer a global `ORDER BY`.

🔴 **Read the blocks, not the milliseconds.** Two reads of the identical statement reported
**1,833 ms** and **13,099 ms** as the buffer cache warmed. The block count moved by **15**
(146,452 → 146,437). Every claim in this document that compares cost compares blocks.

### And on the read that motivated this, those 1.14 GB bought nothing

The live payload was eight chips, **all of them "Starts in Nh"** — section 2. Sections 3, 4 and 5 ran
against a window that was already full, so their loops broke on the first iteration and their rows
were read, sorted, spilled to disk, and discarded.

## 4. The fix, and why it is answer-identical rather than answer-similar

Each section's *only* effect on the response is an `_add(...)` inside a `for` whose **first
statement** is `if len(suggestions) >= 8: break`. When that already holds on entry, the loop body
never executes: the section is a pure no-op on the response and the statement is pure cost. Skipping
the statement in exactly that case is therefore not an approximation.

The soundness of that argument depends entirely on the skip and the `break` testing **the same
number**. They were three separate `8` literals that agreed by coincidence of authorship. They are
now one `_MAX_SUGGESTIONS`, and three AST guards keep it that way:
no bare `8` comparison survives in the function, `_window_full` reads the constant, and the predicate
is called at exactly four sites.

**Section 1 is deliberately not guarded.** It runs against an empty `suggestions`, so a guard there
is a branch that can never be taken — and an untakeable branch is worse than no branch, because it
reads as coverage.

### The permanent form, requested and NOT taken

```sql
CREATE INDEX ON futures_outcomes (abs(probability_change_24h) DESC)
  WHERE probability_change_24h IS NOT NULL;
```

That would make the *unskippable* case cheap too. It is DDL, the migration slot is Integrator-owned
(ruling 080), and gotcha #31 applies. **Parked as P124-1.**

🔴 **Said plainly: the skip only helps when sections 1 and 2 fill the window, and how often that
happens is a function of the clock.** Section 2's limit is 10, so it fills all eight slots whenever
eight tier-1/2 games start within three hours — common in the evening, false at 4 a.m. **The cache
is the load-bearing half**, and what it buys the unlucky reader is that they are the only one per
minute. Until the index lands, this degrades to slow once a minute, never to wrong.

## 5. Found while measuring: two of the five sections have NEVER run

| § | code | reality |
|---|---|---|
| **1** live close games | `OddsSnapshot.home_probability` | the column is `home_win_probability` |
| **5** championship markets | `FuturesMarket.outcome_count` | no such attribute, and no such name anywhere in `app/` |

Both raise `AttributeError` while their statement is still being **built** — before any round trip —
and each section's bare `except Exception: pass` swallows it. That is why every production read
returns nothing but "Starts in Nh" chips: **section 2 is the first section that works.**

Section 1 is worse than free: it executes `live_events_q` (94 blocks) and *then* dies building
`odds_q`, so it buys a round trip on every uncached request and throws the result away.

**Filed as #2286 and deliberately NOT repaired here.** Making a never-executing section start
executing changes what a user sees on `/search` — new chips appear — and adds a round trip this
queue has not measured. Deciding what a "tight game" or a "popular championship market" should be is
a product call, not a latency one. `TestSectionsThatHaveNeverRun` pins both, in the `hasattr`
direction and the behavioural direction, and its failure messages say who owes what when they go
red.

This also revises a note LAT-P107 left under #1605: the `row_number()` window in section 1, surveyed
and left as "a separate, smaller ship on a non-graded surface", is a window **nobody has ever paid
for**, because the statement that would run it has never been built.

## 6. The class guard

The instance was one function. The class is: *a cache write naming a variable its function never
binds, inside a bare `except`.* `TestNoCacheWriteReferencesAnUnboundName` parses
`app/routes/events.py` and fails any top-level function that READS `_cache_key`, `_json` or `_rc`
without BINDING it — by assignment or import — in its own body or at module level. It goes red on
the original code and green on this one.

## 7. Gates

| Gate | Result |
|---|---|
| new suite `test_route_search_suggestions_cold_p124.py` | **21 passed, exit 0** — every assertion on a query count, a cache interaction or a rendered value; **none reads a clock** (gotcha #44) |
| scoped (`test_route_search.py` + new suite + `test_events_odds_enrichment_shape.py`) | **193 passed, exit 0** |
| `tests/test_mutation_guard.py` | **9 passed, exit 0** |
| mutants | **14/14 killed, 0 survived, 0 harness failures, exit 0**; baseline green; denominator printed BEFORE the first verdict |
| residue scanner | **CLEAN exit 0 ON A COMMIT** — 230 needles, 668 broad checks over the 4 changed files. Master baseline measured **CLEAN exit 0** in a throwaway worktree, carrying the *same* two pre-existing `typeahead_warmer` needle drifts — so neither is this branch's |
| `ruff` | branch **41** on the two shared changed paths; master `d9b76e9b` measured **44** on the same paths → **−3, exactly the three F821s this ship fixes**. New files: **All checks passed** |
| collect delta | base `d9b76e9b` **21,690 MEASURED** in a throwaway worktree; branch **21,711** → **+21, exactly the new file** |
| merge-tree vs `origin/master` | **exit 0**, tree `e0ceaab4` |
| merge-tree vs `program/latency-108` / `-109` | **exit 0** both — this branch can merge before or after either |
| frontend / native | **not claimed** — no file of either kind is touched, and the response shape is byte-identical |
| full backend suite | see the READY token |

### The battery's first pass found two of its own defects

M9 and M10 were written against the cache-read block alone and each **matched twice** — the block is
byte-identical to `team_progression`'s, which is the whole reason the original defect was invisible.
The harness reported them **NOT APPLIED**, not skipped, so the two-match was seen rather than quietly
counted out of the denominator. Both anchors now carry the key line.

Pass B of the residue scanner then flagged **M12** as a loose mutant: its replacement is a single
line that appears verbatim in the harness, while its escaped needle did not. Rewritten as a literal
multi-line string, which puts both halves in the file — the same lesson
`cache_refresh_behind_mutations` recorded for its M5 and M8, one queue later.

### Why this harness mutates the file instead of `exec`-ing strings

`_mutation_guard.py` prefers the disk-free design and LAT-P123 took it. It is the wrong trade here.
The oracle for this change is a **query count taken through the real route** — with the real
`_add`/`_window_full` closure and the real bare `except` around every section. LAT-P123's own finding
was that a hand-written in-process fake diverged from the live shape and let a mutant survive. Using
the 21-test suite verbatim as the oracle removes that class of hole: the thing that grades the
mutants is the thing that grades the ship. The cost is a `SHAPES` entry and a `guarded_targets`
manifest, both of which exist for exactly this.

## 8. Ordering against the other open branches

- **vs `origin/master`**: merge-tree exit 0.
- **vs `program/ux-122`**: conflicts on `frontend/components/FeedCard.tsx` only. **CONTROL:**
  `merge-tree origin/master program/ux-122`, with this branch not involved at all, reproduces the
  **identical conflict on the identical blobs** (base `f84136a0`). Pre-existing ux-122 ↔ master. Both
  branches touch `routes/events.py` and it **auto-merges**: ux-122's hunks are at ~11,352 and
  ~11,395, this branch's at 5,623–5,990 — 5,400 lines apart.
- **vs `program/latency-108` and `-109`**: exit 0 both.

## 9. Parked

- **P124-1** — the expression index on `abs(probability_change_24h)`. DDL, ruling 080. It is what
  makes the *unskippable* case cheap; the skip and the cache only bound how often it is paid.
- **P124-2** — the section-1 `row_number()` window over `aggregate` snapshots, inherited from
  LAT-P107's #1605 survey. It is unreachable today (#2286) and becomes real the moment #2286 is
  fixed; whoever fixes #2286 owes it a plan, not a rediscovery.
- **P124-3** — `/api/futures/browse` uncategorised (P123-1, still 2.8–3.8 s / 39,002 blocks, still no
  identified caller — find the caller before optimising).
- **P124-4** — the negated `ILIKE`s on `futures_markets` (= P122-4 = P123-2). DDL, ruling 080.
- **P124-5** — `func.count` at eight more sites in `routes/futures.py` (P123-4). A census, so it
  belongs to the MEASUREMENT lane (ruling 134).
- **P122-5** — option b vs option c, **TENTH** consecutive cycle.

## 10. Re-derivation notes for the next cycle

🔴 **Everything on the board's head is shipped-and-unmerged, and only reading the tree shows it.**
This cycle checked the four newest `program:latency` items — **#2284, #2281, #2270, #2260, #2261** —
and every one of them was already fixed: #2284 on `program/latency-109`, #2281 on `-108`, and #2270,
#2260, #2261 **in master already**. Their issue bodies read as open work because they are written in
the present tense by the queue that fixed them. `git grep` the fix, do not read the title.

- The queue head is **STILL P118-1 and STILL SLOT-BLOCKED** — ruling 080 plus `-103`. Read
  `MIGRATION-SLOT-REQUEST-LATENCY-2026-08-29.md`; do not re-derive it.
- `program/latency-103` through `-107` have **merged**; `-106`, `-108`, `-109` and `-110` have not.
  `serve_stale_and_refresh` still lives only on `-108`, so P123-3 is still blocked.
- **Where the next cold path was found, so the next cycle can repeat it rather than re-invent it:**
  not from the board. From `frontend/lib/api.ts`, by taking each `apiFetch` a page issues on mount
  and timing it three times in a row against the health floor. A second read as slow as the first is
  a cache defect; a first read much slower than the second is a warmer defect. Both are user-visible
  by construction, because the caller is a page's `useEffect`.
