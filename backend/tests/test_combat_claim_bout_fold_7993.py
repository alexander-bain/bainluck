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

import pytest

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


def test_ribovics_claim_folds_onto_the_anchored_bout_with_both_venues():
    """Same corners, 3 h apart, both priced: one card carrying both prices."""
    claim = _claim(
        15315713, "King Green", "Esteban Ribovics", sources={"kalshi": 0.325}
    )
    anchor = _anchor(
        15318684, "King Green", "Esteban Ribovics", sources={"betting": 0.3107}
    )

    result = fold_twin_events([claim, anchor])

    assert _ids(result) == [15318684]
    assert result.survivor_of == {15315713: 15318684}
    assert result.merged_sources[15318684] == {"betting": 0.3107, "kalshi": 0.325}


def test_kopylov_reversed_and_priced_folds_with_kalshi_turned_round():
    """#7993 residual, production 2026-09-30 17:0xZ. The claim 15315711 is
    Gautier @ Kopylov (home Kopylov, Kalshi 0.345 = Kopylov's chance). The
    anchor 15318681 is Kopylov @ Gautier (home Gautier, sportsbooks 0.6506 =
    Gautier's chance). #9304 refused this pair, so `/sports/mma_mixed_martial_arts`
    listed the bout twice. Now one card, and Kalshi reads 0.655 FOR GAUTIER,
    beside the sportsbooks' 0.6506 for Gautier. A verbatim copy (#9304's
    regression) would put 0.345 there."""
    kalshi = {
        "value": 0.345,
        "observed_value": 0.345,
        "updated_at": "2026-09-30T16:57:08.491649+00:00",
        "eligibility": {"v": 1, "market_id": 61620856, "status": "verified"},
        "observed_basis": {"232147185": 1790787428.491649},
    }
    claim = _claim(
        15315711, "Roman Kopylov", "Ateba Gautier", sources={"kalshi": kalshi}
    )
    anchor = _anchor(
        15318681,
        "Ateba Gautier",
        "Roman Kopylov",
        hours_after_card=3.25,
        sources={"betting": {"value": 0.6506}, "betting_book_count": 7},
    )

    result = fold_twin_events([claim, anchor])

    assert _ids(result) == [15318681]
    assert result.survivor_of == {15315711: 15318681}
    merged = result.merged_sources[15318681]
    assert merged["betting"] == {"value": 0.6506}
    assert merged["kalshi"]["value"] == pytest.approx(0.655)
    # The pair turns together, so the basis still dates the value it binds.
    assert merged["kalshi"]["observed_value"] == merged["kalshi"]["value"]
    assert merged["kalshi"]["observed_basis"] == kalshi["observed_basis"]
    assert merged["kalshi"]["eligibility"] == kalshi["eligibility"]
    # The stored row is not touched: the flip is a served reading only.
    assert claim.win_probability_sources == {"kalshi": kalshi}


def test_pulyaev_reversed_bare_number_is_turned_round():
    """Pulyaev–Pinas, a legacy bare-number reading: 0.185 for Pulyaev is 0.815
    for Pinas, the anchor's home fighter."""
    claim = _claim(15315709, "Andrey Pulyaev", "Damian Pinas", sources={"kalshi": 0.185})
    anchor = _anchor(15318680, "Damian Pinas", "Andrey Pulyaev", sources={"betting": 0.8088})

    result = fold_twin_events([claim, anchor])

    assert _ids(result) == [15318680]
    assert result.merged_sources[15318680]["kalshi"] == pytest.approx(0.815)


def test_a_same_corner_claim_is_never_turned_round():
    """The border of the flip: same corners, the number is copied as stored."""
    claim = _claim(15315713, "King Green", "Esteban Ribovics", sources={"kalshi": 0.3})
    anchor = _anchor(15318684, "King Green", "Esteban Ribovics", sources={"betting": 0.31})

    assert fold_twin_events([claim, anchor]).merged_sources[15318684]["kalshi"] == 0.3


