"""The two Kalshi game-level predicates must give the same answer (#2231).

`is_kalshi_game_ticker()` and `is_kalshi_game_level_ticker()` both answer "is
this ticker a single game?" and, before this suite, disagreed. The anchor path
was taught longest-prefix-wins by CERT-409 (queues 414/415); the other predicate
was left on a bare `startswith` against the game map on a blast-radius argument,
so **8 futures prefixes that strictly EXTEND a game prefix read as game-level**
to every caller that asks it — the Phase 1 matching gates, the grammar adapters
and the routes.

Why that is a user-visible bug and not a naming quibble. Both Phase 1 gates
(`tasks/prediction_market_matching.py:1107` and `:1489`) pass `external_id` into
`is_game_level_market()`, whose first and "most reliable" signal is this
predicate. A season-long future that answers True there is handed to matchup
extraction and becomes eligible to be bound to a single game event — the
Home Run Derby, the NBA Pacific Division title and the NBA points-leader race
each pinned to one night's fixture. That is the wrong-game-bind class again,
arrived at from the classification side instead of the scan side.

The fix must survive BOTH directions, and only one of them is loud:

  * 8 futures prefixes extend a game prefix (`kxmlbhrderby` over `kxmlbhr`).
    Left alone, a future is called a game. This is the half that is visible.
  * 146 game prefixes extend a futures prefix (`kxmlbrfi` over `kxmlb`). The
    tempting symmetric rule — "refuse if any futures prefix matches" — breaks
    these, and it breaks them SILENTLY: 146 real game families would simply
    stop being recognised and every count would look healthy (gotcha #53).

So the census counts below are asserted exactly. A map that changes shape must
fail this suite loudly rather than quietly reduce it to covering nothing.
"""

import pytest

from app.utils import sport_keys
from app.utils.sport_keys import (
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_GAME_TICKER_PREFIXES,
    is_kalshi_game_level_ticker,
    is_kalshi_game_ticker,
)

_GAME = set(KALSHI_GAME_TICKER_PREFIXES)
_FUTURES = set(KALSHI_FUTURES_TICKER_TO_SPORT_KEY)

# A futures prefix that strictly extends a game prefix: `startswith` alone calls
# it a game. Measured, not transcribed — the list is derived from the maps.
FUTURES_EXTENDING_A_GAME_PREFIX = sorted(
    {f for f in _FUTURES for g in _GAME if f != g and f.startswith(g)}
)

# The reverse, and the must-not-regress control. These are real game families.
GAME_EXTENDING_A_FUTURES_PREFIX = sorted(
    {g for g in _GAME for f in _FUTURES if f != g and g.startswith(f)}
)

# The census, frozen. See the module docstring for why an exact assert.
EXPECTED_FUTURES_OVER_GAME = 8
EXPECTED_GAME_OVER_FUTURES = 146


def _ticker(prefix: str) -> str:
    """A realistically-shaped Kalshi ticker built from a prefix."""
    return f"{prefix.upper()}-26FOOBAR"


# ── The census itself, so nothing below can go vacuous ────────────────────────


class TestTheCollisionCensusIsNonVacuous:
    def test_eight_futures_prefixes_extend_a_game_prefix(self):
        assert len(FUTURES_EXTENDING_A_GAME_PREFIX) == EXPECTED_FUTURES_OVER_GAME, (
            "The set of futures prefixes that extend a game prefix changed shape. "
            "That is not automatically wrong, but it means the specimens below no "
            "longer cover what they were written to cover — re-measure before "
            f"re-baselining. Now: {FUTURES_EXTENDING_A_GAME_PREFIX}"
        )

    def test_one_hundred_forty_six_game_prefixes_extend_a_futures_prefix(self):
        assert len(GAME_EXTENDING_A_FUTURES_PREFIX) == EXPECTED_GAME_OVER_FUTURES, (
            "The reverse-direction control changed size. This is the half that "
            "fails quietly: if it shrinks to zero the suite still passes every "
            f"other test. Now: {len(GAME_EXTENDING_A_FUTURES_PREFIX)}"
        )

    def test_the_two_maps_share_no_exact_key(self):
        # Not a duplicate of the pre-existing map-overlap test: this one is the
        # premise for the tie-break test below, and it names the consequence.
        assert _GAME & _FUTURES == set(), (
            "A prefix is now in both maps, so a LENGTH tie is reachable in "
            "production. The tie is defined and tested (see the fail-closed "
            "test), but a real one deserves a deliberate decision, not silence."
        )


