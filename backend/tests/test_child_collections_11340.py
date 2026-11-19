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


def test_registered_builtin_producers_carry_parent_and_children_metadata() -> None:
    from app.utils.roundup_containers import ROUNDUP_PRODUCERS

    dec_prod = ROUNDUP_PRODUCERS["by-december-31"]
    nov_prod = ROUNDUP_PRODUCERS["by-november-30"]
    races_prod = ROUNDUP_PRODUCERS["roundup-closest-races"]

    assert [c["slug"] for c in dec_prod.children] == ["by-november-30"]
    assert nov_prod.parent_slug == "by-december-31"
    assert nov_prod.parent_name == "By December 31"
    assert races_prod.parent_slug == "midterms-2026"
    assert races_prod.parent_name == "Midterms 2026"


@pytest.mark.asyncio
async def test_produce_register_closest_applies_withheld_prices_and_hub_checks_all_registered_twins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.routes import events, futures
    from app.services.midterms_collection import load_midterms_cards
    from app.utils.register_closest import (
        CLOSEST_RACES_DEFINITION,
        produce_register_closest,
        select_register_closest,
    )
    from app.utils.roundup_containers import RoundupRefusal

    def _make_orm_market(mid: int, name: str, source: str, outcomes: list[tuple[int, str, float]], *, is_settled: bool = False):
        return SimpleNamespace(
            id=mid,
            name=name,
            source=source,
            status="settled" if is_settled else "open",
            mutually_exclusive=True,
            resolution_date=None,
            updated_at=FIXED_NOW,
            settled_at=FIXED_NOW if is_settled else None,
            group_id=None,
            outcomes=[
                SimpleNamespace(
                    id=oid,
                    name=oname,
                    current_probability=prob,
                    is_winner=(idx == 0) if is_settled else False,
                    resolution_source="api_settlement" if is_settled else None,
                    last_updated=FIXED_NOW,
                )
                for idx, (oid, oname, prob) in enumerate(outcomes)
            ],
        )

    # Three open Senate races in the Midterms register (109085 KS, 109082 ME, 109068 SC),
    # where 109085 has outcome 1090851 withheld by withheld_price_outcome_ids_for_markets:
    orm_rows = [
        _make_orm_market(
            109085,
            "Kansas Senate winner?",
            "kalshi",
            [(1090851, "Adam Hamilton", 0.48), (1090852, "Roger Marshall", 0.52)],
        ),
        _make_orm_market(
            109082,
            "Maine Senate winner?",
            "kalshi",
            [(1090821, "Troy Jackson", 0.49), (1090822, "Susan Collins", 0.51)],
        ),
        _make_orm_market(
            109068,
            "South Carolina Senate winner?",
            "kalshi",
            [(1090681, "Annie Andrews", 0.47), (1090682, "Lindsey Graham", 0.53)],
        ),
    ]

    class _FakeScalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return _FakeScalars(self._rows)

    class _FakeDb:
        apply_withheld_prices = True

        async def execute(self, _stmt):
            return _FakeResult(orm_rows)

    async def _fake_withheld(_db, _markets):
        return {109085: {1090851}}

    monkeypatch.setattr(futures, "withheld_price_outcome_ids_for_markets", _fake_withheld)

    res = await produce_register_closest(_FakeDb(), CLOSEST_RACES_DEFINITION, now=FIXED_NOW)
    assert isinstance(res, RoundupRefusal)
    assert ("register_closest", "unpriced_outcome:109085") in res.reasons
    assert ("register_closest", "too_few_open_races") in res.reasons

    # Also verify load_midterms_cards includes a registered twin in cards even when
    # is_midterms_twin fails (e.g. drifted outcome label while primary settled and twin still priced):
    settled_primary = [
        _make_orm_market(
            109085,
            "Kansas Senate winner?",
            "kalshi",
            [(1090851, "Adam Hamilton", 0.0), (1090852, "Roger Marshall", 1.0)],
            is_settled=True,
        )
    ]
    drifted_open_twin = [
        _make_orm_market(
            113093,
            "Kansas Senate Election Winner",
            "polymarket",
            [(1130931, "Replacement Nominee (D)", 0.48), (1130932, "Roger Marshall (R)", 0.52)],
            is_settled=False,
        )
    ]

    class _HubDb:
        def __init__(self):
            self._reads = iter((settled_primary, drifted_open_twin))

        async def execute(self, _stmt):
            return _FakeResult(next(self._reads))

    def _serialize(market, _withheld):
        return {
            "id": market.id,
            "name": market.name,
            "source": market.source,
            "status": market.status,
            "settled_winner": "Roger Marshall" if market.status == "settled" else None,
            "outcome_count": len(market.outcomes),
            "top_outcomes": [
                {"id": o.id, "name": o.name, "probability": o.current_probability}
                for o in market.outcomes
            ],
        }

    async def _no_withheld(_db, _markets):
        return {}

    monkeypatch.setattr(events, "_format_futures_for_search", _serialize)
    monkeypatch.setattr(futures, "withheld_price_outcome_ids_for_markets", _no_withheld)

    cards, twins, _ = await load_midterms_cards(_HubDb(), [109085])
    assert twins == {}
    assert 113093 in cards
    hub_check = select_register_closest(cards)
    assert isinstance(hub_check, RoundupRefusal)
    assert hub_check.reasons == (("register_closest", "settled_in_register_still_priced:109085"),)


