"""WHAT A PAYLOAD MAY CLAIM ABOUT THE AWAY SIDE WHEN THE WINNER MARKET PRICES A DRAW.

#6238's PRODUCER half — the server-side twin of ``frontend/lib/drawPricedWinner.ts``
(ux/1301, live 2026-09-16) and of ``ios/.../Utilities/DrawPricedWinner.swift``
(native's #5271, live 2026-09-11). Accepted as a notice-46 pair by ux/1304 in
``runner-inbox/latency/FROM-ux1304-0110Z-6238-YES-build-the-payload-half-my-render-half-is-live.md``.

═══ WHY A THIRD COPY OF THE RULE EXISTS, AND WHY IT IS THE LAST ONE ═══

Both client halves fix a RENDER: they take a served away number and decline to
print it. Neither can stop the server SAYING it. Measured on production
2026-09-16 19:00 PDT / 2026-09-17 02:00Z, ``/api/events/{id}`` on three
scheduled Europa League fixtures — the same response both refutes itself and
inverts a favourite:

    15298553  Juventus v NEC Nijmegen
        current_odds       home 0.7937  away 0.2063   sum 1.0000
        the SAME payload's bookmaker_odds[], 10 books, mean
                           home 0.7939  away 0.0740   sum 0.8679
        0 of 10 book pairs sum above 0.97; served away is 2.79x the books' away

    15298549  PFC Levski Sofia v Salzburg     served away 0.6893, books 0.4203 (1.64x)
    15298747  OFI Crete v TSG Hoffenheim      served away 0.8737, books 0.6845 (1.28x)

Read the Juventus row twice. The HOME number is not the defect: 0.7937 against
the books' own de-vigged three-way 0.7939 — since #1011 that leg is honest, and
the withhold below therefore keeps a real number rather than half of a wrong
pair. The whole error is in the second slot, where ``1 − P(home)`` — *"the home
team does not win"* — is printed under the away crest and silently absorbs the
entire draw. On Levski that reverses the favourite outright: Salzburg is served
at 0.6893 over a board that prices them 0.4203.

Every reader of that field inherits the claim — native, My Stuff, share cards,
and any other API consumer — which is why the fix cannot live in one client.

═══ WHY IT WITHHOLDS RATHER THAN SUBSTITUTES THE BOOKS' AWAY ═══

The tempting repair is to serve ``aggregate_bookmaker_odds()["away_probability"]``,
which since #1011 is a real, de-vigged, three-way away price. It is the wrong
repair for THIS pair, and it is worth writing down so nobody re-opens it as an
improvement:

* the home slot is the multi-source BLEND (``compute_aggregate_probability``)
  and the away slot would be a sportsbook-only mean. Two producers, one duel —
  a source-divergence display, which the standing ruling ("the blend IS the
  product") keeps off every surface outside a short closed list this payload is
  not on;
* the consumer halves already shipped read a non-complement pair as SOURCED and
  print it (``awayIsTheComplement``, measured over 13 live soccer cards). So a
  substituted away would not be withheld by the clients — it would be printed
  beside a number computed a different way, which is a subtler version of the
  defect rather than its repair.

A number in the wrong unit is worse than an absent one, because it looks
sourced. The away slot is therefore withheld, exactly as both clients already
withhold it, and the reader keeps the honest home number.

═══ WHAT THIS DOES NOT DO ═══

It does not give the reader a draw price. ``odds_snapshots`` has no draw column,
``win_prob_snapshots.draw_probability`` is NULL fleet-wide, and building that
channel is #1011/#6277's business, not this module's. This closes the payload's
half of #6238: the server stops asserting an away probability it cannot source.
"""

from __future__ import annotations

from typing import Any, Optional, TypeVar

from app.utils.graded_card import is_complement_pair

__all__ = [
    "DRAW_PRICED_SPORT_KEY_MATCHES",
    "sport_prices_a_draw",
    "away_is_the_complement",
    "printable_away",
]

