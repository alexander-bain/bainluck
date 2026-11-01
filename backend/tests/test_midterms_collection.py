"""The curated election page keeps its races, blend and official results."""

from datetime import datetime, timezone
from types import SimpleNamespace
import pytest


def card(mid, source="kalshi", probabilities=(0.52, 0.48)):
    return {
        "id": mid,
        "name": "Maine Senate winner?",
        "source": source,
        "status": "open",
        "outcome_count": 2,
        "top_outcomes": [
            {"name": n, "probability": p}
            for n, p in zip(("Susan Collins", "Graham Platner"), probabilities)
        ],
    }


def members():
    from app.utils.midterms_collection import MANIFEST

    return [
        {"id": mid, "type": "market", "class": s["key"], "source": "human"}
        for s in MANIFEST["sections"]
        for mid in s["market_ids"]
    ]


def test_four_sections_keep_exact_reviewed_order_and_balance_has_one_blended_card():
    from app.utils.midterms_collection import present_midterms_sections, midterms_pin

    cards = {m["id"]: card(m["id"]) for m in members()}
    cards[112905] = card(112905, "polymarket", (0.58, 0.42))
    sections, withheld = present_midterms_sections(members(), cards)
    assert [s["title"] for s in sections] == [
        "Congress control",
        "Balance of power",
        "The closest Senate races",
        "Governors",
    ]
    assert [m["id"] for m in sections[2]["members"]] == [
        109085,
        109088,
        109082,
        109095,
        109065,
        109072,
        109068,
        109081,
    ]
    assert len(sections[1]["members"]) == 1
    blended = sections[1]["members"][0]["card"]
    assert blended["top_outcomes"][0]["probability"] == 0.55
    assert blended["sources"] == ["kalshi", "polymarket"]
    assert withheld == []


def test_withdrawn_member_and_unreviewed_extras_never_reappear():
    from app.utils.midterms_collection import present_midterms_sections, midterms_pin

    supplied = [m for m in members() if m["id"] != 109085]
    supplied.append({"id": 999, "type": "market", "class": "senate_races"})
    cards = {m["id"]: card(m["id"]) for m in supplied}
    sections, _ = present_midterms_sections(supplied, cards)
    ids = [m["id"] for s in sections for m in s["members"]]
    assert 109085 not in ids
    assert 999 not in ids


def test_first_official_venue_result_wins_while_other_venue_is_still_open():
    from app.utils.midterms_collection import present_midterms_sections, midterms_pin

    primary = card(108619)
    twin = card(112905, "polymarket")
    twin.update(status="resolved", settled_at="2026-11-04T03:00:00+00:00")
    twin["top_outcomes"][1].update(is_winner=True, resolution_source="api_settlement")
    sections, _ = present_midterms_sections(members(), {108619: primary, 112905: twin})
    settled = sections[1]["members"][0]["card"]
    assert settled["settled_winner"] == "Graham Platner"
    assert all(o["probability"] is None for o in settled["top_outcomes"])
    primary.update(status="resolved", settled_at="2026-11-04T04:00:00+00:00")
    primary["top_outcomes"][0].update(
        is_winner=True, resolution_source="api_settlement"
    )
    sections, _ = present_midterms_sections(members(), {108619: primary, 112905: twin})
    assert sections[1]["members"][0]["card"]["settled_winner"] == "Graham Platner"


def test_a_certain_price_or_inferred_grade_is_not_official_settlement():
    from app.utils.midterms_collection import present_midterms_sections, midterms_pin

    primary = card(109085, probabilities=(1, 0))
    primary["top_outcomes"][0].update(
        is_winner=True, resolution_source="price_inference"
    )
    sections, _ = present_midterms_sections(members(), {109085: primary})
    assert sections[2]["members"][0]["card"].get("settled_winner") is None
    assert sections[2]["members"][0]["card"]["top_outcomes"][0]["probability"] == 1


