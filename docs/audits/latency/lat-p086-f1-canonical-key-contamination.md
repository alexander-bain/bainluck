# LAT-P086 F1 — `canonical_market_key` used as merge identity: the third and fourth sites

**Status:** FIXED on `program/latency-77` (one site repaired, one site deleted). Not yet deployed.
**Authority:** Fable directive 2026-08-24 item 1, Alex-reviewed. Removal of
`GET /api/futures/compare` was ruled by Alex on zero consumers.
**Measured:** production, 2026-08-24, read-only `POST /api/admin/db-query` and live HTTP.
**Precedent:** LAT-P038 / #1769, `app/routes/events.py:78-157`.

---

## 1. The identity, and why it cannot be one

`compute_canonical_market_key` builds `{sport}:{league}:{category}:{season}` — for example
`soccer:EPL:championship:2026-27`. It was built to count calibration cohorts. **There is nothing in
it that identifies a market**: not the name, not the source, not the external id, not the outcome
set. Two markets share a key when they are the same *kind of thing in the same season*, which is the
definition of a cohort and the opposite of the definition of a duplicate.

LAT-P038 established the consequence in one line: used as a merge identity, it *"does not merge
duplicates, it deletes the corpus."* `events.py` was fixed then. Two more sites were still doing it.

---

## 2. Site A — `GET /api/futures/compare`: DELETED

The route grouped every `FuturesMarket` sharing a `canonical_market_key` and merged their outcomes
into one "how do sources price this" comparison. Measured live before deletion — HTTP **200**, 0.60 s,
61 KB:

```
GET /api/futures/compare?key=entertainment::game_prop:2026
  source_markets ............ 449   (423 distinct names)
  sum of member outcomes .... 890
  outcomes RETURNED .......... 10
```

Members of that single "comparison" included *Will Jay Z release an album in 2026?*, *Will Justin
Bieber perform at the 2026 Todo Mundo no Rio music festival?*, *Taylor Swift pregnant by March 31?*,
*Trump declassifies new UFO files by December 31?*, *Dune vs Avengers: Highest Rotten Tomatoes
Score* and *Yellow Submarine vs. Power Rangers: Map 2*. The ten merged outcomes it returned:

    Yes · No · August 31 · June 12 · May 31 · April 30 ·
    Yellow Submarine · Power Rangers · Dune: Part Three · Avengers: Doomsday

Every Yes/No pair from 400+ unrelated binaries collapsed onto two rows, and the endpoint presented
an esports map name and a film title as competing answers to one question, each with a probability.

**Zero consumers.** Frontend, iOS, backend, docs and scripts grepped in both the master worktree and
this program worktree: no hits outside the route's own tests. Alex ruled removal over repair — there
is no threshold to tune when the merge identity is wrong and nobody is asking.

Removed: the `@router.get("/compare")` handler `compare_futures_sources` (91 lines) and
`_avg_probability` (10 lines, sole caller). Kept: `_outcome_merge_key` and `_GARBAGE_OUTCOME_RE`,
still used by the cross-source timeline. The payload is preserved at
`docs/audits/latency/lat-p086-compare-specimen.json`, which is now the only record of what the
endpoint returned.

Pinned by `backend/tests/integration/test_futures_compare_removed.py`. Note the assertion shape:
with `/compare` unregistered, `GET /api/futures/compare` falls through to
`GET /api/futures/{market_id}` and 422s on **integer parsing of the path**, whereas the old route's
own 422 blamed `query.key`. A bare status check could not tell "deleted" from "still validating", so
the tests read the failure `loc` and `type`.

---

## 3. Site B — `build_league`'s sibling delete: REPAIRED

`app/routes/league_futures.py` kept `seen_canonical: dict[str, dict]` keyed on
`market.canonical_market_key`, skipped any later row sharing a key, and — when a later row had more
outcomes — removed the earlier one with

```python
sections[old_section] = [m for m in sections[old_section]
                         if m.get("canonical_market_key") != ck]
```

Three separate defects, only the first of which the directive named:

**B1 — the identity.** One key holds unrelated markets. On the EPL page, measured 2026-08-24 over
the route's own 200-row pool:

| | rows |
|---|---|
| pool rows | 200 |
| reaching the dedup (tier not in 1/2/4) | 168 |
| of those, carrying a canonical key | 80 |
| distinct canonical keys among them | 8 |
| **deleted by the canonical dedup** | **72** |

