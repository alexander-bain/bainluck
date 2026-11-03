"""#10354 — the NFL division register and the round-up producer.

Pins Alex's 2026-11-02 instruction (an explicit eight-pair register, not fuzzy
matching) and the R4 membership rulings: all eight divisions must blend from
both venues or there is no card; the four lowest leaders are shown, highest
first; the footer is the ruled wording; every number is the blend.

`nfl_division_boards_20261102.json` is the sixteen registered rows as
production served them on 2026-11-02 (public `GET /api/futures/{id}`).
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.utils.discover_bundles import (
    NFL_DIVISION_ROUNDUP_COLLECTION_REF,
    NFL_DIVISION_ROUNDUP_FOOTER,
    NFL_DIVISION_ROUNDUP_HREF,
    NFL_DIVISION_ROUNDUP_SECTION_TITLE,
    NFL_DIVISION_ROUNDUP_SLUG,
    NFL_DIVISION_ROUNDUP_TITLE,
    assemble_nfl_division_roundup,
    nfl_division_roundup,
    nfl_division_roundup_revision,
    reset_nfl_division_roundup_cache_for_tests,
)
from app.utils.nfl_division_register import (
    NFL_DIVISION_REGISTER,
    Refusal,
    board_from_row,
    compose_division,
    compose_register,
    register_identities,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "nfl_division_boards_20261102.json").read_text()
)


def boards(markets=None):
    return [board_from_row(m) for m in (markets if markets is not None else FIXTURE["markets"])]


def markets_copy():
    return copy.deepcopy(FIXTURE["markets"])


def row_for(markets, source, external_id):
    return next(m for m in markets if m["source"] == source and m["external_id"] == external_id)


# ── The register itself ─────────────────────────────────────────────────────


def test_the_register_is_exactly_eight_divisions_and_thirty_two_clubs():
    divisions = [p.division for p in NFL_DIVISION_REGISTER]
    assert sorted(divisions) == sorted(
        f"{c} {d}" for c in ("AFC", "NFC") for d in ("East", "North", "South", "West")
    )
    clubs = [c.club for p in NFL_DIVISION_REGISTER for c in p.clubs]
    assert len(clubs) == 32 and len(set(clubs)) == 32


def test_every_venue_identity_is_unique():
    ids = register_identities()
    assert len(ids) == 16 and len(set(ids)) == 16


def test_every_registered_outcome_name_is_what_production_stores():
    """The register was read off production; this keeps it honest against the capture."""
    for pair in NFL_DIVISION_REGISTER:
        k = row_for(FIXTURE["markets"], "kalshi", pair.kalshi_event_ticker)
        p = row_for(FIXTURE["markets"], "polymarket", pair.polymarket_event_id)
        assert {o["name"] for o in k["outcomes"]} == {c.kalshi_outcome for c in pair.clubs}
        assert {o["name"] for o in p["outcomes"]} - {"Other"} == {c.polymarket_outcome for c in pair.clubs}


# ── Composition ─────────────────────────────────────────────────────────────


def test_todays_production_rows_blend_for_all_eight_divisions():
    blends, refusals = compose_register(boards())
    assert refusals == []
    assert [b.division for b in blends] == [p.division for p in NFL_DIVISION_REGISTER]
    nfc_east = next(b for b in blends if b.division == "NFC East")
    giants = next(c for c in nfc_east.clubs if c.club == "Giants")
    # Kalshi 0.515, Polymarket 0.51 → the unchanged blend's equal-weight midpoint.
    assert giants.kalshi_probability == 0.515 and giants.polymarket_probability == 0.51
    assert giants.probability == pytest.approx(0.5125)
    assert giants.rule == "equal_weight_midpoint"
    assert nfc_east.leader.club == "Giants"


def test_a_club_is_as_old_as_its_oldest_contributing_price():
    blends, _ = compose_register(boards())
    nfc_east = next(b for b in blends if b.division == "NFC East")
    cowboys = next(c for c in nfc_east.clubs if c.club == "Cowboys")
    # Kalshi 14:00:33Z, Polymarket 07:42:01Z → 07:42:01Z.
    assert cowboys.observed_at == datetime(2026, 11, 2, 7, 42, 1, 622104, tzinfo=timezone.utc)


def test_other_is_never_mapped_to_a_club():
    blends, _ = compose_register(boards())
    assert all(c.club != "Other" for b in blends for c in b.clubs)


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda m: m.remove(row_for(m, "polymarket", "232617")), "polymarket_row_missing"),
        (lambda m: m.remove(row_for(m, "kalshi", "KXNFLNFCEAST-27")), "kalshi_row_missing"),
        (lambda m: row_for(m, "kalshi", "KXNFLNFCEAST-27").update(status="closed"), "kalshi_not_open"),
        (lambda m: row_for(m, "polymarket", "232617").update(status="resolved"), "polymarket_not_open"),
        (lambda m: row_for(m, "polymarket", "232617").update(mutually_exclusive=False), "not_single_winner"),
        (lambda m: row_for(m, "polymarket", "232617").update(mutually_exclusive=None), "single_winner_unknown"),
        (lambda m: row_for(m, "kalshi", "KXNFLNFCEAST-27").update(resolution_date="2027-02-01T00:00:00+00:00"), "settles_after_polymarket_cutoff"),
        (lambda m: row_for(m, "polymarket", "232617").update(resolution_date=None), "settlement_undated"),
        (lambda m: row_for(m, "kalshi", "KXNFLNFCEAST-27")["outcomes"].append({"name": "Dallas Cowboys", "probability": 0.2}), "kalshi_outcomes_differ_from_register"),
        (lambda m: row_for(m, "polymarket", "232617")["outcomes"].append({"name": "Dallas", "probability": 0.2}), "polymarket_outcomes_differ_from_register"),
        (lambda m: row_for(m, "polymarket", "232617")["outcomes"].pop(0), "polymarket_outcomes_differ_from_register"),
        (lambda m: row_for(m, "polymarket", "232617")["outcomes"][-1].update(probability=0.01), "polymarket_field_outcome_priced"),
        (lambda m: row_for(m, "kalshi", "KXNFLNFCEAST-27")["outcomes"][0].update(probability=None), "unpriced:"),
        (lambda m: m.append(dict(row_for(m, "kalshi", "KXNFLNFCEAST-27"), market_id=99)), "kalshi_identity_ambiguous"),
    ],
)
def test_each_failure_refuses_that_division_by_name(mutate, reason):
    markets = markets_copy()
    mutate(markets)
    blends, refusals = compose_register(boards(markets))
    assert [r.division for r in refusals] == ["NFC East"]
    assert refusals[0].reason.startswith(reason)
    assert len(blends) == 7


def test_polymarket_other_under_one_percent_still_blends():
    markets = markets_copy()
    row_for(markets, "polymarket", "232617")["outcomes"][-1].update(probability=0.005)
    blends, refusals = compose_register(boards(markets))
    assert refusals == [] and len(blends) == 8


def test_venues_forty_points_apart_on_one_club_are_a_refusal_not_a_number():
    markets = markets_copy()
    pm = row_for(markets, "polymarket", "232617")
    for o in pm["outcomes"]:
        if o["name"] == "New York Giants":
            o["probability"] = 0.05  # Kalshi 0.515
    _, refusals = compose_register(boards(markets))
    assert refusals == [Refusal("NFC East", "venues_disagree:Giants")]


def test_a_display_name_alias_is_not_a_match():
    """'Dallas Cowboys' on the Kalshi row is NOT Kalshi's registered 'Dallas'."""
    markets = markets_copy()
    k = row_for(markets, "kalshi", "KXNFLNFCEAST-27")
    for o in k["outcomes"]:
        if o["name"] == "Dallas":
            o["name"] = "Dallas Cowboys"
    _, refusals = compose_register(boards(markets))
    assert refusals[0].reason == "kalshi_outcomes_differ_from_register"


