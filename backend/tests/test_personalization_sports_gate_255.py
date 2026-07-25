"""Queue #255 Item 2 — sports onboarding must not erase non-sports Discover.

An authenticated user who picked one sport during onboarding gets
``sport_affinities`` set. Before this fix, ``compute_futures_multiplier`` fell
back to an implicit "Nah" (0.0 affinity) for ANY candidate whose sport key /
category didn't match — including politics/economics/tech/etc. futures — and
applied ``NAH_AFFINITY_PENALTY``, hard-suppressing all non-sports Discover.

The fix gates the sport-affinity block on ``_is_sports_candidate``: non-sports
futures skip it entirely and flow through category/feature personalization, while
an explicitly un-picked *sport* still gets the implicit Nah.
"""

import pytest

from app.utils.personalization import (
    PersonalizationContext,
    compute_futures_multiplier,
    _is_sports_candidate,
)


def _ctx_one_sport():
    """Authenticated user who picked only NBA during onboarding."""
    return PersonalizationContext(
        sport_affinities={"basketball_nba": 1.0},
        is_authenticated=True,
    )


# --- _is_sports_candidate ---------------------------------------------------

def test_is_sports_candidate_by_sport_key():
    assert _is_sports_candidate("basketball_nba", None) is True


def test_is_sports_candidate_by_category():
    assert _is_sports_candidate(None, "golf") is True
    assert _is_sports_candidate(None, "hockey") is True


@pytest.mark.parametrize("cat", ["politics", "economics", "tech", "entertainment",
                                  "health", "weather", "culture", "geopolitics"])
def test_non_sports_category_is_not_sports_candidate(cat):
    assert _is_sports_candidate(None, cat) is False


# --- the erase-non-sports regression ---------------------------------------

@pytest.mark.parametrize("cat", ["politics", "economics", "tech", "entertainment",
                                  "health", "weather", "culture"])
def test_non_sports_futures_not_suppressed_by_sports_nah(cat):
    """Non-sports futures keep a neutral multiplier and no sport_nah reason."""
    result = compute_futures_multiplier(
        ctx=_ctx_one_sport(),
        sport_category=cat,
        outcome_team_ids=[],
        sport_key=None,
    )
    assert not any(r.startswith("sport_nah") for r in result.reasons), result.reasons
    assert not any(r.startswith("sport_suppress") for r in result.reasons), result.reasons
    # With no other affinities, the multiplier is untouched (1.0), not crushed.
    assert result.multiplier == pytest.approx(1.0)


def test_unpicked_sport_still_gets_implicit_nah():
    """Explicit sports Nah is preserved: a sport the user didn't pick is
    suppressed (golf, when only NBA was chosen)."""
    result = compute_futures_multiplier(
        ctx=_ctx_one_sport(),
        sport_category="golf",
        outcome_team_ids=[],
        sport_key=None,
    )
    assert any(r.startswith("sport_nah") for r in result.reasons), result.reasons
    assert result.multiplier < 1.0


def test_picked_sport_still_boosted():
    """The chosen sport is still boosted."""
    result = compute_futures_multiplier(
        ctx=_ctx_one_sport(),
        sport_category="basketball",
        outcome_team_ids=[],
        sport_key="basketball_nba",
    )
    assert any(r.startswith("sport_boost") for r in result.reasons), result.reasons
    assert result.multiplier > 1.0
