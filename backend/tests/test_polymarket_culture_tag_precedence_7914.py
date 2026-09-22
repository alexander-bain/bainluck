"""#7914 — the `culture` catch-all stops deciding a badge, and a climate question
stops wearing a 💻 TECH chip.

THE READER'S COMPLAINT. Two shelves, one cause. "Will summer 2026 be France's
hottest summer on record?" and "Where will 2026 rank among the hottest years on
record?" are climate questions; the first wore 🎬 ENTERTAINMENT and the second
💻 TECH. "How many gays become Senator in Brazil Elections?" — five of those —
wore 🎬 ENTERTAINMENT. So did Costco's hotdog price and Valve's Deadlock.

THE CAUSE, TWO HALVES.

  1. `culture` is a catch-all like `awards`, and Polymarket lists tags in its own
     order, so a market tagged `Culture, Economy, Inflation` was decided by
     POSITION. #7874 demoted `awards`; this demotes `culture`.
  2. Demoting it alone would have left France on `tech`, because `Science`
     precedes `Weather` in its tag list and `_WEATHER_HAZARD_RE` knew hurricanes
     and wildfires but not "hottest summer on record". So the climate-record arm
     ships in the same change.

WHY #7874 HELD THIS BACK AND WHY IT NO LONGER APPLIES. #7874's replay modelled
`_tags_to_category` in ISOLATION and reported three wrong landings. Production
decides through a four-arm cascade whose arm 4 runs `misfiled_subject` AFTER the
tag map, and `weather` has been one of its epidemiology sources since #4264 — so
the two Ebola events never stop on `weather`, they land on `health`, which is
where #7914 said they belonged. Re-derived over the same banked 42 rows with the
cascade imported: `artifacts/d396-7914/rederive_culture_cascade.py`. Only France
survived, and half 2 above is its fix.

    The trap, stated once: a replay that imports one rule faithfully can still
    measure the wrong thing, because the rule is not the whole decision.

Every tag list below was read off Gamma on 2026-09-22 and is quoted verbatim;
event ids are in the test names so a later reader can re-read the venue rather
than trust this docstring.

THE CONTROLS ARE THE POINT. The tempting-but-wrong version of half 2 is to match
the bare superlative — `hottest|warmest|coldest` — which a production census of
the two correctable shelves would have blessed, because all three matches there
today are genuine climate markets. That census is present-absence evidence, not
a class guard (the CERT-540 lesson). "The hottest new AI startup", "the hottest
stock", "Hottest album of summer?" all land on the weather shelf under it.
`test_the_climate_arm_refuses_a_figurative_superlative` fails against exactly
that version and passes against the one that shipped.
"""
import pytest

from app.tasks.polymarket import (
    _WEAK_TAGS,
    _tags_to_category,
    resolve_event_category,
)
from app.utils.futures_categorization import misfiled_subject


def serve(tags: list[str], title: str) -> str:
    """The llm_sport_category production would store, through the WHOLE cascade.

    Not `_tags_to_category`: reading the tag map alone is the mistake this ship
    exists to correct. `group_names` is empty because arm 1 (table tennis) only
    fires when the tags said nothing usable, which is not true of any row here.
    """
    category, sport = _tags_to_category(tags)
    return resolve_event_category(category, sport, title, [])[1]


# ---------------------------------------------------------------------------
# The ship — half 1: `culture` stops outranking a subject tag
# ---------------------------------------------------------------------------

def test_culture_is_weak():
    """The one-line statement of half 1, so the set cannot be quietly reverted."""
    assert "culture" in _WEAK_TAGS


def test_the_brazil_election_rows_are_politics_not_entertainment_871036():
    """Events 871036/871037/871038/871039/871045, tagged `Culture, Politics, ...`.

    Five rows asking how many LGBT candidates win Brazilian federal and state
    offices. Unambiguously politics; the venue says so with its second tag.
    """
    assert serve(["Culture", "Politics"], "How many gays become Senator in Brazil Elections?") == "politics"


def test_costco_hotdog_price_is_economics_not_entertainment_96068():
    """Event 96068, tagged `Culture, Economy, Inflation`."""
    assert serve(["Culture", "Economy", "Inflation"], "Costco increases hotdog price before 2027?") == "economics"


def test_deadlock_is_esports_not_entertainment_598412():
    """Event 598412, tagged `Games, Valve, Culture, Esports`."""
    assert serve(["Games", "Valve", "Culture", "Esports"], "Will Valve officially release Deadlock before 2027?") == "esports"


def test_the_millennium_prize_is_tech_not_entertainment_745118():
    """Event 745118, tagged `Culture, Science`."""
    assert serve(["Culture", "Science"], "Will CMI declare a Millennium Prize Problem solved by ___?") == "tech"


def test_both_ebola_events_reach_health_through_arm_four_511422():
    """Events 511422 and 844717, tagged `Ebola, Culture, Weather, Pandemics, Hantavirus`.

    THE HEART OF THE RE-DERIVATION. The tag map alone answers `weather` here —
    that is what #7874 measured and why it held the demotion back. The cascade
    does not stop there: arm 4 reads the title, `weather` is an epidemiology
    source since #4264, and `ebola` is in the pattern.

    Asserting the ARM as well as the answer is deliberate. `health` reached by
    any other route would mean this ship stopped depending on the machinery its
    whole justification rests on.
    """
    tags = ["Ebola", "Culture", "Weather", "Pandemics", "Hantavirus"]
    for title in (
        "Which countries will have an Ebola case in 2026?",
        "Ebola: new country confirmed before October 1?",
    ):
        category, sport = _tags_to_category(tags)
        assert sport == "weather", "the tag map's answer is the premise of this test"
        assert resolve_event_category(category, sport, title, []) == ("health", "health", "subject")


