"""Contract, 7-rules, and Ruling 367: A tests for Kit v1 (`kit_version: 1`, #13551)."""

from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import admin_utils, containers
from app.utils.kit_v1_spec import (
    build_calendar_strip_367a,
    build_kit_v1_worked_examples,
    compute_one_in_n,
    validate_kit_v1_card,
)


def test_all_eight_worked_examples_validate_cleanly() -> None:
    payload = build_kit_v1_worked_examples()
    assert payload["kit_version"] == 1
    assert payload["count"] == 8
    looks = [c["look"] for c in payload["items"]]
    assert looks == [
        "scoreboard_grid",
        "dated_tiles",
        "countdown",
        "road_ahead",
        "bubble_line",
        "one_in_n",
        "single_sport_slate",
        "calendar_strip",
    ]
    for card in payload["items"]:
        ok, errs = validate_kit_v1_card(card)
        assert ok, f"{card['look']} validation failed: {errs}"


def test_rule1_no_text_only_or_unpictured_casting_fallback() -> None:
    bad_text_only = {
        "kit_version": 1,
        "look": "word_list",
        "common_headline": "AI",
        "stat_caption": "Gemini leads at 81%",
        "data": {"rows": []},
    }
    ok, errs = validate_kit_v1_card(bad_text_only)
    assert not ok
    assert any("Rule 1" in e for e in errs)

    bad_casting = {
        "kit_version": 1,
        "look": "casting_sheet",
        "common_headline": "How 2026 gets summed up",
        "stat_caption": "Bad Bunny leads at 97%",
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
        "look": "photo_wall",
        "common_headline": "Who gets engaged",
        "stat_caption": "Top leaders",
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
    assert slate["look"] == "single_sport_slate"
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
    assert cal["look"] == "calendar_strip"
    assert cal["data"]["show_percent"] is True
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
