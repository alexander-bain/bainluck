"""#12288 Slice 6 tests:
2a. First section never repeats the page headline (Oscars embedded paired card & section 0 heading).
2b. Every number on a card or page equals that member's own page at the same moment; report fails on any mismatch.
2c. Failed reads surface an explicit error state, never an empty or shorter grouping.
"""

from __future__ import annotations

import copy
import pytest
from fastapi import HTTPException

from app.utils.container_machinery import (
    CANDIDATE_2028_PRESIDENTIAL_PATH,
    CANDIDATE_NFL_WEEK_PATH,
    CANDIDATE_OSCARS_BEST_PICTURE_PATH,
    compute_visual_diversity_report,
    evaluate_machinery_candidates_preview,
    load_machinery_definition,
    produce_container_machinery,
    serve_machinery_candidate_preview,
)
from tests.test_container_machinery_slice1_12288 import FIXED_NOW, _sample_snapshot


@pytest.mark.asyncio
async def test_slice6_2a_oscars_and_section0_never_repeat_page_headline() -> None:
    snap = _sample_snapshot()
    oscars = await serve_machinery_candidate_preview(
        "machinery-oscars-best-picture", snap, now=FIXED_NOW
    )
    assert oscars is not None and oscars["status"] == "ok"
    page_headline = oscars["container"]["container"]["name"]
    sec0 = oscars["container"]["sections"][0]
    assert sec0["title"].strip().casefold() != page_headline.strip().casefold()
    # Embedded paired card inside section 0 suppresses its duplicate internal header
    assert (
        sec0["visual_block"]["paired_metric_set"]["suppress_card_header_in_section"]
        is True
    )
    # Standalone Discover card keeps its own header
    card_pms = oscars["feed_item"]["data"]["roundup"]["paired_metric_set"]
    assert card_pms["suppress_card_header_in_section"] is False

    # Even if a definition's section 0 title matches the dynamic page headline verbatim,
    # produce_container_machinery replaces or suppresses it so it never repeats twice in a row.
    defn = load_machinery_definition(CANDIDATE_OSCARS_BEST_PICTURE_PATH)
    defn_dup = copy.deepcopy(defn)
    defn_dup["rule"]["sections"][0]["title"] = page_headline
    defn_dup["rule"]["sections"][0]["fallback_title"] = "Category Contenders"
    outcome = await produce_container_machinery(snap, defn_dup, now=FIXED_NOW)
    assert outcome.sections[0]["title"] == "Category Contenders"
    assert outcome.sections[0]["title"].casefold() != outcome.title.casefold()


@pytest.mark.asyncio
async def test_slice6_2b_member_page_number_parity_passes_all_four_and_fails_on_drift() -> None:
    snap = _sample_snapshot()
    # Inject aKalshi-style vig pair (0.675 + 0.335 = 1.01) on 2028 Party Control (#108327):
    # /futures/108327 normalizes 0.675/1.01 -> 67% and 0.335/1.01 -> 33% (NOT 68% / 32%).
    for m in snap["markets"]:
        if int(m["id"]) == 108327:
            m["top_outcomes"] = [
                {"id": 501, "name": "Democratic Party", "probability": 0.675},
                {"id": 502, "name": "Republican Party", "probability": 0.335},
            ]

    items = await evaluate_machinery_candidates_preview(snap, now=FIXED_NOW)
    assert len(items) == 4
    by_slug = {it["slug"]: it for it in items}

    # Verify 108327 normalized to 67% / 33% matching /futures/108327
    pol_sec0_outs = by_slug["machinery-2028-presidential"]["container"]["sections"][0][
        "visual_block"
    ]["items"][0]["outcomes"]
    assert [o["rendered_percent"] for o in pol_sec0_outs] == [67, 33]
    assert "67%" in by_slug["machinery-2028-presidential"]["container"]["container"]["name"]

    # Every grouping passes member_number_parity with 0 mismatches across card & page
    for it in items:
        rep = it["diversity_report"]
        assert rep is not None
        assert rep["overall_passes"] is True, f"{it['slug']} failed: {rep}"
        assert rep["member_number_parity"]["passes"] is True
        assert rep["member_number_parity"]["checked_numbers"] >= 8
        assert rep["member_number_parity"]["mismatch_count"] == 0
        assert rep["card"]["member_number_parity"]["passes"] is True
        assert rep["page"]["member_number_parity"]["passes"] is True

    # 1. Drift on a market outcome's own page fails the grouping
    pol_entry = copy.deepcopy(by_slug["machinery-2028-presidential"])
    pol_defn = load_machinery_definition(CANDIDATE_2028_PRESIDENTIAL_PATH)
    pol_entry["container"]["sections"][0]["visual_block"]["items"][0]["outcomes"][0][
        "rendered_percent"
    ] = 68
    bad_pol_report = compute_visual_diversity_report(
        pol_defn, pol_entry["feed_item"], pol_entry["container"]
    )
    assert bad_pol_report["overall_passes"] is False
    assert bad_pol_report["member_number_parity"]["passes"] is False
    assert bad_pol_report["member_number_parity"]["mismatch_count"] >= 1
    assert "member_number_parity" in bad_pol_report["page"]["failing_points"]

    # 2. Drift on a Discover card row fails card & overall report
    nfl_entry = copy.deepcopy(by_slug["machinery-nfl-week"])
    nfl_defn = load_machinery_definition(CANDIDATE_NFL_WEEK_PATH)
    nfl_entry["feed_item"]["data"]["roundup"]["machinery_card"]["rows"][0]["away_pct"] += 1
    bad_nfl_report = compute_visual_diversity_report(
        nfl_defn, nfl_entry["feed_item"], nfl_entry["container"]
    )
    assert bad_nfl_report["overall_passes"] is False
    assert bad_nfl_report["card"]["overall_passes"] is False
    assert "member_number_parity" in bad_nfl_report["card"]["failing_points"]

    # 3. Drift on Oscars paired_stage_bars Nominated % vs /futures/5165726 fails the grouping
    osc_entry = copy.deepcopy(by_slug["machinery-oscars-best-picture"])
    osc_defn = load_machinery_definition(CANDIDATE_OSCARS_BEST_PICTURE_PATH)
    osc_entry["container"]["sections"][0]["visual_block"]["paired_metric_set"]["entries"][0][
        "stage_1_rendered_percent"
    ] = 81
    bad_osc_report = compute_visual_diversity_report(
        osc_defn, osc_entry["feed_item"], osc_entry["container"]
    )
    assert bad_osc_report["overall_passes"] is False
    assert bad_osc_report["page"]["overall_passes"] is False
    assert "member_number_parity" in bad_osc_report["page"]["failing_points"]


