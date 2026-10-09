"""#5105 — a pinned opening that stops being compliant expires and recomposes
(Alex, 2026-10-08: "expire and recompose").

``discover_opening_edition.compose_opening_edition`` composes the real
``apply_pinned_edition`` and ``seat_opening`` at the final-full-deck seam.
Every pin below is MINTED through the same function (an unpinned compose at
``T0``) and then requested again at ``T1`` against a changed current deck, so
the manifest, token and layout under test are the ones the code itself writes.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import discover_opening_edition as ed
from app.utils.discover_opening_edition import (
    COMPOSED,
    HELD,
    SEATING_EXPIRY_OPENING_ORDER,
    SEATING_EXPIRY_SECTION_BOUNDARY,
    UNSUPPORTED,
    compose_opening_edition,
)
from app.utils.discover_opening_seating import OPENING_SEATS
from app.utils.feed_cache import feed_edition_member, feed_edition_token
from app.utils.feed_editions import (
    EDITION_LAYOUT_FIELD,
    EDITION_LEASE_SECONDS,
    EDITION_STATUS_EXPIRED,
    EDITION_STATUS_INVALIDATED,
    EDITION_STATUS_PINNED,
    EDITION_STATUS_SUPERSEDED,
    EDITION_STATUS_UNPINNED,
    LAYOUT_LEGACY,
    LAYOUT_MALFORMED,
    LAYOUT_SECTIONS,
    apply_pinned_edition,
    build_edition_manifest,
    edition_policy_fingerprint,
    manifest_section_layout,
)

T0 = datetime(2026, 10, 8, 23, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=10)
KICKOFF = T0 + timedelta(minutes=5)  # between the mint and the re-request

POLICY = edition_policy_fingerprint(limit=20, opening_seating=True)
LEGACY_POLICY = edition_policy_fingerprint(limit=20)


# --- cards --------------------------------------------------------------------


def _futures(i, *, p=0.41, score=80.0) -> dict:
    return {
        "type": "futures",
        "score": score,
        "_rank_score": float(score),
        "headline": "Live",  # never lifecycle evidence
        "data": {
            "id": i,
            "name": f"Question {i}?",
            "top_outcomes": [{"name": "Yes", "probability": p}],
        },
    }


def _event(
    i, *, status="scheduled", start=KICKOFF, tags=(), p=0.55, score=90.0, **data
):
    return {
        "type": "event",
        "score": score,
        "_rank_score": float(score),
        "data": {
            "id": i,
            "status": status,
            "commence_time": start.isoformat() if start is not None else None,
            "event_tags": list(tags),
            "hero_probability": p,
            "win_probability_sources": {"kalshi": {"p": p}},
            **data,
        },
    }


def _live(card: dict, **data) -> dict:
    """The same game, re-served after kickoff: a NEW body, typed live."""
    fresh = copy.deepcopy(card)
    fresh["data"]["status"] = "live"
    fresh["data"].update(data)
    return fresh


def _refresh(deck: list) -> list:
    """The same deck re-built: new body objects, identical identities."""
    return [copy.deepcopy(card) for card in deck]


def _ids(items) -> list[str]:
    return [feed_edition_member(card) for card in items]


def _mint(deck: list, *, now=T0):
    out = compose_opening_edition(
        deck, None, requested_token=None, requested_policy=POLICY, now=now
    )
    assert out.status == COMPOSED and out.edition_status == EDITION_STATUS_UNPINNED
    assert out.manifest is not None and out.token == out.manifest["token"]
    return out


def _request(deck, minted, *, now=T1, manifest=None, token=None, policy=POLICY):
    return compose_opening_edition(
        deck,
        minted.manifest if manifest is None else manifest,
        requested_token=minted.token if token is None else token,
        requested_policy=policy,
        now=now,
    )


def _opening_deck(n_futures=15, game_seat=2, **game):
    """``n_futures`` futures with a scheduled game at ``game_seat``."""
    deck = [_futures(i) for i in range(n_futures)]
    deck.insert(game_seat, _event(900, **game))
    return deck


# --- A. the ruling: future → ordinary live in the opening ---------------------


def test_a_future_opening_game_that_goes_ordinary_live_expires_the_pin_whole():
    minted = _mint(_opening_deck())
    assert _ids(minted.items)[2] == "event:900"

    current = _refresh(minted.items)
    current[2] = _live(current[2])
    out = _request(current, minted)

    assert out.status == COMPOSED and out.usable
    assert out.edition_status == EDITION_STATUS_EXPIRED
    assert out.seating_expiry == SEATING_EXPIRY_OPENING_ORDER
    assert out.retire_requested and out.restart_at_page_one
    assert out.requested_token == minted.token
    assert out.token != minted.token
    # Composed from the full current deck: the game competes from seat 11.
    assert _ids(out.items).index("event:900") == OPENING_SEATS
    assert "event:900" not in _ids(out.items)[:OPENING_SEATS]
    assert out.items[_ids(out.items).index("event:900")] is current[2]
    assert out.token == feed_edition_token(out.items, out.continuation_start)


def test_the_same_pin_holds_before_kickoff():
    minted = _mint(_opening_deck())
    current = _refresh(minted.items)
    out = _request(current, minted, now=KICKOFF - timedelta(seconds=1))
    assert out.status == HELD and out.edition_status == EDITION_STATUS_PINNED
    assert out.token == minted.token and not out.retire_requested


@pytest.mark.parametrize(
    "sign",
    [
        {"is_major": True},
        {"is_marquee": True},
        {"event_tags": ["tier:1", "importance:playoff"]},
    ],
    ids=["major", "marquee", "tier1+playoff"],
)
def test_a_positively_exempt_live_game_keeps_its_pinned_seat(sign):
    minted = _mint(_opening_deck())
    current = _refresh(minted.items)
    current[2] = _live(current[2], **sign)
    out = _request(current, minted)
    assert out.status == HELD and out.edition_status == EDITION_STATUS_PINNED
    assert _ids(out.items) == minted.manifest["members"]
    assert out.items[2] is current[2]


@pytest.mark.parametrize("tags", [["tier:1"], ["importance:playoff"]])
def test_half_an_exemption_is_no_exemption(tags):
    minted = _mint(_opening_deck())
    current = _refresh(minted.items)
    current[2] = _live(current[2], event_tags=tags)
    out = _request(current, minted)
    assert out.edition_status == EDITION_STATUS_EXPIRED
    assert out.seating_expiry == SEATING_EXPIRY_OPENING_ORDER


@pytest.mark.parametrize("status", [None, ""])
def test_unknown_lifecycle_is_not_assumed_live(status):
    minted = _mint(_opening_deck())
    current = _refresh(minted.items)
    current[2]["data"]["status"] = status
    out = _request(current, minted)
    assert out.status == HELD


def test_an_ordinary_live_game_already_outside_the_opening_holds_the_pin():
    minted = _mint(_opening_deck(game_seat=12))
    assert _ids(minted.items)[12] == "event:900"
    current = _refresh(minted.items)
    current[12] = _live(current[12])
    out = _request(current, minted)
    assert out.status == HELD and out.token == minted.token
    assert _ids(out.items)[12] == "event:900"


# --- B. what does NOT expire a pin ------------------------------------------


def test_a_price_only_refresh_holds_the_same_order_with_current_bodies():
    minted = _mint(_opening_deck())
    current = _refresh(minted.items)
    for card in current:
        if card["type"] == "futures":
            card["data"]["top_outcomes"][0]["probability"] = 0.77
        else:
            card["data"]["hero_probability"] = 0.12
    out = _request(current, minted)
    assert out.status == HELD
    assert _ids(out.items) == minted.manifest["members"]
    assert all(a is b for a, b in zip(out.items, current))
    assert out.continuation_start is None and out.manifest is None


def test_a_moved_current_ranking_does_not_expire_a_compliant_pin():
    minted = _mint(_opening_deck())
    current = list(reversed(_refresh(minted.items)))
    out = _request(current, minted)
    assert out.status == HELD
    assert _ids(out.items) == minted.manifest["members"]


def test_a_new_card_is_excluded_from_a_valid_pin_and_included_after_expiry():
    minted = _mint(_opening_deck())
    newcomer = _futures(500, score=99.0)

    current = [newcomer] + _refresh(minted.items)
    held = _request(current, minted)
    assert held.status == HELD
    assert "futures:500" not in _ids(held.items)
    assert len(held.items) == minted.manifest["total"]

    current = [newcomer] + _refresh(minted.items)
    current[3] = _live(current[3])  # event:900, seat 3 of the current deck
    expired = _request(current, minted)
    assert (
        expired.status == COMPOSED and expired.edition_status == EDITION_STATUS_EXPIRED
    )
    assert _ids(expired.items)[0] == "futures:500"
    assert set(_ids(expired.items)) == set(_ids(current))


# --- C. the section boundary is edition identity -----------------------------


def _thin_deck(n_eligible: int, n_live: int) -> list:
    """Scheduled games (eligible) behind already-live ordinary games."""
    eligible = [_event(i) for i in range(n_eligible)]
    live = [
        _event(700 + i, status="live", start=T0 - timedelta(hours=1))
        for i in range(n_live)
    ]
    return live + eligible  # live first: seating must move them


def test_an_unchanged_thin_pin_holds_although_seating_reports_sparse():
    minted = _mint(_thin_deck(3, 4))
    assert minted.continuation_start == 3
    assert minted.manifest[EDITION_LAYOUT_FIELD]["continuation_start"] == 3
    out = _request(_refresh(minted.items), minted)
    # seat_opening says "sparse_continuation" (changed=True) on an already
    # partitioned deck — the hold must not read that as a change.
    assert out.pin_seating.changed
    assert out.status == HELD and out.continuation_start == 3
    assert out.token == minted.token


def test_a_moved_boundary_with_the_same_identity_order_expires_the_pin():
    minted = _mint(_thin_deck(3, 4))
    assert _ids(minted.items)[:3] == ["event:0", "event:1", "event:2"]
    current = _refresh(minted.items)
    current[2] = _live(current[2])  # the last eligible game kicks off
    out = _request(current, minted)
    # Seating leaves the identity order alone; only the boundary moved.
    assert _ids(out.pin_seating.items) == minted.manifest["members"]
    assert out.edition_status == EDITION_STATUS_EXPIRED
    assert out.seating_expiry == SEATING_EXPIRY_SECTION_BOUNDARY
    assert out.continuation_start == 2 and out.restart_at_page_one
    assert out.token == feed_edition_token(out.items, 2) != minted.token


def test_a_boundary_moving_to_zero_is_a_new_edition():
    minted = _mint(_thin_deck(1, 3))
    assert minted.continuation_start == 1
    current = _refresh(minted.items)
    current[0] = _live(current[0])  # the only eligible game kicks off
    out = _request(current, minted)
    assert _ids(out.pin_seating.items) == minted.manifest["members"]
    assert out.seating_expiry == SEATING_EXPIRY_SECTION_BOUNDARY
    assert out.continuation_start == 0
    assert (
        out.token == feed_edition_token(out.items, 0) != feed_edition_token(out.items)
    )


def test_missing_and_zero_are_different_boundaries():
    # A short all-eligible deck mints section-aware with NO boundary …
    minted = _mint([_event(1, status="scheduled")])
    assert minted.continuation_start is None
    assert minted.manifest[EDITION_LAYOUT_FIELD] == {
        "version": 1,
        "continuation_start": None,
    }
    # … and its only card going ordinary-live is the same order, boundary 0.
    current = [_live(minted.items[0])]
    out = _request(current, minted)
    assert _ids(out.pin_seating.items) == _ids(current)
    assert out.seating_expiry == SEATING_EXPIRY_SECTION_BOUNDARY
    assert out.continuation_start == 0 and out.token != minted.token


def test_enough_supply_turning_thin_expires_and_recomposes_from_the_current_deck():
    deck = [_event(800 + i, status="scheduled") for i in range(4)] + [
        _futures(i) for i in range(8)
    ]
    minted = _mint(deck)
    assert minted.continuation_start is None
    current = _refresh(minted.items)
    for i in range(4):
        current[i] = _live(current[i])
    out = _request(current, minted)
    assert out.seating_expiry == SEATING_EXPIRY_OPENING_ORDER
    assert out.continuation_start == 8  # 8 eligible: thin
    assert _ids(out.items)[8:] == [f"event:{800 + i}" for i in range(4)]

    # The same transition with fresh eligible entrants recomposes WITH them.
    entrants = [_futures(600 + i, score=50.0) for i in range(3)]
    out = _request(current + entrants, minted)
    assert out.edition_status == EDITION_STATUS_EXPIRED
    assert out.continuation_start is None
    assert _ids(out.items)[8:10] == ["futures:600", "futures:601"]
    assert "event:800" not in _ids(out.items)[:OPENING_SEATS]


# --- D. preserved edition semantics (no new eligibility condition) -----------


def test_a_legacy_manifest_cannot_masquerade_as_a_section_aware_pin():
    deck = _opening_deck()
    legacy = build_edition_manifest(
        deck, token=feed_edition_token(deck), policy=POLICY, built_at=T0.timestamp()
    )
    assert EDITION_LAYOUT_FIELD not in legacy
    out = compose_opening_edition(
        deck, legacy, requested_token=legacy["token"], requested_policy=POLICY, now=T1
    )
    assert out.status == COMPOSED and out.edition_status == EDITION_STATUS_SUPERSEDED
    assert out.seating_expiry is None and out.restart_at_page_one


def test_a_legacy_policy_manifest_is_superseded_under_the_section_aware_policy():
    deck = _opening_deck()
    legacy = build_edition_manifest(
        deck,
        token=feed_edition_token(deck),
        policy=LEGACY_POLICY,
        built_at=T0.timestamp(),
    )
    out = compose_opening_edition(
        deck, legacy, requested_token=legacy["token"], requested_policy=POLICY, now=T1
    )
    assert out.edition_status == EDITION_STATUS_SUPERSEDED


def test_the_legacy_reader_refuses_a_section_aware_manifest():
    minted = _mint(_thin_deck(3, 4))
    items, status = apply_pinned_edition(
        _refresh(minted.items),
        minted.manifest,
        requested_policy=POLICY,
        now=T1.timestamp(),
    )
    assert (items, status) == (None, EDITION_STATUS_SUPERSEDED)


def test_policy_mismatch_is_superseded_with_a_usable_replacement():
    minted = _mint(_opening_deck())
    other = edition_policy_fingerprint(limit=20, principal="u:7", opening_seating=True)
    out = _request(_refresh(minted.items), minted, policy=other)
    assert out.edition_status == EDITION_STATUS_SUPERSEDED and out.usable
    assert out.manifest["policy"] == other


def test_a_missing_member_is_invalidated_not_a_seating_expiry():
    minted = _mint(_opening_deck())
    current = _refresh(minted.items)
    current[2] = _live(current[2])
    del current[5]
    out = _request(current, minted)
    assert out.edition_status == EDITION_STATUS_INVALIDATED
    assert out.seating_expiry is None and out.pin_seating is None
    assert out.status == COMPOSED and out.restart_at_page_one


def test_an_out_of_lease_pin_is_lease_expired_before_seating_is_read():
    minted = _mint(_opening_deck())
    current = _refresh(minted.items)
    current[2] = _live(current[2])
    late = T0 + timedelta(seconds=EDITION_LEASE_SECONDS + 1)
    out = _request(current, minted, now=late)
    assert out.edition_status == EDITION_STATUS_EXPIRED
    assert out.seating_expiry is None and out.pin_seating is None


def test_a_missing_manifest_is_expired_with_a_usable_replacement():
    minted = _mint(_opening_deck())
    out = compose_opening_edition(
        _refresh(minted.items),
        None,
        requested_token=minted.token,
        requested_policy=POLICY,
        now=T1,
    )
    assert out.edition_status == EDITION_STATUS_EXPIRED and out.usable
    assert out.retire_requested


@pytest.mark.parametrize(
    "layout",
    [
        {"version": 2, "continuation_start": None},
        {"version": True, "continuation_start": None},
        {"version": 1},
        {"version": 1, "continuation_start": True},
        {"version": 1, "continuation_start": -1},
        {"version": 1, "continuation_start": 99},
        {"version": 1, "continuation_start": None, "extra": 1},
        None,
    ],
)
def test_a_malformed_layout_is_expired(layout):
    minted = _mint(_opening_deck())
    manifest = {**minted.manifest, EDITION_LAYOUT_FIELD: layout}
    assert manifest_section_layout(manifest)[0] == LAYOUT_MALFORMED
    out = _request(_refresh(minted.items), minted, manifest=manifest)
    assert out.edition_status == EDITION_STATUS_EXPIRED and out.pin_seating is None


def test_a_manifest_that_does_not_re_derive_its_token_is_not_held():
    minted = _mint(_thin_deck(3, 4))
    # Same members, boundary rewritten: the recorded token no longer re-derives.
    manifest = copy.deepcopy(minted.manifest)
    manifest[EDITION_LAYOUT_FIELD]["continuation_start"] = 2
    out = _request(_refresh(minted.items), minted, manifest=manifest)
    assert out.edition_status == EDITION_STATUS_EXPIRED and out.pin_seating is None
    # And a request for another token never holds this manifest.
    out = _request(_refresh(minted.items), minted, token="0" * 16)
    assert out.edition_status == EDITION_STATUS_EXPIRED


# --- E. refusals: no pretend replacement, no mutation ------------------------


def _conflicted(card):
    bad = copy.deepcopy(card)
    bad["data"]["status"] = "live"
    bad["data"]["commence_time"] = (T1 + timedelta(hours=3)).isoformat()
    return bad


def test_a_conflict_in_the_pinned_opening_refuses_without_mutating_input():
    minted = _mint(_opening_deck())
    current = _refresh(minted.items)
    current[2] = _conflicted(current[2])
    before = copy.deepcopy(current)
    order = list(current)
    out = _request(current, minted)
    assert out.status == UNSUPPORTED and not out.usable
    assert out.edition_status is None  # neither held nor shown expired
    assert out.retire_requested and not out.restart_at_page_one
    assert out.token is None and out.manifest is None and out.deck_seating is None
    assert out.pin_seating.refused_conflicts == ["event:900"]
    assert current == before and current == order
    assert all(a is b for a, b in zip(out.items, order)) and out.items is not current


def test_a_refused_replacement_keeps_the_requested_status_and_is_not_usable():
    minted = _mint(_opening_deck())
    current = _refresh(minted.items)
    current[2] = _conflicted(current[2])
    late = T0 + timedelta(seconds=EDITION_LEASE_SECONDS + 1)
    out = _request(current, minted, now=late)
    assert out.status == UNSUPPORTED and not out.usable
    assert out.edition_status == EDITION_STATUS_EXPIRED
    assert out.deck_seating.refused_conflicts == ["event:900"]


def test_an_unpinned_refusal_is_unsupported_not_a_deck():
    deck = _opening_deck()
    deck[2] = _conflicted(deck[2])
    out = compose_opening_edition(
        deck, None, requested_token=None, requested_policy=POLICY, now=T1
    )
    assert out.status == UNSUPPORTED and out.edition_status == EDITION_STATUS_UNPINNED
    assert not out.retire_requested and out.token is None


def test_a_group_laundering_a_live_child_refuses_the_pin():
    deck = _opening_deck(game_seat=14)
    deck.insert(1, {"type": "bundle", "data": {"id": "b1", "items": [_event(901)]}})
    minted = _mint(deck)
    current = _refresh(minted.items)
    current[1]["data"]["items"][0] = _live(current[1]["data"]["items"][0])
    out = _request(current, minted)
    assert out.status == UNSUPPORTED and out.edition_status is None


# --- F. nothing scored, nothing duplicated, manifest ↔ token ----------------


def test_every_score_and_probability_is_preserved_and_no_question_duplicated():
    deck = _opening_deck(n_futures=18)
    minted = _mint(deck)
    current = _refresh(minted.items) + [_futures(501, p=0.33, score=12.5)]
    current[2] = _live(current[2])
    snapshot = {feed_edition_member(c): copy.deepcopy(c) for c in current}
    out = _request(current, minted)
    assert out.status == COMPOSED
    assert len(_ids(out.items)) == len(set(_ids(out.items))) == len(current)
    assert set(_ids(out.items)) == set(snapshot)
    for card in out.items:
        assert card == snapshot[feed_edition_member(card)]
        assert any(card is c for c in current)


def test_the_replacement_manifest_agrees_with_its_token_and_round_trips():
    minted = _mint(_thin_deck(3, 4))
    m = minted.manifest
    assert m["token"] == minted.token == feed_edition_token(minted.items, 3)
    assert m["members"] == _ids(minted.items) and m["policy"] == POLICY
    assert m["built_at"] == T0.timestamp()
    assert manifest_section_layout(m) == (LAYOUT_SECTIONS, 3)
    held = _request(_refresh(minted.items), minted)
    assert held.status == HELD and held.token == minted.token


def test_a_section_aware_manifest_refuses_to_mint_under_a_wrong_token_or_boundary():
    deck = _thin_deck(3, 4)
    kw = dict(policy=POLICY, built_at=1.0, sections=True)
    assert (
        build_edition_manifest(
            deck, token=feed_edition_token(deck), continuation_start=3, **kw
        )
        is None
    )
    assert (
        build_edition_manifest(deck, token="x", continuation_start=len(deck), **kw)
        is None
    )
    assert (
        build_edition_manifest(deck, token="x", continuation_start=True, **kw) is None
    )
    with pytest.raises(ValueError):
        build_edition_manifest(
            deck, token="x", policy=POLICY, built_at=1.0, continuation_start=0
        )


def test_the_default_manifest_and_fingerprint_are_byte_for_byte_legacy():
    # Literals captured from 1d26093515 before this change.
    assert edition_policy_fingerprint(limit=20) == "7d8b95fd3d41a352"
    assert (
        edition_policy_fingerprint(
            limit=50, principal="u:7", category="economics", mode="sports", sport="nfl"
        )
        == "b28aad3c8cd1ac48"
    )
    assert (
        edition_policy_fingerprint(limit=20, opening_seating=True) != "7d8b95fd3d41a352"
    )
    m = build_edition_manifest(
        [{"type": "futures", "data": {"id": 1}}], token="t", policy="p", built_at=1.0
    )
    assert m == {
        "token": "t",
        "policy": "p",
        "members": ["futures:1"],
        "total": 1,
        "built_at": 1.0,
    }
    assert manifest_section_layout(m) == (LAYOUT_LEGACY, None)
    # The legacy reader still pins a legacy manifest exactly as before.
    items, status = apply_pinned_edition(
        [{"type": "futures", "data": {"id": 1}}], m, requested_policy="p", now=1.0
    )
    assert status == EDITION_STATUS_PINNED and _ids(items) == ["futures:1"]


def test_the_composition_reuses_the_existing_pin_seating_and_token_functions():
    """No second pin implementation, classifier or token scheme."""
    import inspect

    src = inspect.getsource(ed)
    for name in ("apply_pinned_edition", "seat_opening", "feed_edition_token"):
        assert f"{name}(" in src
    for forbidden in (
        "hashlib",
        "_event_lifecycle",
        "classify_card",
        'manifest.get("members")',
    ):
        assert forbidden not in src


def test_a_clock_without_a_timezone_is_refused():
    with pytest.raises(ValueError):
        compose_opening_edition(
            [],
            None,
            requested_token=None,
            requested_policy=POLICY,
            now=T0.replace(tzinfo=None),
        )
