"""Guard: a Ligue 1 club named for its city's adjective folds onto the city-named row (#10287).

THE PAGE. `bainluck.com/sport/soccer/ligue1` at 390px, 2026-10-03 05:33Z, opened
its upcoming games with one fixture twice:

    15313577  RC Lens / Lyon                              odds_api (+espn)  kalshi, betting  43%
    15319175  Racing Club de Lens / Olympique Lyonnais    polymarket, no id                  42%

Same league, same minute (2026-10-09 18:45Z), same orientation. `Racing Club de
Lens` / `RC Lens` was already one club (#6022's whole-name alias); the away side
was the miss — `lyonnais` and `lyon` share no token. The same page carried two
more pairs of that shape the following weekend (Brest/Stade Brestois 29 on
10-10, Rennes/Stade Rennais FC 1901 on 10-11).

THE FIX is a fold-local retry with the club adjective written as its city, beside
the #9233 city-exonym retry and for its reason: `soccer_pair_matches` also decides
the StatPal anchors `stamp_v1_statpal_fixtures` WRITES.
"""

from datetime import datetime, timezone

import pytest

from app.utils import event_twin_fold as etf
from app.utils.event_twin_fold import _pair_matches, fold_twin_events
from app.utils.soccer_team_matching import soccer_pair_matches

LIGUE_1 = "soccer_france_ligue_one"


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


OCT_9 = datetime(2026, 10, 9, 18, 45, tzinfo=timezone.utc)
OCT_10 = datetime(2026, 10, 10, 18, 45, tzinfo=timezone.utc)
OCT_11 = datetime(2026, 10, 11, 15, 15, tzinfo=timezone.utc)


def _anchored(id, home, away, kickoff):
    return _Row(id, home, away, kickoff, LIGUE_1, espn_id="401876447",
                external_id="17694e68f399fdf9c5030021ec9bb595",
                sources={"kalshi": {"value": 0.425}, "betting": {"value": 0.43}})


def _polymarket(id, home, away, kickoff):
    return _Row(id, home, away, kickoff, LIGUE_1,
                commence_time_source="polymarket_venue",
                sources={"polymarket": {"value": 0.425}})


#: The three production pairs, read 2026-10-03 05:4xZ.
PRODUCTION_PAIRS = [
    pytest.param(
        _anchored(15313577, "RC Lens", "Lyon", OCT_9),
        _polymarket(15319175, "Racing Club de Lens", "Olympique Lyonnais", OCT_9),
        id="lens-lyon",
    ),
    pytest.param(
        _anchored(15313580, "Brest", "Angers", OCT_10),
        _polymarket(15319676, "Stade Brestois 29", "Angers SCO", OCT_10),
        id="brest-angers",
    ),
    pytest.param(
        _anchored(15313584, "Rennes", "Auxerre", OCT_11),
        _polymarket(15320453, "Stade Rennais FC 1901", "AJ Auxerre", OCT_11),
        id="rennes-auxerre",
    ),
]


@pytest.fixture(autouse=True)
def _fresh_pair_cache():
    # `_pair_matches` is memoised; an answer cached by another test file would
    # survive a monkeypatch and make the control below unable to fail.
    etf._pair_matches.cache_clear()
    yield
    etf._pair_matches.cache_clear()


class TestTheLigue1PageServesEachFixtureOnce:
    @pytest.mark.parametrize("anchored,poly", PRODUCTION_PAIRS)
    def test_the_pair_folds_onto_the_anchored_row_with_both_prices(self, anchored, poly):
        fold = fold_twin_events([anchored, poly])

        assert [e.id for e in fold.events] == [anchored.id]
        assert fold.survivor_of == {poly.id: anchored.id}
        assert set(fold.merged_sources[anchored.id]) == {"kalshi", "betting", "polymarket"}

    @pytest.mark.parametrize("anchored,poly", PRODUCTION_PAIRS)
    def test_without_the_table_the_pair_stays_two_cards(self, monkeypatch, anchored, poly):
        """Non-vacuity: each fold above is this table's doing, not a looser rule."""
        monkeypatch.setattr(etf, "_CLUB_DEMONYMS", {})
        monkeypatch.setattr(etf, "_CLUB_DEMONYM_WORD", etf.re.compile(r"(?!x)x"))
        assert fold_twin_events([anchored, poly]).dropped_ids == []

    def test_a_different_opponent_at_the_same_minute_does_not_fold(self):
        anchored = _anchored(15313577, "RC Lens", "Lyon", OCT_9)
        other = _polymarket(2, "Racing Club de Lens", "Stade Rennais", OCT_9)
        assert fold_twin_events([anchored, other]).dropped_ids == []


class TestTheRetryJoinsOneClubAndNoTwo:
    @pytest.mark.parametrize(
        "left,right",
        [
            (("X", "Olympique Lyonnais"), ("X", "Lyon")),
            (("X", "Olympique Lyonnais"), ("X", "Olympique Lyon")),
            (("Stade Rennais", "X"), ("Rennes", "X")),
            (("Stade Rennais FC", "X"), ("Rennes", "X")),
            (("Stade Brestois 29", "X"), ("Brest", "X")),
            (("Stade Brestois 29", "X"), ("Stade Brest 29", "X")),
            (("OLYMPIQUE LYONNAIS", "X"), ("Lyon", "X")),
        ],
    )
    def test_one_club_two_spellings(self, left, right):
        assert _pair_matches(left, right)

    @pytest.mark.parametrize(
        "left,right",
        [
            # Two clubs whose names share only the club-form word `Stade`.
            (("Stade Rennais", "X"), ("Stade Brestois 29", "X")),
            (("Stade Rennais", "X"), ("Brest", "X")),
            # Lyon's other club is not Olympique Lyonnais.
            (("Olympique Lyonnais", "X"), ("Lyon Duchere", "X")),
            # A reserve side stays a different squad.
            (("Stade Rennais B", "X"), ("Rennes", "X")),
            # Orientation is never relaxed: the reverse fixture is another game.
            (("Lyon", "RC Lens"), ("Racing Club de Lens", "Olympique Lyonnais")),
        ],
    )
    def test_different_clubs_squads_or_fixtures(self, left, right):
        assert not _pair_matches(left, right)

    def test_a_word_containing_the_adjective_is_not_rewritten(self):
        assert etf._city_for_club_demonym("Lyonnaise") == "Lyonnaise"
        assert etf._city_for_club_demonym("Stade RENNAIS") == "Stade Rennes"
        assert etf._city_for_club_demonym(None) is None


class TestTheAnchorWriterIsNotWidened:
    def test_the_stamper_predicate_still_says_no(self):
        """`stamp_v1_statpal_fixtures` pairs on `soccer_pair_matches`. If this ever
        turns True, a Polymarket row in the league makes the stamper refuse the
        fixture as ambiguous (two rows) instead of stamping the one anchored row —
        a writer change, and not this ship's."""
        assert not soccer_pair_matches(("X", "Olympique Lyonnais"), ("X", "Lyon"))
        assert not soccer_pair_matches(("Stade Rennais", "X"), ("Rennes", "X"))
        assert not soccer_pair_matches(("Stade Brestois 29", "X"), ("Brest", "X"))
