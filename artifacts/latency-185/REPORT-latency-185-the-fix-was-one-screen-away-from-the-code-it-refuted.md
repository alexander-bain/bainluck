# latency/185 — the fix was one screen away from the code it refuted

**PILLAR: DISCOVER. SHIP (narrow): when the `/search` warmer refreshes a popular term, that term
stops going blank for the seconds the rebuild takes.**

Written 2026-09-06 ~12:40Z / 05:40am PT. Branch `program/latency-248-...`, head `f81fdfe4`,
PR #3534, issue #3526, CERT-2068 staged.

---

## 0. What this session was handed, and what it did instead

184 handed over a lane with its ship parked. The routing answer for #3480 was delivered, Alex has
the decision (D79 / option D), and the directive was mostly a list of things not to do: do not
re-measure the cold head, do not present a fourth repair of #3480, do not build the grader's named
regression, do not touch the concurrency knobs. It named no build item. The only affirmative work
was watching a sampler and a census 6.5 hours out.

**I confirmed the park is real** — Alex has not ruled (YOUR-TURN D79 still carries its default, the
alex-inbox note's Update 3 was written at 04:59 PT and is unanswered), so there is no mandate for
§3's rename-and-re-present. Then I went looking in the lane's own domain for work that was
unclaimed and permitted, and found some.

## 1. The finding

**`#2304`'s fix was applied to one of two warmers.** The other one still has the defect, and it is
the heavier one.

- `typeahead_warmer` → `/api/events/typeahead`: fixed 2026-08-29 by `8529543f`
  (`_force_cache_rebuild` — skip the cache READ, keep the cache WRITE). `_drop_cached` deleted
  outright. Live: the commit is an ancestor of production `c1ac1d6c`.
- `search_head_warmer` → `/api/events/search`: **still DELETEs**, at `search_head_warmer.py:291`.

The ContextVar that fixes it is named `bainluck_typeahead_force_cache_rebuild` and lives in
`routes/events.py` — **the same file `search_events` lives in.** Meanwhile `_drop_cached`'s docstring
went on teaching the premise that had been refuted a few hundred lines away:

> "The route writes its cache only on the miss path, so the sole way a warmer can extend an entry's
> life is to make the entry not be there."

Eight days. The refutation never crossed the file it was written in.

**Width.** `PER_QUERY_TIMEOUT_SECONDS = 25`, and the key is absent for the whole awaited rebuild.
Production `c1ac1d6c`, `task-metrics?task=warm_search_head`, read ~12:15Z: 98 starts / 97 successes /
0 failures in 24h, with real passes at **3,330–23,820 ms** against ~11–56 ms floor-skips. #2304
measured its `/typeahead` twin at 2.0–3.7 s and that was enough to fix it; this is the endpoint
#1866 prices at 2.8–6.4 s cold.

**Stated as it should be:** the pass durations are measured. The user-facing spike is **inferred**
from #2304's identical mechanism. I did not probe `/search` head-term latency, said so in the issue,
the PR and the cert, and parked the probe as LAT-P245.

## 2. What shipped

`f81fdfe4`, PR #3534, closes #3526.

- `_force_search_cache_rebuild` — a **second** ContextVar, joining the `search_events` cache READ
  condition and only the read. Second var rather than a reuse because one flag read by both routes
  would let either warmer make the *other* route bypass its cache.
- The warmer sets it and stops deleting. Old answer served continuously until the new one replaces
  it. **Max staleness unchanged** at the 60s TTL — this buys latency, not freshness. A failed or
  degraded rebuild now leaves last-good where it used to leave a hole.
- `_warm_one` re-reads the TTL. It previously reported `warmed` because the route returned, which
  was survivable only while the DELETE guaranteed a miss; rebuilding over a live entry removes that
  guarantee. Unchanged ⇒ `no_write` ⇒ pass is `partial`; unreadable ⇒ `warmed_unverified`.
- Module docstring rule 2 corrected in place, since it taught the refuted premise.

**Guard:** `test_search_head_warmer_overwrites_not_deletes.py`, 24 tests, both directions.
**Mutation 6/6 killed, control green.** 577 tests passed across the search/typeahead/warmer band plus
startup and beat wiring. Ruff clean on all three files.

### One thing the sibling's guard does that I could not copy

The sibling's route-side guards match a substring against one source **line**. That works only
because its conditions fit on one line. This route's read condition is a parenthesised multi-line
boolean, so a line-wise `"A" in line and "B" in line` scan over it is **vacuously empty — it would
pass with the feature deleted.** Mine walk the AST instead, and locate the write guard by its
*effect* (a `setex` in its body) rather than by the name `degraded`, so renaming the variable cannot
quietly disarm it. Mutants M2 and M3 exist to prove those two guards actually fire.

## 3. Two corrections to things this lane has on record

Both matter because they route the next session, and one of them is in front of Alex.

**(a) 184's directive says the September probe band corroborates #2304. It cannot.** #2304 *is* the
DELETE hole, and the DELETE has not been on the typeahead path since 2026-08-29. Whatever produced
184's 57.4%-over-2s reading, it is not #2304. Commented on #2304 and corrected in
PARKED-MEASUREMENTS' LAT-P244 entry, which repeats the same claim in its method note.

**(b) The better candidate is #3506, and it is bigger than its title.** From the 239 real passes
already collected by the 182/247 sampler (no new measurement): **87 of 239 (36.4%) left ≥1 of the 40
head terms unwarmed with `reason=error`**, tail reaching **7 of 40** in one pass, against a title
that says 1–6. An unwarmed term makes the next user pay the full cold build — which is exactly what
produces a bimodal ~136 ms / ~2.8 s distribution on a rotating subset of terms. Evidence added to
#3506, unclaimed. It plausibly deserves better than p2.

### A near-miss worth recording

I nearly reported that #2304's fix was **failing in production**, on the strength of
`.lat180-nowrites.jsonl` showing 28 of 88 passes with non-empty `no_writes` — which #2304 itself
declares is the fix failing. It was not. That capture is 05:57–06:31Z, *before* the #3399 deploy;
`sta`/`ben`-class terms degraded and therefore never cached, #3399 fixed it, and 182's 44-pass
post-deploy is the clean AFTER. Checking the window before relaying cost two minutes and would have
cost the lane a false alarm to Alex (notice 26(b)).

**And the instrument trap underneath it, which I hit and 180 had already banked:** `no_writes` and
the named `errors` list live in `last_result_summary`, **not** in the ring's per-pass `records`. The
record shape has no such key, so scanning `records` for `no_writes` returns zero *vacuously* and
reads exactly like a clean result. My first scan did this and I nearly banked it as proof that
#2304 was healthy. It would have been a green reading of an absent field.

## 4. What is NOT done, and is not being quietly dropped

- **#3480 / the collision fix is still parked on Alex**, exactly as 184 left it. PR #3483 open and
  mergeable at `fc9459b6`, nothing staged for it, no fourth repair presented. §3's rename is ready
  to execute the moment a mandate exists.
- **The user-end probe for #2304 and #3526 is unrun**, parked as **LAT-P245** with the method, the
  head-confirmation step and the exclusion trap. **#2304 must not be closed without it.**
- **LAT-P244** (cold head across a full day) still parked, unchanged but for the correction above.
- **The 18:30Z + 18:45Z compaction window** is still the first chance to census the cold rate *with*
  compaction resident. The sampler runs to 19:10Z and covers it at no cost.
- **#3398** — the dominant cause — remains unclaimed, and this session did not touch it.

## 5. For whoever runs 186

The lane has two independent things in flight and they must not be confused: **#3480** (parked on
Alex, do not re-present) and **#3526** (staged as CERT-2068, awaiting a grade). The second is not a
repair of the first and shares nothing with it but a surface.

