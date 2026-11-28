"""Condition 1-6 tests for generic Kit container builder and nightly proposer (#12221)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re

from app.tasks.container_proposer import merge_preview_store, run_nightly_container_proposer
from app.utils.container_proposer import (
    discover_candidate_families,
    normalize_market_record,
    propose_top_containers,
)
from app.utils.kit_container_page_builder import (
    audit_container_page_invariants,
    derive_common_headline,
    propose_container_page_for_family,
)
from app.utils.kit_v1_spec import validate_kit_v1_card

REPO_ROOT = Path(__file__).resolve().parents[2]
REF_NOW = datetime(2026, 11, 24, 22, 0, 0, tzinfo=timezone.utc)

# Use escaped/assembled patterns inside test assertion only so this test file itself
# never embeds forbidden literals directly.
_BANNED_TERMS = (
    "middle" + "-east",
    "middle" + " east",
    "fed-and" + "-rates",
    "fed &" + " rates",
    "russia-" + "uk" + "raine",
    "russia\u2013" + "uk" + "raine",
    "fo" + "mc",
    "jerome " + "pow" + "ell",
    "kham" + "enei",
    "zelen" + "skyy",
    "pu" + "tin",
    "ir" + "an",
    "uk" + "raine",
)


def _bin(
    mid: int,
    name: str,
    pct: float,
    *,
    category: str = "tech",
    series: str = "KXMARS",
    group_id: str | None = None,
    res_days: int = 90,
    status: str = "open",
    settled_at: datetime | None = None,
    vol: int = 5000,
    move: float = 0.02,
    sources_count: int = 1,
) -> dict:
    return {
        "id": mid,
        "source": "kalshi" if not group_id else "polymarket",
        "external_id": f"{series}-{mid}",
        "group_id": group_id,
        "name": name,
        "category": category,
        "llm_sport_category": category,
        "status": status,
        "settled_at": settled_at,
        "resolution_date": REF_NOW + timedelta(days=res_days),
        "created_at": REF_NOW - timedelta(days=10),
        "volume_24h": vol,
        "max_movement_24h": move,
        "sources_count": sources_count,
        "outcomes": [
            {"name": "Yes", "current_probability": pct / 100.0},
            {"name": "No", "current_probability": (100.0 - pct) / 100.0},
        ],
    }


def _multi(
    mid: int,
    name: str,
    probs: dict[str, float],
    *,
    category: str = "economics",
    series: str = "KXBANK",
    vol: int = 8000,
) -> dict:
    return {
        "id": mid,
        "source": "kalshi",
        "external_id": f"{series}-{mid}",
        "group_id": None,
        "name": name,
        "category": category,
        "llm_sport_category": category,
        "status": "open",
        "settled_at": None,
        "resolution_date": REF_NOW + timedelta(days=60),
        "created_at": REF_NOW - timedelta(days=10),
        "volume_24h": vol,
        "max_movement_24h": 0.04,
        "sources_count": 2,
        "outcomes": [
            {"name": k, "current_probability": v / 100.0}
            for k, v in probs.items()
        ],
    }


def test_no_hardcoded_topics_condition1():
    """Condition 1: zero backend code, task, routes, or tests name preview slugs or entities."""
    targets = [
        REPO_ROOT / "backend" / "app" / "utils" / "kit_container_page_builder.py",
        REPO_ROOT / "backend" / "app" / "utils" / "container_proposer.py",
        REPO_ROOT / "backend" / "app" / "tasks" / "container_proposer.py",
        REPO_ROOT / "backend" / "app" / "routes" / "containers.py",
        Path(__file__),
    ]
    pat = re.compile(
        r"\b(?:" + "|".join(re.escape(t) for t in _BANNED_TERMS) + r")\b",
        re.IGNORECASE,
    )
    hits: list[str] = []
    for p in targets:
        text = p.read_text(encoding="utf-8")
        for m in pat.finditer(text):
            hits.append(f"{p.name}:{m.group(0)}")
    assert hits == [], f"Banned Condition 1 references found: {hits}"
    old_fixture = REPO_ROOT / "backend" / "tests" / "fixtures" / "kit_container_pages_item9_fixture.json"
    assert not old_fixture.exists()


def test_headline_common_thing_and_conjunction_rejection():
    ok_h, err = derive_common_headline("Mars Exploration Program", ["Mars rover milestone"])
    assert err is None
    assert ok_h == "Mars Exploration Program"

    hl, err2 = derive_common_headline(None, [
        "Orbit probe launches by Mar 2027?",
        "Orbit probe launches by Jun 2027?",
    ])
    assert err2 is None
    assert hl is not None and 2 <= len(hl.split()) <= 4
    assert "?" not in hl and "%" not in hl

    bad_hl, bad_err = derive_common_headline("Solar Probes & Mars Landers", ["Solar Probes leads 80%"])
    assert bad_hl is None
    assert bad_err == "refused_headline_not_2_to_4_common_thing"


def test_condition5_settled_member_refusal():
    open_set = [
        _bin(1, "Alpha orbit test Before Mar 15 2027", 45, res_days=10),
        _bin(2, "Alpha orbit test Before Jun 30 2027", 65, res_days=100),
        _bin(3, "Alpha dock test Before Mar 15 2027", 35, res_days=12),
        _bin(4, "Alpha dock test Before Jun 30 2027", 55, res_days=120),
        _bin(5, "Alpha moon base anomaly", 8, status="resolved", settled_at=REF_NOW - timedelta(days=1)),
    ]
    res = propose_container_page_for_family("Spaceflight Milestones", open_set, now=REF_NOW)
    assert res["accepted"] is False
    assert res["refusal_reason"] == "refused_contains_settled_member"


def test_generic_classifiers_scoreboard_dated_tiles_scale_countdown_one_in_n_no_dups():
    markets = [
        # scoreboard_grid (2 multi-outcome siblings with Direction 228 compliant columns)
        _multi(101, "Central Bank Rate Move Dec 2026", {"+25 bp": 65, "Hold": 30, "-25 bp": 5}, series="KXCB"),
        _multi(102, "Central Bank Rate Move Jan 2027", {"+25 bp": 40, "Hold": 50, "-25 bp": 10}, series="KXCB"),
        # dated_tiles preserving Before X verbatim
        _bin(103, "Mars cargo ship arrives Before Mar 15 2027", 18, category="science", res_days=110),
        _bin(104, "Mars cargo ship arrives Before Dec 31 2027", 42, category="science", res_days=400),
        # shared_scale (3 comparable binaries >= 10pt spread)
        _bin(105, "Global battery output target A reached", 72, category="science", res_days=90),
        _bin(106, "Global battery output target B reached", 44, category="science", res_days=90),
        _bin(107, "Global battery output target C reached", 19, category="science", res_days=90),
        # countdown (1..45d remaining)
        _bin(108, "Lunar lander launches smoothly", 61, category="science", res_days=14),
        _bin(109, "Telemetry relay upgrade completes", 38, category="science", res_days=28),
        # one_in_n (1..15%)
        _bin(110, "Comet probe enters deep hibernation", 9, category="science", res_days=180),
        _bin(111, "Deep trench submarine finds vents", 6, category="science", res_days=200),
    ]
    res = propose_container_page_for_family(
        "Orbital Research Goals",
        markets,
        now=REF_NOW,
        kicker="SCIENCE",
        family_fingerprint="fp-test-1",
    )
    assert res["accepted"] is True, res
    page = res["page"]
    assert page["state"] == "preview"
    assert page["title"] == "Orbital Research Goals"
    assert 3 <= page["section_count"] <= 5
    variants = page["variants"]
    assert len(variants) == len(set(variants))
    assert "scoreboard_grid" in variants
    assert "dated_tiles" in variants
    assert "shared_scale" in variants
    assert "plain_bar_stack" not in variants  # 388: A bars not used when structured shapes fit

    dated_sec = next(s for s in page["sections"] if s["variant"] == "dated_tiles")
    tile_tops = [
        cell["marks"][0].get("top_label") or ""
        for row in dated_sec["body"]["rows"]
        for cell in row["cells"]
    ]
    assert any(lbl.startswith("Before Mar 15") for lbl in tile_tops), tile_tops
    for sec in page["sections"]:
        ok, errs = validate_kit_v1_card(sec)
        assert ok, errs


def test_plain_bar_stack_is_strictly_last_resort_and_too_few_sections_refused():
    # Insufficient distinct structure (< 3 shapes even with last-resort bars) -> refused
    tiny = [
        _bin(201, "Alpha beta item one", 52, res_days=120),
        _bin(202, "Alpha beta item two", 51, res_days=120),
        _bin(203, "Alpha beta item three", 50, res_days=120),
        _bin(204, "Alpha beta item four", 49, res_days=120),
        _bin(205, "Alpha beta item five", 48, res_days=120),
    ]
    refused = propose_container_page_for_family("Alpha Beta Items", tiny, now=REF_NOW)
    assert refused["accepted"] is False
    assert refused["refusal_reason"] == "refused_too_few_distinct_sections"

    # Exactly 2 structured shapes + residual binaries -> last-resort plain_bar_stack rescues cleanly
    borderline = [
        _bin(211, "Film release schedule Before Jan 15 2027", 25, category="entertainment", res_days=15),
        _bin(212, "Film release schedule Before Jun 30 2027", 68, category="entertainment", res_days=200),
        _bin(213, "Film sequel greenlit", 11, category="entertainment", res_days=22),
        _bin(214, "Film soundtrack reaches chart top", 7, category="entertainment", res_days=180),
        _bin(215, "Studio merger passes regulator", 55, category="entertainment", res_days=90),
        _bin(216, "Festival premiere wins jury prize", 42, category="entertainment", res_days=95),
    ]
    rescued = propose_container_page_for_family("Summer Cinema Slate", borderline, now=REF_NOW)
    assert rescued["accepted"] is True, rescued
    assert "plain_bar_stack" in rescued["page"]["variants"]
    assert rescued["page"]["section_count"] == 3


def test_proposer_interest_beats_size_and_nightly_task_is_idempotent():
    # Huge low-interest sports family (25 markets) vs small vibrant entertainment family (7 markets)
    markets: list[dict] = []
    for i in range(25):
        markets.append(
            _bin(
                1000 + i,
                f"Regional hockey conference seed {i}",
                50,
                category="sports",
                series="KXHOCKEY",
                vol=20,
                move=0.0,
                res_days=150,
                sources_count=1,
            )
        )

    ent_markets = [
        {**_bin(2001, "Autumn blockbuster opens above 90M Before Nov 28 2026", 30, category="entertainment", series="KXMOVIE", vol=90000, move=0.14, res_days=10, sources_count=2), "event_title": "Autumn Cinema Box Office"},
        {**_bin(2002, "Autumn blockbuster opens above 90M Before Dec 15 2026", 62, category="entertainment", series="KXMOVIE", vol=85000, move=0.12, res_days=21, sources_count=2), "event_title": "Autumn Cinema Box Office"},
        {**_bin(2003, "Lead actor tour sells out week one", 76, category="entertainment", series="KXMOVIE", vol=70000, move=0.08, res_days=18, sources_count=2), "event_title": "Autumn Cinema Box Office"},
        {**_bin(2004, "Studio trailer breaks 24h record", 44, category="entertainment", series="KXMOVIE", vol=60000, move=0.07, res_days=12, sources_count=2), "event_title": "Autumn Cinema Box Office"},
        {**_bin(2005, "Original score hits streaming top ten", 18, category="entertainment", series="KXMOVIE", vol=55000, move=0.05, res_days=80, sources_count=2), "event_title": "Autumn Cinema Box Office"},
        {**_bin(2006, "Surprise cameo confirmed in credits", 8, category="entertainment", series="KXMOVIE", vol=50000, move=0.03, res_days=120, sources_count=2), "event_title": "Autumn Cinema Box Office"},
        {**_bin(2007, "Director cut theatrical run announced", 5, category="entertainment", series="KXMOVIE", vol=45000, move=0.02, res_days=130, sources_count=2), "event_title": "Autumn Cinema Box Office"},
    ]
    markets.extend(ent_markets)

    out = propose_top_containers(markets, now=REF_NOW, max_proposals=5, audit_top_n=10)
    assert out["ranked_audit"][0]["key"] == "KXMOVIE"
    assert len(out["pages"]) >= 1
    assert out["pages"][0]["title"] == "Autumn Cinema Box Office"
    assert out["pages"][0]["kicker"] == "ENTERTAINMENT"
    assert out["pages"][0]["state"] == "preview"

    class FakeRedis:
        def __init__(self):
            self.store = {}
        def get(self, k):
            return self.store.get(k)
        def set(self, k, v, ex=None):
            self.store[k] = v

    rc = FakeRedis()
    run1 = asyncio.run(run_nightly_container_proposer(markets=markets, now=REF_NOW, redis_client=rc))
    run2 = asyncio.run(run_nightly_container_proposer(markets=markets, now=REF_NOW, redis_client=rc))
    assert run1["proposed_count"] >= 1
    assert run1["store"]["added_last_run"] == run1["proposed_count"]
    assert run2["store"]["added_last_run"] == 0
    assert run2["store"]["count"] == run1["store"]["count"]
    assert all(p["state"] == "preview" for p in run2["store"]["pages"])
    merged = merge_preview_store(run1["store"], run2["pages"], now=REF_NOW)
    assert merged["count"] == run1["store"]["count"]


def test_normalize_public_futures_api_shape():
    raw = {
        "id": 91001,
        "name": "Annual box office opening top grossing film",
        "llm_sport_category": "entertainment",
        "source": "polymarket",
        "source_count": 2,
        "resolution_date": "2026-12-20T00:00:00+00:00",
        "top_outcomes": [
            {"id": 1, "name": "Yes", "probability": 0.64, "movement": 0.08},
            {"id": 2, "name": "No", "probability": 0.36, "movement": -0.08},
        ],
    }
    norm = normalize_market_record(raw)
    assert norm["sources_count"] == 2
    assert norm["max_movement_24h"] == 0.08
    assert len(norm["outcomes"]) == 2
    assert norm["outcomes"][0]["current_probability"] == 0.64
    assert norm["outcomes"][0]["probability_change_24h"] == 0.08


def test_single_template_threshold_ladder_refused_and_never_split():
    # Ten thresholds sharing the exact same metric/template MUST collapse into ONE section
    # and be refused for < 3 distinct sections (never chopped into scale + countdown + bars).
    ladder = [
        _bin(92000 + i, f'Will "Solaris Film" score at least {45 + i * 5} on the Rotten Tomatoes Tomatometer?', pct, category="entertainment", res_days=10 + i * 3)
        for i, pct in enumerate([92, 84, 76, 68, 59, 49, 37, 25, 13, 6])
    ]
    ladder.append(_multi(
        92099,
        "Solaris Film: Rotten Tomatoes score",
        {"Above 45": 92, "Above 60": 68, "Above 80": 25},
        category="entertainment",
    ))
    res = propose_container_page_for_family("Solaris Film", ladder, now=REF_NOW, kicker="ENTERTAINMENT")
    assert res["accepted"] is False
    assert res["refusal_reason"] == "refused_too_few_distinct_sections"
    assert len(res["variants"]) == 1


def test_multi_outcome_date_rungs_exclude_past_dates():
    # Multi-outcome market with 1 past date and 3 strictly open future dates draws ONLY future open rungs
    mkts = [
        {
            "id": 93001,
            "source": "polymarket",
            "external_id": "KXSAT-1",
            "name": "Meridian Satellite orbital docking test by...?",
            "category": "tech",
            "llm_sport_category": "tech",
            "status": "open",
            "resolution_date": REF_NOW + timedelta(days=120),
            "outcomes": [
                {"name": "October 31", "current_probability": 0.0},
                {"name": "November 30", "current_probability": 0.14},
                {"name": "December 31", "current_probability": 0.52},
                {"name": "February 28", "current_probability": 0.81},
            ],
        },
        _bin(93002, "Meridian Satellite telemetry target A reached", 72, category="tech", res_days=60),
        _bin(93003, "Meridian Satellite telemetry target B reached", 58, category="tech", res_days=75),
        _bin(93004, "Meridian Satellite telemetry target C reached", 44, category="tech", res_days=90),
        _bin(93005, "Meridian Satellite telemetry target D reached", 31, category="tech", res_days=100),
        _bin(93006, "Meridian Satellite telemetry target E reached", 19, category="tech", res_days=110),
        _bin(93007, "Meridian Satellite solar array anomaly", 8, category="tech", res_days=20),
        _bin(93008, "Meridian Satellite deep orbit boost", 4, category="tech", res_days=30),
    ]
    res = propose_container_page_for_family("Meridian Satellite", mkts, now=REF_NOW, kicker="TECH")
    assert res["accepted"] is True, res
    dated = next(s for s in res["page"]["sections"] if s["variant"] == "dated_tiles")
    tops = [c["marks"][0]["top_label"] for r in dated["body"]["rows"] for c in r["cells"]]
    assert not any("Oct" in t for t in tops), tops
    assert any("Nov 30" in t for t in tops) and any("Feb 28" in t for t in tops), tops


def test_partial_overlap_scoreboard_grid_and_game_prop_exclusion():
    # Sibling awards markets sharing overlapping (non-identical) contender columns + game_prop exclusion
    markets = [
        _multi(94001, "Aurora Awards 2027: Best Production Design", {"Starlight": 58, "Horizon": 22, "Cobalt": 9}, category="entertainment", series="KXAUR"),
        _multi(94002, "Aurora Awards 2027: Best Costume Design", {"Starlight": 51, "Velvet": 18, "Cobalt": 11}, category="entertainment", series="KXAUR"),
        _multi(94003, "Aurora Awards 2027: Best Sound Mix", {"Starlight": 46, "Horizon": 29, "Northwind": 12}, category="entertainment", series="KXAUR"),
        _bin(94004, "Aurora Awards ceremony broadcast Before Jan 15 2027", 65, category="entertainment", series="KXAUR", res_days=12),
        _bin(94005, "Aurora Awards ceremony broadcast Before Feb 28 2027", 92, category="entertainment", series="KXAUR", res_days=95),
        _bin(94006, "Aurora Awards surprise duet performance", 11, category="entertainment", series="KXAUR", res_days=25),
        _bin(94007, "Aurora Awards orchestra encore announced", 7, category="entertainment", series="KXAUR", res_days=180),
        # Should be filtered out cleanly by game_prop / vs guard:
        *[_bin(94100 + i, f"Sharks vs. Hawks {i}", 50, category="game_prop", series="") for i in range(6)],
        *[_bin(94200 + i, f"Lions vs Tigers prop {i}", 50, category="sports", series="") for i in range(6)],
    ]
    fams, by_id = discover_candidate_families(markets, now=REF_NOW, min_markets=5)
    for fam in fams:
        for mid in fam.member_ids:
            assert "vs" not in by_id[mid]["name"].lower()

    res = propose_container_page_for_family("Aurora Awards 2027", [m for m in markets if m["id"] < 94100], now=REF_NOW, kicker="ENTERTAINMENT")
    assert res["accepted"] is True, res
    assert "scoreboard_grid" in res["page"]["variants"]
    sb = next(s for s in res["page"]["sections"] if s["variant"] == "scoreboard_grid")
    col_labels = [c["label"] for c in sb["body"]["columns"]]
    assert "Starlight" in col_labels and ("Horizon" in col_labels or "Cobalt" in col_labels)


def test_no_only_probability_4word_dates_single_label_and_no_highest_soup():
    from app.utils.kit_container_page_builder import _build_scoreboard_grid_section, _top_probability

    # 1. No-only binary market returns Yes = 100 - No
    no_only = {"id": 95001, "name": "ApexCorp IPO delayed", "outcomes": [{"name": "No", "current_probability": 0.92}]}
    assert round(_top_probability(no_only), 1) == 8.0

    # 2. 4-word date outcomes must never enter scoreboard_grid
    date_out_mkts = [
        _multi(95002, "ApexCorp product milestone A", {"Before Jan 1, 2027": 45, "Before Oct 1, 2026": 55}, category="tech", series="KXAPX"),
        _multi(95003, "ApexCorp product milestone B", {"Before Jan 1, 2027": 30, "Before Oct 1, 2026": 70}, category="tech", series="KXAPX"),
    ]
    assert _build_scoreboard_grid_section("apex", "TECH", date_out_mkts, set(), now=REF_NOW) is None

    # 3. Single-word family_label yields "<Entity> Outlook" instead of falling through to a single title
    hl, err = derive_common_headline("ApexCorp", ["ApexCorp acquired before 2027?", "ApexCorp revenue target reached"])
    assert err is None
    assert hl == "ApexCorp Outlook"

    # 4. Generic superlative "Highest ..." never creates a mixed "Highest" soup cluster
    mixed = [
        _bin(95100 + i, f"Highest mountain temperature index {i}", 25 + i * 10, category="weather", series="")
        for i in range(6)
    ]
    fams, _ = discover_candidate_families(mixed, now=REF_NOW, min_markets=5)
    assert all(f.label.lower() != "highest" for f in fams)


def test_plain_bar_stack_skips_multi_outcome_date_rungs_and_row_at_least():
    from app.utils.kit_container_page_builder import (
        _build_plain_bar_stack_section,
        _distinguishing_row_label,
    )

    # 1. Past-date multi-outcome market skipped cleanly in plain_bar_stack
    date_multi = {
        "id": 96001,
        "source": "polymarket",
        "external_id": "KXPBS-1",
        "name": "Orbital milestone by...?",
        "category": "tech",
        "llm_sport_category": "tech",
        "status": "open",
        "outcomes": [
            {"name": "March 31, 2026", "current_probability": 0.0},
            {"name": "September 30, 2026", "current_probability": 0.0},
            {"name": "December 31, 2026", "current_probability": 0.16},
        ],
    }
    assert _build_plain_bar_stack_section("orb", "TECH", [date_multi], set(), now=REF_NOW) is None

    # 2. _distinguishing_row_label never chops "At least 36.0" down to "Least 36.0"
    lbl = _distinguishing_row_label(
        "Will metric index be at least 36.0?",
        ["Will metric index be at least 36.0?", "Will metric index be at least 37.0?"],
    )
    assert lbl.startswith("At least 36.0"), lbl

    # 3. derive_common_headline deduplicates possessives and skips "added"
    hl, err = derive_common_headline(
        None,
        ["ApexCorp added ApexCorp's target A", "ApexCorp added ApexCorp's target B"],
    )
    assert err is None
    assert hl is not None and hl.lower().count("apexcorp") == 1, hl
    assert "added" not in hl.lower(), hl


def test_missing_external_id_no_mkt_collapse_and_rendered_row_dedup():
    from app.utils.kit_container_page_builder import _build_countdown_section

    # 1. Missing external_id across unrelated Kalshi markets MUST NOT synthesize "mkt-..." and merge
    unrelated = [
        {
            "id": 97001 + i,
            "source": "kalshi",
            "external_id": None,
            "name": nm,
            "category": cat,
            "llm_sport_category": cat,
            "status": "open",
            "resolution_date": REF_NOW + timedelta(days=30),
            "outcomes": [{"name": "Yes", "current_probability": 0.45}],
        }
        for i, (nm, cat) in enumerate([
            ("Central Bank policy decision Dec 2026", "economics"),
            ("Arctic ice minimum record Dec 2026", "weather"),
            ("Orbital telescope mirror calibration", "tech"),
            ("Botanical gardens festival attendance", "entertainment"),
            ("Deep sea cable upgrade completion", "tech"),
            ("Mountain railway electrification milestone", "economics"),
        ])
    ]
    fams, _ = discover_candidate_families(unrelated, now=REF_NOW, min_markets=5)
    assert all(f.key.upper() != "MKT" and f.label.upper() != "MKT" for f in fams), fams

    # 2. Countdown deduplicates identical rendered row labels without slicing dissimilar suffixes
    dup_cands = [
        _bin(97101, "Will Apex Executive rank in SearchEngine Top 5 Global Searches of 2027?", 66, category="tech", res_days=20),
        _bin(97102, "Apex Executive rank in SearchEngine Top 5 Global Searches of 2027", 66, category="tech", res_days=20),
        _bin(97103, "Will Apex Executive launch new hardware keynote?", 55, category="tech", res_days=10),
    ]
    cd = _build_countdown_section("apex", "TECH", dup_cands, set(), now=REF_NOW)
    assert cd is not None
    row_texts = [it["marks"][0]["text"] for it in cd["body"]["items"]]
    assert len(row_texts) == len(set(t.lower() for t in row_texts)), row_texts
    assert len(row_texts) == 2

    # 3. Date marker stem trims dangling trailing prepositions ("... on Nov 29?" -> "... City")
    from app.utils.kit_container_page_builder import _parse_date_marker

    parsed = _parse_date_marker("Will it rain in New York City on Nov 29?", default_year=2026)
    assert parsed is not None
    assert not parsed["stem"].lower().endswith((" on", " at", " in", " by", " before")), parsed
    assert parsed["stem"].lower() == "it rain in new york city", parsed


def test_every_built_cell_carries_provenance_and_matches_market_page(monkeypatch):
    """Every rendered container cell carries (market_id, outcome_id) matching _format_market_detail."""
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.routes.futures import _format_market_detail
    from app.utils import kit_container_page_builder as builder_mod
    from app.utils.graded_card import rendered_percent
    from app.utils.kit_container_page_builder import _pct_display
    from app.utils.kit_v1_spec import ALLOWED_KIT_IMAGE_HOSTS, compute_one_in_n

    img_host = sorted(ALLOWED_KIT_IMAGE_HOSTS)[0]
    monkeypatch.setattr(
        builder_mod,
        "_verified_art_by_key",
        lambda: {
            "elena vance": {"url": f"https://{img_host}/verified/elena.png", "source": "Wikimedia"},
            "marcus cole": {"url": f"https://{img_host}/verified/marcus.png", "source": "Wikimedia"},
            "nadia lin": {"url": f"https://{img_host}/verified/nadia.png", "source": "Wikimedia"},
        },
    )

    def _m(
        mid: int,
        name: str,
        outcomes: list[tuple[int, str, float]],
        *,
        cat: str = "tech",
        series: str = "KXCELL",
        res_days: int | None = None,
    ) -> dict:
        m = {
            "id": mid,
            "source": "kalshi",
            "external_id": f"{series}-{mid}",
            "name": name,
            "category": cat,
            "llm_sport_category": cat,
            "status": "open",
            "resolution_date": REF_NOW + timedelta(days=res_days) if res_days is not None else REF_NOW + timedelta(days=90),
            "volume_24h": 5000 + mid % 100,
            "outcomes": [
                {"id": oid, "name": oname, "current_probability": prob}
                for oid, oname, prob in outcomes
            ],
        }
        return m

    def _to_orm(m: dict) -> FuturesMarket:
        fm = FuturesMarket(
            id=m["id"],
            name=m["name"],
            description="",
            category=m["category"],
            llm_sport_category=m["llm_sport_category"],
            source=m["source"],
            external_id=m["external_id"],
            status="open",
            volume_24h=m["volume_24h"],
            liquidity=1000.0,
            resolution_date=m["resolution_date"],
            settled_at=None,
            created_at=REF_NOW - timedelta(days=5),
            updated_at=REF_NOW,
            market_tier=2,
            mutually_exclusive=True,
            market_metadata={},
        )
        fm.outcomes = [
            FuturesOutcome(
                id=o["id"],
                external_id=f"{m['external_id']}-{o['id']}",
                name=o["name"],
                current_probability=o["current_probability"],
                opening_probability=o["current_probability"],
                probability_change_24h=0.0,
                rank=idx + 1,
                is_winner=False,
                last_updated=REF_NOW,
            )
            for idx, o in enumerate(m["outcomes"])
        ]
        return fm

    # Family A: exercises scoreboard_grid (dated YY rows with contender columns), dated_tiles,
    # shared_scale, countdown, one_in_n — PLUS sub-0.5% (0.003 -> <1%), sub-1% rounded (0.006, 0.008 -> 1%),
    # and high-precision 0.9985 (rendered_percent -> 100, _display_pct -> >99%).
    family_a = [
        _m(98100, "Helios Reactor Policy Decision in Mar 2026", [(1001, "Hold", 0.91), (1002, "Raise", 0.06), (1003, "Pause", 0.03)], series="KXHEL", res_days=40),
        _m(98101, "Helios Reactor Policy Decision in Dec 2026", [(1011, "Hold", 0.62), (1012, "Raise", 0.24), (1013, "Pause", 0.14)], series="KXHEL", res_days=45),
        _m(98102, "Helios Reactor Policy Decision in Mar 2027", [(1021, "Hold", 0.34), (1022, "Raise", 0.48), (1023, "Pause", 0.18)], series="KXHEL", res_days=55),
        _m(98103, "Helios Reactor target by Feb 14 2027", [(1031, "Yes", 0.008), (1032, "No", 0.992)], series="KXHEL", res_days=22),
        _m(98104, "Helios Reactor target by Apr 30 2027", [(1041, "Yes", 0.9985), (1042, "No", 0.0015)], series="KXHEL", res_days=140),
        _m(98105, "Helios Reactor output exceeds 500 MW", [(1051, "Yes", 0.62), (1052, "No", 0.38)], series="KXHEL", res_days=80),
        _m(98110, "Helios Reactor output exceeds 700 MW", [(1101, "Yes", 0.31), (1102, "No", 0.69)], series="KXHEL", res_days=80),
        _m(98106, "Helios Reactor output exceeds 900 MW", [(1061, "Yes", 0.003), (1062, "No", 0.997)], series="KXHEL", res_days=80),
        _m(98107, "Helios Reactor cooling permit approved", [(1071, "Yes", 0.006), (1072, "No", 0.994)], series="KXHEL", res_days=12),
        _m(98109, "Helios Reactor pressure valve inspected", [(1091, "Yes", 0.77), (1092, "No", 0.23)], series="KXHEL", res_days=18),
        _m(98108, "Helios Reactor extreme surge outlier", [(1081, "Yes", 0.04), (1082, "No", 0.96)], series="KXHEL", res_days=90),
    ]
    # Family B: exercises casting_sheet + shared_scale + plain_bar_stack (multi-outcome & binary fallback)
    family_b = [
        _m(98201, "Vertex Studio Awards: Best Direction", [(2011, "Elena Vance", 0.44), (2012, "Marcus Cole", 0.31), (2013, "Nadia Lin", 0.16), (2014, "Other", 0.09)], cat="entertainment", series="KXVTX", res_days=60),
        _m(98202, "Vertex Studio box office at least $400M", [(2021, "Yes", 0.72), (2022, "No", 0.28)], cat="entertainment", series="KXVTX", res_days=75),
        _m(98203, "Vertex Studio box office at least $800M", [(2031, "Yes", 0.24), (2032, "No", 0.76)], cat="entertainment", series="KXVTX", res_days=75),
        _m(98206, "Vertex Studio box office at least $1200M", [(2061, "Yes", 0.08), (2062, "No", 0.92)], cat="entertainment", series="KXVTX", res_days=75),
        _m(98204, "Vertex Studio wins critic guild honor", [(2041, "Yes", 0.51), (2042, "No", 0.49)], cat="entertainment", series="KXVTX", res_days=85),
        _m(98205, "Vertex Studio sequel greenlit", [(2051, "Yes", 0.63), (2052, "No", 0.37)], cat="entertainment", series="KXVTX", res_days=120),
    ]

    page_a = propose_container_page_for_family("Helios Reactor", family_a, now=REF_NOW, kicker="TECH", family_fingerprint="fam-a")
    page_b = propose_container_page_for_family("Vertex Studio", family_b, now=REF_NOW, kicker="ENTERTAINMENT", family_fingerprint="fam-b")
    assert page_a["accepted"] is True, page_a
    assert page_b["accepted"] is True, page_b

    all_pages = [page_a["page"], page_b["page"]]
    variants_seen = {v for p in all_pages for v in p["variants"]}
    assert {"scoreboard_grid", "dated_tiles", "shared_scale", "countdown", "casting_sheet", "plain_bar_stack"} <= variants_seen, variants_seen

    market_by_id = {m["id"]: m for m in [*family_a, *family_b]}
    detail_by_id = {
        mid: _format_market_detail(_to_orm(m), normalize_numbers=True)
        for mid, m in market_by_id.items()
    }

    verified_cells = 0
    seen_pct_displays: list[str] = []

    def _assert_unit_matches(container_obj: dict) -> None:
        nonlocal verified_cells
        marks = container_obj.get("marks") or []
        tile_marks = [mk for mk in marks if isinstance(mk, dict) and mk.get("mark") == "tile"]
        if tile_marks and all(mk.get("center_label") == "—" for mk in tile_marks) and "provenance" not in container_obj:
            return
        prov = container_obj.get("provenance")
        assert isinstance(prov, dict), f"Missing provenance on {container_obj}"
        mid = prov.get("market_id")
        oid = prov.get("outcome_id")
        assert isinstance(mid, int) and mid in detail_by_id, prov
        served_outcomes = detail_by_id[mid]["outcomes"]
        matched_out = next((o for o in served_outcomes if o.get("id") == oid), None)
        assert matched_out is not None, f"Missing outcome {oid} on market {mid}: {served_outcomes}"
        served_prob = float(matched_out["probability"])
        rp_raw = matched_out.get("rendered_percent")
        expected_int = int(rp_raw) if rp_raw is not None else rendered_percent(served_prob)
        expected_disp = _pct_display(served_prob, expected_int)

        pct_marks = [
            mk for mk in marks
            if isinstance(mk, dict) and mk.get("mark") == "number" and mk.get("unit") == "%"
        ]
        oin_marks = [
            mk for mk in marks
            if isinstance(mk, dict) and mk.get("mark") == "number" and mk.get("unit") == "one_in_n"
        ]
        if oin_marks:
            expected_n = compute_one_in_n(expected_int)
            for mk in oin_marks:
                assert int(mk["value"]) == int(expected_n), (mid, oid, mk, expected_n)
        if pct_marks:
            for mk in pct_marks:
                assert int(mk["value"]) == int(expected_int), (mid, oid, mk, expected_int)
                assert mk["display"] == expected_disp, (mid, oid, mk, expected_disp)
                assert mk["display"] != "80%" or abs(served_prob - 0.8) < 0.01
                seen_pct_displays.append(mk["display"])
        elif tile_marks:
            for mk in tile_marks:
                assert mk["center_label"] == expected_disp, (mid, oid, mk, expected_disp)
                assert mk["center_label"] != "80%" or abs(served_prob - 0.8) < 0.01
                seen_pct_displays.append(mk["center_label"])
        else:
            raise AssertionError(f"Expected % number or tile mark alongside provenance on {container_obj}")
        verified_cells += 1

    for page in all_pages:
        assert len(str(page.get("page_fingerprint") or "")) == 16
        for sec in page["sections"]:
            body = sec["body"]
            layout = sec["layout"]
            if layout == "grid":
                for row in body.get("rows") or []:
                    for cell in row.get("cells") or []:
                        _assert_unit_matches(cell)
            elif layout == "stack":
                for item in body.get("items") or []:
                    _assert_unit_matches(item)
            elif layout == "axis":
                for series in body.get("series") or []:
                    _assert_unit_matches(series)

    # Confirm 0.008 became 1% (not 80%), 0.003 became <1%, and 0.9985 became >99% (via shared _display_pct)
    assert verified_cells >= 20, verified_cells
    assert "<1%" in seen_pct_displays, seen_pct_displays
    assert "1%" in seen_pct_displays, seen_pct_displays
    assert ">99%" in seen_pct_displays, seen_pct_displays
    assert rendered_percent(0.9985) == 100
    assert _pct_display(0.9985) == ">99%"
    print(f"[cell-equals-page verified_cells={verified_cells}]")


def test_kit_pages_route_is_strict_redis_read_only(monkeypatch):
    """Web route reads Redis only; never executes proposer or DB snapshot when Redis is cold."""
    import asyncio
    from types import SimpleNamespace
    from app.routes import containers as containers_route
    from app.tasks import container_proposer as cp_task

    class FakeRedis:
        def __init__(self, initial=None):
            self.store = dict(initial or {})

        def get(self, key):
            return self.store.get(key)

        def set(self, key, val, ex=None):
            self.store[key] = val

    async def _admin_ok(*_a, **_kw):
        return True

    def _boom(*_a, **_kw):
        raise AssertionError("Web route MUST NOT execute proposer or DB snapshot")

    fake_rc = FakeRedis()
    monkeypatch.setattr("app.routes.admin_utils._check_admin_auth", _admin_ok)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: fake_rc)
    monkeypatch.setattr(cp_task, "run_nightly_container_proposer", _boom)
    monkeypatch.setattr(cp_task, "load_open_markets_snapshot", _boom)

    req = SimpleNamespace(headers={}, query_params={})
    cold = asyncio.run(containers_route.get_kit_container_pages_preview(request=req, db=None))
    assert cold["status"] == "not_built_yet"
    assert cold["deck_id"] is None
    assert cold["pages"] == []
    assert cold["count"] == 0

    # When populated, default route returns ready + deck_id; explicit ?deck_id= pins frozen deck
    deck_payload = cp_task.merge_preview_store(
        None,
        [{"slug": "alpha-set", "family_fingerprint": "fp1", "page_fingerprint": "deadbeef12345678", "title": "Alpha Set", "kicker": "TECH", "market_count": 5, "section_count": 3, "variants": ["a", "b", "c"], "sections": []}],
        now=REF_NOW,
        covered_ids_count=42,
        timings_ms={"total_ms": 12.5},
    )
    fake_rc.set(cp_task.CONTAINER_PREVIEWS_REDIS_KEY, json.dumps(deck_payload))
    fake_rc.set(f"{cp_task.CONTAINER_PREVIEWS_DECK_KEY_PREFIX}{deck_payload['deck_id']}", json.dumps(deck_payload))

    ready = asyncio.run(containers_route.get_kit_container_pages_preview(request=req, db=None))
    assert ready["status"] == "ready"
    assert ready["deck_id"] == deck_payload["deck_id"]
    assert ready["covered_ids_count"] == 42
    assert ready["count"] == 1

    pinned = asyncio.run(
        containers_route.get_kit_container_pages_preview(request=req, deck_id=deck_payload["deck_id"], db=None)
    )
    assert pinned["status"] == "ready"
    assert pinned["deck_id"] == deck_payload["deck_id"]

    missing_pin = asyncio.run(
        containers_route.get_kit_container_pages_preview(request=req, deck_id="kit-deck-expired0000", db=None)
    )
    assert missing_pin["status"] == "not_built_yet"
    assert missing_pin["pages"] == []


def test_frozen_deck_id_covered_ids_and_timings_in_task(monkeypatch):
    """Worker loads covered_ids automatically when omitted, records timings, and freezes deck_id."""
    import asyncio
    from app.tasks import container_proposer as cp_task

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, val, ex=None):
            self.store[key] = val

    mkts = [
        _bin(99101, "Alpha Horizon launch Before Feb 1 2027", 35, category="tech", series="KXAL", res_days=30),
        _bin(99102, "Alpha Horizon launch Before Jun 1 2027", 72, category="tech", series="KXAL", res_days=140),
        _bin(99103, "Alpha Horizon budget at least $200M", 61, category="tech", series="KXAL", res_days=90),
        _bin(99104, "Alpha Horizon budget at least $500M", 29, category="tech", series="KXAL", res_days=90),
        _bin(99105, "Alpha Horizon safety audit passed", 8, category="tech", series="KXAL", res_days=20),
        _bin(99106, "Alpha Horizon booster reuse achieved", 44, category="tech", series="KXAL", res_days=25),
    ]

    async def _fake_covered(_sess, **_kw):
        return {99101, 99102}  # Excludes 2 markets so Alpha Horizon drops below 5

    monkeypatch.setattr(cp_task, "load_covered_market_ids", _fake_covered)
    rc = FakeRedis()
    res_filtered = asyncio.run(
        cp_task.run_nightly_container_proposer(
            session=object(),
            markets=mkts,
            covered_ids=None,
            covered_public_set_names=(),
            now=REF_NOW,
            redis_client=rc,
        )
    )
    assert res_filtered["covered_ids_count"] == 2
    assert res_filtered["proposed_count"] == 0
    assert res_filtered["status"] == "complete"
    assert res_filtered["coverage_partial"] is False
    assert res_filtered["timings_ms"]["total_ms"] >= 0.0

    # With empty covered_ids, Alpha Horizon proposes and freezes deck_id in Redis
    res_open = asyncio.run(
        cp_task.run_nightly_container_proposer(
            markets=mkts,
            covered_ids=frozenset(),
            now=REF_NOW,
            redis_client=rc,
        )
    )
    assert res_open["proposed_count"] == 1
    deck_id = res_open["deck_id"]
    assert deck_id.startswith("kit-deck-")
    assert f"{cp_task.CONTAINER_PREVIEWS_DECK_KEY_PREFIX}{deck_id}" in rc.store


def test_taste_harm_guards_zero_ellipsis_chronological_matrix_and_natural_headlines():
    """Enforces taste/harm guard, zero '...', chronological 'YY grid columns, and natural headlines."""
    from app.utils.kit_container_page_builder import _build_scoreboard_grid_section

    # 1. Scout taste & harm guards refuse inappropriate families cleanly
    harm_mkts = [
        _bin(99301 + i, f"Regional nuclear weapon test Before {m} 2027", 20 + i * 10, category="world", series="KXHARM", res_days=30 + i * 20)
        for i, m in enumerate(["Feb", "Mar", "Apr", "May", "Jun", "Jul"])
    ]
    assert propose_container_page_for_family("Regional Nuclear Tests", harm_mkts, now=REF_NOW)["refusal_reason"] == "refused_scout_taste_or_harm_guard"

    taste_mkts = [
        _bin(99351 + i, f"Apex Celebrity arrested or admits to another affair before {m} 2027", 20 + i * 10, category="culture", series="KXTASTE", res_days=30 + i * 20)
        for i, m in enumerate(["Feb", "Mar", "Apr", "May", "Jun", "Jul"])
    ]
    assert propose_container_page_for_family("Apex Celebrity", taste_mkts, now=REF_NOW)["refusal_reason"] == "refused_scout_taste_or_harm_guard"

    from app.utils.discover_fun_tags import check_fun_taste_guard
    assert check_fun_taste_guard("Person admits to another affair with a woman by Dec 31")[0] is False
    assert check_fun_taste_guard("Foreign affairs ministry summit held by Dec 31")[0] is True

    # 2. Dated rows in scoreboard_grid sort chronologically and keep explicit year (2026 / '26 before 2027)
    dated_grid_mkts = [
        _multi(99401, "Photon Chip Policy Decision in Mar 2027", {"Hold": 72, "Cut": 28}, category="tech", series="KXPH"),
        _multi(99402, "Photon Chip Policy Decision in Dec 2026", {"Hold": 54, "Cut": 46}, category="tech", series="KXPH"),
        _multi(99403, "Photon Chip Policy Decision in Mar 2026", {"Hold": 88, "Cut": 12}, category="tech", series="KXPH"),
    ]
    sb = _build_scoreboard_grid_section("photon", "TECH", dated_grid_mkts, set(), now=REF_NOW)
    assert sb is not None
    row_labels = [r["leading"][0]["text"] for r in sb["body"]["rows"]]
    assert len(row_labels) == 3, row_labels
    assert "Mar 2026" in row_labels[0] and "Dec 2026" in row_labels[1] and "Mar 2027" in row_labels[2], row_labels

    # 3. No broken verb-fragment headlines ('X Be Arrested', single-title 'X Join', 'The Fed publish')
    hl1, _ = derive_common_headline("Cobalt Director", ["Will Cobalt Director be arrested?", "Will Cobalt Director step down?"])
    assert hl1 == "Cobalt Director", hl1

    hl2, _ = derive_common_headline(None, ["Will Executive A join Board B?", "Will Board B announce Q4 earnings?"])
    assert hl2 is None or "join" not in hl2.lower(), hl2

    # 4. Zero '...' ellipsis anywhere in rendered cards
    ok_mkts = [
        _bin(99501, "Northstar Rocket orbital flight Before Feb 1 2027", 35, category="tech", series="KXNS", res_days=25),
        _bin(99502, "Northstar Rocket orbital flight Before Aug 1 2027", 74, category="tech", series="KXNS", res_days=190),
        _bin(99503, "Northstar Rocket payload above 40 tons", 58, category="tech", series="KXNS", res_days=90),
        _bin(99504, "Northstar Rocket payload above 80 tons", 21, category="tech", series="KXNS", res_days=90),
        _bin(99505, "Northstar Rocket fairing recovery test", 14, category="tech", series="KXNS", res_days=18),
        _bin(99506, "Northstar Rocket static fire test complete", 68, category="tech", series="KXNS", res_days=12),
    ]
    ok_res = propose_container_page_for_family("Northstar Rocket", ok_mkts, now=REF_NOW, kicker="TECH")
    assert ok_res["accepted"] is True, ok_res
    serialized = json.dumps(ok_res["page"])
    assert "\u2026" not in serialized and "..." not in serialized, serialized