# ── Acceptance 1: the two predicates agree on every prefix in both maps ───────


class TestThePredicatesAgree:
    @pytest.mark.parametrize("prefix", sorted(_GAME))
    def test_they_agree_on_every_game_map_prefix(self, prefix):
        t = _ticker(prefix)
        assert is_kalshi_game_ticker(t) == is_kalshi_game_level_ticker(t), t

    @pytest.mark.parametrize("prefix", sorted(_FUTURES))
    def test_they_agree_on_every_futures_map_prefix(self, prefix):
        t = _ticker(prefix)
        assert is_kalshi_game_ticker(t) == is_kalshi_game_level_ticker(t), t

    def test_the_walk_is_not_covering_an_empty_set(self):
        assert len(_GAME) > 200 and len(_FUTURES) > 400


# ── Acceptance 2: the 8 collisions classify as futures ────────────────────────


class TestAFutureThatExtendsAGamePrefixIsNotAGame:
    @pytest.mark.parametrize("prefix", FUTURES_EXTENDING_A_GAME_PREFIX)
    def test_the_broad_predicate_refuses_it(self, prefix):
        assert is_kalshi_game_ticker(_ticker(prefix)) is False

    @pytest.mark.parametrize("prefix", FUTURES_EXTENDING_A_GAME_PREFIX)
    def test_the_anchor_predicate_also_refuses_it(self, prefix):
        assert is_kalshi_game_level_ticker(_ticker(prefix)) is False

    @pytest.mark.parametrize(
        "ticker,what_it_actually_is",
        [
            ("KXMLBHRDERBY-26", "the Home Run Derby, not one MLB game"),
            ("KXMLBHITS-26SEASON", "a season hits total, not one MLB game"),
            ("KXNBAPACIFIC-26", "the Pacific Division title, not one NBA game"),
            ("KXNBAPTSLEADER-26", "the season points-leader race"),
            ("KXNBAREBOUNDTITLE-26", "the season rebounding title"),
            ("KXNFLRECYDSRECORD-26", "a single-season receiving-yards record"),
            ("KXWNBAGAMESPLAYED-26", "a games-played total, not one WNBA game"),
            ("KXVALORANTGAMETEAM-26", "a team-level Valorant future"),
        ],
    )
    def test_the_named_specimens(self, ticker, what_it_actually_is):
        assert is_kalshi_game_ticker(ticker) is False, what_it_actually_is
        assert is_kalshi_game_level_ticker(ticker) is False, what_it_actually_is


# ── Acceptance 3: the 146 reverse cases still classify as game-level ──────────


class TestAGameThatExtendsAFuturesPrefixStaysAGame:
    """The silent half. A fix that breaks these looks like a fix."""

    @pytest.mark.parametrize("prefix", GAME_EXTENDING_A_FUTURES_PREFIX)
    def test_the_broad_predicate_still_accepts_it(self, prefix):
        assert is_kalshi_game_ticker(_ticker(prefix)) is True

    @pytest.mark.parametrize("prefix", GAME_EXTENDING_A_FUTURES_PREFIX)
    def test_the_anchor_predicate_still_accepts_it(self, prefix):
        assert is_kalshi_game_level_ticker(_ticker(prefix)) is True

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXMLBRFI-26APR01NYYBOS",   # extends the futures prefix `kxmlb`
            "KXATPGAMESPREAD-26JUL01SINNERALCARAZ",  # extends `kxatp`
            "KXBOXINGFIGHT-26APR10FURY",  # extends `kxboxing`
            "KXNFLSPREAD-26SEP07KCBUF",
            "KXNHLGOAL-26MAR30BOSMON",
            "KXMLBF5-26APR01NYYBOS",
        ],
    )
    def test_named_reverse_specimens(self, ticker):
        assert is_kalshi_game_ticker(ticker) is True
        assert is_kalshi_game_level_ticker(ticker) is True


# ── Acceptance 4: a future exact-key collision has defined behaviour ──────────


