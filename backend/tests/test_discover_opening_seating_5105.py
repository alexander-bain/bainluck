"""#5105 — opening seating (Alex, Option A, 2026-10-08).

"A live event with no major, marquee or playoff sign does not take a first-ten
seat on being live. It competes from seat 11 down. Scores stay untouched."

``discover_opening_seating.seat_opening`` is pure and opt-in: nothing in
production calls it (the offline replay arm does). These pin the rule's
boundary (seat 10 vs 11), each exemption alone and together, what counts as
RELIABLY live (typed lifecycle with an explicit clock — never a "Live" headline
or golfer movement), the minimal stable move, sparse supply, group laundering,
and that the stage never touches a card.
"""

from __future__ import annotations

import copy
import random
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import discover_opening_seating as seating
from app.utils.discover_opening_seating import (
    APPLIED,
    COMPLIANT,
    CONFLICT,
    LIVE,
    NOT_LIVE,
    OPENING_SEATS,
    UNKNOWN,
    UNRESOLVED_SPARSE_SUPPLY,
    UNSUPPORTED,
    classify_card,
    seat_opening,
)

NOW = datetime(2026, 10, 4, 10, 18, 7, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _futures(i, score=80.0, **data) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": float(score),
        "headline": "Live",  # a headline is never lifecycle evidence
        "reason": f"why {i}",
        "data": {
            "id": i,
            "name": f"Question {i}?",
            "top_outcomes": [{"name": "Yes", "probability": 0.41}],
            "sources": ["kalshi"],
            **data,
        },
    }


def _event(i, *, status="live", start=NOW - timedelta(hours=1), tags=(), score=90.0, **data):
    return {
        "type": "event",
        "score": score,
        "_rank_score": float(score),
        "headline": None,
        "reason": "Game",
        "data": {
            "id": i,
            "status": status,
            "commence_time": _iso(start) if start is not None else None,
            "event_tags": list(tags),
            "hero_probability": 0.55,
            "win_probability_sources": {"kalshi": {"p": 0.55}},
            **data,
        },
    }


def _tournament(key, *, schedule_status="in-progress", start="2026-10-01T00:00:00+00:00",
                end="2026-10-04T00:00:00+00:00", score=98, **data):
    return {
        "type": "tournament",
        "score": score,
        "_blended_market_ids": [1, 2],
        "headline": "Live",
        "reason": "Tournament",
        "data": {
            "key": key,
            "name": key.replace("_", " ").title(),
            "schedule_status": schedule_status,
            "start_date": start,
            "end_date": end,
            "champion": None,
            "is_major": False,
            "is_marquee": False,
            "golfers": [{"name": "A", "probability": 0.2, "movement_24h": 0.03}],
            **data,
        },
    }


def _concept(key, *, status="live", start=_iso(NOW - timedelta(hours=1)), **data):
    return {
        "type": "concept",
        "score": 85,
        "headline": "Live",
        "reason": "Concept",
        "data": {"key": key, "name": key, "status": status, "start_date": start,
                 "is_major": False, "is_marquee": False, **data},
    }


def _ids(items):
    return [seating._identity(item) for item in items]


def _deck(n_eligible: int, restricted_at: dict[int, dict]) -> list[dict]:
    """``n_eligible`` futures in order, with the given restricted cards inserted
    at the given output positions."""
    deck = [_futures(i, score=100 - i) for i in range(n_eligible)]
    for position in sorted(restricted_at):
        deck.insert(position, restricted_at[position])
    return deck


def _live(key="ordinary"):
    return _tournament(key)


# --------------------------------------------------------------------------- #
# The seat-10 / seat-11 boundary
# --------------------------------------------------------------------------- #


def test_a_restricted_card_at_seat_ten_leaves_the_opening():
    deck = _deck(20, {OPENING_SEATS - 1: _live()})
    out = seat_opening(deck, now=NOW)
    assert out.status == APPLIED
    assert _ids(out.items).index("tournament:ordinary") == OPENING_SEATS
    assert out.displaced == ["tournament:ordinary"]
    assert out.entered == ["futures:9"]


def test_a_restricted_card_at_seat_eleven_is_already_compliant():
    deck = _deck(20, {OPENING_SEATS: _live()})
    out = seat_opening(deck, now=NOW)
    assert out.status == COMPLIANT
    assert out.items == deck and out.displaced == [] and out.entered == []


