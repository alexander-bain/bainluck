"""Q446 / CAL-P132 — 104 markets on the tech shelf that are flu and earthquakes.

THE MEASUREMENT, production 2026-08-29. `llm_sport_category = 'tech'` holds:

     71  epidemiology     "Flu Hospitalization Rate Week 32, 2026?"
                          "Will there be at least 5000 measles cases in the U.S. in 2026?"
     26  seismic/volcanic "10.0 or above earthquake before 2027?"
      7  weather hazard   "Palisades wildfire burns 10,000 acres by Friday?"
                          "How many Tornadoes in the US in June?"

WHY THE TAG MAP CANNOT FIX IT. Polymarket tags "Flu Hospitalization Rate Week 10"
with the single tag `tech`, and the earthquake markets with `['earthquakes','tech']`.
There is no tag to remap. The title is the only place the subject is written down.

WHAT SHIPS, AND WHAT DOES NOT. Epidemiology has a `health` shelf and weather hazards
have a `weather` shelf, both already populated. The 26 seismic and volcanic markets
have no right shelf — an earthquake is not weather — and are deliberately left where
they are, raised as a taxonomy question instead of moved somewhere else that is also
wrong. Routing them to `other` would be a no-op regardless: the Polymarket writer
only updates `llm_sport_category` when the new value is not "other".

Measured over all 2,845 open markets on a correctable shelf: 33 move, and every one
of them is one of the two named kinds.
"""

import pytest

from app.utils.futures_categorization import WORD_BINGO_CATEGORY, misfiled_subject


# --------------------------------------------------------------------------
# Moves — real production titles
# --------------------------------------------------------------------------

TO_HEALTH = [
    "Flu Hospitalization Rate Week 32, 2026?",
    "Will there be at least 5000 measles cases in the U.S. in 2026?",
    "Will there be at least 1000 measles cases in the U.S. in 2026?",
    "New Coronavirus Pandemic in 2026?",
    "CDC issues Level 3 warning by December 31?",
    "Measles cases in 2026?",
    "Bird flu outbreak in 2026?",
]

TO_WEATHER = [
    "Palisades wildfire burns 10,000 acres by Friday?",
    "Will Palisades wildfire spread to Malibu by Sunday?",
    "How many Tornadoes in the US in June?",
    "Named storm forms before hurricane season?",
]


@pytest.mark.parametrize("name", TO_HEALTH)
def test_epidemiology_moves_to_health(name):
    assert misfiled_subject(name, "tech") == "health"


@pytest.mark.parametrize("name", TO_WEATHER)
def test_weather_hazards_move_to_weather(name):
    assert misfiled_subject(name, "tech") == "weather"


# --------------------------------------------------------------------------
# The three refusals, each one a specimen the first cut got wrong
# --------------------------------------------------------------------------

SEISMIC = [
    "10.0 or above earthquake before 2027?",
    "Highest earthquake magnitude in 2026?",
    "How many 6.5 or above earthquakes August 17 - August 23?",
    "Magnitude 6.5+ earthquake in LA before 2027?",
    "Major volcano eruption (VEI ≥6) in 2026?",
]


@pytest.mark.parametrize("name", SEISMIC)
def test_seismic_and_volcanic_are_left_alone(name):
    """An earthquake is not weather, and `other` would be a no-op at the writer.

    26 markets. Named in the report and escalated as a taxonomy question rather than
    filed somewhere else that is also wrong. If a natural-hazard shelf is ever added,
    this is the test that should change.
    """
    assert misfiled_subject(name, "tech") is None


WORD_BINGO = [
    "Will Trump say \"Fever\" or \"Flu\" this week?",
    "Will Leavitt say \"CDC\" or \"WHO\" during the next White House Press Briefing?",
    "Will Tim Cook mention \"pandemic\" during the Apple WWDC 2026 event?",
]


@pytest.mark.parametrize("name", WORD_BINGO)
def test_word_bingo_is_about_the_speaker_not_the_word(name):
    """MEASURED FAILURE of the first cut, on production.

    A wider version of this rule moved both of the first two out of `politics` and
    onto the `health` shelf, because their titles contain "Flu" and "CDC". The
    subject of "Will Trump say X" is Trump.

    **Destination changed by Alex ruling D19 (2026-08-30), the assertion's INTENT
    did not.** These used to return None — "leave it alone, just don't call it
    health". They now get their own shelf. What this test has always been about is
    that the SUBJECT regexes must not claim them, and that is asserted directly
    below rather than inferred from a None: `soundbite` is neither `health` nor
    `weather`, so the measured failure this test records still cannot recur.
    """
    for shelf in ("tech", "other"):
        got = misfiled_subject(name, shelf)
        assert got not in ("health", "weather"), (
            f"the subject regexes claimed a word-bingo market: {name!r} -> {got!r}"
        )
        assert got == WORD_BINGO_CATEGORY


@pytest.mark.parametrize(
    "name",
    [
        # A say/mention verb with neither an occasion nor a quoted token is NOT a
        # confident word-bingo claim, so the original refusal still applies in
        # full. D19 must not have turned the loose guard into a loose claim.
        "Will the Fed say rates will fall?",
        "Will the report mention a recession?",
    ],
)
def test_a_loose_verb_match_is_still_refused(name):
    assert misfiled_subject(name, "tech") is None
    assert misfiled_subject(name, "other") is None


# --------------------------------------------------------------------------
# Shelf scoping
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shelf", ["politics", "geopolitics", "economics", "legal", "culture"])
def test_only_tech_and_other_are_correctable(shelf):
    """MEASURED: widening to politics/geopolitics moved ten more open markets, two of
    them plainly wrong. Re-shelving politics is somebody's decision, not a side
    effect of fixing tech.
    """
    assert misfiled_subject("Flu Hospitalization Rate Week 32, 2026?", shelf) is None
    assert misfiled_subject("Where will Tropical Storm Saudel make landfall?", shelf) is None


@pytest.mark.parametrize("shelf", ["health", "weather"])
def test_a_correctly_shelved_market_is_never_re_decided(shelf):
    """Two classifiers that both answer a settled question eventually disagree."""
    assert misfiled_subject("Flu Hospitalization Rate Week 32, 2026?", shelf) is None
    assert misfiled_subject("Palisades wildfire burns 10,000 acres?", shelf) is None


@pytest.mark.parametrize("shelf", ["basketball", "football", "golf", "tennis"])
def test_a_sport_market_is_never_taken_off_its_sport(shelf):
    """The caller's sport-promotion arms run first and win; this is the backstop."""
    assert misfiled_subject("The Flu Game anniversary jersey drop?", shelf) is None
    assert misfiled_subject("Will the Hurricanes win the Stanley Cup?", shelf) is None


def test_epidemiology_beats_weather_when_a_title_has_both():
    assert (
        misfiled_subject("Flu outbreak during hurricane season 2026?", "tech") == "health"
    )


def test_an_empty_title_is_not_a_subject():
    assert misfiled_subject("", "tech") is None
    assert misfiled_subject(None, "tech") is None


def test_an_ordinary_tech_market_is_untouched():
    for name in (
        "Will OpenAI release GPT-6 before 2027?",
        "#1 Free App in the US Apple App Store on February 20?",
        "Will SpaceX launch Starship in 2026?",
    ):
        assert misfiled_subject(name, "tech") is None