def test_13696_rework_five_fable_fixes():
    """Pins all 5 fixes from Fable's #13696 review (comment-7162594660):

    1. Half-percent binary ties (0.135/0.865 -> 13%, 0.285/0.715 -> 28%) match
       `_format_market_detail(..., normalize_numbers=True)` (`rendered_percent`), not 14%/29%.
    2. `one_in_n` refuses multi-outcome markets so no unlabelled 15%/9% multi-outcome rows appear.
    3. Binary row labels & stat_captions keep full grammatical questions + `'on'` for single days.
    4. Section headings are 2–4 word topical titles (never drawing/scale names).
    5. Leftover families whose core is already in `covered_ids` are refused cleanly.
    """
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.routes.futures import _format_market_detail
    from app.utils.kit_container_page_builder import (
        _BANNED_SECTION_HEADINGS,
        _build_dated_tiles_section,
        _build_one_in_n_section,
        _build_shared_scale_section,
        _top_outcome_cell,
    )

    # 1. Exact rendered_percent parity on 0.135 / 0.865 (13%) and 0.285 / 0.715 (28%)
    half_135 = {
        "id": 99601,
        "name": "Will Exec A resign by Mar 31 2027?",
        "category": "tech",
        "source": "kalshi",
        "status": "open",
        "outcomes": [
            {"id": 6011, "name": "Yes", "current_probability": 0.135},
            {"id": 6012, "name": "No", "current_probability": 0.865},
        ],
    }
    half_285 = {
        "id": 99602,
        "name": "Will Exec A resign by Dec 31 2027?",
        "category": "tech",
        "source": "kalshi",
        "status": "open",
        "outcomes": [
            {"id": 6021, "name": "Yes", "current_probability": 0.285},
            {"id": 6022, "name": "No", "current_probability": 0.715},
        ],
    }
    for m_dict, expected_pct in ((half_135, 13), (half_285, 28)):
        orm = FuturesMarket(
            id=m_dict["id"],
            name=m_dict["name"],
            category="tech",
            llm_sport_category="tech",
            source="kalshi",
            external_id=f"KXHALF-{m_dict['id']}",
            status="open",
            created_at=REF_NOW,
            updated_at=REF_NOW,
            mutually_exclusive=True,
            market_metadata={},
        )
        orm.outcomes = [
            FuturesOutcome(
                id=o["id"],
                external_id=f"out-{o['id']}",
                name=o["name"],
                current_probability=o["current_probability"],
                opening_probability=o["current_probability"],
                rank=i + 1,
                is_winner=False,
                last_updated=REF_NOW,
            )
            for i, o in enumerate(m_dict["outcomes"])
        ]
        detail = _format_market_detail(orm, normalize_numbers=True)
        served_yes = next(o for o in detail["outcomes"] if o["name"] == "Yes")
        assert served_yes["rendered_percent"] == expected_pct
        _, _, built_pct = _top_outcome_cell(m_dict)
        assert built_pct == expected_pct, (m_dict["id"], built_pct, served_yes)

    dt_half = _build_dated_tiles_section("exec-a", "TECH", [half_135, half_285], set(), now=REF_NOW)
    assert dt_half is not None
    centers = [cell["marks"][0]["center_label"] for cell in dt_half["body"]["rows"][0]["cells"]]
    assert centers == ["13%", "28%"], centers

    # 2. one_in_n excludes multi-outcome markets (no unlabelled 15% / 9% field rows)
    oin_multi_and_bin = [
        _multi(99610, "What will central bank rate be at the end of 2027?", {"2.5%": 15, "2.75%": 15, "3.0%": 40, "Other": 30}, category="economics"),
        _multi(99611, "Total policy dissents in 2027?", {"Five": 9, "Four": 45, "Three": 46}, category="economics"),
        _bin(99612, "Will Exec B be TIME Person of the Year?", 8, category="tech"),
        _bin(99613, "Will Exec B join a cabinet panel?", 5, category="tech"),
    ]
    oin = _build_one_in_n_section("exec-b", "TECH", oin_multi_and_bin, set())
    assert oin is not None
    oin_mids = {it["provenance"]["market_id"] for it in oin["body"]["items"]}
    assert oin_mids == {99612, 99613}, oin_mids
    assert oin["common_headline"].lower() not in _BANNED_SECTION_HEADINGS
    assert oin["stat_caption"].startswith('"Will Exec B be TIME Person of the Year?" carries a 1 in 12 (8%) chance'), oin["stat_caption"]

    # 3. Single-day "on", no bare verb fragments ("testify", "be TIME...", "target"), and grammatical captions
    single_day = [
        _bin(99620, "Will Team Alpha reach Checkpoint Z on Nov 25, 2026?", 94, category="politics", res_days=2),
        _bin(99621, "Will Team Alpha reach Checkpoint Z by Dec 15, 2026?", 62, category="politics", res_days=21),
    ]
    dt_day = _build_dated_tiles_section("alpha", "POLITICS", single_day, set(), now=REF_NOW)
    assert dt_day is not None
    dt_lead_text = dt_day["body"]["rows"][0]["leading"][0]["text"]
    assert dt_lead_text.startswith("Will "), dt_lead_text
    assert "on Nov 25, 2026" in dt_day["stat_caption"], dt_day["stat_caption"]
    assert "sits at" not in dt_day["stat_caption"]

    # 4. Stage-speech / shared_scale topical 2-4 word headings + no "shared 0-100% scale"
    stage_mkts = [
        _bin(99630, 'Will Keynote Speaker say "Foundry" during presentation?', 82, category="tech", res_days=60),
        _bin(99631, 'Will Keynote Speaker say "Blackwell" during presentation?', 64, category="tech", res_days=60),
        _bin(99632, 'Will Keynote Speaker say "Robotics" during presentation?', 31, category="tech", res_days=60),
    ]
    ss = _build_shared_scale_section("speaker", "TECH", stage_mkts, set(), require_cluster=False)
    assert ss is not None
    assert 2 <= len(ss["common_headline"].split()) <= 4, ss["common_headline"]
    assert ss["common_headline"].lower() not in _BANNED_SECTION_HEADINGS
    assert "stage remarks" in ss["common_headline"].lower(), ss["common_headline"]
    assert "0–100% scale" not in ss["stat_caption"].lower() and "0-100%" not in ss["stat_caption"].lower()

    # Check end-to-end page never emits any banned drawing heading or broken verb stem
    all_page_mkts = [
        _bin(99640, "Will Meridian Corp publicly testify before Congress by Mar 31 2027?", 95, category="tech", res_days=120),
        _bin(99641, "Will Meridian Corp publicly testify before Congress by Jun 30 2027?", 96, category="tech", res_days=200),
        _bin(99642, 'Will Meridian Corp say "Inference" on stage?', 78, category="tech", res_days=80),
        _bin(99643, 'Will Meridian Corp say "Agentic" on stage?', 54, category="tech", res_days=80),
        _bin(99644, 'Will Meridian Corp say "Photonic" on stage?', 22, category="tech", res_days=80),
        _bin(99645, "Will Meridian Corp file antitrust appeal?", 11, category="tech", res_days=18),
        _bin(99646, "Will Meridian Corp enter defense partnership?", 7, category="tech", res_days=25),
    ]
    res_page = propose_container_page_for_family("Meridian Corp", all_page_mkts, now=REF_NOW, kicker="TECH")
    assert res_page["accepted"] is True, res_page
    for sec in res_page["page"]["sections"]:
        hl_low = sec["common_headline"].lower()
        assert hl_low not in _BANNED_SECTION_HEADINGS, sec
        assert 2 <= len(sec["common_headline"].split()) <= 4, sec
        assert "shared 0" not in sec["stat_caption"].lower(), sec
        assert not sec["stat_caption"].lower().startswith("meridian corp publicly testify"), sec

    # 5. Covered core refusal: leftover remainder markets whose core is in covered_ids are refused
    fed_overlap_mkts = [
        _multi(99701, "Central Bank Dec meeting decision", {"Hold": 85, "Cut": 15}, category="economics", series="KXFED", vol=500000),
        _multi(99702, "Central Bank Jan meeting decision", {"Hold": 70, "Cut": 30}, category="economics", series="KXFED", vol=400000),
        _multi(99703, "Central Bank Mar meeting decision", {"Hold": 60, "Cut": 40}, category="economics", series="KXCBX", vol=30000),
        _multi(99704, "Central Bank Apr meeting decision", {"Hold": 55, "Cut": 45}, category="economics", series="KXCBX", vol=25000),
        _bin(99705, "Central Bank cuts before Jun 30 2027", 48, category="economics", series="KXCBY", res_days=200, vol=10000),
        _bin(99706, "Central Bank cuts before Sep 30 2027", 72, category="economics", series="KXCBY", res_days=300, vol=9000),
        _bin(99707, "Central Bank chair replaced in 2027", 12, category="economics", series="KXCBZ", res_days=20, vol=8000),
        _bin(99708, "Central Bank dissents exceed 3", 9, category="economics", series="KXCBZ", res_days=25, vol=7000),
    ]
    out_overlap = propose_top_containers(
        fed_overlap_mkts,
        covered_ids={99701, 99702},
        now=REF_NOW,
        max_proposals=5,
        audit_top_n=10,
    )
    assert out_overlap["count"] == 0, out_overlap
    assert any(
        a.get("refusal_reason") == "refused_core_already_in_public_set"
        for a in out_overlap["ranked_audit"]
    ), out_overlap["ranked_audit"]

    # Also test topic_stem covered-core tie-breaker branch (no series grouping, equal volume)
    stem_only_mkts = [
        _bin(99721, "Will Meridian Corp announce merger before Q2?", 60, category="tech", res_days=40, vol=10000),
        _bin(99722, "Will Meridian Corp spin off cloud unit?", 45, category="tech", res_days=60, vol=10000),
        _bin(99723, "Will Meridian Corp buy chip startup?", 30, category="tech", res_days=90, vol=10000),
        _bin(99724, "Will Meridian Corp move HQ to Austin?", 20, category="tech", res_days=120, vol=10000),
        _bin(99725, "Will Meridian Corp split stock in 2027?", 15, category="tech", res_days=150, vol=10000),
        _bin(99726, "Will Meridian Corp change auditor?", 10, category="tech", res_days=180, vol=10000),
    ]
    out_stem_overlap = propose_top_containers(
        stem_only_mkts,
        covered_ids={99721},
        now=REF_NOW,
        max_proposals=5,
        audit_top_n=10,
    )
    assert out_stem_overlap["count"] == 0, out_stem_overlap
    assert any(
        a.get("refusal_reason") == "refused_core_already_in_public_set"
        for a in out_stem_overlap["ranked_audit"]
    ), out_stem_overlap["ranked_audit"]

    # 6. Additional Nov 26 live-run rework guards (Point 2/3/4 + plain_bar_stack + twin dedup)
    from app.utils.kit_container_page_builder import (
        _build_plain_bar_stack_section,
        _dedupe_twins,
        _derive_section_headline,
        _distinguishing_row_label,
        _is_binary_market,
        _template_signature,
    )

    partial_multi = {
        "id": 99801,
        "name": "When will Meridian Corp be added to the S&P 500?",
        "mutually_exclusive": False,
        "status": "open",
        "outcomes": [
            {"id": 1, "name": "June 30, 2027", "current_probability": 0.1055},
            {"id": 2, "name": "December 31, 2027", "current_probability": None},
        ],
    }
    assert _is_binary_market(partial_multi) is False
    oin_guarded = _build_one_in_n_section("meridian", "TECH", [
        partial_multi,
        _bin(99802, "Will Meridian Corp announce default before 2028?", 11, category="tech"),
        _bin(99803, "Will Meridian Corp enter robotics market in 2027?", 6, category="tech"),
    ], set())
    assert oin_guarded is not None
    assert 99801 not in {it["provenance"]["market_id"] for it in oin_guarded["body"]["items"]}

    lbl_subj = _distinguishing_row_label(
        "Meridian criminally charges Vendor Alpha by December 31, 2026",
        [
            "Meridian criminally charges Vendor Alpha by December 31, 2026",
            "Meridian criminally charges Vendor Beta by December 31, 2026",
            "Meridian fines Vendor Gamma over deal in 2026",
        ],
    )
    assert lbl_subj.startswith("Meridian "), lbl_subj

    when_multi = {
        "id": 99810,
        "name": "When will Meridian release Data Set 13?",
        "mutually_exclusive": False,
        "status": "open",
        "outcomes": [
            {"id": 10, "name": "Before 2027", "current_probability": 0.0685},
            {"id": 11, "name": "Before March", "current_probability": 0.03},
        ],
    }
    all_winner_multi = {
        "id": 99811,
        "name": "Who will attend Meridian Annual Summit?",
        "mutually_exclusive": False,
        "status": "open",
        "outcomes": [
            {"id": 20, "name": "Speaker One", "current_probability": 1.0, "is_winner": True},
            {"id": 21, "name": "Speaker Two", "current_probability": 1.0, "is_winner": True},
            {"id": 22, "name": "Speaker Three", "current_probability": 1.0, "is_winner": True},
        ],
    }
    assert _build_plain_bar_stack_section("meridian", "TECH", [when_multi], set(), now=REF_NOW) is None
    assert _build_plain_bar_stack_section("meridian", "TECH", [all_winner_multi], set(), now=REF_NOW) is None

    twin_a = _bin(99820, "Meridian fines Vendor Gamma over Groq deal in 2026", 8, group_id="polymarket:111", vol=100)
    twin_b = _bin(99821, "Will the Meridian fine Vendor Gamma over the Groq deal in 2026?", 5, group_id="polymarket:222", vol=5000)
    deduped = _dedupe_twins([twin_a, twin_b])
    assert len(deduped) == 1 and deduped[0]["id"] == 99821, deduped

    sig_lv = _template_signature({"name": "Will Meridian launch in Las Vegas, NV by December 31 2026?"})
    sig_cl = _template_signature({"name": "Will Meridian launch in Charlotte, NC by December 31 2026?"})
    assert sig_lv == sig_cl, (sig_lv, sig_cl)

    for variant_name in ("dated_tiles", "shared_scale", "countdown", "one_in_n", "plain_bar_stack"):
        hl_check = _derive_section_headline(variant_name, ["Arbitrary alpha beta", "Unrelated gamma delta"], "Meridian Outlook")
        assert 2 <= len(hl_check.split()) <= 4, hl_check
        assert hl_check.lower() not in {
            "target dates", "key storylines", "this month", "outside scenarios", "open questions",
        }, hl_check

    # 7. Surgical polish regression checks (possessive quote stem, dangling headline endings, subject dedup)
    from app.utils.container_proposer import _generic_stem_key

    stem_poss = _generic_stem_key({"name": 'Will Oxford\'s 2026 Word of the Year contain "slop"?'})
    assert stem_poss is None or (stem_poss[0] != "s_2026_word_of" and not stem_poss[0].startswith("s_")), stem_poss

    hl_against = _derive_section_headline(
        "dated_tiles",
        [
            "Meridian action against Sector A on Nov 26, 2026",
            "Meridian action against Sector B by Nov 30, 2026",
        ],
        "Meridian Outlook",
    )
    assert not hl_against.lower().endswith((" against", " publicly")), hl_against

    hl_visit = _derive_section_headline(
        "casting_sheet",
        ["Which countries will Meridian Exec visit in 2026?"],
        "Meridian Exec",
    )
    assert "will" not in hl_visit.lower().split(), hl_visit

    # Duplicate person/subject families (e.g. "Apex Prime" vs "Prime Outlook") collapse
    dup_person_mkts = [
        {**_bin(99901, "Will Apex Prime testify before Congress before Mar 31, 2027?", 82, category="politics", res_days=120, vol=80000), "external_id": None},
        {**_bin(99902, "Will Apex Prime testify before Congress before Jun 30, 2027?", 91, category="politics", res_days=200, vol=80000), "external_id": None},
        {**_bin(99903, "Will Apex Prime post statement on Tuesday?", 65, category="politics", res_days=10, vol=70000), "external_id": None},
        {**_bin(99904, "Will Apex Prime attend energy summit this month?", 48, category="politics", res_days=18, vol=70000), "external_id": None},
        {**_bin(99905, "Will Apex Prime win Nobel Prize in 2027?", 8, category="politics", res_days=180, vol=60000), "external_id": None},
        {**_bin(99906, "Will Apex Prime merge with BetaGroup in 2027?", 6, category="politics", res_days=220, vol=60000), "external_id": None},
        {**_bin(99921, "Will Prime testify before Senate before Mar 31, 2027?", 80, category="politics", res_days=120, vol=40000), "external_id": None},
        {**_bin(99922, "Will Prime testify before Senate before Jun 30, 2027?", 90, category="politics", res_days=200, vol=40000), "external_id": None},
        {**_bin(99923, "Will Prime sign border directive on Friday?", 62, category="politics", res_days=12, vol=30000), "external_id": None},
        {**_bin(99924, "Will Prime host foreign summit this month?", 45, category="politics", res_days=20, vol=30000), "external_id": None},
        {**_bin(99925, "Will Prime receive academy award in 2027?", 9, category="politics", res_days=180, vol=20000), "external_id": None},
        {**_bin(99926, "Will Prime relocate headquarters in 2027?", 5, category="politics", res_days=220, vol=20000), "external_id": None},
    ]
    out_dup_person = propose_top_containers(dup_person_mkts, now=REF_NOW, max_proposals=5, audit_top_n=10)
    assert out_dup_person["count"] == 1, out_dup_person["pages"]
    assert any(
        a.get("refusal_reason") == "refused_duplicate_page_subject"
        for a in out_dup_person["ranked_audit"]
    ), out_dup_person["ranked_audit"]


