"""Contract tests for the tournament hub: GET /api/tournaments/{slug} (UX-P131).

Two things are pinned here that the pure-logic suite cannot reach:

1. **The slug does not infer.** An unregistered slug is a 404, never a
   nearest-tournament fallback. This is the floor from #1793, where the US Open
   lost its own page to Cincinnati because a shorter slug matched MORE
   tournaments. The absence of a fallback is the fix; a test is what keeps it
   absent.

2. **Freshness is read from snapshots, never from `futures_outcomes`.** The
   Day-1 census measured `futures_outcomes.last_updated` a month stale on the
   Polymarket men's field while its snapshots ran current, so a route that
   trusted it would publish confidence it does not have. Asserted against the
   route's own SQL rather than against a comment.
"""

import inspect

from app.routes import tournaments


class TestSlugResolution:
    async def test_unregistered_slug_is_404(self, client):
        resp = await client.get("/api/tournaments/wimbledon")
        assert resp.status_code == 404

    async def test_nonsense_slug_is_404_not_a_nearest_match(self, client):
        """#1793's disease: a shorter slug must not match MORE tournaments."""
        for slug in ("open", "us", "us-open-2026", "quidditch"):
            resp = await client.get(f"/api/tournaments/{slug}")
            assert resp.status_code == 404, slug

    async def test_registered_slug_is_served(self, client):
        resp = await client.get("/api/tournaments/us-open")
        assert resp.status_code == 200

    async def test_rejects_post(self, client):
        assert (await client.post("/api/tournaments/us-open")).status_code == 405


class TestPayloadShape:
    async def test_top_level_keys(self, client):
        body = (await client.get("/api/tournaments/us-open")).json()
        for key in (
            "slug",
            "title",
            "subtitle",
            "tournament",
            "season",
            "register_version",
            "draw_released",
            "boards",
            "render_findings",
            "generated_at",
        ):
            assert key in body, key

    async def test_serves_the_committed_register_not_a_query(self, client):
        """80 registered players over two draws, with an empty mock database.

        The rows are empty because nothing is priced in the mock — but the
        BOARDS exist, with their labels and their contender counts, because the
        register is the page's source of truth and it is on disk.
        """
        body = (await client.get("/api/tournaments/us-open")).json()
        assert body["tournament"] == "us-open"
        assert body["season"] == "2026"
        assert [b["draw"] for b in body["boards"]] == [
            "mens-singles",
            "womens-singles",
        ]

    async def test_empty_database_is_an_honest_empty_board(self, client):
        """No prices must never become a fabricated board."""
        body = (await client.get("/api/tournaments/us-open")).json()
        for board in body["boards"]:
            assert board["rows"] == []
            assert board["price_state"] == "dark"
            assert board["newest_observed_at"] is None
            assert board["unpriced"] > 0

    async def test_no_render_contract_findings_on_the_committed_register(self, client):
        body = (await client.get("/api/tournaments/us-open")).json()
        assert body["render_findings"] == []


class TestFreshnessSource:
    """`futures_outcomes.last_updated` is not a freshness signal — census-proven."""

    def test_route_never_reads_last_updated(self):
        """Bans the ACCESS, not the mention.

        The module's docstring names `futures_outcomes.last_updated` in order
        to refuse it, and a substring ban would red on the refusal itself —
        then get "fixed" by deleting the explanation. So the guard looks for
        the attribute access, which is the only form that could be the bug.
        """
        source = inspect.getsource(tournaments)
        assert "FuturesOutcome.last_updated" not in source
        assert ".last_updated" not in source.replace("_outcomes.last_updated", "")

    def test_route_reads_captured_at_from_snapshots(self):
        source = inspect.getsource(tournaments._load_prices)
        assert "FuturesOddsSnapshot.captured_at" in source
        assert "max" in source


class TestRegisteredTournaments:
    def test_every_entry_declares_a_season(self):
        for slug, spec in tournaments.REGISTERED_TOURNAMENTS.items():
            assert spec.get("season"), slug
            assert spec.get("title"), slug

    def test_us_open_is_registered_for_2026(self):
        assert tournaments.REGISTERED_TOURNAMENTS["us-open"]["season"] == "2026"


class TestCacheDiscipline:
    def test_ttl_is_short_enough_not_to_become_a_stale_mirror(self):
        """#1767: a 24h mirror with no warmer served yesterday's slate 99.6% of
        the time. A page whose whole subject is freshness must not inherit it."""
        assert 0 < tournaments.CACHE_TTL_SECONDS <= 300

    def test_series_scan_is_bounded(self):
        assert tournaments.MAX_SERIES_ROWS <= 50000