class TestAnExactKeyCollisionFailsClosed:
    """No tie exists in the maps today, so the behaviour is asserted on a
    synthetic one. Undefined-and-unreachable becomes defined-and-tested: a tie
    resolves to FUTURES, i.e. NOT game-level.

    That is the safe direction for both consumers. For the anchor builder a
    false positive is an absorption — one game claiming another's identity,
    exactly what ruling 048 exists to prevent (gotcha #32). For the Phase 1
    gates a false positive binds a season-long market to one fixture. Refusing
    on a tie costs at most a missed link, which is recoverable and visible;
    accepting on a tie corrupts identity, which is neither.
    """

    @pytest.fixture
    def tied_maps(self, monkeypatch):
        collide = "kxtiedprefix"
        monkeypatch.setattr(
            sport_keys,
            "KALSHI_GAME_TICKER_PREFIXES",
            frozenset(_GAME | {collide}),
        )
        monkeypatch.setattr(
            sport_keys,
            "KALSHI_FUTURES_TICKER_TO_SPORT_KEY",
            {**KALSHI_FUTURES_TICKER_TO_SPORT_KEY, collide: "baseball_mlb"},
        )
        return collide

    def test_a_tie_resolves_to_futures(self, tied_maps):
        t = _ticker(tied_maps)
        assert sport_keys.is_kalshi_game_ticker(t) is False
        assert sport_keys.is_kalshi_game_level_ticker(t) is False

    def test_the_two_predicates_still_agree_under_a_tie(self, tied_maps):
        t = _ticker(tied_maps)
        assert sport_keys.is_kalshi_game_ticker(
            t
        ) == sport_keys.is_kalshi_game_level_ticker(t)

    def test_the_fixture_actually_installed_a_tie(self, tied_maps):
        # A monkeypatch that fails to apply would make the two tests above pass
        # for the wrong reason (gotcha: a mutation must prove it applied).
        assert tied_maps in sport_keys.KALSHI_GAME_TICKER_PREFIXES
        assert tied_maps in sport_keys.KALSHI_FUTURES_TICKER_TO_SPORT_KEY


# ── Regression: the ordinary cases both predicates already got right ──────────


class TestTheOrdinaryCasesAreUnchanged:
    @pytest.mark.parametrize(
        "ticker",
        [
            "KXNBAGAME-26FEB19BOSGSW",
            "kxnbagame-26feb19bosgsw",
            "KXNFLGAME-26SEP14SFDEN",
            "KXNHLGAME-26FEB20BOSNYR",
            "KXMLBGAME-26APR05NYYLAD",
            "KXNCAABGAME-26MAR20DUKEUNC",
            "KXNCAAFGAME-26OCT12OHSTPSU",
            "KXWNBAGAME-26JUN15NYLVLA",
            "KXMLSGAME-26JUL04NYCLA",
            "KXSOCCERGAME-26FEB20ARSCHI",
            "KXUFCFIGHT-26MAR15JONES",
            "KXWCGAME-26JUN15ALGAUT",
        ],
    )
    def test_real_game_tickers_stay_game_level(self, ticker):
        assert is_kalshi_game_ticker(ticker) is True
        assert is_kalshi_game_level_ticker(ticker) is True

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXNFLMVP-26",
            "KXNHLHART-26",
            "KXMLBWS-26",
            "KXWNBA-26",
            "KXNFLAFCCHAMP-26",
            "KXCPI-2026-05",
            "KXNBASERIES-26MAY10BOSPHI",
            "KXMLBSERIES-26OCT15NYYATL",
        ],
    )
    def test_futures_tickers_stay_futures(self, ticker):
        assert is_kalshi_game_ticker(ticker) is False
        assert is_kalshi_game_level_ticker(ticker) is False

    @pytest.mark.parametrize("bad", ["", None])
    def test_falsy_input_is_refused_by_both(self, bad):
        assert is_kalshi_game_ticker(bad) is False
        assert is_kalshi_game_level_ticker(bad) is False

    def test_leagues_we_ingest_no_events_for_are_still_not_game_tickers(self):
        # These sit in the game sport-key MAP but deliberately not in the game
        # PREFIX set, and must stay out of the matching scan.
        for ticker in [
            "KXCODMAP-26X", "KXKBOGAME-26", "KXNPBGAME-26", "KXRUGBYNRLMATCH-26",
            "KXT20MATCH-26", "KXNZNBLGAME-26", "KXKLEAGUEGAME-26", "KXAFLGAME-26",
            "KXWOCURLGAME-26",
        ]:
            assert is_kalshi_game_ticker(ticker) is False, ticker
            assert is_kalshi_game_level_ticker(ticker) is False, ticker
