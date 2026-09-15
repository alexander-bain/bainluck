"""Grade a full-game MARGIN question off the final score (#6312).

WHY THIS EXISTS: A MARKET WHERE EVERY LEG LOST HAS NO WINNER TO POINT AT
-----------------------------------------------------------------------
``routes/events.py::_verdict_is_provable`` (#6169) refuses to treat a graded
loss as an answer unless some sibling leg WON, and that refusal is right and
measured: a VOIDED market is graded on every leg and won by none — 389 markets
across 163 events in a trailing-14-day production read — so from the grades
alone a void and a draw are the same shape.

A 1–1 draw produces that shape honestly. On `/events/15306857` (Gwangju FC 1 ·
FC Anyang 1, K League 1, Final) the settled Kalshi market
``KXKLEAGUESPREAD-26SEP13GWAANY`` holds four legs — "Gwangju wins by more than
1.5 goals" and three siblings — each ``is_winner=false``, ``api_settlement``,
``current_probability`` 0.000000. Nobody wins by more than any line in a draw,
so the grading is correct and there is no winner anywhere on the market. The
page dropped the market whole: ``spreads: []`` on a page already printing that
same fixture's losing moneyline legs and its losing total rungs.

THE PROOF IS ARITHMETIC, AND IT DOES NOT NEED A SIBLING
-------------------------------------------------------
What makes that market provably all-lost is not its grades. It is the FINAL
SCORE, which the event row already holds: margin 0, so "wins by more than 1.5
goals" is false for both sides by subtraction. No appeal to a sibling winner,
and — this is the half that keeps #6169 intact — **a void at the venue does not
change what the scoreboard says**. This is therefore an ADDITIONAL route to
"provable", never a relaxation of the sibling-winner rule.

Its caller uses it as a RECOMPUTATION and not as a grader of record: the row's
stored grade is only treated as an answer when the score independently arrives
at the same answer. A disagreement — the venue says this leg won, the score says
it did not — is a defect in one of the two, so nothing is published and the row
keeps today's behaviour. That is exactly the standard
``_PRICE_IS_A_VERDICT_MIN_TIER`` names ("recomputes to the same winner from
cited data"), performed rather than assumed.

FAIL-SAFE, IN THE SAME DIRECTION AS ``grade_period_window``
------------------------------------------------------------
Every branch defaults to ``None`` — *not provable* — which leaves the row
exactly where it is today. A verdict is published only when the shape, the
side, the scoring unit and both scores are all positively identified. Four
refusals are deliberate:

* **A unit this sport does not score in.** The whole proof is a subtraction of
  two numbers, so the question's unit must be the unit ``home_score`` /
  ``away_score`` are counted in. Tennis's "wins by over 1.5 sets" (204 rows) is
  refused rather than graded against a score column whose unit is not proven to
  be sets — the same scale trap ``parse_period_scale`` exists to prevent, and
  the same refusal ``grade_period_window`` makes for every non-inning window.
  An outcome carrying no unit word at all is refused for the same reason.
* **An ambiguous side.** Delegated to
  :func:`app.utils.team_side.resolve_team_side`, which resolves "New York" on a
  Yankees/Mets matchup to neither.
* **A shape that is not a strict-or-equal threshold.** "wins by 1 to 3 points"
  (64 rows) is a BAND, not a threshold; it does not match and is not guessed at.
* **A missing or non-integer score.** A scoreless event row proves nothing.

GRAMMAR, MEASURED
-----------------
Every ``futures_outcomes`` row whose name contains "wins by", production
2026-09-15 — the whole population, not a sample:

===================================  ======
shape                                 rows
===================================  ======
``<T> wins by more than N goals``     27,257
``<T> wins by over N runs``           21,446
``<T> wins by over N Points``         18,281
``<T> wins by over N points``         17,052
``<T> wins by over N goals``           8,247
``<T> wins by over N sets``              204
``<T> wins by N to M points``             64
``<T> wins by N or more points``          32
===================================  ======

The first five and the last are threshold questions and are parsed. "N to M" is
the band above and is refused. Nothing here is case-sensitive.
"""