@pytest.mark.asyncio
async def test_slice6_2c_failed_read_returns_error_state_never_empty_or_shorter_grouping() -> None:
    snap = _sample_snapshot()

    # Break ONLY Oscars' paired_sets read; the other 3 groupings remain healthy
    broken_oscars_snap = copy.deepcopy(snap)
    broken_oscars_snap["paired_sets"] = {}

    # 1. Direct container read raises HTTP 503 unavailable (never None -> empty unpublished hub)
    with pytest.raises(HTTPException) as exc_info:
        await serve_machinery_candidate_preview(
            "machinery-oscars-best-picture", broken_oscars_snap, now=FIXED_NOW
        )
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["state"] == "unavailable"
    assert exc_info.value.detail["slug"] == "machinery-oscars-best-picture"

    # 2. Preview list keeps all 4 groupings (never drops Oscars to return 3!), with status='error' on Oscars
    preview_items = await evaluate_machinery_candidates_preview(
        broken_oscars_snap, now=FIXED_NOW
    )
    assert len(preview_items) == 4
    by_slug = {it["slug"]: it for it in preview_items}
    assert by_slug["machinery-oscars-best-picture"]["status"] == "error"
    assert by_slug["machinery-oscars-best-picture"]["container"] is None
    assert "Couldn't load" in by_slug["machinery-oscars-best-picture"]["error"]
    for ok_slug in (
        "machinery-nfl-week",
        "machinery-2028-presidential",
        "machinery-fed-and-macro",
    ):
        assert by_slug[ok_slug]["status"] == "ok"
        assert by_slug[ok_slug]["container"]["state"] == "published"

    # 3. Missing one section inside NFL (e.g. zero division markets) refuses the whole NFL grouping
    #    rather than emitting a shorter 4-section NFL page.
    shorter_nfl_snap = copy.deepcopy(snap)
    shorter_nfl_snap["markets"] = [
        m
        for m in shorter_nfl_snap["markets"]
        if "division" not in m["name"].lower() and "north champion" not in m["name"].lower()
    ]
    with pytest.raises(HTTPException) as exc_nfl:
        await serve_machinery_candidate_preview(
            "machinery-nfl-week", shorter_nfl_snap, now=FIXED_NOW
        )
    assert exc_nfl.value.status_code == 503

    # 4. Full DB read exception surfaces status='error' on every grouping (never [] or 500 crash on preview)
    class _ExplodingSession:
        async def execute(self, *_args: object, **_kwargs: object) -> object:
            raise RuntimeError("simulated database connection failure")

    exploded = await evaluate_machinery_candidates_preview(
        _ExplodingSession(), now=FIXED_NOW
    )
    assert len(exploded) == 4
    assert all(it["status"] == "error" and it["container"] is None for it in exploded)
