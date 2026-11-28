"""Tests for #12288 Batch 8 fun groupings + 350: A Fable review fixes."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
    SubjectArtResolver,
    _build_team_lookup_from_entries,
    _compute_member_number_parity,
    build_container_machinery_producer,
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import clear_fun_markets_cache
from app.utils.discover_opening_mix import (
    TOPIC_ENTERTAINMENT,
    TOPIC_ODD,
    TOPIC_SPORTS,
    TOPIC_TECH_BUSINESS,
    classify_discover_opening_topic,
)
from app.utils.roundup_containers import (
    _roundup_lesser_soccer_penalty,
    compose_roundup_container,
    compose_roundup_feed_item,
)

BATCH8_SLUGS: tuple[str, ...] = (
    "machinery-earth-quakes-and-storms-2026",
    "machinery-chess-milestones-and-curiosities",
    "machinery-climate-water-and-energy",
    "machinery-music-and-grammys-2026",
    "machinery-tv-and-gaming-2026",
    "machinery-soccer-cups-and-relegation",
    "machinery-nfl-conference-and-division-races",
    "machinery-ai-math-and-data-centers",
)
NOW = datetime(2026, 11, 23, 5, 0, tzinfo=timezone.utc)


def _sample_batch8_teams() -> list[dict]:
    def _t(
        tid: int,
        name: str,
        abbr: str,
        sk: str,
        logo: str | None,
        alts: list[str] | None = None,
    ) -> dict:
        return {
            "id": tid,
            "sport_id": abs(hash(sk)) % 10_000,
            "sport_key": sk,
            "name": name,
            "slug": name.lower().replace(" ", "-"),
            "abbreviation": abbr,
            "primary_color": "#1E293B",
            "secondary_color": "#FFFFFF",
            "logo_url_small": logo,
            "logo_url_large": logo,
            "alternate_names": alts or [name],
            "espn_id": str(tid),
        }

    return [
        # Decoy clubs across other leagues to ensure strict league scoping
        _t(101, "FC Cincinnati", "CIN", "soccer_usa_mls", "https://a.espncdn.com/i/teamlogos/soccer/500/18267.png", ["Cincinnati", "FC Cincinnati"]),
        _t(102, "Baltimore Orioles", "BAL", "baseball_mlb", "https://a.espncdn.com/i/teamlogos/mlb/500/scoreboard/bal.png", ["Baltimore"]),
        _t(103, "Buffalo Bulls", "UB", "americanfootball_ncaaf", "https://a.espncdn.com/i/teamlogos/ncaa/500/2084.png", ["Buffalo"]),
        _t(104, "Green Bay Phoenix", "GB", "basketball_ncaab", "https://a.espncdn.com/i/teamlogos/ncaa/500/2739.png", ["Green Bay"]),
        _t(105, "LA Clippers", "LAC", "basketball_nba", "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/lac.png", ["Los Angeles C"]),
        _t(106, "Carolina Hurricanes", "CAR", "icehockey_nhl", "https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/car.png", ["Carolina"]),
        _t(107, "New England Revolution", "NE", "soccer_usa_mls", "https://a.espncdn.com/i/teamlogos/soccer/500/189.png", ["New England"]),
        # All 32 canonical NFL clubs
        _t(201, "Arizona Cardinals", "ARI", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/ari.png", ["Arizona"]),
        _t(202, "Atlanta Falcons", "ATL", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/atl.png", ["Atlanta"]),
        _t(203, "Baltimore Ravens", "BAL", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/bal.png", ["Baltimore"]),
        _t(204, "Buffalo Bills", "BUF", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/buf.png", ["Buffalo"]),
        _t(205, "Carolina Panthers", "CAR", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/car.png", ["Carolina"]),
        _t(206, "Chicago Bears", "CHI", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/chi.png", ["Chicago"]),
        _t(207, "Cincinnati Bengals", "CIN", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/cin.png", ["Cincinnati"]),
        _t(208, "Cleveland Browns", "CLE", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/cle.png", ["Cleveland"]),
        _t(209, "Dallas Cowboys", "DAL", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/dal.png", ["Dallas"]),
        _t(210, "Denver Broncos", "DEN", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/den.png", ["Denver"]),
        _t(211, "Detroit Lions", "DET", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/det.png", ["Detroit"]),
        _t(212, "Green Bay Packers", "GB", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/gb.png", ["Green Bay"]),
        _t(213, "Houston Texans", "HOU", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/hou.png", ["Houston"]),
        _t(214, "Indianapolis Colts", "IND", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/ind.png", ["Indianapolis"]),
        _t(215, "Jacksonville Jaguars", "JAX", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/jax.png", ["Jacksonville"]),
        _t(216, "Kansas City Chiefs", "KC", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/kc.png", ["Kansas City"]),
        _t(217, "Las Vegas Raiders", "LV", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/lv.png", ["Las Vegas"]),
        _t(218, "Los Angeles Chargers", "LAC", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/lac.png", ["LA Chargers"]),
        _t(219, "Los Angeles Rams", "LAR", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/lar.png", ["LA Rams"]),
        _t(220, "Miami Dolphins", "MIA", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/mia.png", ["Miami"]),
        _t(221, "Minnesota Vikings", "MIN", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/min.png", ["Minnesota"]),
        _t(222, "New England Patriots", "NE", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/ne.png", ["New England"]),
        _t(223, "New Orleans Saints", "NO", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/no.png", ["New Orleans"]),
        _t(224, "New York Giants", "NYG", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/nyg.png", ["NY Giants"]),
        _t(225, "New York Jets", "NYJ", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/nyj.png", ["NY Jets"]),
        _t(226, "Philadelphia Eagles", "PHI", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/phi.png", ["Philadelphia"]),
        _t(227, "Pittsburgh Steelers", "PIT", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/pit.png", ["Pittsburgh"]),
        _t(228, "San Francisco 49ers", "SF", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/sf.png", ["San Francisco"]),
        _t(229, "Seattle Seahawks", "SEA", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/sea.png", ["Seattle"]),
        _t(230, "Tampa Bay Buccaneers", "TB", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/tb.png", ["Tampa Bay"]),
        _t(231, "Tennessee Titans", "TEN", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/ten.png", ["Tennessee"]),
        _t(232, "Washington Commanders", "WSH", "americanfootball_nfl", "https://a.espncdn.com/i/teamlogos/nfl/500/wsh.png", ["Washington"]),
        # Soccer clubs (including cross-league crest borrowing for Benfica)
        _t(301, "Coventry City", "COV", "soccer_epl", "https://a.espncdn.com/i/teamlogos/soccer/500/388.png", ["Coventry", "Coventry City"]),
        _t(302, "Guadalajara", "GDL", "soccer_mexico_ligamx", "https://a.espncdn.com/i/teamlogos/soccer/500/219.png", ["Guadalajara", "Chivas"]),
        _t(303, "Vancouver Whitecaps FC", "VAN", "soccer_usa_mls", "https://a.espncdn.com/i/teamlogos/soccer/500/9727.png", ["Vancouver Whitecaps"]),
        _t(304, "Benfica", "BEN", "soccer_uefa_champs_league", "https://a.espncdn.com/i/teamlogos/soccer/500/1929.png", ["Benfica"]),
        _t(305, "Benfica", "BEN", "soccer_uefa_europa_league", None, ["Benfica"]),
        _t(306, "Inter Miami CF", "MIA", "soccer_usa_mls", "https://a.espncdn.com/i/teamlogos/soccer/500/20232.png", ["Miami"]),
        _t(307, "Inter Miami CF", "MIA", "soccer_concacaf_leagues_cup", None, ["Inter Miami CF"]),
    ]


def _sample_batch8_markets() -> list[dict]:
    now_iso = datetime(2026, 11, 23, 4, 30, tzinfo=timezone.utc).isoformat()
    specs = [
        # 1. Earth, Quakes & Storms (ODD)
        (113358, "Where will 2026 rank among the hottest years on record?", "weather", [("1", 0.938), ("2", 0.052)], None),
        (114134, "How many 7.0 or above earthquakes in 2026?", "weather", [("14–16", 0.745), ("17–19", 0.195)], None),
        (114137, "How many large volcano eruptions (VEI >=4) in 2026?", "weather", [("1", 0.550), ("0", 0.400)], None),
        (58435808, "How many tropical cyclones will make landfall in China during 2026?", "weather", [("8", 0.735), ("Greater than 8", 0.140)], None),
        (1234182, "How many Tornadoes in the US in 2026?", "weather", [("1250+", 0.920), ("1200–1249", 0.067)], None),
        (59129330, "What will the peak RONI be for the 2026–27 El Nino?", "weather", [("Over 2.5", 0.635), ("2.25–2.5", 0.330)], None),
        # 2. World Chess & Grandmaster Races (ODD, 100% chess)
        (221, "FIDE World Chess Championship 2026 Winner", "chess", [("Javokhir Sindarov", 0.765), ("Gukesh Dommaraju", 0.245)], None),
        (59165041, "Chess.com Player of the Year Winner", "chess", [("Javokhir Sindarov", 0.715), ("Magnus Carlsen", 0.100)], None),
        (70160273, "FIDE Standard Top Women Chess Players: #2 Rated in January 2027", "chess", [("Zhu Jiner", 0.630), ("Ju Wenjun", 0.190)], None),
        (59165040, "Chess.com Woman Player of the Year Winner", "chess", [("Bibisara Assaubayeva", 0.305), ("Vaishali Rameshbabu", 0.185)], None),
        (70160279, "FIDE Blitz Top Chess Players: #2 Rated in January 2027", "chess", [("Hikaru Nakamura", 0.275), ("Arjun Erigaisi", 0.210)], None),
        (62368048, "Will an LLM beat a grandmaster in chess?", "tech", [("Before 2030", 0.730), ("Before 2029", 0.650), ("Before 2028", 0.400), ("Before 2027", 0.015)], None),
        # 3. Water, Rain & Climate Shifts (ODD)
        (65521875, "How much will it rain in Napa in November 2026 through March 2027?", "weather", [("Above 10 inches", 0.875), ("Above 15 inches", 0.790)], None),
        (63828305, "Melbourne's wettest month of 2026?", "weather", [("October", 0.905), ("December", 0.048)], None),
        (61980420, "Lowest Mississippi level at Baton Rouge by November 30?", "weather", [("5.00 to 5.99 ft", 0.230), ("3.00 to 3.99 ft", 0.022)], None),
        (108250, "What will be the largest source of global primary energy consumption in 2030?", "weather", [("Oil", 0.650), ("Coal", 0.135)], None),
        (108248, "US meets its climate goals?", "weather", [("By 2030", 0.181), ("By 2025", 0.038)], None),
        # 4. Grammys & Chart Leaders (ENTERTAINMENT)
        (52755801, "Grammy Winner: Album of the Year", "entertainment", [("Lux", 0.515), ("you seem pretty sad", 0.310)], None),
        (56775571, "Grammy Winner: Best New Artist", "entertainment", [("Ella Langley", 0.745), ("SIENNA SPIRO", 0.200)], None),
        (62368119, "Grammy Winner: Best Contemporary Country Album", "entertainment", [("Dandelion", 0.890), ("Middle of Nowhere", 0.065)], None),
        (58492244, "Grammys 2027: Best Rap Album Winner", "entertainment", [("Octane - Don Toliver", 0.405), ("Dillagence II", 0.182)], None),
        (114301, "Billboard #1 Artist 2026", "entertainment", [("Morgan Wallen", 0.690), ("Kendrick Lamar", 0.069)], None),
        (109508, "Top Song on Spotify in 2026?", "entertainment", [("End of Beginning", 0.865), ("Babydoll", 0.095)], None),
        (57576624, "#2 US Spotify Song 2026", "entertainment", [("Man I Need – Olivia Dean", 0.794), ("Earrings – Malcom Todd", 0.202)], None),
        (52755612, "Top U.S. Selling Vinyl Album: 2026", "entertainment", [("ARIRANG", 0.420), ("you seem pretty sad", 0.320)], None),
        (109520, "Top Album on Spotify U.S in 2026?", "entertainment", [("I’m The Problem", 0.725), ("DeBI TiRAR MaS FOToS", 0.105)], None),
        # 5. TV & Late Night Races (ENTERTAINMENT, 100% TV)
        (65536362, "Critics Choice Awards: Best Actor in a Comedy Series", "entertainment", [("Matthew Rhys", 0.830), ("Jeremy Allen White", 0.040)], None),
        (70160350, "Who will win The Voice Season 30?", "entertainment", [("Joey Henley", 0.555), ("Mia Knight", 0.115)], None),
        (60481087, "Dancing with the Stars Season 35 Winner", "entertainment", [("Ezra Frech", 0.475), ("Amber Glenn", 0.280)], None),
        (108480, "SNL: Lorne Michaels' successor for showrunner", "entertainment", [("Tina Fey", 0.390), ("Steve Higgins", 0.355)], None),
        (109441, "Which companies will release a Fully AI-generated multi-episode scripted series before 2027?", "entertainment", [("Amazon", 0.050), ("Netflix", 0.045)], None),
        # 6. Global Soccer Races (SPORTS)
        (59156925, "LaLiga: Top Goalscorer 2026-27", "soccer", [("Kylian Mbappé", 0.515), ("Raphinha", 0.334), ("Lamine Yamal", 0.061)], None),
        (59516509, "Premier League: Teams relegated (2026-27)", "soccer", [("Coventry City", 0.500), ("Crystal Palace", 0.490)], "EPL"),
        (55674269, "Liga MX Apertura Champion", "soccer", [("Guadalajara", 0.310), ("Cruz Azul", 0.215)], "LIGA_MX"),
        (128718, "MLS Cup Winner 2026", "soccer", [("Vancouver Whitecaps FC", 0.252), ("Inter Miami CF", 0.080)], "MLS"),
        (70732925, "UEFA Europa League: 2027 Champion", "soccer", [("Benfica", 0.180), ("Bournemouth", 0.146)], "EUROPA"),
        (56775477, "2030 FIFA World Cup Champion", "soccer", [("Spain", 0.164), ("France", 0.133)], "FIFA_WC"),
        # 7. NFL Division & Seed Races (SPORTS)
        (129171, "Pro Football: 2027 NFC Champion", "football", [("San Francisco 49ers", 0.375), ("Chicago Bears", 0.180)], None),
        (129172, "Pro Football: 2027 AFC Champion", "football", [("Buffalo Bills", 0.280), ("Cincinnati Bengals", 0.184)], None),
        (2248395, "Pro Football: NFC East Champion", "football", [("New York Giants", 0.690), ("Dallas Cowboys", 0.155)], "NFL"),
        (53677, "AFC North Division Winner", "football", [("Cincinnati", 0.875), ("Cleveland", 0.075)], "NFL"),
        (53676, "AFC South Division Winner", "football", [("Jacksonville", 0.925), ("Houston", 0.085)], "NFL"),
        (52755859, "Pro Football: NFC #1 Seed", "football", [("San Francisco", 0.680), ("Chicago", 0.165)], None),
        (52755860, "Pro Football: AFC #1 Seed", "football", [("Buffalo", 0.450), ("Denver", 0.225)], None),
        # 8. AI Math & Data Centers (TECH)
        (60626097, "Which Millennium Prize Problem will AI solve next?", "tech", [("Riemann Hypothesis", 0.763), ("Yang-Mills", 0.046)], None),
        (60518652, "AI lab announces another Millennium Prize solution by...?", "tech", [("December 31, 2027", 0.934), ("December 31, 2026", 0.705), ("September 30, 2026", 0.000)], None),
        (60607593, "How many more Millennium Prize Problems will AI solve in 2026?", "tech", [("1", 0.595), ("0", 0.280)], None),
        (70732962, "Will any state enact a data center moratorium by December 31?", "tech", [("Yes", 0.246), ("No", 0.754)], None),
        (109305, "What kind of device will Jony Ive and OpenAI announce?", "tech", [("Necklace", 0.090), ("Glasses", 0.060)], None),
        (2415248, "When will any company achieve AGI?", "tech", [("Before Jan 1, 2031", 0.755), ("Before Apr 1, 2027", 0.105), ("Before Jan 1, 2027", 0.045)], None),
        (63267956, "Louisiana enacts data center moratorium by...?", "tech", [("December 31, 2028", 0.350), ("December 31, 2026", 0.029)], None),
        (63263361, "Texas enacts data center moratorium by...?", "tech", [("December 31, 2028", 0.335), ("December 31, 2026", 0.020)], None),
        (63267959, "Indiana enacts data center moratorium by...?", "tech", [("December 31, 2028", 0.305), ("December 31, 2026", 0.016)], None),
        (20571305, "AI data center in space by...?", "tech", [("December 31, 2027", 0.200), ("December 31, 2026", 0.009)], None),
    ]
    return [
        {
            "id": mid,
            "name": name,
            "title": name,
            "status": "open",
            "source": "polymarket",
            "category": cat,
            "llm_sport_category": cat,
            "llm_league": lg,
            "volume": 50_000.0,
            "resolution_date": "2027-02-01T00:00:00+00:00",
            "newest_outcome_updated_at": now_iso,
            "outcomes": [
                {"id": mid * 10 + i + 1, "name": oname, "probability": prob, "last_updated": now_iso}
                for i, (oname, prob) in enumerate(outs)
            ],
        }
        for mid, name, cat, outs, lg in specs
    ]


@pytest.mark.asyncio
async def test_batch8_eight_public_groupings_build_and_hit_mix(caplog: pytest.LogCaptureFixture) -> None:
    clear_fun_markets_cache()
    caplog.set_level(logging.WARNING)
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    assert set(BATCH8_SLUGS) <= set(paths_by_slug)

    db = {
        "events": [],
        "markets": _sample_batch8_markets(),
        "teams": _sample_batch8_teams(),
        "paired_sets": {},
        "market_histories": {},
    }

    expected_topics = {
        "machinery-earth-quakes-and-storms-2026": TOPIC_ODD,
        "machinery-chess-milestones-and-curiosities": TOPIC_ODD,
        "machinery-climate-water-and-energy": TOPIC_ODD,
        "machinery-music-and-grammys-2026": TOPIC_ENTERTAINMENT,
        "machinery-tv-and-gaming-2026": TOPIC_ENTERTAINMENT,
        "machinery-soccer-cups-and-relegation": TOPIC_SPORTS,
        "machinery-nfl-conference-and-division-races": TOPIC_SPORTS,
        "machinery-ai-math-and-data-centers": TOPIC_TECH_BUSINESS,
    }

    seen_headlines: set[str] = set()
    by_slug = {}
    for slug in BATCH8_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        assert defn.get("stage") == "public", slug
        prod = build_container_machinery_producer(defn)
        assert prod.stage == "public", slug
        res = await produce_container_machinery(db, defn, now=NOW)
        assert hasattr(res, "machinery_card"), (slug, res)
        mc = res.machinery_card
        assert mc["stage"] == "public"
        assert mc["title"] and "{answer}" not in mc["title"] and "{rank}" not in mc["title"], (slug, mc["title"])
        assert "by by " not in mc["title"], (slug, mc["title"])
        assert mc["title"] not in seen_headlines, f"Duplicate headline: {mc['title']}"
        seen_headlines.add(mc["title"])
        assert len(mc["rows"]) == 3, (slug, mc["rows"])

        fi = compose_roundup_feed_item(prod, res)
        cp = compose_roundup_container(prod, res)
        c_p, p_p = _compute_member_number_parity(fi, cp)
        assert c_p["passes"] is True and p_p["passes"] is True, (slug, c_p, p_p)
        assert classify_discover_opening_topic(fi) == expected_topics[slug], slug
        by_slug[slug] = (fi, cp, mc)

    assert not any(
        "missing art for subjects=" in rec.message or "dropped row pictures" in rec.message
        for rec in caplog.records
    )

    # 1. NFL Division & Seed Races: Bengals crest (not FC Cincinnati), all 32 city-only names scoped to NFL
    nfl_card = by_slug["machinery-nfl-conference-and-division-races"][2]
    cin_row = next(r for r in nfl_card["rows"] if int(r["market_id"]) == 53677)
    assert cin_row["art"]["url"] == "https://a.espncdn.com/i/teamlogos/nfl/500/cin.png"

    lookup = _build_team_lookup_from_entries(_sample_batch8_teams())
    resolver = SubjectArtResolver(team_lookup=lookup)
    for city_name in (
        "Arizona", "Atlanta", "Baltimore", "Buffalo", "Carolina", "Chicago",
        "Cincinnati", "Cleveland", "Dallas", "Denver", "Detroit", "Green Bay",
        "Houston", "Indianapolis", "Jacksonville", "Kansas City", "Las Vegas",
        "Los Angeles C", "Los Angeles R", "Miami", "Minnesota", "New England",
        "New Orleans", "New York G", "New York J", "Philadelphia", "Pittsburgh",
        "San Francisco", "Seattle", "Tampa Bay", "Tennessee", "Washington",
    ):
        art = resolver.resolve(city_name, sport_key="americanfootball_nfl", allow_team_lookup=True)
        assert art["url"] and "/nfl/" in art["url"], (city_name, art)

    # 2. AI Math & Data Centers: readable labels, "another" kept, nearest open date selected
    ai_card, ai_page = by_slug["machinery-ai-math-and-data-centers"][2], by_slug["machinery-ai-math-and-data-centers"][1]
    assert "another AI Millennium" in ai_card["title"]
    ai_items = {int(it["market_id"]): it for it in ai_page["sections"][0]["visual_block"]["items"]}
    assert ai_items[60518652]["title"] == "AI solves another Millennium Prize by Dec 31, 2026"
    assert ai_items[60518652]["outcomes"][0]["rendered_percent"] == 71
    assert ai_items[2415248]["title"] == "Any lab announces AGI before Jan 1, 2027"
    assert ai_items[2415248]["outcomes"][0]["rendered_percent"] == 5

    # 3. World Chess: 100% chess markets (no Rock Hall or wedding dress), 3/3 card faces & 5/5 GM section faces
    chess_fi, chess_page, chess_card = by_slug["machinery-chess-milestones-and-curiosities"]
    chess_ids = {
        int(m["id"])
        for sec in chess_page["sections"]
        for m in (sec.get("members") or ())
    }
    assert chess_ids == {221, 59165041, 70160273, 59165040, 70160279, 62368048}
    assert len(chess_card["rows"]) == 3
    for r in chess_card["rows"]:
        assert "wikimedia.org" in str((r.get("art") or {}).get("url") or ""), r
    chess_gm_items = (chess_page["sections"][0].get("visual_block") or {}).get("items") or ()
    assert len(chess_gm_items) == 5
    for it in chess_gm_items:
        assert "wikimedia.org" in str((it["outcomes"][0].get("art") or {}).get("url") or ""), it

    # 4. TV & Late Night Races: leads with TV, zero GTA VI or esports, TV shoot image, 3/3 card & Section 1 faces
    tv_fi, tv_page, tv_card = by_slug["machinery-tv-and-gaming-2026"]
    assert tv_card["title"].startswith("Matthew Rhys winning Critics Choice Comedy Series Actor")
    assert "Stand_In_%28Unsplash%29.jpg" in str(tv_card.get("image_url") or "")
    assert len(tv_card["rows"]) == 3
    for r in tv_card["rows"]:
        assert "wikimedia.org" in str((r.get("art") or {}).get("url") or ""), r
    tv_sec1_items = (tv_page["sections"][0].get("visual_block") or {}).get("items") or ()
    assert len(tv_sec1_items) == 3
    for it in tv_sec1_items:
        assert "wikimedia.org" in str((it["outcomes"][0].get("art") or {}).get("url") or ""), it
    tv_ids = {
        int(m["id"])
        for sec in tv_page["sections"]
        for m in (sec.get("members") or ())
    }
    assert {65536362, 60481087, 108480, 70160350, 109441} <= tv_ids
    assert not ({60473244, 63336233, 71176017, 69096405} & tv_ids)

    # 5. Global Soccer Races: portrait on Mbappe + crests on Coventry & Guadalajara, Benfica fallback, 0 lesser penalty
    soc_fi, soc_page, soc_card = by_slug["machinery-soccer-cups-and-relegation"]
    assert soc_card["title"]
    assert _roundup_lesser_soccer_penalty(soc_fi) == 0
    for r in soc_card["rows"]:
        assert (r.get("art") or {}).get("url"), r
    soc_row0 = soc_card["rows"][0]
    assert "Mbapp" in soc_row0["name"] and "wikimedia.org" in soc_row0["art"]["url"]
    soc_items = {int(it["market_id"]): it for it in soc_page["sections"][0]["visual_block"]["items"]}
    assert "1929.png" in str(soc_items[70732925]["outcomes"][0]["art"]["url"])


def test_batch8_market_ids_disjoint_from_earlier_batches() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "data" / "groupings"
    earlier_ids: set[int] = set()
    for fname in (
        "batch3_curated_sets.json",
        "batch4_curated_sets.json",
        "batch5_curated_sets.json",
        "batch6_curated_sets.json",
        "batch7_curated_sets.json",
    ):
        doc = json.loads((root / fname).read_text(encoding="utf-8"))
        for s in (doc.get("sets") or {}).values():
            for e in s.get("entries") or ():
                earlier_ids.add(int(e["id"]))

    b8 = json.loads((root / "batch8_curated_sets.json").read_text(encoding="utf-8"))
    b8_ids = [
        int(e["id"])
        for s in (b8.get("sets") or {}).values()
        for e in s.get("entries") or ()
    ]
    assert len(b8_ids) == len(set(b8_ids)), "Duplicate market id inside batch8_curated_sets.json"
    overlap = set(b8_ids) & earlier_ids
    assert not overlap, f"Batch 8 overlaps earlier curated sets: {sorted(overlap)}"


@pytest.mark.asyncio
async def test_afc_west_duel_carolina_under_nfc_south_resolves_nfl_panthers_crest() -> None:
    """348:B / 350:A: NFC South 'Carolina' on AFC West Duel resolves Panthers (NFL), never Hurricanes (NHL)."""
    clear_fun_markets_cache()
    snap = {
        "events": [],
        "markets": [
            {
                "id": 53675,
                "name": "AFC West Division Winner",
                "status": "open",
                "source": "kalshi",
                "category": "football",
                "sport": None,
                "llm_sport_category": "NFL",
                "outcomes": [
                    {"id": 536751, "name": "Denver", "probability": 0.56},
                    {"id": 536752, "name": "Kansas City", "probability": 0.42},
                    {"id": 536753, "name": "Las Vegas", "probability": 0.02},
                ],
                "volume": 500_000,
                "lifetime_volume": 500_000,
            },
            {
                "id": 53672,
                "name": "NFC South Division Winner",
                "status": "open",
                "source": "kalshi",
                "category": "football",
                "sport": None,
                "llm_sport_category": "NFL",
                "outcomes": [
                    {"id": 846579, "name": "Carolina", "probability": 0.57},
                    {"id": 846580, "name": "Tampa Bay", "probability": 0.30},
                    {"id": 846581, "name": "Atlanta", "probability": 0.13},
                ],
                "volume": 250_000,
                "lifetime_volume": 250_000,
            },
            {
                "id": 53673,
                "name": "NFC North Division Winner",
                "status": "open",
                "source": "kalshi",
                "category": "football",
                "sport": None,
                "llm_sport_category": "NFL",
                "outcomes": [
                    {"id": 536731, "name": "Green Bay", "probability": 0.65},
                    {"id": 536732, "name": "Detroit", "probability": 0.25},
                    {"id": 536733, "name": "Chicago", "probability": 0.10},
                ],
                "volume": 250_000,
                "lifetime_volume": 250_000,
            },
            {
                "id": 53671,
                "name": "NFC West Division Winner",
                "status": "open",
                "source": "kalshi",
                "category": "football",
                "sport": None,
                "llm_sport_category": "NFL",
                "outcomes": [
                    {"id": 536711, "name": "Seattle", "probability": 0.72},
                    {"id": 536712, "name": "Los Angeles R", "probability": 0.20},
                    {"id": 536713, "name": "San Francisco", "probability": 0.08},
                ],
                "volume": 250_000,
                "lifetime_volume": 250_000,
            },
        ],
        "teams": _sample_batch8_teams(),
    }
    from pathlib import Path

    defn_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "groupings"
        / "candidates"
        / "machinery-afc-west-duel.json"
    )
    defn = load_machinery_definition(defn_path)
    prod = build_container_machinery_producer(defn)
    res = await produce_container_machinery(snap, defn, now=NOW)
    page = compose_roundup_container(prod, res)
    carolina_arts = [
        o.get("art")
        for sec in page["sections"]
        for it in ((sec.get("visual_block") or {}).get("items") or ())
        for o in (it.get("outcomes") or ())
        if str(o.get("name") or "") == "Carolina"
    ]
    assert carolina_arts
    assert all(a["url"] == "https://a.espncdn.com/i/teamlogos/nfl/500/car.png" for a in carolina_arts)


@pytest.mark.asyncio
async def test_climate_melbourne_headline_keeps_full_october() -> None:
    """Item 5: standalone month answer stays 'October' in Melbourne headline, never 'Oct'."""
    from pathlib import Path

    clear_fun_markets_cache()
    defn_path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "groupings"
        / "candidates"
        / "machinery-climate-water-and-energy.json"
    )
    defn = load_machinery_definition(defn_path)
    snap = {
        "events": [],
        "teams": [],
        "markets": [
            {
                "id": 63828305,
                "name": "Melbourne's wettest month of 2026?",
                "status": "open",
                "source": "polymarket",
                "llm_sport_category": "weather",
                "volume": 25_000,
                "lifetime_volume": 25_000,
                "outcomes": [
                    {"id": 638283051, "name": "October", "probability": 0.91},
                    {"id": 638283052, "name": "December", "probability": 0.05},
                ],
            },
            {
                "id": 65521875,
                "name": "Napa seasonal rainfall by March",
                "status": "open",
                "source": "kalshi",
                "llm_sport_category": "weather",
                "volume": 25_000,
                "lifetime_volume": 25_000,
                "outcomes": [
                    {"id": 655218751, "name": "Above 10 inches", "probability": 0.87},
                    {"id": 655218752, "name": "8 to 10 inches", "probability": 0.13},
                ],
            },
            {
                "id": 61980420,
                "name": "Lowest Mississippi gauge level at Baton Rouge",
                "status": "open",
                "source": "kalshi",
                "llm_sport_category": "weather",
                "volume": 25_000,
                "lifetime_volume": 25_000,
                "outcomes": [
                    {"id": 619804201, "name": "6.00 ft or more", "probability": 0.66},
                    {"id": 619804202, "name": "4.00 to 5.99 ft", "probability": 0.34},
                ],
            },
        ],
    }
    res = await produce_container_machinery(snap, defn, now=NOW)
    title = str(res.machinery_card["title"])
    assert "October" in title, title
    assert not title.startswith("Oct "), title
