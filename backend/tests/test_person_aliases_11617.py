"""Person identity admission only; route/served acceptance is a separate gate."""

from dataclasses import replace

import pytest

from app.config.person_aliases import (
    REVIEWED_PERSON_ALIASES,
    resolve_reviewed_person_alias,
)
from app.utils.search_match_class import Evidence, match_class


@pytest.mark.parametrize("query", ["SGA", "sga", "Sga", "  SGA  "])
def test_supported_alias_keeps_existing_athlete_identity(query):
    person = resolve_reviewed_person_alias(query)
    assert person is not None
    assert (person.canonical_name, person.provider, person.provider_id) == (
        "Shai Gilgeous-Alexander",
        "espn",
        "4278073",
    )
    assert person.sport_key == "basketball_nba"


@pytest.mark.parametrize(
    "query",
    [
        "",
        "SG",
        "SGAR",
        "Damsgaard",
        "Chhattisgarh",
        "S.G.A.",
        "SGA MVP",
        "Will SGA win MVP",
        "NBA SGA",
        "Shai Gilgeous-Alexander",
        "Katie Zacharia",
        "Zacharia",
        "Zachariah Branch",
        "Lee",
        "ai",
        "ipo",
        "weather",
    ],
)
def test_alias_does_not_infer_a_person_or_compound_intent(query):
    assert resolve_reviewed_person_alias(query) is None


@pytest.mark.parametrize("kind", ["team", "competition", "event_concept", "market"])
def test_explicit_nonperson_context_never_uses_the_person_alias(kind):
    assert resolve_reviewed_person_alias("SGA", kind=kind) is None


def test_explicit_domain_must_match():
    assert resolve_reviewed_person_alias("SGA", sport_key="football_nfl") is None
    assert resolve_reviewed_person_alias(
        "SGA", kind="person", sport_key="basketball_nba"
    )


def test_two_people_contesting_an_alias_are_not_arbitrated():
    shai = REVIEWED_PERSON_ALIASES[0]
    other = replace(shai, canonical_name="Synthetic Other Person", provider_id="other")
    for records in [(shai, other), (other, shai)]:
        assert resolve_reviewed_person_alias("SGA", aliases=records) is None


def test_cross_domain_collision_requires_explicit_domain():
    shai = REVIEWED_PERSON_ALIASES[0]
    other = replace(shai, sport_key="football_nfl", provider_id="other")
    assert resolve_reviewed_person_alias("SGA", aliases=(shai, other)) is None
    assert (
        resolve_reviewed_person_alias(
            "SGA", sport_key="basketball_nba", aliases=(shai, other)
        )
        == shai
    )


def test_repeated_evidence_for_one_identity_is_not_a_second_person():
    shai = REVIEWED_PERSON_ALIASES[0]
    assert resolve_reviewed_person_alias("SGA", aliases=(shai, shai)) == shai


def test_conflicting_name_for_the_same_provider_id_is_refused():
    shai = REVIEWED_PERSON_ALIASES[0]
    assert (
        resolve_reviewed_person_alias(
            "SGA", aliases=(shai, replace(shai, canonical_name="Conflicting Name"))
        )
        is None
    )


@pytest.mark.parametrize(
    "field",
    [
        "canonical_name",
        "sport_key",
        "provider",
        "provider_id",
        "evidence_url",
    ],
)
def test_incomplete_competing_record_is_not_silently_discarded(field):
    shai = REVIEWED_PERSON_ALIASES[0]
    incomplete = replace(shai, **{field: ""})
    assert resolve_reviewed_person_alias("SGA", aliases=(shai, incomplete)) is None
    assert (
        resolve_reviewed_person_alias(
            "SGA", sport_key="basketball_nba", aliases=(shai, incomplete)
        )
        is None
    )


def test_existing_match_class_keeps_exact_katie_before_branch_prefix():
    katie = Evidence(name="Will Katie Zacharia give another press briefing?")
    branch = Evidence(name="Zachariah Branch: Receptions O/U 2.5")
    assert match_class("Zacharia", katie) < match_class("Zacharia", branch)
    assert match_class("Zachariah Branch", branch) < match_class(
        "Zachariah Branch", katie
    )
