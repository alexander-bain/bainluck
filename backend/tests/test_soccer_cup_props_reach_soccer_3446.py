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


# ─────────────────────────────────────────────────────────────────────────────
# CERT-2043 — the second opinion that blocked the first attempt at this ship.
#
# The first attempt mapped these 73 prefixes to `soccer_other` and shipped the
# classification half green. `soccer_other` is a REAL league key with 4,752
# production events, and the matcher scopes candidates with a PREFIX test
# (`event.sport.key.startswith(sport_prefix)` in `_score_candidates`). So a
# Europa League BTTS market keyed `soccer_other` was scoped to the wrong bucket
# and could not see its own fixture, which is keyed `soccer_uefa_europa_league`.
# That is a matching regression against the exact parent, which supplied no key
# at all and linked the identical pair.
#
# These tests are written to FAIL on `soccer_other` and pass on `soccer`. They
# assert the MECHANISM (the startswith filter) rather than the literal value,
# because the value is only wrong in virtue of what the filter does with it.
# ─────────────────────────────────────────────────────────────────────────────

# The real league keys these competitions' events actually carry, measured
# against production on 2026-09-06 (event counts in the last 60 days). Written
# literally: deriving them from the map under test would assert nothing.
REAL_LEAGUE_KEYS_THESE_SERIES_MUST_REACH = [
    ("soccer_uefa_europa_league", 18),
    ("soccer_uefa_europa_conference_league", 18),
    ("soccer_italy_coppa_italia", 24),
    ("soccer_england_efl_cup", 81),
    ("soccer_germany_dfb_pokal", 51),
    ("soccer_fifa_world_cup", 27),
]


def _prop_prefixes():
    from app.utils.sport_keys import _SOCCER_CUP_PROP_TICKER_TO_SPORT_KEY

    return sorted(_SOCCER_CUP_PROP_TICKER_TO_SPORT_KEY)


class TestThePropKeyDoesNotRefuseItsOwnFixture:
    """CERT-2043's finding, stated as the filter the matcher actually runs."""

    @pytest.mark.parametrize("league_key,_events", REAL_LEAGUE_KEYS_THESE_SERIES_MUST_REACH)
    def test_every_prop_prefix_admits_the_real_league_key(self, league_key, _events):
        refused = []
        for prefix in _prop_prefixes():
            scope = get_sport_key_from_ticker(f"{prefix}-26SEP02AAABBB")
            # This is the exact expression `_score_candidates` evaluates before
            # it will consider an event at all.
            if not league_key.startswith(scope or ""):
                refused.append((prefix, scope))
        assert not refused, (
            f"{len(refused)} prop prefixes scope to a key that REFUSES real "
            f"{league_key} fixtures — the market cannot see its own game. "
            f"First few: {refused[:5]}"
        )

    def test_the_europa_league_btts_reproduction_from_cert_2043(self):
        """The named specimen. Both halves must hold at once."""
        ticker = "KXUELBTTS-26SEP18AJASIO"
        name = "Ajax vs Sion: Regulation Time BTTS"

        assert _categorize_kalshi_market(name, "Sports", ticker) == "soccer"

        scope = get_sport_key_from_ticker(ticker)
        assert "soccer_uefa_europa_league".startswith(scope), (
            f"scope {scope!r} refuses the real Europa League fixture"
        )

    def test_the_scope_is_still_narrow_enough_to_refuse_other_sports(self):
        """A broad key is only safe if it is still a sport guard."""
        for prefix in _prop_prefixes():
            scope = get_sport_key_from_ticker(f"{prefix}-26SEP02AAABBB")
            for foreign in ("basketball_nba", "americanfootball_nfl", "tennis_atp"):
                assert not foreign.startswith(scope), (
                    f"{prefix} scopes to {scope!r}, which admits {foreign}"
                )


