"""ux/1036 — the tennis hub's prior obeys the same ORDERED ladder as a game card.

`_prematch_by_pair` took `next(... status == "live")`: the first live source block
in register order. Where a pair is pinned at BOTH venues that is an arbitrary
choice between two different numbers, decided by the order an agent happened to
write the register file in — and where the first block prices incoherently it was
worse than arbitrary, because the function gave up instead of trying the second.

Alex's rule (given for #2747, applied everywhere by ux/1036): Kalshi →
Polymarket → books, ordered and never merged.
"""

from app.utils.tournament_register import TournamentRegister
from app.utils.tournament_slate import _prematch_by_pair


PAIR = ("p:alcaraz", "p:sinner")


def _register(*blocks):
    return TournamentRegister(
        {
            "matchups": [
                {
                    "matchup_key": "m:1",
                    "draw": "mens-singles",
                    "players": list(PAIR),
                    "sources": list(blocks),
                }
            ]
        }
    )


def _block(source, first_outcome, second_outcome):
    return {
        "source": source,
        "status": "live",
        "sides": {
            PAIR[0]: {"outcome_id": first_outcome},
            PAIR[1]: {"outcome_id": second_outcome},
        },
    }


KEY = ("mens-singles", tuple(sorted(PAIR)))


def test_kalshi_wins_even_when_polymarket_is_written_first():
    """The register order is not the ladder. This is the case the old
    `next(...)` form got wrong on every pair pinned at both venues."""
    register = _register(
        _block("polymarket", 1, 2),
        _block("kalshi", 3, 4),
    )
    prices = {
        1: {"opening_probability": 0.70}, 2: {"opening_probability": 0.30},
        3: {"opening_probability": 0.55}, 4: {"opening_probability": 0.45},
    }

    resolved = _prematch_by_pair(register, prices)[KEY]

    assert resolved["source"] == "kalshi"
    assert round(resolved["probabilities"][PAIR[0]], 3) == 0.55


def test_polymarket_is_used_when_kalshi_prices_incoherently():
    """"This VENUE has no coherent prior" is not "this pair has no prior". The
    single-block form could not tell those apart and blanked the row."""
    register = _register(
        _block("kalshi", 1, 2),
        _block("polymarket", 3, 4),
    )
    prices = {
        # Kalshi: nothing loaded for either side — a pinned market with no price.
        3: {"opening_probability": 0.62}, 4: {"opening_probability": 0.38},
    }

    resolved = _prematch_by_pair(register, prices)[KEY]

    assert resolved["source"] == "polymarket"
    assert round(resolved["probabilities"][PAIR[1]], 3) == 0.38


def test_the_number_and_its_normalization_are_unchanged():
    """The ordering is the only thing this touched. The pair still goes through
    `normalize_pair`, so a finished row and a live one are quoted on one basis."""
    register = _register(_block("kalshi", 1, 2))
    prices = {1: {"opening_probability": 0.66}, 2: {"opening_probability": 0.33}}

    probabilities = _prematch_by_pair(register, prices)[KEY]["probabilities"]

    assert round(sum(probabilities.values()), 6) == 1.0


def test_an_incoherent_only_pair_still_yields_nothing():
    """The refusal survives the rewrite: a fabricated tidy split under two real
    players' names is worse than an empty column."""
    register = _register(_block("kalshi", 1, 2))
    prices = {1: {"opening_probability": 0.9}, 2: {"opening_probability": 0.9}}

    assert _prematch_by_pair(register, prices) == {}
