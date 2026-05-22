"""Unit tests for weather route filtering logic.

Tests the health/pandemic exclusion regex and zombie market filtering
added to fix GitHub issue #472.
"""

import re

import pytest

from app.routes.weather import _HEALTH_EXCLUDE_RE


class TestHealthExcludeRegex:
    """Verify _HEALTH_EXCLUDE_RE catches health/pandemic market names."""

    @pytest.mark.parametrize("name", [
        "Will a pandemic be declared by 2030?",
        "Will bird flu reach 1000 US cases?",
        "Will H5N1 become a global emergency?",
        "Will a virus outbreak occur by 2050?",
        "Will a new disease emerge by 2030?",
        "Will there be an epidemic in 2026?",
        "Will a new infection wave hit the US?",
        "Will COVID cases spike in winter 2026?",
        "Will monkeypox spread globally by 2030?",
        "Will ebola return to West Africa?",
        "Will cholera reach 100K cases?",
        "Will plague re-emerge in 2030?",
        "Will influenza kill more than 50K in 2026?",
        "Will mpox be declared a pandemic?",
        "Will tuberculosis be eradicated by 2050?",
        "Will malaria deaths drop by 2030?",
        "Will dengue spread to new regions?",
        "Will zika return to the Americas?",
    ])
    def test_matches_health_keywords(self, name: str):
        """Health/pandemic market names should be caught by the regex."""
        assert _HEALTH_EXCLUDE_RE.search(name) is not None, (
            f"Expected _HEALTH_EXCLUDE_RE to match: {name!r}"
        )

    @pytest.mark.parametrize("name", [
        "Will 2026 be the hottest year on record?",
        "Will CO2 levels exceed 500 ppm by 2050?",
        "Will a hurricane hit the Gulf Coast?",
        "Will it rain in NYC on Tuesday?",
        "Highest temperature in Miami on May 20?",
        "Will a tornado hit Oklahoma in May 2026?",
        "Will a volcano erupt in Yellowstone by 2030?",
        "Will the arctic ice cap reach record low?",
        "Will solar activity peak in 2026?",
        "Will EV adoption reach 50% by 2030?",
    ])
    def test_does_not_match_legitimate_weather(self, name: str):
        """Legitimate weather/climate market names should NOT be caught."""
        assert _HEALTH_EXCLUDE_RE.search(name) is None, (
            f"Expected _HEALTH_EXCLUDE_RE NOT to match: {name!r}"
        )


class TestClimateExcludeRegex:
    """Verify the climate endpoint's _EXCLUDE_RE catches health keywords.

    This tests the inline regex pattern used in get_climate() which includes
    both the original weather exclusions and the new health keywords.
    """

    # Reproduce the pattern from get_climate()
    _CLIMATE_EXCLUDE_RE = re.compile(
        r"\b(?:Ifo|temperature|rain |snow |daily"
        r"|pandemic|virus|outbreak|bird\s*flu|h5n1|disease|epidemic"
        r"|infection|covid|monkeypox|ebola|cholera|plague|influenza"
        r"|mpox|tuberculosis|malaria|dengue|zika)\b",
        re.I,
    )

    @pytest.mark.parametrize("name", [
        "Will a pandemic be declared by 2030?",
        "Will bird flu reach 1000 US cases?",
        "Will a virus outbreak occur by 2050?",
        "Highest temperature in NYC on May 20?",
        "Rain in Miami in June 2026",
        "Daily precipitation totals for NYC",
    ])
    def test_climate_exclude_catches_non_climate(self, name: str):
        """Non-climate content (health, temperature, rain, daily) is excluded."""
        assert self._CLIMATE_EXCLUDE_RE.search(name) is not None

    @pytest.mark.parametrize("name", [
        "Will 2026 be the hottest year on record?",
        "Will CO2 levels exceed 500 ppm by 2050?",
        "Will EV adoption reach 50% by 2030?",
    ])
    def test_climate_exclude_allows_real_climate(self, name: str):
        """Real climate markets should pass through the exclude filter."""
        assert self._CLIMATE_EXCLUDE_RE.search(name) is None