def test_compose_division_refuses_a_row_under_another_identity():
    pair = NFL_DIVISION_REGISTER[0]
    b = {x.external_id: x for x in boards()}
    wrong = b["KXNFLNFCEAST-27"]
    assert compose_division(pair, wrong, b[pair.polymarket_event_id]).reason == "kalshi_identity_mismatch"


# ── The producer ────────────────────────────────────────────────────────────


def test_the_roundup_shows_the_four_closest_highest_first_with_the_ruled_footer():
    blends, refusals = compose_register(boards())
    item = assemble_nfl_division_roundup(blends, refusals)
    data = item["data"]
    assert data["kind"] == "roundup" and data["title"] == "NFL division front-runners"
    c = data["roundup"]
    assert c["kicker"] == "Round-up" and c["tag"] == "NFL"
    assert c["footer"] == NFL_DIVISION_ROUNDUP_FOOTER == "Bain Luck blend · the 4 closest of 8 divisions"
    assert [r["label"] for r in c["rows"]] == [
        "NFC East: Giants",
        "AFC West: Broncos",
        "NFC North: Lions",
        "NFC South: Buccaneers",
    ]
    probs = [r["probability"] for r in c["rows"]]
    assert probs == sorted(probs, reverse=True)
    # The four shown are the four LOWEST leaders of the eight.
    leaders = sorted(b.leader.probability for b in blends)
    assert sorted(probs) == leaders[:4]
    assert data["member_ids"] == [r["market_id"] for r in c["rows"]]


