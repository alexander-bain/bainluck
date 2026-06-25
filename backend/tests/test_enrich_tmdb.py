"""#882 slice 1: server-side TMDB imagery for quoted-title entertainment markets.

Tests the false-positive-safe gates: only a quoted title qualifies, and only a
movie/TV TMDB result with real art produces an image.
"""

from app.tasks.enrich_tmdb import _extract_quoted_title, _pick_tmdb_image, TMDB_IMG


class TestExtractQuotedTitle:
    def test_extracts_straight_quoted_title(self):
        assert _extract_quoted_title('"Toy Story 5" Rotten Tomatoes score?') == "Toy Story 5"
        assert _extract_quoted_title('Will "The Odyssey" score at least 60?') == "The Odyssey"

    def test_extracts_smart_quoted_title(self):
        assert _extract_quoted_title("“The Death of Robin Hood” RT score?") == "The Death of Robin Hood"

    def test_no_quotes_returns_none(self):
        # Awards / reality / generic markets have no quoted title → skipped.
        assert _extract_quoted_title("Emmy Nominations: Outstanding Television Movie") is None
        assert _extract_quoted_title("Highest grossing movie in 2026?") is None
        assert _extract_quoted_title(None) is None


class TestPickTmdbImage:
    def test_prefers_backdrop_landscape(self):
        results = [
            {"media_type": "movie", "id": 1, "title": "Toy Story 5",
             "backdrop_path": "/bd.jpg", "poster_path": "/ps.jpg"},
        ]
        url, meta = _pick_tmdb_image(results)
        assert url == f"{TMDB_IMG}/w1280/bd.jpg"
        assert meta["tmdb_id"] == 1 and meta["media_type"] == "movie"

    def test_falls_back_to_poster(self):
        results = [{"media_type": "tv", "id": 2, "name": "Show",
                    "backdrop_path": None, "poster_path": "/ps.jpg"}]
        url, meta = _pick_tmdb_image(results)
        assert url == f"{TMDB_IMG}/w780/ps.jpg"
        assert meta["title"] == "Show"

    def test_skips_non_movie_tv_and_artless(self):
        # A 'person' result, and a movie with no art → no image (no wrong poster).
        results = [
            {"media_type": "person", "id": 3, "name": "Someone", "profile_path": "/p.jpg"},
            {"media_type": "movie", "id": 4, "title": "No Art", "backdrop_path": None, "poster_path": None},
        ]
        url, meta = _pick_tmdb_image(results)
        assert url is None and meta is None

    def test_empty_results(self):
        assert _pick_tmdb_image([]) == (None, None)
