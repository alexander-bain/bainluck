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
        # The venues' own spellings, read from production 2026-11-02.
        ("D-House, R-Senate", "R Senate, D House"),
        ("R-House, D-Senate", "D Senate, R House"),
        ("Democrats sweep", "Democrats Sweep"),
        ("Republicans sweep", "Republicans Sweep"),
    ],
)
def test_balance_outcomes_align_by_chamber_and_party(left, right):
    from app.utils.midterms_collection import outcome_key

    assert outcome_key(left) == outcome_key(right)


def _balance_cards(other):
    kalshi, polymarket = card(108619), card(112905, "polymarket")
    kalshi["outcome_count"], polymarket["outcome_count"] = 4, 5
    kalshi["top_outcomes"] = [
        {"name": n, "probability": p}
        for n, p in (("Democrats sweep", 0.735), ("D-House, R-Senate", 0.225),
                     ("Republicans sweep", 0.058), ("R-House, D-Senate", 0.007))
    ]
    polymarket["top_outcomes"] = [
        {"name": n, "probability": p}
        for n, p in (("Democrats Sweep", 0.725), ("R Senate, D House", 0.215),
                     ("Republicans Sweep", 0.045), ("D Senate, R House", 0.0065),
                     ("Other", other))
    ]
    return kalshi, polymarket


@pytest.mark.parametrize("other", [0.0005, None])
def test_a_contributor_only_outcome_under_one_percent_is_not_a_row(other):
    from app.utils.midterms_collection import blend_card

    kalshi, polymarket = _balance_cards(other)
    blended = blend_card(kalshi, [kalshi, polymarket])
    assert [o["name"] for o in blended["top_outcomes"]] == [
        "Democrats sweep", "D-House, R-Senate", "Republicans sweep", "R-House, D-Senate"]
    assert blended["outcome_count"] == 4


def test_a_contributor_only_outcome_at_one_percent_stays_a_row():
    from app.utils.midterms_collection import blend_card

    kalshi, polymarket = _balance_cards(0.01)
    blended = blend_card(kalshi, [kalshi, polymarket])
    assert blended["top_outcomes"][-1]["name"] == "Other"
    assert blended["outcome_count"] == 5


def test_explicit_twin_register_covers_all_fourteen_primary_markets():
    from app.utils.midterms_collection import (
        MARKET_IDS,
        MIDTERMS_TWIN_BY_KALSHI_ID,
        MIDTERMS_TWIN_REGISTER,
        REGISTERED_POLYMARKET_TWIN_IDS,
    )

    primary_kalshi_ids = [mid for mid in MARKET_IDS if mid != 112905]
    assert len(primary_kalshi_ids) == 14
    assert [e.kalshi_market_id for e in MIDTERMS_TWIN_REGISTER] == primary_kalshi_ids
    assert set(MIDTERMS_TWIN_BY_KALSHI_ID) == set(primary_kalshi_ids)
    assert REGISTERED_POLYMARKET_TWIN_IDS == frozenset(
        {
            112902,
            112903,
            112905,
            113056,
            113092,
            113093,
            113095,
            113097,
            113106,
            113109,
            113116,
        }
    )
    unpaired = [
        e.kalshi_market_id
        for e in MIDTERMS_TWIN_REGISTER
        if e.polymarket_market_id is None
    ]
    assert unpaired == [109095, 109918, 108629]


