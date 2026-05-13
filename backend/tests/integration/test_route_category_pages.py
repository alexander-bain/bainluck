"""Contract tests for category page APIs: Weather, Politics, Entertainment, Economics.

Tests that each endpoint returns the expected response shape with the correct
top-level keys, nested structure, and field types — even when the DB is empty.
Uses the shared ``client`` fixture from conftest.py (mock empty DB session).
"""

import pytest


# ============================================================================
# Weather — /api/weather/featured, /api/weather/cities, /api/weather/rain,
#            /api/weather/events, /api/weather/climate, /api/weather/wildcards
# ============================================================================


class TestWeatherFeatured:
    """GET /api/weather/featured — hero rotation cards."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/featured")
        assert resp.status_code == 200

    async def test_response_is_list(self, client):
        resp = await client.get("/api/weather/featured")
        body = resp.json()
        assert isinstance(body, list)

    async def test_item_shape_if_present(self, client):
        """If items exist, each should have q, prob, src, tag, closes."""
        resp = await client.get("/api/weather/featured")
        body = resp.json()
        for item in body:
            assert "q" in item, "Missing 'q' (question text)"
            assert "prob" in item, "Missing 'prob'"
            assert "src" in item, "Missing 'src' (source)"
            assert "tag" in item, "Missing 'tag'"
            assert "closes" in item, "Missing 'closes'"
            assert isinstance(item["q"], str)
            assert isinstance(item["prob"], (int, float))
            assert isinstance(item["src"], str)


class TestWeatherCities:
    """GET /api/weather/cities — temperature distributions by city."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/cities")
        assert resp.status_code == 200

    async def test_response_is_list(self, client):
        resp = await client.get("/api/weather/cities")
        body = resp.json()
        assert isinstance(body, list)

    async def test_city_item_shape_if_present(self, client):
        """Each city should have id, name, region, high with unit/mode/dist."""
        resp = await client.get("/api/weather/cities")
        body = resp.json()
        for city in body:
            assert "id" in city
            assert "name" in city
            assert "region" in city
            assert isinstance(city["name"], str)
            assert "high" in city
            high = city["high"]
            assert "unit" in high
            assert high["unit"] in ("F", "C")
            assert "dist" in high
            assert isinstance(high["dist"], list)


class TestWeatherRain:
    """GET /api/weather/rain — daily NYC + monthly city rain data."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/rain")
        assert resp.status_code == 200

    async def test_has_daily_and_monthly(self, client):
        resp = await client.get("/api/weather/rain")
        body = resp.json()
        assert "daily" in body
        assert "monthly" in body
        assert isinstance(body["daily"], list)
        assert isinstance(body["monthly"], list)

    async def test_daily_item_shape(self, client):
        resp = await client.get("/api/weather/rain")
        body = resp.json()
        for item in body["daily"]:
            assert "day" in item
            assert "date" in item
            assert "prob" in item
            assert isinstance(item["prob"], (int, float))


class TestWeatherEvents:
    """GET /api/weather/events — natural disaster markets."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/events")
        assert resp.status_code == 200

    async def test_has_event_groups(self, client):
        resp = await client.get("/api/weather/events")
        body = resp.json()
        assert "hurricane" in body
        assert "earthquake" in body
        assert "tornadoes" in body
        assert isinstance(body["hurricane"], list)
        assert isinstance(body["earthquake"], list)
        assert isinstance(body["tornadoes"], list)


class TestWeatherClimate:
    """GET /api/weather/climate — long-range climate markets."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/climate")
        assert resp.status_code == 200

    async def test_response_is_list(self, client):
        resp = await client.get("/api/weather/climate")
        body = resp.json()
        assert isinstance(body, list)


class TestWeatherWildcards:
    """GET /api/weather/wildcards — rare weather markets."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/weather/wildcards")
        assert resp.status_code == 200

    async def test_response_is_list(self, client):
        resp = await client.get("/api/weather/wildcards")
        body = resp.json()
        assert isinstance(body, list)


# ============================================================================
# Politics — /api/politics
# ============================================================================


