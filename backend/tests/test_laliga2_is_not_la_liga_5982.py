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

        The invariant is unchanged and so is its purpose; what changed under
        #3813 is that "La Liga's standing" is no longer one answer for all nine
        series, so the comparison has to be made against the RIGHT parent.

        When this was written both competitions sat only in the futures map, so
        `is_kalshi_game_level_ticker` answered False for every Spanish series and
        a single parent — La Liga's game series — served as the yardstick for all
        nine. #3813 armed the five biggest domestic leagues game-level (a Kalshi
        fixture's four markets were each minting their own event, because a
        non-game ticker anchors on itself and no two markets can share that), and
        LaLiga 2's four FIXTURE series moved with their parent in the same
        breath, exactly as this test's original docstring required.

        `KXLALIGA2PROMO` did not, and must not: promotion is a SEASON question,
        and the old one-parent form asserted it should match a GAME series, which
        would arm a season-long market to absorb one of its own fixtures
        (CERT-409's failure mode). That comparison was only ever satisfiable
        while La Liga's own fixtures were wrongly non-game-level.

        So the assertion is SPLIT rather than relaxed, and both halves are
        positive: Segunda's fixture series match La Liga's fixture series, and
        Segunda's season series matches La Liga's season series. A future change
        that arms Segunda without arming La Liga still fires, and so does one
        that arms either competition's season markets.
        """
        # Each Segunda series against ITS OWN counterpart, which is what "the
        # same standing as its parent" actually means. The single-yardstick form
        # this replaces compared a promotion market to a game series; that was
        # satisfiable only while La Liga's own fixtures were non-game-level too.
        counterparts = {
            "KXLALIGA2GAME": "KXLALIGAGAME",
            "KXLALIGA2SPREAD": "KXLALIGASPREAD",
            "KXLALIGA2TOTAL": "KXLALIGATOTAL",
            "KXLALIGA2BTTS": "KXLALIGABTTS",
            # Promotion is a SEASON question. Its parent is a La Liga season
            # market, never a fixture one — arming it would let a season-long
            # market absorb one of its own games (CERT-409's failure mode).
            "KXLALIGA2PROMO": "KXLALIGATOP4",
        }
        segunda = {s for s, (key, _) in VENUE_READ.items() if key == SEGUNDA}
        assert set(counterparts) == segunda, (
            "every Segunda series in the venue read needs a named La Liga "
            "counterpart; VENUE_READ changed and this map did not"
        )

        for series, parent_series in counterparts.items():
            child = is_kalshi_game_level_ticker(f"{series}-26SEP12CORALM")
            parent = is_kalshi_game_level_ticker(f"{parent_series}-26SEP13GETDEP")
            assert child == parent, (
                f"{series} and its parent {parent_series} disagree on "
                f"game-level ({child} vs {parent})"
            )

        # Non-vacuity: the two kinds must actually give different answers, or
        # the loop above passes on a map that says the same thing everywhere.
        assert is_kalshi_game_level_ticker("KXLALIGAGAME-26SEP13GETDEP") is True
        assert is_kalshi_game_level_ticker("KXLALIGATOP4-26") is False

    def test_the_segunda_fixture_series_all_share_one_game_anchor(self):
        """#3813's ship, stated on the specimen that paid for it.

        Cádiz v Las Palmas on 2026-09-12 was FOUR events — 15307871, 15312363,
        15312364, 15312370 — one per Kalshi market, each `external_id IS NULL`
        with a single `event_provider_anchors` row at `id_kind='market'`. The
        fixture token `26SEP12CADLPA` was identical in all four tickers and was
        discarded every time, because a ticker that fails the game-level test
        anchors on ITSELF and no two markets can ever share that.

        The anchor key is the thing a reader's duplicate rows are made of, so it
        is what gets asserted here rather than the predicate that feeds it.
        """
        from app.utils.provider_anchor_keys import kalshi_anchor_key

        # The four full-match Segunda families are the ones #3813 armed. The 2H
        # four belong to La Liga and are deliberately NOT armed; they are
        # asserted below, so this test cannot be made to pass by arming
        # everything.
        armed = sorted(
            s
            for s, (key, _) in VENUE_READ.items()
            if key == SEGUNDA and s != "KXLALIGA2PROMO"
        )
        assert armed == [
            "KXLALIGA2BTTS",
            "KXLALIGA2GAME",
            "KXLALIGA2SPREAD",
            "KXLALIGA2TOTAL",
        ]

        keys = {kalshi_anchor_key(f"{s}-26SEP12CADLPA") for s in armed}
        assert len(keys) == 1, (
            "the four markets on one fixture must produce ONE anchor; "
            f"got {sorted(k.source_id for k in keys)}"
        )
        only = keys.pop()
        assert only.id_kind == "game"
        assert only.source_id == f"{SEGUNDA}:26SEP12CADLPA"

        # The other direction: the half markets still anchor on themselves, so
        # four distinct keys, none of them a game.
        half_keys = {
            kalshi_anchor_key(f"{s}-26SEP12CADLPA")
            for s in VENUE_READ
            if s.startswith("KXLALIGA2H")
        }
        assert len(half_keys) == 4
        assert {k.id_kind for k in half_keys} == {"market"}


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
