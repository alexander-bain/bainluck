"""The closing-line selection rule for ``calibration_probability`` (Q436, CAL-P117).

`backfill_winners`'s Part A fills ``futures_outcomes.calibration_probability`` with
"the last price this outcome was quoted at before the event started". That sentence
has two halves, and both of them were wrong for a whole class of rows:

**1. "before the event started" was read off the LINKED EVENT.**

Part A joined ``events`` and used ``e.commence_time`` as the boundary. When a market
is linked to the wrong game — same two teams, next day, which is what a three-game
series makes easy — that boundary sits ~24 hours after the market actually settled,
and "the last snapshot before it" is a POST-SETTLEMENT quote.

The specimen, measured on production 2026-08-29 (market 56675315, *Miami Marlins vs.
Houston Astros - Player Props*, 37 legs):

    fm.resolution_date  2026-07-22 00:10Z   <- Polymarket's own endDate = the game
    e.commence_time     2026-07-23 00:10Z   <- the NEXT game in the series

    leg 210410292  "Xavier Edwards: Home Runs O/U 1.5"
      opening_probability      0.011000
      last snapshot < 00:10Z   0.011500  (a real, two-sided pre-game quote)
      last snapshot < 07-23    0.500500  captured 07-22 02:42Z, bid 0.0010 / ask 1.0000
      calibration_probability  0.500500  <- what the curve published

A market's own ``resolution_date`` is *market-local* truth (for Polymarket it is
Gamma's ``endDate``, `tasks/polymarket.py`), so it does not inherit our linkage
mistakes. Clamping the boundary to ``LEAST(event, resolution_date)`` is therefore
correct whether or not the link is right — and it stays correct when the linkage
is repaired, because a correctly-linked game market has the two within minutes.

Deliberately NOT floored at ``fm.commence_time``. A ``GREATEST(resolution_date,
commence_time)`` floor would guard against an absurdly-early ``resolution_date``,
but it can also push the boundary back PAST settlement on any row whose
``commence_time`` is a creation timestamp — reintroducing the exact defect. The
unfloored clamp fails the other way: no eligible snapshot, so Part A falls back to
``opening_probability``. That is the disclosed ``cp_eq_open`` state (ruling 103 /
gotcha #144), not an invented price, and "no price of ours to publish" is always
the safer error than "a price nobody quoted".

**2. "the last price it was quoted at" accepted prices nobody quoted.**

The post-settlement books above are not merely late, they are *empty*: bid 0.001 /
ask 1.000 is "nobody will buy this at any price", and its midpoint 0.5005 is the
#1574/#1578 phantom — a number manufactured by averaging a spread nobody will trade
inside. UX-P011 stopped Discover showing those, #1578 stopped the poller writing
new ones. Neither reaches back through ``futures_odds_snapshots``, which is where
the calibration writer reads. So the same predicate is applied here, generated from
the same constants by :func:`app.utils.feed_market_quality.fabricated_midpoint_sql`.

**Both arms are load-bearing**, measured on `polymarket/baseball` Player Props
containers in the 56M market band (430 legs, realized win rate 0.163):

    policy                     mean published   corr(published, opening)   legs at ~0.50
    today                          0.4018              0.4774                  186
    clamp only                     0.2305              0.7844                   45
    fabricated-midpoint only       0.2188                 —                       3
    both (shipped)                 0.1806              0.9746                    2

and it does not cost the healthy cohorts anything — correlation improves in all
four, including the 2,976 non-props legs the defect never touched (0.8806 ->
0.8878). Full table: `.claude/handoff/REPORT-LANE1-Q436-*.md`.

**What this module is for.** The rule is expressed once, here, as SQL fragments the
task embeds and a Python evaluator with the same semantics. Neither is a
re-statement of the other's logic in prose: the tests in
``tests/test_calibration_closing_line_q436.py`` assert (a) that the evaluator picks
the pre-game quote on the specimen's real snapshot rows and (b) that the SQL these
functions emit appears verbatim inside the statements ``backfill_winners`` actually
runs. A pure-Python guard that the shipped SQL has drifted away from is a guard that
stays green while the product breaks.
"""

