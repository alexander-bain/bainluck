# The provider-anchor channel for `events` — design (#1946)

**Status: DESIGN ONLY. No code, no migration, no schema change ships with this document.**
Queue 365, lane1, 2026-08-17. Deliverable requested by the FABLE directive: (a) the schema
decision argued rather than asserted, (b) a migration-slot request to the Integrator, (c) how
ruling 048's bounding clause reads once the channel exists.

---

## 1. The finding this answers

Ruling 048 makes an explicit bargain: an id-less claim never absorbs, it CREATES, and the
resulting duplicates are an accepted cost **because** —

> *"id-keyed reconciliation drains the duplicate when an id arrives."*

Queue 364 built that reconciliation and then measured what it could reach. Production,
2026-08-17, all 500 unanchored rows:

| disposition | rows | meaning |
|---|---:|---|
| `NO_ANCHOR_CHANNEL` | **500** | the creating provider has no id column on `events` |
| `AWAITING_ANCHOR` | 0 | an id may yet arrive |
| `DRAINABLE` | 0 | an id arrived and a twin shares it |
| `ANCHORED_NO_TWIN` | 0 | an id arrived, no duplicate existed |

**500 of 500.** Not a backlog — a structural impossibility. `events` carries exactly three
provider-id columns:

```
external_id           String(100)   Odds API
espn_id               String(50)    ESPN
statpal_fixture_id    String(100)   StatPal
```

