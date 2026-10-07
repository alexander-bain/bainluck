# Live consuming return — #10689

PILLARS: TRUTH / FORMATTING. SHIP: coherent Kalshi game prices reach publication sooner by avoiding repeated expression construction.

Live owns `backend/app/tasks/kalshi_ws.py` under #10661. This packet changes no application writer. The companion patch is a mechanically prepared proposal against the exact unmodified writer in source-manifest.json; it compiles and differs in the lifted flush only at price execute arguments. The source PostgreSQL tests exercise that substitution through the actual current flush, canonical rank, task session and market publisher.

After Live's current claim returns, import KALSHI_PRICE_STATEMENTS and kalshi_price_parameters once outside the price loop. Replace only the price UPDATE construction with:

```python
result = await session.execute(
    KALSHI_PRICE_STATEMENTS[tick_has_book],
    kalshi_price_parameters(outcome_id, prob, yes_bid, yes_ask),
)
```

Keep `tick_has_book = yes_bid is not None and yes_ask is not None`. Keep each row's own await in original order and the entire rowcount/RETURNING/diagnostic loop. Keep rank, commit, frame queue/publication, buffer acknowledgement, newer-tick preservation and blend/receipt handoff. Templates must be reused, never rebuilt per row or converted to one executemany call. The parameter mapping is fresh per execution; stored Numeric and compared Float bindings stay separate. Half and absent books select False and write neither side.

Compose this edit into Live's final #10661 source rather than applying an old patch over the active claim. Preserve 500ms transaction-local timeout on periodic phases, continuation only for SQLSTATE55P03 and independent phases, pending-refresh-debt grouping, timeout reset, and all other conservative error/cancellation paths. The final drain remains timeout-free. Run the #10661 control where a lock held longer than1.5s is released and final prices commit with final_flush_dropped==0. This disjoint source packet cannot pay that composite-writer gate.

The held-first-row control explicitly observes the writer waiting on its backend lock before the holder commits a book. Its original before-book subquery retains the statement snapshot and reports that earlier book, with quotes_unchanged1 and a frame for row1. Do not replace that with a prefetch, batch subquery or returned-row-only comparison. The later-row writer control separately confirms each next row begins its own statement snapshot.

Then rerun the focused/source PostgreSQL controls against the integrated writer (the tests lift its current flow and compare the pinned original SQL expression), Live's timeout/final-drain controls, independent exact-source review and hosted CI before normal Integrator composition. Local retained timing is context only; production or reader speed is not accepted here.
