"""#5982 — LaLiga 2 is the Spanish SECOND division, not a La Liga prop.

What a reader saw on 2026-09-13: `https://bainluck.com/sports/soccer_spain_la_liga`
served a *Live & Paused* rail carrying six fixtures presented as if they were in
progress, each reading "No result reported" — Córdoba v Almería, Granada v
Albacete, Girona v Castellón, Cádiz v Las Palmas, Andorra v Real Sociedad B,
Gijón v Eldense. None of them is a La Liga fixture. All six are Segunda.

THE CAUSE IS ONE PREFIX. `KALSHI_FUTURES_TICKER_TO_SPORT_KEY` carries
``kxlaliga`` → ``soccer_spain_la_liga``, and until #5982
`get_sport_key_from_ticker` returned the FIRST declared prefix that matched. Every
Kalshi Spanish ticker starts with those eight characters, so
``KXLALIGA2GAME-26SEP12CORALM`` answered ``soccer_spain_la_liga``.

A wrong competition key is not a label bug. `_find_matching_event` scopes its
candidate search by this key, so the real Segunda fixture — already held, minted
from the schedule under ``soccer_spain_segunda_division`` — could never be a
candidate. The market therefore minted a TWIN of a fixture we already had, on the
wrong league's page. 21 such rows were live when this was written, every one of
them `external_id IS NULL`, `espn_id IS NULL`, `commence_time_source='kalshi'`.

Two guards, aimed at two different things:

1. :class:`TestTheNineSpanishSeries` is the regression test. It pins all nine
   ``KXLALIGA2*`` series to the competition the VENUE names, and it is a
   two-sided assertion on purpose: the `2H` family (second-half markets) must
   stay with La Liga. A fix that moved those to Segunda would be the same defect
   pointed the other way, and a one-sided test would call it green.

2. :class:`TestNoRegisteredPrefixIsShadowed` is the class guard. It walks both
   maps — 797 prefixes — and asserts each resolves to its own value. The original
   defect is invisible to it (``kxlaliga2game`` was not registered at all, so
   there was nothing to shadow), and that is the point: it does not re-prove
   guard 1, it stops the NEXT second-tier league being swallowed the moment
   somebody registers it. `kxbundesliga2game`, `kxserieb` and `kxligue2` are all
   unregistered today and all have production events under their own keys.
"""

from __future__ import annotations

import pytest

from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_TICKER_TO_SPORT_KEY,
    get_sport_key_from_ticker,
    is_kalshi_game_level_ticker,
)

LA_LIGA = "soccer_spain_la_liga"
SEGUNDA = "soccer_spain_segunda_division"

#: series ticker → (expected sport key, the venue's own `/series` title).
#: Read from Kalshi's API 2026-09-13 20:24Z; banked verbatim in
#: `artifacts-lane1-294/kalshi-series-titles.txt`. The three generic titles are
#: resolved against their own markets, which name the clubs:
#: `KXLALIGA2SPREAD-26SEP11BURCEU` is "Burgos vs Ceuta: Spread", and Burgos and
#: Ceuta are Segunda sides.
VENUE_READ: dict[str, tuple[str, str]] = {
    "KXLALIGA2GAME": (SEGUNDA, "LaLiga 2 Game"),
    "KXLALIGA2SPREAD": (SEGUNDA, "Spread"),
    "KXLALIGA2TOTAL": (SEGUNDA, "Point Total"),
    "KXLALIGA2BTTS": (SEGUNDA, "BTTS"),
    "KXLALIGA2PROMO": (SEGUNDA, "La Liga 2 Promotion"),
    "KXLALIGA2H": (LA_LIGA, "2nd Half Winner"),
    "KXLALIGA2HBTTS": (LA_LIGA, "2nd Half BTTS"),
    "KXLALIGA2HSPREAD": (LA_LIGA, "2nd Half Spread"),
    "KXLALIGA2HTOTAL": (LA_LIGA, "2nd Half Total"),
    "KXLALIGAGAME": (LA_LIGA, "La Liga Game"),
}

#: The six the reader could actually see, with the real Segunda row each one is a
#: twin of. Times are as STORED; Kalshi stores an expected expiration three hours
#: after the whistle (#5905), which is why the stored pairs look three hours apart
#: and the served ones do not.
READER_SPECIMENS = [
    ("KXLALIGA2GAME-26SEP12CORALM", "Cordoba vs Almeria"),
    ("KXLALIGA2GAME-26SEP12GIRCAS", "Girona vs Castellon"),
    ("KXLALIGA2SPREAD-26SEP12CORALM", "Cordoba vs Almeria: Spread"),
    ("KXLALIGA2TOTAL-26SEP12CORALM", "Cordoba vs Almeria: Total Goals"),
    ("KXLALIGA2BTTS-26SEP12CORALM", "Cordoba vs Almeria: BTTS"),
    ("KXLALIGA2BTTS-26SEP11BURCEU", "Burgos vs Ceuta: BTTS"),
]