def test_the_row_number_is_the_blend_not_either_venue():
    blends, refusals = compose_register(boards())
    row = assemble_nfl_division_roundup(blends, refusals)["data"]["roundup"]["rows"][0]
    assert row["probability"] == pytest.approx(0.5125)  # Kalshi 0.515, Polymarket 0.51
    assert row["pair"] == {"kalshi_market_id": 53674, "polymarket_market_id": 2248395}


def test_one_refusal_and_there_is_no_card():
    markets = markets_copy()
    markets.remove(row_for(markets, "polymarket", "232647"))
    blends, refusals = compose_register(boards(markets))
    assert len(blends) == 7
    assert assemble_nfl_division_roundup(blends, refusals) is None


def test_no_collection_ref_is_passed_through_as_none_never_invented():
    blends, refusals = compose_register(boards())
    assert assemble_nfl_division_roundup(blends, refusals)["data"]["collection_ref"] is None
    ref = {"slug": "nfl-division-front-runners", "name": "NFL division front-runners", "revision": 3, "collection_count": 4}
    assert assemble_nfl_division_roundup(blends, refusals, collection_ref=ref)["data"]["collection_ref"] == ref


def test_reader_text_says_market_never_question_and_names_no_venue():
    blends, refusals = compose_register(boards())
    c = assemble_nfl_division_roundup(blends, refusals)["data"]["roundup"]
    text = " ".join([c["kicker"], c["footer"], *(r["label"] for r in c["rows"])])
    assert "question" not in text.lower()
    for venue in ("Kalshi", "Polymarket", "sportsbook"):
        assert venue.lower() not in text.lower()


# ── The round-up container (#10357 contract) ────────────────────────────────


class _FakeScalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = 0

    async def execute(self, _stmt):
        self.calls += 1
        return _FakeResult(self.rows)


@pytest.mark.asyncio
async def test_container_members_equal_card_rows_from_one_read():
    """#10357 §9.1: same ids, same order, same probabilities, from one fixture."""
    feed_item, payload = await nfl_division_roundup(markets_copy())
    assert feed_item is not None and payload is not None
    assert feed_item["data"]["collection_ref"] == {
        "slug": NFL_DIVISION_ROUNDUP_SLUG,
        "href": NFL_DIVISION_ROUNDUP_HREF,
        "name": NFL_DIVISION_ROUNDUP_TITLE,
    }

    from app.utils.roundup_containers import roundup_container_id

    rows = feed_item["data"]["roundup"]["rows"]
    assert payload["state"] == "published"
    assert payload["slug"] == NFL_DIVISION_ROUNDUP_SLUG
    assert payload["reason"] is None and payload["edition"] is None
    assert payload["subtitle"] == NFL_DIVISION_ROUNDUP_FOOTER
    assert payload["container"] == {
        "id": roundup_container_id(NFL_DIVISION_ROUNDUP_SLUG),
        "slug": NFL_DIVISION_ROUNDUP_SLUG,
        "name": NFL_DIVISION_ROUNDUP_TITLE,
        "kind": "roundup",
        "category": "nfl",
        "status": "open",
        "window_start": None,
        "window_end": None,
        "parent_container_id": None,
    }
    assert len(payload["sections"]) == 1
    sec = payload["sections"][0]
    assert sec["class"] == "title"
    assert sec["title"] == NFL_DIVISION_ROUNDUP_SECTION_TITLE == "The 4 closest races"
    assert sec["layout"] == "field"
    assert sec["count"] == 4
    assert payload["member_count"] == 4
    assert payload["withheld"] == [] and payload["withheld_count"] == 0

    members = sec["members"]
    assert [m["id"] for m in members] == [r["market_id"] for r in rows] == [53674, 53675, 53673, 53672]
    for row, member in zip(rows, members):
        assert member["type"] == "market"
        assert member["event_id"] is None
        assert member["destination"] == {
            "kind": "market",
            "id": row["market_id"],
            "web": f"/futures/{row['market_id']}",
            "api": f"/api/futures/{row['market_id']}",
        }
        card = member["card"]
        assert card["id"] == row["market_id"]
        assert card["source"] == "both"
        assert card["sources"] == ["kalshi", "polymarket"]
        assert card["outcome_count"] == 4
        assert len(card["top_outcomes"]) == 4
        probs = [o["probability"] for o in card["top_outcomes"]]
        assert probs == sorted(probs, reverse=True)
        assert card["top_outcomes"][0]["probability"] == pytest.approx(row["probability"])
        assert card["prices_updated_at"] == row["observed_at"]


