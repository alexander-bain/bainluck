# LAT-P135 — the "did you mean" that scanned every team

**Pillar: DISCOVER.** Ship: **a misspelled search stops paying for a full table scan before it
can suggest the right team.**

Issue **#1866** (the typeahead cold-path parent). Branch `program/latency-121`, base
`origin/master` @ **`fe5ec72c`**.

⚠️ **THE BRANCH WAS REBASED MID-CYCLE AND EVERY GATE RE-RUN ON THE REBASED TREE.** It was cut from
`ce5f719b`; master advanced to `fe5ec72c` while the first full suite was in flight, and that move
merged **LAT-P134**, which edits `backend/app/routes/events.py` — **the same file this ship edits.**
Different regions (P134 adds the `_force_cache_rebuild` ContextVar on the cache-read path; this
edits the fuzzy fallback ~2,000 lines below), and the rebase was conflict-free with both changes
verifiably present afterwards. **The first suite run was KILLED, NOT QUOTED.** `merge-tree` exit 0
is a statement about text; the suite on the rebased tree is the statement about behaviour, and
INT-151's worked example is that git can auto-merge with no conflict and still silently drop
something the other side depended on.

All production measurements in this document were taken against slug `ce5f719b`. They are
measurements of the *defect*, which `fe5ec72c` does not touch — LAT-P134 changed the typeahead
warmer's cache-write behaviour, not the fuzzy fallback's access path.

---

## 1. How the target was chosen, before a fix was chosen

The lane's frozen instrument (`cold_path_snapshot.py`, LAT-P099 — bars committed before the first
number) against production `ce5f719b`, `n=6` round-robin, organic `latency-stats` read taken first:

```
Discover   native 70.5 ms · web 20.5 ms (cold 2,776.0)   bar 1000  MET
Sports     native 35.0 ms · web 13.0 ms                  bar 1000  MET
Browse                 — no server dependency
Search     native 19.0 ms                                bar 1000  MET
My Stuff   native 20.0 ms                                bar 1000  MET
typeahead  COLD BUILD  p50 2,530.5 ms                    bar  500  NOT MET
search     COLD        p50   274.5 ms                    bar 1000  MET
VERDICT: THE COLD-PATH BAR IS NOT MET                    exit 1
```

**One row fails, and it is the same row that failed last cycle** — #1866, whose 90–95 % cause is an
un-indexed `to_tsvector` scan that needs **DDL and is blocked on Alex** (`alex-inbox/latency-003`).
So the cycle could not take the biggest number. It took the biggest number it was *allowed* to take,
and two candidates were ruled out **by measurement, not by preference**:

### Ruled out 1 — the Discover cold miss was a transient, not a cadence

The snapshot recorded `Discover web` at **cold p50 2,776 ms**, one `miss` in six, on the default
landing page. A p50 over `n=6` cannot distinguish a periodic hole from a single transient, and the
difference is the entire finding. So a purpose-built probe asked the question the snapshot
structurally cannot (`scripts/probe_discover_hole.py`, new this cycle):

| shape | principal | n | cache split | server p50 | **holes** |
|---|---|---:|---|---:|---:|
| `discover_web` | anon | 50 | `hit` 43 · `stale_hit` 7 | 19.0 ms | **0** |
| `discover_native` | fresh session | 50 | `shared_hit` 41 · `shared_stale_hit` 9 | 51.0 ms | **0** |

🟢 **Zero absences in 100 samples over 9 minutes, on both key paths.** LAT-P112's absence net is
doing its job. The snapshot's single miss is not reproducible and is not a defect — **recorded as a
negative result rather than converted into a fix looking for a problem.**

The probe is deliberately SLOWER than the 40 s rail it audits: a `miss` on the anon shape rebuilds
and republishes the shared entry, so a fast prober becomes the warmer and papers over the hole it
came to find.

### Ruled out 2 — the 9.19 s playoffs sample predates the current release

`latency-stats` carried `/api/playoffs/{league_slug}` at **9,190.9 ms**, `n=1`, sample age 3,095 s
against a 1,524 s uptime — i.e. **taken on the previous slug**. Re-measured directly:

| league | http | server |
|---|---|---:|
| nfl | 200 | 32 ms |
| nba | 200 | 28 ms |
| mlb | 200 | 34 ms |
| golf | 200 | 110 ms |

🟢 LAT-P131's warm pass holds and LAT-P133's degradation fix has shipped. Nothing to do.

---

