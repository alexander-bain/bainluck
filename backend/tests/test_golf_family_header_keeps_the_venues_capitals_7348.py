"""#7348 — a golf family must not head itself `Bmw Pga Championship` when its own
members spell the tournament correctly.

WHAT A READER SAW. `https://bainluck.com/search?q=pga`, production `3fa9d18c`,
2026-09-20 03:58Z: the answers group headed **`Bmw Pga Championship`**. That is Alex's
bug report 145 — "awkward to see 'Mma' with the 2nd and 3rd letter in lowercase"
(#1938) — on a tournament a reader had searched for BY ITS ACRONYM.

THE MECHANISM IS A VOTE OVER STRINGS OF UNEQUAL QUALITY. Kalshi ships this one
tournament both ways, and `_golf_tournament_bundle_copy` picked the most common
spelling. Corpus-wide the correct one leads 5-to-3, so the rule looks sound — but
the family the reader actually got held FOUR members, three garbled to one correct:

    Bmw Pga Championship: Top 10 Finishers      <- garbled
    BMW PGA Championship End of Round 3 Leader  <- correct
    Bmw Pga Championship: Top 5 Finishers       <- garbled
    Bmw Pga Championship: Top 20 Finishers      <- garbled

A majority vote on a subset is a coin flip, and this family lost it.

🔴 THE VERBATIM RULE IS NOT WHAT IS BEING FIXED, and these tests exist partly to stop a
later reader "simplifying" it away. Cutting the name verbatim from the venue's own
string is the only thing that recovers `BMW`, the apostrophe in `Nationwide Children's`
and every acronym we neither enumerate nor should. The gate added here does not invent
casing: every candidate remains a string the venue wrote. It only declines to count a
candidate that is indistinguishable from `str.title()` output as evidence of casing.

ONE HELPER, BOTH SURFACES. `story_family_label` routes `/api/events/search` into the
same function the Discover bundler uses, so both are driven below — a fix proved on one
surface only is a fix that can silently drift on the other.
"""

import pytest

from app.utils.discover_bundles import (
    assemble_story_theme_bundles,
    story_family_label,
)
from app.utils.feed_market_quality import golf_tournament_story_key as _story_key

#: The four members of the family production actually served, in served order.
#: Three garbled, one correct — the minority spelling is the right one.
PGA_SEARCH_FAMILY_AS_SERVED = [
    "Bmw Pga Championship: Top 10 Finishers",
    "BMW PGA Championship End of Round 3 Leader",
    "Bmw Pga Championship: Top 5 Finishers",
    "Bmw Pga Championship: Top 20 Finishers",
]

#: Same tournament, no correct spelling anywhere in the family. There is no evidence
#: to act on, so the header must not change — we never invent capitals.
PGA_FAMILY_ALL_GARBLED = [
    "Bmw Pga Championship: Top 10 Finishers",
    "Bmw Pga Championship: Top 5 Finishers",
]

#: Tournaments whose real names ARE plain title case. These must be byte-identical
#: to the pre-#7348 behaviour; they are the regression surface of the whole change.
PLAIN_TITLE_CASE_TOURNAMENTS = [
    (
        [
            "Biltmore Championship Asheville - Winner",
            "Biltmore Championship Asheville - Top 10 Finish",
        ],
        "Biltmore Championship Asheville",
    ),
    (["The Open Winner", "The Open - Top 10 Finish"], "The Open"),
]


def _key(name: str) -> str | None:
    return _story_key(name)


def _feed_items(names: list[str]) -> list[dict]:
    """The Discover folder's input shape, mirroring #6423's own harness."""
    return [
        {
            "type": "futures",
            "score": float(100 - i),
            "_sort_time": 0,
            "_quality_story_key": _key(name),
            "data": {
                "id": 9000 + i,
                "name": name,
                "llm_sport_category": "golf",
                "discover_card": {},
            },
        }
        for i, name in enumerate(names)
    ]


