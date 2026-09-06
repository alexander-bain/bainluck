"""#3446 — the rest of the Kalshi soccer cups stop being filed as court cases.

#3414 mapped the Slovak and KNVB cup legs. It could not reach the other 88 series
prefixes, and those carried 1,615 of the 1,908 rows that production was holding in
`llm_sport_category='legal'` — Conference League, Europa League, DFB-Pokal, Coppa
Italia, Taca de Portugal, the World Cup correct-score legs and eighteen more.

Why the ticker has to answer it: the market name is
"Ajax vs Sion: Regulation Time BTTS". Nothing in that string says football, and the
"Regulation Time" token is exactly what used to drag it into the legal bucket. Step 1
of `_categorize_kalshi_market` (ticker prefix) is the only step that can settle it
before the name is read.

Why these prefixes and not others: each one was confirmed against Kalshi's own
`/series/<ticker>` endpoint, which reports `tags: ["Soccer"]` for all 93 prefixes in
the measured population with zero exceptions (notice 26 — measure the venue, not our
mirror). The row counts below are the measured production population on 2026-09-06.

The expectations here are written literally on purpose. Deriving them from
`KALSHI_TICKER_TO_SPORT_KEY` would make the test agree with production by
construction and assert nothing.
"""

import pytest

from app.tasks.kalshi import _categorize_kalshi_market
from app.utils.sport_keys import get_sport_key_from_ticker

# (series prefix, rows it held in `legal` on 2026-09-06)
SOCCER_CUP_PREFIXES = [
    ("KXAFCCLBTTS", 4),
    ("KXAFCCLSCORE", 4),
    ("KXASEANBTTS", 3),
    ("KXASEANSPREAD", 1),
    ("KXASEANTOTAL", 1),
    ("KXCONMEBOLLIBBTTS", 7),
    ("KXCONMEBOLLIBSPREAD", 4),
    ("KXCONMEBOLLIBTOTAL", 4),
    ("KXCONMEBOLSUDBTTS", 23),
    ("KXCONMEBOLSUDSPREAD", 13),
    ("KXCONMEBOLSUDTOTAL", 13),
    ("KXCOPADOBRASILBTTS", 8),
    ("KXCOPADOBRASILSPREAD", 4),
    ("KXCOPADOBRASILTOTAL", 4),
    ("KXCOPPAITALIABTTS", 26),
    ("KXCOPPAITALIASCORE", 20),
    ("KXCOPPAITALIASPREAD", 8),
    ("KXCOPPAITALIATEAMTOTAL", 8),
    ("KXCOPPAITALIATOTAL", 8),
    ("KXDFBPOKALBTTS", 32),
    ("KXDFBPOKALSCORE", 31),
    ("KXDFBPOKALSPREAD", 17),
    ("KXDFBPOKALTEAMTOTAL", 17),
    ("KXDFBPOKALTOTAL", 17),
    ("KXEFLCUPBTTS", 58),
    ("KXEFLCUPSCORE", 3),
    ("KXEFLCUPSPREAD", 23),
    ("KXEFLCUPTEAMTOTAL", 1),
    ("KXEFLCUPTOTAL", 23),
    ("KXENGCSBTTS", 1),
    ("KXENGCSSCORE", 1),
    ("KXFRASUPERCUPBTTS", 1),
    ("KXFRASUPERCUPSPREAD", 1),
    ("KXFRASUPERCUPTEAMTOTAL", 1),
    ("KXGERSCBTTS", 1),
    ("KXGERSCSCORE", 1),
    ("KXGRECUPBTTS", 11),
    ("KXGRECUPSPREAD", 10),
    ("KXGRECUPTOTAL", 10),
    ("KXISRPLCUPBTTS", 7),
    ("KXISRPLCUPSPREAD", 7),
    ("KXISRPLCUPTOTAL", 7),
    ("KXLEAGUESCUPBTTS", 6),
    ("KXLEAGUESCUPSCORE", 6),
    ("KXLEAGUESCUPSPREAD", 4),
    ("KXLEAGUESCUPTEAMTOTAL", 4),
    ("KXLEAGUESCUPTOTAL", 4),
    ("KXSCOCUPBTTS", 8),
    ("KXSCOCUPSPREAD", 5),
    ("KXSCOCUPTOTAL", 5),
    ("KXSERIECCUPBTTS", 28),
    ("KXSERIECCUPSPREAD", 26),
    ("KXSERIECCUPTOTAL", 26),
    ("KXTACAPORTBTTS", 46),
    ("KXTACAPORTSPREAD", 39),
    ("KXTACAPORTTOTAL", 39),
    ("KXUECLBTTS", 136),
    ("KXUECLSCORE", 111),
    ("KXUECLSPREAD", 68),
    ("KXUECLTEAMTOTAL", 92),
    ("KXUECLTOTAL", 68),
    ("KXUEFASCBTTS", 1),
    ("KXUEFASCSCORE", 1),
    ("KXUELBTTS", 44),
    ("KXUELSCORE", 44),
    ("KXUELSPREAD", 29),
    ("KXUELTEAMTOTAL", 40),
    ("KXUELTOTAL", 29),
    ("KXURYPDBTTS", 1),
    ("KXUSLCUPBTTS", 4),
    ("KXUSLCUPSPREAD", 1),
    ("KXWCBTTS", 32),
    ("KXWCSCORE", 32),
]