## 2. The finding

Both `/api/events/search` and `/api/events/typeahead` carry a fuzzy team fallback that answers
**"did you mean"**. Same question, same table, same 0.25 threshold, ~2,000 lines apart.

**LAT-P002/#1494 fixed one of them.** It moved `search_events` onto the `%` OPERATOR, which the
existing `ix_teams_name_trgm` GIN can serve. `typeahead_search`'s twin was never touched and kept
the FUNCTION form — `similarity(a, b) > 0.25` — which no index can serve, and which is evaluated
**three times per row**: in the SELECT, the WHERE and the ORDER BY.

`EXPLAIN (ANALYZE)` on production, same query, same 9,619-row `teams`:

| predicate | plan | execution |
|---|---|---:|
| `similarity(teams.name, 'yankes') > 0.25` | **Seq Scan**, 9,617 Rows Removed by Filter | **176.379 ms** |
| `teams.name % 'yankes'` | **Bitmap Index Scan** on `ix_teams_name_trgm` | **1.138 ms** |

🔴 **155×, off an index that already exists.** That is the whole reason this was reachable: the
dominant cost on this endpoint is DDL-blocked, and this one is not.

**Where it lands in a real request.** `?debug_timing=1` on production, four misspellings:

| q | total | `futures_query` | `fuzzy_and_concepts` | did you mean |
|---|---:|---:|---:|---|
| `yankes` | 3,680 ms | 3,197 ms | **260 ms** | New York Yankees |
| `lakrs` | 3,621 ms | 3,306 ms | **153 ms** | Växjö Lakers |
| `celtcs` | 3,531 ms | 3,072 ms | **197 ms** | Celtic |
| `dodgrs` | 832 ms | 758 ms | 33 ms | *(arm found nothing)* |

**Said plainly, because the honest size of a fix is part of the fix: `futures_query` is 87 % of this
endpoint and this cycle does not touch it.** The fuzzy stage is 4–7 % of the total, and the scan is
~176 ms of that. This removes ~175 ms from the requests that reach the arm. It does **not** move the
charter's NOT MET row, and it was never going to.

**The arm's gate makes it worse than the headline suggests.** It fires on
`not team_pool and not event_pool and len(futures_pool) < 2` — i.e. when the request found almost
nothing. A futures stage that **TIMED OUT** leaves `futures_pool` empty, so the slowest requests on
this endpoint are exactly the ones that then pay an extra unindexed seq scan on the way out.

---

## 3. The fix

`SET LOCAL pg_trgm.similarity_threshold = 0.25`, then `Team.name.op("%")(q)` **beside** the existing
`func.similarity(Team.name, q) > 0.25`. One statement added, one predicate widened. 34 insertions,
1 deletion, all in `app/routes/events.py`.

🔴 **THE PIN IS THE LOAD-BEARING HALF, AND WITHOUT IT THIS IS A SILENT RECALL CUT.** `%` tests
`similarity >= pg_trgm.similarity_threshold`, and that GUC defaults to **0.3** — *stricter* than the
0.25 this path has always used. Switching to the operator alone would quietly delete every
correction in the 0.25–0.30 band, the endpoint would keep answering, and nothing would fail.

**The band is occupied, and that was checked by looking.** Production, over all 9,619 teams:

```
q = 'lakrs'   ->  max similarity 0.2667      <-- inside (0.25, 0.30)
```

and `/api/events/search?q=lakrs` answers `did_you_mean: "Växjö Lakers"` **today**. That single live
call is doing double duty: it proves the band is real, *and* it is the end-to-end proof that
`SET LOCAL` genuinely takes effect on this connection rather than being a no-op that has sat
unverified in the twin since LAT-P002.

**The recovered-transaction case was checked, not assumed.** `SET LOCAL` is transaction-scoped, and
the futures stage can abort the transaction, so the pin could have been landing on a dead session.
It does not: the timeout handler calls `_recover_search_session`, which rolls back and then
immediately issues its own `SET LOCAL statement_timeout` — the same mechanism, in the same position,
already relied upon. `/search` runs "recover, then pin" on exactly this path.

**Recall is unchanged by construction, not by inspection.** `%` widens the candidate set to
`>= 0.25`; the retained `> 0.25` is the exact boundary (`%` is `>=`, the contract is `>`); the
`ORDER BY similarity DESC` is untouched. Only the access path changes.

---

## 4. Guards

