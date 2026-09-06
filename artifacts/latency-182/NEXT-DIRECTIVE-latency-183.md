# latency/183 — a short prefix stops costing seven seconds, twice

Written by latency/182 at 2026-09-06 ~01:30 PT (08:30Z — PT = local `date` minus 3h,
notice 24, verified with `TZ=America/Los_Angeles date`). Staged, not consumed.

**PILLAR: DISCOVER.** **SHIP: typing a short prefix into the search box stops costing
seven seconds on every keystroke.** Named, user-visible, and already measured with a
control. See §1.

⚠️ **§1 is a REPRODUCTION of 180's baseline, not a new finding, and must not be presented
as one.** 180 banked `sta` 8.35/6.95s, `red` 6.36/8.03/7.02s and `stanley cup`
2.81 → 0.17 → 0.15s at `9dc0fd0e`. What 182 adds is that the same numbers still hold five
hours later with the fix still unmerged, and that the warmer's own `no_writes` field names
the two terms. The value is the *staleness*, not the discovery.

## Read first

`artifacts/latency-182/REPORT-latency-182-five-compaction-passes-two-slots.md` (this
branch) and `artifacts/latency-181/REPORT-…` on `program/latency-181-artifacts`.
Issues **#3480** (182's ship), **#3481**, **#3364**, **#3399**, **#3466**, **#3398**
(parent, CLAIMED by latency), **#3444**, **#3440**.

**Do not re-derive:** the concurrency sweep, `WARM_CONCURRENCY`, `REFRESH_AHEAD_SECONDS`,
`RESPONSE_CACHE_TTL_S` (178); priority queueing (179 refuted it); `pg_stat_statements`
totals (reset, most of the top 200 dead); the compaction collision and the
`long_hold_beats` / `residency_overlaps` derivation (182 settled all of it).

## 1. THE MEASUREMENT THIS QUEUE STARTS FROM — take it as given, re-take it as your before

Production, 2026-09-06 08:24Z, one second between calls, `time_connect` < 1ms on every
line:

```
/api/health                          #1 0.135s   #2 0.369s    <- network is fine
/api/events/typeahead?q=stanley cup  #1 2.027s   #2 0.152s    <- caching WORKS
/api/events/typeahead?q=red sox      #1 4.320s   #2 0.146s    <- caching WORKS
/api/events/typeahead?q=sta          #1 7.424s   #2 8.081s    <- never caches
/api/events/typeahead?q=red          #1 7.868s   #2 6.690s    <- never caches
```

**A short prefix is not slow once. It is slow every time.** A long prefix pays 2–4s once
and then 150ms. That is a cache-write failure, not a query-cost problem, and the control
rules out both the network and "typeahead is just slow".

`.lat182-warmer-samples.jsonl` in the latency worktree has this every five minutes from
08:04Z to 15:10Z, four requests a sample. It is untracked scratch — **read it before it is
cleaned up**, and if it is gone, the sampler is `.lat182-sampler.sh` beside it.

## 2. State on arrival — READ BOTH, they will have moved

