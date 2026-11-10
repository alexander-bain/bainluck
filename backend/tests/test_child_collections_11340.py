"""Tests for child collections from an event hub (#11340)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.utils.midterms_collection import (
    MIDTERMS_CLOSEST_RACES_CHILD_NAME,
    MIDTERMS_CLOSEST_RACES_CHILD_SLUG,
    midterms_children,
)
from app.utils.roundup_containers import (
    CONTAINERS_DATA_DIR,
    RoundupMembers,
    build_roundup_producer_from_definition,
    compose_roundup_container,
    load_roundup_definition,
    roundup_container_id,
)

FIXED_NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def _open_race_section(count: int, *, status: str = "open") -> list[dict]:
    return [
        {
            "class": "senate_races",
            "title": "Competitive Senate races",
            "layout": "table",
            "count": count,
            "members": [
                {
                    "type": "market",
                    "id": 2000 + idx,
                    "destination": {
                        "kind": "market",
                        "id": 2000 + idx,
                        "web": f"/futures/{2000 + idx}",
                        "api": f"/api/futures/{2000 + idx}",
                    },
                    "card": {
                        "id": 2000 + idx,
                        "name": f"Senate race {idx}",
                        "status": status,
                        "top_outcomes": [
                            {"name": "Republican", "probability": 0.51},
                            {"name": "Democrat", "probability": 0.49},
                        ],
                    },
                    "event_id": None,
                }
                for idx in range(count)
            ],
        }
    ]


def test_midterms_children_links_closest_races_when_at_least_three_open() -> None:
    sections = _open_race_section(4, status="open")
    children = midterms_children(sections, include_children=True)
    assert len(children) == 1
    child = children[0]
    assert child["id"] == roundup_container_id(MIDTERMS_CLOSEST_RACES_CHILD_SLUG)
    assert child["slug"] == MIDTERMS_CLOSEST_RACES_CHILD_SLUG
    assert child["name"] == MIDTERMS_CLOSEST_RACES_CHILD_NAME
    assert child["publication_state"] == "published"
    assert child["destination"] == {
        "kind": "container",
        "slug": "roundup-closest-races",
        "web": "/collections/roundup-closest-races",
        "api": "/api/containers/roundup-closest-races",
    }


def test_midterms_children_withholds_child_when_fewer_than_three_open() -> None:
    sections = _open_race_section(2, status="open")
    assert midterms_children(sections, include_children=True) == []


def test_midterms_children_withholds_child_when_include_children_false() -> None:
    sections = _open_race_section(5, status="open")
    assert midterms_children(sections, include_children=False) == []


def test_midterms_children_ignores_settled_races_in_open_count() -> None:
    sections = _open_race_section(4, status="settled")
    assert midterms_children(sections, include_children=True) == []


def test_closest_races_definition_declares_midterms_parent_and_composes_parent_link() -> None:
    defn = load_roundup_definition(CONTAINERS_DATA_DIR / "roundup-closest-races.json")
    assert defn["parent_slug"] == "midterms-2026"
    assert defn["parent_name"] == "Midterms 2026"

    producer = build_roundup_producer_from_definition(defn)
    assert producer.parent_slug == "midterms-2026"
    assert producer.parent_name == "Midterms 2026"

    payload = compose_roundup_container(
        producer,
        RoundupMembers(
            members=_open_race_section(3)[0]["members"],
        ),
    )
    assert payload is not None
    assert payload["container"]["parent_container_id"] == roundup_container_id(
        "midterms-2026"
    )
    assert payload["parent"] == {
        "slug": "midterms-2026",
        "name": "Midterms 2026",
        "destination": {
            "kind": "container",
            "slug": "midterms-2026",
            "web": "/collections/midterms-2026",
            "api": "/api/containers/midterms-2026",
        },
    }


@pytest.mark.asyncio
async def test_live_published_parent_child_pairs_and_serve_roundup_withholding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.utils import container_corrections as cc
    from app.utils import roundup_containers as rc

    now = FIXED_NOW
    assert now.year == 2026

    dec_defn = load_roundup_definition(CONTAINERS_DATA_DIR / "by-december-31.json")
    nov_defn = load_roundup_definition(CONTAINERS_DATA_DIR / "by-november-30.json")
    assert [c["slug"] for c in dec_defn["children"]] == ["by-november-30"]
    assert nov_defn["parent_slug"] == "by-december-31"
    assert nov_defn["parent_name"] == "By December 31"

    dec_producer = build_roundup_producer_from_definition(dec_defn)
    nov_producer = build_roundup_producer_from_definition(nov_defn)
    dec_payload = compose_roundup_container(
        dec_producer,
        RoundupMembers(members=_open_race_section(3)[0]["members"]),
    )
    nov_payload = compose_roundup_container(
        nov_producer,
        RoundupMembers(members=_open_race_section(3)[0]["members"]),
    )
    assert dec_payload is not None and nov_payload is not None
    assert dec_payload["children"][0]["publication_state"] == "published"
    assert dec_payload["children"][0]["slug"] == "by-november-30"
    assert nov_payload["parent"]["slug"] == "by-december-31"

    # When child is published, serve_roundup includes it; when include_children=False, it is omitted.
    async def _fake_eval_published(prod, _db, **_kw):
        if prod.slug == "by-december-31":
            return {"id": "1"}, dec_payload
        if prod.slug == "by-november-30":
            return {"id": "2"}, nov_payload
        return None, None

    monkeypatch.setattr(rc, "evaluate_roundup_producer", _fake_eval_published)
    served_with_children = await rc.serve_roundup(
        "by-december-31", [], include_children=True
    )
    assert [c["slug"] for c in served_with_children["children"]] == ["by-november-30"]

    served_without_children = await rc.serve_roundup(
        "by-december-31", [], include_children=False
    )
    assert served_without_children["children"] == []

    # When child or parent roundup refuses (unpublished), serve_roundup withholds the link.
    async def _fake_eval_child_refused(prod, _db, **_kw):
        if prod.slug == "by-december-31":
            return {"id": "1"}, dec_payload
        return None, None

    monkeypatch.setattr(rc, "evaluate_roundup_producer", _fake_eval_child_refused)
    served_child_refused = await rc.serve_roundup(
        "by-december-31", [], include_children=True
    )
    assert served_child_refused["children"] == []

    async def _fake_eval_parent_refused(prod, _db, **_kw):
        if prod.slug == "by-november-30":
            return {"id": "2"}, nov_payload
        return None, None

    monkeypatch.setattr(rc, "evaluate_roundup_producer", _fake_eval_parent_refused)
    served_parent_refused = await rc.serve_roundup(
        "by-november-30", [], include_children=True
    )
    assert "parent" not in served_parent_refused
    assert served_parent_refused["container"]["parent_container_id"] is None

    # Non-roundup parent (midterms-2026) is checked via read_published.
    races_defn = load_roundup_definition(
        CONTAINERS_DATA_DIR / "roundup-closest-races.json"
    )
    races_producer = build_roundup_producer_from_definition(races_defn)
    races_payload = compose_roundup_container(
        races_producer,
        RoundupMembers(members=_open_race_section(3)[0]["members"]),
    )
    assert races_payload is not None

    async def _fake_eval_races(prod, _db, **_kw):
        if prod.slug == "roundup-closest-races":
            return {"id": "3"}, races_payload
        return None, None

    monkeypatch.setattr(rc, "evaluate_roundup_producer", _fake_eval_races)

    async def _fake_read_published_ok(_db, slug: str):
        return SimpleNamespace(
            state=cc.READ_PUBLISHED if slug == "midterms-2026" else cc.READ_UNAVAILABLE
        )

    monkeypatch.setattr(cc, "read_published", _fake_read_published_ok)
    served_races_ok = await rc.serve_roundup(
        "roundup-closest-races", [], include_children=True
    )
    assert served_races_ok["parent"]["slug"] == "midterms-2026"

    async def _fake_read_published_withdrawn(_db, _slug: str):
        return SimpleNamespace(state="withdrawn")

    monkeypatch.setattr(cc, "read_published", _fake_read_published_withdrawn)
    served_races_withdrawn = await rc.serve_roundup(
        "roundup-closest-races", [], include_children=True
    )
    assert "parent" not in served_races_withdrawn
    assert served_races_withdrawn["container"]["parent_container_id"] is None