from __future__ import annotations

import re
from typing import Optional

from app.utils.team_side import resolve_team_side

__all__ = ["margin_verdict_from_final_score"]


# "<Team> wins by more than 1.5 goals" / "<Team> wins by over 3 runs" /
# "<Team> wins by 5 or more points".
#
# The two alternatives are the only threshold spellings the population holds and
# they differ in their COMPARATOR, which is why they are separate groups rather
# than one number: "more than 1.5" and "over 3" are strict, "5 or more" is not,
# and a margin of exactly 5 is the case that tells them apart.
#
# The trailing `[A-Za-z]*` is the scoring unit and is REQUIRED to be present by
# `_unit_matches_sport` below, not by this pattern — so a name with no unit
# parses and is then refused for the stated reason, rather than failing to match
# for an unstated one.
_MARGIN_RE = re.compile(
    r"^\s*(?P<team>.+?)\s+wins?\s+by\s+"
    r"(?:"
    r"(?:more\s+than|over)\s+(?P<strict>\d+(?:\.\d+)?)"
    r"|(?P<at_least>\d+(?:\.\d+)?)\s+or\s+more"
    r")"
    r"\s*(?P<unit>[A-Za-z]*)\s*$",
    re.IGNORECASE,
)


# THE UNIT THE SCORE COLUMNS ARE COUNTED IN, PER SPORT FAMILY.
#
# Keyed on the `sport_key` PREFIX (`app/utils/sport_keys.py`'s convention:
# `soccer_korea_kleague1`, `baseball_mlb`, `americanfootball_nfl`), because the
# scoring unit is a property of the sport and never of the league.
#
# A sport that is not listed is refused, which is the whole protection: the
# question's unit and the score column's unit have to be the SAME unit before a
# subtraction of the two scores can answer the question. Tennis is deliberately
# absent — `home_score` on a tennis row is not proven here to be sets, and
# "wins by over 1.5 sets" graded against games would invert on every close
# match.
_SPORT_SCORING_UNIT = {
    "soccer": "goal",
    "icehockey": "goal",
    "baseball": "run",
    "basketball": "point",
    "americanfootball": "point",
}


def _singular(unit: str) -> str:
    """"goals" -> "goal". The population writes plurals; a line of exactly 1 would not."""
    lowered = unit.lower()
    return lowered[:-1] if lowered.endswith("s") else lowered


def margin_verdict_from_final_score(
    outcome_name,
    sport_key,
    home_team_name,
    away_team_name,
    home_score,
    away_score,
) -> Optional[bool]:
    """Is this margin claim TRUE of the final score? ``None`` when not provable.

    ``True`` / ``False`` are both positive answers — a claim the score refutes is
    as provable as one it confirms, and the refutation is the whole point here
    (every leg of the specimen market is a refuted claim).

    ``None`` means *this function proves nothing about this row*, and the caller
    must leave the row exactly as it is today. See the module docstring for the
    four refusals.
    """
    prefix = str(sport_key or "").split("_")[0].lower()
    sport_unit = _SPORT_SCORING_UNIT.get(prefix)
    if sport_unit is None:
        return None

    # `bool` is an `int` subclass; a score is never one, and letting it through
    # would silently subtract True from False.
    for score in (home_score, away_score):
        if isinstance(score, bool) or not isinstance(score, int):
            return None

    match = _MARGIN_RE.match(str(outcome_name or ""))
    if match is None:
        return None
    if _singular(match.group("unit")) != sport_unit:
        return None

    side = resolve_team_side(match.group("team"), home_team_name, away_team_name)
    if side is None:
        return None

    mine, theirs = (
        (home_score, away_score) if side == "home" else (away_score, home_score)
    )
    margin = mine - theirs

    strict = match.group("strict")
    if strict is not None:
        return margin > float(strict)
    return margin >= float(match.group("at_least"))