@pytest.mark.asyncio
async def test_registered_polymarket_twins_match_and_blend_across_all_paired_markets(
    monkeypatch,
):
    from app.routes import events, futures
    from app.services.midterms_collection import load_midterms_cards
    from app.utils.cross_source_matching import clean_outcomes
    from app.utils.midterms_collection import (
        MARKET_IDS,
        MIDTERMS_TWIN_REGISTER,
        present_midterms_sections,
    )

    def make_market(mid, name, source, outcomes):
        return SimpleNamespace(
            id=mid,
            name=name,
            source=source,
            group_id=None,
            settled_at=None,
            outcomes=[
                SimpleNamespace(
                    name=n,
                    current_probability=p,
                    is_winner=False,
                    resolution_source=None,
                )
                for n, p in outcomes
            ],
        )

    kalshi_outcomes_by_id = {
        108620: [("Democratic Party", 0.36), ("Republican Party", 0.64)],
        108621: [("Democratic Party", 0.81), ("Republican Party", 0.19)],
        108619: [
            ("Democrats sweep", 0.74),
            ("D-House, R-Senate", 0.22),
            ("Republicans sweep", 0.03),
            ("R-House, D-Senate", 0.01),
        ],
        109085: [("Adam Hamilton", 0.14), ("Roger Marshall", 0.86)],
        109088: [("Josh Turek", 0.37), ("Ashley Hinson", 0.63)],
        109082: [("Troy Jackson", 0.44), ("Susan Collins", 0.56)],
        109095: [("Democratic party", 0.48), ("Republican party", 0.52)],
        109065: [("James Talarico", 0.36), ("Ken Paxton", 0.64)],
        109072: [("Sherrod Brown", 0.52), ("Jon Husted", 0.48)],
        109068: [("Darline Graham", 0.84), ("Annie Andrews", 0.16)],
        109081: [("Abdul El-Sayed", 0.60), ("Mike Rogers", 0.40)],
        108645: [("Keisha Lance Bottoms", 0.44), ("Rick Jackson", 0.56)],
        109918: [("Yes", 0.24), ("No", 0.76)],
        108629: [("Georgia", 0.28), ("Nevada", 0.14)],
    }
    polymarket_outcomes_by_id = {
        112902: [
            ("Democratic Party", 0.40),
            ("Republican Party", 0.60),
            ("Other", None),
        ],
        112903: [
            ("Democratic Party", 0.85),
            ("Republican Party", 0.15),
            ("Other", None),
        ],
        112905: [
            ("Democrats Sweep", 0.72),
            ("R Senate, D House", 0.20),
            ("Republicans Sweep", 0.05),
            ("D Senate, R House", 0.01),
            ("Other", 0.0005),
        ],
        113093: [("Adam Hamilton (D)", 0.18), ("Roger Marshall (R)", 0.82)],
        113092: [("Josh Turek (D)", 0.41), ("Ashley Hinson (R)", 0.59)],
        113095: [("Troy Jackson (D)", 0.48), ("Susan Collins (R)", 0.52)],
        113109: [("James Talarico (D)", 0.40), ("Ken Paxton (R)", 0.60)],
        113116: [("Sherrod Brown (D)", 0.56), ("Jon Husted (R)", 0.44)],
        113106: [
            ("Darline Graham Nordone (R)", 0.88),
            ("Annie Andrews (D)", 0.12),
        ],
        113097: [("Abdul El-Sayed (D)", 0.64), ("Mike Rogers (R)", 0.36)],
        113056: [
            ("Keisha Lance Bottoms", 0.48),
            ("Rick Jackson", 0.52),
            ("Other", None),
            ("Option A", None),
            ("Option B", None),
        ],
    }

    primary = [
        make_market(
            entry.kalshi_market_id,
            entry.kalshi_name,
            "kalshi",
            kalshi_outcomes_by_id[entry.kalshi_market_id],
        )
        for entry in MIDTERMS_TWIN_REGISTER
    ]
    primary.append(
        make_market(
            112905,
            "Balance of Power: 2026 Midterms",
            "polymarket",
            polymarket_outcomes_by_id[112905],
        )
    )
    candidates = [
        make_market(
            entry.polymarket_market_id,
            entry.polymarket_name,
            "polymarket",
            polymarket_outcomes_by_id[entry.polymarket_market_id],
        )
        for entry in MIDTERMS_TWIN_REGISTER
        if entry.polymarket_market_id is not None and entry.polymarket_market_id != 112905
    ]

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return self

        def all(self):
            return self.rows

    class Database:
        def __init__(self):
            self.reads = iter((primary, candidates))

        async def execute(self, statement):
            return Result(next(self.reads))

    def serialize(market, withheld):
        surviving = [
            o
            for o in clean_outcomes(market.outcomes)
            if o.current_probability is not None
        ]
        return {
            "id": market.id,
            "name": market.name,
            "source": market.source,
            "status": "open",
            "outcome_count": len(clean_outcomes(market.outcomes)),
            "top_outcomes": [
                {"name": o.name, "probability": o.current_probability}
                for o in surviving
            ],
        }

    async def withheld_prices(db, markets):
        return {}

    monkeypatch.setattr(events, "_format_futures_for_search", serialize)
    monkeypatch.setattr(
        futures, "withheld_price_outcome_ids_for_markets", withheld_prices
    )
    cards, twins, report = await load_midterms_cards(Database(), MARKET_IDS)
    report_by_id = {row["market_id"]: row for row in report}

    assert all(row["twin_state"] != "unknown" for row in report)
    for entry in MIDTERMS_TWIN_REGISTER:
        row = report_by_id[entry.kalshi_market_id]
        if entry.polymarket_market_id is not None:
            assert row["twin_state"] == "matched", entry
            assert row["polymarket_twin_ids"] == [entry.polymarket_market_id]
            assert twins[entry.kalshi_market_id] == [entry.polymarket_market_id]
        else:
            assert row["twin_state"] == "no_twin_found", entry
            assert row["polymarket_twin_ids"] == []
            assert entry.kalshi_market_id not in twins

    sections, withheld = present_midterms_sections(members(), cards, twins)
    assert withheld == []
    served_by_id = {
        m["id"]: m["card"] for s in sections for m in s["members"]
    }
    for entry in MIDTERMS_TWIN_REGISTER:
        served = served_by_id[entry.kalshi_market_id]
        if entry.polymarket_market_id is not None:
            assert served["sources"] == ["kalshi", "polymarket"]
            assert served["source"] == "both"
        else:
            assert served["sources"] == ["kalshi"]
            assert served["source"] == "kalshi"
    # Verify equal-weight (w=0.8 each) blended probabilities on Senate control, SC Senate, and GA Governor:
    assert served_by_id[108620]["top_outcomes"][0]["probability"] == pytest.approx(0.38)
    assert served_by_id[109068]["top_outcomes"][0]["probability"] == pytest.approx(0.86)
    assert served_by_id[108645]["top_outcomes"][0]["probability"] == pytest.approx(0.46)
    assert served_by_id[108645]["outcome_count"] == 2