def test_13696_fable_nov26_rework_six_invariants():
    from app.utils.kit_container_page_builder import (
        _build_countdown_section,
        _build_dated_tiles_section,
        _build_plain_bar_stack_section,
        _build_shared_scale_section,
        _dedupe_twins,
        _derive_section_headline,
        _parse_date_marker,
    )

    # 1a. Cross-venue verb-s / -ies twin collapse inside dated_tiles (testifies vs testify)
    jensen_mkts = [
        _bin(88001, "Will Meridian Exec publicly testify before Congress before Dec 31, 2026?", 78, vol=50000),
        _bin(88002, "Will Meridian Exec publicly testify before Congress before Mar 31, 2027?", 94, vol=50000),
        _bin(88003, "Will Meridian Exec publicly testify before Congress before Jun 30, 2027?", 96, vol=50000),
        _bin(88004, "Meridian Exec publicly testifies before Congress by Dec 31, 2026", 77, vol=1000),
        _bin(88005, "Meridian Exec publicly testifies before Congress by Mar 31, 2027", 87, vol=1000),
        _bin(88006, "Meridian Exec publicly testifies before Congress by Jun 30, 2027", 91, vol=1000),
    ]
    dt_jensen = _build_dated_tiles_section("meridian-exec", "TECH", jensen_mkts, set(), now=REF_NOW)
    assert dt_jensen is not None
    assert len(dt_jensen["body"]["rows"]) == 1, dt_jensen["body"]["rows"]

    # 1b. Same-group_id binary submarkets collapse into multi-outcome contender parent
    multi_visit = {
        "id": 88010,
        "name": "Which countries will Meridian Explorer visit in 2026?",
        "group_id": "polymarket:703477",
        "mutually_exclusive": False,
        "status": "open",
        "volume_24h": 40000,
        "outcomes": [
            {"id": 1, "name": "Nordmark", "current_probability": 0.13},
            {"id": 2, "name": "Valoria", "current_probability": 0.12},
            {"id": 3, "name": "Kestrel", "current_probability": 0.09},
            {"id": 4, "name": "Borea", "current_probability": 0.08},
        ],
    }
    child_bins = [
        _bin(88011, "Will Meridian Explorer visit Nordmark in 2026?", 12, group_id="polymarket:703477", res_days=35),
        _bin(88012, "Will Meridian Explorer visit Valoria in 2026?", 11, group_id="polymarket:703477", res_days=35),
        _bin(88013, "Will Meridian Explorer visit Kestrel in 2026?", 8, group_id="polymarket:703477", res_days=35),
    ]
    collapsed = _dedupe_twins([multi_visit, *child_bins])
    assert [m["id"] for m in collapsed] == [88010], collapsed

    # 4. Single multi-outcome market names the market and shows row lead % in caption
    pb_visit = _build_plain_bar_stack_section("meridian-explorer", "CULTURE", collapsed, set(), now=REF_NOW)
    assert pb_visit is not None
    assert pb_visit["common_headline"] == "Countries to Visit", pb_visit
    assert "milestones" not in pb_visit["common_headline"].lower()
    assert pb_visit["stat_caption"] == "Nordmark is the most likely at 13%", pb_visit["stat_caption"]

    # 2. Inverted numeric threshold rungs rejected ($1.5T reading higher than $1.4T)
    inv_mkts = [
        _bin(88020, "Will Meridian Labs's valuation hit (HIGH) $1.5T by Mar 31, 2027?", 3, vol=100),
        _bin(88021, "Will Meridian Labs's valuation hit (HIGH) $1.5T by Jun 30, 2027?", 7, vol=100),
        _bin(88022, "Will Meridian Labs's valuation hit (HIGH) $1.4T by Mar 31, 2027?", 1, vol=5000),
        _bin(88023, "Will Meridian Labs's valuation hit (HIGH) $1.4T by Jun 30, 2027?", 5, vol=5000),
        _bin(88024, "Will Meridian Labs IPO by Mar 31, 2027?", 1, vol=9000),
        _bin(88025, "Will Meridian Labs IPO by Jun 30, 2027?", 16, vol=9000),
    ]
    dt_inv = _build_dated_tiles_section("meridian-labs", "TECH", inv_mkts, set(), now=REF_NOW)
    assert dt_inv is not None
    row_labels_inv = [r["leading"][0]["text"] for r in dt_inv["body"]["rows"]]
    assert not (
        any("$1.5T" in lbl for lbl in row_labels_inv)
        and any("$1.4T" in lbl for lbl in row_labels_inv)
    ), row_labels_inv

    # Valid non-inverted lower/upper token rungs remain intact in shared_scale
    tok_mkts = [
        _bin(88030, "Will Meridian Labs's frontier output token price be at or below $15 in 2026?", 23),
        _bin(88031, "Will Meridian Labs's frontier output token price be at or below $10 in 2026?", 12),
        _bin(88032, "Will Meridian Labs's frontier output token price be at or above $50 in 2026?", 15),
        _bin(88033, "Will Meridian Labs's frontier output token price be at or above $75 in 2026?", 6),
    ]
    ss_tok = _build_shared_scale_section("meridian-labs", "TECH", tok_mkts, set())
    assert ss_tok is not None and len(ss_tok["body"]["series"]) == 4

    # 3. Date tiles sort Nov 26 < Nov 28 < Nov 29 (no clamping at day 28)
    d28 = _parse_date_marker("on Nov 28, 2026", default_year=2026)
    d29 = _parse_date_marker("on Nov 29, 2026", default_year=2026)
    assert d28 is not None and d29 is not None and d28["sort_dt"] < d29["sort_dt"]
    nov_mkts = [
        _bin(88040, "Meridian activity on Nov 26, 2026", 91),
        _bin(88041, "Meridian activity on Nov 29, 2026", 85),
        _bin(88042, "Meridian activity on Nov 28, 2026", 84),
    ]
    dt_nov = _build_dated_tiles_section("meridian-nov", "WORLD", nov_mkts, set(), now=REF_NOW)
    assert dt_nov is not None
    tile_periods = [c["marks"][0]["top_label"] for c in dt_nov["body"]["rows"][0]["cells"]]
    assert tile_periods == ["on Nov 26 '26", "on Nov 28 '26", "on Nov 29 '26"], tile_periods

    # 5a. 100%-row-match requirement: 1/4 match cannot produce "Upcoming Launches"
    hl_mix = _derive_section_headline(
        "countdown",
        [
            "Region action against Sector A by November 30, 2026",
            "Will Region make Official C a citizen?",
            "Will Region launch an operation in Sector B by December 31, 2026?",
            "Partner agrees to a new trade deal with Region before 2027",
        ],
        "Region Outlook",
        rows_meta=[
            {"days": 4, "pct": 5, "deadline_dt": datetime(2026, 11, 30, tzinfo=timezone.utc)},
            {"days": 35, "pct": 18, "deadline_dt": datetime(2026, 12, 31, tzinfo=timezone.utc)},
            {"days": 35, "pct": 7, "deadline_dt": datetime(2026, 12, 31, tzinfo=timezone.utc)},
            {"days": 35, "pct": 5, "deadline_dt": datetime(2026, 12, 31, tzinfo=timezone.utc)},
        ],
    )
    assert hl_mix == "Through Dec 2026", hl_mix
    hl_same_dec = _derive_section_headline(
        "countdown",
        [
            "Region action against Sector A by December 31, 2026",
            "Will Region make Official C a citizen by December 31, 2026?",
            "Will Region launch an operation in Sector B by December 31, 2026?",
        ],
        "Region Outlook",
        rows_meta=[
            {"days": 35, "pct": 18, "deadline_dt": datetime(2026, 12, 31, tzinfo=timezone.utc)},
            {"days": 35, "pct": 7, "deadline_dt": datetime(2026, 12, 31, tzinfo=timezone.utc)},
            {"days": 35, "pct": 5, "deadline_dt": datetime(2026, 12, 31, tzinfo=timezone.utc)},
        ],
    )
    assert hl_same_dec == "By December 31", hl_same_dec

    # Dec 31 of NEXT year must not claim "By December 31"
    hl_2027 = _derive_section_headline(
        "dated_tiles",
        ["Senator exits role", "Senator joins new venture"],
        "Senator Outlook",
        rows_meta=[
            {"pct": 29, "deadline_dt": datetime(2027, 12, 31, tzinfo=timezone.utc)},
            {"pct": 11, "deadline_dt": datetime(2027, 12, 31, tzinfo=timezone.utc)},
        ],
    )
    assert hl_2027 == "Through Dec 2027", hl_2027

    # 5b. Countdown preserves 100%-true "Public Remarks", and cleanly splits out "Public Praise" when already used
    praise_mix_mkts = [
        _bin(88050, "Will Senator Alpha publicly praise Leader B by November 30, 2026?", 43, res_days=4),
        _bin(88051, "Will Senator Alpha publicly insult Host C by November 30, 2026?", 20, res_days=4),
        _bin(88052, "Will Senator Alpha publicly praise Leader D by November 30, 2026?", 17, res_days=4),
        _bin(88053, "Will Senator Alpha publicly praise Artist E by November 30, 2026?", 13, res_days=4),
    ]
    cd_remarks = _build_countdown_section("senator-alpha", "POLITICS", praise_mix_mkts, set(), now=REF_NOW)
    assert cd_remarks is not None and cd_remarks["common_headline"] == "Public Remarks", cd_remarks
    cd_praise = _build_countdown_section(
        "senator-alpha",
        "POLITICS",
        praise_mix_mkts,
        set(),
        now=REF_NOW,
        seen_headlines={"public remarks"},
    )
    assert cd_praise is not None
    assert cd_praise["common_headline"] == "Public Praise", cd_praise
    assert all(
        "praise" in it["marks"][0]["text"].lower()
        for it in cd_praise["body"]["items"]
    ), cd_praise["body"]["items"]

    # 6. Full page satisfies audit_container_page_invariants == [] & catches crafted violations
    full_mkts = [
        _bin(88060, "Will Meridian Senator publicly insult Target A on Nov 26, 2026?", 72, res_days=2),
        _bin(88061, "Will Meridian Senator publicly insult Target A on Nov 28, 2026?", 70, res_days=4),
        _bin(88062, "Will Meridian Senator publicly insult Target A on Nov 29, 2026?", 77, res_days=5),
        _bin(88063, "Will Meridian Senator publicly insult Guest One by December 31, 2026?", 61, res_days=60),
        _bin(88064, "Will Meridian Senator publicly insult Guest Two by December 31, 2026?", 42, res_days=60),
        _bin(88065, "Will Meridian Senator publicly insult Guest Three by December 31, 2026?", 28, res_days=60),
        _bin(88066, "Will Meridian Senator publicly praise Ally One by November 30, 2026?", 43, res_days=4),
        _bin(88067, "Will Meridian Senator publicly praise Ally Two by November 30, 2026?", 17, res_days=4),
        _bin(88068, "Will Meridian Senator publicly praise Ally Three by November 30, 2026?", 13, res_days=4),
        _bin(88069, "Will Meridian Senator attend Forum X in 2027?", 12, res_days=120),
        _bin(88070, "Will Meridian Senator publish memoir in 2027?", 8, res_days=120),
    ]
    full_res = propose_container_page_for_family("Meridian Senator", full_mkts, now=REF_NOW)
    assert full_res["accepted"], full_res
    assert audit_container_page_invariants(
        full_res["page"],
        markets_by_id={m["id"]: m for m in full_mkts},
    ) == []

    # Craft violation checks for audit_container_page_invariants
    bad_page = {
        "title": "Donald Senator",
        "snapshot_captured_at": REF_NOW.isoformat(),
        "sections": [
            {
                "id": "s1",
                "variant": "countdown",
                "common_headline": "Public Remarks",
                "stat_caption": "cap",
                "body": {"items": []},
            },
            {
                "id": "s2",
                "variant": "shared_scale",
                "common_headline": "Donald Public Remarks",
                "stat_caption": "cap",
                "body": {"series": []},
            },
        ],
    }
    bad_v = audit_container_page_invariants(bad_page)
    assert any("repeats" in v for v in bad_v), bad_v


