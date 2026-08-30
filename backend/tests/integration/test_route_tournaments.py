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
from app.utils import tournament_event_link


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
        # UX-P152: the hub's body moved to `_hub_payload` so the event page's
        # tournament sections come out of the SAME build. `get_tournament` is
        # now a four-line slug check in front of it, so the assertions about
        # what the build does read the build.
        source = inspect.getsource(tournaments._hub_payload)
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
        # UX-P152: the hub's body moved to `_hub_payload` so the event page's
        # tournament sections come out of the SAME build. `get_tournament` is
        # now a four-line slug check in front of it, so the assertions about
        # what the build does read the build.
        source = inspect.getsource(tournaments._hub_payload)
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


class TestEventTournamentExtensions:
    """A standard event's tournament sections — GET /api/tournaments/by-event/{id}.

    UX-P152 replaced UX-P149's parallel match page with this. Alex, on that
    artifact: *"It seems like we're reinventing the event page here"*, and then
    *"I thought that tournaments were containers for related events."* They are,
    and 94 standard `events` rows for the 96 registered R128 fixtures appeared
    on 2026-08-27 when the Odds API ingested the main draw — the day after
    UX-P149 measured that none existed.

    What is pinned here is what the pure-logic suite cannot reach: that the
    ordinary answer is cheap and is not an error, and that the parallel route
    is gone rather than merely unlinked.
    """

    async def test_the_match_page_route_no_longer_exists(self, client):
        """Not merely unlinked — GONE. Two doors to one thing is the bug.

        A surface left mounted but unreferenced is exactly the shape of
        `GridPlayoffPathPair`, the dead advancement component this queue found
        while answering Alex's question about what the MLB page shows: fully
        plumbed, never rendered, and the reason the code had two plausible
        answers where the product has one.
        """
        resp = await client.get(
            "/api/tournaments/us-open/matches/"
            "mens-singles:alexander-bublik-vs-j-j-wolf:2026-08-30"
        )
        assert resp.status_code == 404

    async def test_a_non_tournament_event_is_a_null_not_a_404(self, client):
        """The ordinary answer for almost every event on the site.

        An error status for the ordinary answer is how a health check learns to
        ignore a real one.
        """
        resp = await client.get("/api/tournaments/by-event/999999999")
        # Either the event does not exist (404) or it does and is not in a
        # tournament (200 + null) — never a 500, and never a 404 for the
        # second case, which is what this pins.
        assert resp.status_code in (200, 404)
        if resp.status_code == 200:
            assert resp.json()["tournament"] is None

    async def test_the_no_costs_one_indexed_read_and_never_a_register(self):
        """A Lakers event page must not pay for the US Open being on.

        The sport-key gate has to come BEFORE `_hub_payload`, or a single event
        page for an unrelated game triggers a full tournament build on a cold
        cache.
        """
        source = inspect.getsource(tournaments.get_event_tournament)
        gate = source.index('return {"event_id": event_id, "tournament": None}')
        assert gate < source.index("_hub_payload"), (
            "the sport-key gate must short-circuit before any register load"
        )

    async def test_membership_is_named_never_inferred_from_the_slug(self):
        """Same posture as `espn_event_name`: three strings a human can check."""
        assert tournaments.REGISTERED_TOURNAMENTS["us-open"]["sport_keys"] == (
            "tennis_atp_us_open",
            "tennis_wta_us_open",
        )

    async def test_it_never_name_matches_the_two_players_sitting_right_there(self):
        """The event row carries both player names. The route must not use them.

        This is the shortcut that would work most of the time and put two real
        players' names over a third match's numbers the rest of it.
        """
        source = inspect.getsource(tournaments.get_event_tournament)
        assert "resolve_matchup_events" not in source, (
            "resolution happens in `_hub_payload` and is READ here"
        )
        assert 'by_event") or {}).get(' in source
        for shortcut in ("home_team_name ==", "in home_team_name", ".lower()"):
            assert shortcut not in source

    async def test_the_hub_publishes_the_link_map_and_its_named_gaps(self, client):
        """NO SILENT CAPS. A fixture with no click-through is a counted gap.

        A row that quietly stopped being a link and a fixture nobody quotes look
        identical from the outside (gotcha #53).
        """
        body = (await client.get("/api/tournaments/us-open")).json()
        links = body["event_links"]
        assert isinstance(links["by_event"], dict)
        assert isinstance(links["linked"], int)
        assert isinstance(links["unresolved"], dict)
        for reason in links["unresolved"]:
            assert reason in tournament_event_link.UNRESOLVED_REASONS

    async def test_slate_rows_carry_the_event_they_route_to(self, client):
        """The routing fix, end to end: a match card addresses `/events/{id}`.

        ⚠️ **The clock is not an input to this property, and it used to be.**
        Until UX-P187 this drove the route and asserted `rows` non-empty. The
        register is a COMMITTED FILE with fixed `scheduled_date` values and
        `build_slate` drops anything older than `now - MATCH_STALE_AFTER_HOURS`
        as `ALREADY_PLAYED` — `tournament_slate.py` says so in as many words:
        "The register is a file and the clock is not." The us-open register's
        latest matchup starts `2026-08-30T04:00:00Z`, so at **10:00:00 UTC on
        2026-08-30** the last row aged out, every one of the 124 matchups
        dropped, and the assertion began failing on unchanged code. It had
        passed an hour earlier.

        So the anchor is now taken FROM the register — its own latest scheduled
        start — and there is no branch on the wall clock (gotcha #44: if your
        anchor contains an `if`, it isn't fixed). The anti-vacuity assertion is
        RE-ASSERTED against that clock rather than deleted; a stand-in that
        stops qualifying gets re-pointed, never dropped.
        """
        from datetime import datetime, timedelta

        from app.utils.tournament_register import load_register
        from app.utils.tournament_slate import build_slate

        body = (await client.get("/api/tournaments/us-open")).json()
        by_matchup = body["event_links"]["by_matchup"]

        def check(rows):
            for row in rows:
                assert "event_id" in row
                assert row["event_id"] is None or isinstance(row["event_id"], int)
                # Whatever the link map resolved must actually reach the rows —
                # a resolution nobody renders is not a ship.
                expected = by_matchup.get(row["matchup_key"])
                if expected is not None:
                    assert row["event_id"] == expected

        # The route's own rows, however many the clock has left it. Vacuous on
        # its own, which is exactly why the register-anchored pass below exists.
        check(body["slate"]["matches"])

        register = load_register(
            "us-open", tournaments.REGISTERED_TOURNAMENTS["us-open"]["season"]
        )
        starts = [
            datetime.fromisoformat(str(m["scheduled_date"]).replace("Z", "+00:00"))
            for m in (register.get("matchups") or [])
            if m.get("scheduled_date")
        ]
        assert starts, "the committed register has no scheduled matchups at all"
        # One second after the last registered start: every matchup is inside
        # its staleness window, so the slate is at its fullest. Derived from the
        # file, so it stays true however long the file sits here.
        anchored = build_slate(
            register,
            prices={},
            now=max(starts) + timedelta(seconds=1),
            event_ids=by_matchup,
        )
        assert anchored["matches"], (
            "no slate rows even at the register's own clock — the drop is not "
            "staleness: %r" % (anchored.get("dropped"),)
        )
        check(anchored["matches"])
