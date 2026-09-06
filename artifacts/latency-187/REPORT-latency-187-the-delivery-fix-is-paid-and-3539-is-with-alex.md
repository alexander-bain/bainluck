# latency/187 — the delivery fix is PAID; #3539 is with Alex

**PILLAR: DISCOVER · SHIP: the `/search` head stops being cold when a user searches.**
Session 2026-09-06, 13:43Z – 14:35Z (06:43 – 07:35 PT). Directive: `187-the-delivery-fix-is-staged-3539-is-now-the-binding-one.md`.

## Verdict in one line

#3546's post-deploy check is **PAID and it passes** — delivery `undelivered_fraction` **1.0 → 0.143**,
and three head terms went `miss → hit` on the live site. #3539 is unchanged, was predicted to be
unchanged, and is now staged for Alex as a single freshness decision.

---

## 1. The post-deploy check (directive §1) — PAID

`b44e47bc` reached production as **v4207 at 14:07:16Z**. Before-window 13:43–14:05Z on `abfc806e`;
after-window 14:07–14:26Z.

| instrument | before | after |
|---|---|---|
| `matched_delivered` / `matched_emitted` (600 s bucket) | **0 / 30** | **24 / 28** |
| `undelivered_fraction` | **1.0** every sample | **0.143** |
| `delivery_age_s` (20 s interval) | 118 → 313 → **946** | **6 – 50** |
| `last_result_summary.period_s` | **1202 s, 1431 s** | **81 s, 85 s, 152 s** |
| real-pass gap p50 (duration ring, wall ≥ 1 s) | **331 s**, max 6864 | **83 s**, max 160 |
| `starts_24h` | 106 / 3135 expected | 140 (+33 in 15 min) |
| `x-search-cache` on `chiefs` / `alcaraz` / `thun` | **miss / miss / miss** | **hit / hit / hit**, 0.16–0.33 s |
| `ratio` | 0.03 | **0.04** ⚠️ |

### The instrument the directive named would have failed a working fix

The directive set the bar as "`ratio` materially under ~0.3 is a finding". `ratio` divides by
`window_s` = **17.4 h**, so fifteen minutes of perfect delivery moves it 0.03 → **0.04**, and it will
read ~0.04 for hours. On that bar this fix fails; on the 600 s bucket it passes decisively. **The
bucket pair is the only instrument in the payload with a window short enough to see a change this
recent.** Recorded because it is the same family as the trap §4 of the directive already carried
(a field computed over completed runs cannot testify about runs that never started) — here the
field is computed over a window *longer than the change*.

### What did not move, and was not supposed to

`expired: 8, fresh: 0, rebuilt: 8` on **every** post-deploy pass. The achieved period is 81–152 s
against a **60 s** TTL, so the entry is dead before its replacement is due. That is #3539. The
directive explicitly pre-empted reporting this as a #3546 regression and it was right to.

**Caveat, stated rather than buried:** five releases (v4207–v4211) restarted the workers inside the
19-minute after-window. It bounds how precisely the *period* can be quoted; it does not touch the
delivery claim, and the conclusion survives it — the best period this scheduler can produce is 60 s,
which already equals the TTL before any rebuild time is spent.

## 2. #3539 (directive §2) — staged for Alex, not decided here

`alex-inbox/latency-187-the-search-box-needs-one-freshness-call-from-you.md`. One lettered decision,
A recommended and the default. Two corrections made to the material before it went in front of him:

- **Option 4's staleness was under-stated.** "At most 120 s old" is the write *interval*; the content
  was queried `D` seconds before it was written, so the age is `120 + D` = **~132 s typical, ~146 s
  worst**. Today's equivalent is `60 + D` ≈ 72–86 s, so the honest framing is **72–86 s → 132–146 s
  (~1.7×)**, not the 3× that "60 → 180" implies. The "half the rebuild load" half of the claim is
  correct and was re-derived.
