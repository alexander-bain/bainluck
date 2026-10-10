"""#10850 — a finished 1st half's questions, served as the half's result.

The #1588 rule takes a window-bounded row out of ``period_markets`` the moment
its window has provably closed and keeps it out until a grade arrives. That is
right for the price: a half that is over must not quote. It also removed the
rows the half maps draw from, so from halftime until the venue graded (30+
minutes on the 2026-10-10 NCAAF slate) the 1st half margin and points cards
were simply gone, at the moment the half had a result to show.

This module serves those rows under a separate, additive key,
``closed_period_markets``, which installed builds do not read. The client
contract was agreed with ux on #10850:

* ``probability`` is always ``None``, and no other price field is carried
  (``over_probability``, ``opening_over_probability`` and ``movement`` are
  absent). A closed window never carries a number.
* ``window_closed`` is ``True``.
* ``period_score`` is the half's evidenced score, ``{"home": int, "away": int}``.
  With no evidenced score the row is NOT served; the client never infers one.

``period_markets`` itself is untouched, so a row is in exactly one list: an
ungraded closed row is here, and once graded it returns to ``period_markets``
through the existing graded path.

WHAT COUNTS AS AN EVIDENCED HALF SCORE
--------------------------------------
The ESPN line score on the event row (``box_score_data.home_period_scores`` /
``away_period_scores``), never the scoreboard at halftime. It is accepted only
when both sides carry at least two whole-number entries AND each side's entries
sum to that side's current scoreboard score. A line score that has fallen
behind the scoreboard is refused, which is the fail-safe direction: no row.

v1 is the leagues whose line score is indexed in QUARTERS, where the 1st half
is the first two entries. Men's college basketball and soccer index halves (the
1st half is one entry) and need a per-league unit map before they can join;
``period_window_grade`` refuses non-inning units for the same reason.
"""

from __future__ import annotations

__all__ = ["CLOSED_PERIOD_LEAGUES", "closed_period_markets", "first_half_score"]

#: Leagues whose ESPN line score is one entry per quarter.
CLOSED_PERIOD_LEAGUES = frozenset({"NFL", "NCAAF", "NBA", "WNBA"})

_V1_MARKET_TYPES = frozenset({"half_spread", "half_total", "half_winner"})
_V1_PERIOD = "1H"


def _whole_numbers(values) -> list[int] | None:
    """The entries as ints, or ``None`` if any entry is not a whole number."""
    if not isinstance(values, list):
        return None
    out: list[int] = []
    for value in values:
        # bool is an int subclass; True is not a score.
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            out.append(value)
        elif isinstance(value, float) and value.is_integer():
            out.append(int(value))
        else:
            return None
    return out


def first_half_score(league, box_score_data, home_score, away_score) -> dict | None:
    """The 1st half's score from the line score, or ``None`` without evidence."""
    if (league or "").strip().upper() not in CLOSED_PERIOD_LEAGUES:
        return None
    if not isinstance(box_score_data, dict):
        return None
    home = _whole_numbers(box_score_data.get("home_period_scores"))
    away = _whole_numbers(box_score_data.get("away_period_scores"))
    if home is None or away is None or len(home) < 2 or len(away) < 2:
        return None
    if not isinstance(home_score, int) or not isinstance(away_score, int):
        return None
    if sum(home) != home_score or sum(away) != away_score:
        return None
    return {"home": home[0] + home[1], "away": away[0] + away[1]}


def closed_period_markets(
    closed_rows, *, league, box_score_data, home_score, away_score
) -> list[dict]:
    """The served ``closed_period_markets`` rows for one game.

    ``closed_rows`` are the ``period_markets`` rows the #1588 filter has just
    taken out: window provably closed, no grade in hand. Rows outside v1's
    scope are ignored; with no evidenced half score nothing is served.
    """
    candidates = [
        row for row in closed_rows
        if row.get("market_type") in _V1_MARKET_TYPES and row.get("period") == _V1_PERIOD
    ]
    if not candidates:
        return []
    score = first_half_score(league, box_score_data, home_score, away_score)
    if score is None:
        return []
    return [
        {
            "market_name": row.get("market_name"),
            "outcome_name": row.get("outcome_name"),
            "threshold": row.get("threshold"),
            "source": row.get("source"),
            "market_type": row.get("market_type"),
            "period": row.get("period"),
            "contributor_outcome_ids": list(row.get("contributor_outcome_ids") or []),
            "probability": None,
            "window_closed": True,
            "period_score": dict(score),
        }
        for row in candidates
    ]