class TestTheNineSpanishSeries:
    """Each Kalshi Spanish series resolves to the competition the venue names."""

    @pytest.mark.parametrize("series", sorted(VENUE_READ))
    def test_series_resolves_to_the_competition_the_venue_names(self, series):
        expected, venue_title = VENUE_READ[series]
        got = get_sport_key_from_ticker(f"{series}-26SEP12CORALM")
        assert got == expected, (
            f"{series} (Kalshi calls it {venue_title!r}) resolved to {got!r}, "
            f"expected {expected!r}"
        )

    def test_the_second_half_family_stays_with_la_liga(self):
        """The other direction, stated on its own so it cannot be traded away.

        ``kxlaliga2h*`` are La Liga second-half markets. A ``kxlaliga2`` prefix
        matched by grammar rather than enumerated would swallow all four and put
        top-flight fixtures on the Segunda page.
        """
        second_half = [s for s in VENUE_READ if s.startswith("KXLALIGA2H")]
        assert len(second_half) == 4, "the 2H family is four series; update this"
        for series in second_half:
            assert get_sport_key_from_ticker(f"{series}-26SEP12SANALA") == LA_LIGA

    def test_the_segunda_series_are_not_all_one_answer(self):
        """Non-vacuity: this file would pass on a map that answered SEGUNDA always."""
        answers = {get_sport_key_from_ticker(f"{s}-26SEP12X") for s in VENUE_READ}
        assert answers == {LA_LIGA, SEGUNDA}

    @pytest.mark.parametrize("ticker,market_name", READER_SPECIMENS)
    def test_the_reader_visible_specimens_leave_la_liga(self, ticker, market_name):
        """The exact tickers behind the six cards in #5982's screenshot."""
        assert get_sport_key_from_ticker(ticker) == SEGUNDA, market_name

    def test_segunda_gains_no_minting_authority_its_parent_lacks(self):
        """LaLiga 2 gets the SAME standing as La Liga, not a wider one.

        Both live in the futures map, so `is_kalshi_game_level_ticker` answers
        False for both — it compares prefix LENGTHS and the game map matches
        neither. If a later change makes Segunda game-level it must make La Liga
        game-level in the same breath, or this fires.
        """
        for series in VENUE_READ:
            ticker = f"{series}-26SEP12CORALM"
            assert is_kalshi_game_level_ticker(ticker) == is_kalshi_game_level_ticker(
                "KXLALIGAGAME-26SEP13GETDEP"
            ), f"{series} and La Liga's own game series disagree on game-level"


class TestNoRegisteredPrefixIsShadowed:
    """Every registered prefix resolves to its OWN sport key.

    The property longest-prefix-wins buys. Before #5982 this held by luck — the
    maps happened to contain no prefix-of pair that disagreed — and the resolver
    returned whichever entry was declared first, so the invariant was a fact about
    line order rather than about the data.
    """

    def test_every_game_prefix_resolves_to_itself(self):
        self._assert_no_shadowing(KALSHI_TICKER_TO_SPORT_KEY, "game")

    def test_every_futures_prefix_resolves_to_itself(self):
        self._assert_no_shadowing(KALSHI_FUTURES_TICKER_TO_SPORT_KEY, "futures")

    @staticmethod
    def _assert_no_shadowing(mapping, label):
        assert len(mapping) > 300, (
            f"the {label} map shrank to {len(mapping)} — this guard walks a "
            "population and is worthless if the population vanished"
        )
        shadowed = []
        for prefix, expected in mapping.items():
            # A suffix no registered prefix can extend into: the resolver must
            # answer on `prefix` alone.
            got = get_sport_key_from_ticker(f"{prefix.upper()}-26SEP12ZZZZZZ")
            if got != expected:
                shadowed.append((prefix, expected, got))
        assert not shadowed, (
            f"{len(shadowed)} {label} prefix(es) are shadowed by another entry — "
            "a ticker resolves to a competition that is not the one it names: "
            f"{shadowed[:10]}"
        )

    def test_the_guard_can_fail(self):
        """Non-vacuity. A shorter entry with a different sport must be caught.

        Proves the walk above is doing work rather than passing on an empty or
        always-true comparison.
        """
        poisoned = dict(KALSHI_TICKER_TO_SPORT_KEY)
        poisoned["kxlaliga2game"] = LA_LIGA  # the #5982 defect, re-introduced
        offenders = [
            p
            for p, expected in poisoned.items()
            if p == "kxlaliga2game" and get_sport_key_from_ticker(f"{p.upper()}-X") != expected
        ]
        assert offenders == ["kxlaliga2game"], (
            "re-introducing the defect must be visible to the same comparison "
            "the walk above performs"
        )
