# #5971 — the clock correction that did not carry its provenance

live/204, read in-command **2026-09-13 19:28Z / 12:28 PT**.

## The row refutes itself, and the witness is a column

`SELECT ... FROM events WHERE id = 15310688` (`BEFORE-15310688-value-and-provenance-disagree.json`):

```
commence_time        = 2026-09-13 18:13:40+00:00   <- ESPN's clock
commence_time_source = odds_api                    <- not ESPN's stamp
espn_id              = 182677
```

The value is ESPN's and the provenance says The Odds API. Decidable from the row alone with
no ground truth — the same family as gotcha #46.

## Why that pair, and not a race, is the cause

`event_registry.commence_time_write_authorized` reads the **stamp**, never where the value
actually came from. So on this row:

| current stamp | incoming | same-record? | verdict |
|---|---|---|---|
| `odds_api` | `odds_api` | yes (q066b) | **AUTHORIZED** — writes 18:00 back |
| `espn` | `odds_api` | sources differ | refused |

The Odds API publishes a whole tennis day at one session-start default before an order of
play exists and staggers real times later — that mechanism is `commence_time_write_authorized`'s
own docstring, measured 2026-09-01. So the poll is not misbehaving; it is revising its own
record, correctly, onto a row whose stamp never told it ESPN had spoken.

Measured oscillation (live/203, 26 samples, one command per sample reading our row and ESPN's
listing together): **18:00:00 → 18:15:00 → 18:00:00 → 18:15:00 → 18:13:40 in seventeen minutes.**

## Which writer is which — ruled out by the stamp, not guessed

Every rail that writes `events.commence_time` (`/usr/bin/grep` over `backend/app/`):

| rail | stamps | verdict |
|---|---|---|
| `espn_helpers` ×2 (main ESPN board) | `espn`, and refuses `statpal` | not reached — 0 tennis rows stamped `espn` |
| `anchor_schedule` | `espn`, REFUSED_STATPAL | same |
| `statpal_sync` ×3 | `statpal` | ruled out — stamp would read `statpal` |
| `schedule_coverage` | REPAIR_SOURCE | ruled out |
| `event_registry._update_fields_by_priority` | `identity.commence_time_source or claim.source` | **the 18:00 writer** |
| `espn_sync` tennis authority | **nothing** | **the 18:15 writer** |

The tennis path is the only rail in the codebase that moves the value and leaves the stamp.
That is #5324's shape on a second column: tennis reaches a different function and never
adopted what the board loop already does.

## Reach

`BEFORE-reach-tennis-provenance-census.json`, tennis rows with a start in the last 7 days:

```
polymarket          1795 rows,   0 anchored
kalshi               653 rows,   0 anchored
odds_api              26 rows,  26 anchored   <- the whole population this fix touches
kalshi_occurrence      7 rows,   0 anchored
```

**26 of 26 anchored tennis rows carry the defective pair.** Zero carry `espn` (the stamp has
never been written) and zero carry `statpal` (so the StatPal refusal ships inert, by
measurement, and is written anyway because adding the stamp without it would newly move a
column ESPN has never held here).

## Reader cost

`Since Start` filters on `commence_time`, so the first twelve minutes of the US Open men's
final left the chart while the match was still being played — ux/1239's two shots bracket it
(18:04Z axis 11:00→11:04; 18:17Z axis 11:13→11:17), and all 16 points were still stored.
No backfill is owed; only the window moved.

## Honest limit on tonight's production receipt

`tennis_espn_sync` at 19:25:36Z reports `anchored: 0` — the US Open is over and the board is
between tournaments, so the counter `commence_writes` reads 0 for reasons that have nothing to
do with this change. 53 ATP/WTA rows carry starts from 20:00Z tonight, so a real counter is
reachable after the release; until one exists the ship is deployed, not proved.