@pytest.mark.asyncio
async def test_one_refusal_anywhere_means_card_none_and_route_404_unavailable(monkeypatch):
    """#10357 §9.2: one refusal -> card None and route 404 unavailable; never <4 members."""
    from fastapi import HTTPException

    from app.routes.containers import get_container

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("NFL_DIVISION_ROUNDUP_ENABLED", "true")
    reset_nfl_division_roundup_cache_for_tests()

    markets = markets_copy()
    markets.remove(row_for(markets, "polymarket", "232647"))
    feed_item, payload = await nfl_division_roundup(markets)
    assert feed_item is None and payload is None

    session = _FakeSession(markets)
    with pytest.raises(HTTPException) as exc:
        await get_container(slug=NFL_DIVISION_ROUNDUP_SLUG, db=session)
    assert exc.value.status_code == 404
    assert exc.value.detail == {"state": "unavailable", "slug": NFL_DIVISION_ROUNDUP_SLUG}


@pytest.mark.asyncio
async def test_revision_unchanged_when_prices_move_and_changes_when_order_or_membership_changes():
    """#10357 §9.3: revision is a function of ordered member ids only."""
    _, payload_initial = await nfl_division_roundup(markets_copy())
    assert payload_initial is not None
    rev_initial = payload_initial["revision"]
    assert isinstance(rev_initial, int) and rev_initial > 0

    # Nudge Giants by +0.01 on both venues (still the closest leader at ~52.25%, order unchanged).
    nudged = markets_copy()
    for o in row_for(nudged, "kalshi", "KXNFLNFCEAST-27")["outcomes"]:
        if o["name"] == "New York Giants":
            o["probability"] = 0.525
    for o in row_for(nudged, "polymarket", "232617")["outcomes"]:
        if o["name"] == "New York Giants":
            o["probability"] = 0.52
    _, payload_nudged = await nfl_division_roundup(nudged)
    assert payload_nudged is not None
    assert [m["id"] for m in payload_nudged["sections"][0]["members"]] == [
        m["id"] for m in payload_initial["sections"][0]["members"]
    ]
    assert payload_nudged["revision"] == rev_initial

    # Lower Giants below Broncos so NFC East and AFC West swap order in the shown four.
    reordered = markets_copy()
    for o in row_for(reordered, "kalshi", "KXNFLNFCEAST-27")["outcomes"]:
        if o["name"] == "New York Giants":
            o["probability"] = 0.44
    for o in row_for(reordered, "polymarket", "232617")["outcomes"]:
        if o["name"] == "New York Giants":
            o["probability"] = 0.44
    _, payload_reordered = await nfl_division_roundup(reordered)
    assert payload_reordered is not None
    assert [m["id"] for m in payload_reordered["sections"][0]["members"]] != [
        m["id"] for m in payload_initial["sections"][0]["members"]
    ]
    assert payload_reordered["revision"] != rev_initial
    assert nfl_division_roundup_revision([53674, 53673, 53672, 53675]) != nfl_division_roundup_revision(
        [53673, 53674, 53672, 53675]
    )


