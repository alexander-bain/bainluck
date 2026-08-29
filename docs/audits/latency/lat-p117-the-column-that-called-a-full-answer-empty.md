# LAT-P117 — the column that called a full answer empty

**Cycle 89 · 2026-08-28 22:3x–23:5x PDT · identity `LAT-P117-20260829-w66302` · branch
`program/latency-102`, cut from CURRENT master `c47b25a5`**

Ran from Fable's runner directive (`runner-inbox/latency/022-coldpath-conveyor.md`), staged
under Alex's standing authorization. Lane lock claimed **exit 0**, prior owner explicitly
RELEASED — no takeover, no MALFORMED repair (the first cycle in seventeen that needed neither).

**Pillar: TRUTH. Ship: a search answered by futures stops being recorded as a search that found
nothing.**

**NEEDLE: latency 21 ms @ 2026-08-29T05:39:27Z** (7/7 served), `DIAG: latency-build REFUSED`
(2/7 cold, floor 4).

---

## The opening read, and why it pointed somewhere else

The queue head named **P116-4**: `?debug_timing=1` on `/api/events/search` still writes a
`search_query_logs` row where `/typeahead` suppresses it on the same flag. Inherited from
P115-2, re-confirmed by LAT-P116, and LAT-P116's own probes were sitting in that table.

The needle run that opened this cycle declared the contamination in its own words, as it is
built to:

```
/api/events/search        6 — one `search_query_logs` row each (#1916). Forced on: cold search is a graded surface.
/api/events/typeahead     6 — debug_timing, 0 votes into search:trending:24h.
```

Six more polluting rows, every published reading, unavoidably. That is a real defect and it is
worth fixing. **It is not, however, what the evidence turned out to be about**, and five
candidates had to be disproved before the thing that was actually wrong became visible.

---

## 🔴 FIVE DISPROOFS, AND THEY ARE THE FINDING

### (a) P116-4 as named would blind the instrument it was meant to clean

`/typeahead` suppresses its trending vote on `debug_evidence or debug_timing`, and the obvious
mirror is to have `/search` set `_suppress_search_log` on the same flag, then teach the harness
to pass it.

`debug_timing` on `/search` **already bypasses the response cache in both directions** — the
read is gated on `not debug_timing` (header goes to `bypass`, not `miss`) and the write on
`not degraded and not debug_timing`. So a harness that passed the flag would pin `search_cold`
to a forced full build **for ever**. Under ruling 127's option-c needle, `search_cold` is a
NEEDLE member and not merely a DIAG one, so the pool's worst path (389.5 ms, 18× the next)
would become permanently incapable of showing that a warmer had started reaching it. The fix
would have bought log hygiene with the ability to observe the thing this lane exists to ship.
This is the typeahead "reads ~2.2× low, NOT comparable to the voting-mode series" trap, in
reverse. **Re-parked P117-3 with the mechanism, not merely re-deferred.**

### (b) The polluter is not the harness, and the in-process guard cannot reach it

The census, production, 30-day window, 2026-08-29:

| rows | attested (`session_id` or `user_id`) | unattested | distinct queries |
|---:|---:|---:|---:|
| 4,257 | **13** | **4,244** | 237 |

**99.7 % machine.** And the polluter is not a warmer, which is why `#1866`'s
`_suppress_search_log` ContextVar never caught it: the **Flow Sentinel**
(`tasks/flow_sentinel.py`, nightly 07:10 UTC) submits its 33-query `GOLD_SET` +
`GOLD_SET_TOP1` **over HTTP via `httpx`**. A ContextVar set inside the API process cannot be
reached by a Celery worker making real HTTP requests.

The signature is **arithmetic, not correlation**. Hour 07 UTC is the single largest hour for
every term at the head, at *exactly* 30 rows per 30 days for a term in one gold set — one per
night — and *exactly* 60 for `masters winner`, which is the one term appearing in **both** gold
sets:

| term | rows/30d | rows at 07 UTC | in gold sets |
|---|---:|---:|---|
| `masters winner` | 112 | **60** | GOLD_SET Q23 + GOLD_SET_TOP1 |
| `stanley cup` | 108 | 30 | GOLD_SET Q09 |
| `world series` | 102 | 30 | GOLD_SET Q08 |
| `nba champion` | 99 | 30 | GOLD_SET Q05 |

**18 of the top 25 terms are literally gold-set entries.** The typeahead warmer's log arm holds
a **guaranteed half** of the warm budget (`_QUERY_LOG_SHARE = 0.5`), so twenty of forty slots
are elected by our own nightly checklist.

`typeahead_warmer` asserted, in the comment that justifies that guaranteed half, that
`search_query_logs` "records SUBMITTED intent. **Nothing in this system can pollute it.**"
Corrected in this commit.

### (c) …and `search_head_warmer` already knew — gotcha #128, exactly

The sibling warmer's docstring has carried the right answer for some time: *"ELECTING A HEAD
FROM THE WHOLE TABLE WOULD HAVE WARMED OUR OWN PROBE TRAFFIC. Every one of the top eight terms
… is a sentinel or probe term."* It elects through `_USER_HEAD_SQL`, an attestation filter.
`typeahead_warmer` reads the table whole. **One rule, two consumers, one repaired — and the
repaired copy hid the broken one**, which is the failure mode gotcha #128 names.