- **The freshness cost is concrete.** `/search` returns `home_score`, `away_score`, `status`,
  `hero_probability`, and the search page renders them via `EventCard` (`:166,270,301`). Under option
  4 a **live score in search results can sit ~2.5 min behind the game page it links to** — the reason
  option 2 is not simply dominated. `search_cache.py:75-88` already frames the TTL as a product
  judgement with a peer group (`/typeahead` 65 s, anon Discover 60 s); option 4 makes `/search` 3× its
  siblings, so it is a consistency ruling across three surfaces.

Also flagged to Alex: **A is free and reduces load**, which he should know before answering D79
("rent another server, ~$25–50/mo") — A may remove the need for it.

## 3. Unasked-for finding: the head we now reliably warm is half unreachable

Filed as evidence on **#1916** (which already exists and already blocks head tuning — no duplicate).

Production head, `last_result_summary.head`:
`chiefs · sabalenka` · alcaraz · safiullin` · broncos cardinals` · lsu ole miss` · sabalenka · thun`

**Four of eight slots carry a trailing backtick**, and `` sabalenka` `` duplicates the clean
`sabalenka` in the same head — two cache keys, two rebuilds per pass, one intent. `btrim` defaults to
whitespace, so they are distinct keys.

`MIN_HEAD_SESSIONS = 2` is cited in `search_head_warmer.py:541` as **this issue's mitigation for the
`/search` side**. It does not mitigate: automation presents a fresh session id per request, so a
distinct-session gate is the one gate it clears for free.

🔴 **A correction I had to make mid-investigation, recorded so nobody repeats it:** I first read the
bare-UUID `session_id`s as the automation tell. They are not — `discoverInteractions.ts:248` **prefers
`crypto.randomUUID()`**, so a UUID is the *normal browser* format and splitting on id shape
false-positives the whole table. The signature that survives is **burst timing**: `` lsu ole miss` ``
puts 4 distinct sessions inside **five seconds**, against a table base rate of 0.08 searches/minute.
`chiefs` I explicitly did **not** call automation — 33 rows over 4 days has an innocent reading.

Provenance of the backtick is **unresolved** — the strings appear nowhere in `.claude/handoff/` or
`tools/`. Not chased further; the write-time origin flag #1916 specifies is what would answer it.

## 4. Traps this session paid for

- 🔴 **A metric whose window is longer than the change cannot see the change.** `ratio` over 17.4 h
  reads 0.03 → 0.04 across a fix that took delivery from 0/30 to 24/28. Before quoting a rate, read
  its `window_s` and compare it to the age of the thing you are testing.
- 🔴 **Probing the surface you are measuring writes the thing you are measuring.** `GET /search`
  populates the very cache whose hit-rate is the ship. Polling it on a loop would have manufactured a
  100 % hit rate. Sampled once per term, 30 min apart, and leant on `expired: 8/8` to prove nothing of
  mine was resident.
- **`deploy: completed/skipped` on a green CI run.** The run was `event=pull_request` on someone
  else's branch whose merge ref contained our sha; `if: github.ref == 'refs/heads/master' &&
  github.event_name == 'push'`. Filter `actions/runs` by `branch=master&event=push`, and read the
  **release**, not the run colour.
- **`actions/runs?head_sha=` needs the full 40 chars** — an 8-char prefix 404s and reads as "no CI".
- **`setsid` does not exist on macOS** — `nohup … & disown`.
- **A merged sha is not a deployed sha.** `b44e47bc` sat on master for 26 minutes behind a 5-deep CI
  queue, and one intervening release (v4206 = `f5785b68`) was its own **first parent** — a release
  whose sha looks adjacent can still be pre-fix. `git merge-base --is-ancestor` before believing it.

## 5. Artifacts

- Samplers/analysers: `.lat187-sampler.sh`, `.lat187-summary-sampler.sh`, `.lat187-passes.py`
- Data: `.lat187-delivery.jsonl` (48 rows), `.lat187-summary.jsonl` (35), `.lat187-passes-BEFORE.txt`
- Issue comments: **#3364** (post-deploy, PAID), **#3539** (binding + two corrections), **#1916** (head contamination)
- Alex: `alex-inbox/latency-187-the-search-box-needs-one-freshness-call-from-you.md`

## 6. For the next session

1. **#3539 is with Alex.** Do not build any of A/B/C before he answers. When he does, the winning
   option must also re-derive `_needs_rebuild` as `ttl < max(R, P_effective)` (#3539's defect 5), and
   PR #3534's 24 guards are reusable.
2. **Re-measure the period in a deploy-free window.** 81–152 s is contaminated by five restarts; the
   theoretical floor is 60 s. Worth one clean read to see whether the residual 14 % undelivered is
   real or was restart churn.
3. **#3364 stays open** — `precompute_discover_candidate_base` (ratio 0.35) is not covered by #3546.
4. **#3398 is now safe to re-measure** — its 35–43 % was taken while 97 % of fires were discarded.
5. Do not present a fourth repair of #3480; it is parked on Alex.

— latency/187

---

# PART TWO — D81 = A arrived mid-session, and the residency fix was built to it

At 14:40Z a directive landed: Fable-5 read the alex-inbox note, opened **D81 in YOUR-TURN §1 with
default A**, and ordered the CERT-2068 repair built to it (Alex is on his phone until Monday). So
the second half of this session is a build, not a measurement.

## 7. What shipped into review

`PR #3534`, branch `program/latency-248-…`, rebased onto current master (which now carries #3546).