def _oscars_edition_fixture(
    *,
    parent_slug: str = "oscars-2027",
    container_id: int = 9901,
    featured_film: str = "The Odyssey",
    sparse_film: str = "Small Indie",
    advancement_count: int = 7,
    mention_count: int = 0,
) -> tuple[list[dict], dict[int, dict]]:
    own_members: list[dict] = []
    cards: dict[int, dict] = {}
    cats = ["Best Picture", "Best Director", "Best Original Score", "Best Cinematography"]
    mid = 8000
    for cat in cats:
        mid += 1
        own_members.append({"id": mid, "type": "market", "class": "title", "container_id": container_id})
        cards[mid] = {
            "id": mid,
            "name": f"Oscar Winner: {cat}",
            "status": "open",
            "source": "kalshi",
            "top_outcomes": [
                {"id": mid * 10 + 1, "name": featured_film, "probability": 0.48},
                {"id": mid * 10 + 2, "name": sparse_film if cat == "Best Picture" else "Other Contender", "probability": 0.22},
            ],
        }
    for idx in range(advancement_count):
        mid += 1
        own_members.append({"id": mid, "type": "market", "class": "advancement", "container_id": container_id})
        cards[mid] = {
            "id": mid,
            "name": f"Oscar Nominees: Category {idx + 1}",
            "status": "open",
            "source": "kalshi",
            "top_outcomes": [
                {"id": mid * 10 + 1, "name": featured_film if idx < 4 else "Ensemble Film", "probability": 0.84},
                {"id": mid * 10 + 2, "name": "Another Nominee", "probability": 0.51},
            ],
        }
    for idx in range(mention_count):
        mid += 1
        own_members.append({"id": mid, "type": "market", "class": "side_question", "container_id": container_id})
        cards[mid] = {
            "id": mid,
            "name": f"Oscars acceptance speech mention #{idx + 1}",
            "status": "open",
            "source": "kalshi",
            "top_outcomes": [{"id": mid * 10 + 1, "name": "Yes", "probability": 0.35}],
        }
    # Add one settled market on featured_film to prove settled rows never inflate counts
    mid += 1
    own_members.append({"id": mid, "type": "market", "class": "side_question", "container_id": container_id})
    cards[mid] = {
        "id": mid,
        "name": "Settled Oscar market",
        "status": "settled",
        "source": "kalshi",
        "top_outcomes": [{"id": mid * 10 + 1, "name": featured_film, "probability": 1.0}],
    }
    return own_members, cards


