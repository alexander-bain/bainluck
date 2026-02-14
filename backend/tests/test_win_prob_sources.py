"""Structural validation tests for win probability source configuration.

Prevents deploying a misconfigured source by validating required fields,
color formats, and source type values.
"""

import re
import pytest

from app.config.win_prob_sources import WIN_PROB_SOURCES, get_source_meta, get_active_sources


REQUIRED_FIELDS = [
    "display_name", "source_type", "sports", "color", "description",
    "methodology", "attribution_url", "attribution_name",
]

VALID_SOURCE_TYPES = {"market", "model"}

HEX_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class TestWinProbSourcesStructure:
    """Validate the WIN_PROB_SOURCES configuration dict."""

    def test_has_at_least_one_source(self):
        assert len(WIN_PROB_SOURCES) >= 1

    @pytest.mark.parametrize("source_key", list(WIN_PROB_SOURCES.keys()))
    def test_required_fields_present(self, source_key):
        source = WIN_PROB_SOURCES[source_key]
        for field in REQUIRED_FIELDS:
            assert field in source, f"Source '{source_key}' missing field '{field}'"

    @pytest.mark.parametrize("source_key", list(WIN_PROB_SOURCES.keys()))
    def test_valid_source_type(self, source_key):
        source_type = WIN_PROB_SOURCES[source_key]["source_type"]
        assert source_type in VALID_SOURCE_TYPES, (
            f"Source '{source_key}' has invalid source_type '{source_type}'"
        )

    @pytest.mark.parametrize("source_key", list(WIN_PROB_SOURCES.keys()))
    def test_color_is_valid_hex(self, source_key):
        color = WIN_PROB_SOURCES[source_key]["color"]
        assert HEX_COLOR_PATTERN.match(color), (
            f"Source '{source_key}' color '{color}' is not a valid #RRGGBB hex"
        )

    @pytest.mark.parametrize("source_key", list(WIN_PROB_SOURCES.keys()))
    def test_sports_is_list(self, source_key):
        sports = WIN_PROB_SOURCES[source_key]["sports"]
        assert isinstance(sports, list), f"Source '{source_key}' sports should be a list"
        assert len(sports) >= 1, f"Source '{source_key}' sports list is empty"

    @pytest.mark.parametrize("source_key", list(WIN_PROB_SOURCES.keys()))
    def test_display_name_is_nonempty(self, source_key):
        name = WIN_PROB_SOURCES[source_key]["display_name"]
        assert isinstance(name, str) and name.strip(), (
            f"Source '{source_key}' display_name is empty"
        )

    def test_expected_sources_exist(self):
        """Verify the three known sources are configured."""
        assert "betting" in WIN_PROB_SOURCES
        assert "espn" in WIN_PROB_SOURCES
        assert "stat_model" in WIN_PROB_SOURCES

    def test_betting_is_market_type(self):
        assert WIN_PROB_SOURCES["betting"]["source_type"] == "market"

    def test_espn_is_model_type(self):
        assert WIN_PROB_SOURCES["espn"]["source_type"] == "model"

    def test_stat_model_is_model_type(self):
        assert WIN_PROB_SOURCES["stat_model"]["source_type"] == "model"

    def test_dash_pattern_is_string_or_none(self):
        """dash_pattern should be None (solid line) or a string like '6 3'."""
        for key, source in WIN_PROB_SOURCES.items():
            dp = source.get("dash_pattern")
            assert dp is None or isinstance(dp, str), (
                f"Source '{key}' dash_pattern should be None or string"
            )


class TestHelperFunctions:
    """Tests for get_source_meta and get_active_sources."""

    def test_get_source_meta_known(self):
        meta = get_source_meta("betting")
        assert meta is not None
        assert meta["display_name"] == "Betting Odds"

    def test_get_source_meta_unknown(self):
        assert get_source_meta("nonexistent_source") is None

    def test_get_active_sources_returns_all(self):
        sources = get_active_sources()
        assert sources is WIN_PROB_SOURCES