def test_a_restricted_card_at_seat_one_leads_the_tail():
    deck = _deck(20, {0: _live()})
    out = seat_opening(deck, now=NOW)
    ids = _ids(out.items)
    assert ids[:OPENING_SEATS] == [f"futures:{i}" for i in range(OPENING_SEATS)]
    assert ids[OPENING_SEATS] == "tournament:ordinary"
    assert ids[OPENING_SEATS + 1 :] == [f"futures:{i}" for i in range(OPENING_SEATS, 20)]


# --------------------------------------------------------------------------- #
# Exemptions: positive typed signs only
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("flag", ["is_major", "is_marquee"])
def test_a_major_or_marquee_live_tournament_keeps_its_seat(flag):
    card = _tournament("protected", **{flag: True})
    deck = _deck(20, {2: card})
    out = seat_opening(deck, now=NOW)
    assert out.status == COMPLIANT
    assert _ids(out.items)[2] == "tournament:protected"
    assert classify_card(card, now=NOW).exempt_by == [flag]


def test_a_major_live_concept_keeps_its_seat():
    deck = _deck(20, {1: _concept("ufc-300", is_major=True)})
    assert seat_opening(deck, now=NOW).status == COMPLIANT


@pytest.mark.parametrize(
    "tags, exempt",
    [
        (("tier:1", "importance:playoff"), True),
        (("tier:1",), False),
        (("importance:playoff",), False),
        (("tier:2", "importance:playoff"), False),
        ((), False),
    ],
)
def test_tier_one_and_playoff_exempt_only_together(tags, exempt):
    card = _event(501, tags=tags)
    deck = _deck(20, {3: card})
    out = seat_opening(deck, now=NOW)
    assert out.status == (COMPLIANT if exempt else APPLIED)
    assert ("event:501" in _ids(out.items)[:OPENING_SEATS]) is exempt


@pytest.mark.parametrize(
    "data",
    [
        {},  # no exemption fields at all
        {"is_major": False, "is_marquee": False},
        {"is_major": None, "is_marquee": None},
        {"is_major": "true", "is_marquee": 1},  # truthy is not a typed True
    ],
)
def test_a_missing_or_non_positive_exemption_is_no_exemption(data):
    card = _event(502, **data)
    assert classify_card(card, now=NOW).restricted


def test_a_missing_exemption_on_a_tournament_is_no_exemption():
    card = _tournament("bare")
    del card["data"]["is_major"], card["data"]["is_marquee"]
    assert classify_card(card, now=NOW).restricted


# --------------------------------------------------------------------------- #
# Reliably live — typed lifecycle with an explicit clock
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "card, lifecycle",
    [
        (_event(1, status="live"), LIVE),
        (_event(2, status="live", start=None), LIVE),
        (_event(3, status="scheduled", start=NOW + timedelta(hours=2)), NOT_LIVE),
        (_event(4, status="completed", start=NOW - timedelta(hours=4)), NOT_LIVE),
        (_event(5, status=None), UNKNOWN),
        # A "live" row whose own kickoff is still ahead is not reliable.
        (_event(6, status="live", start=NOW + timedelta(hours=3)), CONFLICT),
        (_concept("c-live"), LIVE),
        (_concept("c-up", status="upcoming"), NOT_LIVE),
        (_concept("c-none", status=None), UNKNOWN),
        # F1-shaped: "live" from a lights-out lead window, race start still ahead.
        (_concept("c-f1", start=_iso(NOW + timedelta(hours=3))), CONFLICT),
    ],
)
def test_event_and_concept_lifecycle(card, lifecycle):
    got = classify_card(card, now=NOW)
    assert got.lifecycle == lifecycle
    assert got.restricted is (lifecycle == LIVE)


@pytest.mark.parametrize(
    "overrides, lifecycle",
    [
        ({}, LIVE),  # asserted in-progress, dated live
        ({"schedule_status": "in_progress"}, LIVE),
        ({"schedule_status": None}, LIVE),  # LOTTE shape: dates alone, no assertion
        ({"schedule_status": None, "start": None, "end": None}, UNKNOWN),
        ({"schedule_status": "in-progress", "start": None, "end": None}, LIVE),
        ({"champion": "Rory McIlroy"}, NOT_LIVE),
        ({"schedule_status": "completed"}, CONFLICT),
        ({"schedule_status": "completed", "start": None, "end": None}, NOT_LIVE),
        ({"schedule_status": None, "start": "2026-10-08T00:00:00+00:00",
          "end": "2026-10-11T00:00:00+00:00"}, NOT_LIVE),
        ({"schedule_status": "in-progress", "start": "2027-09-17T00:00:00+00:00",
          "end": "2027-09-19T00:00:00+00:00"}, CONFLICT),
        ({"schedule_status": None, "start": "2026-09-24T00:00:00+00:00",
          "end": "2026-09-27T00:00:00+00:00"}, NOT_LIVE),
        # The served 12h tail past the end date's midnight, and one second past it.
        ({"schedule_status": None, "start": "2026-10-01T00:00:00+00:00",
          "end": "2026-10-03T22:18:07+00:00"}, LIVE),
        ({"schedule_status": None, "start": "2026-10-01T00:00:00+00:00",
          "end": "2026-10-03T22:18:06+00:00"}, NOT_LIVE),
        ({"schedule_status": None, "start": "not a date", "end": None}, UNKNOWN),
        ({"schedule_status": None, "start": "2026-10-01", "end": "2026-10-04"}, LIVE),
    ],
)
def test_tournament_lifecycle(overrides, lifecycle):
    overrides = dict(overrides)
    kwargs = {k: overrides.pop(k) for k in ("schedule_status", "start", "end") if k in overrides}
    card = _tournament("t", **kwargs, **overrides)
    assert classify_card(card, now=NOW).lifecycle == lifecycle