| | value | why |
|---|---|---|
| `SEARCH_RESPONSE_TTL_SECONDS` | 60 → **180** | **ruling D81 = A**, cited at the constant, in the docstring, and in the test that pins it |
| `REFRESH_AHEAD_SECONDS` | 25 → **170** | derived: `P_effective + full_rebuild_budget + margin` |
| `effective_pass_period_s()` | **60 s** | `beat × ceil(floor/beat)` — the floor (45 s) is NOT the period |
| `full_rebuild_budget_s()` | **100 s** | `ceil(head/concurrency) × per-query bound` — the pass, not one query |
| `residency_invariant()` | 3 clauses | CAUGHT · SURVIVES · BOUNDED, executable, each with a named failure string |

## 8. Three things this build refuted, two of them mine

**(a) CERT-2068's repair was unsatisfiable as written.** It required the cadence bind *"without
extending the 60 s freshness ceiling"*. Residency needs `TTL > P_effective + budget` = 160 s, so at
a 60 s ceiling the feasible set is **empty**. That is why the ceiling had to become a product
question rather than a lane's tuning — and it is what §2's note to Alex bought.

**(b) #3539's option 4 — which I recommended to Alex in writing — ships a hole.** It set
`REFRESH_AHEAD = 90`, below `TTL − P_effective` = 120, so the first pass that could rebuild an entry
calls it `fresh` and walks past. Refused by name in a test. The ruling's *intent* (a three-minute
answer) is honoured; its arithmetic was wrong.

**(c) 🔴 My first repair was blocked, and the grader was right — CERT-2084.** I asserted
`TTL − period > budget` where #3539's necessary form is **`refresh_ahead − period > budget`**.
`TTL − period` describes only the phase the *warmer* writes at. The route writes its own cache on an
organic MISS at an **arbitrary** phase, so an entry can first be seen at exactly the threshold, be
skipped by the `<`, and return one period later with 90 s against a permitted 100 s rebuild — a
**10 s** cold interval. Reproduced before fixing. The second repair (CERT-2086) binds the threshold.

## 9. The regressions, both halves red-then-green

| case | blocked constants | shipped constants |
|---|---|---|
| CERT-2068's short-then-long, warmer phase | absent **`[(63.3, 83.8)]` = 20.5 s** on `f81fdfe4` | none over 600 s |
| CERT-2084's organic entry at the threshold edge | absent **`[(180.0, 190.0)]`** on `cc2e0694` — the graded interval to the tenth | none over 1200 s |
| every pass pinned at the full 100 s budget | — | none over 900 s |
| phase sweep, every reachable organic offset, by a **closed form that is not the simulation** | convicts 150 (asserted) | clean |

The run lock is modelled (a rebuild longer than one beat suppresses the fires underneath it), and
the beat grid carries a phase, because its alignment relative to a user's write is arbitrary.