def test_the_anchors_own_numbers_are_never_turned_round():
    claim = _claim(15315711, "Roman Kopylov", "Ateba Gautier", sources={"kalshi": 0.345})
    anchor = _anchor(
        15318681, "Ateba Gautier", "Roman Kopylov",
        sources={"betting": 0.6506, "polymarket": 0.66},
    )

    merged = fold_twin_events([claim, anchor]).merged_sources[15318681]
    assert merged == {"betting": 0.6506, "polymarket": 0.66, "kalshi": pytest.approx(0.655)}


@pytest.mark.parametrize(
    "reading",
    [
        {"value": 0.345, "bid": 0.34},  # a key nobody has checked
        {"observed_value": 0.345},  # no value
        {"value": "0.345"},  # not a number
        {"value": 1.4},  # not a probability
        "0.345",
        None,
    ],
)
def test_a_reversed_reading_that_cannot_be_turned_round_stays_two_cards(reading):
    claim = _claim(15315711, "Roman Kopylov", "Ateba Gautier", sources={"kalshi": reading})
    anchor = _anchor(15318681, "Ateba Gautier", "Roman Kopylov", sources={"betting": 0.6506})

    result = fold_twin_events([claim, anchor])

    assert _ids(result) == [15315711, 15318681]
    assert 15318681 not in result.merged_sources


def test_a_reversed_priced_claim_that_would_be_kept_stays_two_cards():
    """A claim with a visible score outranks the anchor, so the anchor's
    numbers would be the ones copied, unturned, onto the claim's corners."""
    claim = _claim(
        15315711, "Roman Kopylov", "Ateba Gautier",
        home_score=1, away_score=0, sources={"kalshi": 0.345},
    )
    anchor = _anchor(15318681, "Ateba Gautier", "Roman Kopylov", sources={"betting": 0.6506})

    assert _ids(fold_twin_events([claim, anchor])) == [15315711, 15318681]


def test_a_reversed_claims_opening_line_crosses_with_its_halves_swapped():
    """Pinas @ Pulyaev with only the claim holding a line: the claim's 0.2 for
    Pulyaev (its home) is the anchor's AWAY half, and 0.8 for Pinas its home."""
    claim = _claim(15315709, "Andrey Pulyaev", "Damian Pinas")
    claim.opening_home_probability = 0.2
    claim.opening_away_probability = 0.8
    anchor = _anchor(15318680, "Damian Pinas", "Andrey Pulyaev", sources={"betting": 0.8})
    anchor.opening_home_probability = None
    anchor.opening_away_probability = None

    result = fold_twin_events([claim, anchor])

    assert _ids(result) == [15318680]
    assert (anchor.opening_home_probability, anchor.opening_away_probability) == (0.8, 0.2)
    assert result.merged_opening[15318680] == (0.8, 0.2)


def test_a_reversed_claim_with_no_number_still_folds_9304():
    """Rodriguez–Coria: corners reversed, the claim holds nothing to misread."""
    claim = _claim(15315710, "Alden Coria", "Imanol Rodriguez")
    anchor = _anchor(15318678, "Imanol Rodriguez", "Alden Coria", sources={"betting": 0.5977})

    result = fold_twin_events([claim, anchor])

    assert _ids(result) == [15318678]
    assert result.survivor_of == {15315710: 15318678}
    assert 15318678 not in result.merged_sources


def test_a_reversed_unpriced_claim_that_would_be_kept_is_refused_9304():
    """A claim with a visible score outranks the anchor (rung 1), so the
    ANCHOR's prices would be the ones copied the wrong way round."""
    claim = _claim(15315710, "Alden Coria", "Imanol Rodriguez", home_score=1, away_score=0)
    anchor = _anchor(15318678, "Imanol Rodriguez", "Alden Coria", sources={"betting": 0.5977})

    assert _ids(fold_twin_events([claim, anchor])) == [15315710, 15318678]


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
