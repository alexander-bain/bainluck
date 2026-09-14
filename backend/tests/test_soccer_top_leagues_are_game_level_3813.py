"""#3813 — one Kalshi fixture was minting one event PER MARKET.

WHAT A READER SAW. `https://bainluck.com/sports/soccer_spain_la_liga` and its
Segunda neighbour carried fixtures that had already been played, sitting in a
*Live & Paused* rail reading "No result reported", beside the real fixture with
its real score. Cádiz v Las Palmas on 2026-09-12 was FOUR such rows:

    15307871  KXLALIGA2GAME-26SEP12CADLPA    created 2026-09-08 14:52Z
    15312363  KXLALIGA2TOTAL-26SEP12CADLPA   created 2026-09-14 00:53Z
    15312364  KXLALIGA2SPREAD-26SEP12CADLPA  created 2026-09-14 01:05Z
    15312370  KXLALIGA2BTTS-26SEP12CADLPA    created 2026-09-14 02:05Z

Every one `external_id IS NULL`, `espn_id IS NULL`, `status='suspended'`, each
with a single `event_provider_anchors` row at `id_kind='market'`. The fixture
token `26SEP12CADLPA` is identical in all four tickers.

THE CAUSE IS AN ABSENCE, WHICH IS WHY NOTHING POINTED AT IT. The game map held
`kxmlsgame` and six cup prefixes and NOT ONE of `kxeplgame`, `kxlaligagame`,
`kxserieagame`, `kxbundesligagame`, `kxligue1game` — the five biggest domestic
leagues in the world appeared only as their bare season prefixes in the FUTURES
map. So `is_kalshi_game_level_ticker` answered False for all 142 live series
across them (measured by calling it, 2026-09-14), `kalshi_anchor_key` degraded
to `id_kind='market'` keyed on the RAW TICKER — a key no two markets can ever
share — and each market therefore arrived with nothing to absorb against. Ruling
048 correctly refuses to absorb an id-less claim (gotcha #32), so the auto-create
fallback minted a separate event. Per market, not per fixture.

Note what is NOT wrong with those rows: the competition key is right (#5982 fixed
that on 09-13, and the three post-fix Cádiz rows are correctly tagged Segunda),
the teams are right, the date is right. A ghost here is not a mis-parse. It is a
correct row that should never have been a second row, which is why every fix
aimed at the row's CONTENTS — the invented kickoff, the competition label — left
the population intact.

WHAT THIS FILE PINS, in the order the defect travels:

1. :class:`TestTheFiveLeaguesAreGameLevel` — the predicate, per league.
2. :class:`TestOneFixtureOneAnchor` — the consequence that matters: the markets
   on one fixture produce ONE shared game anchor. This is the ship. It is
   asserted on the anchor key rather than the predicate because the anchor is
   what a duplicate row is actually made of.
3. :class:`TestTheArmingIsBounded` — the other direction, and the reason this is
   a list and not a pattern. Season markets, half markets and unarmed
   second-tier leagues must NOT have moved. A false positive here is an
   absorption — one game claiming another's identity — which is strictly worse
   than the duplication being fixed.
"""

from __future__ import annotations

import pytest

from app.utils.provider_anchor_keys import kalshi_anchor_key
from app.utils.sport_keys import (
    get_sport_key_from_ticker,
    is_kalshi_game_level_ticker,
)

#: league label -> (ticker stem, expected sport key). The four full-match
#: families are `GAME`, `SPREAD`, `TOTAL`, `BTTS`; every title was read from
#: Kalshi's own `/trade-api/v2/series/<ticker>` on 2026-09-14 and each returned
#: `category: Sports`, `tags: ['Soccer']` — "La Liga Game", "English Premier
#: League Spread", "Serie A Total", "Bundesliga BTTS", "Ligue 1 Game",
#: "LaLiga 2 Game" (notice 26: the venue answers "does this exist", not us).
LEAGUES: dict[str, tuple[str, str]] = {
    "Premier League": ("KXEPL", "soccer_epl"),
    "La Liga": ("KXLALIGA", "soccer_spain_la_liga"),
    "LaLiga 2": ("KXLALIGA2", "soccer_spain_segunda_division"),
    "Serie A": ("KXSERIEA", "soccer_italy_serie_a"),
    "Bundesliga": ("KXBUNDESLIGA", "soccer_germany_bundesliga"),
    "Ligue 1": ("KXLIGUE1", "soccer_france_ligue_one"),
}