def test_golfer_movement_and_a_live_headline_never_make_a_tournament_live():
    """The Korn Ferry card on the October 4 capture: no dates, no schedule
    status, a "Live" headline, and golfers moving. The served
    ``_tournament_is_live`` says yes on movement alone; this does not."""
    from app.routes.feed import _tournament_is_live

    card = _tournament("compliance_solutions_championship", schedule_status=None,
                       start=None, end=None)
    card["data"]["golfers"] = [{"name": "A", "movement_24h": 0.08}]
    assert card["headline"] == "Live"
    assert _tournament_is_live(card["data"], NOW) is True  # the trap is real
    got = classify_card(card, now=NOW)
    assert got.lifecycle == UNKNOWN and not got.restricted
    deck = _deck(20, {0: card})
    assert seat_opening(deck, now=NOW).status == COMPLIANT


def test_the_clock_is_the_callers_and_decides_the_answer():
    card = _tournament("t", schedule_status=None)
    before = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    after = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
    assert classify_card(card, now=before).lifecycle == NOT_LIVE
    assert classify_card(card, now=NOW).lifecycle == LIVE
    assert classify_card(card, now=after).lifecycle == NOT_LIVE


@pytest.mark.parametrize("now", [None, datetime(2026, 10, 4, 10, 18)])
def test_an_absent_or_naive_clock_refuses(now):
    with pytest.raises(ValueError):
        seat_opening(_deck(12, {}), now=now)


def test_a_futures_card_is_never_restricted_for_missing_tournament_flags():
    card = _futures(9, status="live", schedule_status="in-progress",
                    start_date="2026-10-01", end_date="2026-10-04")
    got = classify_card(card, now=NOW)
    assert got.lifecycle is None and not got.restricted
    deck = [card] + [_futures(100 + i) for i in range(5)]
    assert seat_opening(deck, now=NOW).status == COMPLIANT


@pytest.mark.parametrize(
    "card",
    [
        _event(7, status="scheduled", start=NOW + timedelta(hours=1)),
        _event(8, status="completed", start=NOW - timedelta(hours=5)),
        _tournament("future", schedule_status=None, start="2026-10-08T00:00:00+00:00",
                    end="2026-10-11T00:00:00+00:00"),
        _tournament("finished", champion="Someone"),
    ],
)
def test_future_and_finished_cards_keep_their_seats(card):
    deck = _deck(20, {0: card})
    out = seat_opening(deck, now=NOW)
    assert out.status == COMPLIANT and out.items == deck


# --------------------------------------------------------------------------- #
# Supply: exactly ten vs thin
# --------------------------------------------------------------------------- #


def test_exactly_ten_eligible_fill_the_opening_in_order():
    deck = _deck(10, {0: _live("a"), 4: _live("b"), 11: _live("c")})
    out = seat_opening(deck, now=NOW)
    assert out.status == APPLIED
    ids = _ids(out.items)
    assert ids[:OPENING_SEATS] == [f"futures:{i}" for i in range(10)]
    assert ids[OPENING_SEATS:] == ["tournament:a", "tournament:b", "tournament:c"]
    assert out.displaced == ["tournament:a", "tournament:b"]


def test_nine_eligible_is_unresolved_and_changes_nothing():
    deck = _deck(9, {0: _live("a"), 5: _live("b")})
    snapshot = copy.deepcopy(deck)
    out = seat_opening(deck, now=NOW)
    assert out.status == UNRESOLVED_SPARSE_SUPPLY
    assert "9 eligible" in out.detail
    assert out.items == snapshot and all(a is b for a, b in zip(out.items, deck))
    assert out.items is not deck
    assert out.displaced == [] and out.entered == []
    assert len(out.items) == len(deck)  # nothing dropped, no blank inserted