@pytest.mark.asyncio
async def test_route_serves_published_roundup_and_shares_60s_read_cache(monkeypatch):
    """#10357 §3, §8: route serves from nfl_division_roundup and shares the 60s cache."""
    from fastapi import HTTPException

    from app.routes.containers import get_container

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "true")
    monkeypatch.setenv("NFL_DIVISION_ROUNDUP_ENABLED", "true")
    reset_nfl_division_roundup_cache_for_tests()

    session = _FakeSession(markets_copy())
    feed_item, _ = await nfl_division_roundup(session)
    assert feed_item is not None
    assert session.calls == 1

    served = await get_container(slug=NFL_DIVISION_ROUNDUP_SLUG, db=session)
    assert served["state"] == "published"
    assert served["slug"] == NFL_DIVISION_ROUNDUP_SLUG
    assert served["member_count"] == 4
    # Second call within 60s shared the cached read.
    assert session.calls == 1

    # Turning off the card's own flag disables both card and container together.
    monkeypatch.setenv("NFL_DIVISION_ROUNDUP_ENABLED", "false")
    assert await nfl_division_roundup(session) == (None, None)
    with pytest.raises(HTTPException) as exc:
        await get_container(slug=NFL_DIVISION_ROUNDUP_SLUG, db=session)
    assert exc.value.status_code == 404
    assert exc.value.detail == {"state": "unavailable", "slug": NFL_DIVISION_ROUNDUP_SLUG}


@pytest.mark.asyncio
async def test_container_reader_text_says_market_never_question_and_names_no_venue():
    """#10357 §9.5: container title, subtitle, section title, and member cards name no venue and never say 'question'."""
    _, payload = await nfl_division_roundup(markets_copy())
    assert payload is not None
    sec = payload["sections"][0]
    strings = [
        payload["container"]["name"],
        payload["subtitle"],
        sec["title"],
        *(m["card"]["name"] for m in sec["members"]),
        *(o["name"] for m in sec["members"] for o in m["card"]["top_outcomes"]),
    ]
    joined = " ".join(strings)
    assert "question" not in joined.lower()
    for venue in ("Kalshi", "Polymarket", "sportsbook"):
        assert venue.lower() not in joined.lower()


# ── Amendment 1: generic RoundupProducer registry and composer ──────────────