FAMILIES = ("GAME", "SPREAD", "TOTAL", "BTTS")

#: The real fixture token from the specimen above: 2026-09-12, Cádiz v Las
#: Palmas. Shared by all four of that fixture's tickers.
FIXTURE = "26SEP12CADLPA"


def _cases():
    for league, (stem, key) in LEAGUES.items():
        for family in FAMILIES:
            yield pytest.param(
                f"{stem}{family}-{FIXTURE}", key, id=f"{league}-{family}"
            )


class TestTheFiveLeaguesAreGameLevel:
    @pytest.mark.parametrize("ticker,sport_key", list(_cases()))
    def test_ticker_is_game_level(self, ticker, sport_key):
        assert is_kalshi_game_level_ticker(ticker) is True

    @pytest.mark.parametrize("ticker,sport_key", list(_cases()))
    def test_ticker_keeps_its_competition(self, ticker, sport_key):
        """Arming must not move a league, which is #5982's defect reversed.

        LaLiga 2's four families MOVED from the futures map to the game map to
        get here — a tie between the maps is not game-level, so a copy in both
        would have been inert. The move is only safe because
        `get_sport_key_from_ticker` reads the game map first, and that is what
        this asserts.
        """
        assert get_sport_key_from_ticker(ticker) == sport_key


class TestOneFixtureOneAnchor:
    """The ship. Four markets on one fixture, one anchor between them."""

    @pytest.mark.parametrize("league", sorted(LEAGUES))
    def test_the_four_markets_share_one_game_anchor(self, league):
        stem, sport_key = LEAGUES[league]
        keys = {
            kalshi_anchor_key(f"{stem}{family}-{FIXTURE}") for family in FAMILIES
        }
        assert len(keys) == 1, (
            f"{league}: the four markets on one fixture must produce ONE "
            f"anchor; got {sorted(k.source_id for k in keys)}"
        )
        only = keys.pop()
        assert only.id_kind == "game"
        assert only.source_id == f"{sport_key}:{FIXTURE}"

    def test_two_different_fixtures_never_share_an_anchor(self):
        """The absorption direction, which is the dangerous one.

        Sharing a key is the whole mechanism, so a mutant that returned one
        constant key would satisfy every assertion above. This is what refuses
        it.
        """
        a = kalshi_anchor_key(f"KXLALIGAGAME-{FIXTURE}")
        b = kalshi_anchor_key("KXLALIGAGAME-26SEP12BARATH")
        c = kalshi_anchor_key(f"KXSERIEAGAME-{FIXTURE}")
        assert a.source_id != b.source_id, "same league, different fixtures"
        assert a.source_id != c.source_id, "same fixture token, different league"

    def test_before_this_fix_the_four_anchors_were_all_different(self):
        """Non-vacuity, stated as the defect rather than as a number.

        The `market` branch is still reachable — it is what every unarmed ticker
        gets — so the failure this file exists to prevent can be exhibited
        rather than described: four tickers, four keys, no two alike.
        """
        unarmed = {
            kalshi_anchor_key(f"KXLALIGA2H{suffix}-{FIXTURE}")
            for suffix in ("", "BTTS", "SPREAD", "TOTAL")
        }
        assert len(unarmed) == 4
        assert {k.id_kind for k in unarmed} == {"market"}