def test_pin_uses_live_democratic_numbers_and_expires_after_november_six_pacific():
    from app.utils.midterms_collection import present_midterms_sections, midterms_pin

    cards = {108620: card(108620), 108621: card(108621)}
    for c in cards.values():
        c["top_outcomes"] = [
            {"name": "Republican", "probability": 0.585},
            {"name": "Democratic", "probability": 0.415},
        ]
    sections, _ = present_midterms_sections(members(), cards)
    payload = {"state": "published", "slug": "midterms-2026", "sections": sections}
    assert (
        midterms_pin(payload, datetime(2026, 11, 6, 23, tzinfo=timezone.utc))[
            "subtitle"
        ]
        == "Senate 41% D - House 41% D"
    )
    assert midterms_pin(payload, datetime(2026, 11, 7, 8, tzinfo=timezone.utc)) is None
    assert (
        midterms_pin(
            {**payload, "state": "withdrawn"},
            datetime(2026, 11, 3, tzinfo=timezone.utc),
        )
        is None
    )


@pytest.mark.asyncio
async def test_midterms_route_uses_publication_and_live_market_hydration(monkeypatch):
    from app.routes import containers
    from app.utils.container_corrections import PublishedRead

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("COLLECTIONS_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_COLLECTIONS_ENABLED", "true")

    async def published(db, slug):
        return PublishedRead(
            state="published",
            slug=slug,
            container_id=901,
            revision=1,
            members=members(),
        )

    async def hydrate(db, market_ids):
        return {m["id"]: card(m["id"]) for m in members()}, {}, []

    monkeypatch.setattr(containers, "read_published", published)
    monkeypatch.setattr(containers, "load_midterms_cards", hydrate, raising=False)
    result = await containers.get_container("midterms-2026", True, SimpleNamespace())
    assert result["container"]["name"] == "Midterms 2026"
    assert result["member_count"] == 14
    assert result["sections"][0]["layout"] == "party"


@pytest.mark.asyncio
async def test_midterms_switches_fail_closed(monkeypatch):
    from fastapi import HTTPException
    from app.routes import containers

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("COLLECTIONS_ENABLED", "false")
    monkeypatch.setenv("CONTAINER_COLLECTIONS_ENABLED", "true")
    with pytest.raises(HTTPException) as error:
        await containers.get_container("midterms-2026", True, SimpleNamespace())
    assert error.value.status_code == 404


def test_healthy_twin_keeps_both_candidate_names_when_primary_price_is_missing():
    from app.utils.midterms_collection import blend_card

    primary = card(109085)
    primary["top_outcomes"] = primary["top_outcomes"][:1]
    twin = card(100, "polymarket", (0.6, 0.4))
    result = blend_card(primary, [primary, twin])
    assert [o["name"] for o in result["top_outcomes"]] == [
        "Susan Collins",
        "Graham Platner",
    ]
    assert result["top_outcomes"][1]["probability"] == 0.4


def test_balance_field_leader_is_selected_after_blending():
    from app.utils.midterms_collection import present_midterms_sections

    primary, twin = card(108619), card(112905, "polymarket")
    primary["top_outcomes"] = [
        {"name": "A", "probability": 0.55},
        {"name": "B", "probability": 0.45},
    ]
    twin["top_outcomes"] = [
        {"name": "A", "probability": 0.3},
        {"name": "B", "probability": 0.7},
    ]
    sections, _ = present_midterms_sections(members(), {108619: primary, 112905: twin})
    assert sections[1]["members"][0]["card"]["top_outcomes"][0]["name"] == "B"


def test_missing_candidate_price_does_not_turn_a_two_candidate_race_into_yes_no():
    from app.utils.midterms_collection import blend_card

    primary = card(109085)
    primary["top_outcomes"] = primary["top_outcomes"][:1]
    assert blend_card(primary, [primary])["outcome_count"] == 2


@pytest.mark.parametrize(
    "left,right",
    [
        ("Democratic House and Republican Senate", "R Senate / D House"),
        ("Republican House and Senate", "R House / R Senate"),
        ("Democratic House and Senate", "D Senate / D House"),
    ],
)
def test_balance_outcomes_align_by_chamber_and_party(left, right):
    from app.utils.midterms_collection import outcome_key

    assert outcome_key(left) == outcome_key(right)