def test_a_compliant_short_deck_is_not_rejected():
    deck = _deck(5, {})
    out = seat_opening(deck, now=NOW)
    assert out.status == COMPLIANT and out.items == deck


def test_a_short_deck_holding_a_restricted_card_is_unresolved():
    deck = _deck(5, {4: _live()})
    assert seat_opening(deck, now=NOW).status == UNRESOLVED_SPARSE_SUPPLY


# --------------------------------------------------------------------------- #
# Order: the minimal stable move, pages are slices of ONE deck
# --------------------------------------------------------------------------- #


def _restricted_ids(out):
    return {c.identity for c in out.cards if c.restricted}


def test_the_move_keeps_both_subsequences_and_takes_the_earliest_tail_cards():
    deck = _deck(40, {1: _live("a"), 3: _live("b"), 7: _live("c"), 25: _live("d")})
    out = seat_opening(deck, now=NOW)
    before, after = _ids(deck), _ids(out.items)
    restricted = _restricted_ids(out)
    assert [i for i in after if i not in restricted] == [i for i in before if i not in restricted]
    assert [i for i in after if i in restricted] == [i for i in before if i in restricted]
    assert after[OPENING_SEATS : OPENING_SEATS + 3] == ["tournament:a", "tournament:b", "tournament:c"]
    # The entrants are exactly the first eligible cards past the old opening.
    assert out.entered == ["futures:7", "futures:8", "futures:9"]
    assert sorted(after) == sorted(before) and len(set(after)) == len(after)
    # Everything past the entrants is untouched relative order — and the
    # restricted card already in the tail did not move at all.
    assert after.index("tournament:d") == before.index("tournament:d")


@pytest.mark.parametrize("page_size", [20, 50])
def test_pages_at_any_size_and_offset_are_slices_of_one_seated_deck(page_size):
    deck = _deck(80, {0: _live("a"), 9: _live("b"), 15: _live("c")})
    seated = seat_opening(deck, now=NOW).items
    pages = [seated[o : o + page_size] for o in range(0, len(seated), page_size)]
    flat = [card for page in pages for card in page]
    assert _ids(flat) == _ids(seated)
    assert len(set(_ids(flat))) == len(flat) == len(deck)
    # Seating the seated deck again is a no-op: no page-local reshuffle exists.
    assert seat_opening(seated, now=NOW).status == COMPLIANT
    # The first page of either size shares one opening.
    assert _ids(pages[0][:OPENING_SEATS]) == _ids(seated[:OPENING_SEATS])


def test_randomised_decks_keep_every_invariant():
    rng = random.Random(5105)
    for trial in range(400):
        n = rng.randint(0, 40)
        deck = []
        for i in range(n):
            roll = rng.random()
            if roll < 0.15:
                deck.append(_tournament(f"t{trial}_{i}"))
            elif roll < 0.2:
                deck.append(_tournament(f"m{trial}_{i}", is_major=True))
            elif roll < 0.3:
                deck.append(_event(10_000 * trial + i, status=rng.choice(["live", "scheduled", "completed"])))
            else:
                deck.append(_futures(10_000 * trial + i))
        snapshot = copy.deepcopy(deck)
        out = seat_opening(deck, now=NOW)
        assert deck == snapshot, "the caller's list and cards are never mutated"
        assert sorted(map(id, out.items)) == sorted(map(id, deck))
        restricted = [c.restricted for c in out.cards]
        if out.status == APPLIED:
            by_id = {id(card): r for card, r in zip(deck, restricted)}
            assert not any(by_id[id(card)] for card in out.items[:OPENING_SEATS])
            order = [deck.index(card) for card in out.items]
            elig = [i for i in order if not restricted[i]]
            restr = [i for i in order if restricted[i]]
            assert elig == sorted(elig) and restr == sorted(restr)
        else:
            assert out.items == deck
            if out.status == COMPLIANT:
                assert not any(restricted[:OPENING_SEATS])
            else:
                assert out.status == UNRESOLVED_SPARSE_SUPPLY
                assert sum(not r for r in restricted) < OPENING_SEATS


# --------------------------------------------------------------------------- #
# The stage never touches a card
# --------------------------------------------------------------------------- #


