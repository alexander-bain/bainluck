# RULING 117 — The clock-task cutover is MEASURE-THEN-DECIDE: no coverage change to a live producer during a freeze, and the decision comes back carrying the number its own gate produced

date: 2026-08-21
author: Fable (directive 2026-08-22, pasted and reviewed by Alex; decided on the calibration lane's own framing)
issues: #1912, #1544, #2076
supersedes nothing; **extends** ruling 066 (a deferred read owes a receipt) and ruling 075 clause 2

## The ruling

CAL-P086A shipped a winner-proof gate on resolved-writes and deliberately did **not** take
codex's stronger `[P0]` fix-sketch — *"stop the generic clock task resolving prediction-market
sources"*. It banked that as a ruling owed to Alex. This is the ruling, and it ratifies the
deferral:

1. **The cutover is measure-then-decide, not decide-then-measure.** `_mark_resolved_impl` keeps
   its current coverage. No producer loses rows on an estimate.
2. **No coverage change to a live producer during a deploy freeze.** A freeze exists so that
   something can be measured on a stable subject; a coverage change is the one edit guaranteed to
   move the subject.
3. **The number that decides it is already specified, and the gate is what produces it.** After
   the gate deploys, ~48 h of `market_metadata.resolution_gate` stamps grouped by producer is the
   exact count — not a sample, not an extrapolation.
4. **The decision comes back through Fable carrying that number.** Not through whichever window
   happens to be holding the lane when the 48 h elapse.

**The deferral is only legitimate because it shipped the counter.** Deferring a P0 to make it
countable first is correct; deferring a P0 and writing down that someone should count it later is
the failure this program has a dozen names for. The distinguishing test is mechanical: *did the
deferring change make the number obtainable by a query that did not exist before it?* Here it did.

## The exact receipt this deferral owes (ruling 066)

Not "measure it later". This, and the exit condition is a value, not a feeling:

```sql
SELECT market_metadata->'resolution_gate'->>'task'      AS producer,
       market_metadata->'resolution_gate'->>'reason'    AS reason,
       COUNT(*)                                         AS n
FROM futures_markets
WHERE market_metadata ? 'resolution_gate'
  AND (market_metadata->'resolution_gate'->>'at')::timestamptz > now() - interval '48 hours'
GROUP BY 1, 2
ORDER BY 3 DESC;
```

* **Starts** when the branch carrying `app/utils/resolved_write_gate.py` is DEPLOYED — not when
  it merges, and certainly not now. The gate is behind an unmerged branch behind a freeze, so the
  48 h clock has not started and no window may report otherwise.
* **Ends** at the first read taken ≥48 h after that deploy.
* **Decides:** the share of `resolution_date_elapsed_no_venue_result` rows attributable to
  `_mark_resolved_impl` on prediction-market sources. That share is the cutover's whole case.
* **Addressee:** Fable. A deferral with no addressee is an abandonment with better manners.

## Why this and not the stronger fix

Codex is not wrong that a task with no winner evidence should not be minting `resolved` on
prediction-market rows. The disagreement is about **order**, and the order matters here for three
reasons that are specific rather than general caution:

**The stranding hazard is real and already documented.** Gotcha #33: a market stuck in `open`
blocks every downstream pipeline that keys on `resolved` — `cal_prob`, `is_winner`, candlestick
backfill, all of them. So "stop resolving these" is not a no-op that merely withholds a bad row;
it is a coverage change whose own failure mode is a second, quieter backlog in a different state.
Trading a counted problem for an uncounted one is not obviously an improvement, and nobody has
measured which is bigger.

**The population was, until this gate, only inferable from a silence.** `FuturesOutcome.is_winner`
defaults to non-null `False`, so a clock-resolved market does not present as *ungraded* — it
presents as *all-loser* (ruling 058's finding, ~398,136 of ~1,961,984 outcomes at ~20.3%). That is
gotcha #53 at the level of a state transition: the reassuring reading and the true reading produce
identical rows. You cannot size a cutover against a population whose members are indistinguishable
from correct ones. The gate makes them distinguishable. **That is the change that had to come
first**, and it is why the order is not merely cautious but load-bearing.

**An estimate here would have been an estimate of the thing most likely to surprise us.** The
calibration program has now been wrong twice in one week about the size of a population it
reasoned about instead of reading: #2087's leg-vs-market fold (`3.7630 → 3.7226` before the
granularity was even right) and #2076's own extrapolation, which predicted 576 s against a
measured floor of 901.96 s — **directionally right, quantitatively useless, understated by
≥2.35×.** A program with that record does not get to size a P0 by intuition.

## The general clause

> **A deferral is legitimate when it ships the instrument that ends it.**

Stated so it survives deleting this case: when a fix is deferred because its size is unknown, the
deferring change must make the size *obtainable* — a query, a counter, a stamp — and must name the
value that ends the deferral and the party who receives it. A deferral that leaves the size exactly
as unknowable as it found it is not a deferral; it is a decision to not do the work, recorded in
the vocabulary of doing it later.

Routed to `docs/doctrine.md` as a candidate clause: it pays out here, and it is the same sentence
ruling 066 arrived at from the other direction (a deferred *read* owes a receipt) — 066 governs the
read you did not take, this governs the fix you did not make.

## What this ruling does NOT say

It does not endorse the clock task. If the 48 h read shows what codex expects, the cutover is
right and should be taken with the same urgency a P0 deserves. This ruling buys **one measurement
window**, not a standing licence, and it expires the moment the number exists.

It also does not license the reverse move — measuring forever. If the branch is merged and
deployed and no window takes the read, that is the deferral failing, and the correct response is
to take codex's fix on the estimate rather than to extend the window again.
