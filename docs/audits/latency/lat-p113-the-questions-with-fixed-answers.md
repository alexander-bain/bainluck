# LAT-P113 — the three questions with fixed answers

**Pillar:** DISCOVER · **Ship:** opening Discover on a brand-new install stops
spending most of the request loading personalization the server then throws
away.

Cycle 85. Ran from Fable's runner directive
`runner-inbox/latency/018-coldpath-conveyor.md`, staged under Alex's standing
authorization. Identity `LAT-P113-20260828-w5434`. Branch `program/latency-98`,
cut from **current master `f0b512b8`** — not stacked on `-95`/`-96`/`-97`, all
three of which are open and unmerged.

The item was **named by the predecessor**: LAT-P112 closed by parking P112-2 and
refilling the conveyor to take it. The queue head was otherwise empty.

---

## 1. What was measured before touching code

Production, deployed slug `f0b512b8`, uptime 8,018 s at first probe — well past
the post-deploy window, so none of this is the reading-a-warm-slug artifact
(`reference_post_deploy_latency_not_evidence`). Native Discover first-paint
shape, `GET /api/feed?limit=50&event_pct=0.15`, one **fresh `x-session-id` per
request** — i.e. a brand-new install, six times.

| run | `x-feed-cache` | total ms | `personalization` | `cache_shared_hit` |
|-----|----------------|---------:|------------------:|-------------------:|
| 1 | `shared_hit` | 48.75 | **40.36** | 8.35 |
| 2 | `shared_hit` | 46.91 | **40.20** | 6.67 |
| 3 | `shared_stale_hit` | 23.14 | **15.22** | 7.88 |
| 4 | `shared_stale_hit` | 42.29 | **34.77** | 7.46 |
| 5 | `shared_stale_hit` | 46.64 | **38.65** | 7.94 |
| 6 | `shared_hit` | 30.00 | **21.32** | 8.62 |

**`personalization` is 66–86 % of the entire request** — p50 **36.7 ms** of a
**44.5 ms** total. The whole remainder is an ~8 ms shared-cache read. Every one
of the six took the LAT-P089 inert-principal share, which is the point: the
context is loaded, compared to a default, found equal, and **discarded**.

🔴 **This is a bigger finding than the parked item claimed.** P112-2 described
~200 ms on a *cold worker* with a ~17 ms steady state, and parked it as "an
order of magnitude below" the hole it was found next to. On the warm,
steady-state, cache-hit path — the path a brand-new install actually takes —
personalization is not a tail, it is **the request**.

---

## 2. Where the 36.7 ms goes, and why it is not the queries

`_load_personalization_context` issues **seven sequential** `await db.execute(...)`
round trips for a session-only principal. They are sequential, not parallel: one
`AsyncSession` is not safe for concurrent use, so there is no `gather` available.
(The docstring called them "parallel-ish". It was describing an intention.)

Server-side execution for a principal the database has never seen, EXPLAIN
ANALYZE via `/api/admin/db-query`, same slug, same day:

| query | server-side |
|---|---:|
| `discover_interactions` category/action aggregate (30 d) | **0.877 ms** |
| `discover_interactions` recent-items aggregate (14 d) | **3.408 ms** |
| `user_seen_markets` (48 h) | **0.046 ms** |

Roughly **5 ms of server work inside a ~37 ms stage.** The remaining ~31 ms is
per-round-trip overhead. **The stage is round TRIPS, not work** — which is what
makes the count the thing worth attacking, and the thing worth guarding.

### The three that could never have returned anything

When `user` is `None`, three of the seven were:

```python
favorites_query = select(UserFavorite).where(False)
prefs_query     = select(UserPreference).where(False)
pins_query      = select(UserPin).where(False)
```

Not "usually empty" — **empty by construction.** Production's own planner says
so, and it is worth quoting because it removes the last doubt that these were
doing something:

| statement | plan | exec |
|---|---|---:|
| `SELECT * FROM user_favorites WHERE false` | bare `Result`, **no table access** | 0.016 ms |
| `SELECT * FROM user_preferences WHERE false` | bare `Result`, **no table access** | 1.225 ms |
| `SELECT * FROM user_pins WHERE false` | bare `Result`, **no table access** | 0.024 ms |

They cost ~nothing to **run** and one full round trip each to **ask**. And by
LAT-P089's own census the principal asking them is very nearly the whole
population of cold opens: **two users have EVER recorded a Discover
interaction.**

---

## 3. The fix

Skip them. Not filter them — skip them. **7 → 4 round trips** for an anonymous
principal; **7 → 7, unchanged**, for an identified one.

The claim being made is deliberately narrow and needs no correctness argument
beyond itself: *do not ask a question whose answer is fixed.*

### What was deliberately NOT done

**LAT-P089's inert-principal share is untouched.** It still tests structural
equality against a default `PersonalizationContext()` rather than a bespoke
"has this session any interactions" probe. LAT-P089 chose that deliberately, so
that a personalization field added later is covered without anyone remembering
a predicate, and so that anything uncomparable fails CLOSED. That reasoning is
sound and this cycle does not re-litigate it.

It would have been easy to go further and short-circuit the whole load behind a
cheap `EXISTS`. That is **parked P113-1**, with the reason it was refused: it
adds a round trip for the *non-inert* principal, and the non-inert principal is
essentially Alex.

---

