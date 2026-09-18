"""#6936 — a district-code regex compiled IGNORECASE claimed four hurricanes.

THE READER'S SPECIMEN (authority/461, production, 2026-09-18 11:34Z): searching
"Atlantic Hurricane Season" returned a card group headed **REGIONAL US
ELECTIONS** holding four hurricane questions. `_REGIONAL_US_ELECTION_RE`'s first
alternative — meant for `NJ-07` — is compiled `re.IGNORECASE` with an OPTIONAL
separator, so `be 1`, `at 5` and `BO3` all read as congressional districts.

WHY THE OBVIOUS FIX IS NOT ENOUGH, AND THE TEST SAYS SO IN A LIVE ARM.
Making the alternative case-sensitive removes the five lowercase hits and leaves
the biggest cohort untouched: `BO1`/`BO3`/`BO5` esports fixtures are ALREADY
upper case. Measured over the 500 highest-volume open markets that can carry the
shape — 91 claimed by the loose pattern, 59 of them esports. It is the SEPARATOR
that tells a district from a shorthand, which is why the repair reuses the
spelling this file had already blessed sixty lines below
(`_US_DISTRICT_RE`) rather than inventing a third one.
`test_case_sensitivity_alone_would_not_have_fixed_it` keeps that argument
falsifiable instead of leaving it in a comment.

BOTH DIRECTIONS (gotcha #43): a cap's guard has to prove it did not also stop
matching the family it exists for. `story:regional_us_elections` carries a
diversity cap of 1 and forces `quality_class = "low_quality"`, so a pattern that
swallows esports spends a real local election's only slot — and a pattern that
narrows too far silently un-caps the family. Both arms are asserted.
"""

import re

from app.utils.feed_market_quality import (
    _REGIONAL_US_ELECTION_RE,
    _US_DISTRICT_CODE,
    _US_DISTRICT_NUMBERED_PATTERN,
    _US_DISTRICT_PATTERN,
    _US_DISTRICT_RE,
    _story_key,
    classify_market_quality,
)

REGIONAL = "story:regional_us_elections"
US_STATE = "story:us_state_races"

# The pattern as it shipped before this fix. Written out rather than imported so
# the anti-vacuity arm below still means something after the source is repaired.
_LOOSE_AS_SHIPPED = re.compile(r"\b[A-Z]{2}[-\s]?\d{1,2}\b", re.IGNORECASE)

# Real production rows (open `futures_markets`, reach-ordered) — not invented
# specimens. Ids are the production ids at capture time, 2026-09-18.
NOT_DISTRICTS = [
    "Will there be 0 hurricanes during the Atlantic Hurricane Season?",
    "Will there be 1-3 hurricanes during the Atlantic Hurricane Season?",
    "Will there be 7+ hurricanes during the Atlantic Hurricane Season?",
    "Brent crude oil price on September 30, 2026 at 5:00 PM EDT?",
    "Gold price on September 30, 2026 at 5:00 PM EDT?",
    "Counter-Strike: MOUZ vs Natus Vincere (BO3) - StarLadder StarSeries Playoffs",
    "Counter-Strike: 3DMAX vs EYEBALLERS (BO1) - Logitech G Play Connect Group B",
    "LoL: Team WE vs JD Gaming (BO5) - LPL Regional Finals Playoffs",
    "Will the highest score achieved by an OpenAI model on Humanity's Last Exam "
    "in 2026 be 60% or higher?",
]

REAL_DISTRICTS = [
    "TX-15 House winner?",
    "NJ-11 Special Election winner?",
    "MN-01 House winner?",
    "NH-01 Democratic primary: voter turnout",
    "CO-06 House Election Margin of Victory",
]