from typing import Any, Iterable, Optional, Sequence

from app.utils.feed_market_quality import (
    fabricated_midpoint_sql,
    is_fabricated_midpoint,
)

__all__ = [
    "closing_line_boundary_sql",
    "closing_line_lateral_sql",
    "is_eligible_closing_snapshot",
    "select_closing_line",
]


def closing_line_boundary_sql(event_commence: str, resolution_date: str) -> str:
    """The instant a closing line must precede: the earlier of event start and settlement.

    Postgres ``LEAST`` already ignores NULL arguments, so the ``COALESCE`` is
    redundant to the engine and present for the reader — this expression must not
    read as though a NULL ``resolution_date`` could NULL the whole boundary and
    silently drop every row from the LATERAL.
    """
    return f"LEAST({event_commence}, COALESCE({resolution_date}, {event_commence}))"


def closing_line_lateral_sql(
    *,
    outcome_id: str,
    boundary: str,
    extra_and: str = "",
) -> str:
    """The LATERAL that picks one closing line: the last eligible snapshot before ``boundary``.

    Args:
        outcome_id: SQL expression for the outcome id to seek on. Uses
            ``idx_fos_outcome_captured(outcome_id, captured_at)`` — one index seek
            per outcome, which is why this stays a LATERAL and not a window.
        boundary: SQL timestamp expression, normally
            :func:`closing_line_boundary_sql`.
        extra_and: an extra conjunct for callers with a source-specific rule, e.g.
            Part A's Kalshi ``N+`` threshold guard (#167/#941/#1054). Must begin
            with ``AND``.

    Returns:
        A parenthesised sub-SELECT yielding at most one ``probability`` column.
    """
    return f"""(
                                SELECT fos.probability
                                FROM futures_odds_snapshots fos
                                WHERE fos.outcome_id = {outcome_id}
                                  AND fos.captured_at < {boundary}
                                  AND fos.probability > 0 AND fos.probability < 1
                                  AND NOT {fabricated_midpoint_sql(
                                      "fos.probability", "fos.yes_bid", "fos.yes_ask"
                                  )}
                                  {extra_and}
                                ORDER BY fos.captured_at DESC
                                LIMIT 1
                            )"""


def is_eligible_closing_snapshot(
    probability: Optional[float],
    yes_bid: Optional[float],
    yes_ask: Optional[float],
) -> bool:
    """Whether one snapshot may be used as a closing line. Mirrors the SQL above.

    Two rejections, in the order the SQL applies them: a probability outside the
    open interval (0, 1) is a settled marker rather than a quote, and a fabricated
    midpoint is not a price at all.
    """
    if probability is None:
        return False
    prob = float(probability)
    if not (0 < prob < 1):
        return False
    return not is_fabricated_midpoint(prob, yes_bid, yes_ask)


def select_closing_line(
    snapshots: Iterable[Sequence[Any]],
    *,
    event_commence: Any,
    resolution_date: Any = None,
) -> Optional[float]:
    """Pick the closing line from ``snapshots`` the way the shipped SQL does.

    Args:
        snapshots: rows of ``(captured_at, probability, yes_bid, yes_ask)``, in any
            order — this sorts, exactly as the SQL's ``ORDER BY captured_at DESC``
            does, rather than trusting the caller.
        event_commence: the linked event's start.
        resolution_date: the market's own settlement date, or None.

    Returns:
        The chosen probability, or None when no snapshot is eligible (the caller's
        ``opening_probability`` fallback then applies).
    """
    boundary = event_commence
    if resolution_date is not None and resolution_date < boundary:
        boundary = resolution_date
    best = None
    for captured_at, probability, yes_bid, yes_ask in snapshots:
        if captured_at >= boundary:
            continue
        if not is_eligible_closing_snapshot(probability, yes_bid, yes_ask):
            continue
        if best is None or captured_at > best[0]:
            best = (captured_at, float(probability))
    return None if best is None else best[1]
