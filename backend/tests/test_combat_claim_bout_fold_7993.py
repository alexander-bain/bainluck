"""#7993 — an id-less bout claim folds onto the one anchored bout it names.

Production 2026-09-28 02:1xZ, the Oct 3 UFC card: `/api/events/search` served
six bouts twice. One card was the Polymarket-born row (no provider id, every
bout at the card's 21:00Z, three of them carrying the Kalshi price). The other
was the Odds API row (`external_id` set, the bout's own slot, the sportsbook
price). The specimens below are those rows' stored values.

Every refusal leaves two cards, which is the page before this pass. Each one is
paired with the admission it borders, so deleting a clause fails a test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.utils.event_twin_fold import (
    COMBAT_CLAIM_BOUT_WINDOW,
    fold_twin_events,
)
from app.utils.search_fixture_dedup import FIXTURE_TIME_WINDOW_HOURS

CARD = datetime(2026, 10, 3, 21, 0, tzinfo=timezone.utc)

MMA = ("mma_mixed_martial_arts", 61)
MMA_OTHER = ("mma_other", 62)
BOXING = ("boxing_boxing", 63)
TENNIS = ("tennis_atp", 64)


class _Sport:
    def __init__(self, key):
        self.key = key


class _Row:
    """The subset of `Event` the fold reads. Not a MagicMock (see #5918's file)."""

    def __init__(
        self,
        id,
        home,
        away,
        *,
        sport=MMA,
        commence_time=CARD,
        external_id=None,
        espn_id=None,
        statpal_fixture_id=None,
        commence_time_source="polymarket_venue",
        status="scheduled",
        home_score=None,
        away_score=None,
        sources=None,
    ):
        self.id = id
        self.sport = _Sport(sport[0])
        self.sport_id = sport[1]
        self.home_team_name = home
        self.away_team_name = away
        self.commence_time = commence_time
        self.external_id = external_id
        self.espn_id = espn_id
        self.statpal_fixture_id = statpal_fixture_id
        self.commence_time_source = commence_time_source
        self.status = status
        self.home_score = home_score
        self.away_score = away_score
        self.win_probability_sources = sources


def _claim(id, home, away, **kwargs):
    """A Polymarket-born bout row: no provider id, the card's 21:00Z."""
    return _Row(id, home, away, **kwargs)


def _anchor(id, home, away, *, hours_after_card=3, **kwargs):
    """An Odds API bout row: `external_id` set, the bout's own slot."""
    kwargs.setdefault("sources", {"betting": 0.5})
    return _Row(
        id,
        home,
        away,
        commence_time=CARD + timedelta(hours=hours_after_card),
        external_id=f"odds-{id}",
        commence_time_source="odds_api",
        **kwargs,
    )


def _ids(result):
    return sorted(row.id for row in result.events)


# --- the specimens -----------------------------------------------------------


def test_kopylov_claim_folds_onto_the_anchored_bout_with_both_venues():
    """Corners reversed, 4 h apart, both priced: one card carrying both prices."""
    claim = _claim(
        15315711, "Roman Kopylov", "Ateba Gautier", sources={"kalshi": 0.62}
    )
    anchor = _anchor(
        15318681,
        "Ateba Gautier",
        "Roman Kopylov",
        hours_after_card=4,
        sources={"betting": 0.4},
    )

    result = fold_twin_events([claim, anchor])

    assert _ids(result) == [15318681]
    assert result.survivor_of == {15315711: 15318681}
    assert result.merged_sources[15318681] == {"betting": 0.4, "kalshi": 0.62}


def test_a_first_name_spelled_two_ways_still_folds_across_the_catch_all_key():
    """`Mick` / `Michael` Parkin, the claim on `mma_other`: one card."""
    claim = _claim(15315707, "Johnny Walker", "Mick Parkin", sport=MMA_OTHER)
    anchor = _anchor(15318686, "Johnny Walker", "Michael Parkin")

    assert _ids(fold_twin_events([claim, anchor])) == [15318686]


def test_a_particle_surname_and_a_short_first_name_fold():
    """`Rafael Dos Anjos v Alexander Hernandez` / `Rafael dos Anjos v Alex Hernandez`."""
    claim = _claim(
        15315706, "Rafael Dos Anjos", "Alexander Hernandez", sport=MMA_OTHER
    )
    anchor = _anchor(15318679, "Rafael dos Anjos", "Alex Hernandez")

    assert _ids(fold_twin_events([claim, anchor])) == [15318679]


def test_a_surname_only_kalshi_claim_folds_onto_the_full_name_bout():
    claim = _claim(
        15315972,
        "Vettori",
        "Naurdiev",
        commence_time=CARD + timedelta(hours=4, minutes=20),
        commence_time_source="kalshi",
        sources={"kalshi": 0.48},
    )
    anchor = _anchor(15318685, "Marvin Vettori", "Ismail Naurdiev")

    result = fold_twin_events([claim, anchor])

    assert _ids(result) == [15318685]
    assert result.merged_sources[15318685]["kalshi"] == 0.48


def test_a_generational_suffix_does_not_become_the_surname():
    claim = _claim(1, "Dustin Jacoby Jr.", "Kevin Holland")
    anchor = _anchor(2, "Dustin Jacoby", "Kevin Holland")

    assert _ids(fold_twin_events([claim, anchor])) == [2]


def test_the_boxing_bout_folds_the_same_way():
    claim = _claim(15152315, "Lopez", "Stevenson", sport=BOXING)
    anchor = _anchor(
        1157, "Teofimo Lopéz", "Shakur Stevenson", sport=BOXING, hours_after_card=10
    )

    assert _ids(fold_twin_events([claim, anchor])) == [1157]


# --- the refusals, each beside its admission ---------------------------------


def test_two_different_first_initials_are_two_fighters():
    claim = _claim(1, "John Smith", "Kevin Holland")
    anchor = _anchor(2, "Kyle Smith", "Kevin Holland")

    assert _ids(fold_twin_events([claim, anchor])) == [1, 2]


def test_one_shared_fighter_is_not_one_bout():
    claim = _claim(1, "Johnny Walker", "Mick Parkin")
    anchor = _anchor(2, "Johnny Walker", "Dominick Reyes")

    assert _ids(fold_twin_events([claim, anchor])) == [1, 2]


def test_the_window_is_the_search_dedup_window_and_binds_at_its_edge():
    assert COMBAT_CLAIM_BOUT_WINDOW == timedelta(hours=FIXTURE_TIME_WINDOW_HOURS)
    hours = FIXTURE_TIME_WINDOW_HOURS

    inside = fold_twin_events(
        [_claim(1, "A Pulyaev", "D Pinas"), _anchor(2, "Andrey Pulyaev", "Damian Pinas", hours_after_card=hours)]
    )
    outside = fold_twin_events(
        [
            _claim(1, "A Pulyaev", "D Pinas"),
            _anchor(2, "Andrey Pulyaev", "Damian Pinas", hours_after_card=hours + 0.1),
        ]
    )

    assert _ids(inside) == [2]
    assert _ids(outside) == [1, 2]


def test_two_anchored_candidates_leave_the_claim_standing():
    """The Odds API re-mint (#7993's first half) is two anchored rows: no guess."""
    claim = _claim(1, "Marvin Vettori", "Ismail Naurdiev")
    set_b = _anchor(2, "Marvin Vettori", "Ismail Naurdiev", hours_after_card=3)
    set_a = _anchor(3, "Marvin Vettori", "Ismail Naurdiev", hours_after_card=27)

    assert 1 in _ids(fold_twin_events([claim, set_b, set_a]))
    assert _ids(fold_twin_events([claim, set_b])) == [2]


def test_two_anchored_rows_are_never_joined_here():
    left = _anchor(1, "King Green", "Esteban Ribovics", hours_after_card=0)
    right = _anchor(2, "King Green", "Esteban Ribovics", hours_after_card=3)

    assert _ids(fold_twin_events([left, right])) == [1, 2]


def test_two_claims_with_no_anchor_are_never_joined_here():
    left = _claim(1, "Roberto Soldic", "Khaos Williams")
    right = _claim(
        2,
        "Williams",
        "Soldic",
        commence_time=CARD + timedelta(hours=8),
        commence_time_source="kalshi",
    )

    assert _ids(fold_twin_events([left, right])) == [1, 2]


def test_a_statpal_fixture_row_is_a_schedule_row_not_a_claim():
    scheduled = _claim(1, "King Green", "Esteban Ribovics", statpal_fixture_id="sp-9")
    anchor = _anchor(2, "King Green", "Esteban Ribovics")

    assert _ids(fold_twin_events([scheduled, anchor])) == [1, 2]
    assert _ids(fold_twin_events([_claim(1, "King Green", "Esteban Ribovics"), anchor])) == [2]


def test_tennis_keeps_its_own_machinery():
    claim = _claim(1, "Daniil Medvedev", "Arthur Royer", sport=TENNIS)
    anchor = _anchor(2, "Daniil Medvedev", "Arthur Royer", sport=TENNIS)

    assert _ids(fold_twin_events([claim, anchor])) == [1, 2]


def test_an_mma_claim_never_folds_onto_a_boxing_bout():
    claim = _claim(1, "Jake Paul", "Nate Diaz", sport=MMA)
    anchor = _anchor(2, "Jake Paul", "Nate Diaz", sport=BOXING)

    assert _ids(fold_twin_events([claim, anchor])) == [1, 2]


def test_two_scorelines_are_two_bouts():
    claim = _claim(1, "Neil Magny", "Ramiz Brahimaj", status="completed", home_score=0, away_score=1)
    anchor = _anchor(2, "Neil Magny", "Ramiz Brahimaj", status="completed", home_score=1, away_score=0)
    agreeing = _anchor(2, "Neil Magny", "Ramiz Brahimaj", status="completed", home_score=0, away_score=1)

    assert _ids(fold_twin_events([claim, anchor])) == [1, 2]
    assert _ids(fold_twin_events([claim, agreeing])) == [2]


def test_a_live_claim_folds_only_when_it_holds_no_score():
    scored = _claim(1, "Mateusz Gamrot", "Quillan Salkilld", status="live", home_score=1, away_score=0)
    scoreless = _claim(1, "Mateusz Gamrot", "Quillan Salkilld", status="live")
    anchor = _anchor(2, "Mateusz Gamrot", "Quillan Salkilld", status="live")

    assert _ids(fold_twin_events([scored, anchor])) == [1, 2]
    assert _ids(fold_twin_events([scoreless, anchor])) == [2]


def test_an_unknown_status_is_refused():
    claim = _claim(1, "Neil Magny", "Ramiz Brahimaj", status="postponed")
    anchor = _anchor(2, "Neil Magny", "Ramiz Brahimaj")

    assert _ids(fold_twin_events([claim, anchor])) == [1, 2]