def test_13696_fable_nov27_seven_fixes_and_must_not_headings(monkeypatch):
    """Regression suite for all 7 Fable Nov 27 review items + explicit must-not headings."""
    import asyncio
    from types import SimpleNamespace
    from app.routes import containers as containers_route
    from app.utils.kit_container_page_builder import (
        _build_casting_sheet_section,
        _build_dated_tiles_section,
        _build_plain_bar_stack_section,
        _build_scoreboard_grid_section,
        _dedupe_twins,
        _derive_section_headline,
        audit_container_page_invariants,
        propose_container_page_for_family,
    )

    # Points 1 & 4: Must-not list for overbroad single words & mismatched themes.
    must_not_cases = [
        (["Will President approval rating be at least 36.0 on Nov 27?", "Will President approval rating be at least 37.0 on Nov 27?"], {"executive actions"}),
        (["Phase 3 clinical trial announced", "New clinical trial for RSV vaccine"], {"legal & enforcement"}),
        (["Will league players' strike last into May?", "Owners respond to players' strike"], {"conflict & talks", "military action"}),
        (["Will Exec post again on X in 2026?", "Will Exec be Google most searched CEO in 2026?"], {"public appearances"}),
        (["Will team win NBA championship after trade cut?", "Will Fed dissent hold rate?", "Will Senate confirm board nominee?"], set()),
        (["Will Exec speak at summit?", "What will happen to hardware device?"], {"public statements", "hardware & devices"}),
        (["Will Star chart higher on Spotify?", "Will Rocket launch in July?"], {"charts & releases", "upcoming launches"}),
    ]
    for titles, forbidden in must_not_cases:
        hl = _derive_section_headline("shared_scale", titles, "Subject Outlook")
        assert hl.lower() not in forbidden, (titles, hl)

    # Verify Trump approval-rating rows get "Nov 27 Approval Rating" instead of "Executive Actions".
    trump_approval = _derive_section_headline(
        "shared_scale",
        [
            "Will Donald Trump's approval rating be at least 36.0 on Nov 27?",
            "Will Donald Trump's approval rating be at least 37.0 on Nov 27?",
            "Will Donald Trump's approval rating be at least 38.0 on Nov 27?",
        ],
        "Donald Trump",
    )
    assert trump_approval == "Nov 27 Approval Rating", trump_approval

    # Point 2: Cross-venue twins ("before Jan 1, 2027" == "by December 31, 2026") collapse & combine probability.
    openai_mkts = [
        {**_bin(77001, "Will OpenAI or Anthropic announce recursive self-improvement before Jan 1, 2027?", 18, res_days=400, vol=50000), "source": "kalshi"},
        {**_bin(77002, "Will OpenAI or Anthropic announce recursive self-improvement by December 31, 2026?", 13, res_days=35, vol=30000), "source": "polymarket"},
        {**_bin(77003, "Will OpenAI or Anthropic announce recursive self-improvement before Jan 1, 2028?", 44, res_days=700, vol=40000), "source": "kalshi"},
        {**_bin(77004, "Will OpenAI IPO valuation hit $1T+ in 2026?", 98, res_days=20, vol=20000), "source": "kalshi"},
        {**_bin(77005, "Will OpenAI release GPT-6 in 2027?", 61, res_days=120, vol=15000), "source": "kalshi"},
        {**_bin(77006, "Will OpenAI acquire Windsurf in 2026?", 7, res_days=30, vol=15000), "source": "kalshi"},
        {**_bin(77007, "Will OpenAI face antitrust lawsuit in 2027?", 11, res_days=220, vol=15000), "source": "kalshi"},
    ]
    from app.utils.kit_container_page_builder import _pct_int, _sources_count
    twins_seen: list[dict] = []
    deduped_ai = _dedupe_twins(openai_mkts, unlinked_twins_out=twins_seen)
    rsi_rows = [m for m in deduped_ai if "recursive" in m["name"].lower() and "2028" not in m["name"]]
    assert len(rsi_rows) == 1, rsi_rows
    # Never average unlinked twins (0.18 vs 0.13): preserve lead market 77001's exact 18% and log unlinked pair.
    assert rsi_rows[0]["id"] == 77001, rsi_rows[0]
    assert _pct_int(rsi_rows[0]["outcomes"][0]["current_probability"]) == 18, rsi_rows[0]
    assert rsi_rows[0]["outcomes"][0]["current_probability"] == 0.18, rsi_rows[0]
    assert _sources_count(rsi_rows[0]) == 1, rsi_rows[0]
    assert len(twins_seen) == 1 and twins_seen[0]["lead_market_id"] == 77001 and twins_seen[0]["dropped_market_id"] == 77002, twins_seen
    page_ai = propose_container_page_for_family("OpenAI Outlook", openai_mkts, now=REF_NOW)
    assert page_ai["accepted"], page_ai
    assert len(page_ai.get("unlinked_twins") or []) == 1, page_ai.get("unlinked_twins")
    assert audit_container_page_invariants(page_ai["page"], markets_by_id={m["id"]: m for m in openai_mkts}) == []

    # Point 3: Scoreboard grid with 2 deadlines uses "Deadline" leading column, uniform dates, and market-naming headline.
    cities = ["Druzhkivka", "Pokrovsk", "Kupiansk", "Toretsk"]
    ru_mkts = [
        {
            "id": 77101,
            "name": "Which cities will Russia capture by December 31, 2026?",
            "mutually_exclusive": False,
            "status": "open",
            "volume_24h": 25000,
            "outcomes": [{"id": i + 1, "name": c, "current_probability": p} for i, (c, p) in enumerate(zip(cities, [0.30, 0.25, 0.20, 0.15]))],
        },
        {
            "id": 77102,
            "name": "Which cities will Russia capture by June 30, 2027?",
            "mutually_exclusive": False,
            "status": "open",
            "volume_24h": 25000,
            "outcomes": [{"id": i + 10, "name": c, "current_probability": p} for i, (c, p) in enumerate(zip(cities, [0.45, 0.30, 0.18, 0.12]))],
        },
    ]
    sb = _build_scoreboard_grid_section("russia-outlook", "GEOPOLITICS", ru_mkts, set(), now=REF_NOW, family_headline="Russia Outlook")
    assert sb is not None
    assert sb["common_headline"] != "Contender Odds", sb["common_headline"]
    assert sb["body"]["leading_label"] == "Deadline", sb["body"]["leading_label"]
    row_dates = [r["leading"][0]["text"] for r in sb["body"]["rows"]]
    assert row_dates == ["By Dec 31, 2026", "By Jun 30, 2027"], row_dates
    assert "leads June" not in sb["stat_caption"] and sb["common_headline"].lower() in sb["stat_caption"].lower(), sb["stat_caption"]

    # Point 5: Deadline tiles always say "by"/"before"; single-day tiles always say "on".
    dl_mkts = [
        _bin(77201, "Out as NVIDIA CEO again Dec 31, 2026?", 22, vol=10000),
        _bin(77202, "Out as NVIDIA CEO again Jun 30, 2027?", 41, vol=10000),
        _bin(77203, "Will TechExec join SpaceX Dec 31, 2026?", 18, vol=9000),
        _bin(77204, "Will TechExec join SpaceX Jun 30, 2027?", 31, vol=9000),
    ]
    dt_dl = _build_dated_tiles_section("techexec", "TECH", dl_mkts, set(), now=REF_NOW)
    assert dt_dl is not None
    for row in dt_dl["body"]["rows"]:
        for cell in row["cells"]:
            lbl = cell["marks"][0]["top_label"].lower()
            assert lbl.startswith(("by ", "before ")), cell

    # Point 6: Preview route returns status="error" on Redis error / malformed JSON (never "not_built_yet").
    async def _admin_ok(*_a, **_kw):
        return True

    class BrokenRedis:
        def get(self, _k):
            raise RuntimeError("redis down")

    class CorruptRedis:
        def get(self, _k):
            return "{not valid json"

    monkeypatch.setattr("app.routes.admin_utils._check_admin_auth", _admin_ok)
    req = SimpleNamespace(headers={}, query_params={})

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: BrokenRedis())
    err1 = asyncio.run(containers_route.get_kit_container_pages_preview(request=req, db=None))
    assert err1["status"] == "error" and err1["pages"] == []

    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: CorruptRedis())
    err2 = asyncio.run(containers_route.get_kit_container_pages_preview(request=req, db=None))
    assert err2["status"] == "error" and err2["pages"] == []

    # Point 7: Clean captions on single-market fields and non-competing binary rows.
    dress_mkt = {
        "id": 77301,
        "name": "Taylor Swift: Wedding Dress",
        "status": "open",
        "volume_24h": 30000,
        "outcomes": [
            {"id": 1, "name": "Christian Dior", "current_probability": 0.34},
            {"id": 2, "name": "Oscar de la Renta", "current_probability": 0.25},
            {"id": 3, "name": "Vera Wang", "current_probability": 0.21},
            {"id": 4, "name": "Alexander McQueen", "current_probability": 0.20},
        ],
    }
    pb_dress = _build_plain_bar_stack_section("taylor-swift", "CULTURE", [dress_mkt], set(), now=REF_NOW, family_headline="Taylor Swift")
    assert pb_dress is not None
    assert "leads wedding dress" not in pb_dress["stat_caption"].lower(), pb_dress["stat_caption"]
    assert "34%" in pb_dress["stat_caption"]
    assert _build_casting_sheet_section is not None

    # Regression: never strip shared prefix+year into a dangling preposition fragment ("... in the U.S. in").
    from app.utils.kit_container_page_builder import _distinguishing_row_label
    sibling_qs = [
        "Will there be at least 6500 widget shipments in the U.S. in 2026?",
        "Will there be at least 7000 widget shipments in the U.S. in 2026?",
        "Will there be at least 6200 widget shipments in the U.S. by November 30, 2026?",
    ]
    for q in sibling_qs:
        lbl = _distinguishing_row_label(q, sibling_qs)
        assert not lbl.lower().endswith((" in", " by", " on", " at")), lbl
        assert lbl.startswith("Will "), lbl