**Mutation: 12/12 killed, control green, tree clean.** Including threshold → 150 (the blocked
value), threshold → 161 (clears `P+B` by 1 s with no margin), clause (2) reverted to the exact
blocked bug, and each of the three clauses dropped independently.

## 10. Cost, corrected in Alex's inbox

I told Alex option A "halves the work". **That was wrong** and is corrected in an appended section
of his note: the halving came from option 4's every-other-pass cadence, which is precisely what
opens the hole. The head rebuilds on **every** pass, so load is unchanged and a served answer stays
**~71–86 s** old — essentially today's freshness. 180 s is a provability ceiling, not a typical age,
which also shrinks the live-score concern I raised.

## 11. Traps this half paid for

- 🔴 **A guard can be written against the wrong phase and look rigorous.** The first harness seeded
  only warmer-aligned writes, so it could not observe the state that holes. When a system has two
  writers (a warmer and the route itself), a residency proof must sweep the phase, not sample it.
- 🔴 **A sweep that ranges outside the reachable set manufactures failures.** Mine initially swept
  organic offsets to the TTL and reported 80–180 as cold; a pass arrives within one period of any
  write, so those states cannot occur. The temptation is then to loosen the assertion. Bound the
  sweep instead, and say why in the docstring.
- **A fake Redis with one mutable expiry cannot answer a question about the past.** The first
  write-log draft reported a clean run over a configuration that measurably holes, because a later
  write had moved the expiry the backwards scan read. Append-only log.
- **Read a mutation battery's exit code, not its text.** My first battery printed all nine SURVIVED
  because it grepped lowercase `failed` against pytest's uppercase `FAILED` summary line. Every one
  had actually died. `rc == 1` is a result; anything else is a story about the harness.
- **A blocked cert's required repair can contain an impossible clause.** Reading it as binding would
  have produced a fourth blocked presentation. The move is to prove the impossibility arithmetically
  and route the impossible term to whoever owns it — here, Alex.

## 12. State at session end

- **CERT-2086** staged (`repairs CERT-2084`), sha `31598471`, PR #3534 OPEN, exact-sha CI in flight.
- **CERT-2084** BLOCK banked; **CERT-2068** BLOCK banked. Chain: 2068 → 2084 → 2086.
- Nothing merged. No production write. `master` untouched by this lane.
- **Owed after deploy:** head-term `x-search-cache` hit rate and `last_result_summary.expired`
  (8/8 on production today) — named in the cert rather than claimed.

---

# PART THREE — four presentations, four correct BLOCKs, and where presentation five starts

The residency ship did **not** land. It is on `program/latency-248-…` at `5e5b3f70`, PR #3534 OPEN
and MERGEABLE, CERT-2089 BLOCK. Stopping here is a judgement, not an abandonment — reasoning in §16.

## 13. The chain, and what each grade found

Every BLOCK was correct, and each found a term the previous one had no reason to look at. Recording
them together because the *pattern* is the lesson, not any single defect.

| cert | sha | what it found | verified by me before accepting |
|---|---|---|---|
| **2068** | `f81fdfe4` | removing the DELETE does not keep the entry alive through a rebuild | reproduced 20.5 s |
| **2084** | `cc2e0694` | invariant used `TTL − period` where the necessary form is **`refresh_ahead − period`**; an organic write at the threshold edge is skipped, then rebuilt with 90 s against a 100 s budget | reproduced **10.0 s** |
| **2086** | `31598471` | the head is **re-ranked every pass** and dispatched through a **shared cursor**, so one query is written first in one pass and last in the next | reproduced **[181, 200) = 19 s** |
| **2089** | `5e5b3f70` | the route's 20 s deadline is a **cooperative per-stage** timeout, not a hard wall; `wait_for` wraps only the route call at 25 s, and the two **sync** `_cache_ttl_seconds` Redis reads occupy the cursor *outside* it | confirmed at `search_head_warmer.py:858` and `:734` |

**The through-line: every one of my four models was a bound taken from something that was not the
thing that binds.** The floor instead of the period. The TTL instead of the threshold. A stable
position instead of a re-ranked one. A cooperative stage deadline instead of an enforced wall. Each
time the number was *available and plausible* and each time it was not the constraint.

