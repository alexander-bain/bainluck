"""Tests for Forms Lab Batch 1 (#13551): member art, 7 pre-draw truth checks, and admin preview."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.utils.forms_lab_preview import (
    BATCH1_LOOK_ORDER,
    build_forms_lab_batch1_preview,
    build_places_grid_card,
    build_scoreboard_ai_card,
)
from app.utils.forms_lab_truth import (
    check_ladder_monotonic,
    check_no_computed_number,
    check_no_price_floor,
    check_one_date_per_family,
    check_one_unit_per_axis,
    check_one_winner_adds_to_100,
    check_ties_handled,
)
from app.utils.container_machinery import _default_art_resolver
from app.utils.member_art_13551 import (
    NBA_CONFERENCES,
    NFL_CONFERENCES,
    NHL_CONFERENCES,
    canonical_contender_name,
    compose_short_member_label,
    resolve_member_art,
    team_conference,
)


def test_canonical_aliases_unicode_and_conference_tables() -> None:
    assert canonical_contender_name("Gemini") == "Google"
    assert canonical_contender_name("Claude") == "Anthropic"
    assert canonical_contender_name("ChatGPT") == "OpenAI"
    assert canonical_contender_name("Grok") == "xAI"

    assert len(NHL_CONFERENCES["Eastern"]) == 16
    assert len(NHL_CONFERENCES["Western"]) == 16
    assert len(NBA_CONFERENCES["Eastern"]) == 15
    assert len(NBA_CONFERENCES["Western"]) == 15
    assert len(NFL_CONFERENCES["AFC"]) == 16
    assert len(NFL_CONFERENCES["NFC"]) == 16
    assert team_conference("Anaheim Ducks", "nhl") == "Western"
    assert team_conference("Boston Bruins", "nhl") == "Eastern"

    for name in ("Apple", "NVIDIA", "Microsoft", "Gemini", "Claude", "ChatGPT", "Victor Wembanyama", "Luka Dončić", "Penélope Cruz", "Alabama Crimson Tide", "Utah Mammoth"):
        art = resolve_member_art(name)
        assert art["url"], f"Expected verified url for {name}: {art}"

    assert compose_short_member_label("Actor cast as Felix Leiter") == "Felix Leiter"


def test_seven_pre_draw_truth_checks_pass_and_refuse() -> None:
    assert check_one_winner_adds_to_100([51, 29, 5, 4, 3, 10.5], field_label="MVP").passed
    bad_sum = check_one_winner_adds_to_100([68, 61, 55], field_label="NBA Scoring")
    assert not bad_sum.passed
    assert "184" in bad_sum.reason

    assert check_ladder_monotonic([("Nov 30", 14), ("Dec 15", 65), ("Dec 31", 85)]).passed
    bad_climb = check_ladder_monotonic([("Apr 28", 62), ("Jul 28", 52)], ladder_label="AGI")
    assert not bad_climb.passed

    assert check_one_date_per_family(["2026-12-31", "Dec 31, 2026"]).passed
    bad_date = check_one_date_per_family(["2026-12-31", "2027-03-31"])
    assert not bad_date.passed

    assert check_one_unit_per_axis(["$M", "$m"]).passed
    bad_unit = check_one_unit_per_axis(["$M", "% RT Score"])
    assert not bad_unit.passed

    assert check_ties_handled([("Holbrook", 11.0), ("Mackie", 11.0)], tie_rule="Tie badge").passed
    bad_tie = check_ties_handled([("Holbrook", 11.0), ("Mackie", 11.0)], tie_rule=None)
    assert not bad_tie.passed
    bad_cut_tie = check_ties_handled(
        [("T1", 90), ("T2", 80), ("T3", 70), ("T4", 60), ("T5", 55), ("T6", 50), ("T7", 45), ("Ducks", 38), ("Blues", 38)],
        cut_index=8,
        cut_tie_rule=None,
    )
    assert not bad_cut_tie.passed

    assert check_no_price_floor([45, 22, 11]).passed
    assert not check_no_price_floor([3, 2, 1, 1]).passed

    assert check_no_computed_number(has_computed_numbers=False, allowed=False).passed
    bad_d367 = check_no_computed_number(has_computed_numbers=True, allowed=False)
    assert not bad_d367.passed
    assert "decision 367" in bad_d367.reason


def test_forms_lab_batch1_all_five_looks_complete_art_percent_and_real_sets() -> None:
    payload = build_forms_lab_batch1_preview(include_refusal_demos=True)
    assert payload["preview_only"] is True
    assert payload["public_release"] is False
    assert payload["decision_367_daily_numbers_enabled"] is False
    assert tuple(payload["look_order"]) == BATCH1_LOOK_ORDER
    assert len(payload["looks"]) == 5

    for group in payload["looks"]:
        real_sets = group["real_sets"]
        assert len(real_sets) >= 5, group["look_id"]
        distinct_topics = {s["topic"].split("·")[0].strip() for s in real_sets}
        assert len(distinct_topics) >= 2, (group["look_id"], distinct_topics)

        draws = [c for c in group["cards"] if c["status"] == "draw"]
        refusals = [c for c in group["cards"] if c["status"] == "refused_fallback_rows"]
        assert len(draws) >= 1, group["look_id"]
        assert len(refusals) >= 1, group["look_id"]
        for ref_card in refusals:
            assert ref_card["refusal_reasons"]
            assert ref_card["fallback_rows"]

        for card in draws:
            body = card["body"]
            if group["look_id"] == "calendar_strip":
                assert body["decision_367_daily_numbers_enabled"] is False
                assert all(tile["daily_number_label"] is None for tile in body["tiles"])
                assert body["art"]["url"]
            if card["card_id"] == "casting-sheet-next-james-bond":
                felix = next(r for r in body["rows"] if r["role"] == "Felix Leiter")
                assert felix["is_tie"] is True
                assert felix["certainty"] == "Tie"
                assert felix["co_leader"] is not None
                assert felix["co_leader"]["art"]["url"]
            if card["card_id"] == "the-cut-nhl-conferences":
                confs = {c["conference"]: c for c in body["conferences"]}
                assert len(confs["Eastern"]["teams"]) == 16
                assert len(confs["Western"]["teams"]) == 16
                assert confs["Western"]["has_cut_tie"] is True


def test_specific_refusal_scenarios_also_cover_unclosed_ai_arena() -> None:
    res = _default_art_resolver()
    ai_bad = build_scoreboard_ai_card(res, include_unclosed_arena=True)
    assert ai_bad["status"] == "refused_fallback_rows"
    assert any("41%" in r for r in ai_bad["refusal_reasons"])

    places_ok = build_places_grid_card(res, include_mismatched_nov30_date=False)
    assert places_ok["status"] == "draw"


def test_admin_preview_endpoint_requires_auth_and_serves_when_authorized() -> None:
    client = TestClient(app)
    with patch("app.routes.admin_utils._check_admin_auth", new=AsyncMock(return_value=False)):
        denied = client.get("/api/containers/preview/forms-lab")
        assert denied.status_code == 403

    with patch("app.routes.admin_utils._check_admin_auth", new=AsyncMock(return_value=True)):
        bad_look = client.get("/api/containers/preview/forms-lab?look=nonexistent")
        assert bad_look.status_code == 400

        ok = client.get("/api/containers/preview/forms-lab?look=grid_of_cells")
        assert ok.status_code == 200
        data = ok.json()
        assert data["preview_only"] is True
        assert data["public_release"] is False
        assert len(data["looks"]) == 1
        assert data["looks"][0]["look_id"] == "grid_of_cells"
