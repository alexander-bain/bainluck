"""CAL-P159 — `probability_change_24h` is NOT a 24h change. Pinned, not fixed.

TOP-PRODUCT-DEFECTS item 12. Alex, on the AI-scripted-series market: *"Amazon
went to ~98.5% and back to 27% in a day"* and *"why is the chart so janky?!?"*.

**The chart was honest. The number was not.** This file pins the true semantics
so the next reader does not assume the field means what it is named, and so the
day someone fixes the writers, the workarounds that exist because of it get
revisited rather than silently kept.

WHAT WAS MEASURED (production, 2026-08-31, market 109441 / Kalshi
``KXAISTREAMSERIES-27``)
------------------------------------------------------------------------
``futures_outcomes`` row for ``Amazon`` (``-AMA``)::

    current_probability      0.270
    probability_change_24h  -0.715     <- served to the UI as a 24h move
    last_updated             2026-08-28 20:50Z    (three days before it was read)

``futures_odds_snapshots`` for that outcome::

    2026-08-18 22:49   prob 0.985   bid 0.98  ask 0.99
    2026-08-28 20:49   prob 0.270   bid 0.26  ask 0.28

``0.270 - 0.985 == -0.715`` exactly. So the "24-hour" move is the **ten-day**
step from Aug 18 to Aug 28, and it had then been frozen for three more days.

THE SPIKE ITSELF IS NOT OUR BUG — item 12's premise is wrong on that half
--------------------------------------------------------------------------
Three checks, executed rather than assumed:

* **Linkage is clean.** The eight outcomes carry distinct correct tickers
  ``-AMA``/``-APP``/``-DIS``/``-HUL``/``-MAX``/``-NET``/``-PAR``/``-PEA``.
* **The book was tight at the spike** — bid 0.98 / ask 0.99. Not the
  wide-spread / no-liquidity capture artifact.
* **Only Amazon moved.** In the same 2026-08-18 22:49 capture the other seven
  sat at 0.025-0.095. A systematic capture fault would have moved the column.

So nobody should go hunting a capture bug behind that chart. The label is ours;
the price is Kalshi's.

WHY THERE IS NO FIX IN THIS COMMIT, AND WHERE IT BELONGS
---------------------------------------------------------
A read-side freshness filter is the obvious fix and the repo has already
measured it WRONG: ``app/routes/futures.py`` (the pooled-movers bound) records
that filtering the answer by freshness while ranking the pool by
``max_movement_24h`` breaks the superset guarantee — *"at limit 20 the two arms
disagree on VALUES, not just on ties."* That same comment parks the real cause:
*"nothing ever clears ``probability_change_24h`` on a row that stops being
written."* Independently, ``tests/test_futures_stamp_semantics.py`` (#2024)
treats any NEW read-side stamp comparison in ``app/routes``/``app/utils`` as a
finding in its own right — a draft of this work added one and that census
correctly rejected it.

The fix is therefore **upstream and one statement**: clear the column for stale
rows inside ``app.tasks.update_max_movement``, immediately BEFORE its existing
aggregate, in the same transaction — which keeps
``max_movement_24h == MAX(ABS(probability_change_24h))`` exactly true and so
*preserves* the bound a read-side filter would have broken. It is not in this
commit because ``futures_outcomes.last_updated`` is unindexed (a second full
scan every 10 min) and production Postgres was at 103% of capacity and being
replaced on the day this was found. Deploy it once the plan upgrade settles,
with a feed before/after — the field also feeds Discover interestingness.
"""

import inspect


class TestTheFieldDoesNotMeanWhatItIsNamed:
    def test_every_writer_computes_a_per_write_delta_not_a_windowed_one(self):
        """All four writers store ``new - previous``, over whatever interval that was."""
        from app.tasks import futures as futures_task
        from app.tasks import kalshi as kalshi_task
        from app.tasks import polymarket as polymarket_task

        kalshi_src = inspect.getsource(kalshi_task)
        poly_src = inspect.getsource(polymarket_task)
        futures_src = inspect.getsource(futures_task)

        assert "- FuturesOutcome.current_probability" in kalshi_src
        assert "- FuturesOutcome.current_probability" in poly_src
        assert "prob_change = prob - old_prob" in futures_src

    def test_nothing_recomputes_it_over_a_real_24_hour_window(self):
        """The claim that makes the field's name false. If this ever fails, the
        defect may be fixed — re-read this file's docstring before deleting it."""
        from app.tasks import futures as futures_task
        from app.tasks import kalshi as kalshi_task
        from app.tasks import polymarket as polymarket_task

        for mod in (kalshi_task, polymarket_task, futures_task):
            src = inspect.getsource(mod)
            assert "interval '24 hours'" not in src, mod.__name__

    def test_the_upstream_fix_has_not_silently_landed_elsewhere(self):
        """`update_max_movement` is where the fix belongs; pin that it is absent.

        Anchored on the task's own source so the pin cannot be satisfied by a
        comment in some other module that merely mentions the column.
        """
        from app.tasks import update_max_movement

        src = inspect.getsource(update_max_movement)
        assert "MAX(ABS(fo.probability_change_24h))" in src, (
            "the aggregate this fix must sit in front of has moved — re-locate it"
        )
        assert "SET probability_change_24h = NULL" not in src


class TestTheParkedReasoningIsStillRecordedWhereItWasFound:
    def test_the_movers_bound_still_documents_why_read_side_is_wrong(self):
        """If this comment is ever deleted, the measured objection is lost and
        someone will re-derive the wrong fix. That is what happened once."""
        from app.routes import futures as futures_routes

        src = inspect.getsource(futures_routes)
        assert "breaks the superset guarantee" in src
        assert "nothing ever clears `probability_change_24h`" in src