def test_south_carolina_alias_lives_on_register_entry_not_generic_outcome_key():
    from app.utils.midterms_collection import MIDTERMS_TWIN_BY_KALSHI_ID, outcome_key

    assert outcome_key("Darline Graham Nordone (R)") == "darline graham nordone"
    sc_entry = MIDTERMS_TWIN_BY_KALSHI_ID[109068]
    assert outcome_key("Darline Graham Nordone (R)", sc_entry) == "darline graham"
    assert outcome_key("Darline Graham Nordone (R)", MIDTERMS_TWIN_BY_KALSHI_ID[109085]) == "darline graham nordone"


@pytest.mark.asyncio
async def test_registered_twin_failing_outcome_check_reports_register_mismatch_without_pool_scan(
    monkeypatch,
):
    from app.routes import events, futures
    from app.services.midterms_collection import load_midterms_cards

    def make_market(mid, name, source, outcomes):
        return SimpleNamespace(
            id=mid,
            name=name,
            source=source,
            group_id=None,
            settled_at=None,
            outcomes=[
                SimpleNamespace(
                    name=n,
                    current_probability=p,
                    is_winner=False,
                    resolution_source=None,
                )
                for n, p in outcomes
            ],
        )

    primary = [
        make_market(
            109085,
            "Kansas Senate winner?",
            "kalshi",
            [("Adam Hamilton", 0.14), ("Roger Marshall", 0.86)],
        ),
        make_market(
            109082,
            "Maine Senate winner?",
            "kalshi",
            [("Troy Jackson", 0.44), ("Susan Collins", 0.56)],
        ),
    ]
    # 113093 (registered twin for 109085) has a drifted outcome name ("Replacement Nominee"),
    # while 113095 (in the pool for 109082) happens to carry 109085's question/outcomes:
    # 109085 must report "register_mismatch" and must NOT fuzzy-match 113095 from the pool.
    candidates = [
        make_market(
            113093,
            "Kansas Senate Election Winner",
            "polymarket",
            [("Replacement Nominee (D)", 0.18), ("Roger Marshall (R)", 0.82)],
        ),
        make_market(
            113095,
            "Kansas Senate Election Winner",
            "polymarket",
            [("Adam Hamilton (D)", 0.18), ("Roger Marshall (R)", 0.82)],
        ),
    ]

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return self

        def all(self):
            return self.rows

    class Database:
        def __init__(self):
            self.reads = iter((primary, candidates))

        async def execute(self, statement):
            return Result(next(self.reads))

    def serialize(market, withheld):
        return {
            "id": market.id,
            "name": market.name,
            "source": market.source,
            "status": "open",
            "outcome_count": len(market.outcomes),
            "top_outcomes": [
                {"name": o.name, "probability": o.current_probability}
                for o in market.outcomes
            ],
        }

    async def withheld_prices(db, markets):
        return {}

    monkeypatch.setattr(events, "_format_futures_for_search", serialize)
    monkeypatch.setattr(
        futures, "withheld_price_outcome_ids_for_markets", withheld_prices
    )
    _, twins, report = await load_midterms_cards(Database(), [109085, 109082])
    report_by_id = {row["market_id"]: row for row in report}

    assert report_by_id[109085]["twin_state"] == "register_mismatch"
    assert report_by_id[109085]["polymarket_twin_ids"] == [113093]
    assert report_by_id[109082]["twin_state"] == "register_mismatch"
    assert report_by_id[109082]["polymarket_twin_ids"] == [113095]
    assert twins == {}