@pytest.mark.asyncio
async def test_second_roundup_producer_needs_only_a_registry_entry(monkeypatch):
    """#10357 §9.6 (Amendment 1): a fake second producer registered in a test proves a
    second round-up needs only a registry entry: its route serves, its revision and
    refusal behave, roundup_feed_items(db) includes it only when served, and the NFL
    entry is untouched.
    """
    from fastapi import HTTPException

    from app.routes.containers import get_container
    from app.utils.roundup_containers import (
        ROUNDUP_PRODUCERS,
        RoundupMembers,
        RoundupProducer,
        RoundupRefusal,
        reset_roundup_cache_for_tests,
        roundup_container_id,
        roundup_feed_items,
        roundup_revision,
    )

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    monkeypatch.setenv("NFL_DIVISION_ROUNDUP_ENABLED", "true")
    reset_roundup_cache_for_tests()

    state = {
        "refuse": False,
        "ids": [9001, 9002, 9003],
        "lead_prob": 0.62,
    }

    def fake_produce(_db):
        if state["refuse"]:
            return RoundupRefusal([("MVP", "venue_missing")])
        members = [
            {
                "id": mid,
                "name": f"Award market {mid}",
                "source": "both",
                "sources": ["kalshi", "polymarket"],
                "outcome_count": 3,
                "top_outcomes": [
                    {"name": f"Player {mid}", "probability": state["lead_prob"] - idx * 0.05}
                ],
                "prices_updated_at": "2026-11-02T15:00:00+00:00",
            }
            for idx, mid in enumerate(state["ids"])
        ]
        rows = [
            {
                "market_id": mid,
                "label": f"Award {mid}: Player {mid}",
                "probability": state["lead_prob"] - idx * 0.05,
                "observed_at": "2026-11-02T15:00:00+00:00",
            }
            for idx, mid in enumerate(state["ids"])
        ]
        return RoundupMembers(members=members, rows=rows)

    fake_slug = "roundup-nba-award-front-runners"
    fake_producer = RoundupProducer(
        fake_slug,
        "NBA award front-runners",
        "roundup",
        "nba",
        "The 3 closest award races",
        "Bain Luck blend · the 3 closest of 5 awards",
        fake_produce,
    )
    monkeypatch.setitem(ROUNDUP_PRODUCERS, fake_slug, fake_producer)

    session = _FakeSession(markets_copy())

    # Route serves the fake second producer from its registry entry alone.
    served = await get_container(slug=fake_slug, db=session)
    assert served["state"] == "published"
    assert served["slug"] == fake_slug
    assert served["container"] == {
        "id": roundup_container_id(fake_slug),
        "slug": fake_slug,
        "name": "NBA award front-runners",
        "kind": "roundup",
        "category": "nba",
        "status": "open",
        "window_start": None,
        "window_end": None,
        "parent_container_id": None,
    }
    assert served["subtitle"] == "Bain Luck blend · the 3 closest of 5 awards"
    assert served["sections"][0]["title"] == "The 3 closest award races"
    assert [m["id"] for m in served["sections"][0]["members"]] == [9001, 9002, 9003]
    rev1 = served["revision"]
    assert rev1 == roundup_revision([9001, 9002, 9003])

    # Prices moving do not change revision; order change does.
    state["lead_prob"] = 0.68
    served_nudged = await get_container(slug=fake_slug, db=session)
    assert served_nudged["revision"] == rev1
    state["ids"] = [9002, 9001, 9003]
    served_reordered = await get_container(slug=fake_slug, db=session)
    assert served_reordered["revision"] != rev1

    # roundup_feed_items(db) includes both producers when both serve.
    items = await roundup_feed_items(session)
    slugs = [it["data"]["collection_ref"]["slug"] for it in items]
    assert slugs == [NFL_DIVISION_ROUNDUP_SLUG, fake_slug]

    # When the fake second producer refuses, its route 404s unavailable and it drops
    # from roundup_feed_items, while the NFL entry is completely untouched.
    state["refuse"] = True
    with pytest.raises(HTTPException) as exc:
        await get_container(slug=fake_slug, db=session)
    assert exc.value.status_code == 404
    assert exc.value.detail == {"state": "unavailable", "slug": fake_slug}

    nfl_served = await get_container(slug=NFL_DIVISION_ROUNDUP_SLUG, db=session)
    assert nfl_served["state"] == "published"
    assert nfl_served["slug"] == NFL_DIVISION_ROUNDUP_SLUG
    assert nfl_served["member_count"] == 4

    items_after_refusal = await roundup_feed_items(session)
    assert [it["data"]["collection_ref"]["slug"] for it in items_after_refusal] == [
        NFL_DIVISION_ROUNDUP_SLUG
    ]


