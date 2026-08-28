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


class TestMatchDetail:
    """One match's own page — GET /api/tournaments/{slug}/matches/{key} (UX-P149).

    The surface lane1's Q426 note asked for: match props rendered on the
    match's own page, grouped under the match-winner market. What is pinned
    here is what the pure-logic suite cannot reach — that a matchup key does
    not infer any more than a slug does, and that the sibling load is an
    id-anchored group hop rather than a query anyone could widen.
    """

    MATCH = "mens-singles:henrique-rocha-vs-lloyd-harris:2026-08-26"

    async def test_a_registered_matchup_is_served(self, client):
        resp = await client.get(f"/api/tournaments/us-open/matches/{self.MATCH}")
        assert resp.status_code == 200

    async def test_a_matchup_key_does_not_infer(self, client):
        """Ruling 031's disease, one level down from the slug.

        Answering a mistyped key with a plausible other match is exactly the
        failure that cost the US Open its own page (#1793), and it would be
        worse here — the reader would be looking at two real players' names
        over another match's numbers.
        """
        for key in ("nonsense", "mens-singles:a-vs-b:2026-08-26", self.MATCH[:-2]):
            resp = await client.get(f"/api/tournaments/us-open/matches/{key}")
            assert resp.status_code == 404, key

    async def test_an_unregistered_tournament_is_404(self, client):
        resp = await client.get(f"/api/tournaments/wimbledon/matches/{self.MATCH}")
        assert resp.status_code == 404

    async def test_rejects_post(self, client):
        resp = await client.post(f"/api/tournaments/us-open/matches/{self.MATCH}")
        assert resp.status_code == 405

    async def test_payload_shape(self, client):
        body = (
            await client.get(f"/api/tournaments/us-open/matches/{self.MATCH}")
        ).json()
        for key in (
            "slug", "title", "matchup_key", "match", "result", "decided",
            "props", "props_count", "props_dropped", "generated_at",
        ):
            assert key in body, key
        assert body["matchup_key"] == self.MATCH
        assert body["match"]["matchup_key"] == self.MATCH

    async def test_empty_database_is_an_honest_empty_page(self, client):
        """No prices must never become a fabricated question."""
        body = (
            await client.get(f"/api/tournaments/us-open/matches/{self.MATCH}")
        ).json()
        assert body["props"] == []
        assert body["decided"] is False
        assert all(side["probability"] is None for side in body["match"]["sides"])

    async def test_a_started_match_still_has_a_page(self, client):
        """`build_slate` drops a match six hours after its start; this must not.

        Every match in the committed register was played days before this test
        runs, so if the page inherited the slate's window every one of them
        would 404 — at exactly the moment its result exists.
        """
        resp = await client.get(f"/api/tournaments/us-open/matches/{self.MATCH}")
        assert resp.status_code == 200

    def test_the_sibling_load_is_a_group_hop_not_a_search(self):
        """The grouping is an id. If this stops being true, say so loudly.

        No name comparison, no time window and no category test may enter this
        path — that is the whole reason lane1 could hand the surface over
        without handing over a matching problem with it.
        """
        source = inspect.getsource(tournaments._load_match_group)
        assert "FuturesMarket.group_id == group_id" in source
        assert "MAX_MATCH_GROUP_ROWS" in source
        for banned in ("ilike", "like(", "commence_time", "llm_sport_category"):
            assert banned not in source.lower(), banned


class TestLinkOverlayOnTheMatchPage:
    """The match page reads the SAME overlay the hub does (UX-P149).

    Lane1's Q426 linker fills in the R128 fixtures the ceremony census recorded
    as `missing`. If the match page did not read it, the hub would print a
    probability for those 96 main-draw matches and the match's own page would
    say no market exists — two surfaces disagreeing about one question, on the
    main draw, in the week it starts.

    On THIS branch the linker module does not exist (it is lane1's, on master),
    so what is pinned here is the seam and the degradation: the call is made,
    the absence costs nothing, and the page renders the committed register.
    """

    MATCH = "mens-singles:henrique-rocha-vs-lloyd-harris:2026-08-26"

    def test_the_match_route_applies_the_overlay(self):
        source = inspect.getsource(tournaments.get_tournament_match)
        assert "_with_link_overlay" in source

    def test_the_overlay_is_never_a_gate(self):
        """It must not be able to 503 the page, whatever it does."""
        source = inspect.getsource(tournaments._with_link_overlay)
        assert "except Exception" in source
        assert "return register, 0" in source

    async def test_a_missing_linker_leaves_the_page_exactly_as_the_register_wrote_it(
        self, client
    ):
        resp = await client.get(f"/api/tournaments/us-open/matches/{self.MATCH}")
        assert resp.status_code == 200
        assert resp.json()["matchup_key"] == self.MATCH

    async def test_the_overlay_cannot_mutate_the_cached_register(self):
        """gotcha #6: a module-level cached dict edited in place leaks forward.

        Proven against the real helper rather than the real linker, because the
        register the route holds is the thing at risk and it is the same object
        on the next request.
        """
        from app.utils.tournament_register import load_register

        register = load_register("us-open", "2026")
        before = len(register["matchups"])
        out, applied = await tournaments._with_link_overlay("us-open", register)
        assert applied == 0
        assert out is register or len(out["matchups"]) == before
        assert len(register["matchups"]) == before
