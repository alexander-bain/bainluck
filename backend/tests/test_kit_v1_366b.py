"""Contract, 7-rules, and Ruling 367: A tests for Kit v1 (`kit_version: 1`, #13551)."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import admin_utils, containers
from app.utils.kit_v1_spec import (
    GOLDEN_EXAMPLES_PATH,
    build_calendar_strip_367a,
    build_fallback_today,
    build_kit_v1_worked_examples,
    compute_one_in_n,
    validate_kit_v1_card,
)


def test_all_eight_worked_examples_validate_and_match_golden_json() -> None:
    payload = build_kit_v1_worked_examples()
    assert payload["kit_version"] == 1
    assert payload["count"] == 8
    pairs = [(c["layout"], c["variant"]) for c in payload["items"]]
    assert pairs == [
        ("grid", "scoreboard_grid"),
        ("grid", "dated_tiles"),
        ("stack", "countdown"),
        ("stack", "road_ahead"),
        ("axis", "bubble_line"),
        ("stack", "one_in_n"),
        ("stack", "single_sport_slate"),
        ("calendar", "calendar_strip"),
    ]
    for card in payload["items"]:
        ok, errs = validate_kit_v1_card(card)
        assert ok, f"{card['variant']} validation failed: {errs}"
        assert card["source_mark"]["label"]
        assert card["route"]["kind"] in {"collection", "event", "market", "team"}

    assert GOLDEN_EXAMPLES_PATH.exists(), "Golden JSON must be committed for Swift Codable parity"
    golden = json.loads(GOLDEN_EXAMPLES_PATH.read_text(encoding="utf-8"))
    assert golden == payload


def test_mismatched_layout_and_variant_and_fallback_envelope_fail_closed() -> None:
    payload = build_kit_v1_worked_examples()
    bad = copy.deepcopy(payload["items"][2])  # stack / countdown
    bad["layout"] = "grid"
    ok, errs = validate_kit_v1_card(bad)
    assert not ok
    assert any("mismatch" in e for e in errs)

    fb = build_fallback_today("No fit")
    assert fb["layout"] is None
    assert fb["variant"] is None
    assert fb["fallback_today"] is True


def test_scoreboard_grid_strips_refused_and_requires_two_columns() -> None:
    payload = build_kit_v1_worked_examples()
    grid_with_refused = copy.deepcopy(payload["items"][0])
    grid_with_refused["data"]["columns"].append(
        {"key": "bad", "label": "Broken", "refused_sum": 183}
    )
    ok_ref, errs_ref = validate_kit_v1_card(grid_with_refused)
    assert not ok_ref
    assert any("strip refused" in e for e in errs_ref)

    grid_one_col = copy.deepcopy(payload["items"][0])
    grid_one_col["data"]["columns"] = grid_one_col["data"]["columns"][:1]
    ok_one, errs_one = validate_kit_v1_card(grid_one_col)
    assert not ok_one
    assert any("at least 2 valid columns" in e for e in errs_one)


def test_rule1_no_text_only_or_unpictured_casting_fallback() -> None:
    bad_text_only = {
        "kit_version": 1,
        "id": "bad-text",
        "layout": "stack",
        "variant": "word_list",
        "common_headline": "AI",
        "stat_caption": "Gemini leads at 81%",
        "source_mark": {"label": "1 source", "count": 1},
        "route": {"kind": "collection", "id": None, "slug": "ai"},
        "data": {"rows": []},
    }
    ok, errs = validate_kit_v1_card(bad_text_only)
    assert not ok
    assert any("Rule 1" in e for e in errs)

    bad_casting = {
        "kit_version": 1,
        "id": "bad-casting",
        "layout": "stack",
        "variant": "casting_sheet",
        "common_headline": "How 2026 gets summed up",
        "stat_caption": "Bad Bunny leads at 97%",
        "source_mark": {"label": "2 sources", "count": 2},
        "route": {"kind": "collection", "id": None, "slug": "2026"},
        "data": {"rows": [{"name": "Bad Bunny", "p": 97, "image_url": "", "image_kind": "person"}]},
    }
    ok_cast, errs_cast = validate_kit_v1_card(bad_casting)
    assert not ok_cast
    assert any("image_url" in e for e in errs_cast)


def test_rule3_shared_scale_rejects_mixed_units_or_missing_scale() -> None:
    payload = build_kit_v1_worked_examples()
    card = copy.deepcopy(payload["items"][1])
    card["data"]["shared_scale"] = True
    card["data"]["scale_units"] = ["$M", "%"]
    ok, errs = validate_kit_v1_card(card)
    assert not ok
    assert any("Rule 3" in e for e in errs)


def test_rule4_and_rule5_enforce_ranks_images_and_full_names() -> None:
    payload = build_kit_v1_worked_examples()
    grid = copy.deepcopy(payload["items"][0])
    grid["data"]["rows"][0]["rank"] = 9
    ok, errs = validate_kit_v1_card(grid)
    assert not ok
    assert any("rank=1" in e for e in errs)

    first_name_only_wall = {
        "kit_version": 1,
        "id": "bad-wall",
        "layout": "grid",
        "variant": "photo_wall",
        "common_headline": "Who gets engaged",
        "stat_caption": "Top leaders",
        "source_mark": {"label": "1 source", "count": 1},
        "route": {"kind": "collection", "id": None, "slug": "engaged"},
        "data": {
            "rows": [
                {
                    "rank": 1,
                    "name": "Cher",
                    "p": 30,
                    "image_url": "https://thumb.wikimedia.org/wikipedia/commons/a.jpg",
                    "image_kind": "person",
                }
            ]
        },
    }
    ok_wall, errs_wall = validate_kit_v1_card(first_name_only_wall)
    assert not ok_wall
    assert any("first & last name" in e or "first and last" in e for e in errs_wall)


def test_rule6_single_sport_slate_rejects_mixed_sports() -> None:
    payload = build_kit_v1_worked_examples()
    slate = copy.deepcopy(payload["items"][6])
    assert slate["variant"] == "single_sport_slate"
    slate["data"]["rows"][1]["sport_key"] = "icehockey_nhl"
    ok, errs = validate_kit_v1_card(slate)
    assert not ok
    assert any("Rule 6" in e for e in errs)


def test_rule7_one_in_n_matches_percent() -> None:
    assert compute_one_in_n(12) == 8
    assert compute_one_in_n(5) == 20
    payload = build_kit_v1_worked_examples()
    one_in_n_card = copy.deepcopy(payload["items"][5])
    one_in_n_card["data"]["rows"][0]["one_in_n"] = 99
    ok, errs = validate_kit_v1_card(one_in_n_card)
    assert not ok
    assert any("Rule 7" in e for e in errs)


def test_ruling_367a_calendar_strip_math_and_dip_refusal() -> None:
    payload = build_kit_v1_worked_examples()
    cal = payload["items"][7]
    assert cal["layout"] == "calendar"
    assert cal["variant"] == "calendar_strip"
    assert cal["data"]["show_percent"] is True
    assert "Served ladder:" in cal["footnote"]
    wed = next(d for d in cal["data"]["days"] if d["dow"] == "Wed")
    assert wed["daily_pct"] == 67
    assert wed["is_peak"] is True

    with pytest.raises(ValueError, match="dipped"):
        build_calendar_strip_367a(
            kicker="CULTURE",
            common_headline="Bad ladder",
            stat_caption="Should refuse",
            rungs=[
                {"dow": "Mon", "day_num": "1", "month_abbr": "Dec", "cum_pct": 50},
                {"dow": "Tue", "day_num": "2", "month_abbr": "Dec", "cum_pct": 42},
            ],
            ladder_footer="Invalid",
        )


def test_kit_v1_preview_endpoint_requires_admin_auth(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(containers.router, prefix="/api/containers")

    async def _fake_db():
        return SimpleNamespace()

    app.dependency_overrides[containers.get_db] = _fake_db
    client = TestClient(app)

    monkeypatch.setattr(admin_utils, "_check_admin_auth", _async_return(False))
    r_forbidden = client.get("/api/containers/preview/kit-v1")
    assert r_forbidden.status_code == 403

    monkeypatch.setattr(admin_utils, "_check_admin_auth", _async_return(True))
    r_ok = client.get("/api/containers/preview/kit-v1")
    assert r_ok.status_code == 200
    body = r_ok.json()
    assert body["kit_version"] == 1
    assert body["count"] == 8
    assert len(body["refusals"]) == 3


def _async_return(value: bool):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