def test_compose_roundup_container_is_pure_and_has_no_nfl_names():
    """#10357 §9.7 (Amendment 1): compose_roundup_container is pure; payload fields
    come from the producer, members in the given order, and no NFL names appear in the
    generic code.
    """
    import inspect

    from app.utils.roundup_containers import (
        RoundupMembers,
        RoundupProducer,
        compose_roundup_container,
        compose_roundup_feed_item,
        evaluate_roundup_producer,
        roundup_container_id,
        roundup_feed_items,
        roundup_revision,
        serve_roundup,
    )

    producer = RoundupProducer(
        slug="roundup-tennis-slam-contenders",
        name="Grand Slam front-runners",
        kind="roundup",
        category="tennis",
        section_title="The 2 closest draws",
        footer="Bain Luck blend · the 2 closest of 4 slams",
        produce=lambda _db: None,
    )
    cards = [
        {"id": 702, "name": "Wimbledon Men's Singles", "top_outcomes": [{"name": "Alcaraz", "probability": 0.42}]},
        {"id": 701, "name": "US Open Women's Singles", "top_outcomes": [{"name": "Sabalenka", "probability": 0.36}]},
    ]
    payload = compose_roundup_container(producer, RoundupMembers(members=cards))
    assert payload is not None
    assert payload["slug"] == "roundup-tennis-slam-contenders"
    assert payload["revision"] == roundup_revision([702, 701])
    assert payload["subtitle"] == "Bain Luck blend · the 2 closest of 4 slams"
    assert payload["container"] == {
        "id": roundup_container_id("roundup-tennis-slam-contenders"),
        "slug": "roundup-tennis-slam-contenders",
        "name": "Grand Slam front-runners",
        "kind": "roundup",
        "category": "tennis",
        "status": "open",
        "window_start": None,
        "window_end": None,
        "parent_container_id": None,
    }
    sec = payload["sections"][0]
    assert sec["class"] == "title"
    assert sec["title"] == "The 2 closest draws"
    assert sec["count"] == 2
    assert [m["id"] for m in sec["members"]] == [702, 701]
    assert [m["card"]["name"] for m in sec["members"]] == [
        "Wimbledon Men's Singles",
        "US Open Women's Singles",
    ]

    for fn in (
        compose_roundup_container,
        compose_roundup_feed_item,
        evaluate_roundup_producer,
        serve_roundup,
        roundup_feed_items,
    ):
        src = inspect.getsource(fn).lower()
        assert "nfl" not in src
        assert "division" not in src
        assert "front-runners" not in src


@pytest.mark.asyncio
async def test_orm_kalshi_width_truncated_outcome_names_repair_via_ticker(monkeypatch):
    """ORM FuturesOutcome rows store Kalshi's width-truncated strings ('New York J',
    'Los Angeles C', 'New York G', 'Los Angeles R') with id-anchored outcome tickers
    ('KXNFLAFCEAST-27-NYJ', etc.); produce_nfl_division_roundup repairs them via #6479
    so the ORM path matches the served /api/futures/{id} names.
    """
    from types import SimpleNamespace

    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    monkeypatch.setenv("NFL_DIVISION_ROUNDUP_ENABLED", "true")
    reset_nfl_division_roundup_cache_for_tests()

    truncations = {
        ("KXNFLAFCEAST-27", "New York Jets"): ("KXNFLAFCEAST-27-NYJ", "New York J"),
        ("KXNFLAFCWEST-27", "Los Angeles Chargers"): ("KXNFLAFCWEST-27-LAC", "Los Angeles C"),
        ("KXNFLNFCEAST-27", "New York Giants"): ("KXNFLNFCEAST-27-NYG", "New York G"),
        ("KXNFLNFCWEST-27", "Los Angeles Rams"): ("KXNFLNFCWEST-27-LAR", "Los Angeles R"),
    }

    orm_rows = []
    for m in markets_copy():
        outcomes = []
        for idx, o in enumerate(m["outcomes"]):
            ext_id, shipped_name = truncations.get(
                (m["external_id"], o["name"]),
                (f"{m['external_id']}-{idx}", o["name"]),
            )
            outcomes.append(
                SimpleNamespace(
                    id=m["market_id"] * 100 + idx,
                    external_id=ext_id,
                    name=shipped_name,
                    current_probability=o["probability"],
                    current_american_odds=None,
                    current_yes_bid=None,
                    current_yes_ask=None,
                    probability_change_24h=None,
                    rank=idx + 1,
                    last_updated=datetime.fromisoformat(o["last_updated"]),
                    is_winner=False,
                    resolution_source=None,
                    volume=None,
                )
            )
        orm_rows.append(
            SimpleNamespace(
                id=m["market_id"],
                source=m["source"],
                external_id=m["external_id"],
                name=m["name"],
                status=m["status"],
                mutually_exclusive=m["mutually_exclusive"],
                resolution_date=datetime.fromisoformat(m["resolution_date"]),
                sport=SimpleNamespace(key="americanfootball_nfl", name="NFL"),
                category="sports",
                llm_sport_category="nfl",
                market_tier=4,
                market_type="field",
                updated_at=None,
                outcomes=outcomes,
            )
        )

    feed_item, payload = await nfl_division_roundup(_FakeSession(orm_rows))
    assert feed_item is not None and payload is not None
    assert payload["member_count"] == 4
    assert [m["id"] for m in payload["sections"][0]["members"]] == [53674, 53675, 53673, 53672]

