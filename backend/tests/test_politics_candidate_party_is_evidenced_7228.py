"""#7228 — the /politics candidate badge states a party only where one is evidenced.

Measured on production 2026-09-19 (release v4776 `8cb3172e`), inside the
headline card *"2028 Democratic presidential nominee"*: **Rahm Emanuel, James
Talarico, Ro Khanna and Abdul El-Sayed — four Democrats — were badged `I`**,
in the served payload, not by the renderer:

    GET /api/politics -> themes.presidential.candidates[11]
    {"name": "Ro Khanna", "party": "I", "kalshi": 1.8, "poly": 1.4, ...}

Cause: `_detect_party()` was an allowlist of 30 surnames per party whose
fall-through `return "I"` turned every miss into a positive claim about a real
person — the allowlist-with-a-non-raising-default class. The list is 2024-era
and fixed, so the defect grows with every new name the field acquires.

TWO THINGS ARE PINNED HERE, and they are different claims:

1.  A miss is no longer *asserted*. `_detect_party` returns the caller's
    fallback (default `""`), and `"I"` went back to being a verdict that needs
    the name to say so.
2.  The contest is evidence. A candidate in the Democratic nomination race is a
    Democrat because that is what the race IS, so the presidential card passes
    `dem_primary -> "D"` / `gop_primary -> "R"` as the fallback and Ro Khanna
    badges **D** — right, not merely blank.

⚠️  A TEST THAT ONLY ASSERTS "nobody is badged I" PASSES ON AN EMPTY LADDER, and
a `None` headline satisfies every negative (the shape #3838's suite inherited
from #5541). So every case below asserts the positive — the ladder was built,
the specimen is in it, and it carries the right letter — beside the negative.

⚠️  THE FOUR NAMES MUST STAY OFF BOTH ALLOWLISTS. `TestTheSpecimensAreMisses`
fails the moment someone "fixes" this issue by appending surnames, which is the
repair this test exists to refuse: the next unrecognised name would be badged
falsely again.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.politics import (
    _build_presidential,
    _detect_party,
    _extract_dem_prob,
)

_NOW = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)

# The four production specimens: Democrats the allowlist has not heard of.
_UNKNOWN_DEMOCRATS = [
    "Rahm Emanuel",
    "James Talarico",
    "Ro Khanna",
    "Abdul El-Sayed",
]

# Democratic-nominee field, at production's shape: recognised names first, then
# the four specimens at their real (small) prices.
_DEM_LEGS = [
    ("Alexandria Ocasio-Cortez", 0.171), ("Jon Ossoff", 0.158),
    ("Gavin Newsom", 0.131), ("Kamala Harris", 0.078),
    ("Pete Buttigieg", 0.051), ("Josh Shapiro", 0.046),
    ("Rahm Emanuel", 0.021), ("James Talarico", 0.019),
    ("Ro Khanna", 0.018), ("Abdul El-Sayed", 0.014),
]

_GOP_LEGS = [
    ("JD Vance", 0.520), ("Marco Rubio", 0.121), ("Ron DeSantis", 0.061),
    ("Glenn Youngkin", 0.032), ("Byron Donalds", 0.024),
    ("Brian Kemp", 0.021), ("Tim Sheehy", 0.011),
]

_GENERAL_LEGS = [
    ("JD Vance", 0.211), ("Alexandria Ocasio-Cortez", 0.132),
    ("Jon Ossoff", 0.116), ("Marco Rubio", 0.097),
    ("Gavin Newsom", 0.076), ("Ro Khanna", 0.011),
]


def _outcome(name: str, prob: float, oid: int):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob,
        probability_change_24h=None, rank=None,
    )


def _market(name, legs, *, source, market_id, external_id, base):
    return SimpleNamespace(
        id=market_id, name=name, source=source, external_id=external_id,
        outcomes=[_outcome(n, p, base + i) for i, (n, p) in enumerate(legs)],
    )


def _kalshi_dem():
    return _market(
        "2028 Democratic presidential nominee", _DEM_LEGS[:8],
        source="kalshi", market_id=108445, external_id="KXPRESNOMD-28", base=100,
    )


def _poly_dem():
    return _market(
        "Democratic Presidential Nominee 2028", _DEM_LEGS,
        source="polymarket", market_id=112895, external_id="30829", base=200,
    )


def _kalshi_gop():
    return _market(
        "2028 Republican presidential nominee", _GOP_LEGS,
        source="kalshi", market_id=108446, external_id="KXPRESNOMR-28", base=300,
    )


def _poly_general():
    return _market(
        "Presidential Election Winner 2028", _GENERAL_LEGS,
        source="polymarket", market_id=112897, external_id="31552", base=400,
    )


def _candidates(markets):
    response, _ = _build_presidential(markets, now=_NOW)
    return {c["name"]: c for c in response["candidates"]}, response


class TestTheSpecimensAreMisses:
    """The premise: these four names are unknown to BOTH allowlists.

    If a later change makes them known by appending surnames, every test below
    would pass while the class — the next unrecognised Democrat — is untouched.
    """

    @pytest.mark.parametrize("name", _UNKNOWN_DEMOCRATS)
    def test_the_bare_name_carries_no_party_evidence(self, name):
        assert _detect_party(name) == "", (
            f"{name} is now recognised by an allowlist — this issue was "
            "'fixed' by appending a surname, which fixes one name and leaves "
            "the class. Keep the specimens unknown."
        )


class TestAMissIsNeverAssertedIndependent:
    @pytest.mark.parametrize("name", _UNKNOWN_DEMOCRATS)
    def test_the_fall_through_is_not_a_claim(self, name):
        assert _detect_party(name) != "I", (
            "an unrecognised name must not be STATED to be an Independent"
        )

    def test_the_caller_chooses_what_a_miss_means(self):
        assert _detect_party("Ro Khanna", "D") == "D"
        assert _detect_party("Ro Khanna", "R") == "R"
        assert _detect_party("Ro Khanna") == ""

    @pytest.mark.parametrize("name,expected", [
        ("Gavin Newsom", "D"),
        ("Kamala Harris", "D"),
        ("JD Vance", "R"),
        ("Marco Rubio", "R"),
    ])
    def test_a_recognised_name_outranks_the_fallback(self, name, expected):
        """A Republican in a Democratic field is still badged R, not D."""
        assert _detect_party(name, "D") == expected
        assert _detect_party(name, "R") == expected
        assert _detect_party(name) == expected

    @pytest.mark.parametrize("name", [
        "Angus King (I)",
        "Independent candidate",
        "Bill Walker (Independent)",
    ])
    def test_independent_is_a_positive_verdict_again(self, name):
        assert _detect_party(name, "D") == "I", (
            "a name that SAYS independent is badged I even inside a party "
            "field — the letter is earned by evidence, not by a fall-through"
        )


class TestTheDemocraticLadderBadgesDemocrats:
    """The production case, through the route that serves the card."""

    def test_the_four_specimens_are_badged_d(self):
        candidates, response = _candidates([_kalshi_dem(), _poly_dem()])
        # POSITIVE: the ladder was built and it is the Democratic race.
        assert response["headline_q"] == "2028 Democratic presidential nominee"
        for name in _UNKNOWN_DEMOCRATS:
            assert name in candidates, f"{name} must be IN the ladder to be graded"
            assert candidates[name]["party"] == "D", (
                f"{name} is a Democrat in the Democratic nomination race"
            )

    def test_no_candidate_in_a_democratic_field_is_badged_independent(self):
        candidates, _ = _candidates([_kalshi_dem(), _poly_dem()])
        assert len(candidates) >= len(_DEM_LEGS)
        assert [c["name"] for c in candidates.values() if c["party"] == "I"] == []

    def test_the_republican_field_badges_its_unknowns_r(self):
        candidates, response = _candidates([_kalshi_gop()])
        assert response["headline_q"] == "2028 Republican presidential nominee"
        assert candidates["Byron Donalds"]["party"] == "R"
        assert candidates["Tim Sheehy"]["party"] == "R"
        assert candidates["JD Vance"]["party"] == "R"


class TestAContestWithNoPartyClaimsNothing:
    def test_the_general_election_leaves_an_unknown_name_unbadged(self):
        candidates, response = _candidates([_poly_general()])
        # POSITIVE: the general-election ladder was built, both parties on it.
        assert response["headline_q"] == "Presidential Election Winner 2028"
        assert candidates["JD Vance"]["party"] == "R"
        assert candidates["Alexandria Ocasio-Cortez"]["party"] == "D"
        # The miss: no evidence either way, so no claim either way.
        assert candidates["Ro Khanna"]["party"] == "", (
            "a general-election ladder is not evidence of anyone's party; the "
            "badge is omitted rather than invented"
        )


class TestTheOtherCallSiteIsUnchanged:
    """`_extract_dem_prob` tested `== "D"` / `== "R"`, and "" is neither.

    It failed closed on a miss before this change (an unknown name fell through
    both loops and the state was omitted from the Senate map) and must still.
    """

    def test_an_unknown_name_still_yields_no_dem_probability(self):
        m = _market(
            "Ohio Senate election winner",
            [("Ro Khanna", 0.44), ("Abdul El-Sayed", 0.56)],
            source="kalshi", market_id=900, external_id="KXSENOH", base=500,
        )
        assert _extract_dem_prob(m) is None

    def test_a_recognised_democrat_still_yields_one(self):
        m = _market(
            "Ohio Senate election winner",
            [("Sherrod Brown (D)", 0.51), ("Bernie Moreno", 0.49)],
            source="kalshi", market_id=901, external_id="KXSENOH", base=600,
        )
        assert _extract_dem_prob(m) == pytest.approx(0.51)