### (d) The attestation filter cannot simply be copied across — it would warm FEWER terms

The obvious remedy is to give the typeahead arm the filter its sibling already has. Measured:

- `search_head_warmer`'s attested head, run against production, returns **exactly one row**:
  `red sox` (2 sessions). Out of a 40-slot budget. *This is why LAT-P116 found `search_cold`
  "the only pool member no warmer reaches" — the warmer exists; its head-election starves it
  to one term.*
- Dropping `MIN_HEAD_SESSIONS` and filtering the typeahead arm on attestation alone yields
  **7 distinct queries** — and several (`orenburg`, `bridesmaid`, `pregnancy`) are other
  harnesses' probes carrying a session id.

`_blend_heads`' share is a **FLOOR, not a quota**, and the zset arm reads empty in production
(LAT-P115: `{"trending": []}`, `resolve_head` falling through on 40/40 slots). So the filter
would cut the log arm 20 → ~7 with nothing to take up the slack: **fewer terms warm than
today**, which is a regression on the exact metric the change would exist to move. The gold set
is, by accident, a defensible warm list — it was *chosen* to be representative user intents.
**Parked P117-2. Do not "fix" this without a demand signal to put in its place.**

### (e) 🔴 The one that would have shipped as a win

`search_query_logs` has a `result_count` column. "Stop warming the queries that come up empty"
is one predicate, it is principled, and it is what anyone reaches for next. Measured against
the top 40:

> **27 of the top 40 head terms have NEVER recorded a non-zero `result_count`.**

Shipped on that number it would have pruned two thirds of the warm head. Every one of those 27
answers fine:

| query | `total_results` | teams | concepts | futures | families |
|---|---:|---:|---:|---:|---:|
| `stanley cup` | 0 | 0 | 0 | **2** | 1 |
| `lebron james` | 0 | 0 | 0 | **10** | 2 |
| `trump approval` | 0 | 0 | 0 | **10** | 1 |
| `nba mvp` | 0 | 0 | 0 | **6** | 0 |

`pagination.total_results` counts the `results` array — **game events, one section of four**.
The Flow Sentinel independently grades `stanley cup` as FOUND (`GOLD_SET` Q09) while this column
called it empty 108 times, and nobody reconciled the two.

Those 27 are futures-answering queries, and the futures/outcome arm is **59.9 % of the
cold-search build** (LAT-P116). The cleanup would have evicted from the warm head precisely the
queries whose cold path costs the most, while looking like a tidy-up. **Gotcha #53 wearing a
number: an absent section and an empty answer must never read the same.** Structurally the same
shape as LAT-P116's `OFFSET 0` fence — shipped on the principled-looking figure, it makes things
worse.

**So disproof (e) is the ship.**

---

## THE SHIP

`_record_search_query` now records what the search actually put in front of the person, via
`_answered_result_count`. The definition is **taken from the product, not invented here**: it is
the condition the search page itself uses to decide whether to render the zero-state
(`frontend/app/search/page.tsx`: `!hasEvents && !hasFutures && !hasTeams && !hasEventConcepts`),
so the log and the screen cannot disagree. Events contribute their paginated
`total_results` (`results` is one 25-row page of it); teams, concepts and futures are unpaginated
and contribute their lengths.

`futures_families` is **excluded, and the exclusion is load-bearing** — a family composes markets
already present in `futures` (the page's `familyShownIds` filters them back out so nothing
double-renders), so counting both would inflate the very column this exists to make honest.

`top_result_id` is **deliberately not widened**. It carries no type discriminator, so writing a
`futures_markets` id into it would make the column ambiguous across two tables — a worse defect
than the null it replaces. **Parked P117-1** as a schema question rather than smuggled in behind
a count fix.

### It also sharpens an open p1

**#2239** (*"Search intermittently returns 0 results for a query that has 25"*, p1, OPEN) says of
this column: *"**This is the only place the flap is recorded**, and it is recorded by accident."*
That detector is "`result_count = 0` for a query that has results" — and it was competing with 27
chronic false positives. After this fix a 0 means the answer was empty. #2239's own census
("13 attested rows in 30 days") reproduces exactly, which independently corroborates the census
above. The flap itself is untouched and remains real: `patriots` is an events query, so its
25→0→0→0→25 is not this artifact.

---

## Gates

| gate | result |
|---|---|
| full suite | **PENDING — see the report; ONE run, exit code read BY VALUE** |
| smoke (`test_startup.py`) | **4 passed, EXIT 0** |
| targeted (`test_search_latency_contract.py`) | **102 passed, EXIT 0** (7 new) |
| mutants | **7/7 killed** |
| residue | **CLEAN, exit 0**, 155 needles, **408 broad checks** |
| ruff | finding set **byte-identical** to master's (44 = 44, **diffed, not counted**) |
| `migration_slot` | **none** — no DDL, no index, no schema change |
| `beat_schedule_change` | **FALSE** — no beat file touched, no Celery task added, no config var |
| scope | **backend only**, 4 files |

