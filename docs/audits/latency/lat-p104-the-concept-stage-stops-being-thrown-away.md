# LAT-P104 — the concept stage stops being thrown away while it is still fresh

**Ship:** a person opening Discover is half as likely to pay for a concept-stage rebuild that
another request already did. The shared stage's cache key rotated every **30 seconds** against a
**60-second** TTL, so the fleet discarded a still-fresh artifact twice a minute and charged the
next person who opened the app the **865–1,249 ms** rebuild. The key now rotates once an hour;
the TTL is untouched, so nothing a user reads can get staler.

Cycle 76 · lane `latency` · identity `LAT-P104-20260828-w38563` · 2026-08-28 AM PT.
Branch `program/latency-90`, stacked on `-89` (LAT-P103).

---

## 1. Where this came from, and what this window actually did

LAT-P103 parked this as **`LAT-P103-1`**:

> the concept stage key buckets on **30 s** while its TTL is **60 s**, so the key changes twice
> per TTL and every rotation costs a fleet-wide rebuild. Whether the bucket can widen (what
> actually moves in the concept build inside 60 s […]) is a measurement nobody has taken, and it
> is a strictly larger lever than this queue's, on the same artifact.

**This window inherited a built tree.** The prior latency window was killed mid-run by an API
infra error, leaving modified `feed.py` and `principal_independent_cache.py` and an untracked
gate file in the worktree. The re-staging directive says to treat that work as **untrusted**.

That is exactly how it was treated, and it matters for how the evidence below should be read:

- Every claim in the inherited comments was **re-derived from source in this window**, not taken
  on faith (§3). One of them was **wrong and is corrected** (§5).
- The red-first battery was **run from scratch here**, five mutations, each from a `cp` backup
  with every restore verified by `cmp` **and** `shasum` (§4). Counts are what pytest printed.
- Nothing was pre-registered about the build, because the build predates the window. What *is*
  pre-registered is the post-deploy check: `lat-p104-postdeploy-prereg.md`, committed with the
  code. Writing a "pre-registration" for work already done would be the failure the practice
  exists to prevent.

The parked item asked for a **measurement**. It does not need one. The concept build's
`now`-sensitivity is **enumerable** — four inputs, all readable — so it is settled by
enumeration, and the enumeration is then held true by an executing test rather than by this
paragraph.

## 2. The evidence, which was already paid for

No new production read was taken. LAT-P103's own BEFORE instrument is a natural experiment:
ten cold builds, ten distinct principals, ten unwarmed shapes, slug `ba3be25f`, 2026-08-27.

| | n | `x-feed-shared` | median `x-feed-elapsed-ms` |
|---|---:|---|---:|
| **REBUILT** the concept stage | **4** | `canonical_counts` | **2,481.99 ms** |
| REUSED the concept stage | 6 | `canonical_counts,concepts` | 1,295.07 ms |

`x-feed-cache: miss` 10/10. Two artifacts, one instrument, **one difference between their keys**:
`canonical_counts` carries no clock component and was reused 10/10; `concepts` carries a 30 s
bucket and was reused 6/10. The 1,186.9 ms gap independently reproduces LAT-P084's 865–1,249 ms
concept-stage cost from a different instrument.

## 3. The premise, enumerated rather than sampled — and re-verified here

The bucket may only be widened to a grid the build's `now` actually moves on. `now` enters
`_score_event_concepts` in exactly four places. Each was read in this window at the source:

| input | `now` granularity | verified at |
|---|---|---|
| `marquee_pin_state(key, now)` | windows open at UTC **00:00**, `whathit` expires at settlement + 36 h = UTC **12:00** | `app/utils/majors_calendar.py:104-111` |
| `_score_event_concept(c, now)` | `(start.date() - now.date()).days` — nothing finer | `app/routes/feed.py:8531` |
| `_concept_headline(c, now)` | `(start.date() - now.date()).days` — nothing finer | `app/routes/feed.py:8559` |
| `list_all_concepts(db, …)` | **takes no clock at all** | `app/routes/feed.py:8898` |

Finest boundary spacing across all four: **12 hours**. An hourly grid lands exactly on every one
of them, because `int(now.timestamp()) // 3600` turns on each UTC hour and 3600 divides both
86,400 and 43,200. `_resolve_concept_leader` / `_resolve_concept_champion` take no `now`; their
freshness is bounded by the TTL, which is unchanged.

**`time_bucket` has exactly one caller in the whole tree** (`grep -rn` over `app/`), so this
change cannot reach `canonical_counts` or anything else.

### Why staleness genuinely cannot move

An entry is served only while `age < TTL` **and** its key is still current, so staleness is
`min(TTL, bucket)`. Both TTL checks were read directly rather than assumed:

- L1: `principal_independent_cache.py:546` — `if (now - stored_at) > ttl_s: <miss>`
- L2 (Redis, LAT-P103): `:698-699` — `age_s = max(0.0, time.time() - stored_wall)`, `if age_s > ttl_s: <miss>`

Neither is a function of the key. So at any bucket `>= 60 s` the TTL is the binding constraint
and widening the key is **free**. That is the whole safety argument, and §4's M4 executes it.

