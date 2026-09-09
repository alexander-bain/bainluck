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

from app.utils.futures_categorization import misfiled_subject


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
    """
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


def test_the_health_shelf_is_never_re_decided():
    """Two classifiers that both answer a settled question eventually disagree.

    AMENDED by #4264. This test used to be parametrized over `["health", "weather"]`
    and asserted the flu title returned None on BOTH. The `weather` half of it was
    the bug: it encoded "a market filed `weather` is correctly filed", which is true
    of a hurricane and false of a hantavirus pandemic — and 22 open production
    markets were sitting behind it. The clause survives for `health`, which is the
    destination this override moves things TO and therefore genuinely settled.
    """
    assert misfiled_subject("Flu Hospitalization Rate Week 32, 2026?", "health") is None
    assert misfiled_subject("Palisades wildfire burns 10,000 acres?", "health") is None


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


# ==========================================================================
# #4264 — the same defect one shelf over: disease markets on `weather`
# ==========================================================================
#
# A reader at 390px, production `6f24a670`, page one slot 5:
#
#     🌤  WEATHER        Resolves Dec 30, 2026
#     3%
#     Hantavirus pandemic in 2026?
#
# CAL-P132 censused the `tech` shelf and scoped its fix to what it had measured.
# Nobody censused `weather`. Measured 2026-09-09 against production, open markets,
# `llm_sport_category = 'weather'`: 22 rows whose titles name a disease, all 22 from
# Polymarket — so the cascade's arm 4 does reach them and a code fix is not inert.
#
# THE TITLES BELOW ARE THE PRODUCTION ROWS, not invented specimens. All 22.

WEATHER_SHELF_DISEASE = [
    "Measles cases in U.S. in 2026?",
    "Flu Hospitalization Rate Week 15, 2026?",
    "Flu Hospitalization Rate Week 17, 2026?",
    "Hantavirus pandemic in 2026?",
    "Hantavirus vaccine in 2026?",
    "Flu Hospitalization Rate Week 18, 2026?",
    "Ebola pandemic in 2026?",
    "Which countries will have an Ebola case in 2026?",
    "Will Uganda have an Ebola case in 2026?",
    "Will South Sudan have an Ebola case in 2026?",
    "Will Rwanda have an Ebola case in 2026?",
    "Will Burundi have an Ebola case in 2026?",
    "Will the United States have an Ebola case in 2026?",
    "Will Canada have an Ebola case in 2026?",
    "Will Kenya have an Ebola case in 2026?",
    "Will India have an Ebola case in 2026?",
    "Will the Republic of the Congo have an Ebola case in 2026?",
    "Will Nigeria have an Ebola case in 2026?",
    "Will Ethiopia have an Ebola case in 2026?",
    "Will Somalia have an Ebola case in 2026?",
    "Will China have an Ebola case in 2026?",
    "Flu Hospitalization Rate Week 22, 2026?",
]


@pytest.mark.parametrize("name", WEATHER_SHELF_DISEASE)
def test_a_disease_market_leaves_the_weather_shelf(name):
    assert misfiled_subject(name, "weather") == "health"


def test_the_whole_measured_population_moves_and_nothing_is_left_behind():
    """The BEFORE count is the assertion, not a spot check.

    A parametrized per-title test goes green if 21 of 22 move; the reader still
    sees a sun over a pandemic. This pins the denominator.
    """
    moved = [n for n in WEATHER_SHELF_DISEASE if misfiled_subject(n, "weather") == "health"]
    assert len(moved) == 22, f"{22 - len(moved)} of 22 still stranded on weather"


def test_hantavirus_is_reachable_without_a_second_disease_word():
    """"Hantavirus vaccine in 2026?" names no other disease word.

    Its sibling "Hantavirus pandemic in 2026?" was already caught by `pandemic`, so
    a fix that widened only the shelf and not the pattern would have left this one
    row behind — and the two are the same market to a reader.
    """
    assert misfiled_subject("Hantavirus vaccine in 2026?", "weather") == "health"
    assert misfiled_subject("Hantavirus outlook 2026?", "tech") == "health"


# --------------------------------------------------------------------------
# The control. This is the half that can fail.
# --------------------------------------------------------------------------
#
# The easy over-correction is a blanket "the weather shelf is suspect" sweep, and
# that is a bigger regression than the bug: 982 open markets sit on `weather`
# legitimately. These are real titles sampled from that population.

GENUINELY_WEATHER = [
    "Will the world pass 2 degrees Celsius over pre-industrial levels?",
    "Will a supervolcano erupt before 2050?",
    "Will there be an at least 8.0 magnitude earthquake in 2026?",
    "EU meets its 2030 climate goals?",
    "Arctic sea ice extent below 4 million km2 in 2026?",
    "Will El Nino conditions return before 2027?",
    "Vail ski resort opening date 2026?",
    "White Christmas in NYC in 2026?",
    "Highest temperature in Phoenix in July?",
    "How many named storms in the 2026 Atlantic season?",
]


@pytest.mark.parametrize("name", GENUINELY_WEATHER)
def test_a_genuine_weather_market_stays_on_the_weather_shelf(name):
    assert misfiled_subject(name, "weather") is None


@pytest.mark.parametrize(
    "name",
    [
        "Palisades wildfire burns 10,000 acres by Friday?",
        "How many Tornadoes in the US in June?",
        "Named storm forms before hurricane season?",
        "Where will Tropical Storm Saudel make landfall?",
    ],
)
def test_the_weather_hazard_arm_still_cannot_fire_on_the_weather_shelf(name):
    """Only the EPIDEMIOLOGY arm widened.

    These titles DO move when they are on `tech` — that is CAL-P132's ship and it is
    unchanged. What must not happen is this override answering "weather" about a
    market already filed `weather`: it can then never re-decide a market into the
    shelf it is already on, which is the clause the widening had to preserve.
    """
    assert misfiled_subject(name, "weather") is None
    assert misfiled_subject(name, "tech") == "weather"


def test_word_bingo_survives_the_widening():
    """"Will Trump say 'Ebola'?" is politics wherever it is currently filed."""
    assert misfiled_subject("Will Trump say 'Ebola' this week?", "weather") is None
    assert misfiled_subject("Will Leavitt mention 'CDC' at the briefing?", "weather") is None


@pytest.mark.parametrize("shelf", ["politics", "geopolitics", "economics", "legal", "culture"])
def test_the_widening_did_not_reopen_the_shelves_cal_p132_refused(shelf):
    """#4264 added `weather` to the epidemiology arm and NOTHING else.

    The measured reason those five stay shut is unchanged: widening to politics moved
    ten more markets, two of them plainly wrong.
    """
    assert misfiled_subject("Ebola pandemic in 2026?", shelf) is None
    assert misfiled_subject("Hantavirus pandemic in 2026?", shelf) is None


@pytest.mark.parametrize("shelf", ["basketball", "hockey", "golf"])
def test_a_sport_market_is_still_never_taken_off_its_sport(shelf):
    assert misfiled_subject("Will the Hurricanes win the Stanley Cup?", shelf) is None
    assert misfiled_subject("The Flu Game anniversary jersey drop?", shelf) is None
