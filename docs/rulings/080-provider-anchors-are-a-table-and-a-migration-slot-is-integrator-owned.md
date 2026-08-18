# RULING 080 — Provider anchors are a TABLE, and a migration slot is an integrator-owned artifact

date: 2026-08-18
author: Alex
issues: #1946, #1798

## The ruling

Two things, ratified together because the second is what makes the first buildable.

**1. `event_provider_anchors` is RATIFIED as a table.** The design in
`docs/event-provider-anchor-channel-1946.md` is accepted as argued: a child table keyed
`(event_id, provider, id_kind, provider_id)`, not two more scalar columns on `events`. The
cardinality argument is the deciding one — Kalshi keys on market *tickers*, Polymarket on nested
`condition_id`s under an outer event id, so a scalar column forces a choice of which id is THE id,
and two rows for one game can then hold two *legitimate* non-matching ids. The anchor arrives and
the drain still cannot see it, which is the exact failure (#1946) the channel exists to end.
`id_kind` (`game` / `market` / `container`) gates which anchors may license an absorption.

**2. A migration slot is written by the INTEGRATOR, as an integrator-owned artifact.** A lane
REQUESTS a slot; it does not take one. The lane's build **arms** when the slot is written, and not
before. Queue 365 was right to design and stop.

## Why the slot is owned there and nowhere else

Alembic has a single linear head. A slot is not a scheduling courtesy — it is an exclusive write to
a shared serialization point, and it is the one artifact where two lanes each doing the obviously
correct thing produces two heads and a blocked release for everyone. The Integrator is the only
role that sees every lane's branches at once, so it is the only role that can say "yours is next"
truthfully.

Writing it down as an artifact rather than a conversation matters for the same reason ruling 028
exists: a slot conveyed in prose in a report is a slot that a lane can believe it has. The artifact
is the grant.

## The four conditions carried into the build

Inherited from the Option-D grant already written in `PROGRAM-LATENCY-NEXT.md`, and they bind here
too:

1. **Table-only migration.** Create the table and its constraints; nothing else rides along.
2. **The GIN/large index goes out of band** — gotcha #31. `CREATE INDEX CONCURRENTLY` inside a
   migration hangs Heroku's ~5-minute release phase and takes the site down; it caused the May 22
   outage. And note the agent-side constraint: psql/TCP 5432 egress is blocked from a session, so
   the out-of-band index is an **Alex action**, not something the lane can quietly do later.
3. **Backfill is a task, never a migration.** A release phase is not a place to iterate rows.
4. **Revision id ≤ 32 characters** — gotcha #1.

## What this does NOT license

Ratifying the table does not ratify a *use* of it. An anchor row is evidence that an id was
observed, and ruling 048 still governs what an id may do: arriving in this table does not by itself
license an absorption, and ruling 079 still forbids admitting a refused population in bulk once the
channel exists. The channel ends "we cannot see the id"; it does not begin "the id is enough".
