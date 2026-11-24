"""Contract, layout-generic kit, 7-rules, and Ruling 367: A tests for Kit v1 (#13551)."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import admin_utils, containers
from app.utils.kit_v1_spec import (
    ALLOWED_LAYOUTS,
    COSMETIC_KIT_FIELDS,
    GOLDEN_EXAMPLES_PATH,
    KIT_V1_FIELD_BEHAVIOR_TABLE,
    MEANING_CARRYING_KIT_FIELDS,
    build_calendar_strip_367a,
    build_fallback_today,
    build_kit_v1_worked_examples,
    compute_one_in_n,
    validate_kit_v1_card,
)


def _walk_marks_dicts(node: Any, *, inside_marks: bool = False):
    if isinstance(node, list):
        for el in node:
            yield from _walk_marks_dicts(el, inside_marks=inside_marks)
    elif isinstance(node, dict):
        if inside_marks:
            yield node
        for k, child in node.items():
            if k == "route":
                continue
            yield from _walk_marks_dicts(
                child,
                inside_marks=(
                    k in {"marks", "header_marks", "footer_marks", "leading", "summary_marks", "sub_marks"}
                ),
            )


def test_all_eight_worked_examples_validate_and_match_golden_json() -> None:
    payload = build_kit_v1_worked_examples()
    assert payload["kit_version"] == 1
    assert payload["count"] == 17
    pairs = [(c["layout"], c["variant"]) for c in payload["items"]]
    assert pairs[:8] == [
        ("grid", "scoreboard_grid"),
        ("grid", "dated_tiles"),
        ("stack", "countdown"),
        ("stack", "road_ahead"),
        ("axis", "bubble_line"),
        ("stack", "one_in_n"),
        ("stack", "single_sport_slate"),
        ("calendar", "calendar_strip"),
    ]
    assert pairs[8:] == [
        ("grid", "scoreboard_grid"),
        ("grid", "scoreboard_grid"),
        ("grid", "scoreboard_grid"),
        ("axis", "shared_scale"),
        ("grid", "dated_tiles"),
        ("axis", "deadline_race"),
        ("stack", "casting_sheet"),
        ("stack", "casting_sheet"),
        ("stack", "the_cut"),
    ]
    for card in payload["items"]:
        assert "data" not in card
        assert isinstance(card["body"], dict) and card["body"]
        assert card["layout"] in ALLOWED_LAYOUTS
        ok, errs = validate_kit_v1_card(card)
        assert ok, f"{card['id']} validation failed: {errs}"
        assert card["source_mark"]["label"]
        assert card["route"]["kind"] in {"collection", "event", "market", "team"}
        blob = json.dumps(card)
        assert not card["common_headline"].endswith("?"), card["id"]
        assert "PTB" not in blob, card["id"]
        assert "US x Iran" not in blob, card["id"]
        assert "Served ladder" not in blob, card["id"]
        assert "rung" not in blob.lower(), card["id"]
        assert "other markets in this set are not drawn here" not in blob, card["id"]
        assert "Toss-up" not in blob, card["id"]
        assert "11%–11%" not in blob, card["id"]
        assert "->" not in blob, card["id"]

    assert "11% each" in json.dumps(payload["items"][14])
    assert "38% each" in json.dumps(payload["items"][16])
    assert "Shai Gilgeous-Alexander" in json.dumps(payload["items"][10])
    assert "Giannis Antetokounmpo" in json.dumps(payload["items"][10])

    assert GOLDEN_EXAMPLES_PATH.exists(), "Golden JSON must be committed for Swift Codable parity"
    golden = json.loads(GOLDEN_EXAMPLES_PATH.read_text(encoding="utf-8"))
    assert golden == payload


def test_defining_kit_rule_unknown_variant_or_none_still_validates() -> None:
    """Ruling 366: B — renaming `variant` to an unknown string (or None) MUST still draw/validate."""
    payload = build_kit_v1_worked_examples()
    for card in payload["items"]:
        mutated_unknown = copy.deepcopy(card)
        mutated_unknown["variant"] = "unheard_of_future_bracket_2027"
        ok, errs = validate_kit_v1_card(mutated_unknown)
        assert ok, f"Unknown variant must not fail closed for {card['id']}: {errs}"

        mutated_none = copy.deepcopy(card)
        mutated_none["variant"] = None
        ok_none, errs_none = validate_kit_v1_card(mutated_none)
        assert ok_none, f"None variant must not fail closed for {card['id']}: {errs_none}"


def test_builder_c_swift_compatibility_no_kind_or_type_inside_marks() -> None:
    """KitCardEnvelope366B treats 'kind'/'type' inside marks arrays as a mark discriminator."""
    payload = build_kit_v1_worked_examples()
    for card in payload["items"]:
        for mark_dict in _walk_marks_dicts(card["body"]):
            assert "kind" not in mark_dict, f"Unexpected 'kind' key in {card['id']}: {mark_dict}"
            assert "type" not in mark_dict, f"Unexpected 'type' key in {card['id']}: {mark_dict}"


def test_unknown_version_layout_mark_and_empty_body_fail_closed() -> None:
    payload = build_kit_v1_worked_examples()
    sample = payload["items"][2]  # stack

    bad_ver = copy.deepcopy(sample)
    bad_ver["kit_version"] = 2
    assert not validate_kit_v1_card(bad_ver)[0]

    bad_layout = copy.deepcopy(sample)
    bad_layout["layout"] = "carousel"
    assert not validate_kit_v1_card(bad_layout)[0]

    bad_mark = copy.deepcopy(sample)
    bad_mark["body"]["items"][0]["marks"].append({"mark": "sparkle", "text": "x"})
    ok_mark, errs_mark = validate_kit_v1_card(bad_mark)
    assert not ok_mark
    assert any("Unsupported mark" in e for e in errs_mark)

    empty_body = copy.deepcopy(sample)
    empty_body["body"] = {}
    assert not validate_kit_v1_card(empty_body)[0]

    fb = build_fallback_today("No fit")
    assert fb["layout"] is None
    assert fb["variant"] is None
    assert fb["fallback_today"] is True
    assert not validate_kit_v1_card(fb)[0]


def test_scoreboard_grid_strips_refused_and_requires_two_columns() -> None:
    payload = build_kit_v1_worked_examples()
    grid_with_refused = copy.deepcopy(payload["items"][0])
    grid_with_refused["body"]["columns"].append(
        {"key": "bad", "label": "Broken", "refused_sum": 183}
    )
    ok_ref, errs_ref = validate_kit_v1_card(grid_with_refused)
    assert not ok_ref
    assert any("strip refused" in e for e in errs_ref)

    grid_one_col = copy.deepcopy(payload["items"][0])
    grid_one_col["body"]["columns"] = grid_one_col["body"]["columns"][:1]
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
        "body": {"items": [{"id": "r1", "marks": [{"mark": "word", "text": "Gemini"}]}]},
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
        "body": {
            "items": [
                {
                    "id": "r1",
                    "marks": [
                        {"mark": "picture", "url": "", "alt": "Bad Bunny", "subject_kind": "person"},
                        {"mark": "word", "text": "Bad Bunny", "style": "row"},
                        {"mark": "number", "value": 97, "display": "97%", "unit": "%"},
                    ],
                }
            ]
        },
    }
    ok_cast, errs_cast = validate_kit_v1_card(bad_casting)
    assert not ok_cast
    assert any("image_url" in e for e in errs_cast)


def test_rule3_shared_scale_rejects_mixed_units_or_missing_scale() -> None:
    payload = build_kit_v1_worked_examples()
    card = copy.deepcopy(payload["items"][4])  # axis / bubble_line
    card["body"]["scale_units"] = ["$M", "%"]
    ok, errs = validate_kit_v1_card(card)
    assert not ok
    assert any("Rule 3" in e for e in errs)

    no_scale = copy.deepcopy(payload["items"][4])
    del no_scale["body"]["scale"]
    ok_ns, errs_ns = validate_kit_v1_card(no_scale)
    assert not ok_ns
    assert any("Rule 3" in e for e in errs_ns)


def test_rule4_and_rule5_enforce_ranks_images_and_full_names() -> None:
    payload = build_kit_v1_worked_examples()
    grid = copy.deepcopy(payload["items"][0])
    grid["body"]["rows"][0]["leading"][0]["text"] = "9"
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
        "body": {
            "row_layout": "stacked_cells",
            "columns": [{"key": "a", "label": "A"}, {"key": "b", "label": "B"}],
            "rows": [
                {
                    "id": "cher",
                    "leading": [
                        {
                            "mark": "picture",
                            "url": "https://thumb.wikimedia.org/wikipedia/commons/a.jpg",
                            "alt": "Cher",
                            "subject_kind": "person",
                        },
                        {"mark": "word", "text": "Cher", "style": "row"},
                    ],
                    "cells": [
                        {"column_key": "a", "marks": [{"mark": "tile", "shade": 0.3, "center_label": "30%"}]},
                        {"column_key": "b", "marks": [{"mark": "tile", "shade": 0.1, "center_label": "10%"}]},
                    ],
                }
            ],
        },
    }
    ok_wall, errs_wall = validate_kit_v1_card(first_name_only_wall)
    assert not ok_wall
    assert any("first & last name" in e for e in errs_wall)


def test_rule6_single_sport_slate_rejects_mixed_sports() -> None:
    payload = build_kit_v1_worked_examples()
    slate = copy.deepcopy(payload["items"][6])
    assert slate["variant"] == "single_sport_slate"
    slate["body"]["items"][1]["sport_key"] = "icehockey_nhl"
    ok, errs = validate_kit_v1_card(slate)
    assert not ok
    assert any("Rule 6" in e for e in errs)


def test_rule7_one_in_n_matches_percent() -> None:
    assert compute_one_in_n(12) == 8
    assert compute_one_in_n(5) == 20
    payload = build_kit_v1_worked_examples()
    one_in_n_card = copy.deepcopy(payload["items"][5])
    # Mutate the one_in_n number mark to mismatch 12%
    one_in_n_card["body"]["items"][0]["marks"][2]["value"] = 99
    one_in_n_card["body"]["items"][0]["marks"][2]["display"] = "1 in 99"
    ok, errs = validate_kit_v1_card(one_in_n_card)
    assert not ok
    assert any("Rule 7" in e for e in errs)


def test_ruling_367a_calendar_strip_math_and_dip_refusal() -> None:
    payload = build_kit_v1_worked_examples()
    cal = payload["items"][7]
    assert cal["layout"] == "calendar"
    assert cal["variant"] == "calendar_strip"
    assert cal["footnote"].startswith("Chance it is out before each day:")
    assert "3% before Nov 27" in cal["footnote"]
    assert "Dec 4 or later, 10%" in cal["footnote"]
    assert "Served ladder" not in cal["footnote"]

    nov30 = next(d for d in cal["body"]["days"] if d["date_key"] == "Nov-30")
    assert nov30["daily_pct"] == 0
    nov30_tile = next(m for m in nov30["marks"] if m["mark"] == "tile")
    assert nov30_tile["bottom_label"] == "<1%"

    wed = next(d for d in cal["body"]["days"] if d["date_key"] == "Dec-2")
    assert wed["daily_pct"] == 67
    tile = next(m for m in wed["marks"] if m["mark"] == "tile")
    assert tile["bottom_label"] == "67%"
    assert tile["highlight_role"] == "day_peak"

    tail = cal["body"]["days"][-1]
    assert tail["daily_pct"] == 10
    tail_tile = next(m for m in tail["marks"] if m["mark"] == "tile")
    assert tail_tile["bottom_label"] == "10%"

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


def test_fable_nov23_overnight_wording_and_adaptive_team_colors() -> None:
    """PR #13577 review asks 2(a) & 2(b): no 'opens at' wording and adaptive light/dark colors."""
    payload = build_kit_v1_worked_examples()
    celtics = payload["items"][3]
    assert celtics["id"] == "kit-boston-celtics-road"
    assert "opens" not in celtics["stat_caption"].lower()
    assert celtics["stat_caption"].startswith("Boston is 79% at Washington on Tuesday")

    fill_col = celtics["body"]["items"][0]["marks"][3]["fill_color"]
    assert isinstance(fill_col, dict) and set(fill_col.keys()) == {"light", "dark"}
    assert fill_col["light"] == "#008348"
    assert fill_col["dark"] != fill_col["light"]

    bad_raw_hex = copy.deepcopy(celtics)
    bad_raw_hex["body"]["items"][0]["marks"][3]["fill_color"] = "#008348"
    ok_raw, errs_raw = validate_kit_v1_card(bad_raw_hex)
    assert not ok_raw
    assert any("adaptive" in e for e in errs_raw)


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
    assert body["count"] == 17
    assert len(body["refusals"]) == 3
    for item in body["items"]:
        assert "data" not in item
        assert isinstance(item["body"], dict)


