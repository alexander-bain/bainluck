"""Batch 5 public sets (#12288, Fable Item 3 / Sat Nov 21; public under Decision 336: A Sun Nov 22):

1. `machinery-march-madness-2027` — March Madness 2027 (10 rows, public, NCAA crests via `teams`)
2. `machinery-ai-model-leaderboard-2026` — The 2026 AI Model Leaderboard (7 rows, public, tech)
3. `machinery-big-tech-deals-hardware` — Big Tech Deals & Hardware (8 rows, public, tech/business)
4. `machinery-nhl-100-point-club` — The NHL 100-Point Club (7 rows, public, ESPN NHL headshots)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
    _SUBJECT_ART_PATH,
    _compute_member_number_parity,
    _effective_market_volume,
    _market_matches_query,
    build_container_machinery_producer,
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import (
    CURATED_GROUPING_SETS_PATHS,
    check_fun_real_trading,
    clear_fun_markets_cache,
    fun_market_ids_for_sub_tag,
    load_fun_markets_registry,
)
from app.utils.discover_image_policy import _REGISTER_PATH, sanitize_discover_feed_item
from app.utils.roundup_containers import (
    compose_roundup_container,
    compose_roundup_feed_item,
)

NOW = datetime(2026, 11, 21, 21, 0, tzinfo=timezone.utc)

BATCH5_SLUGS = (
    "machinery-march-madness-2027",
    "machinery-ai-model-leaderboard-2026",
    "machinery-big-tech-deals-hardware",
    "machinery-nhl-100-point-club",
)

BAD_MID_SENTENCE_CAP_RE = re.compile(
    r", with (?:A|An|The|New|Next|Major|Magnitude|Humanoid|Before|By|After|Nuclear|In|Is|Will|When|Which)\b"
)


def _sample_ncaa_teams() -> list[dict]:
    specs = [
        (101, "Houston Cougars", "HOU", "Houston", "https://a.espncdn.com/i/teamlogos/ncaa/500/248.png"),
        (102, "Duke Blue Devils", "DUKE", "Duke", "https://a.espncdn.com/i/teamlogos/ncaa/500/150.png"),
        (103, "Florida Gators", "FLA", "Florida", "https://a.espncdn.com/i/teamlogos/ncaa/500/57.png"),
        (104, "UConn Huskies", "CONN", "UConn", "https://a.espncdn.com/i/teamlogos/ncaa/500/41.png"),
        (105, "Illinois Fighting Illini", "ILL", "Illinois", "https://a.espncdn.com/i/teamlogos/ncaa/500/356.png"),
        (106, "Kansas Jayhawks", "KU", "Kansas", "https://a.espncdn.com/i/teamlogos/ncaa/500/2305.png"),
        (107, "Arkansas Razorbacks", "ARK", "Arkansas", "https://a.espncdn.com/i/teamlogos/ncaa/500/8.png"),
        (108, "Arizona Wildcats", "ARIZ", "Arizona", "https://a.espncdn.com/i/teamlogos/ncaa/500/12.png"),
        # Ambiguity distractors that exist in D-I teams table
        (201, "Florida State Seminoles", "FSU", "Florida State", "https://a.espncdn.com/i/teamlogos/ncaa/500/52.png"),
        (202, "Florida Atlantic Owls", "FAU", "Florida Atlantic", "https://a.espncdn.com/i/teamlogos/ncaa/500/2226.png"),
        (203, "Kansas State Wildcats", "KSU", "Kansas State", "https://a.espncdn.com/i/teamlogos/ncaa/500/2306.png"),
    ]
    return [
        {
            "id": tid,
            "sport_key": "basketball_ncaab",
            "name": name,
            "abbreviation": abbr,
            "primary_color": "#003087",
            "logo_url_small": url,
            "logo_url_large": url,
            "alternate_names": [short],
        }
        for tid, name, abbr, short, url in specs
    ]


def _sample_batch5_markets() -> list[dict]:
    rows = [
        # Set 1: March Madness 2027 (10 rows)
        {"id": 52755955, "name": "College Basketball (M): #1 Ranked Team on Dec 7 AP Poll", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 5101, "name": "Houston", "probability": 0.54}, {"id": 5102, "name": "Duke", "probability": 0.25}]},
        {"id": 68954772, "name": "Will Duke reach the 2027 NCAA Men's Basketball Final Four?", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 5103, "name": "Yes", "probability": 0.375}, {"id": 5104, "name": "No", "probability": 0.625}]},
        {"id": 68954773, "name": "Will Florida reach the 2027 NCAA Men's Basketball Final Four?", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 5105, "name": "Yes", "probability": 0.325}, {"id": 5106, "name": "No", "probability": 0.675}]},
        {"id": 68954808, "name": "Will UConn reach the 2027 NCAA Men's Basketball Final Four?", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 5107, "name": "Yes", "probability": 0.235}, {"id": 5108, "name": "No", "probability": 0.765}]},
        {"id": 68954776, "name": "Will Illinois reach the 2027 NCAA Men's Basketball Final Four?", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 5109, "name": "Yes", "probability": 0.215}, {"id": 5110, "name": "No", "probability": 0.785}]},
        {"id": 68948342, "name": "Will Kansas reach the 2027 NCAA Men's Basketball Final Four?", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 5111, "name": "Yes", "probability": 0.200}, {"id": 5112, "name": "No", "probability": 0.800}]},
        {"id": 68954759, "name": "Will Arkansas reach the 2027 NCAA Men's Basketball Final Four?", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 5113, "name": "Yes", "probability": 0.170}, {"id": 5114, "name": "No", "probability": 0.830}]},
        {"id": 68954775, "name": "Will Houston reach the 2027 NCAA Men's Basketball Final Four?", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 5115, "name": "Yes", "probability": 0.120}, {"id": 5116, "name": "No", "probability": 0.880}]},
        {"id": 68954760, "name": "Will Arizona reach the 2027 NCAA Men's Basketball Final Four?", "status": "open", "source": "polymarket", "category": "basketball", "outcomes": [{"id": 5117, "name": "Yes", "probability": 0.105}, {"id": 5118, "name": "No", "probability": 0.895}]},
        {"id": 3, "name": "NCAAB Championship Winner", "status": "open", "source": "odds_api", "sport": "basketball_ncaab", "category": "basketball", "outcomes": [{"id": 5119, "name": "Florida Gators", "probability": 0.08}, {"id": 5120, "name": "Duke Blue Devils", "probability": 0.07}]},
        # Set 2: The 2026 AI Model Leaderboard (7 rows)
        {"id": 109596, "name": "Best AI at the end of 2026?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 5201, "name": "Gemini", "probability": 0.83}, {"id": 5202, "name": "OpenAI", "probability": 0.10}]},
        {"id": 62134324, "name": "Next Claude Opus (5.6+) released?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 5203, "name": "December 31", "probability": 0.785}]},
        {"id": 109623, "name": "Which AI company will have the best coding model at the end of 2026?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 5204, "name": "Anthropic", "probability": 0.475}, {"id": 5205, "name": "OpenAI", "probability": 0.30}]},
        {"id": 109322, "name": "Which AI will be the first to hit 1550 on Text Arena?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 5206, "name": "Gemini", "probability": 0.37}]},
        {"id": 22737639, "name": "Next Google Gemini Pro Model: Arena Debut?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 5207, "name": "1495+", "probability": 0.095}]},
        {"id": 30692108, "name": "Next Google Gemini Pro Model released?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 5208, "name": "December 31", "probability": 0.095}]},
        {"id": 11269760, "name": "When will Anthropic release Mythos?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 5209, "name": "Before Jan 1, 2027", "probability": 0.045}]},
        # Set 3: Big Tech Deals & Hardware (8 rows)
        {"id": 115374, "name": "Tesla and SpaceX merger officially announced?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 5301, "name": "December 31, 2027", "probability": 0.855}]},
        {"id": 109349, "name": "When will Apple release the iPhone 18?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 5302, "name": "Before April 2027", "probability": 0.835}]},
        {"id": 113435, "name": "AI bubble burst?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 5303, "name": "June 30, 2027", "probability": 0.69}]},
        {"id": 69851942, "name": "Next CEO of NVIDIA?", "status": "open", "source": "polymarket", "category": "entertainment", "outcomes": [{"id": 5304, "name": "Rene Haas", "probability": 0.28}]},
        {"id": 112875, "name": "Will OpenAI launch a consumer hardware product?", "status": "open", "source": "kalshi", "category": "tech", "outcomes": [{"id": 5305, "name": "December 31, 2026", "probability": 0.15}]},
        {"id": 115369, "name": "What kind of product will OpenAI announce in 2026?", "status": "open", "source": "polymarket", "category": "tech", "outcomes": [{"id": 5306, "name": "Necklace", "probability": 0.105}]},
        {"id": 108555, "name": "When will Starlink officially announce an IPO?", "status": "open", "source": "kalshi", "category": "economics", "outcomes": [{"id": 5307, "name": "Before Jun 30, 2027", "probability": 0.035}]},
        {"id": 16756459, "name": "Will GameStop acquire eBay in 2026?", "status": "open", "source": "kalshi", "category": "economics", "outcomes": [{"id": 5308, "name": "Yes", "probability": 0.015}, {"id": 5309, "name": "No", "probability": 0.985}]},
        # Set 4: The NHL 100-Point Club (7 rows)
        {"id": 63105212, "name": "Will Connor McDavid record 100+ points?", "status": "open", "source": "polymarket", "category": "hockey", "outcomes": [{"id": 5401, "name": "Yes", "probability": 0.942}, {"id": 5402, "name": "No", "probability": 0.058}]},
        {"id": 63218794, "name": "Will Leon Draisaitl record 100+ points?", "status": "open", "source": "polymarket", "category": "hockey", "outcomes": [{"id": 5403, "name": "Yes", "probability": 0.895}, {"id": 5404, "name": "No", "probability": 0.105}]},
        {"id": 63105213, "name": "Will Nathan MacKinnon record 100+ points?", "status": "open", "source": "polymarket", "category": "hockey", "outcomes": [{"id": 5405, "name": "Yes", "probability": 0.786}, {"id": 5406, "name": "No", "probability": 0.214}]},
        {"id": 63218771, "name": "Will David Pastrnak record 100+ points?", "status": "open", "source": "polymarket", "category": "hockey", "outcomes": [{"id": 5407, "name": "Yes", "probability": 0.610}, {"id": 5408, "name": "No", "probability": 0.390}]},
        {"id": 63119688, "name": "Will Macklin Celebrini record 100+ points?", "status": "open", "source": "polymarket", "category": "hockey", "outcomes": [{"id": 5409, "name": "Yes", "probability": 0.600}, {"id": 5410, "name": "No", "probability": 0.400}]},
        {"id": 63218780, "name": "Will Jack Eichel record 100+ points?", "status": "open", "source": "polymarket", "category": "hockey", "outcomes": [{"id": 5411, "name": "Yes", "probability": 0.500}, {"id": 5412, "name": "No", "probability": 0.500}]},
        {"id": 63218767, "name": "Will Cale Makar record 100+ points?", "status": "open", "source": "polymarket", "category": "hockey", "outcomes": [{"id": 5413, "name": "Yes", "probability": 0.110}, {"id": 5414, "name": "No", "probability": 0.890}]},
    ]
    for r in rows:
        r.setdefault("volume", 50_000)
    return rows


def test_batch5_definitions_are_public_non_politics_with_verified_art_and_zero_ncaa_static_entries() -> None:
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    register_doc = json.loads(_REGISTER_PATH.read_text(encoding="utf-8"))
    verified_urls = {
        str(entry.get("url") or "").strip()
        for entry in (register_doc.get("entries") or [])
        if isinstance(entry, dict)
    }

    art_manifest = json.loads(_SUBJECT_ART_PATH.read_text(encoding="utf-8"))
    for entry in art_manifest.get("subjects") or ():
        if not isinstance(entry, dict):
            continue
        assert "/teamlogos/ncaa/" not in str(entry.get("url") or "").lower()
        if str(entry.get("kind") or "").lower() == "team_logo":
            aliases = {str(a).lower() for a in (entry.get("aliases") or ())}
            assert aliases.isdisjoint(
                {"houston", "houston cougars", "duke", "duke blue devils", "florida", "florida gators", "uconn", "uconn huskies", "illinois", "kansas", "arkansas", "arizona"}
            )

    expected_counts = {
        "machinery-march-madness-2027": 10,
        "machinery-ai-model-leaderboard-2026": 7,
        "machinery-big-tech-deals-hardware": 8,
        "machinery-nhl-100-point-club": 7,
    }
    prior_ids: set[int] = set(load_fun_markets_registry().ordered_market_ids)
    for tag in (
        "batch3-2026-summed-up",
        "batch3-cast-delayed-cancelled",
        "batch3-stage-and-cover",
        "batch3-elon-musk-side-quests",
        "batch4-game-awards-2026",
        "batch4-big-championships-2027",
        "batch4-unsolved-big-problems",
        "batch4-ai-and-big-tech-race",
    ):
        prior_ids.update(fun_market_ids_for_sub_tag(tag))

    seen_batch5: set[int] = set()
    for slug in BATCH5_SLUGS:
        assert slug in paths_by_slug
        defn = load_machinery_definition(paths_by_slug[slug])
        assert "market_id" not in json.dumps(defn)
        assert defn["stage"] == "public"
        assert defn["category"] != "politics"
        rule = defn["rule"]
        assert rule.get("suppress_card_photo") is True
        url = str(rule.get("card_image_url") or "").strip()
        assert url.startswith("https://thumb.wikimedia.org/")
        assert url in verified_urls
        assert str(rule.get("card_image_alt") or "").strip()
        assert str(rule.get("card_image_credit") or "").strip()
        assert str(rule.get("card_image_author") or "").strip()
        lic = str(rule.get("card_image_license") or "").lower()
        assert "cc0" in lic or "public domain" in lic
        assert str(rule.get("card_image_source_page") or "").startswith(
            "https://commons.wikimedia.org/wiki/File:"
        )
        sec = rule["sections"][0]
        assert "trading" not in str(sec.get("note") or "").lower()
        sub_tag = sec["atom_query"]["fun_sub_tag"]
        ids = fun_market_ids_for_sub_tag(sub_tag)
        assert len(ids) == expected_counts[slug]
        assert set(ids).isdisjoint(prior_ids), f"{slug} overlaps prior batches"
        assert set(ids).isdisjoint(seen_batch5), f"{slug} overlaps sibling Batch 5 set"
        seen_batch5.update(ids)


@pytest.mark.asyncio
async def test_batch5_four_public_sets_build_with_crests_headshots_wording_and_parity() -> None:
    clear_fun_markets_cache()
    db = {
        "events": [],
        "markets": _sample_batch5_markets(),
        "teams": _sample_ncaa_teams(),
        "paired_sets": {},
        "market_histories": {},
    }
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}

    expected_titles = {
        "machinery-march-madness-2027": (
            "Houston holding the Dec 7 AP #1 spot is at 54%, "
            "with Duke reaching the 2027 Final Four at 38%"
        ),
        "machinery-ai-model-leaderboard-2026": (
            "Gemini finishing 2026 as the top AI model is at 83%, "
            "with a new Claude Opus arriving by Dec 31 at 79%"
        ),
        "machinery-big-tech-deals-hardware": (
            "A Tesla and SpaceX merger announced by Dec 31, 2027 is at 86%, "
            "with Apple releasing the iPhone 18 before Apr 2027 at 84%"
        ),
        "machinery-nhl-100-point-club": (
            "Connor McDavid reaching 100 points is at 94%, "
            "with Leon Draisaitl reaching 100 points at 90%"
        ),
    }

    for slug, expected_title in expected_titles.items():
        defn = load_machinery_definition(paths_by_slug[slug])
        prod = build_container_machinery_producer(defn)
        res = await produce_container_machinery(db, defn, now=NOW)
        assert res.machinery_card["stage"] == "public"
        assert res.machinery_card["image_url"] == defn["rule"]["card_image_url"]
        assert res.title == expected_title
        assert "? at " not in res.title
        assert ": " not in res.title
        assert "___" not in res.title
        assert "..." not in res.title
        assert not BAD_MID_SENTENCE_CAP_RE.search(res.title)

        fi = sanitize_discover_feed_item(compose_roundup_feed_item(prod, res))
        cp = compose_roundup_container(prod, res)
        c_p, p_p = _compute_member_number_parity(fi, cp)
        assert c_p["passes"] is True and p_p["passes"] is True

        card_rows = res.machinery_card["rows"]
        assert len(card_rows) == 3

        if slug == "machinery-march-madness-2027":
            assert [r["market_id"] for r in card_rows] == [52755955, 68954772, 68954773]
            for r in card_rows:
                art = r.get("art") or {}
                assert art.get("kind") == "team_logo"
                assert "/teamlogos/ncaa/500/" in str(art.get("url") or "")
            for sec_item in cp["sections"][0]["visual_block"]["items"]:
                art = sec_item["outcomes"][0]["art"]
                assert art.get("kind") == "team_logo"
                assert "/teamlogos/ncaa/500/" in str(art.get("url") or "")

        elif slug == "machinery-nhl-100-point-club":
            assert [r["market_id"] for r in card_rows] == [63105212, 63218794, 63105213]
            for r in card_rows:
                art = r.get("art") or {}
                assert art.get("kind") == "person"
                assert "/headshots/nhl/players/full/" in str(art.get("url") or "")
            for sec_item in cp["sections"][0]["visual_block"]["items"]:
                art = sec_item["outcomes"][0]["art"]
                assert art.get("kind") == "person"
                assert "/headshots/nhl/players/full/" in str(art.get("url") or "")

        else:
            for r in card_rows:
                art = r.get("art") or {}
                assert art.get("url") is None
                assert art.get("kind") == "monogram"


@pytest.mark.asyncio
async def test_batch5_every_row_reads_cleanly_in_slot_1_and_slot_2() -> None:
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    base_markets = {m["id"]: dict(m) for m in _sample_batch5_markets()}
    curated_sets: dict[str, list[dict]] = {}
    for p in CURATED_GROUPING_SETS_PATHS:
        doc = json.loads(p.read_text(encoding="utf-8"))
        for k, spec in (doc.get("sets") or {}).items():
            curated_sets[k.lower()] = list((spec or {}).get("entries") or [])

    for slug in BATCH5_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        sub_tag = defn["rule"]["sections"][0]["atom_query"]["fun_sub_tag"].lower()
        entries = curated_sets[sub_tag]
        ids = [int(e["id"]) for e in entries]
        for idx, mid in enumerate(ids):
            others = [x for x in ids if x != mid]
            a, b = others[0], others[1]
            # Swap top probabilities so `mid` leads in case 1 and sits #2 in case 2
            for case, (top_id, sec_id, thd_id) in enumerate(((mid, a, b), (a, mid, b)), 1):
                mkts = []
                for x in ids:
                    m = dict(base_markets[x])
                    outs = [dict(o) for o in m["outcomes"]]
                    if x == top_id:
                        outs[0]["probability"] = 0.91
                    elif x == sec_id:
                        outs[0]["probability"] = 0.77
                    elif x == thd_id:
                        outs[0]["probability"] = 0.43
                    else:
                        outs[0]["probability"] = 0.09
                    if len(outs) == 2 and outs[1]["name"].lower() == "no":
                        outs[1]["probability"] = round(1.0 - outs[0]["probability"], 3)
                    m["outcomes"] = outs
                    mkts.append(m)
                db = {
                    "events": [],
                    "markets": mkts,
                    "teams": _sample_ncaa_teams(),
                    "paired_sets": {},
                    "market_histories": {},
                }
                res = await produce_container_machinery(db, defn, now=NOW)
                h = res.title
                assert h, f"{slug}[case{case}:{mid}]: empty headline"
                assert "? at " not in h and not h.endswith("?"), f"{slug}: question headline {h!r}"
                assert ": " not in h, f"{slug}: colon dump {h!r}"
                assert not BAD_MID_SENTENCE_CAP_RE.search(h), f"{slug}: mid-sentence cap in {h!r}"


def test_missing_lifetime_volume_fallback_and_failure_contract() -> None:
    """Missing lifetime volume falls back to volume_24h or traded gamma_volume; neither fails (#336-A)."""
    # Missing lifetime volume + positive 24h volume -> passes.
    eff_v24 = _effective_market_volume(None, volume_24h=960)
    assert eff_v24 == 960.0
    assert check_fun_real_trading(eff_v24, min_lifetime_volume=1) == (True, None)

    # Missing lifetime & 24h volume + recorded traded Polymarket gamma_volume -> passes.
    traded_meta = {"volume_evidence": {"verdict": "traded", "gamma_volume": 1741.84}}
    eff_gamma = _effective_market_volume(None, volume_24h=None, market_metadata=traded_meta)
    assert eff_gamma == 1741.84
    assert check_fun_real_trading(eff_gamma, min_lifetime_volume=1) == (True, None)

    # Missing lifetime & zero 24h volume still accepts recorded traded gamma_volume.
    assert _effective_market_volume(None, volume_24h=0, market_metadata=traded_meta) == 1741.84

    # When both traded gamma_volume and volume_24h exist, recorded lifetime gamma_volume wins (#13437 note, Item 4).
    assert _effective_market_volume(None, volume_24h=960, market_metadata=traded_meta) == 1741.84
    low_24h_good_lifetime = {"volume_evidence": {"verdict": "traded", "gamma_volume": 120.0}}
    assert (
        check_fun_real_trading(
            _effective_market_volume(None, volume_24h=25.0, market_metadata=low_24h_good_lifetime),
            min_lifetime_volume=100,
        )
        == (True, None)
    )
    high_24h_low_lifetime = {"volume_evidence": {"verdict": "traded", "gamma_volume": 40.0}}
    assert (
        check_fun_real_trading(
            _effective_market_volume(None, volume_24h=500.0, market_metadata=high_24h_low_lifetime),
            min_lifetime_volume=100,
        )
        == (False, "thin_trading:40<100")
    )

    # Explicit 0 lifetime volume stays 0 (does not fall back) and fails min_lifetime_volume.
    eff_zero = _effective_market_volume(0, volume_24h=960, market_metadata=traded_meta)
    assert eff_zero == 0.0
    assert check_fun_real_trading(eff_zero, min_lifetime_volume=1) == (False, "thin_trading:0<1")

    # Missing all three (or confirmed_zero with neither) -> None / missing_volume.
    eff_none = _effective_market_volume(None, volume_24h=None, market_metadata=None)
    assert eff_none is None
    assert check_fun_real_trading(eff_none, min_lifetime_volume=1) == (False, "missing_volume")
    eff_conf_zero = _effective_market_volume(
        None,
        volume_24h=None,
        market_metadata={"volume_evidence": {"verdict": "confirmed_zero", "gamma_volume": 0}},
    )
    assert eff_conf_zero is None
    assert check_fun_real_trading(eff_conf_zero, min_lifetime_volume=1) == (False, "missing_volume")
    assert _effective_market_volume(True, volume_24h=float("nan")) is None

    # Non-fun query min_lifetime_volume respects the exact same contract.
    non_fun_q = {"min_lifetime_volume": 1}
    sample_outs = [{"id": 101, "name": "Kansas City Chiefs", "probability": 0.18}]
    assert _market_matches_query(
        {"id": 1, "name": "NFL Super Bowl Winner", "volume": None, "volume_24h": 960, "outcomes": sample_outs},
        non_fun_q,
    )
    assert _market_matches_query(
        {
            "id": 4,
            "name": "NFL Super Bowl Winner",
            "volume": None,
            "volume_24h": None,
            "market_metadata": traded_meta,
            "outcomes": sample_outs,
        },
        non_fun_q,
    )
    assert not _market_matches_query(
        {"id": 2, "name": "NFL Super Bowl Winner", "volume": None, "volume_24h": None, "outcomes": sample_outs},
        non_fun_q,
    )
    assert not _market_matches_query(
        {"id": 3, "name": "NFL Super Bowl Winner", "volume": 0, "volume_24h": 960, "outcomes": sample_outs},
        non_fun_q,
    )


@pytest.mark.asyncio
async def test_march_madness_and_nhl_100_point_build_when_lifetime_volume_is_missing() -> None:
    """Both sets build cleanly with volume=None rows when 24h or traded gamma volume exists; rows with neither fail."""
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    markets = []
    # Keep 52755955 at volume=384, give Polymarket Final Four & NHL sub-markets volume=None + gamma_volume/24h,
    # except drop 68954775 & 63218767 to neither so we verify markets without either still fail.
    dropped_mids = {68954775, 63218767}
    for m in _sample_batch5_markets():
        row = dict(m)
        mid = int(row["id"])
        if mid in dropped_mids:
            row["volume"] = None
            row["volume_24h"] = None
            row["market_metadata"] = None
        elif mid == 68954773:
            row["volume"] = None
            row["volume_24h"] = 125.0
            row["market_metadata"] = None
        elif mid != 52755955:
            row["volume"] = None
            row["volume_24h"] = None
            row["market_metadata"] = {
                "volume_evidence": {"verdict": "traded", "gamma_volume": 1741.84}
            }
        markets.append(row)

    db = {
        "events": [],
        "markets": markets,
        "teams": _sample_ncaa_teams(),
        "paired_sets": {},
        "market_histories": {},
    }

    for slug, dropped_id in (
        ("machinery-march-madness-2027", 68954775),
        ("machinery-nhl-100-point-club", 63218767),
    ):
        defn = load_machinery_definition(paths_by_slug[slug])
        prod = build_container_machinery_producer(defn)
        res = await produce_container_machinery(db, defn, now=NOW)
        assert hasattr(res, "machinery_card"), (slug, res)
        mids = {int(it["market_id"]) for it in res.sections[0]["visual_block"]["items"]}
        assert dropped_id not in mids
        assert len(mids) >= 3
        assert all(isinstance(r.get("rendered_percent"), int) for r in res.machinery_card["rows"])
        fi = sanitize_discover_feed_item(compose_roundup_feed_item(prod, res))
        cp = compose_roundup_container(prod, res)
        c_p, p_p = _compute_member_number_parity(fi, cp)
        assert c_p["passes"] is True and p_p["passes"] is True

    # If every market lacks lifetime, 24h, and traded gamma volume, assembly still refuses cleanly.
    empty_db = {
        "events": [],
        "markets": [{**m, "volume": None, "volume_24h": None, "market_metadata": None} for m in _sample_batch5_markets()],
        "teams": _sample_ncaa_teams(),
        "paired_sets": {},
        "market_histories": {},
    }
    for slug in ("machinery-march-madness-2027", "machinery-nhl-100-point-club"):
        res_refused = await produce_container_machinery(empty_db, load_machinery_definition(paths_by_slug[slug]), now=NOW)
        assert not hasattr(res_refused, "machinery_card"), slug