**1. #3480 / PR #3483 (182's stagger).** `program/latency-247-the-search-box-stops-going-cold-at-dawn`
@ **`51e9079e`**. CERT-2045 BLOCKed the first presentation at `22bed49c` and was right;
repaired and **restaged as CERT-2053**. Two invariants now — pairwise long-hold non-overlap,
and a budget-derived rule that no compaction beat fires within `warm-typeahead`'s own
`expires` of other long-holding work. 52 tests, fails 5/52 against the blocked sha and 10/52
against the original parent, 22/22 mutants, 607 green, no alembic. Carries LAT-P242 (#3466)
as its rider, discharging CERT-2038's restage condition. Exact-sha CI `completed/success`
(run `34025029657`). **Check the ledger for CERT-2053's grade before assuming anything.**

⚠️ **A large part of the required repair was declined with a measurement, not delivered**:
"a slot opportunity throughout every compaction window" is not schedulable (59 beat entries
over budget, 1,222 fires/day, 7 clean minutes in 1,440). The remaining path is a dedicated
worker, which is in `alex-inbox` as a spend decision with a stated default of "measure for a
week first". **Do not decide it in a lane, and do not re-derive the table — it is asserted
by `TestTheClaimThatIsolationIsTheOnlyRemainingPath`, which is written so failing is good
news.**

If it landed, **the post-deploy proof is yours and it is time-boxed**: the first
single-grinder window under the new schedule is `turbo-collapse-futures` alone at
**13:40Z**, then `turbo-collapse-odds` alone at **15:30Z**, then 19:40Z. Compare against
12:30Z/12:45Z in the sampler file, which is the last two-grinder window under the parent.
The sampler runs to 16:40Z, so both solo windows are covered.
What to show: `warm_typeahead` **delivered** inside its 120s expiry through the window, and
the warmer's `period_s` p95 staying under the 65s `response_cache_ttl_s` instead of the
116–318s it reads today.

**2. 🔴 #3399 / CERT-2037 STILL HAD NOT LANDED at 08:26Z.**
`9dc0fd0e63de5665235287206fc52297646c2396`, GREEN, exact-sha CI `completed/success` (run
`34019461018`), notice-13 grep passes, no supersedes row, PR #3441 MERGEABLE, no alembic.
The integrator held `LANE-integrator.lock` (pid 71476, INTEGRATOR-228) through 182's whole
session. Two notes are pending in their inbox — 181's, and 182's with the numbers in §1.

**This is the blocker on §1's ship, and it is the first thing to check.** #3399 is 180's
shed fix; §1 is its symptom, still live. If it landed while you were away, run its
post-deploy check (`q=sta` twice, ~2s apart — the second should be a warm hit) and then
§3 is what remains. If it has **not** landed and the lock is free, gate and merge it
yourself under ruling 017; if the lock is still held, escalate to alex-inbox with §1's
table in plain English (notice 19: no "cert", no jargon — "typing three letters into the
search box takes seven seconds and the fix has been ready since 07:51Z").

## 3. ITEM 1 — THE SHIP: the guard that says a shed answer is still an answer

**This is `TYPEAHEAD-SHED-RUNTIME-CACHE-CONTRACT`, the nonblocking follow-up CERT-2032/2037
left behind, and §1 is why it is now the cargo rather than debt.** The contract: **a shed
answer WRITES and the next request HITS; a full futures-stage timeout writes NOTHING.**
Proved by hand on production, never tested — and §1 is what "never tested" looks like from
the outside.

Do **not** restage it as bare guard debt. Name the pillar and the ship in the block header
(rule ggg). The ship is §1's sentence.

**Why it was not done, so it is not rediscovered.** Three test files drive
`typeahead_search` directly and **all three rely on a cache HIT returning before the first
query**, so they pass `db=None`. This needs the MISS path — a fake `AsyncSession` surviving
every stage of a ~1,000-line function. `test_search_response_cache.py::_search` is the
model.

⚠️ **The trap that cost that file a red run:** the debug flags' declared defaults are
`Query(...)` marker objects, **truthy outside FastAPI**. Pass every flag explicitly or you
assert against the uncached path and prove nothing.

**The question §1 raises is already answered — by 180, and by the warmer's own instrument.
Do not re-derive it.** `2b6e82ac`'s message states the cause: `typeahead_search` had ONE
`_ta_degraded` flag set from two places that lose very different things — the bonus
outcome-NAME arm shedding (the dropdown still answers) and the futures query timing out
(the whole stage gone) — and `if not _ta_degraded` gated the cache write, so the first case
made an entry permanently uncacheable. Confirmed still live at 08:40Z from
`/api/admin/task-metrics?task=warm_typeahead` → `last_result_summary`:

```
terminal   partial        completed 38   total 40   rebuilt 38   seconds_max 8.022
timeouts   []
errors     []
no_writes  ['sta', 'red']      <- the route ran and Redis still holds nothing
```

`no_write` is the warmer's own **defect** category, and it names the two terms exactly.
`terminal: partial` on every single pass is these two and nothing else. So the repair is
`2b6e82ac`'s, the failing state is the shed arm and not a futures timeout, and **the guard
in this item pins the narrowed contract**: a SHED answer writes and the next request hits;
a `futures_query_TIMED_OUT` still writes nothing and must keep writing nothing (that branch
loses the whole futures stage and is the sticky-wrong-answer case LAT-P007 describes).
`no_writes` is the field to assert against on the production side.

## 4. ITEM 2 — the second half of #3364, now that the coincidence is gone

**Do not open this until #3480 has deployed and you have re-measured.** #3364's premise —
`warm_search_head` at `expires: 20` discarding 96.7% of its fires — was measured against a
pool that had a scheduled hour-long outage in it. #3480 removes the outage but not the
contention, so the residual is the real number and nobody has it yet.

The generalisation is filed and correct: **an `expires` bound must be compared against
DELIVERY LATENCY, not against the task's own wall.** `warm_search_head`'s constant carries
a comment justifying 20s against a ~4–8s pass duration; the reasoning is sound and its
premise is the wrong quantity. That belongs in `_EXPIRING_WARMER_BEATS`, beside
`warm-typeahead`'s already-derived 120.

⚠️ `warm-typeahead`'s own bound is `_LOCK_TTL_SECONDS`, chosen as a CONSTANT precisely
because a sampled worst-wall has been wrong twice. Derive `warm_search_head`'s the same
way. A number read off this week's delivery latency is refuted by next week's.

## 5. ITEM 3 — filed, not ours; coordinate, do not claim

- **#3481** — `turbo_collapse_futures` reads all 195.6M rows of a 52 GB table to choose
  5,000 partitions: `ORDER BY priority` makes the `LIMIT` unpushable, `EXPLAIN` Total Cost
  **9,024,690** against **20,422** for the same shape on the `odds` sibling. Bigger win
  than #3480 and a genuinely separate ship — it changes which rows a **destructive** pass
  selects. The cheap candidate (resolved-first in two phases, `Limit` cost 34,061) leans on
  an early stop over a 5 GB heap and needs an `ANALYZE` read before anyone believes it.
  A covering index on a 52 GB table is a migration and an attended `CREATE INDEX
  CONCURRENTLY` via psql, never Alembic (gotcha #31).
- **#3444** — `label_map` is single-valued, so `poll_all_odds` is graded on a DataGolf
  sub-poll (3.3x over) and `discover_events` on a taxonomy enrichment (4.0x under).
  LAT-P242 routes around it for capacity but it still distorts the adherence **verdicts**.
  `poll_all_odds` is the live lane's.
- **#3440** — settled golf concepts, 426 wsec/hr, byte-identical output over 3–4 rebuilds.
- Seven `external_id ==` sites remain; `admin_matching.py` is **D35/D39 — file, do not
  fix**, #2693.
- **CERT-1988 stays PARKED.** Do not merge PR #3377, do not re-stage, do not rewrite its
  header.
- **`LAT-P240-PREDICATE-SEMANTICS-GUARD`** still owed. 179's guard counts emitted writes
  against a permissive fake; production answered it empirically (1.642 → 1.647) but that is
  evidence, not a guard.

## Explicitly NOT in scope

Spending; `WARM_CONCURRENCY` / `REFRESH_AHEAD_SECONDS` / `RESPONSE_CACHE_TTL_S` / priority
queueing; a third background slot or `--concurrency=3` (a dyno purchase — that is a
YOUR-TURN entry with the number in plain English, not a change); the tsvector index
(Tier-1, integrator + Alex); ITEM 4 of 178 (`red sox` headline market — recall, not
latency, and must not be bundled); matching symptoms (D35, file under #2693).

## Rules carried forward

168 (a)–(g), 170 (b)–(e), 171 (b)–(e), 173 (f)–(i), 174 (j)–(m), 175 (n)–(x), 176 (y)–(dd),
177 (ee)–(kk), 178 (ll)–(oo), 179 (pp)–(uu), 180 (vv)–(aaa), 181 (bbb)–(ggg),
**182 (hhh)–(ppp)** all hold.

**(hhh)** A comment that names a failure is not a guard against it. The outage fixed by
#3480 was written out in full, in the codebase's own words, directly above the task that
caused it, and it stayed true for as long as the comment did. The moment you can write the
sentence, you can usually write the assertion.

**(iii)** Scope a co-residency check by THRESHOLD, never by the family you came for. The
brief said "five compaction beats". The set that actually shares the pool is six, and the
sixth belongs to another lane, sits inside the biggest offender's window at all four of its
daily fires, and would never have appeared in a check scoped to tasks named "collapse".
Derive the population from the property that makes it dangerous and the members you do not
know about are covered before you learn their names.

**(jjj)** An `ORDER BY` over a `LIMIT`ed scan can silently convert a bounded read into a
full-table aggregate. `LIMIT 5000` over 195.6M rows reads as a bounded pass and `Node Type`
is not the tell either — the tell is `Total Cost` against the same query shape on a sibling
table. When a prioritisation is added to a limited scan, the limit stops being a bound.

**(kkk)** When every fixture in a battery declares the same value for a parameter, an
expression over that parameter is untested. `min(e_a, e_b)` and `e_a` are the same function
when both windows are the same length, and the mutant survived a suite that killed twelve
of thirteen. Vary the thing the expression discriminates on, or the expression is
decoration.

**(lll) — the one §1 teaches.** Measure the user's actual sequence, not one request. One
`q=sta` at 7.4s is a slow endpoint and reads as a capacity story. `q=sta` **twice**, beside
`q=stanley cup` twice, is a *cache-write* story with its own control built in, and it
points at a specific line of code. The second call costs one second and changes what the
number means.

**(nnn) A sha you merge may never itself deploy, because the next push overtakes it in the
queue — so any post-deploy gate must test ANCESTRY, and an equality check is a hang, not a
slow pass.** The failure mode is nasty because it is silent and indistinguishable from
patience: a watcher polling for `commit == <my sha>` never errors, it just never fires, and
everyone reads it as a slow deploy. Tonight `7cb6531d` will never be the deployed head —
`138fc435` overtook it 31 minutes later — so an equality watcher would have run to its
deadline and reported nothing. `git merge-base --is-ancestor <mine> <deployed>`.

**(ooo) Before you conclude a red CI is yours, recompute the gate with your diff removed.**
`10304a33`'s CI failed on a coverage gate at 1201/1337 = 89.83% against a 90% floor, and my
one new test file was in the denominator. Without it: 1201/1336 = 89.90% — under either way.
Two minutes of arithmetic separated "my change broke the build" from "the build was already
broken and I am the fourth window to notice". Four lanes independently built the same fix
inside twenty minutes tonight (#3497).

**(ppp) A ratio's MARGIN and its DRIFT are different numbers, and only one of them
predicts.** The same gate was "under by a tenth of a percent, about two test files" and
"drifted by 135 unmeasured files". Both true. The first invites "two more files will red it
again", which is false. When you report a threshold breach, report the drift, not the margin.

⚠️ Build on a FRESH branch off master. `program/latency-247-…` (in flight),
`program/latency-182-artifacts` (docs, this file), `program/latency-181-artifacts` (docs +
the now-cherry-picked LAT-P242 commit), `program/latency-246-…` and `program/latency-242-…`
(parked) are all live.

Idle rule: empty inbox → write the next directive from the charter; never stop, never end
with a question.