def test_automatic_child_discovery_oscars_nominations_odyssey_sparse_and_held_out_edition() -> None:
    from app.utils.discovered_child_collections import (
        discover_children_from_admitted_inventory,
        event_hub_child_discovery_enabled,
    )

    assert event_hub_child_discovery_enabled() is False

    # 1. Oscars 2027: discovers Nominations (7 open) + The Odyssey (8 open across title+advancement),
    #    withholds sparse Small Indie (1 market) and withholds Mentions (0 markets).
    own, cards = _oscars_edition_fixture(
        parent_slug="oscars-2027",
        featured_film="The Odyssey",
        sparse_film="Small Indie",
        advancement_count=7,
        mention_count=2,  # below MIN_MENTION_CHILD_MARKETS (4) -> stays ungrouped
    )
    children = discover_children_from_admitted_inventory(
        "oscars-2027", "Oscars 2027", own, cards
    )
    slugs = [c["slug"] for c in children]
    assert slugs == [
        "oscars-2027-nominations",
        "oscars-2027-subject-the-odyssey",
    ]
    by_slug = {c["slug"]: c for c in children}
    assert by_slug["oscars-2027-nominations"]["member_count"] == 7
    assert by_slug["oscars-2027-subject-the-odyssey"]["member_count"] == 8  # excludes settled market!
    assert all(c["cross_listed_in_parent"] is True for c in children)

    # 2. When mention inventory is coherent (>= 4 open mention markets), Mentions child also qualifies.
    own_m, cards_m = _oscars_edition_fixture(mention_count=4)
    slugs_m = [
        c["slug"]
        for c in discover_children_from_admitted_inventory(
            "oscars-2027", "Oscars 2027", own_m, cards_m
        )
    ]
    assert "oscars-2027-mentions" in slugs_m

    # 3. Sparse advancement (< 6 open nomination markets): stays an ordinary inline section!
    own_sparse, cards_sparse = _oscars_edition_fixture(
        featured_film="Two Category Film",
        advancement_count=3,
    )
    # Trim featured_film to only 3 markets total -> neither nominations nor subject child created
    for k in list(cards_sparse)[3:]:
        for o in cards_sparse[k]["top_outcomes"]:
            if o["name"] == "Two Category Film":
                o["name"] = f"Distinct Film {k}"
    assert (
        discover_children_from_admitted_inventory(
            "oscars-2027", "Oscars 2027", own_sparse, cards_sparse
        )
        == []
    )

    # 4. Held-out edition (oscars-2028 with 'Heat 2') works with ZERO bespoke member code.
    own_28, cards_28 = _oscars_edition_fixture(
        parent_slug="oscars-2028",
        container_id=9902,
        featured_film="Heat 2",
        advancement_count=6,
    )
    children_28 = discover_children_from_admitted_inventory(
        "oscars-2028", "Oscars 2028", own_28, cards_28
    )
    assert [c["slug"] for c in children_28] == [
        "oscars-2028-nominations",
        "oscars-2028-subject-heat-2",
    ]