`soccer:EPL:championship:2026-27` alone held 23 of them within that pool — and **29** in the full
open population (1 at tier 3, 28 at tier 5), spanning three different countries' Premier Leagues:

```
59164820  t3  kalshi      EPL Playmaker Award
12727863  t5  polymarket  EPL: Next Chelsea Manager?
57774279  t5  kalshi      EPL: Team Points
58904929  t5  polymarket  Egypt Premier League: 2026-27 Runner-Up
59156924  t5  polymarket  English Premier League: Top Goalscorer 2026-27
59516454  t5  polymarket  Ukrainian Premier League: 3rd Place Finish 2026-27
59516509  t5  polymarket  Premier League: Teams relegated (2026-27)
  ... 22 more, every one a distinct question
```

Corpus-wide the identity's failure rate is stark — **13,789 keyed dedup-eligible open rows collapse
onto 241 keys**: 13,548 rows deleted, 13,303 of them carrying a distinct name, worst key
`soccer::championship:2026` at 8,749 rows / 8,741 names. That is the identity's error rate, *not* any
single page's loss, because `build_league` only ever dedups inside the league it was asked for.

**B2 — the removal filter deleted every row carrying the key, not the row being replaced.** The list
comprehension filtered on `!= ck`, so replacing one row swept out all its keyed siblings from that
section. Invisible only because the skip arm had already suppressed them.

**B3 — the deletion crossed sections.** The key spans tier 3 and tier 5. The pool is ordered
`market_tier ASC`, so "EPL Playmaker Award" (tier 3) was appended to `awards` first, and the first
richer tier-5 row then removed it from `awards`. A manager market deleted an award.

### The fix, following `events.py` verbatim

`_normalize_futures_dedup_key` is imported from `app.routes.events` and used unchanged. It returns
`matchup:{teams}:{tier}` or `name:{folded name}:{tier}`, so it keys on what the market *is*. Removal
is now by row id:

```python
dedup_key = _normalize_futures_dedup_key(market)
existing = seen_dedup.get(dedup_key)
if existing is not None:
    if len(outcomes_data) <= len(existing["top_outcomes"]):
        continue
    old_section = existing["section"]
    sections[old_section] = [
        m for m in sections[old_section] if m["id"] != existing["id"]
    ]
seen_dedup[dedup_key] = market_data
```

That fixes B2 (one row, by id) and B3 for free (the key carries `market_tier`, so a cross-tier
collision is impossible by construction).

**Do not relocate `_normalize_futures_dedup_key`.** `test_search_futures_dedup_identity.py` pins it
by `inspect.getsource`.

Pinned by `backend/tests/integration/test_league_futures_dedup_identity.py` (8 tests), which asserts
both directions per gotcha #43: the six-row EPL specimen renders all six *and* a genuine
cross-source duplicate ("NBA Championship Winner" / "2026 NBA Champion") still collapses to one row,
with an innocent row between them surviving the survivor-removal.

---

## 4. Not fixed here, and named so it is not lost

**The deletions are invisible to `section_counts`.** The tier resolver runs over `sections` *after*
this loop and reports `total = shown + resolved_skipped`. Canonically-deleted rows were subtracted
before anything counted them, so the envelope published a denominator smaller than the truth — a
ruling 025 clause 3 silent truncation. Repairing the identity removes most of the deletions but not
the blind spot: a row dropped by the *name* dedup is still not in either term. That is a separate
lever and belongs to whoever owns the league-page envelope.

**Tiers 1, 2 and 4 never reach this dedup at all.** `_assign_section` routes them to `championship`
and `continue`s into `championship_census` first. This is why the directive's JAY-Z/Bieber ids
(8430959, 13791149, 13792932, 20271688, 22915647 — all tier 2, verified live) are a real specimen of
this defect whose home is site A, not site B, and it is why the first draft of the league-page test
came out red for the wrong reason. `TestTierOneTwoFourNeverReachTheDedup` is in the suite as an
explicit scope statement.

---

## 5. Verification owed after deploy

- `GET /api/futures/compare?key=entertainment::game_prop:2026` → 422 on `path.market_id`, not 200.
- `GET /api/leagues/soccer_epl` → the awards section still carries "EPL Playmaker Award" while the
  tier-5 manager and runner-up markets render in their own sections; count the rendered rows against
  the 168 that reach the dedup.