class TestPoliticsEndpoint:
    """GET /api/politics — full politics market data."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/politics")
        assert resp.status_code == 200

    async def test_has_top_level_fields(self, client):
        resp = await client.get("/api/politics")
        body = resp.json()
        assert "total_markets" in body
        assert "updated_at" in body
        assert "themes" in body
        assert "cross_source" in body
        assert "by_source" in body

    async def test_total_markets_is_int(self, client):
        resp = await client.get("/api/politics")
        body = resp.json()
        assert isinstance(body["total_markets"], int)
        assert body["total_markets"] >= 0

    async def test_updated_at_is_iso_string(self, client):
        resp = await client.get("/api/politics")
        body = resp.json()
        assert isinstance(body["updated_at"], str)
        assert "T" in body["updated_at"]

    async def test_themes_has_expected_keys(self, client):
        resp = await client.get("/api/politics")
        body = resp.json()
        themes = body["themes"]
        expected_keys = {
            "presidential", "congressional", "gubernatorial",
            "policy", "scotus", "international", "other",
        }
        assert expected_keys.issubset(set(themes.keys())), (
            f"Missing theme keys: {expected_keys - set(themes.keys())}"
        )

    async def test_presidential_structure(self, client):
        resp = await client.get("/api/politics")
        body = resp.json()
        pres = body["themes"]["presidential"]
        assert "candidates" in pres
        assert isinstance(pres["candidates"], list)
        assert "count" in pres
        assert "has_dual_source" in pres
        assert "side_markets" in pres

    async def test_congressional_structure(self, client):
        resp = await client.get("/api/politics")
        body = resp.json()
        cong = body["themes"]["congressional"]
        assert "count" in cong
        assert "markets" in cong
        assert isinstance(cong["markets"], list)
        assert "chamber_control" in cong
        chamber = cong["chamber_control"]
        assert "senate" in chamber
        assert "house" in chamber

    async def test_themed_section_structure(self, client):
        """Each non-presidential theme should have count + markets list."""
        resp = await client.get("/api/politics")
        body = resp.json()
        themes = body["themes"]
        for key in ("gubernatorial", "policy", "scotus", "international", "other"):
            section = themes[key]
            assert "count" in section, f"{key} missing 'count'"
            assert "markets" in section, f"{key} missing 'markets'"
            assert isinstance(section["markets"], list)
            assert isinstance(section["count"], int)

    async def test_by_source_structure(self, client):
        resp = await client.get("/api/politics")
        body = resp.json()
        by_source = body["by_source"]
        assert "kalshi" in by_source
        assert "polymarket" in by_source
        assert isinstance(by_source["kalshi"], int)
        assert isinstance(by_source["polymarket"], int)

    async def test_cross_source_is_list(self, client):
        resp = await client.get("/api/politics")
        body = resp.json()
        assert isinstance(body["cross_source"], list)


# ============================================================================
# Entertainment — /api/entertainment
# ============================================================================


class TestEntertainmentEndpoint:
    """GET /api/entertainment — full entertainment market data."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/entertainment")
        assert resp.status_code == 200

    async def test_has_top_level_fields(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        assert "total_markets" in body
        assert "updated_at" in body
        assert "trending" in body
        assert "themes" in body
        assert "cultural_moments" in body
        assert "by_source" in body

    async def test_total_markets_is_int(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        assert isinstance(body["total_markets"], int)
        assert body["total_markets"] >= 0

    async def test_updated_at_is_iso_string(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        assert isinstance(body["updated_at"], str)
        assert "T" in body["updated_at"]

    async def test_trending_is_list(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        assert isinstance(body["trending"], list)

    async def test_themes_has_expected_keys(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        themes = body["themes"]
        expected_keys = {"music", "movies_tv", "tech_culture"}
        assert expected_keys.issubset(set(themes.keys())), (
            f"Missing theme keys: {expected_keys - set(themes.keys())}"
        )

    async def test_music_structure(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        music = body["themes"]["music"]
        assert "count" in music
        assert isinstance(music["count"], int)
        assert "spotify_race" in music
        assert isinstance(music["spotify_race"], list)
        assert "billboard_watch" in music
        assert isinstance(music["billboard_watch"], list)

    async def test_movies_tv_structure(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        mtv = body["themes"]["movies_tv"]
        assert "count" in mtv
        assert isinstance(mtv["count"], int)
        assert "rt_groups" in mtv
        assert "box_office" in mtv
        assert "reality_tv" in mtv
        assert isinstance(mtv["rt_groups"], list)
        assert isinstance(mtv["box_office"], list)
        assert isinstance(mtv["reality_tv"], list)

    async def test_tech_culture_structure(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        tc = body["themes"]["tech_culture"]
        assert "count" in tc
        assert isinstance(tc["count"], int)
        assert "markets" in tc
        assert isinstance(tc["markets"], list)

    async def test_cultural_moments_is_list(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        assert isinstance(body["cultural_moments"], list)

    async def test_by_source_structure(self, client):
        resp = await client.get("/api/entertainment")
        body = resp.json()
        by_source = body["by_source"]
        assert "kalshi" in by_source
        assert "polymarket" in by_source
        assert isinstance(by_source["kalshi"], int)
        assert isinstance(by_source["polymarket"], int)


# ============================================================================
# Economics — /api/economics
# ============================================================================


class TestEconomicsEndpoint:
    """GET /api/economics — full economics market data."""

    async def test_returns_200(self, client):
        resp = await client.get("/api/economics")
        assert resp.status_code == 200

    async def test_has_top_level_fields(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        assert "total_markets" in body
        assert "updated_at" in body
        assert "themes" in body
        assert "by_source" in body

    async def test_total_markets_is_int(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        assert isinstance(body["total_markets"], int)
        assert body["total_markets"] >= 0

    async def test_updated_at_is_iso_string(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        assert isinstance(body["updated_at"], str)
        assert "T" in body["updated_at"]

    async def test_themes_has_expected_keys(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        themes = body["themes"]
        expected_keys = {
            "fed", "inflation", "jobs", "recession",
            "markets", "energy", "housing", "trade", "government",
        }
        assert expected_keys.issubset(set(themes.keys())), (
            f"Missing theme keys: {expected_keys - set(themes.keys())}"
        )

    async def test_fed_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        fed = body["themes"]["fed"]
        assert "count" in fed
        assert isinstance(fed["count"], int)
        assert "fomc_meetings" in fed
        assert isinstance(fed["fomc_meetings"], list)
        assert "rate_cuts" in fed
        assert "side_markets" in fed
        assert isinstance(fed["side_markets"], list)

    async def test_inflation_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        inflation = body["themes"]["inflation"]
        assert "count" in inflation
        assert isinstance(inflation["count"], int)
        assert "cpi_releases" in inflation
        assert isinstance(inflation["cpi_releases"], list)
        assert "side_markets" in inflation
        assert isinstance(inflation["side_markets"], list)

    async def test_jobs_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        jobs = body["themes"]["jobs"]
        assert "count" in jobs
        assert isinstance(jobs["count"], int)
        assert "markets" in jobs
        assert isinstance(jobs["markets"], list)

    async def test_recession_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        recession = body["themes"]["recession"]
        assert "count" in recession
        assert isinstance(recession["count"], int)
        assert "gdp_quarters" in recession
        assert isinstance(recession["gdp_quarters"], list)
        assert "side_markets" in recession
        assert isinstance(recession["side_markets"], list)

    async def test_markets_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        markets = body["themes"]["markets"]
        assert "count" in markets
        assert isinstance(markets["count"], int)
        assert "today" in markets
        assert isinstance(markets["today"], list)
        assert "stocks" in markets
        assert isinstance(markets["stocks"], list)
        assert "side_markets" in markets
        assert isinstance(markets["side_markets"], list)

    async def test_energy_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        energy = body["themes"]["energy"]
        assert "count" in energy
        assert isinstance(energy["count"], int)
        assert "gas" in energy
        assert isinstance(energy["gas"], list)
        assert "oil" in energy
        assert isinstance(energy["oil"], list)

    async def test_housing_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        housing = body["themes"]["housing"]
        assert "count" in housing
        assert isinstance(housing["count"], int)
        assert "mortgage_brackets" in housing
        assert "markets" in housing
        assert isinstance(housing["markets"], list)

    async def test_trade_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        trade = body["themes"]["trade"]
        assert "count" in trade
        assert isinstance(trade["count"], int)
        assert "markets" in trade
        assert isinstance(trade["markets"], list)

    async def test_government_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        gov = body["themes"]["government"]
        assert "count" in gov
        assert isinstance(gov["count"], int)
        assert "markets" in gov
        assert isinstance(gov["markets"], list)

    async def test_by_source_structure(self, client):
        resp = await client.get("/api/economics")
        body = resp.json()
        by_source = body["by_source"]
        assert "kalshi" in by_source
        assert "polymarket" in by_source
        assert isinstance(by_source["kalshi"], int)
        assert isinstance(by_source["polymarket"], int)

    async def test_all_theme_counts_non_negative(self, client):
        """Every theme count should be >= 0."""
        resp = await client.get("/api/economics")
        body = resp.json()
        for theme_key, section in body["themes"].items():
            assert section["count"] >= 0, f"{theme_key} has negative count"