`tests/test_typeahead_fuzzy_index_lat_p135.py` — **14 tests**, a 6 × 2 matrix plus two sweeps.

🔴 **EVERY PROPERTY IS ASSERTED OVER BOTH SURFACES.** The defect was never "typeahead is slow" — it
was that one of two twins was repaired and **nothing compared them for 130 cycles**. A guard pinning
only `/typeahead` would rebuild that arrangement facing the other way.

Red-first, on unmodified master: **5 failed, 9 passed** — the four typeahead access-path cells and
the module sweep red, every `search_events` cell green. The guard discriminates between the two
surfaces before it is asked to protect either.

Two checks are not substring tests and are the ones worth having:

* **`check_pin_is_not_stricter_than_the_boundary`** — extracts both numbers and asserts
  `pin <= boundary`. A pin *below* the boundary is harmless; a pin *above* it silently narrows
  recall and nothing notices. The two numbers live on different lines with nothing comparing
  them — the same shape as a period and a TTL set in different files.
* **`check_pin_is_issued_before_the_query`** — index comparison, because `SET LOCAL` after the
  SELECT pins nothing. **A substring test passes with the two lines swapped.**

🔴 **THE CHECKS READ COMMENT-STRIPPED SOURCE. LAT-P002's EQUIVALENT DOES NOT** — and the code it
guards is heavily commented with text that *quotes the anti-pattern it replaced*, so
`test_search_latency_contract.py` passes today by luck of phrasing rather than by construction. The
helper that would fix it (`_strip_comments`) already exists in that file and is simply not used by
those two tests. **Parked as P135-1 rather than fixed here** — it is someone else's guard and this
is a latency cycle.

### Mutation battery — `scripts/evals/typeahead_fuzzy_index_mutations.py`

**9 mutants, 8 killed, 1 survived AS DECLARED, 0 not-applied, exit 0.**

| mutant | outcome | killed by |
|---|---|---|
| `M1-REVERT-OPERATOR` | killed | uses_indexable_operator, pin_before_query |
| `M2-DROP-PIN` | killed | pins_threshold, pin_not_stricter, pin_before_query |
| `M3-PIN-ABOVE-BOUNDARY` | killed | **pin_not_stricter only** |
| `M4-PIN-AFTER-QUERY` | killed | **pin_before_query only** |
| `M5-BOUNDARY-WIDENED` | killed | keeps_exact_boundary |
| `M6-DROP-RANKING` | killed | **still_ranks_by_similarity only** |
| `M7-DROP-BOUNDARY` | killed | keeps_exact_boundary, pin_not_stricter |
| `M8-PIN-LOWER` | **survives (declared)** | *no check objected — correct* |
| `M9-SEARCH-REVERT` | killed | uses_indexable_operator, pin_before_query |

🔴 **`M8` IS DECLARED `survives` AND THE RUN FAILS IF IT IS KILLED.** A battery whose every mutant
dies has shown that the guard is loud, not that it is precise. Lowering the pin to 0.10 is
semantically harmless — `%` widens, the explicit `> 0.25` still cuts, recall is identical — so a
check asserting `pin == 0.25` would kill M8 *and* would reject a future harmless widening. The
invariant is `pin <= boundary`. M8 is the mutant that tells those two apart.

Three mutants (M3, M4, M6) die to exactly **one** check each, which is the isolation evidence that
those checks earn their place rather than riding on a neighbour.

🔴 **THE NEW HARNESS BROKE TWO TESTS ON ITS WAY IN, AND THE BREAKAGE WAS THE GUARD WORKING.** The
first full-suite run on the rebased tree came back **2 failed** —
`test_mutation_guard.py::test_no_mutant_is_sitting_in_a_harness_target_right_now` and
`::test_an_unresolvable_base_exits_2_not_1`. Both were **mine**, not the sandbox `PermissionError`
that INT-154 and INT-155 have been trading notes about, and the temptation to credit that known
flake is exactly why the control matters. The real cause is in the scanner's own output:

```
   typeahead_fuzzy_index_mutations
   Add them to SHAPES. A partial scan must not print a clean line.
```

`scan_mutation_residue.py` refuses — **exit 2, `CANNOT MEASURE`** — when a harness exists on disk
that it has no entry for, rather than printing a clean line over a harness it cannot see. A new
harness is unregistered by definition, so the scanner correctly declared itself unable to measure,
and the second failure was the first one's exit code arriving where a different reason was expected.