def test_every_card_is_the_same_object_with_the_same_payload():
    deck = _deck(20, {0: _live("a"), 2: _event(77, tags=("tier:1",))})
    snapshot = copy.deepcopy(deck)
    out = seat_opening(deck, now=NOW)
    assert out.status == APPLIED
    assert deck == snapshot
    by_ident = dict(zip(_ids(snapshot), snapshot))
    for card in out.items:
        assert card == by_ident[seating._identity(card)]
        assert any(card is original for original in deck)
    for card in out.items:
        original = by_ident[seating._identity(card)]
        for key in ("score", "_rank_score", "_blended_market_ids", "headline", "reason"):
            assert card.get(key) == original.get(key)


# --------------------------------------------------------------------------- #
# Groups never launder; unknown shapes refuse
# --------------------------------------------------------------------------- #


def _bundle(ident, children):
    return {
        "type": "bundle",
        "score": 93.0,
        "reason": "Group",
        "headline": "G",
        "data": {"id": ident, "items": children, "member_ids": [1, 2]},
    }


def _collection(ident, *, status="scheduled", matched=()):
    return {
        "type": "collection",
        "score": 35,
        "reason": "NFL Week",
        "headline": None,
        "data": {"id": ident, "status": status, "matched_event_ids": list(matched)},
    }


def test_a_bundle_of_ordinary_live_events_is_refused_not_seated():
    group = _bundle("golf-weekend", [_tournament("a"), _tournament("b"), _tournament("c")])
    deck = _deck(20, {0: group})
    out = seat_opening(deck, now=NOW)
    assert out.status == UNSUPPORTED
    assert "golf-weekend" in out.detail and "tournament:a" in out.detail
    assert out.items == deck


def test_a_refused_group_anywhere_in_the_deck_refuses():
    group = _bundle("deep", [_futures(1), _event(88)])
    deck = _deck(30, {25: group})
    assert seat_opening(deck, now=NOW).status == UNSUPPORTED


@pytest.mark.parametrize(
    "children",
    [
        [_futures(1), _futures(2)],
        [_tournament("major", is_major=True), _futures(3)],
        [_event(90, status="scheduled", start=NOW + timedelta(hours=2))],
    ],
)
def test_a_group_with_nothing_to_launder_is_an_ordinary_card(children):
    deck = _deck(20, {0: _bundle("fine", children)})
    assert seat_opening(deck, now=NOW).status == COMPLIANT


@pytest.mark.parametrize("child", [{"type": "mystery", "data": {"id": 1}}, "text",
                                   {"type": "bundle", "data": {"id": "nested", "items": []}}])
def test_a_bundle_member_of_unknown_kind_refuses(child):
    deck = _deck(20, {0: _bundle("odd", [child])})
    assert seat_opening(deck, now=NOW).status == UNSUPPORTED


def test_a_collection_reading_live_refuses():
    deck = _deck(20, {0: _collection(7, status="live")})
    assert seat_opening(deck, now=NOW).status == UNSUPPORTED


def test_a_collection_naming_a_restricted_event_refuses():
    deck = _deck(20, {0: _collection(7, matched=[601]), 12: _event(601)})
    out = seat_opening(deck, now=NOW)
    assert out.status == UNSUPPORTED and "event:601" in out.detail


def test_a_collection_of_scheduled_games_is_an_ordinary_card():
    game = _event(602, status="scheduled", start=NOW + timedelta(hours=3))
    deck = _deck(20, {0: _collection(7, matched=[602, 999]), 1: game})
    assert seat_opening(deck, now=NOW).status == COMPLIANT


@pytest.mark.parametrize(
    "card",
    [
        {"type": "mystery", "data": {"id": 1}},
        {"type": "event", "data": None},
        "not a card",
    ],
)
def test_an_unknown_card_shape_refuses(card):
    deck = _deck(12, {0: card})
    out = seat_opening(deck, now=NOW)
    assert out.status == UNSUPPORTED and out.items == deck


def test_a_duplicated_identity_refuses():
    deck = _deck(12, {})
    deck.append(copy.deepcopy(deck[0]))
    assert seat_opening(deck, now=NOW).status == UNSUPPORTED


def test_the_summary_names_every_conclusion():
    deck = _deck(20, {
        0: _live("a"),
        1: _tournament("major", is_major=True),
        2: _concept("f1", start=_iso(NOW + timedelta(hours=3))),
        3: _tournament("undated", schedule_status=None, start=None, end=None),
    })
    summary = seat_opening(deck, now=NOW).summary()
    assert summary["status"] == APPLIED
    assert [c["identity"] for c in summary["restricted"]] == ["tournament:a"]
    assert [c["identity"] for c in summary["exempt_live"]] == ["tournament:major"]
    assert [c["identity"] for c in summary["conflicts"]] == ["concept:f1"]
    assert [c["identity"] for c in summary["unknown_lifecycle"]] == ["tournament:undated"]
