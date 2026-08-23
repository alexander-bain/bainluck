# RULING 125 — A join that can delete a row must carry every dimension that identifies it

date: 2026-08-23
author: Fable (directive pasted and reviewed by Alex)
issues: #2098, #2076, #1544

**#2098's unchunked behaviour is WRONG.** `mode_prices` and `deduped` join on a `vm_id`
that carries no source, while the rows they can eliminate are source-identified. A join
that can delete a cross-source leg must carry `source`.

## The defect

`_calibration_population_ctes()` builds the virtual-market id without a source:

```sql
CASE WHEN gs.group_size >= 3 THEN 'g:' || mi.group_id
     WHEN es.event_size  >= 3 THEN 'e:' || mi.event_id::text
     ELSE                          'm:' || mi.market_id::text END AS vm_id
```

Every neighbouring aggregate is source-scoped **deliberately** — `group_sizes` and
`event_sizes` both `GROUP BY … , source`, `virtual_market` joins on
`… AND gs.source = mi.source`, `vm_stats` groups on `vm.source`. Exactly two do not:

* `mode_prices` — `GROUP BY vm_id, adj_opening_probability, eligible`
* `deduped` — `LEFT JOIN mode_prices mp ON mp.vm_id = ro.vm_id AND mp.mode_price = ro.adj_opening_probability`

The exception is the defect. Where one `vm_id` string is reachable from two sources, a mode
price computed from one venue's legs suppresses the other venue's legs.

## It fires, and the number is the ruling's second half

CAL-P087 measured it rather than resolving it in the reassuring direction: whole `event_id`
domain, **0 unswept ranges**, 559 chunks, 1,788 s.

| | |
|---|---|
| rows cross-suppressed | **35** |
| distinct `vm_id`s | **2** |
| the issue's own upper bound | 1,271 → **corrected to 35** |

The correction is because the `g:` arm wins before the `e:` arm, which the bound did not
model. Charter specimen `e:14887630`: a **four-leg Polymarket market deletes 23 Kalshi
legs** at `p = 0.01`. Polymarket's `eligible 4` clears the `GREATEST(eligible * 0.5, 2)`
floor at 2; Kalshi's `eligible 120` needs 60 and has 23; and because the join carries no
source, the winner takes the loser's rows.

So the second clause travels with the first:

> An unmeasured upper bound is not a finding. The measurement is what converts *"this could
> fire"* into *"this fires, 35 times, here"* — and it is also what converts it back down,
> by a factor of 36, from a number that would have justified a much larger intervention.

CAL-P087 deliberately declined to rule on whether the behaviour was *right*, having only
measured that it happens. This ruling makes that call.

## The general clause

> Wherever a join's key is COARSER than the identity of the rows it can eliminate, the join
> silently picks a winner across a dimension nobody declared.

A row-**deleting** join is the one place a missing dimension cannot be absorbed downstream,
because the evidence of the mistake is the thing that was removed. A join that merely
duplicates or mislabels leaves its error visible in the output; a join that suppresses
leaves a smaller, tidier, wronger result that looks exactly like a correct one. This is
gotcha #53's shape — an absence and a decision reaching the reader in the same bytes — at
the level of a SQL predicate.

The corollary for `vm_id` specifically: an identifier assembled from columns of a
source-scoped table is not source-scoped merely because its inputs were. `'e:' || event_id`
discards the scoping that `event_sizes` was careful to compute, and `event_id` is an FK to
`events` that both Kalshi and Polymarket link to. Only the `e:` arm collides; group ids are
source-prefixed in practice (`polymarket:<event_id>`), which is why `g:` measured 0.

## The fix is NOT a drive-by, and that is part of the ruling

`AND mp.source = ro.source` is a change to the **frozen** builder under ruling 009. It
therefore requires:

1. its **own exception** to the freeze, named and granted;
2. its **own re-baseline declaration** — `_main_input_fingerprint()` moves, banked units are
   invalidated, the convergence count restarts;
3. a **stated curve movement**, measured before and after, because this ADDS 35 rows back
   into the calibration denominator and ruling 103 / doctrine clause 18 govern in reverse —
   a row-restoring fix is graded on the same two things a row-dropping one is;
4. its **own cert**, sequenced **after** the apply blockers.

This ruling banks the JUDGMENT ahead of the fix, by design, so that the question *"is the
current behaviour acceptable?"* is settled before the certification of the change starts,
rather than being re-litigated inside it.

## What it does not decide

It does not decide that source-chunking (#2076) is now safe. Chunking was closed on cost
and on the pushdown measurement, independently — CAL-P086B refuted the premise
(tail-filtered chunk = 1.0000× the unfiltered fold) and the binding polymarket chunk is
0.7616× against a 3-way, not 7-way, partition. Fixing the join removes one *objection* to
chunking; it does not supply an argument for it.
