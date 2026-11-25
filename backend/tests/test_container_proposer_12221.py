"""Condition 1-6 tests for generic Kit container builder and nightly proposer (#12221)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

from app.tasks.container_proposer import merge_preview_store, run_nightly_container_proposer
from app.utils.container_proposer import (
    discover_candidate_families,
    normalize_market_record,
    propose_top_containers,
)
from app.utils.kit_container_page_builder import (
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

    # 2. Countdown deduplicates truncated near-duplicate row labels cleanly
    dup_cands = [
        _bin(97101, "Will Apex Executive rank in SearchEngine Global Top 5 Most Searched People in US of 2027?", 66, category="tech", res_days=20),
        _bin(97102, "Will Apex Executive rank in SearchEngine Global Top 5 Most Searched People of 2027?", 66, category="tech", res_days=20),
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
