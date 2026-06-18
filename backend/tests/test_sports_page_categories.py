"""/sports page must not leak non-sports content (#958/#959/#960).

esports stays in Discover/Browse (DISCOVER_SPORTS_CATEGORIES) but is scoped out
of the /sports surfaces via SPORTS_PAGE_CATEGORIES. motorsports (F1/NASCAR)
stays a sport.
"""

import inspect

from app.routes import feed, futures
from app.routes.feed import DISCOVER_SPORTS_CATEGORIES, SPORTS_PAGE_CATEGORIES
from app.models import FuturesMarket


class TestSportsPageCategories:
    def test_excludes_esports(self):
        assert "esports" not in SPORTS_PAGE_CATEGORIES

    def test_keeps_motorsports_and_core_sports(self):
        assert "motorsports" in SPORTS_PAGE_CATEGORIES
        for c in ("basketball", "football", "baseball", "hockey", "soccer", "golf"):
            assert c in SPORTS_PAGE_CATEGORIES

    def test_is_discover_set_minus_esports_only(self):
        # The sports-page set is exactly Discover minus esports — nothing else dropped.
        assert set(SPORTS_PAGE_CATEGORIES) == set(DISCOVER_SPORTS_CATEGORIES) - {"esports"}

    def test_discover_browse_unchanged(self):
        # esports MUST stay in Discover/Browse — do not regress this.
        assert "esports" in DISCOVER_SPORTS_CATEGORIES


class TestSportsModeFuturesFilter:
    def test_sports_mode_filter_compiles_to_esports_excluded(self):
        # The actual filter the sports-mode query uses.
        clause = FuturesMarket.llm_sport_category.in_(SPORTS_PAGE_CATEGORIES)
        compiled = clause.compile(compile_kwargs={"literal_binds": True})
        sql = str(compiled)
        assert "esports" not in sql
        assert "motorsports" in sql
        assert "basketball" in sql

    def test_score_sports_mode_futures_uses_sports_page_set(self):
        src = inspect.getsource(feed._score_sports_mode_futures)
        assert "SPORTS_PAGE_CATEGORIES" in src
        # the sports_filter must NOT bind to the broader Discover set
        assert "in_(DISCOVER_SPORTS_CATEGORIES)" not in src


class TestGroupedFeedSportsOnly:
    def test_grouped_feed_has_sports_only_param_and_uses_sports_page_set(self):
        src = inspect.getsource(futures.grouped_feed)
        assert "sports_only" in src
        assert "SPORTS_PAGE_CATEGORIES" in src
        # must filter llm_sport_category, NOT FuturesMarket.category == "sports"
        assert "llm_sport_category.in_(SPORTS_PAGE_CATEGORIES)" in src

    def test_sports_page_import_is_circular_safe(self):
        # the function-level import resolves without a circular-import error
        from app.routes.feed import SPORTS_PAGE_CATEGORIES as _s

        assert "esports" not in _s