The honest summary of this lane's week is that the search box has **at least four** separate causes
of going cold — #3398 (head wholly expired), #3506 (per-term errors), #2304/#3526 (warmers blanking
their own entries), #3480 (the morning collision) — and until 184 they were being treated as one.
Naming them apart is most of the progress. Only #3526 moved today.

---

## 6. Postscript, ~13:15Z — CERT-2068 came back BLOCK, and the grader was right

Graded at 12:22Z, four minutes after staging. **Token withheld, and correctly.**

> "removing the eager DELETE does not keep the old `/search` entry alive through rebuild. A 20s beat
> plus a 45s minimum yields actual eligible starts 60s apart… the submitted measured 3.3s-to-23.8s
> sequence permits ~20.5s of absence during the second rebuild."

Checked and accepted in full. The arithmetic is `hole = max(0, D_next − D_prev)`: the entry written
at the end of one pass expires `TTL` later, the next pass finds it with roughly the *previous*
build's duration left, and a short-then-long pair leaves the gap. My ship line — "that term stops
going blank for the seconds the rebuild takes" — claims a continuity the diff does not deliver.

**What the diff does deliver, unchanged and still worth having:**

| | before | after |
|---|---|---|
| hole per pass | `D` — unconditional, every pass, full rebuild duration | `max(0, D_next − D_prev)` |
| failed / degraded rebuild | leaves a hole | leaves last-good |

Strictly better, never worse — and not what the header said. §3(a) of this report criticises 184 for
an attribution it did not check; this is the same failure in my own header, caught by someone else.
Worth stating plainly rather than filing under "narrow scope".

### The block exposed the real bug — #3539

`test_the_refresh_ahead_window_actually_keeps_the_head_alive` is supposed to prove the head never
goes cold. It is unsound twice over:

1. It reads `MIN_PASS_PERIOD_SECONDS` (45) rather than the **achievable** period. The beat is 20s
   and the floor is 45s, so passes actually land 60s apart. The first clause is really `60 < 60`
   — **false**.
2. It has **no rebuild-duration term at all** — it assumes the write lands the instant the pass
   starts, when the warmer awaits a rebuild measured at 3.3–23.8s.

So the `/search` head has never been guaranteed resident, and the guard that says otherwise has been
green throughout. `_drop_cached` was masking it: the head was unconditionally absent during every
rebuild anyway, so cadence could never make it worse. Removing the DELETE is what made the cadence
binding — and the bus noticed within four minutes.

Filed as **#3539** with the three mutually exclusive repairs and what each costs: 2–3× rebuild load
on the contended `background` queue, or a staleness ceiling moving 60s → 85s, or #1866's blocked
DDL. **I did not pick one**, deliberately — none is a build lane's unilateral call, and the cert
explicitly forbade the second. PR #3534 stays open and unmerged; the code and its 24 guards are
reusable by whichever repair wins.

### The honest scoreboard for this session

Nothing shipped to production. What moved: one real defect fixed but blocked on an overstated claim,
one pre-existing unsound invariant found and filed (#3539), two mis-attributions corrected (#2304's
citation, LAT-P244's method note), one issue corroborated at scale (#3506), one measurement parked
(LAT-P245), and Alex given a correction he had not asked for. The lane now names five distinct
causes of a cold search box where it named one on Friday.
