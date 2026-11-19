"""The served reading stays paired with its producer clock through projection."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.activitykit_payload import ActivityKitPayloadError
from app.utils.activitykit_projection import project_activitykit_snapshot

CLOCK = datetime(2026, 10, 5, tzinfo=timezone.utc)


def reading(**changes):
    return {
        "id": 42,
        "home_team": "Home",
        "away_team": "Away",
        "status": "live",
        "sport": "basketball_nba",
        "home_score": 0,
        "away_score": 1,
        "score_observed_at": CLOCK.isoformat(),
        "score_source": "statpal",
        "hero_probability": 0.565,
        "hero_probability_away": 0.435,
        "hero_probability_observed_at": CLOCK.isoformat(),
        **changes,
    }


def test_canonical_reading_and_zero_score_preserve_their_clocks():
    snapshot = project_activitykit_snapshot(reading())
    assert snapshot.home_rendered_percent == 57
    assert snapshot.home_score == 0
    assert snapshot.probability_observed_at == CLOCK
    assert snapshot.score_observed_at == CLOCK


@pytest.mark.parametrize(
    "pair,clock",
    [
        ((0.565, 0.435), CLOCK),
        ((0.565, 0.4), None),
        ((0.8, 0.2), None),
    ],
)
def test_current_reading_borrows_hero_clock_only_for_exact_pair(pair, clock):
    snapshot = project_activitykit_snapshot(
        reading(
            current_odds={
                "home_probability": pair[0],
                "away_probability": pair[1],
                "timestamp": CLOCK.isoformat(),
            }
        )
    )
    assert snapshot.probability_observed_at == clock
    assert snapshot.home_rendered_percent == (57 if clock is not None else None)


@pytest.mark.parametrize("current_home", [None, 0.565])
@pytest.mark.parametrize("opening_clock", [None, CLOCK.isoformat()])
def test_cached_opening_pair_cannot_become_a_live_activity_chance(current_home, opening_clock):
    detail = reading(
        hero_probability_source="opening",
        hero_probability_observed_at=opening_clock,
        current_odds={"home_probability": current_home, "away_probability": 0.435},
    )
    snapshot = project_activitykit_snapshot(detail)

    assert snapshot.lifecycle == "live"
    assert (snapshot.home_score, snapshot.away_score) == (0, 1)
    assert snapshot.score_observed_at == CLOCK
    assert snapshot.home_rendered_percent is None
    assert snapshot.probability_observed_at is None

    detail["hero_probability_source"] = "blend"
    detail["hero_probability_observed_at"] = CLOCK.isoformat()
    current = project_activitykit_snapshot(detail)
    assert current.home_rendered_percent == 57
    assert current.probability_observed_at == CLOCK


@pytest.mark.parametrize(
    "sport,expected", [("basketball_nba", 50), ("soccer_epl", 51), (None, 51)]
)
def test_two_way_pair_rounds_together_but_draw_and_unknown_sport_do_not(
    sport, expected
):
    snapshot = project_activitykit_snapshot(
        reading(
            sport=sport,
            hero_probability=0.505,
            hero_probability_away=0.505,
        )
    )
    assert snapshot.home_rendered_percent == expected


@pytest.mark.parametrize(
    "status,lifecycle",
    [
        (" completed ", "final"),
        ("FINAL", "final"),
        ("closed", "closed"),
        ("suspended", "suspended"),
        ("mystery", "unknown"),
    ],
)
def test_nonforecast_lifecycles_suppress_probability_and_its_clock(status, lifecycle):
    snapshot = project_activitykit_snapshot(reading(status=status))
    assert snapshot.lifecycle == lifecycle
    assert snapshot.home_rendered_percent is None
    assert snapshot.probability_observed_at is None
    assert snapshot.score_observed_at == CLOCK


@pytest.mark.parametrize("probability", [0.0, 1.0])
def test_extreme_probability_never_proves_a_final(probability):
    snapshot = project_activitykit_snapshot(
        reading(
            hero_probability=probability,
            hero_probability_away=1 - probability,
        )
    )
    assert snapshot.lifecycle == "live"
    assert not snapshot.is_terminal
    assert snapshot.home_rendered_percent == probability * 100


@pytest.mark.parametrize(
    "value", [None, True, float("nan"), float("inf"), -0.1, 1.1, "0.5"]
)
def test_invalid_current_reading_falls_back_to_hero_without_mixing_away(value):
    snapshot = project_activitykit_snapshot(
        reading(
            current_odds={
                "home_probability": value,
                "away_probability": 0.9,
            }
        )
    )
    assert snapshot.home_rendered_percent == 57
    assert snapshot.probability_observed_at == CLOCK


@pytest.mark.parametrize("clock", [None, "bad", "2026-10-05T00:00:00"])
def test_missing_or_naive_clock_never_borrows_receipt_or_row_time(clock):
    snapshot = project_activitykit_snapshot(
        reading(
            hero_probability_observed_at=clock,
            score_observed_at=clock,
            updated_at=CLOCK.isoformat(),
            timestamp=CLOCK.isoformat(),
        )
    )
    assert snapshot.home_rendered_percent is None
    assert snapshot.probability_observed_at is None
    assert snapshot.score_observed_at is None


def test_undated_projection_sends_score_without_a_chance():
    snapshot = project_activitykit_snapshot(
        reading(hero_probability_source="blend", hero_probability_observed_at=None)
    )
    wire = snapshot.content_state()["snapshot"]

    assert (wire["homeScore"], wire["awayScore"]) == (0, 1)
    assert "scoreObservedAt" in wire
    assert "homeRenderedPercent" not in wire
    assert "probabilityObservedAt" not in wire


def test_partial_score_and_missing_forecast_discard_orphan_clocks():
    snapshot = project_activitykit_snapshot(
        reading(
            home_score=None,
            hero_probability=None,
        )
    )
    assert snapshot.score_observed_at is None
    assert snapshot.probability_observed_at is None


def test_different_malformed_away_readings_do_not_borrow_hero_clock():
    snapshot = project_activitykit_snapshot(
        reading(
            hero_probability_away=1.3,
            current_odds={"home_probability": 0.565, "away_probability": 1.2},
        )
    )
    assert snapshot.home_rendered_percent is None
    assert snapshot.probability_observed_at is None


@pytest.mark.parametrize("source", [None, "", "  "])
def test_score_clock_requires_the_canonical_attribution_pair(source):
    snapshot = project_activitykit_snapshot(
        reading(
            score_source=source,
            updated_at=CLOCK.isoformat(),
            timestamp=CLOCK.isoformat(),
        )
    )
    assert snapshot.score_observed_at is None


def test_real_detail_formatter_dates_its_displayed_score_tuple():
    from app.routes.events import _format_event

    event = SimpleNamespace(
        id=42,
        home_team_name="Home",
        away_team_name="Away",
        commence_time=CLOCK,
        completed_at=None,
        status="live",
        home_score=0,
        away_score=1,
        score_source="statpal",
        score_observed_at=CLOCK,
        sport=SimpleNamespace(key="baseball_mlb", name="MLB"),
        box_score_data=None,
        win_probability_sources={},
        external_id="x",
    )
    detail = _format_event(event)
    assert detail["score_source"] == "statpal"
    assert detail["score_observed_at"] == CLOCK.isoformat()
    snapshot = project_activitykit_snapshot(detail)
    assert (snapshot.home_score, snapshot.away_score) == (0, 1)
    assert snapshot.score_observed_at == CLOCK


@pytest.mark.parametrize("changes", [{"id": 0}, {"home_team": ""}])
def test_invalid_identity_cannot_form_an_activity(changes):
    with pytest.raises(ActivityKitPayloadError):
        project_activitykit_snapshot(reading(**changes))


def test_full_headline_fields_project_for_live_and_final_college_game():
    """#12999 — server APNs push projects the same full headline as the iOS app."""
    live_detail = reading(
        home_team="Florida Gators",
        away_team="Houston Cougars",
        sport="basketball_ncaab",
        home_score=40,
        away_score=37,
        hero_probability=0.632,
        hero_probability_away=0.368,
        home_team_data={
            "abbreviation": "FLA",
            "primary_color": "#0021a5",
            "secondary_color": "#fa4616",
        },
        away_team_data={
            "abbreviation": "HOU",
            "primary_color": "#c8102e",
            "secondary_color": "#960c22",
        },
        espn={"period": "HT"},
    )
    live = project_activitykit_snapshot(live_detail)
    wire = live.content_state()["snapshot"]
    assert wire["sport"] == "basketball_ncaab"
    assert wire["homeRenderedPercent"] == 63
    assert wire["awayRenderedPercent"] == 37
    assert wire["homeHeadlineTenths"] == 632
    assert wire["homeAbbreviation"] == "FLA"
    assert wire["awayAbbreviation"] == "HOU"
    assert wire["homeColorHex"] == "#0021A5"
    assert wire["awayColorHex"] == "#C8102E"
    assert wire["awaySecondaryColorHex"] == "#960C22"
    assert wire["periodLabel"] == "HT"
    assert "result" not in wire

    # A running clock inside espn.period is dropped so a Live Activity never freezes a clock.
    clocked = project_activitykit_snapshot({**live_detail, "espn": {"period": "2nd 5:26"}})
    assert clocked.period_label is None

    # Final carries settled result and strict prematch_odds pair (never opening_odds).
    final_detail = reading(
        home_team="Florida Gators",
        away_team="Houston Cougars",
        sport="basketball_ncaab",
        status="completed",
        home_score=78,
        away_score=74,
        hero_settled_result="home",
        prematch_odds={
            "home_probability": 0.52,
            "away_probability": 0.48,
            "rendered_percents": [48, 52],
        },
        opening_odds={"home_probability": 0.70, "away_probability": 0.30},
        espn={"period": "Final"},
    )
    final = project_activitykit_snapshot(final_detail)
    final_wire = final.content_state()["snapshot"]
    assert final_wire["lifecycle"] == "final"
    assert final_wire["result"] == "home"
    assert final_wire["pregameAwayPercent"] == 48
    assert final_wire["pregameHomePercent"] == 52
    assert "periodLabel" not in final_wire
    assert "homeRenderedPercent" not in final_wire
    assert "awayRenderedPercent" not in final_wire
    assert "homeHeadlineTenths" not in final_wire

    # Opening odds alone never become the pregame pair (ruling 209).
    opening_only = project_activitykit_snapshot(
        {k: v for k, v in final_detail.items() if k != "prematch_odds"}
    )
    assert opening_only.pregame_away_percent is None
    assert opening_only.pregame_home_percent is None