class TestTheReadersSpecimen:
    def test_hurricane_questions_are_not_a_regional_us_election(self):
        for name in NOT_DISTRICTS:
            assert _REGIONAL_US_ELECTION_RE.search(name) is None, name
            assert _story_key(name, "politics") != REGIONAL, name

    def test_the_specimen_loses_the_reason_that_demoted_it(self):
        # `regional_election` forces `quality_class = "low_quality"`. Removing a
        # WRONG demotion is the whole ship; nothing else about the row moves.
        hurricane = "Will there be 1-3 hurricanes during the Atlantic Hurricane Season?"
        q = classify_market_quality(
            market_name=hurricane,
            sport_category="weather",
            status="open",
            outcome_names=["Yes", "No"],
        )
        assert "regional_us_election" not in q.reasons
        # The reasons the row already had are untouched — this is a deletion, not
        # a new admission path.
        assert "salient_entity" in q.reasons

    def test_the_oil_market_reaches_the_arm_that_was_always_meant_for_it(self):
        # `_story_key` tests the regional arm BEFORE `story:oil` twelve lines
        # below, so "at 5:00 PM EDT" was taking oil markets off the oil key.
        assert _story_key("Brent crude oil price on September 30, 2026 at 5:00 PM EDT?", "economics") == "story:oil"


class TestTheFamilyItExistsFor:
    def test_real_district_codes_still_key_regional(self):
        for name in REAL_DISTRICTS:
            assert _REGIONAL_US_ELECTION_RE.search(name) is not None, name
            assert _story_key(name, "politics") == REGIONAL, name

    def test_the_office_alternatives_stay_case_insensitive(self):
        # Only the district alternative is case-sensitive — `(?-i:…)` is scoped
        # for exactly this reason. Dropping IGNORECASE from the whole pattern
        # would have taken these with it.
        for name in [
            "maine state senate winner?",
            "Ohio City Council winner?",
            "virginia lieutenant governor election",
            "Texas Republican primary winner?",
        ]:
            assert _REGIONAL_US_ELECTION_RE.search(name) is not None, name

    def test_at_large_districts_still_belong_to_the_state_races_family(self):
        # THE ARM CI CAUGHT. `AK-AL` has no digits, so the regional alternative
        # never claimed it and it falls through to the sub-national key. Folding
        # `AL` into the shared pattern moves at-large seats between two families
        # whose caps are different product decisions — the first attempt at this
        # fix did exactly that and `test_us_congressional_districts` went red.
        assert _story_key("AK-AL House Election Winner", "politics") == US_STATE
        assert _US_DISTRICT_RE.search("AK-AL House Election Winner") is not None


class TestTheTwoSpellingsCannotDriftAgain:
    """The defect was a second copy of a pattern this file had already got right."""

    def test_both_spellings_are_built_from_one_shared_code(self):
        assert _US_DISTRICT_NUMBERED_PATTERN.startswith(_US_DISTRICT_CODE)
        assert _US_DISTRICT_PATTERN.startswith(_US_DISTRICT_CODE)
        # The separator is not optional in either, which is the load-bearing half.
        assert "[-\\s]?" not in _US_DISTRICT_CODE

    def test_the_regional_pattern_embeds_the_shared_spelling_verbatim(self):
        assert _US_DISTRICT_NUMBERED_PATTERN in _REGIONAL_US_ELECTION_RE.pattern
        assert f"(?-i:{_US_DISTRICT_NUMBERED_PATTERN})" in _REGIONAL_US_ELECTION_RE.pattern

    def test_the_subnational_regex_is_compiled_from_the_shared_pattern(self):
        assert _US_DISTRICT_RE.pattern == _US_DISTRICT_PATTERN


class TestTheseSpecimensReallyAreTheDefect:
    """Anti-vacuity: prove the rows above were claimed by the shipped pattern.

    Without this, every assertion in `TestTheReadersSpecimen` would keep passing
    against a pattern that had never had the bug.
    """

    def test_the_loose_pattern_claimed_every_one_of_them(self):
        for name in NOT_DISTRICTS:
            assert _LOOSE_AS_SHIPPED.search(name) is not None, name

    def test_case_sensitivity_alone_would_not_have_fixed_it(self):
        # The fix the issue suggested. It removes "be 1" and "at 5" and leaves
        # every `BO3` — 59 of the 64 false positives measured in production.
        case_sensitive_only = re.compile(r"\b[A-Z]{2}[-\s]?\d{1,2}\b")
        still_wrong = [n for n in NOT_DISTRICTS if case_sensitive_only.search(n)]
        assert [n.split(":")[0] for n in still_wrong] == [
            "Counter-Strike",
            "Counter-Strike",
            "LoL",
        ]
        # ...and the shipped repair takes them.
        assert not [n for n in still_wrong if _REGIONAL_US_ELECTION_RE.search(n)]