### Why an hour and not 12 hours

Rebuild rate with `B >= T` is `1/T + 1/B`. At `T = 60`: an hour gives 0.01694/s, twelve hours
gives 0.01669/s — **1.5 %**, for a grid that stops being aligned the moment anything reads a
naive datetime. Not worth it.

## 4. RED-FIRST — five mutations, measured in this window

Each applied **alone**, from a `cp` backup, with the restore verified by `cmp` **and** `shasum`
against a pristine manifest before the next was applied. LAT-P100 lost an entire battery to
mutations silently stacking because its restore matched no pathspec (gotcha #51); the manifest
is the cheap defence against repeating it. Final restore confirmed byte-identical:
`feed.py 14ab5c36…`, `principal_independent_cache.py f4254a73…`.

| | mutation | result |
|---|---|---:|
| M1 | call site back to `_shared_time_bucket(now, 30)` | **2 fail** |
| M2 | `clock_bucket_s` returns the bare constant, clamp removed | **1 fail** |
| M3 | clock component dropped from `_concept_key` entirely | **1 fail** |
| M4 | L1 TTL check disabled (`if False and …`) | **1 fail** |
| M5 | a `"Starts in N min"` branch added to `_concept_headline` | **10 fail** |

- **M1** reddens the two route-level gates — two principals, two cold builds, 35 s apart, which
  is inside the TTL and outside the old bucket.
- **M2** is the one that matters for the *future*: `FEED_SHARED_BUILD_TTL_S` is a no-deploy
  runtime lever, and without the clamp the defect returns one env var later, silently. Nothing
  about a slower feed announces "someone raised the TTL past the bucket".
- **M3 and M4 are a pair.** M3 proves the clock component still does its remaining job (turn the
  key *at* a content boundary rather than a TTL after it); M4 proves the TTL still bites. Without
  both, "the key stopped churning" is indistinguishable from "nothing ever expires".
- **M5 is the load-bearing one.** It is the guard on the §3 premise: a minute-granularity branch
  added by a future author goes red *at the place the bucket width is justified*, rather than
  shipping an hour of stale text. It failed on the `starts-later-today` row **only** — which
  vindicates the gate file's own `CONCEPT_ROWS` note that a single far-off row misses it.

## 5. One inherited claim was wrong, and is corrected

The inherited gate file's RED-FIRST section predicted that M1 "takes the route-level headline
gate **and the key-stability gates** red". It does not. `test_the_key_component_is_stable_across_
a_full_ttl` calls `clock_bucket_s()` directly, so no call-site mutation can move it — only M2
can, and M1 measured **2 fail**, not 3.

It was a prediction that had never been executed. It is replaced in the file by the measured
matrix above. This is small, and it is recorded rather than quietly fixed because a gate file
whose own red-first note is aspirational is the exact artifact that decays into decoration.

## 6. Gates

- **Full backend suite:** see the READY token for the single run, unpiped, exit code read by
  value on the committed tree.
- **New gate file:** `tests/test_feed_concept_stage_key_bucket_p104.py` — **92 passed**, exit 0.
- **Siblings on the same module:** `test_feed_shared_build_survives_a_cold_worker.py` +
  `test_feed_shared_principal_independent_build.py` — **38 passed**, exit 0.
- **ruff: ZERO NEW.** Compared finding-for-finding against `git show HEAD:` for both touched
  source files. `feed.py` carries **12 pre-existing** findings, identical before and after; the
  cache module and the new test file are clean.
- **black: reported, not claimed clean.** `black --check` is **not** a CI gate here (absent from
  every workflow; `requirements.txt` pins only `black>=24.1.0`). Under local black 26.5.1 both
  `feed.py` and `principal_independent_cache.py` were **already dirty at base** — the reformat it
  wants in `feed.py` is in `_score_event_concepts` lines this change does not touch — so there is
  no regression, and reformatting either whole file would turn a 60-line diff into a thousand-line
  one. The new test file also does not satisfy 26.5.1, in the same `assert x, (msg)` construct as
  LAT-P103's already-shipped sibling gate file; it was left consistent with its stack-mate rather
  than churned to match a non-gating tool that master itself does not satisfy.
- **Frontend/native gates not run and not owed:** zero frontend files, zero iOS files.
- **Migration slot none; beat schedule unchanged; no config var changed at deploy.**

## 7. What is NOT claimed

- **No latency delta is claimed.** A paired before/after wall-clock read on this endpoint is
  confounded by Postgres buffer sharing (LAT-P100: 383.5 ms interleaved vs 1,034.5 ms paired on
  one shape, 2.7×, from read order alone). The graded claim is a header state.
- **The win is 2×, not more.** The fleet is 1 web dyno × `WEB_CONCURRENCY=2` = 2 worker
  processes, and the rebuild-rate halving is from `1/30 s` to `~1/59 s`. What generalises is the
  mechanism, not the multiplier.
- **This is not deployed.** The production bar is in `lat-p104-postdeploy-prereg.md` and is
  **owed** by the first window after this reaches a release, along with LAT-P103's own.