@pytest.mark.asyncio
async def test_discovered_child_route_switched_off_for_readers_and_withholds_withdrawn_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException
    from app.routes import admin_utils, containers as containers_route
    from app.utils import container_corrections as cc
    from app.utils import discovered_child_collections as dcc

    own, cards = _oscars_edition_fixture()
    monkeypatch.setattr(containers_route, "containers_read_enabled", lambda: True)

    async def _fake_admin_auth(_secret, req, _db=None) -> bool:
        hdrs = getattr(req, "headers", None) or {}
        return hdrs.get("Authorization") == "Bearer admin-preview"

    monkeypatch.setattr(admin_utils, "_check_admin_auth", _fake_admin_auth)

    async def _fake_read_published(_db, slug: str, **_kw):
        if slug == "oscars-2027":
            return SimpleNamespace(
                state=cc.READ_PUBLISHED,
                slug="oscars-2027",
                container_id=9901,
                revision=42,
                reason=None,
                members=own,
            )
        return SimpleNamespace(state=cc.READ_UNAVAILABLE, slug=slug)

    monkeypatch.setattr(cc, "read_published", _fake_read_published)
    monkeypatch.setattr(dcc, "read_published", _fake_read_published)
    monkeypatch.setattr(containers_route, "read_published", _fake_read_published)

    async def _fake_snap(_cid: int, _rev: int):
        return {
            "shown_ids": [m["id"] for m in own],
            "shown_count": len(own),
            "eligible_count": len(own),
            "withheld": {},
            "inventory_complete": True,
        }

    async def _fake_hydrate(_db, mids, **_kw):
        return ({i: cards[i] for i in mids if i in cards}, {i: None for i in mids}, {})

    monkeypatch.setattr(containers_route, "_read_theme_snapshot", _fake_snap)
    monkeypatch.setattr(containers_route, "_hydrate_market_cards", _fake_hydrate)

    class _FakeRowResult:
        def fetchone(self):
            return (9901, "theme", "Oscars 2027", "oscars-2027", "entertainment", "open", None, None, None)

    class _FakeThemeDb:
        async def execute(self, stmt, *_a, **_kw):
            sql = str(stmt)
            if "SELECT name, category" in sql:
                res = SimpleNamespace(fetchone=lambda: ("Oscars 2027", "entertainment"))
                return res
            return _FakeRowResult()

    public_req = SimpleNamespace(headers={})
    admin_req = SimpleNamespace(headers={"Authorization": "Bearer admin-preview"})

    # 1. Public reader while switched OFF: parent hub keeps children=[] and child URL returns 404.
    pub_hub = await containers_route.get_container(
        slug="oscars-2027",
        include_children=True,
        revision=None,
        cursor=None,
        limit=None,
        market_revision=None,
        market_cursor=None,
        market_limit=None,
        compact=True,
        debug_timing=False,
        db=_FakeThemeDb(),
        request=public_req,
    )
    assert pub_hub["children"] == []

    with pytest.raises(HTTPException) as pub_exc:
        await containers_route.get_container(
            slug="oscars-2027-subject-the-odyssey",
            include_children=True,
            revision=None,
            cursor=None,
            limit=None,
            market_revision=None,
            market_cursor=None,
            market_limit=None,
            compact=True,
            debug_timing=False,
            db=_FakeThemeDb(),
            request=public_req,
        )
    assert pub_exc.value.status_code == 404

    # 2. Admin previewer sees discovered children on oscars-2027 AND opens child hub cleanly.
    adm_hub = await containers_route.get_container(
        slug="oscars-2027",
        include_children=True,
        revision=None,
        cursor=None,
        limit=None,
        market_revision=None,
        market_cursor=None,
        market_limit=None,
        compact=True,
        debug_timing=False,
        db=_FakeThemeDb(),
        request=admin_req,
    )
    adm_child_slugs = [c["slug"] for c in adm_hub["children"]]
    assert "oscars-2027-nominations" in adm_child_slugs
    assert "oscars-2027-subject-the-odyssey" in adm_child_slugs

    odyssey_child = await containers_route.get_container(
        slug="oscars-2027-subject-the-odyssey",
        include_children=True,
        revision=None,
        cursor=None,
        limit=None,
        market_revision=None,
        market_cursor=None,
        market_limit=None,
        compact=True,
        debug_timing=False,
        db=_FakeThemeDb(),
        request=admin_req,
    )
    assert odyssey_child["state"] == "published"
    assert odyssey_child["member_count"] == 8
    assert odyssey_child["parent"]["slug"] == "oscars-2027"
    assert [s["title"] for s in odyssey_child["sections"]] == [
        "Award Winner Markets",
        "Nomination Markets",
    ]

    # 3. Withdrawn parent immediately withholds child hub (zero leaked members or parent link).
    async def _fake_withdrawn(_db, _slug: str, **_kw):
        return SimpleNamespace(
            state="withdrawn",
            slug="oscars-2027",
            container_id=9901,
            revision=43,
            reason="ceremony_cancelled",
            members=own,
        )

    monkeypatch.setattr(dcc, "read_published", _fake_withdrawn)
    withdrawn_child = await dcc.serve_discovered_child_collection(
        "oscars-2027-subject-the-odyssey", _FakeThemeDb()
    )
    assert withdrawn_child["state"] == "withdrawn"
    assert withdrawn_child["sections"] == []
    assert withdrawn_child["member_count"] == 0
    assert "parent" not in withdrawn_child