Registered in `DISK_FREE` (not `SHAPES`: an empty `SHAPES` list harvests zero pairs and prints
nothing, which is indistinguishable from the harness having been forgotten — the silent narrowing
the scanner exists to refuse), and the claim is **verified rather than trusted**: the module must
itself declare `MUTATES_WORKING_TREE = False`, so a list entry cannot drift away from a harness that
later grows a real write. After registration: `test_mutation_guard.py` **9 passed**, residue
**CLEAN exit 0** with three disk-free harnesses now NAMED.

⚠️ **AND THE FIRST RESIDUE SCAN OF THIS CYCLE WAS GREEN FOR THE WRONG REASON.** It ran BEFORE the
harness existed. A clean scan is a statement about the tree it ran on, and the tree changed
afterwards — the scan quoted in this document is the one taken **on the commit**, where PASS B
sweeps 5 changed files / 1,055 pairwise checks instead of 0.

⚠️ One residue run in this cycle reported **exit 2** purely because it was launched from the repo
root instead of `backend/` — `can't open file`. Recorded because gotcha #54 is exactly this:
**`1` is a result; everything else is a story about the harness**, and an exit 2 read as a finding
would have sent the next reader hunting a mutant that was never there.

🔴 **THE BATTERY MUTATES STRINGS IN MEMORY AND NEVER TOUCHES DISK.** `_mutation_guard.py` records
why: a disk-mutating harness once left a live mutant inside a real commit after a SIGTERM between
backup and restore, and SIGTERM does not run `finally`. Its own docstring says new harnesses should
prefer the in-memory form. This one does, so there is no manifest, no restore path, and no residue
that `scan_mutation_residue` needs to verify. Its oracle is the guard's own checks, **imported**,
not a second copy that could drift green over a broken guard.

---

## 5. What this does NOT fix, said plainly

* **The charter's cold-typeahead row will still read NOT MET after this deploys.** `futures_query`
  is 87 % of the endpoint and is the un-indexed `to_tsvector` scan — **DDL, blocked on Alex.**
* A never-asked term still costs seconds on first touch. Unchanged by this cycle.
* This lane does not deploy, so **nothing post-deploy is claimed.**

---

## 6. Contamination declared

* 100 `/api/feed` requests from the absence probe + 30 from the needle + 36 from the snapshot — all
  land in the always-sampled `latency-stats` window. Subtract before quoting it as organic.
* 4 `/api/events/typeahead` probes with `?debug_timing=1` (suppresses the trending vote) and 6 from
  the needle. **0 votes into `search:trending:24h`.**
* 1 bare `/api/events/search?q=lakrs` call carrying `X-Bainluck-Origin: harness`, plus the
  snapshot's 6 and the needle's 6.
* Organic `latency-stats` reads taken BEFORE each instrument run.

---

## 7. Parked

**P135-1** — `test_search_latency_contract.py`'s two fuzzy guards assert against RAW source while
the file already defines `_strip_comments`; the code they guard quotes its own anti-pattern in
comments, so they can pass over deleted code. One-line fix, not this lane's file.

**P135-2** — the fuzzy arm fires when `futures_pool` is empty, which **includes the case where the
futures stage timed out**. So the slowest requests on this endpoint do extra work on the way out.
Worth asking whether the fallback should be skipped on a degraded answer rather than merely made
fast — a product question about whether "did you mean" is worth 1.1 ms on a request that has already
lost its main answer.

**P135-3** — the second fuzzy query (`fuzzy_events`, an unanchored
`ILIKE '%<team name>%'` over `events.home_team_name` / `away_team_name`) was not examined this
cycle. It is the remainder of the `fuzzy_and_concepts` stage after the 176 ms scan is removed.

🟢 **P134-3 DISCHARGED — this cycle IS P134-3.** It was parked one cycle ago as "the fuzzy team
fallback still uses the non-indexable `similarity() > 0.25` function form; `/search`'s twin already
uses the `%` operator". That park is what pointed this cycle at the right line.

Carried unchanged from LAT-P134: **P134-1** · **P134-2** · **P133-1**–**P133-3** · **P132-1**–**P132-5** · **P131-3** · **P131-4** ·
**P130-1**–**P130-3** · **P129-1** · **P129-2** · **P129-3** · **P129-5** · **P128-1** ·
**P127-3** (**NEEDS ALEX**) · **P127-4** · **P126-1** · **P125-A** · **P125-1** · **P125-2** ·
**P124-1**–**P124-5** · **P110-4** · **P122-5**.