#: The declared draw-priced sports, as SUBSTRINGS of ``sports.key``.
#:
#: BYTE-FOR-BYTE THE WEB VOCAB'S ONE ``winnerMarketPricesADraw: true`` ROW
#: (``frontend/lib/marketMapUtils.ts``, ``SPORT_SCORING``), and pinned to it by
#: ``tests/test_event_payload_draw_priced_away_6238.py`` the way
#: ``frontend/__tests__/ios/aDrawIsNotTheAwayTeam5271.test.ts`` pins the web to
#: the Swift. Three runtimes answer this question and the answer has to be one
#: answer; the alternative is the split that let the web print the complement
#: for five days after native stopped.
#:
#: SUBSTRING, NOT PREFIX, because that is what ``sportVocab`` does and a reader
#: that is stricter than its declaration is how two surfaces come to disagree
#: about one match. Measured 2026-09-16 over all 177 rows of ``sports``: this
#: list matches exactly the 60 ``soccer*`` keys and nothing else — no
#: accidental hit, and no soccer league missed.
#:
#: The default for an undeclared sport is False, so widening the rule is one
#: string here plus the same string in the web vocab, by somebody who has
#: measured the sport. Withholding a number is only right where the complement
#: is provably wrong, and that has been measured for soccer and nowhere else.
DRAW_PRICED_SPORT_KEY_MATCHES: tuple[str, ...] = (
    "soccer",
    "mls",
    "epl",
    "uefa",
    "fifa",
)

_T = TypeVar("_T")


def sport_prices_a_draw(sport_key: Any) -> bool:
    """Does this sport's match-winner market price a draw as a third outcome?"""
    if not isinstance(sport_key, str):
        return False
    key = sport_key.lower()
    if not key:
        return False
    return any(match in key for match in DRAW_PRICED_SPORT_KEY_MATCHES)


def away_is_the_complement(away: Any, home: Any, sport_key: Any) -> bool:
    """Is the away figure in hand ``1 − home`` wearing an away team's name?

    ═══ WHY THE SPORT ALONE IS THE WRONG QUESTION ═══

    :func:`sport_prices_a_draw` asks whether a draw is a real outcome. Necessary,
    not sufficient: it says nothing about whether the away NUMBER IN HAND is the
    derived complement or an independently sourced price. Withholding is right
    only for the first, and this payload carries both kinds in one response —
    ``current_odds.away_probability`` is derived as ``1 − home`` (sum 1.0000 on
    13 of 13 live soccer cards measured 2026-09-16), while
    ``opening_odds.away_probability`` is the stored pre-game consensus, which
    since #1011 is de-vigged across the whole quoted board and sums to
    0.68–0.94 with its home (11 of 13). That second pair's away IS the away
    team's price and deleting it would be the mirror-image defect: printing a
    number we cannot source is one failure, deleting one we can is the other.

    So each object asks about its OWN pair, and the answer can legitimately
    differ between two objects in one response.

    ``is_complement_pair``'s [0.99, 1.01] band is this repo's existing measured
    definition of "these two are one question" and is reused rather than
    restated — the same constant the served whole percents are built on.

    THE ABSENT ARM IS DELIBERATE. On a draw-priced sport a missing away figure
    is withheld rather than merely missing, so a caller keeps its layout and its
    home number instead of deriving the complement itself further downstream.
    On a two-way sport an absent away is NOT withheld, which leaves every
    existing "one side has no reading" path exactly as it was.
    """
    if not sport_prices_a_draw(sport_key):
        return False
    if away is None:
        return True
    return is_complement_pair([away, home])


def printable_away(away: Optional[_T], home: Any, sport_key: Any) -> Optional[_T]:
    """The away figure this payload may serve — the one in hand, or ``None``.

    The value is passed through rather than re-derived, for the reason
    ``rendered_duel_percents`` documents: a caller that rebuilds ``1 − home``
    locally is how two surfaces on one page come to disagree. This only ever
    removes a value; it never invents or changes one.
    """
    return None if away_is_the_complement(away, home, sport_key) else away
