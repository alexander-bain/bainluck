"""Contract tests for the Competition Hub API: GET /api/hub/{competition}.

The hub is a thin, config-driven composition layer (B1 / #1028): an "upcoming"
rail from a per-domain event-concept lister + futures/awards/props sections from
the league-futures endpoint. These tests pin the response shape, the 404 for
unknown competitions, the upcoming-rail wiring, and the props reclassification
(combat-sport game_props that league_futures buries in "matches").
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

# UX-P209: `import pytest` was here and unused — zero `pytest.` references in the
# file. It predates this branch (proved by re-running ruff on the parent's own
# bytes), and it was invisible because changed-file Ruff only sees a file
# somebody touches. This diff touches it, so it is fixed here rather than
# carried as a red gate. Parked as UX-P209-3: nothing sweeps for the class.


# ---------------------------------------------------------------------------
# Helpers (mirror test_route_league_futures for section-shaped mock markets)
# ---------------------------------------------------------------------------


def _mock_outcome(*, outcome_id=1, name="Yes", probability=0.55, rank=1):
    return SimpleNamespace(
        id=outcome_id,
        name=name,
        current_probability=probability,
        opening_probability=None,
        probability_change_24h=0,
        rank=rank,
        team_id=None,
    )


def _mock_market(
    *, market_id=1, name="Jones vs Aspinall", external_id="KXUFCFIGHT-26JUL11JONASP",
    category="game_prop", market_tier=5, status="open", outcomes=None,
    canonical_market_key=None,
    group_id=None,
):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=market_id,
        name=name,
        source="kalshi",
        external_id=external_id,
        category=category,
        llm_sport_category="mma",
        llm_league="mma",
        market_tier=market_tier,
        status=status,
        event_id=None,
        outcomes=outcomes or [
            _mock_outcome(outcome_id=market_id * 10, name="Jones", probability=0.6),
            _mock_outcome(outcome_id=market_id * 10 + 1, name="Aspinall", probability=0.4, rank=2),
        ],
        resolution_date=now + timedelta(days=30),
        canonical_market_key=canonical_market_key,
        # UX-P061 (#1742): the real FuturesMarket has carried `group_id` all along;
        # this stand-in did not, so the route's new read of it AttributeError'd.
        # A fake that is missing a field the model has is a fake that certifies a
        # shape production never serves.
        group_id=group_id,
    )


def _scalars_result(items):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.unique.return_value = scalars
    result.scalars.return_value = scalars
    # list_ufc_card_concepts uses (await db.execute(...)).all()
    result.all.return_value = []
    return result


# ============================================================================
# Empty DB / basic contract
# ============================================================================


class TestHubContract:
    async def test_mma_returns_200(self, client):
        resp = await client.get("/api/hub/mma")
        assert resp.status_code == 200

    async def test_top_level_keys(self, client):
        body = (await client.get("/api/hub/mma")).json()
        for key in (
            "competition", "label", "title", "emoji", "blurb",
            "sport_key", "upcoming", "sections", "total_markets",
        ):
            assert key in body, f"missing {key}"

    async def test_config_values_echoed(self, client):
        body = (await client.get("/api/hub/mma")).json()
        assert body["competition"] == "mma"
        assert body["label"] == "MMA"
        assert body["sport_key"] == "mma_mixed_martial_arts"

    async def test_slug_is_case_insensitive(self, client):
        assert (await client.get("/api/hub/MMA")).status_code == 200

    async def test_empty_db_shapes(self, client):
        body = (await client.get("/api/hub/mma")).json()
        assert body["upcoming"] == []
        assert body["sections"] == {}
        assert body["total_markets"] == 0

    async def test_unknown_competition_404(self, client):
        resp = await client.get("/api/hub/quidditch")
        assert resp.status_code == 404

    async def test_rejects_post(self, client):
        assert (await client.post("/api/hub/mma")).status_code == 405


class TestBoxingHub:
    """L2-86 (B5): boxing is a config drop — the same generic hub, one HUB_CONFIGS
    entry + combat-engine lister/classifier, no new page code."""

    async def test_boxing_returns_200_and_echoes_config(self, client):
        body = (await client.get("/api/hub/boxing")).json()
        assert body["competition"] == "boxing"
        assert body["label"] == "Boxing"
        assert body["sport_key"] == "boxing_boxing"
        # Same top-level shape as MMA.
        for key in (
            "competition", "label", "title", "emoji", "blurb",
            "sport_key", "upcoming", "sections", "total_markets",
        ):
            assert key in body, f"missing {key}"

    async def test_boxing_case_insensitive(self, client):
        assert (await client.get("/api/hub/Boxing")).status_code == 200


class TestGolfTennisHubs:
    """L2-87 (B6): golf + tennis hubs drop in as config over the winner-field event
    concepts — same generic hub, one HUB_CONFIGS entry + a winner-field lister."""

    async def test_golf_returns_200_and_echoes_config(self, client):
        body = (await client.get("/api/hub/golf")).json()
        assert body["competition"] == "golf"
        assert body["label"] == "Golf"
        assert body["sport_key"] == "golf_pga"
        for key in (
            "competition", "label", "title", "emoji", "blurb",
            "sport_key", "upcoming", "sections", "total_markets",
        ):
            assert key in body, f"missing {key}"

    async def test_tennis_returns_200_and_echoes_config(self, client):
        body = (await client.get("/api/hub/tennis")).json()
        assert body["competition"] == "tennis"
        assert body["label"] == "Tennis"
        assert body["sport_key"] == "tennis_atp"

    async def test_golf_upcoming_rail_links_to_event_page(self, client, monkeypatch):
        """A golf tournament concept flows into `upcoming` linking to /event/{key}."""
        import app.routes.hub as hub

        async def _fake_golf(db, *, limit=20):
            return [{
                "key": "event:golf:the-open-championship",
                "name": "The Open Championship",
                "domain": "golf",
                "status": "upcoming",
                "start_date": "2026-07-16T00:00:00+00:00",
                "is_major": True,
                "entry_count": 156,
                "_internal": "dropped",  # non-whitelisted — must not leak
            }]

        monkeypatch.setitem(hub._UPCOMING_LISTERS, "golf", _fake_golf)
        body = (await client.get("/api/hub/golf")).json()
        assert len(body["upcoming"]) == 1
        card = body["upcoming"][0]
        assert card["key"] == "event:golf:the-open-championship"
        assert card["is_major"] is True
        assert "_internal" not in card

    async def test_end_date_survives_the_serializer_allowlist(self, client, monkeypatch):
        """UX-P178 (#2167): `_serialize_concept` is an ALLOWLIST.

        A key the lister emits but the serializer does not name is dropped
        silently while the route still returns 200 — the failure mode this same
        test file already pins with `_internal`, in the opposite direction. The
        tennis rail has no start date to serve, so `end_date` IS the card's date:
        if it does not survive the allowlist the card renders "TBD" and the whole
        ship is invisible with every backend test still green.
        """
        import app.routes.hub as hub

        async def _fake_tennis(db, *, limit=20):
            return [{
                "key": "event:tennis:us-open",
                "name": "2026 Women's US Open Winner (Tennis)",
                "domain": "tennis",
                "status": "unknown",
                "start_date": None,
                "end_date": "2026-09-13T00:00:00+00:00",
                "is_major": True,
                "entry_count": 128,
            }]

        monkeypatch.setitem(hub._UPCOMING_LISTERS, "tennis", _fake_tennis)
        card = (await client.get("/api/hub/tennis")).json()["upcoming"][0]
        assert card["end_date"] == "2026-09-13T00:00:00+00:00"
        assert card["start_date"] is None
        assert card["is_major"] is True

    async def test_a_domain_with_a_real_start_still_serves_it(self, client, monkeypatch):
        """The control: adding `end_date` must not disturb the domains that know
        a genuine start. Golf serves one and it survives unchanged, with
        `end_date` present-and-null rather than the start moved."""
        import app.routes.hub as hub

        async def _fake_golf(db, *, limit=20):
            return [{
                "key": "event:golf:the-open-championship",
                "name": "The Open Championship",
                "domain": "golf",
                "status": "upcoming",
                "start_date": "2026-07-16T00:00:00+00:00",
                "is_major": True,
                "entry_count": 156,
            }]

        monkeypatch.setitem(hub._UPCOMING_LISTERS, "golf", _fake_golf)
        card = (await client.get("/api/hub/golf")).json()["upcoming"][0]
        assert card["start_date"] == "2026-07-16T00:00:00+00:00"
        assert card["end_date"] is None


class TestEsportsHub:
    """L2-92 (B4): esports drops in as a sections-ONLY hub (no concept_domain).
    The data is too messy for per-tournament event concepts yet, so the hub
    surfaces tournament outrights via league_futures and has no upcoming rail."""

    async def test_esports_returns_200_and_echoes_config(self, client):
        body = (await client.get("/api/hub/esports")).json()
        assert body["competition"] == "esports"
        assert body["label"] == "Esports"
        assert body["sport_key"] == "esports"
        for key in (
            "competition", "label", "title", "emoji", "blurb",
            "sport_key", "upcoming", "sections", "total_markets",
        ):
            assert key in body, f"missing {key}"

    async def test_esports_case_insensitive(self, client):
        assert (await client.get("/api/hub/Esports")).status_code == 200

    async def test_esports_has_no_upcoming_rail(self, client):
        # No concept_domain → sections-only; the upcoming rail stays empty.
        body = (await client.get("/api/hub/esports")).json()
        assert body["upcoming"] == []


# ============================================================================
# Upcoming rail (event-concept lister)
# ============================================================================


class TestHubUpcoming:
    async def test_upcoming_rail_serialized(self, client, monkeypatch):
        """A card concept flows into `upcoming` with only the public fields."""
        import app.routes.hub as hub

        async def _fake_lister(db, *, limit=20):
            return [{
                "key": "event:ufc:26jul11",
                "name": "UFC 329: Jones vs. Aspinall",
                "domain": "ufc",
                "status": "upcoming",
                "start_date": "2026-07-11T23:00:00+00:00",
                "is_major": True,
                "fight_count": 12,
                "main_event_id": 999,          # internal — must be dropped
                "latest_commence": "whatever",  # internal — must be dropped
            }]

        monkeypatch.setitem(hub._UPCOMING_LISTERS, "ufc", _fake_lister)

        body = (await client.get("/api/hub/mma")).json()
        assert len(body["upcoming"]) == 1
        card = body["upcoming"][0]
        assert card["key"] == "event:ufc:26jul11"
        assert card["name"] == "UFC 329: Jones vs. Aspinall"
        assert card["is_major"] is True
        assert card["fight_count"] == 12
        # internal fields not leaked
        assert "main_event_id" not in card
        assert "latest_commence" not in card

    async def test_far_future_upcoming_card_capped(self, client, monkeypatch):
        """L2-101 Item 2: a combat card ~1yr out is dropped from the rail (it sorts
        marquee-first and otherwise pads /hub/mma), while a soon card survives."""
        import app.routes.hub as hub
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        soon = (now + timedelta(days=5)).isoformat()
        far = (now + timedelta(days=365)).isoformat()  # ~1yr out (e.g. McGregor)

        async def _fake_lister(db, *, limit=20):
            return [
                {  # a numbered major ~1yr out — is_major floats it first
                    "key": "event:ufc:27jul11",
                    "name": "UFC 350: Pimblett vs. McGregor",
                    "domain": "ufc",
                    "status": "upcoming",
                    "start_date": far,
                    "is_major": True,
                    "fight_count": 12,
                    "latest_commence": far,
                },
                {  # this Saturday's card
                    "key": "event:ufc:26jul18",
                    "name": "Ricci vs. Kline",
                    "domain": "ufc",
                    "status": "upcoming",
                    "start_date": soon,
                    "is_major": False,
                    "fight_count": 10,
                    "latest_commence": soon,
                },
            ]

        monkeypatch.setitem(hub._UPCOMING_LISTERS, "ufc", _fake_lister)
        body = (await client.get("/api/hub/mma")).json()
        keys = {c["key"] for c in body["upcoming"]}
        assert "event:ufc:26jul18" in keys  # soon card survives
        assert "event:ufc:27jul11" not in keys  # far-future card dropped

    async def test_live_card_never_capped(self, client, monkeypatch):
        """The horizon only caps `upcoming` — a live card is kept regardless."""
        import app.routes.hub as hub
        from datetime import datetime, timedelta, timezone

        far = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

        async def _fake_lister(db, *, limit=20):
            return [{
                "key": "event:ufc:live",
                "name": "Live Card",
                "domain": "ufc",
                "status": "live",  # not "upcoming" → never dropped
                "start_date": far,
                "is_major": False,
                "fight_count": 8,
                "latest_commence": far,
            }]

        monkeypatch.setitem(hub._UPCOMING_LISTERS, "ufc", _fake_lister)
        body = (await client.get("/api/hub/mma")).json()
        assert {c["key"] for c in body["upcoming"]} == {"event:ufc:live"}

    async def test_a_card_with_an_unknown_phase_is_still_capped(
        self, client, monkeypatch
    ):
        """UX-P209. The cap used to read `status != "upcoming"` and keep
        everything else, on the reasoning that live/settled cards are happening
        now. `unknown` is neither: it says we could not establish the phase, and
        a card dated a year out is far-future whether or not we know what it is
        doing. Left alone, the fix one layer down — a lister that stops making
        an affirmative claim — would have quietly exempted every card it emits
        from the horizon without one line here changing.

        No capped domain emits `unknown` today (`_HORIZON_CAPPED_DOMAINS` is
        combat-only, tennis is not in it), so this drives the real route with a
        substituted lister and pins the rule rather than a current behaviour.
        The near-dated sibling is the control: it proves the rail did not simply
        come back empty.
        """
        import app.routes.hub as hub
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        far = (now + timedelta(days=365)).isoformat()
        soon = (now + timedelta(days=5)).isoformat()

        async def _fake_lister(db, *, limit=20):
            return [
                {
                    "key": "event:ufc:unknown-far",
                    "name": "Phase Unknown, A Year Out",
                    "domain": "ufc",
                    "status": "unknown",
                    "start_date": far,
                    "is_major": False,
                    "fight_count": 8,
                    "latest_commence": far,
                },
                {
                    "key": "event:ufc:unknown-soon",
                    "name": "Phase Unknown, This Week",
                    "domain": "ufc",
                    "status": "unknown",
                    "start_date": soon,
                    "is_major": False,
                    "fight_count": 8,
                    "latest_commence": soon,
                },
            ]

        monkeypatch.setitem(hub._UPCOMING_LISTERS, "ufc", _fake_lister)
        body = (await client.get("/api/hub/mma")).json()
        keys = {c["key"] for c in body["upcoming"]}
        assert keys == {"event:ufc:unknown-soon"}, (
            "an unknown-phase card escaped the horizon cap"
        )


# ============================================================================
# Props reclassification (fights vs props out of league_futures "matches")
# ============================================================================


class TestHubPropSplit:
    async def test_props_split_out_of_matches(self, client, mock_db):
        """A KXUFCMOV prop lands in `props` (not `matches`); the fight stays."""
        mock_db.execute.return_value = _scalars_result([
            # A real fight (KXUFCFIGHT, two-sided) → stays in matches
            _mock_market(
                market_id=1,
                name="Jones vs Aspinall",
                external_id="KXUFCFIGHT-26JUL11JONASP",
            ),
            # A method-of-victory prop (KXUFCMOV) → moves to props
            _mock_market(
                market_id=2,
                name="Jones-Aspinall method of victory",
                external_id="KXUFCMOV-26JUL11JONASP",
            ),
        ])

        body = (await client.get("/api/hub/mma")).json()
        sections = body["sections"]

        assert "props" in sections
        prop_ids = {m["id"] for m in sections["props"]}
        assert 2 in prop_ids
        prop = next(m for m in sections["props"] if m["id"] == 2)
        assert prop["prop_type"] == "method"
        assert prop["section"] == "props"

        # The fight is not in props
        assert 2 not in {m["id"] for m in sections.get("matches", [])}
        assert 1 not in prop_ids


# ============================================================================
# UX-P167 (#2167) — the section vocabulary is served per competition
# ============================================================================


class TestHubSectionVocabulary:
    """`/hub/tennis` printed "Fight Markets" over 103 tennis markets.

    The heading map lived in the page as one competition-blind object written
    when MMA was the only hub, so MMA's words rendered on every hub the generic
    page grew afterwards. Measured live 2026-08-29, during US Open week — the
    payloads are banked at `backend/tests/fixtures/uxp167_hub_vocabulary.json`:

        /hub/tennis    "FIGHT MARKETS"    over 103 tennis markets
                       "UPCOMING CARDS"   over 12 tournaments
        /hub/esports   "FIGHT MARKETS"    over  98 esports markets
        /hub/golf      "FIGHTER STATS"    over   5 golf markets
                       "UPCOMING CARDS"   over  3 tournaments

    The words now travel in the payload beside `label`/`title`/`blurb`, and only
    the sport-SPECIFIC ones do: combat overrides, everyone else sends `{}` and
    the client falls back to a neutral default. Both directions are asserted
    (gotcha #43) — combat must KEEP its vocabulary, and a hub that is not a
    combat sport must carry none of it.
    """

    # The words that may only ever reach a combat hub. Asserted against served
    # VALUES for named keys, never as a bare substring sweep over the whole
    # body — an over-broad `not in` fails on a correct file (UX-P164/165).
    COMBAT_WORDS = ("Fight", "Fighter", "Cards")

    async def test_combat_hubs_keep_their_vocabulary(self, client):
        """The fix must not flatten MMA and boxing into generic words."""
        for slug in ("mma", "boxing"):
            body = (await client.get(f"/api/hub/{slug}")).json()
            labels = body["section_labels"]
            assert labels["matches"] == "Fight Markets", slug
            assert labels["props"] == "Fight Props", slug
            assert labels["season_stats"] == "Fighter Stats", slug
            assert body["upcoming_label"] == "Upcoming Cards", slug

    async def test_non_combat_hubs_carry_no_fight_vocabulary(self, client):
        """golf / tennis / esports: the three hubs that rendered it wrong."""
        for slug in ("golf", "tennis", "esports"):
            body = (await client.get(f"/api/hub/{slug}")).json()
            # An empty override map is the declaration, not an omission: it says
            # "this competition has no words of its own", which is what makes the
            # client's neutral default the intended reading rather than a guess.
            assert body["section_labels"] == {}, slug
            assert body["upcoming_label"] == "Upcoming Tournaments", slug
            for word in self.COMBAT_WORDS:
                assert word not in body["upcoming_label"], (slug, word)

    async def test_every_configured_hub_declares_both_fields(self, client):
        """Vacuity companion: a hub added later cannot skip the declaration and
        silently inherit whatever the client happens to default to."""
        from app.routes.hub import HUB_CONFIGS

        assert len(HUB_CONFIGS) >= 5, "the census below covered five hubs"
        seen = 0
        for slug in HUB_CONFIGS:
            body = (await client.get(f"/api/hub/{slug}")).json()
            assert isinstance(body["section_labels"], dict), slug
            assert isinstance(body["upcoming_label"], str), slug
            assert body["upcoming_label"], slug
            seen += 1
        assert seen == len(HUB_CONFIGS)

    async def test_only_combat_configs_override_section_labels(self, client):
        """The override map is opt-IN, so silence can never mean another sport's
        word. Reading the configs directly, not the responses, so a hub whose
        sections happen to be empty today is still covered."""
        from app.routes.hub import HUB_CONFIGS

        overriding = {s for s, c in HUB_CONFIGS.items() if c.section_labels}
        assert overriding == {"mma", "boxing"}, overriding

    async def test_fixture_records_what_production_served(self):
        """The BEFORE side, re-derived rather than asserted from prose: the
        banked payloads plus the SHIPPED chrome rule (a header needs >= 2 items
        and >= 2 sections) must reproduce the five wrong headings."""
        import json
        import pathlib

        fixture = json.loads(
            (
                pathlib.Path(__file__).resolve().parents[1]
                / "fixtures"
                / "uxp167_hub_vocabulary.json"
            ).read_text()
        )
        wrong = {
            (slug, b["header"], b["over"])
            for slug, hub in fixture["hubs"].items()
            for b in hub["before_headers"]
            if any(w in b["header"] for w in TestHubSectionVocabulary.COMBAT_WORDS)
        }
        assert wrong == {
            ("tennis", "Fight Markets", 103),
            ("tennis", "Upcoming Cards", 12),
            ("esports", "Fight Markets", 98),
            ("golf", "Fighter Stats", 5),
            ("golf", "Upcoming Cards", 3),
            # mma / boxing are the control: their fight words were correct.
            ("mma", "Fight Markets", 28),
            ("mma", "Upcoming Cards", 15),
            ("boxing", "Upcoming Cards", 17),
        }, wrong


class TestHubNeutralUpcomingLabel:
    """UX-P210, repairing CERT-525 — the rail heading gets a phase-free twin.

    CERT-519 stopped a tennis card CLAIMING a phase it cannot establish; the
    card's pill goes silent on `unknown`. CERT-525 found the claim one level up
    and still standing:

        > Unknown tennis cards lose the per-card Upcoming pill but remain
        > directly beneath the visible `Upcoming Tournaments` heading, so the
        > hub still makes the same unsupported phase claim one level up.

    The heading is a claim about EVERY card under it, so it is licensed only
    when every card is actually upcoming. That is a fact about the rail the
    client assembled, so the client decides (see
    `frontend/lib/hubUpcomingHeading.ts`) and this side supplies the word it
    picks from. Deciding it here instead would leave the renderer free to print
    an affirmative heading over an `unknown` card, which is precisely the state
    CERT-525 blocked — and would make the render guard the cert asked for
    vacuous, since the page would only be proving that it prints what it is
    handed.

    What this class polices is the vocabulary contract: the neutral word exists
    for every hub, and no phase claim ever gets back into it.
    """

    # A word that says WHEN. The neutral label may contain none of them; the
    # affirmative label must contain one, which is what keeps this list honest.
    PHASE_WORDS = ("upcoming", "live", "final", "settled", "soon", "next", "today")

    def _phase_words_in(self, text: str) -> list[str]:
        low = text.lower()
        return [w for w in self.PHASE_WORDS if w in low]

    async def test_the_phase_word_list_can_report_a_positive(self, client):
        """Vacuity control FIRST (UX-P204): a detector that matches nothing would
        pass every assertion below. The affirmative labels are the known
        positives — each one is a phase claim and must be seen as one."""
        from app.routes.hub import HUB_CONFIGS

        assert HUB_CONFIGS, "no configs to census"
        for slug, cfg in HUB_CONFIGS.items():
            assert self._phase_words_in(cfg.upcoming_label), (
                slug,
                cfg.upcoming_label,
            )
        # And the other direction — it must not match everything it is shown.
        assert self._phase_words_in("Tournaments") == []
        assert self._phase_words_in("Cards") == []

    async def test_every_hub_declares_a_phase_free_neutral_label(self, client):
        """Both halves, on the SERVED payload rather than the config, because the
        payload is what the renderer gets (UX-P208-5: an allowlist between the
        two can drop a field silently)."""
        from app.routes.hub import HUB_CONFIGS

        assert len(HUB_CONFIGS) >= 5, "the census below covered five hubs"
        seen = 0
        for slug in HUB_CONFIGS:
            body = (await client.get(f"/api/hub/{slug}")).json()
            # `in`, not `.get()` — absent and null are different failures and
            # `.get()` cannot tell them apart (UX-P200-6).
            assert "upcoming_label_neutral" in body, slug
            neutral = body["upcoming_label_neutral"]
            assert isinstance(neutral, str) and neutral, (slug, neutral)
            assert self._phase_words_in(neutral) == [], (slug, neutral)
            seen += 1
        assert seen == len(HUB_CONFIGS)

    async def test_the_neutral_label_keeps_each_hub_its_own_noun(self, client):
        """Dropping the phase word must not also flatten the sport's vocabulary —
        that was UX-P167's bug in the opposite direction. A card is still a card
        and a slam is still a tournament; only the WHEN goes away."""
        for slug in ("mma", "boxing"):
            body = (await client.get(f"/api/hub/{slug}")).json()
            assert body["upcoming_label_neutral"] == "Cards", slug
        for slug in ("golf", "tennis", "esports"):
            body = (await client.get(f"/api/hub/{slug}")).json()
            assert body["upcoming_label_neutral"] == "Tournaments", slug
