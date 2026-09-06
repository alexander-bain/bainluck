"""#3672 — a sport we hold no abbreviations for stops borrowing the NBA's.

`KXWTACHALLENGERMATCH-26SEP06DENLAC` is Kalshi's WTA Challenger market
"Dencheva vs Lachinova". We minted an event from it called **Nuggets vs
Clippers**, and it rendered on `/sport/tennis/wta` (live/080, #2878).

The mechanism was a default, not a missing entry. `_SPORT_ABBREV_SUFFIX` was
derived with `.get(sport_key, "")`, and `""` is not "no namespace" — it is the
BARE namespace, which `_BARE_ABBREV_OWNER` records as the NBA's. So every ticker
prefix whose sport key was not spelled out in `_SPORT_KEY_TO_ABBREV_SUFFIX`
asked the NBA what `DEN` and `LAC` meant. 143 of the 368 registered prefixes did
that; about 30 of them are actually NBA.

The repair flips the default to a sentinel that resolves nothing, and makes the
NBA's ownership of the bare namespace explicit rather than incidental. These
tests pin the flip, not the list: a new sport added to
`KALSHI_TICKER_TO_SPORT_KEY` must inherit "we do not know", never "ask the NBA".
"""

import pytest

from app.utils.prediction_market_matching import (
    _ABBREV_NAMESPACE_UNKNOWN,
    _BARE_ABBREV_OWNER,
    _KALSHI_TEAM_ABBREVS,
    _SPORT_ABBREV_SUFFIX,
    _SPORT_KEY_TO_ABBREV_SUFFIX,
    _TICKER_TO_SPORT_PREFIX,
    _resolve_team_abbrev,
    extract_team_codes_from_ticker,
    extract_teams_from_ticker,
)


class TestTheProductionSpecimen:
    def test_the_wta_challenger_ticker_no_longer_mints_an_nba_game(self):
        """Event 15305644 on production, 2026-09-06: `Nuggets` vs `Clippers`,
        `sport_key = tennis_wta`, minted from this ticker."""
        assert extract_teams_from_ticker(
            "KXWTACHALLENGERMATCH-26SEP06DENLAC"
        ) is None

    @pytest.mark.parametrize("ticker", [
        "KXATPMATCH-26SEP06DENLAC",
        "KXITFWMATCH-26SEP06DENLAC",
        "KXCS2GAME-26SEP06DENLAC",
        "KXFACUPGAME-26JAN10DENLAC",
        "KXBOXINGFIGHT-26SEP06DENLAC",
    ])
    def test_no_other_sport_answers_with_nba_teams_either(self, ticker):
        """The same two codes across five unrelated sports. Each of these
        prefixes resolved `Nuggets`/`Clippers` before the default flipped."""
        assert extract_teams_from_ticker(ticker) is None


class TestTheNbaKeepsItsOwnVocabulary:
    @pytest.mark.parametrize("ticker,expected", [
        ("KXNBAGAME-26FEB21DETCHI", ("Pistons", "Bulls")),
        ("KXNFLGAME-26SEP20JACDEN", ("Jaguars", "Broncos")),
        ("KXMLBGAME-26MAR281910CWSMIL", ("White Sox", "Brewers")),
        ("KXNHLGAME-26JAN10BOSTOR", ("Bruins", "Maple Leafs")),
    ])
    def test_the_four_sports_with_a_vocabulary_are_untouched(
        self, ticker, expected,
    ):
        assert extract_teams_from_ticker(ticker) == expected

    def test_the_codes_still_travel_with_the_names(self):
        """`extract_team_codes_from_ticker` is the one parse (#2060); the code
        half is what disambiguates Kalshi's truncated outcome labels."""
        assert extract_team_codes_from_ticker("KXNBAGAME-26FEB21DETCHI") == (
            ("det", "Pistons"), ("chi", "Bulls"),
        )

    def test_the_nba_owns_the_bare_namespace_in_writing(self):
        """It was relying on the old `""` default, which is precisely what made
        the default unsafe to change."""
        assert _SPORT_KEY_TO_ABBREV_SUFFIX["basketball_nba"] == ""
        assert _SPORT_ABBREV_SUFFIX["kxnbagame"] == ""


class TestTheDefaultItself:
    def test_an_unlisted_sport_key_resolves_nothing(self):
        """The test that survives every future prefix Kalshi ships: the DEFAULT
        is 'we do not know', so a sport nobody has written a namespace for
        cannot borrow one."""
        assert _SPORT_KEY_TO_ABBREV_SUFFIX.get("a_sport_nobody_registered") is None
        for abbrev in ("den", "lac", "bos", "chi", "nyy"):
            assert _resolve_team_abbrev(abbrev, _ABBREV_NAMESPACE_UNKNOWN) is None

    def test_the_unknown_sentinel_owns_no_keys(self):
        """If a key were ever suffixed with it, the sentinel would stop being a
        refusal and become a fifth vocabulary."""
        assert not [
            k for k in _KALSHI_TEAM_ABBREVS
            if k.endswith(_ABBREV_NAMESPACE_UNKNOWN)
        ]
        assert _ABBREV_NAMESPACE_UNKNOWN not in _BARE_ABBREV_OWNER.values()

    def test_every_registered_prefix_still_has_a_namespace(self):
        """The derivation must stay total — a prefix missing from
        `_SPORT_ABBREV_SUFFIX` raises rather than refusing, and the two failure
        modes must not be confused."""
        for prefix in _TICKER_TO_SPORT_PREFIX:
            assert prefix in _SPORT_ABBREV_SUFFIX

    def test_only_basketball_prefixes_read_the_bare_namespace(self):
        """The count is the finding. Before the flip, 143 prefixes read the
        NBA's vocabulary; ~30 of them are NBA."""
        bare = {
            prefix for prefix, suffix in _SPORT_ABBREV_SUFFIX.items()
            if suffix == ""
        }
        assert bare
        for prefix in bare:
            assert _TICKER_TO_SPORT_PREFIX[prefix] == "basketball_nba", prefix