## 14. What IS built and correct on that branch

Not wasted, and presentation five should build on it rather than restart:

- `effective_pass_period_s()` — `beat × ceil(floor/beat)` = 60 s, not the 45 s floor.
- `max_same_query_write_interval_s()` — `quantize(max(floor, budget)) + budget`, the run lock
  bounding the pass gap.
- `residency_invariant()` — four clauses (CAUGHT · SURVIVES · BOUNDED · INTERVAL), each with a named
  failure string, each independently mutation-killed.
- Four regressions, each red-then-green with the graded interval reproduced to the tenth, plus a
  reachable-offset phase sweep by a closed form that is asserted to convict its own blocked value.
- **13/13 mutants killed**, control green.

The only wrong number is the **budget**, and clause (4) already consumes it correctly.

## 15. Presentation five, specified

CERT-2089's required repair: *"derive from and enforce a hard whole-worker-unit bound, or change
width/concurrency/cadence so that real bound fits D81."*

The constraint is `quantize(max(45, B)) + B < 180` with `B = ceil(head/concurrency) × U`, where `U`
is the **enforced** whole-worker-unit bound (TTL read + route call + TTL re-read). Feasible set:

| option | B | interval | margin | cost |
|---|---|---|---|---|
| current (head 8, conc 2, U=25 + unbounded sync reads) | ≥100 | ≥200 | **−20** | the BLOCK |
| **(a) head 8, conc 2, hard U=20** | 80 | 160 | +20 | tightest timeout; load unchanged |
| **(b) head 8, conc 4, U=25** | 50 | 110 | **+70** | doubles concurrent DB sessions on the heavy endpoint |
| (c) head 6, conc 2, U=25 | 75 | 155 | +25 | warms 2 fewer terms — a product regression |
| (d) head 8, conc 2, hard U=15 | 60 | 120 | +60 | tighter still |

**Recommendation: (a), and it needs one open question answered honestly rather than modelled away.**
A hard unit bound means a rebuild can be *abandoned*, and an abandoned rebuild writes nothing — so
the write interval for that key becomes two pass gaps and the invariant's own premise ("every pass
writes every key") is not guaranteed by any choice of constants. Presentation five must either bound
that case too or state it as a reported failure mode (`timeouts`) distinct from a residency defect,
and say which in the cert's first paragraph. Modelling it silently is how presentation five becomes
BLOCK five.

Two mechanical items the same repair should carry:

1. Wrap the **whole** unit, not the route call — the sync TTL reads at `:734` are inside the cursor
   and outside the timeout. They also block the event loop (gotcha #39's shape) while holding a
   cursor slot.
2. `effective_per_query_bound_s()`'s `min` against the route deadline is **wrong as justification**
   and should go or be re-framed: a cooperative stage deadline is not a wall. Keep the function only
   if it takes the min of *enforced* bounds.

## 16. Why I stopped at four rather than pushing a fifth

Four consecutive presentations, each blocked by a term I had not modelled, at the end of a long
session. The remaining choice is not a bug fix — it is a **load/product trade-off** (tighten the
per-query wall, double concurrency on the heaviest endpoint, or warm fewer terms), and option (a)
carries an unresolved question about abandoned rebuilds. A fifth attempt built now would be a guess
dressed as a proof, and the cert bus has correctly refused four of those already.

Nothing is stranded: the branch is pushed, the PR is open and mergeable, the invariant and all four
regressions are committed, and the feasible set above is arithmetic rather than opinion.

## 17. Session totals

- ✅ **#3546's post-deploy check PAID** — the one thing the directive ordered first. Delivery
  `undelivered_fraction` **1.0 → 0.143**, three head terms **miss → hit**.
- ✅ **#3539 put to Alex**, ruled **D81 = A**, and the note corrected twice when the build refuted it.
- ✅ **#1916** extended to `/search` with measured evidence.
- ⛔ **The residency ship is not landed.** CERT-2089 BLOCK, specified above for the next session.
- Issue comments: #3364, #3539, #1916. Alex: one note + one correction. Certs staged: 2084, 2086, 2089.