### 🔴 A gate lied, and it was a stale build artifact

The residue scanner's first run reported **`🔴 RESIDUE: 2 candidate mutant(s)`**, exit 1, in
`backend/scripts/evals/cache_refresh_behind_mutations.py` — **a file that does not exist in this
tree**, is not tracked by git on this branch, and whose name appears in no `.py` anywhere in the
repo. The only thing carrying it was an orphaned
`__pycache__/cache_refresh_behind_mutations.cpython-312.pyc`.

🔴 **And the source of that bytecode is the interesting part: it belongs to the SIBLING BRANCH.**
`cache_refresh_behind_mutations.py` is added by `program/latency-101` (LAT-P116, unmerged).
LAT-P116 ran the harness in this worktree, leaving compiled bytecode in `__pycache__`; this cycle
then cut `program/latency-102` from master, where that `.py` does not exist. **`__pycache__` is
untracked, so it survives `git checkout` between branches** — and the gate read a sibling branch's
build output as residue on mine. Removing the orphaned bytecode took the gate to CLEAN exit 0.

This is not a one-off. Every lane switches branches inside a long-lived worktree, and every
mutation harness compiles on first run, so any harness file introduced on an unmerged branch can
fail the residue gate for whatever branch is checked out next. **Parked P117-4** (the scanner
should distinguish "harness source missing" from "residue found") **and offered as a gotcha**.
⚠️ **For the Integrator:** when `-101` merges, that `.py` returns to the tree and this finding will
not reproduce — do not read its disappearance as the scanner having been fixed.

### 🔴 Pass B silently covered NOTHING until the work was committed

The same gate's Pass B is scoped `git diff --name-only origin/master...HEAD` — a **commit**
diff. With four modified files in the working tree and `HEAD == origin/master`, it reported
`102 literals x 0 files = 0 pairwise checks` and still printed **✅ CLEAN**. A green with zero
coverage, and the line that says so is one word different from a green with real coverage. Re-run
after committing: `408 pairwise checks`. **The residue gate must be run on a COMMIT, never on a
dirty tree** — parked P117-5, and worth a gotcha.

### Inherited, not mine

`typeahead_warmer_mutations:M4` and `:M6` are reported as **needle DRIFT**. Both needles are
code blocks I did not touch — this commit changes only comments in that file — and both were
verified **absent on master `c47b25a5` too**, by testing the full needle strings against both
trees. Pre-existing. They score NOT-APPLIED rather than false-killing, so the battery is not
lying, but two of its mutants are silently inert. **Parked P117-6.**

---

## Needle

**NEEDLE: latency 21 ms @ 2026-08-29T05:39:27Z**, 7/7 members served, all 3 graded surfaces
present. `DIAG: latency-build REFUSED` — 2 of 7 members cold against a floor of 4.

**Said up front: this ship does not move the needle, and could not.** The needle is the median of
seven per-path p50s (12, 13, 17, **21**, 47, 50, 389.5) — the median is `discover_web` at 21 ms,
and nothing in this cycle touches it. `search_cold` at 389.5 ms is the **maximum** of the set,
18× the next member, so even a large win there moves the median by zero. That is the instrument
working as ruled, not a disappointment; the third cycle running to say so.

⚠️ The runner directive still specifies **option b** (per-surface equal-weighted cold p50); the
harness in the tree is **option c** (ruling 127) and prints `NEEDLE` over every served sample with
the cold statistic demoted to `DIAG`. **Third consecutive cycle to flag this drift** — parked
P116-6, not this lane's to edit, and it is now old enough to be worth a ruling rather than a park.

---

## Parked

- **P117-1** — `top_result_id` is null for every futures-only answer; needs a type discriminator
  before it can be widened. Schema question.
- **P117-2** — the typeahead log arm's guaranteed half is elected by the Flow Sentinel's gold set.
  Real, measured, **and not safely removable** until a demand signal exists. Blocked on #1916.
- **P117-3** — P116-4's mechanism: `debug_timing` cannot be the suppression flag on `/search`
  without pinning `search_cold` to a forced cold build. Needs a suppression channel that is not
  also a cache bypass — and one reachable over HTTP, since the polluter is.
- **P117-4** — the residue scanner reports a missing harness source as RESIDUE.
- **P117-5** — the residue scanner's Pass B is a commit diff and prints CLEAN at zero coverage.
- **P117-6** — `typeahead_warmer_mutations` M4/M6 needles have drifted on master; both inert.
- **P116-6** (inherited, third flag) — the option-b/option-c directive drift.

Issues: **#1916** is this finding's home and now carries the census. **#2239** sharpened, not
closed. None closed — nothing here has production evidence of a user-visible change yet, and
`result_count` is written forward-only, so the 30-day window heals rather than backfills.

**Rulings banked NONE** (next free **138**). **Gotchas NONE banked**; two candidates offered in
the report (the dirty-tree residue green, and "an orphaned `.pyc` can fail a gate for a file that
does not exist").