def test_13696_fable_nov27_1007am_four_review_fixes() -> None:
    """Fable 10:07 AM PT 4-point review: no twin averaging, midpoint ladder rungs, non-excl group fold, copy fixes."""
    from app.utils.kit_container_page_builder import _distinguishing_row_label

    # Point 2: Dated 5-rung ladder keeps the 50%-straddling rungs (including midpoint 38.0 even with highest ID),
    # and uses "stands at" (never "sits at") in dated_tiles caption.
    ladder_mkts = [
        _bin(88010, "Will Widget approval rating reach 37.0 or higher by Dec 31, 2026?", 81, series="KXWIDGET", res_days=37),
        _bin(88011, "Will Widget approval rating reach 39.0 or higher by Dec 31, 2026?", 5, series="KXWIDGET", res_days=37),
        _bin(88012, "Will Widget approval rating reach 40.0 or higher by Dec 31, 2026?", 3, series="KXWIDGET", res_days=37),
        _bin(88013, "Will Widget approval rating reach 36.0 or higher by Dec 31, 2026?", 93, series="KXWIDGET", res_days=37),
        _bin(88014, "Will Widget approval rating reach 38.0 or higher by Dec 31, 2026?", 19, series="KXWIDGET", res_days=37),
        _bin(88015, "Will Widget approval rating reach 37.0 or higher by Nov 30, 2026?", 98, series="KXWIDGET", res_days=6),
        _bin(88016, "Will Widget approval rating reach 39.0 or higher by Nov 30, 2026?", 2, series="KXWIDGET", res_days=6),
        _bin(88017, "Will Widget approval rating reach 40.0 or higher by Nov 30, 2026?", 1, series="KXWIDGET", res_days=6),
        _bin(88018, "Will Widget approval rating reach 36.0 or higher by Nov 30, 2026?", 99, series="KXWIDGET", res_days=6),
        _bin(88019, "Will Widget approval rating reach 38.0 or higher by Nov 30, 2026?", 12, series="KXWIDGET", res_days=6),
        _bin(88020, "Will Widget Corp sign trade deal in 2026?", 42, series="KXWIDGET", res_days=37),
        _bin(88021, "Will Widget Corp pass bill by Q1 2027?", 64, series="KXWIDGET", res_days=120),
        _bin(88022, "Will Widget Corp hold summit in 2027?", 28, series="KXWIDGET", res_days=150),
        {
            "id": 88023,
            "source": "kalshi",
            "name": "Who will Widget Corp pick as CEO next?",
            "category": "tech",
            "mutually_exclusive": True,
            "resolution_date": REF_NOW + timedelta(days=90),
            "volume_24h": 40000,
            "outcomes": [
                {"id": 88301, "name": "Alice Smith", "current_probability": 0.48},
                {"id": 88302, "name": "Bob Jones", "current_probability": 0.31},
                {"id": 88303, "name": "Carol Lee", "current_probability": 0.14},
            ],
        },
        _bin(88024, "Will Widget Corp launch new chip before Dec 31, 2026?", 11, series="KXWIDGET", res_days=37),
    ]
    ladder_page = propose_container_page_for_family("Widget Outlook", ladder_mkts, now=REF_NOW)
    assert ladder_page["accepted"], ladder_page
    dated_secs = [s for s in ladder_page["page"]["sections"] if s["variant"] == "dated_tiles"]
    assert dated_secs, ladder_page["page"]["sections"]
    tile_texts = [
        f"{(r.get('leading') or [{}])[0].get('text', '')} "
        + " ".join((m.get("center_label") or "") for c in (r.get("cells") or []) for m in (c.get("marks") or []))
        for r in dated_secs[0]["body"]["rows"]
    ]
    assert any("38.0" in t or "19%" in t for t in tile_texts), tile_texts
    assert "stands at" in dated_secs[0]["stat_caption"].lower(), dated_secs[0]["stat_caption"]
    assert "sits at" not in dated_secs[0]["stat_caption"].lower(), dated_secs[0]["stat_caption"]

    # Point 3: Non-exclusive multi-outcome parent + same-group_id sibling binaries unify into ONE section,
    # sorted descending by probability, preserving exact provenance and using "most likely".
    non_excl_mkts = [
        {
            "id": 89001,
            "source": "polymarket",
            "group_id": "polymarket:exp_703",
            "name": "Which cities will Mars Rover visit in 2026?",
            "category": "science",
            "mutually_exclusive": False,
            "resolution_date": REF_NOW + timedelta(days=60),
            "volume_24h": 50000,
            "max_movement_24h": 0.04,
            "outcomes": [
                {"id": 9101, "name": "Tokyo", "current_probability": 0.56},
                {"id": 9102, "name": "Berlin", "current_probability": 0.09},
                {"id": 9103, "name": "Cairo", "current_probability": 0.06},
            ],
        },
        _bin(89002, "Will Mars Rover visit Seoul in 2026?", 22, category="science", series="KXMARS", group_id="polymarket:exp_703", res_days=60, vol=30000),
        _bin(89003, "Will Mars Rover visit Toronto in 2026?", 15, category="science", series="KXMARS", group_id="polymarket:exp_703", res_days=60, vol=25000),
        _bin(89004, "Will Mars Rover visit Sydney in 2026?", 8, category="science", series="KXMARS", group_id="polymarket:exp_703", res_days=60, vol=20000),
        _bin(89010, "Will Mars Rover find ice by Nov 30, 2026?", 68, category="science", series="KXMARS", res_days=6, vol=18000),
        _bin(89011, "Will Mars Rover launch upgrade by Nov 30, 2026?", 9, category="science", series="KXMARS", res_days=6, vol=16000),
        _bin(89012, "Will Mars Rover deploy drill by Dec 31, 2026?", 31, category="science", series="KXMARS", res_days=37, vol=15000),
        _bin(89013, "Will Mars Rover transmit 4k video by Dec 31, 2026?", 52, category="science", series="KXMARS", res_days=37, vol=14000),
        {
            "id": 89014,
            "source": "kalshi",
            "name": "When will Mars Rover reach ridge?",
            "category": "science",
            "mutually_exclusive": True,
            "resolution_date": REF_NOW + timedelta(days=180),
            "volume_24h": 22000,
            "outcomes": [
                {"id": 9201, "name": "By March 2027", "current_probability": 0.35},
                {"id": 9202, "name": "By June 2027", "current_probability": 0.62},
                {"id": 9203, "name": "By December 2027", "current_probability": 0.88},
            ],
        },
    ]
    non_excl_page = propose_container_page_for_family("Mars Rover Outlook", non_excl_mkts, now=REF_NOW)
    assert non_excl_page["accepted"], non_excl_page
    visit_secs = [
        s for s in non_excl_page["page"]["sections"]
        if any(
            m.get("text") in {"Tokyo", "Seoul", "Toronto"}
            for it in (s.get("body", {}).get("items") or [])
            for m in (it.get("marks") or [])
        )
    ]
    assert len(visit_secs) == 1, visit_secs
    visit_items = visit_secs[0]["body"]["items"]
    visit_labels = [next((m["text"] for m in it["marks"] if m.get("mark") == "word"), "") for it in visit_items]
    assert visit_labels[:4] == ["Tokyo", "Seoul", "Toronto", "Berlin"], visit_labels
    assert "most likely" in visit_secs[0]["stat_caption"].lower(), visit_secs[0]["stat_caption"]
    assert "favorite" not in visit_secs[0]["stat_caption"].lower(), visit_secs[0]["stat_caption"]
    seoul_item = next(
        it for it in visit_items
        if any(m.get("text") == "Seoul" for m in (it.get("marks") or []))
    )
    assert seoul_item["provenance"]["market_id"] == 89002, seoul_item
    assert audit_container_page_invariants(non_excl_page["page"], markets_by_id={m["id"]: m for m in non_excl_mkts}) == []

    # Point 4a: Preserve dotted initialism "U.S." in derive_common_headline and discover_candidate_families.
    us_mkts = [
        _bin(90001, "Will U.S. GDP growth exceed 3% by Nov 30, 2026?", 22, series="KXUS", res_days=6),
        _bin(90002, "Will U.S. GDP growth exceed 3% by Dec 31, 2026?", 45, series="KXUS", res_days=35),
        _bin(90003, "Will U.S. unemployment stay under 4.5% by Nov 30, 2026?", 61, series="KXUS", res_days=6),
        _bin(90004, "Will U.S. unemployment stay under 4.5% by Dec 31, 2026?", 55, series="KXUS", res_days=35),
        _bin(90005, "Will U.S. launch digital treasury note in 2027?", 9, series="KXUS", res_days=180),
        _bin(90008, "Will U.S. sign tariff treaty before 2028?", 11, series="KXUS", res_days=240),
        {
            "id": 90006,
            "source": "kalshi",
            "name": "Who will lead U.S. Central Desk next?",
            "category": "economics",
            "mutually_exclusive": True,
            "resolution_date": REF_NOW + timedelta(days=90),
            "volume_24h": 42000,
            "outcomes": [
                {"id": 90301, "name": "Jane Doe", "current_probability": 0.44},
                {"id": 90302, "name": "Mark Smith", "current_probability": 0.29},
                {"id": 90303, "name": "Pat Lee", "current_probability": 0.17},
            ],
        },
        {
            "id": 90007,
            "source": "kalshi",
            "name": "When will U.S. balance the federal budget?",
            "category": "economics",
            "mutually_exclusive": True,
            "resolution_date": REF_NOW + timedelta(days=365),
            "volume_24h": 31000,
            "outcomes": [
                {"id": 90311, "name": "2027", "current_probability": 0.11},
                {"id": 90312, "name": "2028", "current_probability": 0.23},
                {"id": 90313, "name": "2029", "current_probability": 0.38},
            ],
        },
    ]
    fams, _ = discover_candidate_families(us_mkts, now=REF_NOW, min_markets=5)
    us_fams = [f for f in fams if "u.s." in f.label.lower()]
    assert us_fams, [f.label for f in fams]
    assert any("U.S." in f.label and "U.S " not in f.label for f in us_fams), [f.label for f in us_fams]
    us_page = propose_container_page_for_family("U.S.", us_mkts, now=REF_NOW)
    assert us_page["accepted"], us_page
    assert us_page["page"]["title"].startswith("U.S."), us_page["page"]["title"]

    # Point 4b: Never emit "By December 31" when grouped binaries mix November 30 and December 31 deadlines.
    mixed_date_mkts = [
        _bin(91001, "Will Nimbus build 50 towers by Nov 30, 2026?", 32, series="KXNIMB", res_days=6),
        _bin(91002, "Will Nimbus ship 10k units by Nov 30, 2026?", 71, series="KXNIMB", res_days=6),
        _bin(91003, "Will Nimbus pass safety review by Dec 31, 2026?", 88, series="KXNIMB", res_days=37),
        _bin(91004, "Will Nimbus sign airport deal before Jan 1, 2027?", 14, series="KXNIMB", res_days=37),
        _bin(91005, "Will Nimbus open factory in 2027?", 8, series="KXNIMB", res_days=140),
        _bin(91006, "Will Nimbus acquire supplier by Q3 2027?", 6, series="KXNIMB", res_days=240),
        {
            "id": 91007,
            "source": "kalshi",
            "name": "Who will Nimbus pick as chair?",
            "category": "tech",
            "mutually_exclusive": True,
            "resolution_date": REF_NOW + timedelta(days=90),
            "volume_24h": 35000,
            "outcomes": [
                {"id": 91301, "name": "Nora Chen", "current_probability": 0.51},
                {"id": 91302, "name": "Omar Patel", "current_probability": 0.27},
                {"id": 91303, "name": "Dana Fox", "current_probability": 0.14},
            ],
        },
        _bin(91008, "Will Nimbus reach $20B revenue before Jan 1, 2027?", 41, series="KXNIMB", res_days=37),
        _bin(91009, "Will Nimbus reach $20B revenue before Nov 30, 2026?", 29, series="KXNIMB", res_days=6),
    ]
    mixed_page = propose_container_page_for_family("Nimbus Outlook", mixed_date_mkts, now=REF_NOW)
    assert mixed_page["accepted"], mixed_page
    for sec in mixed_page["page"]["sections"]:
        assert sec.get("common_headline") != "By December 31", sec

    # Point 4c: Keep "at or" intact on threshold sibling labels ("At or below $15", never "Below $15").
    thresh_qs = [
        "Will Cobalt futures settle at or below $15 by Dec 31?",
        "Will Cobalt futures settle at or below $18 by Dec 31?",
        "Will Cobalt futures settle at or below $20 by Dec 31?",
    ]
    lbl15 = _distinguishing_row_label(thresh_qs[0], thresh_qs)
    assert "at or below $15" in lbl15.lower(), lbl15

    # Ensure no Condition 1 banned terms exist across all newly proposed pages.
    dumped = json.dumps([ladder_page["page"], non_excl_page["page"], us_page["page"], mixed_page["page"]]).lower()
    for term in _BANNED_TERMS:
        assert term not in dumped, term


