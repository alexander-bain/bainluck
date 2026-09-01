# Q067 — why every MLB game exists twice, and why one of the twins ends in a tie

**Pillar:** TRUTH. **Ship:** a finished baseball game never shows as a tie.
Measured against production 2026-09-01. All queries read-only via `/api/admin/db-query`.

---

## 1. The writer, and the exact reason dedup missed

**Dedup did not miss. `_find_by_structured_match` was never reachable, by design, for
either of the two providers that create these rows.** The cert must say this, because the
obvious "add a uniqueness check" fix is the one thing ruling 048 exists to forbid.

The chain, each link verified:

1. **StatPal's season-schedule sync creates the first row.** `app/tasks/statpal_sync.py:191`
   passes `schedule_derived=STATPAL_LISTING_IS_NOT_A_DEREFERENCE`, which is a named
   **`False`** (`event_registry.py:241`). ~7 days before first pitch, no row exists, so it
   CREATEs. Correct — there was nothing to match.

2. **Ruling 048's gate is on REACHABILITY, not on the match.** `event_registry.py:371`
   returns `None` *before* the matcher is called for any unanchored claim. The matcher the
   directive expected to fire is never invoked.

3. **The Odds API creates the second row, 5 days later.** `app/tasks/odds_polling.py:805`
   (and three sibling call sites) pass `schedule_derived=ODDS_LISTING_IS_NOT_A_DEREFERENCE`
   — also a named **`False`** (`event_registry.py:145`). Step 1 misses (the id is new),
   Step 2 misses, Step 3 is gated off. It CREATEs. **Two rows.**

4. **Step 2 structurally cannot join them.** The anchor channel is ruling 048 *arm A* — a
   **shared** id. StatPal's fixture id and the Odds API's `external_id` are two different
   providers' ids for one game, so there is nothing shared to join on. Arm A can only ever
   re-find the *same* provider's id.

5. **ESPN is the only cross-source joiner, and it can only pick one.** `espn_helpers.py:769`
   passes `schedule_derived=True`, so ESPN alone reaches `_find_by_structured_match`. Both
   twins sit at an identical `commence_time` with byte-identical names, so both name-match;
   the matcher returns exactly one. **The other twin never receives an `espn_id`.**

6. **No `external_id` ⇒ no odds snapshots, ever.** Verified: event 15291461 has **0**
   `odds_snapshots`; its real twin 15298071 has **2,321**.

7. **The staleness closer turns that into a tie.** `detect_and_close_stale_events`
   (`odds_polling.py`) sees `total_snapshots == 0`, takes the `no_odds_data` branch, writes
   `status='closed'` — **and never touches scores.** Whatever the row holds becomes its
   final. 15291461 froze at **1-1**. The real game finished **1-2**.

**And the drain that would reconcile the twins does not exist.** `_tag_duplicate_of`
(`event_registry.py:599`) says so in its own docstring: *"This is a LABEL, not a merge …
the drain that consumes these tags is #1946 Item 8 and does not exist yet."* It also only
fires on a same-provider anchor collision, so it would never have fired on this pair.

---

## 2. The directive's `DATE(commence_time)` question — YES, and it is worse than a grouping bug

There is no `DATE()` grouping in the matching predicate (`_find_by_structured_match` uses a
`BETWEEN ±28h` window). But there is one in the **lock**, `event_registry.py:672`:

```python
lock_key = hash((sport_id, commence_time.date().isoformat())) & 0x7FFFFFFF
await session.execute(_text(f"SELECT pg_advisory_xact_lock({lock_key})"))
```

Two independent defects in one line:

- **It is keyed on the UTC calendar date**, so two claims for one Pacific-evening game
  whose times straddle UTC midnight take *different* locks — exactly the boundary the
  directive identified.
- **`hash()` on a `str` is salted per process** (PEP 456) and `PYTHONHASHSEED` is **not set
  on Heroku** (checked). Three interpreters, same input: `1017695454`, `405647744`,
  `1382534938`. The docstring claims this serializes *"ESPN sync on realtime, Odds API on
  background"* — different processes. **This advisory lock has never serialized anything
  across workers.**

