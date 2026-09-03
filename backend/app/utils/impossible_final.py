"""Can this sport's rules produce a draw? — and the finals that prove they did not.

WHY THIS FILE EXISTS
--------------------

Alex opened his Orioles team page on 2026-08-31 and read **"Final · TIED 1-1"** on a
baseball game. Baseball's rules do not permit that. The real game (event 15298071)
finished 1-2; the row he clicked (event 15291461) was a duplicate that held 1-1 when
``detect_and_close_stale_events`` marked it ``closed``.

The closer is the writer. It closes on **odds staleness**, and it never touches scores::

    if total_snapshots == 0:
        should_close = True
        close_reason = "no_odds_data"

Whatever ``home_score``/``away_score`` the row happened to hold at that moment silently
becomes its final — a mid-game freeze, or the 0-0 a row carries when scores never arrived
at all. Nothing downstream can tell that apart from a real result: the team page renders
it as a Recent Result, the record grows a third column, and the ``game_score`` grader in
``backfill_winners`` reads it as ground truth.

Measured in production 2026-09-01: **130** terminal events in draw-impossible-or-mixed
sports hold an equal score; **354** ``futures_outcomes`` rows are stamped
``game_score``/``box_score`` on them and **248** more ``pass2_guess``/``pass2_loser``.
Both grader families read a score. Only **4** of those sit on duplicate rows — the rest
are on rows with a real ``external_id``, so this is NOT merely a duplicate-row artifact.

THE PREDICATE IS RULES-BASED, AND DELIBERATELY NARROW
-----------------------------------------------------

The temptation is to declare every equal score impossible. That is false, and a guard
that fires on true finals gets muted:

* **NFL and CFL ties are real** — regular season and preseason both. 9-9 is a result.
* **MLB *spring training* ties are real** — exhibition games stop at the agreed inning.
  ``baseball_mlb_preseason`` must not be guarded even though ``baseball_mlb`` is.
* **NCAA baseball ties are real** — curfew and suspension rules permit them.
* **Some hockey leagues keep the tie** — Allsvenskan does; the NHL does not.
* **MMA and boxing draws are real** — a draw is one of the scorecard outcomes.

So the table below lists only sports whose rules *guarantee* a winner, and every other
sport is ``None`` — "not known to be impossible" — which the guard treats as permitted.
An unknown sport key is never asserted against. This costs coverage on purpose: the
NCAA-baseball bucket (71 equal-score finals, 66 of them 0-0) is almost certainly the same
defect, but "almost certainly" is not what a permanent guard may be built on. That bucket
is detected by its own signature (a ``no_odds_data`` close) and reported, not asserted.

See ``docs/rulings/048-an-id-less-claim-never-absorbs.md`` for why the duplicate rows
exist in the first place; this module is about what the *closer* then does to them, which
is a separate defect with a separate blast radius.
"""

from typing import Optional

__all__ = [
    "DRAW_IMPOSSIBLE_SPORT_PREFIXES",
    "DRAW_POSSIBLE_SPORT_KEYS",
    "sport_allows_draw",
    "is_impossible_final",
    "TERMINAL_STATUSES",
]


# Statuses that present to a user as "this game is over". Both are terminal:
# `completed` is the scores-API path, `closed` is the staleness fallback, and the
# user-visible language ("Final") is identical for the two.
TERMINAL_STATUSES = frozenset({"completed", "closed"})


# Sport-key PREFIXES whose rules guarantee a winner. Prefix-matched because the
# key space carries per-tournament suffixes (`tennis_atp_cincinnati_open`).
#
# Each entry is a rules claim and is defended here, because the next person to
# widen this table needs to know what the bar was:
#
#   baseball_mlb    — extra innings until someone leads after a full inning.
#   basketball_     — overtime periods repeat until a lead exists. Covers nba,
#                     wnba, ncaab, wncaab and the `basketball_other` bucket.
#   icehockey_nhl   — 3-on-3 overtime then a shootout; the NHL abolished the tie
#                     in 2005. Other hockey leagues are NOT covered (see below).
#   tennis_         — a match ends when someone wins the deciding set. There is
#                     no scoreline in tennis that is both final and level.
DRAW_IMPOSSIBLE_SPORT_PREFIXES: tuple[str, ...] = (
    "baseball_mlb",
    "basketball_",
    "icehockey_nhl",
    "tennis_",
)


# Explicit exceptions that sit UNDER a draw-impossible prefix and must escape it.
# Order matters: this set is consulted before the prefix table.
#
#   baseball_mlb_preseason — spring training games are called at an agreed inning
#                            and tie routinely. 12 such finals in production on
#                            2026-09-01, and every one of them is a real result.
DRAW_POSSIBLE_SPORT_KEYS: frozenset[str] = frozenset(
    {
        "baseball_mlb_preseason",
    }
)


def sport_allows_draw(sport_key: Optional[str]) -> Optional[bool]:
    """Do this sport's rules permit a level final score?

    Returns ``False`` only for sports whose rules guarantee a winner, ``True``
    for the named exceptions, and ``None`` for everything else — including an
    unknown or missing key.

    ``None`` is not ``True``. It means *we have not made a rules claim about this
    sport*, and callers must treat it as "do not assert", never as "draws are
    fine". The distinction is the whole reason this returns a tri-state instead
    of a bool: a bool would force every unlisted sport into one of two lies.
    """
    if not sport_key:
        return None

    key = sport_key.strip().lower()
    if not key:
        return None

    if key in DRAW_POSSIBLE_SPORT_KEYS:
        return True

    for prefix in DRAW_IMPOSSIBLE_SPORT_PREFIXES:
        if key.startswith(prefix):
            return False

    return None


def is_impossible_final(
    sport_key: Optional[str],
    status: Optional[str],
    home_score: Optional[int],
    away_score: Optional[int],
) -> bool:
    """Would persisting this row assert a result the sport cannot produce?

    True only when ALL of the following hold:

    * the sport is one whose rules guarantee a winner (``sport_allows_draw`` is
      strictly ``False`` — a ``None`` tri-state never trips this),
    * the status is terminal, so the row reads "Final" to a user,
    * BOTH scores are present, and
    * they are equal.

    A missing score is not an impossible final. ``None`` means "we don't know",
    which is the honest state and the one this module's caller writes on purpose;
    only a *stated* level result is a lie.
    """
    if sport_allows_draw(sport_key) is not False:
        return False

    if (status or "").strip().lower() not in TERMINAL_STATUSES:
        return False

    if home_score is None or away_score is None:
        return False

    return home_score == away_score
