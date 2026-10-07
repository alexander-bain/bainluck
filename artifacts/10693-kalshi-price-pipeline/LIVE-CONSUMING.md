# #10693 consuming contract — Live owns activation

PILLARS: TRUTH / FORMATTING. SHIP: coherent Kalshi game prices reach readers sooner while unchanged quotes remain quiet.

This is a disjoint utility. No consuming patch has been applied. Install once on the consumer-owned AsyncEngine, consume each price phase through that engine's actual AsyncSession, and close after all scoped iterators finish or cancel, before engine disposal.

```python
from contextlib import aclosing
from app.utils.kalshi_price_pipeline import install_kalshi_price_pipeline

pipeline = install_kalshi_price_pipeline(engine)
try:
    async with get_task_session(engine=engine) as session:
        async with aclosing(pipeline.iter_phase(session, phase)) as results:
            async for result in results:
                declined += result.attempted - result.rowcount
                for row in result.all():
                    # Preserve existing result counters and queue_market_change.
                    ...
finally:
    pipeline.close()
```

The caller must exhaust successful phases. A caller processing exception or deliberate early exit closes the iterator via aclosing and must use its normal session rollback. The utility does not acquire sessions, commit, rollback, retry, acknowledge buffered debt, publish, rerank, set timeouts, or classify lock failures.

Input mapping order and consecutive complete/no-book runs remain intact. Singleton-only phases bypass version/import/template/connection preflight. Any multi-row run causes whole-phase preflight before the first price write, even a leading singleton. Unsupported versions/imports/templates/cursors select ordinary execution before submission. Checkout/query/cancellation errors propagate. Submitted runs never replay scalar. Completed earlier runs retain their diagnostics; a failed pipeline run exposes no partial result prefix, the disclosed comparator difference.

Live must preserve the 500ms periodic phase lock_timeout, 55P03-only independent continuation, pending-debt grouping, successful-phase bookkeeping, and timeout-free final drain. The composed actual Live source still owes the greater-than1.5s held-lock final drain with final_flush_dropped0, plus periodic timeout / unrelated continuation / pending retry controls. This utility's 0.6s timeout-free mechanism test does not pay that source acceptance.

Fast-path compatibility is exactly SQLAlchemy2.0.50 / asyncpg0.31.0. Requirements ranges (SQLAlchemy>=2.0.50,<2.1; asyncpg>=0.31.0) do not prove installed production eligibility. Normal delivery/readback must record actual loaded versions and selected path before calling the adapter active. No production probe or dependency change is requested by this packet. No SDK-envelope expansion, reconnect/network recovery, or ambiguous-COMMIT guarantee is inferred from pinned same-backend stale-plan rollback/new-Session recovery.

Consumer activation and offer remain blocked on simpler-factory delivery and independent exact Live composition acceptance. Root owns review routing, capacity and offer. Reservation82074 is unchanged.