## 4. Gates

* **Guard test:** `tests/test_feed_personalization_roundtrips_p113.py`, 8 tests.
  It asserts the count **exactly** (`== 4`), never as an upper bound — a `<= 7`
  bound stays green through the exact regression it exists to catch.
* **RED-proven 8 ways**, each mutation applied ALONE from a `cp` backup, every
  restore verified by **both `filecmp` and `sha256`**, harness **refuses** a
  pattern matching other than exactly once. Registered in
  `scripts/evals/scan_mutation_residue.py`; residue scan **CLEAN**, exit 0.

🔴 **M3 survived the first battery, and the survivor was the finding.** M3
neutered the pins predicate to `where(False)` *inside* the authenticated branch
and all seven tests stayed green. Cause: the test's session mock routes results
by **table name**, so a query with the right table and a dead predicate is
indistinguishable from a correct one — and no in-memory fixture can fix that,
because a mock does not evaluate SQL. The behavioural test therefore proves less
than it appears to, which is now written into the test file rather than left for
the next reader to discover.

The repair was **not** a bespoke assertion for M3. The constant-false property
was widened from the anonymous path to **both** principals — the general clause
instead of the case (doctrine 081: the sentence that survives deleting its case).
Asking the database a question whose answer is fixed is never right here, for
anyone. That kills M3, and it will kill the next one of its shape.

Second battery: **8/8 killed**, exit 0, final restore VERIFIED by sha256.

* **ruff: ZERO NEW.** `feed.py`'s finding set is **byte-identical** to master's
  own copy (12 pre-existing, compared set-to-set and not by count). The three
  new/changed script and test files: *All checks passed*.
* **black:** new files formatted. `feed.py` deliberately **not** — master's copy
  is not black-clean and reformatting it would bury a 30-line change in a
  whole-file diff (`reference_black_reformats_whole_file`).
* **Collect count:** master measured **21,057** in a throwaway worktree at
  `f0b512b8` — independently reproducing LAT-P112's figure for the same master.
  Branch is expected at **21,065 (+8)**, which is the new file exactly.

---

## 5. Parked

* **P113-1 — the `EXISTS` short-circuit, refused with its reason.** The three
  remaining `discover_interactions` reads are all subsets of one 30-day window;
  a single `EXISTS` probe could prove all three empty and replace them, taking
  an anonymous open from 4 round trips to 2. **Refused here because it costs the
  non-inert principal an extra round trip, and that principal is Alex.** A
  version gated on `user is None` avoids that, at the price of a fourth spelling
  of "is this principal interesting" in one function. Worth doing deliberately,
  not as a rider.
* **P113-2 — the loader's round trips cannot be parallelised as written.** Six
  of the seven are independent, but they share one `AsyncSession`. Real
  concurrency needs separate connections, which is a pool question, not a feed
  question.
* **P113-3 — the mock-routes-by-table-name weakness is not local to this file.**
  `_seeded_session` in `test_feed_inert_principal_share_p089.py` has the same
  shape and the same blind spot. Any test in this family that believes it is
  checking a predicate is checking a table name.

---

## 6. Post-deploy bar, pre-registered

Registered here **before** the branch is merged, so it cannot be chosen after
the fact.

* **PRIMARY.** Re-run the exact §1 probe — six fresh `x-session-id`s at
  `/api/feed?limit=50&event_pct=0.15`, reading `X-Feed-Stages`. The
  `personalization` stage p50 must fall from **36.7 ms** to **< 26 ms**. That
  is a deliberately conservative bar: 4/7 of 36.7 is 21 ms, and the three
  removed statements are the *cheapest* of the seven server-side, so a
  proportional prediction is optimistic. A reading at or above 36.7 ms means
  the round-trip model is wrong and the finding needs re-deriving, not
  re-quoting.
* **GUARD (must NOT move).** `x-feed-cache` must still report
  `shared_hit`/`shared_stale_hit` on those same six requests. If a fresh session
  starts reporting `miss`, the LAT-P089 share has stopped firing — the context
  is no longer default-equal — and this change must be reverted. That is the
  one way this fix could make things dramatically worse rather than slightly
  better, so it is graded, not assumed.
* **NOT CLAIMED.** No effect on the identified principal, by construction and
  by test. No effect on any cold *build* — this is the inert-share path, which
  is already a cache read. And no needle movement is predicted (see §7).

---

## 7. The needle

**Opening read REFUSED** — `LAT-P113-open`, slug `f0b512b8`, exit code **1**
read by VALUE. Only **2 of 7** member paths produced a cold sample (floor 4) and
only **2 of 3** graded surfaces (Discover open missing entirely). Raw-pool
cross-check 204.0 ms over n=11; `my_stuff_stats` 16.0 ms, `search_cold`
332.0 ms.

🔴 **This is the fifth refusal running, and it refuses for exactly the reason
LAT-P112 diagnosed:** all four `/api/feed` members produced zero cold samples,
because the warm rails work during the hours a human is at a keyboard. Without
LAT-P107's floors the run would have published a two-member median.

**This ship should not be expected to move the needle, and the reason is
structural rather than an excuse.** The needle measures *cold* samples. This fix
improves the **warm** path — the `shared_hit` a brand-new install actually gets.
The instrument, by construction, discards precisely the samples this cycle makes
faster. The number to re-read after deploy is the one in §6, not the needle.