def test_cosmetic_vs_meaning_carrying_field_table() -> None:
    """Agreed #13551 table: unknown cosmetic values pass; unknown meaning-carrying fail closed."""
    assert set(KIT_V1_FIELD_BEHAVIOR_TABLE.keys()) == {"cosmetic", "meaning_carrying"}
    assert "picture.subject_kind" in COSMETIC_KIT_FIELDS
    assert "bar.bar_style" in MEANING_CARRYING_KIT_FIELDS
    assert "number.unit" in MEANING_CARRYING_KIT_FIELDS

    payload = build_kit_v1_worked_examples()
    stack_card = copy.deepcopy(payload["items"][2])
    stack_card["variant"] = "unknown_cosmetic_variant"
    stack_card["body"]["header_layout"] = "ticker"
    stack_card["body"]["items"][0]["marks"][0]["size"] = "xxl"
    stack_card["body"]["items"][0]["marks"][0]["contain"] = "auto"
    stack_card["body"]["items"][0]["marks"][0]["subject_kind"] = "future_entity_kind"
    stack_card["body"]["items"][0]["marks"][1]["style"] = "future_word_style"
    stack_card["body"]["items"][0]["marks"][1]["tone"] = "neon"
    stack_card["body"]["items"][0]["marks"][1]["align"] = "justify"
    stack_card["body"]["items"][0]["marks"][1]["width"] = "giant"
    stack_card["body"]["items"][0]["marks"][2]["width"] = "ultra_wide"
    stack_card["body"]["items"][0]["marks"][3]["tone"] = "neon"
    stack_card["body"]["items"][0]["marks"][3]["prominence"] = "giant"
    stack_card["body"]["items"][0]["marks"][3]["align"] = "justify"
    stack_card["body"]["items"][0]["marks"][3]["width"] = "giant"
    ok_cosmetic, errs_cosmetic = validate_kit_v1_card(stack_card)
    assert ok_cosmetic, f"Unknown cosmetic fields should validate: {errs_cosmetic}"

    cal_card = copy.deepcopy(payload["items"][7])
    cal_card["body"]["days"][0]["marks"][1]["highlight_role"] = "future_tile_highlight"
    assert validate_kit_v1_card(cal_card)[0]

    # Meaning-carrying fields fail closed on unknown values
    bad_bar_style = copy.deepcopy(payload["items"][2])
    bad_bar_style["body"]["items"][0]["marks"][2]["bar_style"] = "stacked3"
    ok_bs, errs_bs = validate_kit_v1_card(bad_bar_style)
    assert not ok_bs and any("bar_style" in e for e in errs_bs)

    bad_unit = copy.deepcopy(payload["items"][2])
    bad_unit["body"]["items"][0]["marks"][3]["unit"] = "points"
    ok_un, errs_un = validate_kit_v1_card(bad_unit)
    assert not ok_un and any("number.unit" in e for e in errs_un)

    bad_row_layout = copy.deepcopy(payload["items"][0])
    bad_row_layout["body"]["row_layout"] = "carousel_grid"
    ok_rl, errs_rl = validate_kit_v1_card(bad_row_layout)
    assert not ok_rl and any("row_layout" in e for e in errs_rl)

    bad_scale_kind = copy.deepcopy(payload["items"][4])
    bad_scale_kind["body"]["scale"]["scale_kind"] = "logarithmic"
    ok_sk, errs_sk = validate_kit_v1_card(bad_scale_kind)
    assert not ok_sk and any("scale_kind" in e for e in errs_sk)


def _async_return(value: bool):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