class TestEverySoccerCupPrefixReachesSoccer:
    @pytest.mark.parametrize("prefix,_rows", SOCCER_CUP_PREFIXES)
    def test_prefix_resolves_to_a_soccer_sport_key(self, prefix, _rows):
        key = get_sport_key_from_ticker(f"{prefix}-26SEP02AAABBB")
        assert key is not None, f"{prefix} still resolves to nothing"
        assert key.startswith("soccer"), f"{prefix} resolved to {key}"

    @pytest.mark.parametrize("prefix,_rows", SOCCER_CUP_PREFIXES)
    def test_regulation_time_name_is_categorised_soccer_not_legal(self, prefix, _rows):
        """The real production inputs.

        Kalshi's event payload carries `category="Sports"` — NOT "Soccer" — so the
        step-4 category fallback cannot rescue these. Passing "Sports" here is what
        the two live call sites in `tasks/kalshi.py` actually pass; a test that
        passed "Soccer" would pass even with the mapping removed.
        """
        name = "Ajax vs Sion: Regulation Time BTTS"
        result = _categorize_kalshi_market(name, "Sports", f"{prefix}-26SEP02AAABBB")
        assert result == "soccer", f"{prefix} -> {result}"


class TestTheMappingStaysNarrow:
    def test_non_soccer_tickers_are_untouched(self):
        assert get_sport_key_from_ticker("KXNFLGAME-26SEP07X") == "americanfootball_nfl"
        assert get_sport_key_from_ticker("KXNBASPREAD-26SEP07X") == "basketball_nba"
        assert get_sport_key_from_ticker("KXUFCFIGHT-26SEP08X") == "mma_mixed_martial_arts"
        assert get_sport_key_from_ticker("KXATPMATCH-26SEP07X") == "tennis_atp"

    def test_a_genuine_legal_question_is_still_legal(self):
        """The #3414 boundary must survive: only the TICKER moves these rows."""
        result = _categorize_kalshi_market(
            "Will the Supreme Court rule on regulation time limits?", "Legal", None
        )
        assert result != "soccer"

    def test_an_unmapped_prefix_does_not_silently_become_soccer(self):
        assert get_sport_key_from_ticker("KXTOTALLYMADEUPCUPBTTS-26SEP02X") is None


# ── The `…GAME` legs are DELIBERATELY EXCLUDED, and this is the evidence ──────
# Mapping these 15 to "soccer_other" regressed 17 golden-set pairs (CI run
# 34019815553). The cause is not the classifier, it is the SPORT KEY: the events
# these moneylines must reach carry specific league keys —
#   Fulham vs Wimbledon        -> soccer_england_efl_cup
#   América vs Columbus Crew   -> soccer_concacaf_leagues_cup
# — so declaring the market "soccer_other" makes the matcher's sport check refuse
# the very event the golden set expects. Nine of the fifteen have a precise key in
# the `sports` table (efl_cup, concacaf_leagues_cup, uefa_europa_league,
# uefa_europa_conference_league, germany_dfb_pokal, italy_coppa_italia, fa_cup,
# conmebol_copa_libertadores, conmebol_copa_sudamericana); six have none. Getting
# that right is matching work with its own verification, filed separately.
#
# This list is here so the omission is a decision on the record, not a gap, and so
# the test below fails loudly if someone adds one without doing that work.
GAME_LEGS_DELIBERATELY_UNMAPPED = [
    "KXASEANGAME",
    "KXCONMEBOLLIBGAME",
    "KXCONMEBOLSUDGAME",
    "KXCOPADOBRASILGAME",
    "KXCOPPAITALIAGAME",
    "KXDFBPOKALGAME",
    "KXEFLCUPGAME",
    "KXFACUPGAME",
    "KXGRECUPGAME",
    "KXISRPLCUPGAME",
    "KXLEAGUESCUPGAME",
    "KXSERIECCUPGAME",
    "KXTACAPORTGAME",
    "KXUECLGAME",
    "KXUELGAME",
]


class TestTheGameLegsStayUnmapped:
    """Not a wish — a tripwire.

    Mapping any of these to a generic soccer key regresses the golden set. If a
    future change maps one, it must map it to the competition's real league key and
    re-run `tests/test_matching_golden_set_2706.py`, at which point this test should
    be updated deliberately rather than deleted in passing.
    """

    def test_game_legs_are_not_mapped_to_a_generic_soccer_key(self):
        from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY

        offenders = [
            p for p in GAME_LEGS_DELIBERATELY_UNMAPPED
            if KALSHI_TICKER_TO_SPORT_KEY.get(p.lower()) == "soccer_other"
        ]
        assert not offenders, (
            "mapped to the generic key, which refuses the golden-set event: "
            f"{offenders} — see tests/test_matching_golden_set_2706.py"
        )
