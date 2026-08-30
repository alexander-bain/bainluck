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
        """Follows the CALL, because the statement moved (LAT-P147, #2328).

        This used to read `FuturesOddsSnapshot.captured_at` and `max` straight
        out of `_load_prices`, which pinned the freshness source and the
        AGGREGATE SPELLING together. The spelling was the defect — `max() ...
        GROUP BY` read 342,059 rows to return 514 — so a guard that could only
        stay green while it survived was pinning the wrong half.

        Rewritten to follow the delegation instead: `_load_prices` must get its
        freshness from the shared top-1 loader, and that loader must read
        `captured_at` off the snapshot table. Same property, one indirection,
        and it no longer red-lights the fix for the bug it was guarding.
        """
        source = inspect.getsource(tournaments._load_prices)
        assert "load_latest_observed_at" in source

        from app.utils import latest_observation

        loader = inspect.getsource(latest_observation.latest_observed_at_subquery)
        assert "FuturesOddsSnapshot.captured_at" in loader


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


class TestSlateContract:
    """The daily slate — the half of this page that has live prices (UX-P132)."""

    async def test_slate_is_in_the_payload(self, client):
        body = (await client.get("/api/tournaments/us-open")).json()
        assert "slate" in body
        for key in (
            "matches", "count", "incoherent", "dropped",
            "price_state", "newest_observed_at", "age_hours",
        ):
            assert key in body["slate"], key

    async def test_empty_database_is_an_honest_empty_slate(self, client):
        """No prices must never become a fabricated match card."""
        slate = (await client.get("/api/tournaments/us-open")).json()["slate"]
        assert slate["price_state"] == "dark"
        assert slate["newest_observed_at"] is None
        for row in slate["matches"]:
            assert row["probability_is_live"] is False
            assert all(side["probability"] is None for side in row["sides"])

    async def test_slate_never_emits_a_yes_no_side(self, client):
        """The measured failure: 'Yes 54% / No 47%' instead of two players."""
        slate = (await client.get("/api/tournaments/us-open")).json()["slate"]
        for row in slate["matches"]:
            for side in row["sides"]:
                assert side["display_name"] not in {"Yes", "No", ""}

    async def test_participants_never_reach_a_championship_board(self, client):
        """The contamination guard, at the route boundary.

        The register carries ~130 qualifying participants whose only price is
        P(wins this match). If one reached a board it would be ranked against
        P(wins the tournament) — a first-round qualifier above Alcaraz, with a
        number that is not wrong so much as an answer to a different question.
        """
        body = (await client.get("/api/tournaments/us-open")).json()
        board_keys = {
            row["entity_key"] for board in body["boards"] for row in board["rows"]
        }
        board_capacity = sum(
            len(b["rows"]) + b["unpriced"] for b in body["boards"]
        )
        assert board_capacity == 80, board_capacity

        slate_only = {
            side["entity_key"]
            for row in body["slate"]["matches"]
            for side in row["sides"]
            if side["role"] == "participant"
        }
        assert board_keys.isdisjoint(slate_only)

    def test_slate_and_board_loads_are_both_bounded_id_lists(self):
        """Neither half may become a table scan as the register grows."""
        source = inspect.getsource(tournaments.get_tournament)
        assert "matchup_outcome_ids" in source
        assert "board_outcome_ids" in source
        # Trend series stay a board concern; loading them for the slate's ~130
        # outcomes would triple the per-request scan to draw nothing.
        assert "_load_series(db, board_outcome_ids" in source


class TestAutoLinkedMatchups:
    """The overlay that fills fixtures the draw census found no market for (Q426).

    The census ran once at the ceremony and wrote `status: "missing"` against
    all 96 R128 fixtures. It was right at that instant and wrong by the next
    morning, and nothing re-asked — so the cards rendered blank while Kalshi
    quoted every match. These pin the two properties that make filling them
    safe.
    """

    async def test_payload_reports_how_many_fixtures_were_auto_linked(self, client):
        """A dark card and a dead linker must not look identical (gotcha #53)."""
        body = (await client.get("/api/tournaments/us-open")).json()
        assert "auto_linked_matchups" in body
        assert isinstance(body["auto_linked_matchups"], int)

    async def test_an_unreachable_overlay_leaves_the_committed_register_intact(
        self, client, monkeypatch
    ):
        """No Redis, no links — and the page is exactly what the file says.

        The overlay is an optimisation over the committed truth, never a gate.
        If this ever 500s, a task outage takes the tournament page down with it.
        """
        async def _boom(slug):
            raise RuntimeError("redis is down")

        monkeypatch.setattr(tournaments, "read_links", _boom)
        resp = await client.get("/api/tournaments/us-open")
        assert resp.status_code == 200
        body = resp.json()
        assert body["auto_linked_matchups"] == 0
        # The page is whole: the register's own rows are all still there.
        assert body["register_version"]
        assert body["slate"]["count"] >= 0
        assert body["boards"]

    async def test_route_applies_links_before_building_the_register_view(self):
        """Order matters: `TournamentRegister` snapshots what it is handed.

        Applying the overlay after construction would leave every downstream
        reader — the bounded outcome-id lists especially — looking at the
        unlinked register while the payload claimed otherwise.
        """
        source = inspect.getsource(tournaments.get_tournament)
        assert source.index("apply_resolved_links") < source.index(
            "TournamentRegister(register)"
        )

    def test_the_overlay_can_only_fill_a_blank(self):
        """The asymmetry that keeps a task from re-pointing a curated row."""
        from app.utils.tournament_link_resolver import apply_resolved_links

        pinned = {
            "matchup_key": "k", "players": ["a", "b"],
            "sources": [{
                "source": "kalshi", "status": "live",
                "market_id": 1, "outcome_id": 2,
                "evidence": {"kind": "match-market-census",
                             "observed_at": "2026-08-27T00:15:00+00:00"},
                "sides": {},
            }],
        }
        register = {"matchups": [pinned]}
        out, applied = apply_resolved_links(
            register, {"k|kalshi": {"source": "kalshi", "market_id": 999}}
        )
        assert applied == 0
        assert out["matchups"][0]["sources"][0]["market_id"] == 1
