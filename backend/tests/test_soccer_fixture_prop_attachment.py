"""Soccer fixture-prop slices must be game-level, not futures.

Measured on production `c1397139`, 2026-09-01: for the SAME MLS fixture,
``KXMLSGAME`` / ``BTTS`` / ``SPREAD`` / ``TOTAL`` attached to their event at
~78%, while ``KXMLS1HSPREAD``, ``KXMLS1HTOTAL``, ``KXMLS1HBTTS``, ``KXMLS1H``,
``KXMLSFTTS``, ``KXMLSSCORE`` and ``KXMLSTEAMTOTAL`` sat at 0 — 476 markets,
1 attached.

The cause is prefix precedence. ``kxmls`` is a *futures* prefix, so an MLS
series not explicitly listed as game-level fell through to the futures map and
read as a season-long market. The matcher's SQL candidate set is built from
``KALSHI_GAME_TICKER_PREFIXES`` (``_KALSHI_TICKER_LIKE_PATTERNS`` in
``tasks/prediction_market_matching.py``), so such a market is never even a
candidate — it cannot attach, at any confidence.

The paired risk this file also guards is over-reach: the naive prefix read
assigns SECOND-DIVISION and Women's-competition series to the top-flight sport
key. Those are different competitions with their own fixtures. Attaching them
to a top-flight event would be an absorption, not a fix.
"""

import pytest

from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_TICKER_TO_SPORT_KEY,
    SPORT_LEAGUE_MAP,
    _SOCCER_ESPN_LEAGUE_STEMS,
    _SOCCER_FIXTURE_PROP_SUFFIXES,
    get_sport_key_from_ticker,
    is_kalshi_game_level_ticker,
)

# The families measured at 0 attach on production.
MLS_DARK_FAMILIES = [
    "kxmls1hspread", "kxmls1htotal", "kxmls1hbtts", "kxmls1h",
    "kxmlsftts", "kxmlsscore", "kxmlsteamtotal",
]

# Series that must NOT inherit a top-flight sport key: different competitions.
DIFFERENT_COMPETITIONS = [
    ("kxlaliga2game", "Albacete vs Almeria — Segunda Division"),
    ("kxlaliga2total", "Albacete vs Oviedo: Total Goals — Segunda Division"),
    ("kxbundesliga2game", "Bielefeld vs Bochum — 2. Bundesliga"),
    ("kxbundesliga2total", "Bielefeld vs Cottbus: Total Goals — 2. Bundesliga"),
    ("kxbrasileirobgame", "AC Goianiense vs Athletic Club Sjdr — Serie B"),
    ("kxbrasileirocgame", "Amazonas vs Botafogo — Serie C"),
    ("kxuclwgame", "Women's Champions League"),
]


class TestDarkPropFamiliesAreGameLevel:
    """The named ship: a prop slice lands on the same event as the moneyline."""

    @pytest.mark.parametrize("series", MLS_DARK_FAMILIES)
    def test_family_is_a_game_ticker_prefix(self, series):
        # Membership here is what puts the series in the matcher's SQL
        # candidate set. Without it the market is never considered.
        assert series in KALSHI_GAME_TICKER_PREFIXES

    @pytest.mark.parametrize("series", MLS_DARK_FAMILIES)
    def test_family_resolves_to_mls_not_futures(self, series):
        ticker = f"{series.upper()}-26SEP01ATLCLT"
        assert get_sport_key_from_ticker(ticker) == "soccer_usa_mls"
        assert is_kalshi_game_level_ticker(ticker) is True

    def test_the_moneyline_and_its_props_share_one_sport_key(self):
        """Same fixture, same league — the whole point of the ship."""
        keys = {
            get_sport_key_from_ticker(f"{s.upper()}-26SEP01ATLCLT")
            for s in ["kxmlsgame", *MLS_DARK_FAMILIES]
        }
        assert keys == {"soccer_usa_mls"}


class TestEveryEspnLeagueGetsTheSameSlices:
    """No league silently gets a shorter prop list than its neighbour."""

    @pytest.mark.parametrize("stem,sport_key", sorted(_SOCCER_ESPN_LEAGUE_STEMS.items()))
    def test_each_stem_has_every_prop_suffix(self, stem, sport_key):
        missing = [
            f"{stem}{suf}" for suf in _SOCCER_FIXTURE_PROP_SUFFIXES
            if KALSHI_TICKER_TO_SPORT_KEY.get(f"{stem}{suf}") != sport_key
        ]
        assert not missing, f"{stem}: prop families absent or mis-keyed: {missing}"

    def test_every_stem_league_has_an_espn_fixture_to_attach_to(self):
        """A prop slice needs an ESPN fixture; else this is new authority, not
        attachment — which is explicitly out of scope for this change."""
        unmapped = sorted(
            sk for sk in _SOCCER_ESPN_LEAGUE_STEMS.values() if sk not in SPORT_LEAGUE_MAP
        )
        assert not unmapped, f"stems whose league has no ESPN mapping: {unmapped}"


class TestDivisionDiscipline:
    """Over-reach guard — the expensive direction."""

    @pytest.mark.parametrize("series,why", DIFFERENT_COMPETITIONS)
    def test_other_competitions_are_not_game_level_for_the_top_flight(self, series, why):
        assert series not in KALSHI_TICKER_TO_SPORT_KEY, (
            f"{series} is a different competition ({why}); attaching it to a "
            "top-flight fixture would be an absorption"
        )
        assert series not in KALSHI_GAME_TICKER_PREFIXES

    def test_second_half_is_kept_and_is_not_a_second_division(self):
        # `2h` reads as SECOND HALF — verified against real market names:
        # "Alaves vs Getafe: Second Half Winner" (La Liga, not Segunda).
        assert KALSHI_TICKER_TO_SPORT_KEY["kxlaliga2h"] == "soccer_spain_la_liga"
        assert KALSHI_TICKER_TO_SPORT_KEY["kxbundesliga2h"] == "soccer_germany_bundesliga"


class TestNoPrefixCollisions:
    """The maps must share no exact key — CERT-409 / Q440 tie rule."""

    def test_game_and_futures_maps_share_no_exact_key(self):
        collisions = set(KALSHI_TICKER_TO_SPORT_KEY) & set(KALSHI_FUTURES_TICKER_TO_SPORT_KEY)
        assert not collisions, f"exact key in both maps — tie is not game-level: {collisions}"

    def test_generated_series_never_shadow_a_different_competition(self):
        generated = {
            f"{stem}{suf}"
            for stem in _SOCCER_ESPN_LEAGUE_STEMS
            for suf in _SOCCER_FIXTURE_PROP_SUFFIXES
        }
        for other, why in DIFFERENT_COMPETITIONS:
            shadowing = sorted(g for g in generated if other.startswith(g))
            assert not shadowing, f"{other} ({why}) is prefix-captured by {shadowing}"


class TestControl:
    """Green in both arms — proves the suite reads the real maps."""

    def test_the_already_working_families_still_work(self):
        for series in ["kxmlsgame", "kxmlsbtts", "kxmlsspread", "kxmlstotal"]:
            assert series in KALSHI_GAME_TICKER_PREFIXES
            assert KALSHI_TICKER_TO_SPORT_KEY[series] == "soccer_usa_mls"

    def test_an_unrelated_sport_is_untouched(self):
        assert KALSHI_TICKER_TO_SPORT_KEY["kxnbagame"] == "basketball_nba"
        assert KALSHI_TICKER_TO_SPORT_KEY["kxnflgame"] == "americanfootball_nfl"