class TestTheDefectIsRealAndTheTestCanFail:
    """🔴 A guard that cannot fail proves nothing. Before asserting the fix, pin that
    the specimen genuinely inverts a plain majority vote — otherwise a later reader
    cannot tell whether these tests are watching anything at all."""

    def test_the_garbled_spelling_is_the_majority_in_the_family_as_served(self):
        """The pre-#7348 rule was `max(names, key=count)`. On this family that
        returns the damaged string, which is exactly what production served."""
        spellings = [
            "Bmw Pga Championship"
            if n.startswith("Bmw")
            else "BMW PGA Championship"
            for n in PGA_SEARCH_FAMILY_AS_SERVED
        ]
        assert spellings.count("Bmw Pga Championship") == 3
        assert spellings.count("BMW PGA Championship") == 1
        # The plain majority vote — the old behaviour — picks the damaged one.
        assert max(spellings, key=spellings.count) == "Bmw Pga Championship"

    def test_title_case_is_exactly_the_transform_that_damages_the_acronym(self):
        """The gate keys on `t != t.title()`, so this is the property it rests on:
        `.title()` is what turns `BMW` into `Bmw`, and the damaged string is
        indistinguishable from that function's own output."""
        assert "BMW PGA Championship".title() == "Bmw Pga Championship"
        assert "Bmw Pga Championship".title() == "Bmw Pga Championship"


class TestTheSearchFamilyHeader:
    """The surface in the issue: `/api/events/search` -> `story_family_label`."""

    def test_the_family_keeps_the_venues_capitals_though_they_are_outvoted(self):
        label = story_family_label(
            _key(PGA_SEARCH_FAMILY_AS_SERVED[0]), PGA_SEARCH_FAMILY_AS_SERVED
        )
        assert label == "BMW PGA Championship"

    def test_the_readers_own_acronym_is_never_lowercased(self):
        """Stated as the reader-visible rule rather than as one string, so a future
        spelling change cannot pass by matching a literal."""
        label = story_family_label(
            _key(PGA_SEARCH_FAMILY_AS_SERVED[0]), PGA_SEARCH_FAMILY_AS_SERVED
        )
        assert "Pga" not in label
        assert "Bmw" not in label

    def test_no_evidence_means_no_change(self):
        """Fail open. Every member is damaged, so there is nothing to prefer and
        nothing is invented — we do not up-case a string the venue never wrote."""
        label = story_family_label(
            _key(PGA_FAMILY_ALL_GARBLED[0]), PGA_FAMILY_ALL_GARBLED
        )
        assert label == "Bmw Pga Championship"

    @pytest.mark.parametrize("names,expected", PLAIN_TITLE_CASE_TOURNAMENTS)
    def test_a_plain_title_case_tournament_is_untouched(self, names, expected):
        assert story_family_label(_key(names[0]), names) == expected

    def test_the_apostrophe_name_still_survives_verbatim(self):
        names = [
            "Nationwide Children's Hospital Championship - Winner",
            "Nationwide Children's Hospital Championship - Top 10 Finish",
        ]
        assert (
            story_family_label(_key(names[0]), names)
            == "Nationwide Children's Hospital Championship"
        )


class TestTheDiscoverCardAReaderActuallyGets:
    """The same helper heads the Discover bundle. #6423 learned the hard way that
    helper-level tests stay green while the shipped wiring reverts, so this drives
    the public folder."""

    def test_the_folded_card_keeps_the_venues_capitals(self):
        out = assemble_story_theme_bundles(_feed_items(PGA_SEARCH_FAMILY_AS_SERVED))
        bundles = [i for i in out if i.get("type") == "bundle"]
        assert len(bundles) == 1, out
        bundle = bundles[0]
        assert bundle["headline"] == "BMW PGA Championship"
        assert bundle["data"]["title"] == "BMW PGA Championship"
        assert bundle["reason"] == "What happens at the BMW PGA Championship?"
        assert bundle["data"]["shared_question"] == (
            "What happens at the BMW PGA Championship?"
        )

    def test_the_damaged_spelling_reaches_no_reader_facing_string(self):
        """Notice 34's neighbour: not our internal words this time, but the venue's
        worse string. Checked across every string the bundle puts on a screen."""
        out = assemble_story_theme_bundles(_feed_items(PGA_SEARCH_FAMILY_AS_SERVED))
        bundle = next(i for i in out if i.get("type") == "bundle")
        for field in (
            bundle["headline"],
            bundle["reason"],
            bundle["data"]["title"],
            bundle["data"]["shared_question"],
        ):
            assert "Bmw" not in field
            assert "Pga" not in field
