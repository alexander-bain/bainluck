# RULING 098 — A control and the metric that grades it are counted on ONE window

date: 2026-08-19
author: Fable
issues: #1958, #1998

Issued on UX-P103's boring-rate reads, which set out to answer whether 5% held
across days and found instead that the 5% was counted over twenty cards nobody
sees.

## The case

`enforce_first_page_quality_floor` is the #1958 control, banked under ruling (d)
on 2026-08-18. Its docstring is explicit about where it runs and why:

> LAST, deliberately. `boring-rate@20` / `ladder-rate@20` are counted over the
> first twenty cards of the SERVED payload, so the only place a control can
> match that target is the final order.

It is right about itself. It protects the first twenty cards of the served
payload, and on production 2026-08-19 it was doing so perfectly: **zero boring
futures among the first twenty served cards**, on every payload measured, which
is also what the server's own `debug_summary.boring_count` reported.

The instrument that grades it does not use that window. `audit_feed_quality.py`
and `census_boring_rate.py` filter the payload to `type == "futures"` and take
the first twenty of *that* list. The served page interleaves bundle, concept and
tournament cards — 4 to 6 of them in the first twenty slots on the payloads
measured — so the windows are offset by exactly the number of non-futures cards
on the page:

| card | futures-window rank | served position |
|---|---|---|
| Maine State Senate winner? | 17 | **22** |
| Will Meta (META) close above $540 on August 19? | 18 | **23** |
| 2Y US Treasury yield on Aug 21, 2026? | 20 | **24** |

Every card the metric flagged was past the fold of the page the metric names.

Both numbers are arithmetically correct. Neither is wrong about its own window.
But one of them has a screen behind it and the other does not, and the one
without a screen is the one that has been open as a P2 (#1958), the one cycle 99
refused to close, and the one whose 5.00% was quoted as the lane's finding.

## The ruling

**A control and the metric that grades it are counted on ONE window, and the
window is named in both.**

Three obligations follow.

1. **The window is part of the metric's name, not a detail of its
   implementation.** `boring-rate@20` says nothing about which twenty. Both
   tools now print `[SERVED]` or `[futures-only window]`, and the artifacts
   carry the label. A metric whose window is implicit will be read against
   whichever window the reader has in mind — usually the one the product has,
   which is usually not the one the code used.

2. **The offset is measured, not assumed equal.** The two windows coincide only
   when the page contains nothing but futures. That is an empirical property of
   each build, so `non_futures_in_served_window` is recorded per read. "They are
   basically the same" is the assumption that hid this for a month.

3. **A metric is not renamed into its replacement.** The futures-only number
   stays, labelled, alongside the served number. Every prior cycle's rate is a
   futures-window rate; silently redefining the metric would have made this
   cycle's improvement unfalsifiable and every earlier comparison meaningless.

## Why this is not just a units bug

The failure mode is that **both readings are defensible**, so neither party
notices the disagreement. The control's author measured the served page and
shipped a control that works. The audit's author measured the futures list and
shipped a metric that reports honestly. Each tested their own half, each was
green, and the gap between them was the only place the defect could live — which
is precisely where nobody was looking, because there was no artifact whose job
was to hold both numbers at once.

That generalises past this metric, so the sentence is lifted to
`docs/doctrine.md`: *two measurements of "the same thing" that were never
computed side by side have not been compared.* The cheap fix is not more
careful review; it is one artifact that prints both and forces the difference to
be a number.

## The narrower lesson, kept with its case

Bundles are the mechanism here. `assemble_*_theme_bundles` folds several cards
into one, which is why the floor runs after them — and it is also why an audit
run before that fold, or over a list that never had them, sees a different page.
Any future first-page control or metric must state whether it counts pre-fold or
post-fold cards.