class TestThePropPrefixesNeverBecomeAHardMatchKey:
    """CERT-2043 clause 2 — these derivative props must not reach auto-create.

    Being in ``KALSHI_GAME_TICKER_PREFIXES`` arms two things at once: signal 1
    of ``is_game_level_market`` (so the ticker alone declares the row a game),
    and the Pass-1 ticker scan that feeds the auto-create path. The parent had
    none of these prefixes, so it armed neither.
    """

    def test_no_prop_prefix_is_game_level_on_the_ticker_alone(self):
        from app.utils.sport_keys import is_kalshi_game_level_ticker

        armed = [p for p in _prop_prefixes()
                 if is_kalshi_game_level_ticker(f"{p}-26SEP02AAABBB")]
        assert not armed, f"{len(armed)} prop prefixes declare themselves games: {armed[:5]}"

    def test_no_prop_prefix_enters_the_matchers_game_prefix_tuple(self):
        from app.utils.sport_keys import (
            KALSHI_GAME_TICKER_PREFIXES,
            KALSHI_LINK_RATE_GAME_TICKER_PREFIXES,
        )

        leaked = [p for p in _prop_prefixes() if p in KALSHI_GAME_TICKER_PREFIXES]
        assert not leaked, f"leaked into the matcher's hard key set: {leaked[:5]}"

        # Classification-only rows must not inflate the link-rate denominator
        # either — they are not markets we expect the ticker scan to link.
        leaked_lr = [p for p in _prop_prefixes()
                     if p in KALSHI_LINK_RATE_GAME_TICKER_PREFIXES]
        assert not leaked_lr, f"leaked into the link-rate denominator: {leaked_lr[:5]}"

    def test_the_exclusion_is_derived_so_a_new_prefix_cannot_arm_matching(self):
        """The anti-drift rail.

        The exclusion set is built FROM the classification dict, so adding a
        prefix up there cannot silently arm it down here. If someone restates
        the list by hand instead, this fails.
        """
        from app.utils.sport_keys import (
            _CLASSIFICATION_ONLY_PREFIXES,
            _SOCCER_CUP_PROP_TICKER_TO_SPORT_KEY,
        )

        missing = set(_SOCCER_CUP_PROP_TICKER_TO_SPORT_KEY) - _CLASSIFICATION_ONLY_PREFIXES
        assert not missing, (
            "the exclusion no longer covers the whole classification dict — it "
            f"has been restated by hand and has drifted: {sorted(missing)[:5]}"
        )


# The five Leagues Cup prop prefixes held out of this ship. Mapping any of them
# regresses golden-set pair 59700871 (see the HELD OUT note in `sport_keys.py`).
# They are held pending lane1b's adjudication of that pair, not abandoned.
HELD_PENDING_GOLDEN_ADJUDICATION = [
    "kxleaguescupbtts",
    "kxleaguescupscore",
    "kxleaguescupspread",
    "kxleaguescupteamtotal",
    "kxleaguescuptotal",
]


class TestTheHeldLeaguesCupPrefixesStayHeld:
    """A tripwire, like `TestTheGameLegsStayUnmapped` above.

    Whoever maps these must re-run `tests/test_matching_golden_set_2706.py` and
    land lane1b's amendment for market 59700871 FIRST, then update this test
    deliberately. Deleting it to go green is the failure mode it exists for.
    """

    def test_the_leagues_cup_props_are_not_mapped(self):
        from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY

        mapped = [p for p in HELD_PENDING_GOLDEN_ADJUDICATION
                  if p in KALSHI_TICKER_TO_SPORT_KEY]
        assert not mapped, (
            f"{mapped} were mapped without amending golden pair 59700871 — "
            "run tests/test_matching_golden_set_2706.py and read the HELD OUT "
            "note in app/utils/sport_keys.py"
        )

    def test_the_hold_is_the_only_gap_and_it_is_named(self):
        """The hold must stay a NAMED five, not quietly grow."""
        from app.utils.sport_keys import _SOCCER_CUP_PROP_TICKER_TO_SPORT_KEY

        assert len(_SOCCER_CUP_PROP_TICKER_TO_SPORT_KEY) == 68, (
            "the classification set changed size — if prefixes were added or "
            "held, say which in the HELD OUT note and update this count"
        )
