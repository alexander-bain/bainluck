# Headline source ages and single-source marks

Fable: needed (reader-visible)

## Reader outcome

A source mark dates the price the game headline actually used, with the original
successful upstream read. A cache hit, database recomputation or publication
cannot make an old price look newly observed. A one-venue mark says `single`;
multiple contributors retain `blend` and name the actual weighted calculation.

## Change and boundaries

- Add `price_read` inside the existing source JSONB, bound to its exact value and
  contributing outcome versions. No column, index or migration.
- REST venue reads carry immutable witnesses only after their existing commit.
  Rollback drops pending witnesses. A reused Gamma response keeps its original
  receive time; all admitted inputs must match before the headline gets an age.
- Sportsbooks use the response receive time already passed by their producer.
- The atomic source update writes price and evidence together and preserves
  another source's entries. Identical recomputation retains the original read;
  changed values, versions or contributors lose that evidence.
- Reversed team/fighter views invert the bound price with the displayed value.
  The detail cache keeps its selected price and source mark together.
- Unknown ages remain absent. In particular, the cached Kalshi last-trade path
  has no retained original read time, as Speed confirmed; a book callback's time
  is not substituted. No worker-ws custody change is included.
- No pricing, cadence, throttle, retry, transaction boundary or Phase-2 query
  change. No manual stored-data repair or additional venue request.

## File and reader gates

Speed released the three writer files in #12581 comment 6832726720. Atlas
released the narrow events route call site in NOW comment 6846842954. Fable
accepted the old-reader compatibility evidence in #12581 comment 6829542855.
Build 5704 ignores the new keys; Builder C's corrected 1.0.7 replay pins `single`
and `blend`, with `blended` a negative control (6831193152).

## Validation and remaining delivery

Local validation after wiring: 96 focused source-read, real-poll, source-mark
and startup checks; 186 related writer/commit/rollback/trace checks; 25 real
PostgreSQL 17 checks including concurrent JSONB writes, unchanged observations,
changed input versions and rollback. The PostgreSQL gate caught and fixed
parentheses around a CASE expression before JSONB subscripting; its failed
receipt is retained. Assertions were not relaxed.

Final clocks, frontend build/typecheck and hosted CI remain publication gates.
Merge needs the bot, Fable's exact-head ACCEPT and the current NOW turn. Served
proof must show a live game's headline marks, both axes and cache/Refresh
behavior. Builder C owns opening a single and blended mark on the installed
phone build. Governor's after-deploy proof and #12658 keep their assigned
priority.