def test_13696_fable_nov27_v5_four_guards(monkeypatch) -> None:
    """Fable 11:11 AM + 11:12 AM PT guards: full-title fallback, clean non-excl captions, nightly-only deck, partial coverage."""
    from types import SimpleNamespace
    from app.routes import containers as containers_route
    from app.tasks import container_proposer as cp_task
    from app.utils.kit_container_page_builder import (
        _build_casting_sheet_section,
        _build_plain_bar_stack_section,
        _derive_single_market_field_headline,
        _format_single_market_field_caption,
    )

    # 1. Must-not "Spy Be Accused Of": full title used instead of mid-sentence chop; audit rejects clipped fragment.
    spy_title = "Who will the OpenAI spy be accused of working for in 2026?"
    derived_hl = _derive_single_market_field_headline(
        spy_title,
        subject_tokens={"openai"},
        seen_headlines={"openai outlook", "through jan 2029", "ai & safety", "long shots"},
    )
    assert derived_hl == spy_title, derived_hl
    assert derived_hl != "Spy Be Accused Of"

    spy_mkts = [
        {
            "id": 65740158,
            "source": "polymarket",
            "name": spy_title,
            "category": "tech",
            "mutually_exclusive": False,
            "status": "open",
            "resolution_date": REF_NOW + timedelta(days=34),
            "volume_24h": 45000,
            "outcomes": [
                {"id": 1, "name": "Saudi Arabia", "current_probability": 0.07},
                {"id": 2, "name": "Russia", "current_probability": 0.06},
                {"id": 3, "name": "Israel", "current_probability": 0.05},
            ],
        },
        _bin(65740201, "Will OpenAI or Anthropic announce recursive self-improvement before Jan 1, 2027?", 18, series="KXAI", res_days=34),
        _bin(65740202, "Will OpenAI or Anthropic announce recursive self-improvement before Jan 1, 2029?", 81, series="KXAI", res_days=730),
        _bin(65740203, "Will OpenAI IPO valuation hit $1T+ by Dec 31, 2026?", 97, series="KXAI", res_days=34),
        _bin(65740204, "Will OpenAI launch a new consumer hardware product by Dec 31, 2026?", 15, series="KXAI", res_days=34),
        _bin(65740205, "Will the highest score achieved by an OpenAI model on HLE in 2026 be 55% or higher?", 47, series="KXAI", res_days=34),
    ]
    openai_page = propose_container_page_for_family("OpenAI Outlook", spy_mkts, now=REF_NOW)
    assert openai_page["accepted"], openai_page
    dumped_openai = json.dumps(openai_page["page"])
    assert "Spy Be Accused Of" not in dumped_openai
    spy_secs = [
        s for s in openai_page["page"]["sections"]
        if any(
            (it.get("provenance") or {}).get("market_id") == 65740158
            for it in (s.get("body", {}).get("items") or [])
        )
    ]
    assert len(spy_secs) == 1, spy_secs
    assert spy_secs[0]["common_headline"] == spy_title, spy_secs[0]["common_headline"]
    assert audit_container_page_invariants(openai_page["page"], markets_by_id={m["id"]: m for m in spy_mkts}) == []

    # Craft a bad casting_sheet section with clipped headline "Spy Be Accused Of" -> audit MUST flag it
    bad_clipped_page = {
        "title": "OpenAI Outlook",
        "snapshot_captured_at": REF_NOW.isoformat(),
        "sections": [
            {
                **spy_secs[0],
                "common_headline": "Spy Be Accused Of",
                "stat_caption": "Saudi Arabia is most likely for Spy Be Accused Of at 7%",
            }
        ],
    }
    bad_clipped_errs = audit_container_page_invariants(bad_clipped_page, markets_by_id={m["id"]: m for m in spy_mkts})
    assert bad_clipped_errs, bad_clipped_errs
    bad_clipped_no_map = audit_container_page_invariants(bad_clipped_page)
    assert bad_clipped_no_map, bad_clipped_no_map

    # 2. Non-exclusive field caption omits "for <heading>": "X is the most likely at N%".
    assert spy_secs[0]["stat_caption"] == "Saudi Arabia is the most likely at 7%", spy_secs[0]["stat_caption"]
    dress_mkt = {
        "id": 77301,
        "name": "Taylor Swift: Wedding Dress",
        "mutually_exclusive": False,
        "status": "open",
        "volume_24h": 30000,
        "outcomes": [
            {"id": 1, "name": "Dior", "current_probability": 0.31},
            {"id": 2, "name": "Vera Wang", "current_probability": 0.21},
            {"id": 3, "name": "Oscar de la Renta", "current_probability": 0.19},
        ],
    }
    pb_dress = _build_plain_bar_stack_section("taylor-swift", "CULTURE", [dress_mkt], set(), now=REF_NOW, family_headline="Taylor Swift")
    assert pb_dress is not None
    assert pb_dress["common_headline"] == "Wedding Dress", pb_dress["common_headline"]
    assert pb_dress["stat_caption"] == "Dior is the most likely at 31%", pb_dress["stat_caption"]
    assert "is most likely for" not in pb_dress["stat_caption"].lower()
    assert _format_single_market_field_caption("Jane Doe", "44%", "Central Desk", mutually_exclusive=True) == "Jane Doe is the favorite for Central Desk at 44%"
    assert _format_single_market_field_caption("Jane Doe", "44%", spy_title, mutually_exclusive=True) == "Jane Doe is the favorite at 44%"

    # Keep unused casting helper imported for lint parity
    assert _build_casting_sheet_section is not None

    # 3. Tonight's deck contains ONLY tonight's pages (omitted run1 families never survive under run2's timestamp).
    class FakeRedis:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def set(self, key, val, ex=None):
            self.store[key] = val

    t1 = datetime(2026, 11, 26, 8, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 27, 8, 0, 0, tzinfo=timezone.utc)
    fam_a_page = {
        "slug": "alpha-family",
        "family_fingerprint": "fp-alpha",
        "page_fingerprint": "pfp-alpha",
        "title": "Alpha Family",
        "kicker": "TECH",
        "market_count": 5,
        "section_count": 3,
        "variants": ["dated_tiles", "shared_scale", "countdown"],
        "sections": [],
    }
    fam_b_page = {
        "slug": "beta-family",
        "family_fingerprint": "fp-beta",
        "page_fingerprint": "pfp-beta",
        "title": "Beta Family",
        "kicker": "TECH",
        "market_count": 5,
        "section_count": 3,
        "variants": ["dated_tiles", "shared_scale", "countdown"],
        "sections": [],
    }
    store1 = merge_preview_store(None, [fam_a_page, fam_b_page], now=t1)
    assert [p["slug"] for p in store1["pages"]] == ["alpha-family", "beta-family"]
    store2 = merge_preview_store(store1, [fam_b_page], now=t2)
    assert [p["slug"] for p in store2["pages"]] == ["beta-family"], store2["pages"]
    assert store2["updated_at"] == t2.isoformat()
    assert store2["updated_last_run"] == 1 and store2["added_last_run"] == 0

    rc = FakeRedis()
    fam_a_mkts = [
        {**_bin(95101, "Alpha Corp ship chip Before Nov 28 2026", 35, category="tech", series="KXALF", vol=80000, move=0.12, res_days=10, sources_count=2), "event_title": "Alpha Corp"},
        {**_bin(95102, "Alpha Corp ship chip Before Dec 15 2026", 68, category="tech", series="KXALF", vol=75000, move=0.10, res_days=21, sources_count=2), "event_title": "Alpha Corp"},
        {**_bin(95103, "Alpha Corp pass safety audit by Dec 31", 72, category="tech", series="KXALF", vol=65000, move=0.08, res_days=18, sources_count=2), "event_title": "Alpha Corp"},
        {**_bin(95104, "Alpha Corp launch consumer hub by Dec 31", 44, category="tech", series="KXALF", vol=60000, move=0.07, res_days=12, sources_count=2), "event_title": "Alpha Corp"},
        {**_bin(95105, "Alpha Corp acquire cloud lab in 2027", 14, category="tech", series="KXALF", vol=55000, move=0.05, res_days=80, sources_count=2), "event_title": "Alpha Corp"},
        {**_bin(95106, "Alpha Corp open Tokyo datacenter in 2027", 8, category="tech", series="KXALF", vol=50000, move=0.03, res_days=120, sources_count=2), "event_title": "Alpha Corp"},
        {**_bin(95107, "Alpha Corp list on Nasdaq in 2027", 6, category="tech", series="KXALF", vol=45000, move=0.02, res_days=130, sources_count=2), "event_title": "Alpha Corp"},
    ]
    fam_b_mkts = [
        {**_bin(95201, "Beta Systems pass audit Before Nov 28 2026", 41, category="tech", series="KXBET", vol=80000, move=0.12, res_days=10, sources_count=2), "event_title": "Beta Systems"},
        {**_bin(95202, "Beta Systems pass audit Before Dec 15 2026", 74, category="tech", series="KXBET", vol=75000, move=0.10, res_days=21, sources_count=2), "event_title": "Beta Systems"},
        {**_bin(95203, "Beta Systems publish benchmark by Dec 31", 69, category="tech", series="KXBET", vol=65000, move=0.08, res_days=18, sources_count=2), "event_title": "Beta Systems"},
        {**_bin(95204, "Beta Systems release SDK by Dec 31", 48, category="tech", series="KXBET", vol=60000, move=0.07, res_days=12, sources_count=2), "event_title": "Beta Systems"},
        {**_bin(95205, "Beta Systems split stock in 2027", 12, category="tech", series="KXBET", vol=55000, move=0.05, res_days=80, sources_count=2), "event_title": "Beta Systems"},
        {**_bin(95206, "Beta Systems file patent suit in 2027", 9, category="tech", series="KXBET", vol=50000, move=0.03, res_days=120, sources_count=2), "event_title": "Beta Systems"},
        {**_bin(95207, "Beta Systems reach 10M users in 2027", 5, category="tech", series="KXBET", vol=45000, move=0.02, res_days=130, sources_count=2), "event_title": "Beta Systems"},
    ]
    task_run1 = asyncio.run(
        run_nightly_container_proposer(
            markets=fam_a_mkts + fam_b_mkts,
            covered_ids=frozenset(),
            covered_public_set_names=(),
            now=t1,
            redis_client=rc,
        )
    )
    assert len(task_run1["store"]["pages"]) == 2
    deck1_id = task_run1["deck_id"]
    task_run2 = asyncio.run(
        run_nightly_container_proposer(
            markets=fam_b_mkts,
            covered_ids=frozenset(),
            covered_public_set_names=(),
            now=t2,
            redis_client=rc,
        )
    )
    assert [p["title"] for p in task_run2["store"]["pages"]] == ["Beta Systems"], task_run2["store"]["pages"]
    assert task_run2["store"]["updated_at"] == t2.isoformat()
    # Earlier deck frozen under its own deck_id still keeps both pages intact for saved grades.
    assert len(json.loads(rc.get(f"{cp_task.CONTAINER_PREVIEWS_DECK_KEY_PREFIX}{deck1_id}"))["pages"]) == 2

    # 4. Failed coverage read is recorded on stored deck & API preview response, never silent complete.
    import importlib
    gs_mod = importlib.import_module("app.tasks.grouping_sentinel")

    class FailingSession:
        async def execute(self, stmt):
            sql_text = str(stmt)
            if "SELECT slug, title FROM containers" in sql_text:
                class _Res:
                    def all(self):
                        return []
                return _Res()
            raise RuntimeError("graph SQL timeout")

        async def rollback(self):
            return None

    async def _fail_def_cov(_sess):
        raise RuntimeError("definition_coverage timeout")

    monkeypatch.setattr(gs_mod, "definition_coverage", _fail_def_cov)
    partial_run = asyncio.run(
        run_nightly_container_proposer(
            session=FailingSession(),
            markets=fam_b_mkts,
            covered_ids=None,
            now=t2,
            redis_client=rc,
        )
    )
    assert partial_run["status"] == "partial_coverage", partial_run
    assert partial_run["coverage_partial"] is True
    assert set(partial_run["coverage_failed_reads"]) == {"graph_sql", "definition_coverage"}
    assert partial_run["store"]["coverage_partial"] is True
    assert set(partial_run["store"]["coverage_failed_reads"]) == {"graph_sql", "definition_coverage"}

    async def _admin_ok(*_a, **_kw):
        return True

    monkeypatch.setattr("app.routes.admin_utils._check_admin_auth", _admin_ok)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", lambda: rc)
    req = SimpleNamespace(headers={}, query_params={})
    preview_resp = asyncio.run(containers_route.get_kit_container_pages_preview(request=req, db=None))
    assert preview_resp["status"] == "ready"
    assert preview_resp["coverage_partial"] is True
    assert set(preview_resp["coverage_failed_reads"]) == {"graph_sql", "definition_coverage"}
