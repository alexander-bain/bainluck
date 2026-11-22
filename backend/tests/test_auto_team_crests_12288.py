"""Automatic teams-table crests & public sports missing-art logging (#12288, Fable 2:08 PM Item 1)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from app.routes.events import TeamSnapshot, _dedupe_team_name_lookup
from app.utils.container_machinery import (
    CANDIDATE_NFL_WEEK_PATH,
    SubjectArtResolver,
    _CANDIDATES_DIR,
    _is_sports_context,
    _is_sports_definition,
    _load_snapshot_from_db,
    load_machinery_definition,
    produce_container_machinery,
)

NOW = datetime(2026, 11, 21, 18, 0, tzinfo=timezone.utc)


def _sample_teams() -> list[TeamSnapshot]:
    return [
        TeamSnapshot(
            id=1,
            sport_id=10,
            sport_key="icehockey_nhl",
            name="Seattle Kraken",
            abbreviation="SEA",
            primary_color="#001628",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/sea.png",
            alternate_names=("Seattle", "Kraken"),
        ),
        TeamSnapshot(
            id=2,
            sport_id=10,
            sport_key="icehockey_nhl",
            name="Florida Panthers",
            abbreviation="FLA",
            primary_color="#C8102E",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/fla.png",
            alternate_names=("Panthers",),
        ),
        # Corroborated school across NCAAF + NCAAB -> populates both lookup & by_league (#7262).
        TeamSnapshot(
            id=3,
            sport_id=11,
            sport_key="basketball_ncaab",
            name="Duke Blue Devils",
            abbreviation="DUKE",
            primary_color="#003087",
            logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/150.png",
            alternate_names=("Duke",),
        ),
        TeamSnapshot(
            id=4,
            sport_id=16,
            sport_key="americanfootball_ncaaf",
            name="Duke Blue Devils",
            abbreviation="DUKE",
            primary_color="#003087",
            logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/150.png",
            alternate_names=("Duke",),
        ),
        # Corroborated Oregon across NCAAF + NCAAB, plus bare alias colliding in lacrosse.
        TeamSnapshot(
            id=11,
            sport_id=11,
            sport_key="basketball_ncaab",
            name="Oregon Ducks",
            abbreviation="ORE",
            primary_color="#154733",
            logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2483.png",
            alternate_names=("Oregon",),
        ),
        TeamSnapshot(
            id=12,
            sport_id=16,
            sport_key="americanfootball_ncaaf",
            name="Oregon Ducks",
            abbreviation="ORE",
            primary_color="#154733",
            logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2483.png",
            alternate_names=("Oregon",),
        ),
        TeamSnapshot(
            id=13,
            sport_id=17,
            sport_key="baseball_ncaa",
            name="Oregon Ducks Baseball",
            abbreviation="ORE",
            primary_color="#154733",
            logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/default.png",
            alternate_names=("Oregon",),
        ),
        TeamSnapshot(
            id=5,
            sport_id=12,
            sport_key="soccer_spain_la_liga",
            name="FC Barcelona",
            abbreviation="BAR",
            primary_color="#A50044",
            logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/83.png",
            alternate_names=("Barcelona",),
        ),
        TeamSnapshot(
            id=6,
            sport_id=13,
            sport_key="soccer_france_ligue_one",
            name="Paris Saint-Germain",
            abbreviation="PSG",
            primary_color="#004170",
            logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/160.png",
            alternate_names=("PSG",),
        ),
        TeamSnapshot(
            id=7,
            sport_id=14,
            sport_key="basketball_nba",
            name="Atlanta Hawks",
            abbreviation="ATL",
            primary_color="#E03A3E",
            logo_url_small="https://teams-table.example.com/nba/atl-live-db-crest.png",
            alternate_names=("Atlanta", "Hawks"),
        ),
        TeamSnapshot(
            id=8,
            sport_id=15,
            sport_key="baseball_ncaa",
            name="Coastal Carolina Chanticleers",
            abbreviation="CCU",
            primary_color="#006F71",
            logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/default.png",
            alternate_names=("Coastal Carolina",),
        ),
        TeamSnapshot(
            id=9,
            sport_id=18,
            sport_key="lacrosse_pll",
            name="New York Atlas",
            abbreviation="ATL",
            primary_color="#0B162A",
            logo_url_small="https://a.espncdn.com/i/teamlogos/pll/500/atlas.png",
            alternate_names=("Atlas",),
        ),
    ]


def test_teams_table_resolves_nhl_ncaa_and_soccer_crests_with_league_disambiguation() -> None:
    lookup = _dedupe_team_name_lookup(_sample_teams())
    resolver = SubjectArtResolver(team_lookup=lookup)

    # NHL team not on any static list resolves automatically from teams table.
    kraken = resolver.resolve(
        "Seattle Kraken",
        sport_key="icehockey_nhl",
        allow_team_lookup=True,
    )
    assert kraken["url"] == "https://a.espncdn.com/i/teamlogos/nhl/500/sea.png"
    assert kraken["kind"] == "team_logo"
    assert kraken["accent_color"] == "#001628"

    # Full NHL name resolves while cross-league bare collision stays protected.
    fla_nhl = resolver.resolve("Florida Panthers", sport_key="icehockey_nhl", allow_team_lookup=True)
    assert fla_nhl["url"] == "https://a.espncdn.com/i/teamlogos/nhl/500/fla.png"

    # Per-league resolution across NCAAB + NCAAF when a school collides with a placeholder row (#7262).
    oregon_ncaab = resolver.resolve("Oregon", sport_key="basketball_ncaab", allow_team_lookup=True)
    oregon_ncaaf = resolver.resolve("Oregon", sport_key="americanfootball_ncaaf", allow_team_lookup=True)
    assert oregon_ncaab["url"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/2483.png"
    assert oregon_ncaaf["url"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/2483.png"

    # Sport-family refusal (#8787): PLL lacrosse "Atlas" never paints a soccer Liga MX fixture.
    atlas_soccer = resolver.resolve("Atlas", sport_key="soccer_mexico_ligamx", allow_team_lookup=True)
    assert atlas_soccer["url"] is None

    # Prefix/diacritic stripping + short alias for college & European soccer clubs.
    duke = resolver.resolve("Duke", sport_key="basketball_ncaab", allow_team_lookup=True)
    assert duke["url"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/150.png"
    psg_ascii = resolver.resolve(
        "Paris Saint Germain", sport_key="soccer_uefa_champs_league", allow_team_lookup=True
    )
    assert psg_ascii["url"] == "https://a.espncdn.com/i/teamlogos/soccer/500/160.png"

    # Teams table takes precedence over static hand list when a team row carries a crest.
    hawks = resolver.resolve("Atlanta Hawks", sport_key="basketball_nba", allow_team_lookup=True)
    assert hawks["url"] == "https://teams-table.example.com/nba/atl-live-db-crest.png"

    # ESPN placeholder /default.png is never treated as a crest.
    ccu_placeholder = resolver.resolve(
        "Coastal Carolina", sport_key="baseball_ncaa", allow_team_lookup=True
    )
    assert ccu_placeholder["url"] is None


def test_culture_and_non_sports_cards_never_pull_from_teams_table() -> None:
    lookup = _dedupe_team_name_lookup(_sample_teams())
    resolver = SubjectArtResolver(team_lookup=lookup)

    for label in ("Oregon", "Duke", "Seattle Kraken", "FC Barcelona"):
        res = resolver.resolve(label, allow_team_lookup=False)
        assert res["url"] is None
        assert res["kind"] == "monogram"


@pytest.mark.asyncio
async def test_championship_card_automatically_resolves_nhl_and_soccer_crests_3_of_3() -> None:
    defn = load_machinery_definition(_CANDIDATES_DIR / "machinery-big-championships-2027.json")
    markets = [
        {
            "id": 57792807,
            "name": "NCAA Football: 2026 Heisman Award Winner",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "football",
            "volume": 50000,
            "outcomes": [{"id": 201, "name": "Jeremiah Smith", "probability": 0.63}],
        },
        {
            "id": 66031970,
            "name": "NBA: 2026-27 MVP",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "basketball",
            "volume": 50000,
            "outcomes": [{"id": 202, "name": "Victor Wembanyama", "probability": 0.39}],
        },
        {
            "id": 52755659,
            "name": "2026-27 Stanley Cup Final Winner",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "hockey",
            "volume": 50000,
            "outcomes": [{"id": 206, "name": "Seattle Kraken", "probability": 0.22}],
        },
    ]
    res = await produce_container_machinery(
        {"markets": markets, "teams": _sample_teams()},
        defn,
        now=NOW,
    )
    assert hasattr(res, "machinery_card")
    rows = res.machinery_card["rows"]
    assert len(rows) == 3
    urls = [r.get("art", {}).get("url") for r in rows]
    assert all(urls)
    assert urls[2] == "https://a.espncdn.com/i/teamlogos/nhl/500/sea.png"


@pytest.mark.asyncio
async def test_public_sports_card_logs_missing_subject_when_row_pictures_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    defn = load_machinery_definition(_CANDIDATES_DIR / "machinery-big-championships-2027.json")
    markets = [
        {
            "id": 57792807,
            "name": "NCAA Football: 2026 Heisman Award Winner",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "football",
            "volume": 50000,
            "outcomes": [{"id": 201, "name": "Jeremiah Smith", "probability": 0.63}],
        },
        {
            "id": 66031970,
            "name": "NBA: 2026-27 MVP",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "basketball",
            "volume": 50000,
            "outcomes": [{"id": 202, "name": "Victor Wembanyama", "probability": 0.39}],
        },
        {
            "id": 52755659,
            "name": "2026-27 Stanley Cup Final Winner",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "hockey",
            "volume": 50000,
            "outcomes": [{"id": 206, "name": "Unlisted Expansion Club", "probability": 0.22}],
        },
    ]
    with caplog.at_level(logging.WARNING, logger="app.utils.container_machinery"):
        res = await produce_container_machinery(
            {"markets": markets, "teams": _sample_teams()},
            defn,
            now=NOW,
        )
    assert hasattr(res, "machinery_card")
    rows = res.machinery_card["rows"]
    by_mid = {int(r["market_id"]): r for r in rows}
    # Pictured sports rows keep their verified crests while unpictured rows get initials fallback...
    assert by_mid[57792807].get("art", {}).get("url")
    assert by_mid[66031970].get("art", {}).get("url")
    missing_art = by_mid[52755659].get("art") or {}
    assert not missing_art.get("url")
    assert missing_art.get("kind") == "monogram"
    assert missing_art.get("initials") == "UC"
    # ...and logs the exact missing subject on public sports cards.
    warn_msgs = [rec.message for rec in caplog.records if rec.levelno == logging.WARNING]
    assert any(
        "machinery-big-championships-2027" in m and "Unlisted Expansion Club" in m
        for m in warn_msgs
    ), warn_msgs


@pytest.mark.asyncio
async def test_culture_card_never_uses_teams_table_and_does_not_emit_sports_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    defn = load_machinery_definition(_CANDIDATES_DIR / "machinery-2026-summed-up.json")
    markets = [
        {
            "id": 27467306,
            "name": "TIME Person of the Year 2026",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000,
            "outcomes": [{"id": 101, "name": "Oregon", "probability": 0.45}],
        },
        {
            "id": 8431009,
            "name": "Merriam-Webster Word of the Year 2026?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000,
            "outcomes": [{"id": 102, "name": "Duke", "probability": 0.20}],
        },
        {
            "id": 109517,
            "name": "Top artist on Spotify in 2026?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000,
            "outcomes": [{"id": 103, "name": "Seattle Kraken", "probability": 0.15}],
        },
    ]
    with caplog.at_level(logging.WARNING, logger="app.utils.container_machinery"):
        res = await produce_container_machinery(
            {"markets": markets, "teams": _sample_teams()},
            defn,
            now=NOW,
        )
    assert hasattr(res, "machinery_card")
    rows = res.machinery_card["rows"]
    assert all(not r.get("art", {}).get("url") for r in rows)
    assert not any("dropped row pictures" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_load_snapshot_from_db_warms_team_lookup_even_when_names_only_live_in_by_league(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.routes.events as events_mod

    defn = load_machinery_definition(CANDIDATE_NFL_WEEK_PATH)
    # Two schools share one corroborated logo each across their own sports while a different
    # school uses the same bare alias in another sport -> bare dict may drop the key while
    # `.by_league` still carries it (#7262 invariant: check `is not None`, never truthiness).
    colliding_lookup = _dedupe_team_name_lookup(
        [
            TeamSnapshot(
                id=2,
                sport_id=10,
                sport_key="icehockey_nhl",
                name="Oregon",
                abbreviation="ORE",
                primary_color="#154733",
                logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/col.png",
            ),
            TeamSnapshot(
                id=3,
                sport_id=11,
                sport_key="basketball_ncaab",
                name="Oregon",
                abbreviation="ORE",
                primary_color="#154733",
                logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2483.png",
            ),
            TeamSnapshot(
                id=4,
                sport_id=16,
                sport_key="americanfootball_ncaaf",
                name="Oregon",
                abbreviation="ORE",
                primary_color="#154733",
                logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/2483.png",
            ),
        ]
    )
    assert len(colliding_lookup) == 0
    assert "Oregon" in colliding_lookup.by_league

    calls: list[list[str]] = []

    async def _fake_build(db, names):
        calls.append(list(names))
        return colliding_lookup

    monkeypatch.setattr(events_mod, "_build_team_lookup", _fake_build)
    monkeypatch.setattr(events_mod, "_team_cache", None)

    class _FakeScalarResult:
        def all(self):
            return []

        def unique(self):
            return self

        def scalars(self):
            return self

    class _FakeSession:
        async def execute(self, stmt):
            return _FakeScalarResult()

    snap = await _load_snapshot_from_db(_FakeSession(), defn, NOW)
    assert snap["team_lookup"] is colliding_lookup
    assert calls, "_build_team_lookup should be called for sports definitions"


def test_pure_teams_table_resolution_with_empty_static_catalog_and_wncaab_borrow() -> None:
    db_teams = [
        TeamSnapshot(
            id=101,
            sport_id=20,
            sport_key="soccer_spain_la_liga",
            name="Barcelona",
            abbreviation="BAR",
            primary_color="#A50044",
            logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/83.png",
        ),
        TeamSnapshot(
            id=102,
            sport_id=21,
            sport_key="soccer_epl",
            name="Arsenal",
            abbreviation="ARS",
            primary_color="#EF0107",
            logo_url_small="https://a.espncdn.com/i/teamlogos/soccer/500/359.png",
        ),
        TeamSnapshot(
            id=103,
            sport_id=22,
            sport_key="icehockey_nhl",
            name="Seattle Kraken",
            abbreviation="SEA",
            primary_color="#001628",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/sea.png",
        ),
        TeamSnapshot(
            id=104,
            sport_id=23,
            sport_key="basketball_nba",
            name="Oklahoma City Thunder",
            abbreviation="OKC",
            primary_color="#007AC1",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/okc.png",
        ),
        TeamSnapshot(
            id=105,
            sport_id=22,
            sport_key="icehockey_nhl",
            name="Colorado Avalanche",
            abbreviation="COL",
            primary_color="#6F263D",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/col.png",
        ),
        TeamSnapshot(
            id=106,
            sport_id=24,
            sport_key="basketball_ncaab",
            name="UConn Huskies",
            abbreviation="CONN",
            primary_color="#000E2F",
            logo_url_small="https://a.espncdn.com/i/teamlogos/ncaa/500/41.png",
        ),
    ]
    lookup = _dedupe_team_name_lookup(db_teams)
    resolver = SubjectArtResolver(team_lookup=lookup, _static_by_norm={})

    barca = resolver.resolve("FC Barcelona", sport_key="soccer_uefa_champs_league", allow_team_lookup=True)
    arsenal = resolver.resolve("Arsenal FC", sport_key="soccer_epl", allow_team_lookup=True)
    kraken = resolver.resolve("Seattle Kraken", sport_key="icehockey_nhl", allow_team_lookup=True)
    thunder = resolver.resolve("Oklahoma City Thunder", sport_key="basketball_nba", allow_team_lookup=True)
    avs = resolver.resolve("Colorado Avalanche", sport_key="icehockey_nhl", allow_team_lookup=True)
    w_uconn = resolver.resolve("UConn Huskies", sport_key="basketball_wncaab", allow_team_lookup=True)

    assert barca["url"] == "https://a.espncdn.com/i/teamlogos/soccer/500/83.png"
    assert arsenal["url"] == "https://a.espncdn.com/i/teamlogos/soccer/500/359.png"
    assert kraken["url"] == "https://a.espncdn.com/i/teamlogos/nhl/500/sea.png"
    assert thunder["url"] == "https://a.espncdn.com/i/teamlogos/nba/500/okc.png"
    assert avs["url"] == "https://a.espncdn.com/i/teamlogos/nhl/500/col.png"
    assert w_uconn["url"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/41.png"


def test_super_bowl_halftime_show_is_not_sports_and_suppresses_static_team_logos() -> None:
    culture_def = load_machinery_definition(_CANDIDATES_DIR / "machinery-2026-summed-up.json")
    halftime_market = {
        "id": 999001,
        "name": "Super Bowl Halftime Show Performer",
        "llm_sport_category": "entertainment",
    }
    assert _is_sports_context(halftime_market, culture_def) is False
    # True sports Super Bowl market remains sports context.
    assert _is_sports_context({"id": 999002, "name": "NFL Super Bowl Winner"}) is True

    resolver = SubjectArtResolver(team_lookup=_dedupe_team_name_lookup(_sample_teams()))
    for city_or_nickname in ("Miami", "Chicago", "Seattle Kraken"):
        res = resolver.resolve(city_or_nickname, allow_team_lookup=False)
        assert res["url"] is None, f"expected no static team_logo for {city_or_nickname!r}, got {res}"
        assert res["kind"] == "monogram"


@pytest.mark.asyncio
async def test_championship_missing_art_warning_names_outcome_subject_not_champions_league(
    caplog: pytest.LogCaptureFixture,
) -> None:
    defn = load_machinery_definition(_CANDIDATES_DIR / "machinery-big-championships-2027.json")
    markets = [
        {
            "id": 57792807,
            "name": "NCAA Football: 2026 Heisman Award Winner",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "football",
            "volume": 50000,
            "outcomes": [{"id": 201, "name": "Jeremiah Smith", "probability": 0.63}],
        },
        {
            "id": 66031970,
            "name": "NBA: 2026-27 MVP",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "basketball",
            "volume": 50000,
            "outcomes": [{"id": 202, "name": "Victor Wembanyama", "probability": 0.39}],
        },
        {
            "id": 70732924,
            "name": "UEFA Champions League: 2027 Champion",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "soccer",
            "volume": 50000,
            "outcomes": [{"id": 203, "name": "Unknown Club", "probability": 0.18}],
        },
    ]
    with caplog.at_level(logging.WARNING, logger="app.utils.container_machinery"):
        res = await produce_container_machinery(
            {"markets": markets, "teams": _sample_teams()},
            defn,
            now=NOW,
        )
    assert hasattr(res, "machinery_card")
    by_mid = {int(r["market_id"]): r for r in res.machinery_card["rows"]}
    assert by_mid[57792807].get("art", {}).get("url")
    assert by_mid[66031970].get("art", {}).get("url")
    missing_art = by_mid[70732924].get("art") or {}
    assert not missing_art.get("url")
    assert missing_art.get("kind") == "monogram"
    assert missing_art.get("initials") == "UC"
    warn_msgs = [rec.message for rec in caplog.records if rec.levelno == logging.WARNING]
    assert any(
        "machinery-big-championships-2027" in m
        and "Unknown Club" in m
        and "Champions League" not in m
        for m in warn_msgs
    ), warn_msgs


@pytest.mark.asyncio
async def test_three_culture_cards_keep_card_image_and_verified_people_row_pictures_without_team_logos(
    caplog: pytest.LogCaptureFixture,
) -> None:
    culture_fixtures = [
        (
            "machinery-2026-summed-up.json",
            [
                (27467306, "TIME Person of the Year 2026", "James Talarico", 0.45),
                (109517, "Top artist on Spotify in 2026?", "Bad Bunny", 0.40),
                (109537, "#2 Most Searched Person on Google in 2026?", "Drake", 0.35),
            ],
        ),
        (
            "machinery-stage-and-cover.json",
            [
                (62368061, "Who will host Saturday Night Live Season 52?", "Taylor Swift", 0.65),
                (109296, "Call Her Daddy: Guests this year", "Bad Bunny", 0.50),
                (56775621, "Vogue (US) 2026: Cover Models", "SZA", 0.40),
            ],
        ),
        (
            "machinery-cast-delayed-cancelled.json",
            [
                (109214, "Avengers: Doomsday: Cast", "Taylor Swift", 0.55),
                (108506, "Marvel: Actor cast as Miles Morales", "Bad Bunny", 0.30),
                (70150106, "The Brave and the Bold · Cast", "SZA", 0.20),
            ],
        ),
    ]
    static_resolver = SubjectArtResolver()
    for matched_person in ("James Talarico", "Bad Bunny", "Drake", "Taylor Swift", "SZA"):
        assert static_resolver.resolve(matched_person, allow_team_lookup=False)["url"]

    with caplog.at_level(logging.WARNING, logger="app.utils.container_machinery"):
        for filename, rows_spec in culture_fixtures:
            defn = load_machinery_definition(_CANDIDATES_DIR / filename)
            assert not defn["rule"].get("hide_row_art")
            markets = [
                {
                    "id": mid,
                    "name": mname,
                    "status": "open",
                    "source": "polymarket",
                    "llm_sport_category": "entertainment",
                    "volume": 50000,
                    "outcomes": [{"id": idx + 1, "name": subj, "probability": prob}],
                }
                for idx, (mid, mname, subj, prob) in enumerate(rows_spec)
            ]
            res = await produce_container_machinery(
                {"markets": markets, "teams": _sample_teams()},
                defn,
                now=NOW,
            )
            assert hasattr(res, "machinery_card")
            assert res.machinery_card["image_url"] == defn["rule"]["card_image_url"]
            card_rows = res.machinery_card["rows"]
            assert len(card_rows) == 3
            assert all(r.get("art", {}).get("url") for r in card_rows), (filename, card_rows)
            assert all(r.get("art", {}).get("kind") != "team_logo" for r in card_rows), (filename, card_rows)

    assert not any("dropped row pictures" in rec.message for rec in caplog.records)


def test_ambiguous_city_or_nickname_never_falls_back_to_other_sport_static_crest() -> None:
    """When TeamNameLookup refuses an ambiguous city ('Miami', 'Carolina') or nickname,
    static nfl_teams/espn_team_logo entries from another league must be refused too."""
    teams = [
        TeamSnapshot(
            id=101,
            sport_id=12,
            sport_key="basketball_nba",
            name="Miami Heat",
            abbreviation="MIA",
            primary_color="#98002E",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/mia.png",
            alternate_names=("Miami",),
        ),
        TeamSnapshot(
            id=565,
            sport_id=13,
            sport_key="americanfootball_nfl",
            name="Miami Dolphins",
            abbreviation="MIA",
            primary_color="#008E97",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/mia.png",
            alternate_names=("Miami",),
        ),
        TeamSnapshot(
            id=10716,
            sport_id=14,
            sport_key="baseball_mlb",
            name="Miami Marlins",
            abbreviation="MIA",
            primary_color="#00A3E0",
            logo_url_small="https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/mia.png",
            alternate_names=("Miami",),
        ),
        TeamSnapshot(
            id=58,
            sport_id=10,
            sport_key="icehockey_nhl",
            name="Carolina Hurricanes",
            abbreviation="CAR",
            primary_color="#CE1126",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/car.png",
            alternate_names=("Carolina",),
        ),
        TeamSnapshot(
            id=548,
            sport_id=13,
            sport_key="americanfootball_nfl",
            name="Carolina Panthers",
            abbreviation="CAR",
            primary_color="#0085CA",
            logo_url_small="https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/car.png",
            alternate_names=("Carolina",),
        ),
    ]
    lookup = _dedupe_team_name_lookup(teams)
    resolver = SubjectArtResolver(team_lookup=lookup)

    for bad_sk in ("basketball_nba", "americanfootball_ncaaf", "baseball_mlb"):
        art = resolver.resolve("Miami", sport_key=bad_sk, allow_team_lookup=True)
        assert art["kind"] == "monogram", (bad_sk, art)
        assert art["url"] is None, (bad_sk, art)

    nfl_miami = resolver.resolve("Miami", sport_key="americanfootball_nfl", allow_team_lookup=True)
    assert nfl_miami["url"] and "/nfl/" in nfl_miami["url"]

    nhl_carolina = resolver.resolve("Carolina", sport_key="icehockey_nhl", allow_team_lookup=True)
    assert nhl_carolina["kind"] == "monogram"
    assert nhl_carolina["url"] is None

    nhl_kings = resolver.resolve("Kings", sport_key="icehockey_nhl", allow_team_lookup=True)
    assert nhl_kings["kind"] == "monogram"
    assert nhl_kings["url"] is None

    for mlb_name in ("Giants", "Cardinals"):
        mlb_art = resolver.resolve(mlb_name, sport_key="baseball_mlb", allow_team_lookup=True)
        assert mlb_art["kind"] == "monogram", (mlb_name, mlb_art)
        assert mlb_art["url"] is None, (mlb_name, mlb_art)


@pytest.mark.asyncio
async def test_long_shots_with_extra_sports_category_does_not_emit_dropped_row_pictures_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Non-sports cards with sports extra_llm_categories (e.g. Long shots pulling a basketball prop)
    must not fire 'Public sports card ... dropped row pictures'."""
    defn = load_machinery_definition(_CANDIDATES_DIR / "machinery-long-shots.json")
    assert not _is_sports_definition(defn)
    markets = [
        {
            "id": mid,
            "name": mname,
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "odd",
            "volume": 50_000.0,
            "outcomes": [{"id": idx + 1, "name": subj, "probability": prob}],
        }
        for idx, (mid, mname, subj, prob) in enumerate(
            [
                (109435, "First contact confirmed?", "Unmapped Signal One", 0.08),
                (113504, "Bigfoot DNA verified?", "Unmapped Cryptid Two", 0.05),
                (109295, "Time travel proven?", "Unmapped Paradox Three", 0.03),
            ]
        )
    ]
    with caplog.at_level(logging.WARNING, logger="app.utils.container_machinery"):
        res = await produce_container_machinery(
            {"markets": markets, "teams": _sample_teams()},
            defn,
            now=NOW,
        )
    assert hasattr(res, "machinery_card")
    rows = res.machinery_card["rows"]
    assert len(rows) == 3
    by_mid = {int(r["market_id"]): r for r in rows}
    assert (by_mid[109435].get("art") or {}).get("url") is None
    assert (by_mid[113504].get("art") or {}).get("url") is None
    assert "image.tmdb.org" in str((by_mid[109295].get("art") or {}).get("url") or "")
    assert not any(
        "dropped row pictures" in rec.message or "missing row pictures" in rec.message
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_public_sports_card_with_hide_row_art_does_not_emit_dropped_row_pictures_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A public sports card that explicitly sets hide_row_art=True must not warn on missing row art."""
    import copy

    defn = copy.deepcopy(dict(load_machinery_definition(_CANDIDATES_DIR / "machinery-big-championships-2027.json")))
    defn["rule"] = {**dict(defn["rule"]), "hide_row_art": True}
    assert _is_sports_definition(defn)
    markets = [
        {
            "id": mid,
            "name": mname,
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "basketball",
            "volume": 50_000.0,
            "outcomes": [{"id": idx + 1, "name": subj, "probability": prob}],
        }
        for idx, (mid, mname, subj, prob) in enumerate(
            [
                (57792807, "Heisman Trophy Winner 2026", "Unmapped Prospect One", 0.42),
                (66031970, "NBA MVP 2026-27", "Unmapped Prospect Two", 0.35),
                (70732924, "UEFA Champions League 2026-27", "Unmapped Club Three", 0.28),
            ]
        )
    ]
    with caplog.at_level(logging.WARNING, logger="app.utils.container_machinery"):
        res = await produce_container_machinery(
            {"markets": markets, "teams": _sample_teams()},
            defn,
            now=NOW,
        )
    assert hasattr(res, "machinery_card")
    assert not any("dropped row pictures" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_public_sports_card_still_warns_when_row_pictures_are_expected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Genuine public sports cards where row pictures are expected still log missing-row-pictures."""
    defn = load_machinery_definition(_CANDIDATES_DIR / "machinery-big-championships-2027.json")
    assert _is_sports_definition(defn)
    markets = [
        {
            "id": mid,
            "name": mname,
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "basketball",
            "volume": 50_000.0,
            "outcomes": [{"id": idx + 1, "name": subj, "probability": prob}],
        }
        for idx, (mid, mname, subj, prob) in enumerate(
            [
                (57792807, "Heisman Trophy Winner 2026", "Unmapped Prospect One", 0.42),
                (66031970, "NBA MVP 2026-27", "Unmapped Prospect Two", 0.35),
                (70732924, "UEFA Champions League 2026-27", "Unmapped Club Three", 0.28),
            ]
        )
    ]
    with caplog.at_level(logging.WARNING, logger="app.utils.container_machinery"):
        res = await produce_container_machinery(
            {"markets": markets, "teams": _sample_teams()},
            defn,
            now=NOW,
        )
    assert hasattr(res, "machinery_card")
    assert any(
        "Public sports card machinery-big-championships-2027 has missing row pictures (initials fallback); missing art for subjects="
        in rec.message
        for rec in caplog.records
    )
