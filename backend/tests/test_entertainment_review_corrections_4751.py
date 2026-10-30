"""Independent PR11624 review F1-F3, with the original numeric refusals retained."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.routes import entertainment
from tests.test_entertainment_ladder_coherence_4751 import market, names


@pytest.mark.parametrize("direction", ["Above", "Below"])
def test_float_noise_equal_prices_are_not_refused(direction):
    probabilities = [0.5, 0.03, (0.01 + 0.05) / 2]
    if direction == "Below":
        probabilities.reverse()
    subject = market(
        [(f"{direction} {n}", p) for n, p in zip([10, 20, 30], probabilities)]
    )
    before = deepcopy(subject)
    row = entertainment._market_row(subject, max_outcomes=8)
    assert not row.get("ladder_treatment_refused")
    assert sorted(o["prob"] for o in row["top_outcomes"]) == [3.0, 3.0, 50.0]
    assert subject == before


def test_real_small_reversal_remains_refused_even_when_display_rounds_equal():
    row = entertainment._market_row(
        market([("Above 10", 0.5), ("Above 20", 0.03), ("Above 30", 0.030001)])
    )
    assert row["ladder_treatment_refused"] is True


@pytest.mark.parametrize(
    "legs",
    [
        [("By June 2027", 0.9), ("By July 2027", 0.5), ("By August 2027", 0.1)],
        [
            ("By June 2027", 0.2),
            ("By July 2027", 0.6),
            ("By August 2027", 0.57),
            ("By Sept 2027", 0.9),
        ],
    ],
)
def test_unadmitted_date_policy_preserves_base_prices_without_new_trim_or_refusal(legs):
    subject = market(legs)
    subject.name = "When will X happen?"
    row = entertainment._market_row(subject, max_outcomes=8)
    assert not row.get("ladder_treatment_refused")
    assert {o["name"]: o["prob"] for o in row["top_outcomes"]} == {
        n: round(p * 100, 1) for n, p in legs
    }


@pytest.mark.parametrize("missing", ["null", "withheld"])
def test_spotify_served_calendar_slice_is_unranked_without_inventing_a_headline(
    missing,
):
    subject = market(
        [
            ("Before Dec 3", 0.2),
            ("Before Dec 4", 0.5),
            ("Before Dec 5", 0.8),
            ("Not in 2026", None if missing == "null" else 0.9),
        ]
    )
    subject.name = "When will Spotify release 2026 Wrapped?"
    subject.external_id = "KXSPOTIFYWRAPPED-26"
    before = deepcopy(subject)
    withheld = {subject.outcomes[-1].id} if missing == "withheld" else set()
    row = entertainment._build_music({"music": [subject]}, withheld)["spotify_race"][0]
    assert row["ladder"] is True
    assert names(row) == ["Before Dec 3", "Before Dec 4", "Before Dec 5"]
    assert [o["prob"] for o in row["top_outcomes"]] == [20, 50, 80]
    assert row["headline"] is None
    assert row["outcome_count"] == 4
    assert subject == before


def test_spotify_web_fixture_matches_actual_backend_output():
    subject = market(
        [
            ("Before Dec 3", 0.2),
            ("Before Dec 4", 0.5),
            ("Before Dec 5", 0.8),
            ("Not in 2026", None),
        ]
    )
    subject.name = "When will Spotify release 2026 Wrapped?"
    subject.external_id = "KXSPOTIFYWRAPPED-26"
    row = entertainment._build_music({"music": [subject]})["spotify_race"][0]
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "frontend/__tests__/fixtures/4751SpotifyCalendarSlice.json"
        ).read_text()
    )
    assert {key: row[key] for key in fixture} == fixture