# ---------------------------------------------------------------------------
# The ship — half 2: a climate record is a weather question
# ---------------------------------------------------------------------------

def test_frances_hottest_summer_is_weather_not_tech_838969():
    """Event 838969, tagged `France, Culture, Science, Weather, climate, global warming`.

    The one landing the re-derivation could not clear. `Science` precedes
    `Weather`, so with `culture` demoted the tag map says `tech`; the climate arm
    corrects it. Both halves of this ship are load-bearing for this single row,
    which is why they ship together.
    """
    tags = ["France", "Culture", "Science", "Weather", "climate", "global warming"]
    title = "Will summer 2026 be France's hottest summer on record?"
    category, sport = _tags_to_category(tags)
    assert sport == "tech", "the tag map's answer is the premise of this test"
    assert resolve_event_category(category, sport, title, []) == ("weather", "weather", "subject")


@pytest.mark.parametrize(
    "title",
    [
        # Both are LIVE on the `tech` shelf today and are corrected by half 2
        # alone — this ship is not inert without the culture demotion.
        "September 2026 1st, 2nd, or 3rd hottest on record?",
        "Where will 2026 rank among the hottest years on record?",
        # Shapes the same market family takes.
        "Will 2026 be the hottest year on record?",
        "Coldest winter in Chicago since 1985?",
        "Warmest February day on record in Boston?",
    ],
)
def test_a_climate_record_market_leaves_the_tech_shelf(title):
    assert misfiled_subject(title, "tech") == "weather"


# ---------------------------------------------------------------------------
# The controls — what the fix must NOT do
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "title",
    [
        "Hottest album of summer?",
        "Hottest album of the summer?",
        "Who will be the hottest new AI startup of 2026?",
        "Will the hottest stock double by December?",
        "Hottest toy of the holiday season?",
        "Will Taylor Swift have the hottest tour?",
    ],
)
def test_the_climate_arm_refuses_a_figurative_superlative(title):
    """THE CONTROL THIS SHIP IS GUARDED BY.

    Fails against "just match the superlative", which is the version a census of
    the correctable shelves would have approved, and which sends a market about
    an album, a startup or a stock to the weather shelf.

    `Hottest album of summer?` is the tight one and is why the gap between the
    superlative and its noun is ONE word rather than two: at two, "album of"
    fits between them and the pattern matches.
    """
    assert misfiled_subject(title, "tech") is None


def test_the_climate_arm_cannot_re_decide_a_market_already_on_weather():
    """The override still never returns the shelf a market is already on.

    `weather` is reachable by arm 4 only through the EPIDEMIOLOGY source set;
    the hazard/climate arm is gated on `_SUBJECT_OVERRIDE_SOURCES`. Widening the
    pattern must not have quietly widened that.
    """
    assert misfiled_subject("Will 2026 be the hottest year on record?", "weather") is None


def test_the_climate_arm_does_not_fire_on_a_word_bingo_market():
    """A market about who SAYS a phrase is about the speaker (D19)."""
    assert misfiled_subject("Will Trump say 'hottest summer on record' this week?", "tech") is None


@pytest.mark.parametrize(
    "title",
    [
        "How many acres will the Palisades wildfire burn by Friday?",
        "How many Tornadoes in the US in June?",
        "Will a Category 5 hurricane make landfall in 2026?",
        "Heat wave in Phoenix next week?",
    ],
)
def test_the_original_weather_hazards_still_fire(title):
    """The climate arm was added as a second alternation to an existing pattern.

    An alternation is the easy place to break what was already there — a stray
    group or a misplaced anchor takes the hazard words down with it, and every
    other test in this file would still pass. These are #7914's regression
    surface, not its ship.
    """
    assert misfiled_subject(title, "tech") == "weather"


def test_epidemiology_still_beats_the_climate_arm():
    """Stated ordering, not pattern order: a disease during a heatwave is health."""
    assert misfiled_subject("Flu deaths during the hottest summer on record?", "tech") == "health"


def test_a_culture_only_market_keeps_its_shelf():
    """A weak tag is not ignored — it still decides when it is all a market has.

    Fails against "delete `culture` from the map", which is the other tempting
    wrong version of half 1 and would drop these markets to `other`.
    """
    assert _tags_to_category(["Culture"]) == ("entertainment", "entertainment")
    assert serve(["Culture", "MrBeast", "YouTube", "Mentions", "Recurring"], "MrBeast mentions") == "entertainment"


def test_an_awards_and_culture_market_with_no_subject_tag_is_still_entertainment():
    """Event 839316, the Turner Prize, tagged `UK, Art, Awards, Culture`.

    With BOTH catch-alls now weak this is the row most likely to fall through to
    `other`. `UK` and `Art` are not keys in the map, so the second pass returns
    `awards` and an art prize keeps the entertainment shelf it belongs on.
    """
    assert serve(["UK", "Art", "Awards", "Culture"], "Turner Prize 2026 Winner") == "entertainment"
