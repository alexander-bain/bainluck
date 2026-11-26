"""Tests for #12288 Item 4 row pictures and initials-in-circle fallback."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
    SubjectArtResolver,
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import clear_fun_markets_cache
from app.utils.nation_flags import flag_url

NOW = datetime(2026, 11, 22, 18, 0, tzinfo=timezone.utc)

ROW_ART_ENABLED_SLUGS = (
    "machinery-golden-globes-2027",
    "machinery-google-year-in-search-2026",
    "machinery-2026-box-office-showdown",
    "machinery-pop-culture-oddities",
    "machinery-2026-summed-up",
    "machinery-cast-delayed-cancelled",
    "machinery-stage-and-cover",
    "machinery-tv-and-gaming-2026",
    "machinery-chess-milestones-and-curiosities",
)

ROW_ART_HIDDEN_SLUGS = (
    "machinery-ai-model-leaderboard-2026",
    "machinery-big-tech-deals-hardware",
)


def test_hide_row_art_turned_off_on_person_film_show_sets_and_kept_off_tech() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    for slug in ROW_ART_ENABLED_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        assert not defn["rule"].get("hide_row_art"), f"{slug} should allow row art"
    for slug in ROW_ART_HIDDEN_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        assert defn["rule"].get("hide_row_art") is True, f"{slug} should stay hide_row_art=True"


def test_tmdb_vetted_portraits_posters_and_country_flags_resolve() -> None:
    resolver = SubjectArtResolver()
    for subject in (
        "Florence Pugh",
        "Kate O’Flynn",
        "David Harbour",
        "Beyoncé",
        "Olivia Colman",
        "Cillian Murphy",
        "Benedict Cumberbatch",
        "Sydney Sweeney",
        "Elon Musk",
        "MrBeast",
    ):
        art = resolver.resolve(subject, allow_team_lookup=False)
        assert art["url"] and "image.tmdb.org/t/p/" in art["url"], (subject, art)
        assert art["kind"] in {"person", "tmdb_headshot"}, (subject, art)

    for title in ("DTF St. Louis", "The Pitt", "Euphoria", "Avengers: Secret Wars", "Stranger Things"):
        art = resolver.resolve(title, allow_team_lookup=False)
        assert art["url"] and "image.tmdb.org/t/p/" in art["url"], (title, art)
        assert art["kind"] in {"film", "tmdb_poster"}, (title, art)

    # Erling Braut Haaland keeps the vetted Wikimedia portrait via alias.
    haaland = resolver.resolve("Erling Braut Haaland", allow_team_lookup=False)
    assert haaland["url"] and "wikimedia.org" in haaland["url"], haaland

    # Obsession (2026 film, TMDB movie 1339713) uses its clean vetted TMDB poster (#7461-safe).
    obsession = resolver.resolve("Obsession", allow_team_lookup=False)
    assert obsession["url"] == "https://image.tmdb.org/t/p/w342/bRwnj8WEKBCvmfeUNOukJPwB43K.jpg"
    assert obsession["kind"] == "film"
    assert "TMDB movie 1339713" in str(obsession.get("detail") or "")

    # Raye resolves to her TMDB portrait (3108777), not album cover art; her song still gets Cover Art Archive.
    raye = resolver.resolve("Raye", allow_team_lookup=False)
    assert raye["url"] == "https://image.tmdb.org/t/p/w185/zA5WXnyg8iH8DPpuXvsmJpPT2n1.jpg"
    assert raye["kind"] == "person"
    assert "RAYE, British singer-songwriter" in str(raye.get("detail") or "")
    raye_song = resolver.resolve("WHERE IS MY HUSBAND! - RAYE", allow_team_lookup=False)
    assert raye_song["kind"] == "song"
    assert "coverartarchive.org" in str(raye_song["url"])

    # Puka Nacua resolves to vetted ESPN headshot (4426515) for Engaged 16/16 set-page coverage.
    puka = resolver.resolve("Puka Nacua", allow_team_lookup=False)
    assert puka["url"] == "https://a.espncdn.com/i/headshots/nfl/players/full/4426515.png"
    assert puka["kind"] == "person"

    # Extreme Earth resolves to NASA PD Top_of_Atmosphere.jpg.
    earth = resolver.resolve("Extreme Earth 2026", allow_team_lookup=False)
    assert earth["url"] and "Top_of_Atmosphere.jpg" in earth["url"]

    # Country flags resolve cleanly for major international markets.
    assert flag_url("China") == "https://flagcdn.com/w160/cn.png"
    for country in ("United States", "China", "India", "Russia", "United Kingdom", "France"):
        cart = resolver.resolve(country, allow_team_lookup=False)
        assert cart["kind"] == "flag", (country, cart)
        assert cart["url"] and "flagcdn.com/w160/" in cart["url"], (country, cart)


@pytest.mark.asyncio
async def test_complete_card_keeps_pictures_while_partial_section_drops_row_pictures_all_or_nothing() -> None:
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    pop_defn = load_machinery_definition(paths_by_slug["machinery-pop-culture-oddities"])
    pop_markets = [
        {
            "id": 67804457,
            "name": '"All I Want for Christmas Is You" Dec 19 Hot 100 rank',
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 1, "name": "Rank 1 to 2", "probability": 0.45}],
        },
        {
            "id": 108306,
            "name": "Beyonce next album genre?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 2, "name": "Rock", "probability": 0.40}],
        },
        {
            "id": 109309,
            "name": "Taylor Swift announces Taylor's Version?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 4, "name": "Yes", "probability": 0.30}, {"id": 5, "name": "No", "probability": 0.70}],
        },
        {
            "id": 58903285,
            "name": "Turner Prize 2026 Winner?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 3, "name": "Simeon Barclay", "probability": 0.25}],
        },
        {
            "id": 67804475,
            "name": "NYC 2026 Michelin stars: Kabawa",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 6, "name": "Kabawa", "probability": 0.20}],
        },
        {
            "id": 108254,
            "name": "Time Person of the Decade?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "politics",
            "volume": 50000.0,
            "outcomes": [{"id": 7, "name": "Elon Musk", "probability": 0.80}],
        },
    ]
    pop_res = await produce_container_machinery({"markets": pop_markets, "teams": []}, pop_defn, now=NOW)
    assert hasattr(pop_res, "machinery_card"), pop_res
    pop_rows = pop_res.machinery_card["rows"]
    assert len(pop_rows) == 3
    # Discover card has 3/3 pictured rows (Mariah Carey, Beyoncé, Taylor Swift) -> keeps all 3.
    assert all((r.get("art") or {}).get("url") for r in pop_rows), pop_rows
    # Decision 387: A (#13605): set-page section keeps verified pictures on pictured rows
    # (Beyoncé, Taylor Swift, Elon Musk) and keeps clean monogram initials on unpictured rows.
    pop_sec_items = pop_res.sections[0]["visual_block"]["items"]
    assert len(pop_sec_items) == 6
    by_mid = {int(it["market_id"]): it for it in pop_sec_items}
    for pictured_mid in (67804457, 108306, 109309, 108254):
        assert (by_mid[pictured_mid]["outcomes"][0]["art"] or {}).get("url")
    for unpictured_mid in (58903285, 67804475):
        u_art = by_mid[unpictured_mid]["outcomes"][0]["art"]
        assert not u_art.get("url")
        assert u_art.get("kind") == "monogram"
        assert u_art.get("initials")

    # Complete section (every row pictured on card AND set page) keeps all pictures on both.
    stage_defn = load_machinery_definition(paths_by_slug["machinery-stage-and-cover"])
    stage_markets = [
        {
            "id": 62368061,
            "name": "Who will host Saturday Night Live?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 11, "name": "Florence Pugh", "probability": 0.35}],
        },
        {
            "id": 109296,
            "name": "Who will appear on Call Her Daddy?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 12, "name": "David Harbour", "probability": 0.30}],
        },
        {
            "id": 109287,
            "name": "Who will appear on Joe Rogan Experience?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 13, "name": "Olivia Colman", "probability": 0.25}],
        },
        {
            "id": 56775621,
            "name": "Vogue 2026 cover star?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 14, "name": "Cillian Murphy", "probability": 0.22}],
        },
    ]
    stage_res = await produce_container_machinery({"markets": stage_markets, "teams": []}, stage_defn, now=NOW)
    assert hasattr(stage_res, "machinery_card"), stage_res
    assert all((r.get("art") or {}).get("url") for r in stage_res.machinery_card["rows"])
    assert all(
        (it.get("outcomes") or [{}])[0].get("art", {}).get("url")
        for it in stage_res.sections[0]["visual_block"]["items"]
    )


@pytest.mark.asyncio
async def test_partial_card_and_section_keep_held_pictures_with_monogram_fallback_387a() -> None:
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}

    space_defn = load_machinery_definition(paths_by_slug["machinery-space-race"])
    space_markets = [
        {
            "id": 108300,
            "name": "Blue Origin land on the moon before SpaceX?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "tech",
            "volume": 50000.0,
            "outcomes": [{"id": 11, "name": "Yes", "probability": 0.66}, {"id": 12, "name": "No", "probability": 0.34}],
        },
        {
            "id": 108247,
            "name": "Which country will be next to land humans on the Moon?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "tech",
            "volume": 50000.0,
            "outcomes": [{"id": 13, "name": "China", "probability": 0.57}, {"id": 14, "name": "United States", "probability": 0.43}],
        },
        {
            "id": 108236,
            "name": "Humanoid robot walks on Mars before a human?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "tech",
            "volume": 50000.0,
            "outcomes": [{"id": 15, "name": "Yes", "probability": 0.49}, {"id": 16, "name": "No", "probability": 0.51}],
        },
    ]
    space_res = await produce_container_machinery({"markets": space_markets, "teams": []}, space_defn, now=NOW)
    assert hasattr(space_res, "machinery_card"), space_res
    # Decision 387: A (#13605): keep held flag on United States/China row while unpictured siblings stay monograms with initials.
    card_by_mid = {int(r["market_id"]): r for r in space_res.machinery_card["rows"]}
    assert (card_by_mid[108247]["art"] or {}).get("url")
    for unpictured_mid in (108300, 108236):
        u_art = card_by_mid[unpictured_mid]["art"]
        assert u_art.get("url") is None
        assert u_art.get("kind") == "monogram"
        assert u_art.get("initials")

    sec_by_mid = {int(it["market_id"]): it for it in space_res.sections[0]["visual_block"]["items"]}
    assert (sec_by_mid[108247]["outcomes"][0]["art"] or {}).get("url")
    for unpictured_mid in (108300, 108236):
        u_art = sec_by_mid[unpictured_mid]["outcomes"][0]["art"]
        assert u_art.get("url") is None
        assert u_art.get("kind") == "monogram"
        assert u_art.get("initials")

    engaged_defn = load_machinery_definition(paths_by_slug["machinery-who-gets-engaged"])
    engaged_markets = [
        {
            "id": 109618,
            "name": "Will Sydney Sweeney & Scooter Braun get engaged?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "culture",
            "volume": 50000.0,
            "outcomes": [{"id": 21, "name": "Yes", "probability": 0.29}, {"id": 22, "name": "No", "probability": 0.71}],
        },
        {
            "id": 109386,
            "name": "Will Megan Thee Stallion & Klay Thompson get engaged?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "culture",
            "volume": 50000.0,
            "outcomes": [{"id": 23, "name": "Yes", "probability": 0.25}, {"id": 24, "name": "No", "probability": 0.75}],
        },
        {
            "id": 109385,
            "name": "Will Timothee Chalamet & Kylie Jenner get engaged?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "culture",
            "volume": 50000.0,
            "outcomes": [{"id": 25, "name": "Yes", "probability": 0.21}, {"id": 26, "name": "No", "probability": 0.79}],
        },
    ]
    eng_res = await produce_container_machinery({"markets": engaged_markets, "teams": []}, engaged_defn, now=NOW)
    assert hasattr(eng_res, "machinery_card"), eng_res
    assert all("image.tmdb.org" in str((r.get("art") or {}).get("url") or "") for r in eng_res.machinery_card["rows"])


@pytest.mark.asyncio
async def test_taylor_swift_uses_person_portrait_elon_skips_repeat_and_date_row_uses_subject_initials() -> None:
    clear_fun_markets_cache()
    resolver = SubjectArtResolver()
    ts_person = resolver.resolve("Taylor Swift", allow_team_lookup=False)
    assert ts_person["kind"] == "person"
    assert "image.tmdb.org" in str(ts_person["url"])
    ts_song = resolver.resolve("The Fate of Ophelia - Taylor Swift", allow_team_lookup=False)
    assert ts_song["kind"] == "song"
    assert "coverartarchive.org" in str(ts_song["url"])

    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    musk_defn = load_machinery_definition(paths_by_slug["machinery-elon-musk-side-quests"])
    musk_markets = [
        {
            "id": 108218,
            "name": "Will Elon Musk visit Mars in his lifetime?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "odd",
            "volume": 50000.0,
            "outcomes": [{"id": 31, "name": "Yes", "probability": 0.14}, {"id": 32, "name": "No", "probability": 0.86}],
        },
        {
            "id": 109412,
            "name": "Will Elon Musk buy Ryanair?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "business",
            "volume": 50000.0,
            "outcomes": [{"id": 33, "name": "Yes", "probability": 0.08}, {"id": 34, "name": "No", "probability": 0.92}],
        },
        {
            "id": 109633,
            "name": "Will Elon Musk be cast in Superman?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 35, "name": "Yes", "probability": 0.05}, {"id": 36, "name": "No", "probability": 0.95}],
        },
    ]
    musk_res = await produce_container_machinery({"markets": musk_markets, "teams": []}, musk_defn, now=NOW)
    assert hasattr(musk_res, "machinery_card"), musk_res
    assert all((r.get("art") or {}).get("url") is None for r in musk_res.machinery_card["rows"])

    summed_defn = load_machinery_definition(paths_by_slug["machinery-2026-summed-up"])
    summed_markets = [
        {
            "id": 109517,
            "name": "Top Spotify artist of 2026?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 41, "name": "Bad Bunny", "probability": 0.45}],
        },
        {
            "id": 109614,
            "name": "Game of the Year 2026?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 42, "name": "Grand Theft Auto VI", "probability": 0.35}],
        },
        {
            "id": 109527,
            "name": "When will Spotify Wrapped 2026 release?",
            "status": "open",
            "source": "kalshi",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 43, "name": "Before Dec 5, 2026", "probability": 0.55}],
        },
    ]
    summed_res = await produce_container_machinery({"markets": summed_markets, "teams": []}, summed_defn, now=NOW)
    assert hasattr(summed_res, "machinery_card"), summed_res
    s_by_mid = {int(r["market_id"]): r for r in summed_res.machinery_card["rows"]}
    assert s_by_mid[109527]["art"]["initials"] not in {"DEC", "JAN", "B2"}
    assert s_by_mid[109527]["art"]["initials"] == "SR"


@pytest.mark.asyncio
async def test_item3_bond_28_contenders_and_engaged_second_partner_fallback() -> None:
    """Item 3: all 28 Bond contenders and Who Gets Engaged couples (including partner-2 fallback) resolve."""
    clear_fun_markets_cache()
    resolver = SubjectArtResolver()
    bond_28 = (
        "Raye",
        "Olivia Dean",
        "Dua Lipa",
        "Harry Styles",
        "Olivia Colman",
        "Ralph Fiennes",
        "Idris Elba",
        "Charles Dance",
        "Margaret Qualley",
        "Florence Pugh",
        "Anya Taylor-Joy",
        "Zendaya",
        "Ben Whishaw",
        "Andrew Scott",
        "Dev Patel",
        "Richard Ayoade",
        "Cillian Murphy",
        "Oscar Isaac",
        "Barry Keoghan",
        "Adam Driver",
        "Naomie Harris",
        "Jodie Turner-Smith",
        "Phoebe Dynevor",
        "Jodie Comer",
        "Boyd Holbrook",
        "Anthony Mackie",
        "Steven Yeun",
        "Chiwetel Ejiofor",
    )
    for person in bond_28:
        art = resolver.resolve(person, allow_team_lookup=False)
        assert art["url"], f"Missing vetted portrait/cover for Bond contender {person!r}: {art}"

    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    engaged_defn = load_machinery_definition(paths_by_slug["machinery-who-gets-engaged"])
    engaged_markets = [
        {
            "id": 109618,
            "name": "Will Sydney Sweeney & Scooter Braun get engaged?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "entertainment",
            "volume": 50000.0,
            "outcomes": [{"id": 21, "name": "Yes", "probability": 0.45}, {"id": 22, "name": "No", "probability": 0.55}],
        },
        {
            "id": 991001,
            "name": "Will Livvy Dunne & Paul Skenes get engaged in 2026?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "culture",
            "volume": 50000.0,
            "outcomes": [{"id": 23, "name": "Yes", "probability": 0.35}, {"id": 24, "name": "No", "probability": 0.65}],
        },
        {
            "id": 991002,
            "name": "Will Puka Nacua & Sara Saffari get engaged in 2026?",
            "status": "open",
            "source": "polymarket",
            "llm_sport_category": "culture",
            "volume": 50000.0,
            "outcomes": [{"id": 25, "name": "Yes", "probability": 0.25}, {"id": 26, "name": "No", "probability": 0.75}],
        },
    ]
    res = await produce_container_machinery({"markets": engaged_markets, "teams": []}, engaged_defn, now=NOW)
    assert hasattr(res, "machinery_card"), res
    urls = [(r.get("art") or {}).get("url") for r in res.machinery_card["rows"]]
    assert len(urls) == 3 and all(urls), urls
    sec_urls = [
        (it.get("outcomes") or [{}])[0].get("art", {}).get("url")
        for it in res.sections[0]["visual_block"]["items"]
    ]
    assert len(sec_urls) == 3 and all(sec_urls), sec_urls


def test_every_tmdb_person_entry_records_positive_tmdb_person_id() -> None:
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    b_text = (root / "backend/data/discover/verified_discover_art.json").read_text(encoding="utf-8")
    doc = json.loads(b_text)
    tmdb_people = [
        e for e in doc["entries"]
        if e.get("kind") == "person" and "image.tmdb.org" in str(e.get("url") or "")
    ]
    assert len(tmdb_people) >= 86
    for e in tmdb_people:
        pid = e.get("tmdb_person_id")
        assert isinstance(pid, int) and not isinstance(pid, bool) and pid > 0, (
            f"Missing/invalid tmdb_person_id on {e['entity_key']}: {pid!r}"
        )


def test_nfl_2026_mvp_portraits_and_jaxson_spelling_alias_resolve() -> None:
    resolver = SubjectArtResolver()
    expected = {
        "Joe Burrow": "https://a.espncdn.com/i/headshots/nfl/players/full/3915511.png",
        "Brock Purdy": "https://a.espncdn.com/i/headshots/nfl/players/full/4361741.png",
        "Patrick Mahomes": "https://a.espncdn.com/i/headshots/nfl/players/full/3139477.png",
        "Josh Allen": "https://a.espncdn.com/i/headshots/nfl/players/full/3918298.png",
        "Trevor Lawrence": "https://a.espncdn.com/i/headshots/nfl/players/full/4360310.png",
        "Jaxson Smith-Njigba": "https://a.espncdn.com/i/headshots/nfl/players/full/4430878.png",
        "Jaxon Smith-Njigba": "https://a.espncdn.com/i/headshots/nfl/players/full/4430878.png",
        "Caleb Williams": "https://a.espncdn.com/i/headshots/nfl/players/full/4431611.png",
        "Justin Herbert": "https://a.espncdn.com/i/headshots/nfl/players/full/4038941.png",
    }
    for name, url in expected.items():
        art = resolver.resolve(name, allow_team_lookup=False)
        assert art["url"] == url, (name, art)
        assert art["kind"] == "person", (name, art)


@pytest.mark.asyncio
async def test_nfl_week_2026_mvp_section_draws_all_portraits() -> None:
    import copy
    from tests.test_container_machinery_slice1_12288 import FIXED_NOW, _sample_snapshot

    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    nfl_defn = load_machinery_definition(paths_by_slug["machinery-nfl-week"])
    snapshot = copy.deepcopy(_sample_snapshot())
    for m in snapshot["markets"]:
        if m.get("id") == 40532:
            m["id"] = 7585490
            m["name"] = "Pro Football: 2026 MVP Winner"
            m["llm_sport_category"] = "football"
            m["top_outcomes"] = [
                {"id": 1, "name": "Joe Burrow", "probability": 0.49},
                {"id": 2, "name": "Brock Purdy", "probability": 0.28},
                {"id": 3, "name": "Patrick Mahomes", "probability": 0.08},
                {"id": 4, "name": "Josh Allen", "probability": 0.07},
                {"id": 5, "name": "Trevor Lawrence", "probability": 0.03},
                {"id": 6, "name": "Jaxson Smith-Njigba", "probability": 0.02},
            ]
            break

    res = await produce_container_machinery(snapshot, nfl_defn, now=FIXED_NOW)
    assert hasattr(res, "sections"), res
    mvp_sec = next(s for s in res.sections if s.get("class") == "mvp_race")
    outs = mvp_sec["visual_block"]["items"][0]["outcomes"]
    assert len(outs) == 6
    assert all((o.get("art") or {}).get("url") for o in outs), outs
