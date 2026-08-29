# LAT-P114 — the page that never worked

**Ship:** the Categories page stops saying "Failed to load categories" and shows real
per-sport counts.
**Pillar:** DISCOVER (the category index is how a person browses what exists), riding
priority #1, reliability — "the app does what it's supposed to do".
**Issue:** #2267. **Branch:** `program/latency-99`, cut from **current master `b8ee7e14`**.

---

## the finding

`/api/feed/tag-counts` returns Starlette's plain-text `500`. Measured on the deployed slug
`f0b512b8` at 2026-08-29:

```
HTTP 500 in 0.548739s
Internal Server Error
```

`frontend/app/categories/page.tsx:26` fetches it through `fetchTagCounts`
(`frontend/lib/api.ts:1144`) and renders `ErrorState("Failed to load categories")` when it
fails. So `/categories` has been a dead page.

**Not "since a regression" — since the beginning.** The route was written in `c536d738`
(2026-03-01, "Event Taxonomy Phase 2: filter chips, category pages, analytics dashboard").
The column it collides with was already on the model at that commit. Verified by reading
`models.py` at `c536d738`: `category` on line 14 of the `FuturesMarket` class, one line
above `llm_sport_category`. **The page has never worked, on any deploy, for any user.**

## the cause

```sql
SELECT
    COALESCE(llm_sport_category, 'other') AS category,
    COUNT(*) AS cnt
FROM futures_markets
WHERE status = 'open' AND event_id IS NULL
  AND (resolution_date IS NULL OR resolution_date >= :now)
GROUP BY category
```

`GROUP BY category` reads as though it names the alias on the line above. It does not.
**PostgreSQL resolves a bare `GROUP BY` identifier against the INPUT columns first, and only
falls back to an output alias when no input column matches.** `futures_markets` has a real
`category` column, so the grouping key is `futures_markets.category`, and the selected
`COALESCE(...)` is left ungrouped:

```
GroupingError: column "futures_markets.llm_sport_category" must appear in the
GROUP BY clause or be used in an aggregate function
```

Sentry issue `7512011775`, culprit `/api/feed/tag-counts`, last seen `2026-08-29T02:51:21Z`,
with the failing statement and its bind parameter attached.

Reproduced independently through `/api/admin/db-query`: the statement verbatim returns
`{"error":"query_failed","reason":"invalid_statement"}`; the same statement with
`GROUP BY COALESCE(llm_sport_category, 'other')` returns 40+ rows in 1,120 ms.

## 🔴 the prior diagnosis was careful, disproved the right thing, and still missed it

LAT-P110 parked this as **P110-2** and did real work on it: it named the consumer the
earlier park (P108-4, "undiagnosed") had not, and it **disproved the obvious diagnosis** —
both statements are fast in isolation (566 ms and 120 ms), so it is not the statement
timeout the shape suggests. It even read the response body correctly and concluded "an
unhandled exception escaping the handler rather than a handled failure". All of that is
right.

What it did not do was **run the futures statement verbatim**. A paraphrase of it succeeds —
that is the whole trap, and it is why "the `futures_markets` count is 566 ms" appears in the
park as evidence of health. The statement that 500s and the statement that was timed are not
the same statement.

The park closed with "**The read:** the traceback, from Sentry or `heroku logs`. Not
attempted." That read took one API call and named the column outright.

**The clause worth keeping:** when a route 500s, the traceback is not one hypothesis among
several — it is the measurement, and a timing experiment is not a substitute for it. A
paraphrase that succeeds is evidence about the paraphrase.

## the fix

Both statements now `GROUP BY 1`. An ordinal is a positional reference; no column name can
capture it, so the fix does not depend on the schema staying as it is today.

The **events** statement was not failing — neither `events` nor `sports` has a `category`
column, checked in `information_schema` — but it is the identical shape one migration away
from the identical silent breakage. It groups by ordinal too, and the change was proven
behaviour-neutral before it was made: both forms run against production and return
**byte-identical result sets** (12 categories: soccer 255, other 124, baseball 79, football
36, tennis 35, mma 28, hockey 17, rugby 8, aussierules 7, cricket 6, boxing 5, basketball 4).

**What the page will show.** Reconstructing the handler's merged payload from production
data: **47 categories**, e.g. `table_tennis` 14,408 futures, `soccer` 262 events / 8,495
futures, `politics` 6,609 futures, `football` 36 / 3,018, `baseball` 79 / 1,364.

## the guards, and why there are two

**The oracle — `tests/integration/test_tag_counts_real_postgres.py`.** ~19,000 tests were
green for six months, and they had to be: the statement is valid SQL, it names only real
identifiers, and **the thing that rejects it is the server's name-resolution rule**. No mock
session has one. No recording double has one. Reading the line does not reveal it either,
because the broken version looks exactly like the correct one. So the gate needs a real
PostgreSQL, which the `search-recall` CI job provides.

Two design choices matter:

* It **drives the handler** rather than quoting it. A recording session captures what
  `get_tag_counts` actually issues, and those exact strings are executed. A copied statement
  would become a self-oracle the moment the route changed — it would go on proving that a
  string in a test file is valid SQL while the shipped route drifted away from it.
* It is **two-armed**. It also executes the pre-fix statement and REQUIRES it to fail. Without
  that, a green result is equally consistent with PostgreSQL having stopped caring about the
  ambiguity, and the file would be decorative.