`event_registry._find_by_source_id` says so in a comment (*"Kalshi/Polymarket don't have direct
ID columns on events"*, returns `None`) and `_attach_claim` has no branch for either source, so
it silently does nothing. **499 of the 500 rows were created by Polymarket** (487 of them
`soccer_other`), inside twelve days, and the population is growing.

So the bounding clause has no arrival channel for the source generating 99.8% of its cost.
Scheduling a drain cannot fix this, which is why queue 364 refused to pretend otherwise and
escalated instead.

---

## 2. The decision: an anchors TABLE, not two more columns

### 2.1 The case for columns (the cheap option, and it is real)

Add `kalshi_id` and `polymarket_id` to `events`. It matches the existing shape exactly, needs no
join on a hot path, and `PROVIDER_ID_COLUMNS` already exists as the one place rails enumerate —
so `shared_provider_id_sql`, `shared_provider_ids`, the drain's census and
`event_absorption_guard._GUARD_COLUMNS` all pick the new providers up from a single edit. That
is not nothing; it is the whole reason the R6 module was written that way.

### 2.2 Why it is still the wrong shape — three reasons, in order of weight

**(a) The cardinality is wrong, and this is decisive.** A scalar column asserts *one id per
event per provider*. Neither provider is shaped like that:

* Kalshi's unit is a **market ticker**, not a game. One MLB game carries a moneyline market plus
  totals, spreads and player props — many tickers, all equally "the Kalshi id of this event".
  `FuturesMarket.event_id` is already the many-to-one link that exists because of this.
* Polymarket nests **sub-markets by `condition_id`** under a Polymarket event id (gotcha #18),
  and `market_metadata->>'polymarket_event_id'` already stores the outer one separately from the
  inner ones.

A column forces a choice of which ticker is THE id. Whichever is chosen, two rows for one game
can hold two *different* legitimate ids and fail to share one — the anchor arrives and the drain
still cannot see it. That is the same bug in a new column.

**(b) `events` cannot say WHEN an anchor arrived, and the drain needs to know.** There is no
`updated_at` on `events` (a standing project note). A column records that an id is present; it
cannot distinguish "anchored at create" from "anchored ten minutes ago by a late Polymarket
poll", and the second is precisely the event the reconciliation is waiting for. A row in an
anchors table has its own `first_seen_at` for free, which turns the drain from a full-table
census into a watermark scan over new anchors.

**(c) #1947 needs anchors to carry provenance, not just value.** Production holds three
`espn_id` values shared by genuinely different games. With a column, the collision is invisible:
two rows hold the same string and nothing records who claimed it or whether anyone disputed it.
With a table, a `(source, source_id)` that resolves to two events is a **queryable defect** —
and the corroboration arms added for #1947 can be recorded against the anchor rather than
recomputed from team labels every time.

### 2.3 The proposed shape

```sql
CREATE TABLE event_provider_anchors (
    id             BIGSERIAL PRIMARY KEY,
    event_id       INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    source         VARCHAR(32) NOT NULL,     -- odds_api | espn | statpal | kalshi | polymarket
    source_id      VARCHAR(200) NOT NULL,    -- ticker / condition_id / fixture id
    id_kind        VARCHAR(32) NOT NULL,     -- 'game' | 'market' | 'container'
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claim_context  JSONB                      -- provenance of the claim that attached it
);

CREATE UNIQUE INDEX uq_anchor_source_id ON event_provider_anchors (source, source_id, id_kind);
CREATE INDEX ix_anchor_event ON event_provider_anchors (event_id);
CREATE INDEX ix_anchor_first_seen ON event_provider_anchors (first_seen_at);
```

`id_kind` is load-bearing and is the part that makes (a) safe. **Only `id_kind = 'game'` may
anchor an absorption.** A Kalshi player-prop ticker and a Polymarket `condition_id` are `market`;
a Polymarket event id is `container`. Both are worth recording — they are how the anchor is
*discovered* — but neither asserts "these two rows are the same game", and a table that stored
them without saying which kind they are would re-create ruling 048's original defect with better
indexing. The unique index includes `id_kind` so a value can legitimately appear as both.

The three existing columns **stay**. They are read by too much live code to move in the same
change, and this design deliberately does not propose moving them. The anchors table is the
channel for providers that have none; unifying the other three is a later, separate, and
entirely optional step.

---

## 3. Migration-slot request to the Integrator

- **What:** one `CREATE TABLE` + three `CREATE INDEX` on a table that starts EMPTY.
- **Runtime:** effectively instant. Nothing is rewritten and no existing table is locked.
- **`CONCURRENTLY`: NO** — and deliberately not, which is the safe direction here. Gotcha #31
  bans it in Alembic because the release phase times out on large tables; on an empty new table
  a plain `CREATE INDEX` is the correct and fast choice.
- **Backfill: NOT in the migration.** Populating anchors from the three existing columns is a
  bounded task on the background queue, oldest-first, run after deploy. Putting a multi-hundred-
  thousand-row backfill in the release phase is how #31 happened.
- **Alembic revision id: ≤32 chars** (gotcha #1), psycopg2 not asyncpg.
- **Serialisation:** this must not land in the same cycle as another Alembic revision (CLAUDE.md
  never-parallelize). **The slot is what this document is requesting — lane1 has not created a
  revision file, precisely so that the Integrator can choose the cycle.**

---

## 4. How ruling 048's bounding clause reads once the channel exists

Today the ruling's bounding half is unexecutable prose. The amendment should be a **quotation of
a predicate**, not a re-description. Proposed text, to replace the bounding clause only:

> **Bounding clause (amended).** A duplicate is drained when two events share a provider anchor
> of `id_kind='game'` — that is, a row each in `event_provider_anchors` with equal `(source,
> source_id)` — **and** the pair satisfies the corroboration arms in
> `app/utils/event_merge_invariant.py` (matching participants, and a `commence_time` separation
> within `MAX_ABSORPTION_SEPARATION_SECONDS`). A shared anchor is *evidence* of identity and is
> not, on its own, proof of it: production holds `espn_id` values shared by genuinely different
> games (#1947).
>
> An event whose creating provider has no row in `event_provider_anchors` and no anchoring
> column is **outside** the bargain, not queued inside it. It must be reported as
> `NO_ANCHOR_CHANNEL` — never as "awaiting" — because a zero over rows that can never be
> reconciled and a zero over rows that are about to be say opposite things to an operator
> (gotcha #53).

In code, `shared_provider_id_sql` gains a sibling rather than a fourth OR-arm:

```sql
EXISTS (
  SELECT 1 FROM event_provider_anchors aa
  JOIN event_provider_anchors bb
    ON aa.source = bb.source AND aa.source_id = bb.source_id
   AND aa.id_kind = 'game' AND bb.id_kind = 'game'
  WHERE aa.event_id = a.id AND bb.event_id = b.id
)
```

and the existing three-column OR-chain is `OR`-ed with it during the transition, so no rail
loses coverage on the day the table lands.

---

## 5. What this does NOT decide, and who decides it

1. **Whether a Kalshi/Polymarket `game` anchor exists at all.** Both providers key on markets.
   Deriving a game-level id (e.g. the Kalshi game-ticker prefix, which the matching rail already
   parses) is a judgment about whether that prefix is reliably game-unique. It is testable
   against production and is the first thing to measure before any of this is built.
2. **Whether the three existing columns migrate into the table.** Recommended: not now.
3. **Whether the four MLB duplicate pairs from queue 364 become drainable.** They would not —
   they are refused on separation, not on anchoring, and that is #1947's open policy question.

## Evidence checked

- `app/models/models.py` — the three provider-id columns on `Event`, with their types
- `app/services/event_registry.py::_find_by_source_id` (returns `None` for kalshi/polymarket)
  and `::_attach_claim` (no branch for either)
- `app/tasks/reconcile_unanchored_events.py` — the four dispositions and `CHANNEL_LESS_SOURCES`
- `app/utils/event_merge_invariant.py` — `PROVIDER_ID_COLUMNS`, `shared_provider_id_sql`, and
  the #1947 corroboration arms added in queue 365
- production census, 2026-08-17 (queue 364): 500 unanchored, 499 Polymarket-created, 0 reconciled
- #1946, #1947, `docs/rulings/048-an-id-less-claim-never-absorbs.md`
- CLAUDE.md gotchas #1, #18, #31, #53; the never-parallelize rule on Alembic
