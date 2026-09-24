"""The charted series and the printed number, on ONE scale (#4992).

`GET /api/futures/{id}/history` feeds the Probability Trend chart. It used to
average the RAW per-bookmaker rows of `futures_odds_snapshots` and serve that,
while `GET /api/futures/{id}` — the hero and every outcome row drawn directly
above the chart — serves the de-vigged consensus with the #23 display squeeze
applied. Two scales, one screen.

WHAT A READER SAW. `/futures/56775503` (*2027 FIFA Women's World Cup Champion*)
printed a hero of **20% Spain** over a chart plotting **Spain at 32.5**, and the
chart's three visible lines summed to 70% for three of thirty-two candidates in
a one-winner field (#4992, found in a D48 mystery-shop). The class is not
Kalshi-specific: `/futures/7` (*US Open Winner*, odds_api golf, 205 outcomes)
printed **Scheffler 12%** over a line at **17.6%** on 2026-09-17, both stamped
the same microsecond, so it is scale and never staleness. The charted value was
raw implied straight off the American odds — `+469 -> 100/569 = 0.17575`, to the
digit.

THE STANDING RULE THIS RESTORES (Alex, 2026-08-13, quoted in
``odds_math.remove_vig_nway``): **raw vig-inclusive book prices NEVER enter
probability arithmetic, anywhere. De-vig first, then compare, average, or
subtract.** ``mean([raw_draftkings, raw_betmgm, ...])`` is that arithmetic, and
it is what this module replaces. It is the same defect as #1844, whose grid
"Biggest Movers" row rendered 29 of 30 teams falling every day because it
subtracted a 1.3178-sum column from a 0.9873-sum one, on the same table.

NO SECOND NORMALIZER, WHICH IS THE WHOLE POINT. ``devig_consensus``'s docstring
states #1844's design constraint in one sentence — *a second copy written to
serve the historical side re-creates exactly the divergence this closes* — so
this module does no division and owns no threshold. It reshapes rows and hands
them to the two helpers the detail route already runs, in the detail route's
order:

  1. ``odds_math.devig_consensus``   — per-book de-vig, then average across books
  2. ``outcome_display.normalize_display_probs``  — the #23 display squeeze

BOTH HELPERS ARE RUN OVER THE WHOLE FIELD, NOT THE TEN CHARTED LINES, because
that is the only input on which either one is meaningful: `remove_vig_nway`
divides a book's column by that column's own sum, and the #23 squeeze tests the
field's sum against its own thresholds. Handing them ten of 205 outcomes would
answer a different question and force the ten to sum to 1.0. The caller
therefore reads the market's full snapshot field for the charted timestamps —
measured at 103 ms for the largest board in the table (market 3, NCAAB, 19,068
rows over 168 h) — and slices the charted outcomes out of the result.

#7103'S GATE TRAVELS WITH THEM, AND FOR ONE SESSION IT DID NOT (#7747). The
detail serializer passes a THIRD argument these two steps need —
``field_complete=prices_withheld == 0`` — because withholding a leg changes
whether the squeeze FIRES, not merely what it divides by: once a leg's price is
refused as UNKNOWN, the survivors' sum is no longer a proved distribution. This
module ran the same two helpers without it, so on a board where the detail had
refused a leg the hero printed RAW and the chart beneath it printed SQUEEZED.

WHAT A READER SAW, AGAIN. `/futures/61308736` (*2027 US Open Men's Singles*)
served Jannik Sinner at **0.315** in the hero and in his own All Outcomes row,
and **0.203** in the Probability Trend directly below them, both stamped
2026-09-22T03:50:54.864277Z — 32% over a line at 20%, one screen at 390px. The
divisor was 1.555 and 0.740 of it was Jakub Mensik, the single leg the page had
just declined to price (`yes_bid 0.0400` against `yes_ask 0.7400`, no 24-hour
volume). So the refused leg was not merely still in the arithmetic: it WAS the
arithmetic, pushing every honest line on the board down by a third.

THE DETAIL ROUTE'S OWN #7103 COMMENT PREDICTED THIS AND DID NOT REACH IT. It
says the hub "moves with it", because gating one surface and not the other
"would divide the same board by two different numbers and manufacture exactly
the detail-vs-hub disagreement #7016 closed" — and then enumerates the detail
and the hub. The chart runs the same two steps through this module and was
never in that enumeration.

A MEASURED EQUIVALENCE, NOT AN ASSUMED ONE: reconstructed from production rows
for market 7 at 2026-09-17T20:30:09Z, this returns Scheffler 0.130444 against
the ``current_probability`` the live ingest path stored the same second,
0.130446 — the live path and this one are the same computation over the same
column, which is what "one scale" has to mean.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Collection, Mapping

logger = logging.getLogger(__name__)


def carry_forward_quotes(
    raw_by_time: Mapping[datetime, Mapping[str, Mapping[int, float]]],
    *,
    do_not_carry: frozenset | set = frozenset(),
) -> dict[datetime, dict[str, dict[int, float]]]:
    """Complete each book's column at each instant from that book's last quotes (#8296).

    ``futures_odds_snapshots`` is de-duplicated at WRITE time: a poll that finds a
    leg's price unchanged writes no row for it. So the rows stamped with one
    instant are the legs that MOVED, not the field — and handing that partial
    column to the #23 squeeze asks it about a distribution that never existed.

    WHAT A READER SAW. ``/futures/59698965`` (*KBO Korean Series Champion*)
    printed **LG Twins 37%** in its hero and ended the same line at **47%** in
    the Probability Trend directly below, both stamped 2026-09-23T21:50:32Z —
    every leg off by the same 1.27. The hero divides each leg's standing price
    by the whole board (sum 1.268). The chart's last instant held rows for 7 of
    10 legs (Samsung, Kia and NC had not moved since 9/21-9/23), summing to
    0.89, which is under the squeeze's threshold, so the chart printed RAW. Same
    board, same second, two divisors.

    THE READING THIS APPLIES IS THE ONE THE DEDUP ALREADY MEANS: no row means
    "unchanged", so a leg's standing price at instant ``t`` is its last quote at
    or before ``t``. That is the price the hero divides by, so a completed column
    at the final instant is the hero's own column.

    Three bounds, each deliberate:

    * **Only a book that quoted at this instant is completed.** A book with no
      row at ``t`` contributes nothing at ``t``, exactly as before; this never
      resurrects a book that stopped quoting.
    * **Only inside the served window.** A leg whose last quote is older than
      the window is not seeded from before it — and needs no seed: at the 168 h
      window that leg is more than seven days behind its own board, which is
      #7537's ``stale_observation_keys`` withhold, so ``field_complete`` is
      already False and neither the hero nor this chart squeezes.
    * **Graded legs are not carried** (``do_not_carry``). A graded leg's
      standing value changed at a moment no snapshot row records, so carrying
      its last price would print a loser alive after elimination, and carrying
      its grade backwards would squeeze a finalist to certainty before the final
      was played. Such a leg keeps exactly today's behaviour: present at its own
      rows, absent between them.
    """
    completed: dict[datetime, dict[str, dict[int, float]]] = {}
    last: dict[str, dict[int, float]] = {}
    for captured_at in sorted(raw_by_time):
        books = raw_by_time[captured_at]
        column_by_book: dict[str, dict[int, float]] = {}
        for bookmaker, column in books.items():
            standing = last.setdefault(bookmaker, {})
            if not column:
                continue
            filled = {
                key: value
                for key, value in standing.items()
                if key not in do_not_carry
            }
            filled.update(column)
            standing.update(column)
            column_by_book[bookmaker] = filled
        if column_by_book:
            completed[captured_at] = column_by_book
    return completed


def carried_endpoint(
    oid: int,
    devigged: Mapping[datetime, Mapping[int, float]],
    *,
    own: Collection[datetime],
    observed: Collection[datetime],
    drawn_last: float | None,
) -> tuple[datetime, float] | None:
    """The point at which a line that did not move is closed by its carried value (#8296).

    :func:`carry_forward_quotes` completes the COLUMN, but ``/history`` draws each
    line only at that line's own rows. A leg that did not move at the column's
    last instant therefore never reached it: on KBO 59698965 LG and KT ended on
    the hero while Samsung, NC and Kia ended at 0.160 / 0.1115 / 0.105 under a
    hero of 0.126 / 0.088 / 0.083 (CERT-3362's second opinion).

    ONE point, at the last instant whose column carries this leg — the hero's
    own column — not a point at every instant. Every drawn point is right at its
    own instant; the stretch between is interpolation, as it already is for a
    moved leg between polls. A point per instant would multiply the payload by
    polls × books for nothing a reader can see.

    ``own`` is the instants the line already draws from (support-filtered);
    ``observed`` is every instant the leg wrote a row, refused or not;
    ``drawn_last`` is the value the line currently ends at. None when:

    * the line draws nothing (a point from nothing is not a line);
    * the line already ends at the carried value (a raw-printed board): the point
      would only stretch a flat line, and move every count read off the payload;
    * the leg wrote a row at that instant (it is drawn there already, or #5898
      refused that row and nothing may stand in for it);
    * the standing price being carried came from a refused row (carrying it would
      draw the refused price at a later stamp);
    * the leg is absent from every column (a graded leg is never carried).
    """
    if drawn_last is None:
        return None
    column_instants = [t for t, point in devigged.items() if oid in point]
    if not column_instants:
        return None
    last = max(column_instants)
    if last in observed:
        return None
    standing = max((t for t in observed if t <= last), default=None)
    if standing is None or standing not in own:
        return None
    value = devigged[last][oid]
    if abs(value - drawn_last) <= 1e-9:
        return None
    return last, value


def devigged_consensus_by_time(
    raw_by_time: Mapping[datetime, Mapping[str, Mapping[int, float]]],
    *,
    mutually_exclusive: bool = True,
    field_complete: bool = True,
) -> dict[datetime, dict[int, float]]:
    """Return ``{captured_at: {outcome_id: probability}}`` on the PRINTED scale.

    Args:
        raw_by_time: ``{captured_at: {bookmaker: {outcome_id: raw_probability}}}``
            covering EVERY outcome of the market each book quoted at that
            instant, not only the charted ones. Raw means straight from the
            snapshot column — vig-inclusive, per book, not a consensus.
        mutually_exclusive: ``FuturesMarket.mutually_exclusive``, forwarded to
            the #23 squeeze. #199: a golf make-cut/top-N family is not a
            one-winner field and must not be squeezed — normalizing one squashed
            an honest 86% make-cut to ~1%.
        field_complete: ``prices_withheld == 0`` on the board being charted,
            forwarded to the #23 squeeze exactly as the detail serializer
            forwards it. #7103's gate, which this module ran without until
            #7747 — see the note above. PER BOARD, never per instant: the
            squeeze is a change of SCALE, so applying it to some instants of
            one line and not others renders as movement, which is the failure
            this module exists to close.

    Returns:
        One entry per timestamp that produced a usable column. A timestamp whose
        books all refused normalization is ABSENT rather than present-and-raw:
        a gap in a line is honest, and a raw point drawn beside de-vigged ones
        is the very defect this closes, and would be invisible — it renders as
        movement (gotcha #53 — an absence and a fact must not share a shape).
    """
    # Lazy, and from the route module that owns them, for the same reason
    # `outcome_display.normalize_display_probs` lazily imports the #23 util out
    # of `app.routes.politics`: the classification is shared, and a copy here
    # would be a second list of source names free to drift from the one CI
    # scans (`tests/test_playoff_movers_basis.py`).
    from app.routes.playoffs import (
        _ALREADY_PROBABILITY_SOURCES,
        _DEVIGGED_AT_INGEST_SOURCES,
    )
    from app.utils.odds_math import devig_consensus
    from app.utils.outcome_display import normalize_display_probs

    # A source in neither bucket is de-vigged by the default arm. That is right
    # for a new Odds API sportsbook and WRONG for a new prediction market, and
    # the two are indistinguishable from here — so say it once per read, the way
    # `_compute_movers` does, rather than let it ride silently (#6675).
    unknown_sources = {
        bookmaker
        for books in raw_by_time.values()
        for bookmaker in books
        if bookmaker not in _ALREADY_PROBABILITY_SOURCES
        and bookmaker not in _DEVIGGED_AT_INGEST_SOURCES
    }
    if unknown_sources:
        logger.warning(
            "futures history: unclassified snapshot source(s) %s de-vigged by "
            "default — if any of them stores a probability rather than a price, "
            "its charted line is re-scaled by the column sum (#6675)",
            sorted(unknown_sources),
        )

    series: dict[datetime, dict[int, float]] = {}

    for captured_at, books in raw_by_time.items():
        # Keys are outcome ids; `devig_consensus` is key-agnostic.
        book_columns = {
            bookmaker: dict(column) for bookmaker, column in books.items() if column
        }
        if not book_columns:
            continue

        consensus = devig_consensus(
            book_columns,
            method="mean",
            already_normalized=_ALREADY_PROBABILITY_SOURCES,
        )
        if not consensus:
            continue

        # The #23 squeeze, run by the helper that owns its thresholds, over the
        # whole field — the same list shape and now ALL of the arguments the
        # detail route passes (#7747: the missing one was `field_complete`, and
        # this comment claimed a parity it did not have). Carries `_key` because
        # the helper may SHORTEN the list in place (#1201 strips a run of
        # exact-0.5 untraded midpoints), so position cannot be trusted to
        # survive the call.
        entries = [
            {"_key": key, "probability": value} for key, value in consensus.items()
        ]
        normalize_display_probs(
            entries,
            mutually_exclusive=mutually_exclusive,
            field_complete=field_complete,
        )

        point = {entry["_key"]: entry["probability"] for entry in entries}
        if point:
            series[captured_at] = point

    return series