* A third test asserts **two statements were captured**, because a gate grading an empty list
  passes on anything (gotcha #53: "it returned" is not "it worked").

**The net — `tests/test_sql_group_by_alias_collision.py`.** Static, no database, runs in the
ordinary suite, covers every `text()` statement in `app/`. The oracle covers one route
perfectly; this covers the class.

Its predicate needs all three of: (1) a bare-identifier `GROUP BY`, (2) that identifier
introduced as an output alias, (3) that identifier also a real column at the **same select
level**. Dropping (2) flags the common and correct `SELECT source, COUNT(*) ... GROUP BY
source`. Dropping (3) flags every aliased grouping key in the repo.

🔴 **Dropping the same-level requirement is not hypothetical — the first pass did it and
reported three false positives**, all CTEs in `app/tasks/precompute_backfill_progress.py` and
`app/routes/admin_data_quality.py`, all correct. A second version collapsed sub-selects but
was defeated by non-select parens nested inside a CTE body (`to_char(...)`), which blocked
the enclosing sub-select from ever collapsing. Both blind spots are now mutants (M8, M9).

Repo-wide the shipped scan finds **exactly one hazard: this one**. It examines **393 files
and 487 `text()` statements**, and asserts that denominator — a clean sweep over nothing
prints the same empty list as a clean sweep.

## RED-proven 10 ways

`scripts/evals/tag_counts_group_by_mutations.py`. Five mutants reintroduce the defect (the
original verbatim; inside a multi-column list; a different alias against a different real
column; the events statement once its table gains `category`; and the reporting layer, not
just the helper). Five attack the guard: a blanked column map, an alias that no longer
collides, removed CTE scoping, the collapse helper's nested-paren blind spot, and the
ordinal fix being flagged as a false positive.

**The control runs first and is printed.** A kill count without a passing control is not a
measurement — an oracle that fails for every input reports 100% kills while completely blind.

**The harness writes nothing.** No tracked file, no temp file. Every mutant is a string held
in memory, including the one that drives the repo-wide reporting layer — which needed
`scan_repository` split into `iter_sources` + `scan_sources` to be possible. It therefore has
no backup to restore and can leave no residue even under SIGKILL, which is the design
`_mutation_guard.py` explicitly asks new harnesses to prefer.

🔴 **The first version did not clear that bar and the gate caught it.**
`tests/test_mutation_guard.py::test_every_on_disk_harness_is_guarded` failed, because the
harness copied `feed.py` into a `tempfile.TemporaryDirectory` and called `write_text` on the
copy. The gate keys on the verb, not the destination, so it could not tell a temp file from a
tracked one. **The fix was to remove the writes, not to weaken the gate** — a gate loosened
to accommodate the first thing that trips it stops being a gate.

## a registry entry that could have been silent

The harness is a `*_mutations.py`, so `scan_mutation_residue.py` refuses to run until it is
registered. It has no needle/replacement pairs to declare, and an **empty `SHAPES` list would
have harvested zero pairs and printed nothing** — indistinguishable from the harness having
been forgotten, which is the exact silent-narrowing failure that scanner exists to refuse.

So it gets a named `DISK_FREE` entry that Pass A **counts and prints**, and the claim is
**verified** against a `MUTATES_WORKING_TREE = False` constant declared in the harness
itself. A name in a list can drift away from a harness that later grows a write; a constant
in the harness is edited by the person doing the growing.

## gates

* Full backend suite: see the READY token for the run, exit code read by value.
* Collect count: master **21,087**, branch **21,099** — **+12 exactly** (9 static-guard tests
  + 3 real-Postgres tests), predicted before the run and measured on **both** sides, master's
  in a throwaway worktree at `b8ee7e14`.
* `ruff` on `feed.py`: finding set **byte-identical** to master's own copy (14 findings,
  diffed rather than counted). New files clean. `black` clean on all three new files.
* Residue scan: **exit 0**, clean. (Two pre-existing `typeahead_warmer_mutations` DRIFT lines
  are on master and are not this branch's.)
* Merge: `-99` is **unordered against all four** open latency branches — eight pairwise
  `merge-tree` runs, exit 0, identical trees in both orders. A real five-way merge was
  **performed**: `-95`/`-96`/`-97` clean, `-98` hit its own documented conflict with `-97`
  (resolved by keeping both entries), then `-99` merged **clean** — including into the same
  `SHAPES` file the other two collide over. The merged scanner was **run** (148 needles, 2,280
  broad checks, exit 0) and the merged tree's guards **run** (27 passed, battery 10/10).
  ⚠️ A first attempt at the pairwise table exited **1 on all eight pairs** with "not something
  we can merge" — zsh not word-splitting an unquoted variable in `set --`. That is a story
  about the harness, not a verdict (gotcha #124), and it is the **second** consecutive cycle
  in this lane to hit that exact shape.

## what this ship is NOT

**It is not a cold-path latency win**, and the needle cannot see it. The conveyor asks for the
next cold-path win; the queue head's named item (`P113-1`) was refused for a different reason
(below), and the top independent item on the board was a page that has never rendered. A 500
becoming a 200 outranks a millisecond, and it is priority #1 by the product's own ordering —
but the needle line for this cycle measures something this change does not touch, and saying
so is the point.

## the head item, and why it was not taken

The queue head named **P113-1** — the `EXISTS` short-circuit gated on `user is None`, taking a
brand-new install from 4 personalization round trips to 2. It is a good item and it is still
the right next latency ship.

It was **not taken**, because it is a direct successor of LAT-P113's change to
`_load_personalization_context`, which is unmerged on `program/latency-98`. The conveyor's
standing rule is explicit: *"branch from CURRENT MASTER, never stack on unmerged latency-8x
branches."* On master that function still issues seven round trips, so implementing P113-1
there would mean re-doing LAT-P113's work inside it — a second branch claiming the same ship,
guaranteed to conflict with `-98`, and deepening a stack that is already four deep.

**P113-1 comes back the moment `-98` merges.** It is not parked and not dropped; it is
blocked on an integration, and the conveyor is refilled naming it first.