**Deliberately not fixed in this commit.** Making the lock actually lock introduces real
cross-process serialization on a hot ingest path (contention risk). That is its own
attended change with its own cert, and it does not ride this ship (THE RIDER RULE).

---

## 3. The escalation the directive asked me to size — it inverts

> *"how many NON-orphan closed events in no-draw sports hold 0-0 or an equal score, and how
> many futures_outcomes are graded on them, and how many of those are stamped game_score?"*

**Reading (a) is correct, and it is large.**

| | events | outcome rows |
|---|---|---|
| Terminal equal-score finals, draw-impossible-or-mixed sports | **130** | 3,833 graded |
| …on **orphan** rows | 52 | — |
| …on **real** rows (`external_id` present) | **78** | — |
| `game_score` + `box_score` (**not overwritable**) | 9 | **354 — all on real rows, 0 on orphans** |
| `pass2_guess` + `pass2_loser` | 25 | **248 real + 4 orphan** |

Fable's count of **4** orphan-bound guess-family outcomes is exactly right. The real-row
exposure is **602 outcome rows** — ~150× larger — and **the merge does not fix any of it,
because those rows are not duplicates.**

**Worst single specimen — 12080413**, Athletics @ Toronto Blue Jays, 2026-03-28, MLB
regular season, frozen at **7-7**: 189 `game_score`/`box_score` + 103 guess-family
outcomes, **0 authoritative**. `espn_id` NULL, `completed_at` NULL,
`win_probability_sources` NULL, 14 odds snapshots → closed via `all_bookmakers_stale`. It
is **not** a duplicate: its ±28h neighbours are the other two games of the series.

14877917 NYY@BOS (the row the directive flagged) is the same class: real row, 0-0,
`completed_at` set, 17 score-graded outcomes against 409 authoritative ones.

**This is its own issue and it outranks the merge**, exactly as the directive pre-committed.

**Duplicate-group census, independently reproduced:** ~**1,743** has-id/no-id groups
(Fable: 1,748) — corroborated by a different query shape.

---

## 4. What shipped in this commit

- `backend/app/utils/impossible_final.py` — a rules-based, tri-state draw-capability
  predicate. Narrow on purpose: NFL/CFL ties, spring-training ties, NCAA-baseball ties and
  Allsvenskan ties are **real results**, and a guard that fires on them gets muted. Unknown
  sports return `None` ("no claim made"), never `True`.
- `detect_and_close_stale_events` — **both** close paths now refuse to let an impossible
  score stand: the event still closes, but the scores are written `NULL`. Same move
  `derive_completed_at` makes four lines below, for the same stated reason: *a visible gap
  a repair can fill beats a plausible-looking wrong value nothing will question.*
  `game_state_backfill` can fill a NULL; it has no reason to revisit a confident 7-7.
- `backend/tests/test_impossible_final_guard.py` — 43 tests, behavioural (not
  `inspect.getsource`), no clock anchor.

**Red-first proof.** Both call sites removed in an rsync copy → exit **1**, 2 failed /
41 passed; the two failures are the two close paths, and the "real result" and "NFL tie"
controls stay green (so they are controls, not co-firing).

---

## 5. What I did NOT do, and why

- **Item 2, stop new duplicates.** Cannot be done by loosening absorption — Alex REJECTED
  that (gotcha #32 amendment: *"BUILD THE CHANNEL, loosening absorption REJECTED"*). The
  real fix is the reconciliation drain, #1946 Item 8. That is a program, not a session.
- **Item 3, merge ~5,000 events.** A data migration across the 10 child FK tables in
  `app/utils/event_fk_inventory.py` (3 CASCADE, 7 NO ACTION). SEQUENCE.md hard rule: no
  migrations in unattended queues.
- **Item 4, repair the derived ties.** Same gate — and now correctly re-scoped: 130 events,
  of which **78 are not orphans** and need a score backfill, not a merge.

The guard stops the bleeding. It does not clean the 130 rows already written.
