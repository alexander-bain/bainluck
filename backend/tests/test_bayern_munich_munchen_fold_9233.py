"""Guard: `Bayern Munich` and `FC Bayern München` are one club to the serve-time fold (#9233).

THE PAGE. `bainluck.com/sports/soccer_germany_bundesliga` at 390px, 2026-09-27
~23:33Z: **Augsburg v Bayern Munich** (Oct 10, 11%) and, two cards later, **FC
Augsburg v FC Bayern München** (Oct 10, 10%). Production:

    15313587  Augsburg / Bayern Munich            odds_api (+espn 401884777)  kalshi
    15319675  FC Augsburg / FC Bayern München     polymarket 1089281, no id   17 polymarket

Same league, same minute (2026-10-10 13:30Z), same orientation. The Polymarket
claim is id-less, so ruling 048 made it create; the fold is the reader-facing
repair. It missed because `munich` and `munchen` share no token — an exonym, the
Köln/Cologne case (#5829), which no transliteration reaches.

THE FIX is a fold-local retry with the city written in its own language, beside
the transliteration and nation-spelling retries and for their reason:
`soccer_pair_matches` also decides the StatPal anchors
`stamp_v1_statpal_fixtures` WRITES, and widening it would turn a one-row stamp
into a two-row refusal whenever a Polymarket row sits in the league.
"""

from datetime import datetime, timezone

import pytest

from app.utils import event_twin_fold as etf
from app.utils.event_twin_fold import _pair_matches, fold_twin_events
from app.utils.soccer_team_matching import soccer_pair_matches


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads. Not a MagicMock: an auto-attribute
    mock makes every `espn_id` truthy and every `sport.key` anything at all."""

    def __init__(self, id, home, away, kickoff, sport_key, *, espn_id=None,
                 external_id=None, sources=None, commence_time_source="odds_api"):
        self.id = id
        self.sport_id = 1
        self.sport = _Sport(sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = kickoff
        self.status = "scheduled"
        self.home_score = None
        self.away_score = None
        self.espn_id = espn_id
        self.external_id = external_id
        self.commence_time_source = commence_time_source
        self.win_probability_sources = sources


OCT_10 = datetime(2026, 10, 10, 13, 30, tzinfo=timezone.utc)
SEP_30 = datetime(2026, 9, 30, 19, 0, tzinfo=timezone.utc)


def _bundesliga_pair():
    """The production pair, read 2026-09-28 01:0xZ."""
    odds = _Row(
        15313587, "Augsburg", "Bayern Munich", OCT_10, "soccer_germany_bundesliga",
        espn_id="401884777", external_id="3b71160ad20dba786c4f92e33c987d80",
        sources={"kalshi": {"value": 0.11}},
    )
    poly = _Row(
        15319675, "FC Augsburg", "FC Bayern München", OCT_10, "soccer_germany_bundesliga",
        commence_time_source="polymarket_venue", sources={"polymarket": {"value": 0.10}},
    )
    return odds, poly


@pytest.fixture(autouse=True)
def _fresh_pair_cache():
    # `_pair_matches` is memoised; an answer cached by another test file would
    # survive a monkeypatch and make the control below unable to fail.
    etf._pair_matches.cache_clear()
    yield
    etf._pair_matches.cache_clear()


class TestTheBundesligaPageServesAugsburgVBayernOnce:
    def test_the_pair_folds_onto_the_anchored_row_with_both_prices(self):
        odds, poly = _bundesliga_pair()
        fold = fold_twin_events([odds, poly])

        assert [e.id for e in fold.events] == [odds.id]
        assert fold.survivor_of == {poly.id: odds.id}
        assert set(fold.merged_sources[odds.id]) == {"kalshi", "polymarket"}

    def test_without_the_exonym_the_pair_stays_two_cards(self, monkeypatch):
        """Non-vacuity: the fold above is this table's doing, not a looser rule."""
        monkeypatch.setattr(etf, "_CITY_EXONYMS", {})
        monkeypatch.setattr(etf, "_CITY_EXONYM_WORD", etf.re.compile(r"(?!x)x"))
        odds, poly = _bundesliga_pair()
        assert fold_twin_events([odds, poly]).dropped_ids == []

    def test_a_different_opponent_at_the_same_minute_does_not_fold(self):
        odds, _ = _bundesliga_pair()
        other = _Row(2, "FC Augsburg", "TSV 1860 München", OCT_10,
                     "soccer_germany_bundesliga", commence_time_source="polymarket_venue",
                     sources={"polymarket": {"value": 0.5}})
        assert fold_twin_events([odds, other]).dropped_ids == []


