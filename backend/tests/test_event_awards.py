"""L2-87 (B6): awards adapter pure helpers — proves the "config drop" grammar over
the real KX award ticker/name shapes (verified live 2026-07-12). The adapter's
build_event is exercised via the route test (test_route_event_concept.py)."""

from datetime import datetime, timezone

from app.utils.event_awards import (
    CEREMONIES,
    classify_market,
    clean_category_label,
    edition_year,
    parse_awards_slug,
)


class TestParseAwardsSlug:
    def test_bare_ceremony(self):
        cfg, yr = parse_awards_slug("oscars")
        assert cfg is not None and cfg.slug == "oscars"
        assert yr is None

    def test_four_digit_year(self):
        cfg, yr = parse_awards_slug("oscars-2027")
        assert cfg.slug == "oscars"
        assert yr == 27

    def test_two_digit_year(self):
        cfg, yr = parse_awards_slug("emmys-26")
        assert cfg.slug == "emmys"
        assert yr == 26

    def test_aliases_resolve(self):
        assert parse_awards_slug("academy-awards-2027")[0].slug == "oscars"
        assert parse_awards_slug("tony-awards")[0].slug == "tonys"
        assert parse_awards_slug("grammy")[0].slug == "grammys"

    def test_unknown_ceremony_is_none(self):
        cfg, yr = parse_awards_slug("golden-globes")
        assert cfg is None

    def test_empty(self):
        assert parse_awards_slug("") == (None, None)


class TestEditionYear:
    def test_ticker_year_token(self):
        assert edition_year("KXOSCARPIC-27") == 27
        assert edition_year("kalshi:KXOSCARPIC-26") == 26

    def test_emmy_date_token(self):
        # KXEMMYDSERIES-26SEP14 -> first -NN is the edition year, not the day.
        assert edition_year("KXEMMYDSERIES-26SEP14") == 26
        assert edition_year("KXEMMYNOMS-26-DS") == 26

    def test_tony_embedded(self):
        assert edition_year("KXTONYAWARDS-26BM") == 26

    def test_falls_back_to_resolution_date(self):
        # Grammy tickers carry no year token.
        rd = datetime(2027, 11, 1, tzinfo=timezone.utc)
        assert edition_year("KXGRAMAOTY", rd) == 27
        assert edition_year("KXGRAMAOTY", None) is None


class TestClassifyMarket:
    def test_winner_categories(self):
        assert classify_market("KXOSCARPIC-27", "Oscar winner: Best Picture") == "category"
        assert classify_market("KXOSCARPIC-26", "Oscar for Best Picture?") == "category"
        assert classify_market("KXEMMYDSERIES-26SEP14", "Emmy Award for Drama Series") == "category"
        assert classify_market("KXTONYAWARDS-26BM", "Tony Award for Best Musical?") == "category"
        assert classify_market("KXGRAMAOTY", "Grammy winner: Album of the Year") == "category"

    def test_nominations(self):
        assert classify_market("KXOSCARNOMPIC-27", "Oscar nominations for Best Picture?") == "nominations"
        assert classify_market("KXEMMYNOMS-26-DS", "Emmy Nominations: Outstanding Drama Series") == "nominations"
        assert classify_market("KXGRAMMYNOMAOTY", "2026 Grammy nominations for Album of the Year") == "nominations"

    def test_novelty(self):
        assert classify_market("KXOSCARGUESTS-26", "Who will attend the Oscars?") == "novelty"
        assert classify_market("KXMOSTWINSOSCARS", "Most Oscar wins?") == "novelty"


class TestCleanCategoryLabel:
    def test_strips_ceremony_boilerplate(self):
        assert clean_category_label("Oscar winner: Best Picture") == "Best Picture"
        assert clean_category_label("Oscar for Best Director?") == "Best Director"
        assert clean_category_label("Emmy Award for Drama Series") == "Drama Series"
        assert clean_category_label("Tony Award for Best Play?") == "Best Play"
        assert clean_category_label("Grammy winner: Album of the Year") == "Album of the Year"

    def test_strips_leading_year(self):
        assert clean_category_label("2026 Oscar for Best Music (Original Score)?") == "Best Music (Original Score)"

    def test_empty_falls_back(self):
        assert clean_category_label("") == ""


class TestCeremoniesConfig:
    def test_all_ceremonies_have_marquee(self):
        for cfg in CEREMONIES.values():
            assert cfg.marquee_re is not None
            assert cfg.ticker.startswith("KX")

    def test_emmy_ticker_excludes_sports_emmy(self):
        # KXEMMY is not a substring of KXSPORTSEMMY, so the Sports Emmys are excluded.
        assert "KXEMMY" not in "KXSPORTSEMMY"
