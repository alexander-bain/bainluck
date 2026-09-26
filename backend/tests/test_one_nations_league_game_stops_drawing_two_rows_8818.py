"""Guard: `Czechia v Croatia` and `Czech Republic v Croatia` are ONE card (#8818).

THE PAGE THIS EXISTS FOR. `/api/events/search?q=croatia`, 2026-09-26 14:1xZ,
four hours before kick-off:

    15195324  soccer_uefa_nations_league  Czech Republic v Croatia  18:45Z
    15311809  soccer_other                Czechia v Croatia         18:45Z

One game, two cards, two different answers. The Nations League row (ESPN
401861063, Odds API, StatPal) carries only the sportsbooks; the catch-all row
Polymarket minted on 09-13 carries Kalshi and Polymarket. `?q=italy` draws
`Turkey v Italy` above `Türkiye v Italy` the same way (15304745 × 15312968,
09-28).

WHY THE FOLD MISSED THEM. The catch-all arm (#2866 rung 3) asks
`soccer_pair_matches`, and `czechia` and `czech republic` share no token. The
registry learned the spelling on 09-25 (#8675) — twelve days after these rows
were minted, so it never had the chance to join them.

The fix is a retry on the country's one spelling, asked only after the strict
question said no. These tests pin that it folds the specimens, that the Kalshi
and Polymarket readings reach the surviving card, and the three shapes it must
NOT fold: a youth side, the reverse fixture, and a pair with the retry removed
(the strawman — without it every other assertion could pass on a pass that
was never reached).
"""

from datetime import datetime, timezone

import pytest

import app.utils.event_twin_fold as fold_module
from app.utils.event_twin_fold import fold_twin_events
from app.utils.name_normalization import nation_spelling

KICKOFF = datetime(2026, 9, 26, 18, 45, tzinfo=timezone.utc)

NATIONS_LEAGUE_SPORT_ID = 5101
SOCCER_OTHER_SPORT_ID = 9901


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads. Not a MagicMock (#5918's reason:
    auto-attributes make every `espn_id` truthy and the file passes on nothing)."""

    def __init__(self, id, home, away, *, sport_key, sport_id, espn_id=None,
                 external_id=None, commence_time_source, sources=None):
        self.id = id
        self.sport_id = sport_id
        self.sport = _Sport(sport_key)
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = KICKOFF
        self.home_score = None
        self.away_score = None
        self.espn_id = espn_id
        self.external_id = external_id
        self.commence_time_source = commence_time_source
        self.status = "scheduled"
        self.win_probability_sources = sources


def _nations_league(id, home, away):
    """ESPN-anchored, as 15195324 is on production: espn_id + Odds API id, books only."""
    return _Row(
        id, home, away,
        sport_key="soccer_uefa_nations_league",
        sport_id=NATIONS_LEAGUE_SPORT_ID,
        espn_id=str(401861000 + id % 1000),
        external_id=f"odds-{id}",
        commence_time_source="espn",
        sources={"betting": {"value": 0.62}},
    )


def _polymarket_catchall(id, home, away):
    """Id-less `soccer_other`, as 15311809 is: Kalshi + Polymarket, venue-timed."""
    return _Row(
        id, home, away,
        sport_key="soccer_other",
        sport_id=SOCCER_OTHER_SPORT_ID,
        commence_time_source="polymarket_venue",
        sources={"kalshi": {"value": 0.61}, "polymarket": {"value": 0.605}},
    )


def _ids(result):
    return sorted(row.id for row in result.events)


def _czech_pair():
    return [
        _nations_league(15195324, "Czech Republic", "Croatia"),
        _polymarket_catchall(15311809, "Czechia", "Croatia"),
    ]


def test_czechia_and_czech_republic_fold_to_the_nations_league_card():
    result = fold_twin_events(_czech_pair())

    assert _ids(result) == [15195324]
    assert result.dropped_ids == [15311809]
    assert result.survivor_of == {15311809: 15195324}


def test_the_surviving_card_carries_kalshi_and_polymarket_beside_the_books():
    """The point of one card: one number, all three sources, not two halves."""
    result = fold_twin_events(_czech_pair())

    merged = result.merged_sources[15195324]
    assert set(merged) == {"betting", "kalshi", "polymarket"}


def test_turkiye_and_turkey_fold_the_same_way():
    result = fold_twin_events([
        _nations_league(15304745, "Turkey", "Italy"),
        _polymarket_catchall(15312968, "Türkiye", "Italy"),
    ])

    assert _ids(result) == [15304745]


def test_czechia_v_england_folds_too():
    """The second Czech fixture of the window (29 Sep): 15315653 × 15313497."""
    result = fold_twin_events([
        _nations_league(15315653, "Czech Republic", "England"),
        _polymarket_catchall(15313497, "Czechia", "England"),
    ])

    assert _ids(result) == [15315653]


def test_without_the_country_retry_the_pair_is_still_two_cards(monkeypatch):
    """Strawman: the retry is what folds it — not some other pass."""
    monkeypatch.setattr(fold_module, "nation_spelling", lambda name: None)
    fold_module._pair_matches.cache_clear()
    try:
        result = fold_twin_events(_czech_pair())
    finally:
        fold_module._pair_matches.cache_clear()

    assert _ids(result) == [15195324, 15311809]


def test_a_youth_side_is_never_spelled_as_the_senior_side():
    result = fold_twin_events([
        _nations_league(15195324, "Czech Republic", "Croatia"),
        _polymarket_catchall(15399001, "Czechia U21", "Croatia"),
    ])

    assert _ids(result) == [15195324, 15399001]


def test_the_reverse_fixture_is_not_this_game():
    """Orientation holds through the retry: Croatia at home is a different match."""
    result = fold_twin_events([
        _nations_league(15195324, "Czech Republic", "Croatia"),
        _polymarket_catchall(15399002, "Croatia", "Czechia"),
    ])

    assert _ids(result) == [15195324, 15399002]


@pytest.mark.parametrize(
    "name, spelled",
    [
        ("Czechia", "czech republic"),
        ("  CZECHIA ", "czech republic"),
        ("Türkiye", "turkey"),
        ("Bosnia-Herzegovina", "bosnia & herzegovina"),
        ("Bosnia and  Herzegovina", "bosnia & herzegovina"),
        ("Czech Republic", None),
        ("Czechia U21", None),
        ("Czechia Women", None),
        ("", None),
        (None, None),
    ],
)
def test_nation_spelling_is_whole_name_only(name, spelled):
    assert nation_spelling(name) == spelled
