"""#1958 — the ADMISSION DECISION for `regional_us_election + salient_entity`.

THE SPECIMEN. Across the two-day boring-rate census (2026-08-18/19, 5 distinct
builds, artifacts in `.claude/handoff/artifacts-ux-p103/`), exactly one card was
boring on EVERY day — standing, not rotation:

    Maine State Senate winner?      reasons: regional_us_election, salient_entity

Fable's cycle-101 directive asked for that class to get a NAMED admission
decision rather than continuing to ride the `story:regional_us_elections` cap.

THE DECISION, both halves, asserted below:

1. **The pairing was a false positive, so the class dissolves.** `salient_entity`
   was firing on the OFFICE — Maine / State / Senate — not on any entity. A
   signal that reads the seat as the candidate would re-propose this card for
   admission every cycle, so it is narrowed rather than adjudicated.

2. **Salience alone still does not admit a regional election.** Where a real
   named person is present the card keeps `salient_entity` and its ceiling, and
   stays `low_quality` anyway. National consequence is what admits an election,
   and a proper-noun count cannot stand in for it.

Both directions, per gotcha #43: the office boilerplate stops counting AND every
genuine salient entity outside this path keeps counting. The second half is the
one that would break the feed if it regressed — `has_named_salient_entity` sets
the score ceiling (88 vs 82) for every normal-class card in Discover.
"""

import pytest

from app.utils.feed_market_quality import (
    _has_named_salient_entity,
    classify_market_quality,
)

# Read off the census artifact, not invented.
MAINE = "Maine State Senate winner?"


def _q(name, category="politics"):
    return classify_market_quality(market_name=name, sport_category=category)


# ── Half 1: the false positive is gone, and the class dissolves ─────────


def test_the_maine_specimen_no_longer_claims_a_salient_entity():
    q = _q(MAINE)
    assert q.has_named_salient_entity is False
    assert "salient_entity" not in q.reasons
    # It is now a plain regional election — already-ruled low quality, with no
    # second reason to argue about.
    assert q.reasons == ["regional_us_election"]
    assert q.quality_class == "low_quality"


@pytest.mark.parametrize(
    "name",
    [
        "Maine State Senate winner?",
        "Ohio State Senate winner?",
        "Kansas State House winner?",
    ],
)
def test_the_office_is_not_an_entity(name):
    """The whole class, not just the one card the census happened to catch."""
    q = _q(name)
    assert "regional_us_election" in q.reasons
    assert q.has_named_salient_entity is False
    assert q.quality_class == "low_quality"


def test_office_nouns_only_stop_counting_on_the_regional_election_path():
    """Scoping matters more than the fix. `_has_named_salient_entity` keeps its
    full vocabulary by default; only the regional-election branch narrows it."""
    assert _has_named_salient_entity(MAINE) is True
    assert _has_named_salient_entity(MAINE, ignore_office_nouns=True) is False


# ── Half 2: a genuine entity still counts, and still does not admit ─────


def test_a_named_person_survives_the_narrowing():
    """The candidate is not the office. Mamdani must still register."""
    q = _q("Will Zohran Mamdani win the NYC mayoral election?")
    assert q.has_named_salient_entity is True
    assert "salient_entity" in q.reasons
    assert "regional_us_election" in q.reasons


def test_salience_does_not_admit_a_regional_election():
    """The decision itself. A famous candidate does not promote the race."""
    q = _q("Will Zohran Mamdani win the NYC mayoral election?")
    assert q.quality_class == "low_quality"


@pytest.mark.parametrize(
    "name",
    [
        "Will the Supreme Court overturn Chevron?",
        "Will Taylor Swift announce a tour?",
        "Will the Federal Reserve cut rates in September?",
        "Will Kansas City Chiefs win the Super Bowl?",
    ],
)
def test_every_salient_entity_off_this_path_is_untouched(name):
    assert _q(name, category="politics").has_named_salient_entity is True
    assert _has_named_salient_entity(name) is True


# These are the cards that PROVE the scoping, because they are the ones where
# the narrowed vocabulary gives a DIFFERENT answer. Chosen by measurement: the
# four specimens above all survive narrowing anyway ("Supreme"/"Chevron",
# "Federal"/"Reserve", "Kansas"/"Chiefs" each keep two non-office tokens), so a
# guard built only on them cannot tell a scoped fix from a global one — it
# passed a mutation that applied the narrowing to every card in Discover.
NARROWING_WOULD_FLIP = [
    "Will the State Department issue a travel ban?",
    "Will Attorney General Bondi resign?",
]


@pytest.mark.parametrize("name", NARROWING_WOULD_FLIP)
def test_the_narrowing_is_SCOPED_not_global(name):
    """The blast-radius guard, with teeth.

    Office nouns are legitimately salient when the office IS the subject. These
    two cards lose their salience under the narrowed vocabulary — so if the
    narrowing ever escapes the regional-election branch, their score ceiling
    silently drops from 88 to 82 and this reds.
    """
    assert _has_named_salient_entity(name, ignore_office_nouns=True) is False
    # ...but by default, and therefore in Discover, they are salient.
    assert _has_named_salient_entity(name) is True
    assert _q(name, category="politics").has_named_salient_entity is True
