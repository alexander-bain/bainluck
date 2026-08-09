import json
from pathlib import Path

from backend.scripts.evals.collapsed_family_mount_contract import render_plan, validate_plan


FIXTURES = Path(__file__).parent / "fixtures" / "collapsed_family_mount_contract.json"


def groups():
    return json.loads(FIXTURES.read_text())["groups"]


def large_groups():
    return [
        {"key": "winners", "items": [{"id": f"w-{i}", "effects": 2} for i in range(400)]},
        {"key": "totals", "items": [{"id": f"t-{i}", "effects": 2} for i in range(300)]},
        {"key": "completed", "items": [{"id": f"c-{i}", "effects": 2} for i in range(744)]},
    ]


def test_large_closed_groups_mount_headers_not_children():
    plan = render_plan(large_groups(), set())
    assert len(plan["headers"]) == 3
    assert len(plan["reachable_ids"]) == 1444
    assert plan["mounted_ids"] == []
    assert plan["mounted_effects"] == 0
    assert validate_plan(large_groups(), set(), plan, initial=True) == []


def test_opening_one_group_mounts_only_that_group():
    plan = render_plan(large_groups(), {"totals"})
    assert len(plan["mounted_ids"]) == 300
    assert all(item.startswith("t-") for item in plan["mounted_ids"])
    assert plan["mounted_effects"] == 600


def test_every_item_remains_reachable_while_unmounted():
    plan = render_plan(large_groups(), set())
    assert set(plan["reachable_ids"]) == {item["id"] for group in large_groups() for item in group["items"]}


def test_open_state_survives_item_refresh_by_stable_key():
    before = render_plan(large_groups(), {"winners"})
    refreshed = large_groups()
    refreshed[0]["items"].append({"id": "w-new", "effects": 2})
    after = render_plan(refreshed, {"winners"})
    assert before["headers"][0]["open"] is True
    assert after["headers"][0]["open"] is True
    assert "w-new" in after["mounted_ids"]


def test_small_groups_may_mount_without_interaction():
    plan = render_plan(groups(), set(), eager_limit=24)
    assert len(plan["mounted_ids"]) == 6
    assert validate_plan(groups(), set(), plan, initial=True) == []


def test_eager_large_dom_is_refused_even_when_visually_collapsed():
    eager = render_plan(large_groups(), {"winners", "totals", "completed"})
    reasons = validate_plan(large_groups(), set(), eager, initial=True)
    assert set(reasons) == {"COLLAPSED_DOM_EAGER", "COLLAPSED_EFFECTS_EAGER"}


def test_dropped_tail_is_refused():
    plan = render_plan(large_groups(), set())
    plan["reachable_ids"].pop()
    assert "ITEMS_NOT_REACHABLE" in validate_plan(large_groups(), set(), plan, initial=True)