class TestTheWomensChampionsLeagueGameFoldsItsCatchallTwin:
    """The second pair the retry reaches, through the catch-all pass: Polymarket
    15313704 `Sport Lisboa e Benfica v FC Bayern München` (`soccer_other`) and the
    Odds API's 15319993 `Benfica v Bayern Munich` (women's Champions League), both
    2026-09-30 19:00Z. ESPN's uefa.wchampions board lists Bayern Munich at Benfica
    at 19:00Z that day (401917005); its men's board lists no game that date."""

    def test_the_catchall_row_folds_onto_the_league_row(self):
        league = _Row(15319993, "Benfica", "Bayern Munich", SEP_30,
                      "soccer_uefa_champs_league_women", external_id="x",
                      sources={"betting": {"value": 0.2}})
        catchall = _Row(15313704, "Sport Lisboa e Benfica", "FC Bayern München", SEP_30,
                        "soccer_other", commence_time_source="polymarket_venue",
                        sources={"polymarket": {"value": 0.2}})
        fold = fold_twin_events([league, catchall])
        assert fold.survivor_of == {catchall.id: league.id}


class TestTheRetryJoinsOneClubAndNoTwo:
    @pytest.mark.parametrize(
        "left,right",
        [
            (("FC Augsburg", "FC Bayern München"), ("Augsburg", "Bayern Munich")),
            (("Augsburg", "Bayern Munich"), ("FC Augsburg", "FC Bayern München")),
            (("FC Bayern Munchen", "X"), ("Bayern Munich", "X")),
            (("Munich 1860", "X"), ("TSV 1860 München", "X")),
            (("1860 Munich", "X"), ("TSV 1860 München", "X")),
        ],
    )
    def test_one_club_in_two_languages(self, left, right):
        assert _pair_matches(left, right)

    @pytest.mark.parametrize(
        "left,right",
        [
            # The city's two football clubs.
            (("Bayern Munich", "X"), ("TSV 1860 München", "X")),
            (("FC Bayern München", "X"), ("Munich 1860", "X")),
            # Its hockey club shares only the city.
            (("Red Bull Munich", "X"), ("FC Bayern München", "X")),
            # A reserve side stays a different squad.
            (("FC Bayern München II", "X"), ("Bayern Munich", "X")),
            # Orientation is never relaxed: the reverse fixture is another game.
            (("Bayern Munich", "Augsburg"), ("FC Augsburg", "FC Bayern München")),
        ],
    )
    def test_different_clubs_squads_or_fixtures(self, left, right):
        assert not _pair_matches(left, right)

    def test_a_word_containing_the_city_is_not_rewritten(self):
        assert etf._native_city_spelling("Munichen") == "Munichen"
        assert etf._native_city_spelling("Bayern MUNICH") == "Bayern Munchen"
        assert etf._native_city_spelling(None) is None


class TestTheAnchorWriterIsNotWidened:
    def test_the_stamper_predicate_still_says_no(self):
        """`stamp_v1_statpal_fixtures` pairs on `soccer_pair_matches`. If this ever
        turns True, the stamper refuses Augsburg v Bayern as ambiguous (two rows)
        instead of stamping the one ESPN-anchored row — a writer change, and not
        this ship's."""
        assert not soccer_pair_matches(
            ("FC Augsburg", "FC Bayern München"), ("Augsburg", "Bayern Munich")
        )
