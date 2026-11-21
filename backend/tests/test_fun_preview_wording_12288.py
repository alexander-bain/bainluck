"""Wording & stage guards across all 7 preview grouping sets (Batch 2 + Batch 4)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from app.utils.container_machinery import (
    discover_machinery_candidate_paths,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_fun_tags import (
    CURATED_GROUPING_SETS_PATHS,
    clear_fun_markets_cache,
    load_fun_markets_registry,
)

NOW = datetime(2026, 11, 21, 19, 0, tzinfo=timezone.utc)

SEVEN_PREVIEW_SLUGS = (
    "machinery-long-shots",
    "machinery-long-awaited",
    "machinery-space-race",
    "machinery-game-awards-2026",
    "machinery-big-championships-2027",
    "machinery-unsolved-big-problems",
    "machinery-ai-and-big-tech-race",
)

BAD_MID_SENTENCE_CAP_RE = re.compile(
    r", with (?:A|An|The|New|Next|Major|Magnitude|Humanoid|Before|By|After|Nuclear|In|Is|Will|When|Which)\b"
)


def _sample_outcomes(mid: int, title: str, slug: str) -> list[tuple[str, float]]:
    if mid == 108247:
        return [("United States", 0.57), ("China", 0.37)]
    if mid in (53049401, 112792):
        return [("Before 2035", 0.91), ("Before 2032", 0.80)]
    if mid in (108232, 112826):
        return [("Before 2040", 0.70), ("Before 2035", 0.60)]
    if mid == 112835:
        return [("Before 2030", 0.64), ("Before 2028", 0.46)]
    if mid == 60626095:
        return [("Riemann Hypothesis", 0.74), ("Ramsey Number R(5,5)", 0.32)]
    if mid in (109435,):
        return [("Before Jan 20, 2029", 0.14), ("Before Jan 1, 2028", 0.09)]
    if mid in (9997262,):
        return [("December 31", 0.014), ("April 30", 0.001)]
    if mid in (109398,):
        return [("Before 2027", 0.02), ("Before 2026", 0.001)]
    if mid in (112833,):
        return [("Before 2030", 0.18), ("Before 2028", 0.10)]
    if mid in (108494,):
        return [("Before 2028", 0.12), ("Before 2027", 0.025)]
    if mid in (112760,):
        return [("2027", 0.31), ("2026", 0.18)]
    if mid in (59693617,):
        return [("Before Dec 1, 2026", 0.095), ("Before Jan 1, 2027", 0.065)]
    if mid in (114237,):
        return [("March 31, 2027", 0.055), ("December 31, 2026", 0.017)]
    if mid in (67717832,):
        return [("March 2027", 0.136), ("January 2027", 0.088)]
    if mid == 113184:
        return [("June 30, 2027", 0.43), ("March 31, 2027", 0.19)]
    if slug == "machinery-game-awards-2026":
        return [(f"Studio Game {mid % 10}", 0.55), ("Other Game", 0.25)]
    if slug == "machinery-big-championships-2027":
        return [("Top Contender", 0.50), ("Runner Up", 0.25)]
    if slug == "machinery-ai-and-big-tech-race":
        return [("Company One", 0.55), ("Company Two", 0.30)]
    return [("Yes", 0.15 if slug == "machinery-long-shots" else 0.55), ("No", 0.85 if slug == "machinery-long-shots" else 0.45)]


def _mk_market(mid: int, name: str, outcomes: list[tuple[str, float]], *, category: str = "tech") -> dict:
    now_iso = datetime(2026, 11, 21, 18, 0, tzinfo=timezone.utc).isoformat()
    return {
        "id": mid,
        "name": name,
        "title": name,
        "status": "open",
        "source": "kalshi",
        "category": category,
        "llm_sport_category": category,
        "volume": 100_000.0,
        "resolution_date": "2028-06-01T00:00:00+00:00",
        "newest_outcome_updated_at": now_iso,
        "outcomes": [
            {"id": mid * 10 + i, "name": oname, "probability": prob, "last_updated": now_iso}
            for i, (oname, prob) in enumerate(outcomes)
        ],
    }


def _assert_clean_headline(headline: str, *, slug: str) -> None:
    assert headline, f"{slug}: empty headline"
    assert "? at " not in headline and not headline.endswith("?"), f"{slug}: question headline {headline!r}"
    assert ": " not in headline, f"{slug}: colon dump in headline {headline!r}"
    assert not BAD_MID_SENTENCE_CAP_RE.search(headline), f"{slug}: mid-sentence cap in {headline!r}"


@pytest.mark.asyncio
async def test_all_seven_preview_sets_remain_preview_and_every_row_reads_as_sentence() -> None:
    clear_fun_markets_cache()
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    reg = load_fun_markets_registry()

    curated_sets: dict[str, list[dict]] = {}
    for p in CURATED_GROUPING_SETS_PATHS:
        doc = json.loads(p.read_text(encoding="utf-8"))
        for k, spec in (doc.get("sets") or {}).items():
            curated_sets[k.lower()] = list((spec or {}).get("entries") or [])

    for slug in SEVEN_PREVIEW_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        assert defn["stage"] == "public", f"{slug} must be stage='public' under 324: A"
        sec = defn["rule"]["sections"][0]
        sub_tag = sec["atom_query"]["fun_sub_tag"]
        cat = str(defn.get("category") or "tech")

        if sub_tag.lower() in curated_sets:
            row_specs = [(int(e["id"]), str(e["short_label"])) for e in curated_sets[sub_tag.lower()]]
        else:
            row_specs = [
                (mid, reg.markets[mid].title)
                for mid in reg.ordered_market_ids
                if sub_tag in reg.markets[mid].sub_tags
            ]

        assert len(row_specs) >= 6
        filler_specs = row_specs[-3:]

        # Test every market in BOTH slot #1 and slot #2 by varying probabilities cleanly.
        for idx, (mid, title) in enumerate(row_specs):
            others = [s for s in row_specs if s[0] != mid]
            anchor_a, anchor_b = others[0], others[1]

            # Case 1: `mid` in slot #1 (highest probability), `anchor_a` in slot #2
            def_high = 0.19 if slug == "machinery-long-shots" else 0.92
            def_second = 0.17 if slug == "machinery-long-shots" else 0.78
            def_third = 0.12 if slug == "machinery-long-shots" else 0.45

            markets_case1 = [
                _mk_market(mid, title, [(o[0], def_high if oi == 0 else 0.05) for oi, o in enumerate(_sample_outcomes(mid, title, slug))], category=cat),
                _mk_market(anchor_a[0], anchor_a[1], [(o[0], def_second if oi == 0 else 0.05) for oi, o in enumerate(_sample_outcomes(anchor_a[0], anchor_a[1], slug))], category=cat),
                _mk_market(anchor_b[0], anchor_b[1], [(o[0], def_third if oi == 0 else 0.05) for oi, o in enumerate(_sample_outcomes(anchor_b[0], anchor_b[1], slug))], category=cat),
            ]
            # Add extra markets so min_items is always satisfied even if date exclusion applies
            for f_mid, f_t in filler_specs:
                if f_mid not in {mid, anchor_a[0], anchor_b[0]}:
                    markets_case1.append(
                        _mk_market(f_mid, f_t, [(o[0], 0.05) for o in _sample_outcomes(f_mid, f_t, slug)], category=cat)
                    )
            res1 = await produce_container_machinery(
                {"events": [], "markets": markets_case1, "paired_sets": {}, "market_histories": {}},
                defn,
                now=NOW,
            )
            _assert_clean_headline(res1.title, slug=f"{slug}[slot1:{mid}]")

            # Case 2: `anchor_a` in slot #1, `mid` in slot #2
            markets_case2 = [
                _mk_market(anchor_a[0], anchor_a[1], [(o[0], def_high if oi == 0 else 0.05) for oi, o in enumerate(_sample_outcomes(anchor_a[0], anchor_a[1], slug))], category=cat),
                _mk_market(mid, title, [(o[0], def_second if oi == 0 else 0.05) for oi, o in enumerate(_sample_outcomes(mid, title, slug))], category=cat),
                _mk_market(anchor_b[0], anchor_b[1], [(o[0], def_third if oi == 0 else 0.05) for oi, o in enumerate(_sample_outcomes(anchor_b[0], anchor_b[1], slug))], category=cat),
            ]
            for f_mid, f_t in filler_specs:
                if f_mid not in {mid, anchor_a[0], anchor_b[0]}:
                    markets_case2.append(
                        _mk_market(f_mid, f_t, [(o[0], 0.05) for o in _sample_outcomes(f_mid, f_t, slug)], category=cat)
                    )
            res2 = await produce_container_machinery(
                {"events": [], "markets": markets_case2, "paired_sets": {}, "market_histories": {}},
                defn,
                now=NOW,
            )
            _assert_clean_headline(res2.title, slug=f"{slug}[slot2:{mid}]")


@pytest.mark.asyncio
async def test_game_awards_never_names_same_game_twice_even_when_all_rows_share_leader() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    defn = load_machinery_definition(paths_by_slug["machinery-game-awards-2026"])

    all_gta_markets = [
        _mk_market(mid, name, [("Grand Theft Auto VI", prob), ("Other", 0.05)], category="entertainment")
        for mid, name, prob in (
            (58399979, "Best Game Direction", 0.84),
            (58399941, "Best Narrative", 0.79),
            (58399980, "Best Audio Design", 0.72),
            (58399978, "Best Multiplayer", 0.68),
        )
    ]
    res_all = await produce_container_machinery(
        {"events": [], "markets": all_gta_markets, "paired_sets": {}, "market_histories": {}},
        defn,
        now=NOW,
    )
    assert res_all.title == "Grand Theft Auto VI for Best Game Direction is at 84%, leading 4 of 4 awards"
    assert res_all.title.count("Grand Theft Auto VI") == 1


@pytest.mark.asyncio
async def test_space_race_china_omits_the_article() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    defn = load_machinery_definition(paths_by_slug["machinery-space-race"])
    markets = [
        _mk_market(108300, "Will Blue Origin land on the moon before SpaceX?", [("Yes", 0.63), ("No", 0.37)]),
        _mk_market(108247, "Which country will be the next to send humans to the Moon?", [("China", 0.58), ("United States", 0.38)]),
        _mk_market(108236, "A humanoid robot walks on Mars before a human does?", [("Yes", 0.49), ("No", 0.51)]),
    ]
    res = await produce_container_machinery(
        {"events": [], "markets": markets, "paired_sets": {}, "market_histories": {}},
        defn,
        now=NOW,
    )
    assert res.title == (
        "Blue Origin beating SpaceX to the Moon leads the race to the Moon and Mars at 63%, "
        "with China as the next country on the Moon at 58%"
    )