class TestTheArmingIsBounded:
    """A false positive here is an absorption. These are the refusals."""

    @pytest.mark.parametrize(
        "ticker",
        [
            # Season-long questions. Arming one lets it absorb its own fixtures
            # (CERT-409's failure mode, which is why the predicate is positive
            # and asked directly rather than inferred from a date token).
            "KXEPLTOP4-26",
            "KXEPLRELEGATION-26",
            "KXEPLLEADER-26",
            "KXLALIGATOP4-26",
            "KXLALIGA2PROMO-26",
            "KXSERIEATOP4-26",
            "KXBUNDESLIGARELEGATION-26",
            "KXLIGUE1TOP4-26",
        ],
    )
    def test_season_markets_are_not_game_level(self, ticker):
        assert is_kalshi_game_level_ticker(ticker) is False

    @pytest.mark.parametrize(
        "ticker",
        [
            # THE TRAP #5982 NAMED, AND IT IS STILL THE TRAP. A `kxlaliga2`
            # prefix matched by grammar swallows all four of these, and they are
            # La Liga SECOND-HALF markets — the same defect pointed the other
            # way. They stay non-game-level and stay with their own competition.
            "KXLALIGA2H-26SEP12SANALA",
            "KXLALIGA2HBTTS-26SEP12SANALA",
            "KXLALIGA2HSPREAD-26SEP12SANALA",
            "KXLALIGA2HTOTAL-26SEP12SANALA",
            # The half families across the other leagues are per-fixture too and
            # are a named follow-up, NOT this change. Pinned so that arming them
            # is a decision somebody makes on purpose.
            "KXEPL1H-26SEP12ARSMCI",
            "KXEPL2HTOTAL-26SEP12ARSMCI",
            "KXSERIEA1HBTTS-26SEP12JUVINT",
            "KXBUNDESLIGA1HSPREAD-26SEP12BAYDOR",
        ],
    )
    def test_half_markets_are_not_game_level(self, ticker):
        assert is_kalshi_game_level_ticker(ticker) is False

    def test_the_second_half_family_keeps_its_competition(self):
        """`KXLALIGA2H*` is La Liga, not Segunda — #5982's two-sided assertion."""
        for suffix in ("", "BTTS", "SPREAD", "TOTAL"):
            ticker = f"KXLALIGA2H{suffix}-26SEP12SANALA"
            assert get_sport_key_from_ticker(ticker) == "soccer_spain_la_liga"

    def test_bundesliga_2_is_not_armed_and_is_not_swallowed(self):
        """The next second-tier league, held back deliberately.

        "Bundesliga 2 Game" is a real series with 153 live markets, and it has
        the same duplication. It is NOT armed here because it needs the
        competition-identity half FIRST — the way #5982 did for LaLiga 2 — and
        there is no `soccer_germany_bundesliga2` key to arm it to. Arming it
        without that would file second-division fixtures on the Bundesliga page,
        which is the defect #5982 existed to fix.

        What must hold meanwhile: `kxbundesligagame` must not SWALLOW it. The
        two diverge at the character after `kxbundesliga`, so the top-flight
        prefix cannot match the second-tier ticker.
        """
        second = "KXBUNDESLIGA2GAME-26SEP12HSVSGF"
        assert is_kalshi_game_level_ticker(second) is False
        assert get_sport_key_from_ticker(second) == "soccer_germany_bundesliga"

    def test_arming_did_not_reach_beyond_the_named_families(self):
        """Prop and stat series on the armed leagues stay unarmed.

        Enumerated rather than matched by grammar, so a later `kxepl`-shaped
        pattern cannot quietly promote the whole league.
        """
        for ticker in (
            "KXEPLCORNERS-26SEP12ARSMCI",
            "KXEPLFIRSTGOAL-26SEP12ARSMCI",
            "KXEPLSCORE-26SEP12ARSMCI",
            "KXEPLTEAMTOTAL-26SEP12ARSMCI",
            "KXLALIGAGOAL-26SEP12BARATH",
            "KXLALIGATCORNERS-26SEP12BARATH",
            "KXSERIEAFTTS-26SEP12JUVINT",
        ):
            assert is_kalshi_game_level_ticker(ticker) is False, ticker
