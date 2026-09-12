"""T4-B2 / #5102 — browsing editions: page two is served in page one's order.

What is actually being defended, stated as a reader would: *a card does not move
or vanish under your thumb while you scroll, and its number is still live.* The
two halves of that sentence pull against each other, and most of this file is
about the tension:

  * pin the ORDER and the reader keeps their place;
  * pin the PAYLOAD and you have frozen the prices, which is the other bug.

So the load-bearing test here is not "pinned order is honoured" — it is
`test_a_pinned_serve_carries_current_prices_not_the_ones_the_edition_was_minted_with`.
A snapshot implementation passes every ordering test in this file and fails that
one, which is why it exists and why it is not merely an ordering assertion with
extra words.

Every function under test is pure and takes `now` as a parameter, so nothing
here fakes a clock (gotcha #44 — an anchor that branches on the clock is not an
anchor). Ages are written as offsets from one module-level `NOW`.
"""

from __future__ import annotations

import inspect

import pytest

from app.utils.feed_cache import feed_edition_token
from app.utils.feed_editions import (
    EDITION_LEASE_SECONDS,
    EDITION_STATUS_EXPIRED,
    EDITION_STATUS_INVALIDATED,
    EDITION_STATUS_PINNED,
    EDITION_STATUS_SUPERSEDED,
    apply_pinned_edition,
    build_edition_manifest,
    edition_manifest_cache_key,
    edition_policy_fingerprint,
    manifest_is_within_lease,
    pinned_member_identities,
)

NOW = 1_789_200_000.0
POLICY = "policy-a"


def card(kind: str, ident, price: float = 0.5) -> dict:
    """One feed card, shaped as the route emits it.

    ``price`` is the thing that must move between the mint and the serve; it is
    a stand-in for every live number on a card (probability, score, reason).
    """
    key = "key" if kind in ("concept", "tournament") else "id"
    return {"type": kind, "data": {key: ident, "probability": price}}


def deck(*idents, price: float = 0.5) -> list:
    return [card("event", i, price) for i in idents]


def mint(items, *, policy: str = POLICY, built_at: float = NOW) -> dict:
    token = feed_edition_token(items)
    manifest = build_edition_manifest(
        items, token=token, policy=policy, built_at=built_at
    )
    assert manifest is not None, "fixture minted an unstorable manifest"
    return manifest


# ---------------------------------------------------------------------------
# A. The ship — the order holds, the numbers do not
# ---------------------------------------------------------------------------


def test_a_reordered_build_is_served_in_the_editions_order():
    """The whole point. The build has reshuffled; the reader is mid-scroll."""
    original = deck(1, 2, 3, 4)
    manifest = mint(original)
    reshuffled = deck(4, 1, 3, 2)

    items, status = apply_pinned_edition(
        reshuffled, manifest, requested_policy=POLICY, now=NOW
    )

    assert status == EDITION_STATUS_PINNED
    assert pinned_member_identities(items) == pinned_member_identities(original)


def test_a_pinned_serve_carries_current_prices_not_the_ones_the_edition_was_minted_with():
    """🔴 THE ONE THAT SEPARATES THE FIX FROM THE EASY WRONG FIX.

    Storing the payloads would satisfy every ordering test above and ship a feed
    whose numbers stop moving for half an hour. "A card stays put while its
    probability updates" is the ship; a frozen probability is not an update.

    The manifest is minted off a 0.10 deck and the serve happens against a 0.99
    deck. Pinned order, current numbers.
    """
    manifest = mint(deck(1, 2, 3, price=0.10))
    current = deck(3, 1, 2, price=0.99)

    items, status = apply_pinned_edition(
        current, manifest, requested_policy=POLICY, now=NOW
    )

    assert status == EDITION_STATUS_PINNED
    assert [i["data"]["id"] for i in items] == [1, 2, 3]
    assert [i["data"]["probability"] for i in items] == [0.99, 0.99, 0.99]


def test_the_pinned_items_are_the_very_objects_from_the_current_build():
    """Identity, not equality — a copy would be a snapshot by another name and
    would drift from whatever the route mutates downstream."""
    manifest = mint(deck(1, 2))
    current = deck(2, 1)
    items, _ = apply_pinned_edition(
        current, manifest, requested_policy=POLICY, now=NOW
    )
    assert items[0] is current[1]
    assert items[1] is current[0]


def test_a_pinned_build_re_derives_the_very_token_it_was_asked_for():
    """The route relies on this and says so: after reordering ``feed_items`` it
    does NOT override the edition token, because hashing the pinned order must
    reproduce the requested token by construction. If that identity ever broke,
    a pinned reader would be handed a token they did not ask for and the client
    would re-render — the pin would cause the bug it fixes."""
    original = deck(1, 2, 3, 4, 5)
    token = feed_edition_token(original)
    manifest = mint(original)

    items, status = apply_pinned_edition(
        deck(5, 4, 3, 2, 1), manifest, requested_policy=POLICY, now=NOW
    )

    assert status == EDITION_STATUS_PINNED
    assert feed_edition_token(items) == token


# ---------------------------------------------------------------------------
# B. Never a splice — the four ways a pin declines
# ---------------------------------------------------------------------------


def test_a_card_that_left_the_feed_invalidates_the_whole_edition():
    """NOT a quiet drop. Dropping the missing card and shuffling the rest up is
    exactly the "new order spliced into page two" the design rules out, and to
    the reader it is indistinguishable from the defect."""
    manifest = mint(deck(1, 2, 3))
    items, status = apply_pinned_edition(
        deck(1, 3), manifest, requested_policy=POLICY, now=NOW
    )
    assert status == EDITION_STATUS_INVALIDATED
    assert items is None


def test_a_card_that_is_new_since_the_mint_is_not_spliced_in():
    """The other direction of the same rule. A reader browses the edition they
    started; a new card belongs to the next one."""
    manifest = mint(deck(1, 2))
    items, status = apply_pinned_edition(
        deck(1, 99, 2), manifest, requested_policy=POLICY, now=NOW
    )
    assert status == EDITION_STATUS_PINNED
    assert [i["data"]["id"] for i in items] == [1, 2]


def test_a_missing_manifest_is_expired_not_an_error():
    """A reader who leaves a tab open overnight gets today's feed, not a 410."""
    items, status = apply_pinned_edition(
        deck(1, 2), None, requested_policy=POLICY, now=NOW
    )
    assert status == EDITION_STATUS_EXPIRED
    assert items is None


def test_a_manifest_from_another_build_is_superseded():
    manifest = mint(deck(1, 2), policy="policy-a")
    items, status = apply_pinned_edition(
        deck(1, 2), manifest, requested_policy="policy-b", now=NOW
    )
    assert status == EDITION_STATUS_SUPERSEDED
    assert items is None


def test_policy_is_checked_before_the_lease_so_a_sign_in_reads_superseded():
    """Diagnostic quality, and it is the field's whole job. An account switch on
    a stale manifest must say `superseded` — "you are asking the wrong list" —
    not `expired`, which would send an operator hunting a TTL."""
    manifest = mint(deck(1), policy="anon", built_at=NOW - EDITION_LEASE_SECONDS * 10)
    _, status = apply_pinned_edition(
        deck(1), manifest, requested_policy="signed-in", now=NOW
    )
    assert status == EDITION_STATUS_SUPERSEDED


def test_the_lease_is_checked_before_membership_so_a_stale_reader_reads_expired():
    """Same reasoning one step along: a reader returning tomorrow to a slate that
    has completely turned over gets `expired`, not an `invalidated` that blames
    the slate for the clock."""
    manifest = mint(deck(1, 2), built_at=NOW - EDITION_LEASE_SECONDS - 1)
    _, status = apply_pinned_edition(
        deck(97, 98), manifest, requested_policy=POLICY, now=NOW
    )
    assert status == EDITION_STATUS_EXPIRED


# ---------------------------------------------------------------------------
# C. The lease boundary, from both sides
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "age,inside",
    [
        (0, True),
        (EDITION_LEASE_SECONDS - 1, True),
        (EDITION_LEASE_SECONDS, True),
        (EDITION_LEASE_SECONDS + 1, False),
        (EDITION_LEASE_SECONDS * 4, False),
    ],
)
def test_both_sides_of_the_browsing_lease(age, inside):
    manifest = mint(deck(1), built_at=NOW - age)
    assert manifest_is_within_lease(manifest, now=NOW) is inside


def test_a_manifest_with_no_build_time_is_not_treated_as_fresh():
    """Defaulting an unknown age to zero is how a lease becomes unbounded, and
    the failure is invisible — the reader just keeps one order forever."""
    assert manifest_is_within_lease({"members": ["event:1"]}, now=NOW) is False


def test_the_lease_is_measured_from_the_mint_not_from_the_read():
    """Re-reading an edition must not extend it. The route enforces the other
    half (it does not republish a manifest on a pinned serve); this is the
    arithmetic half."""
    manifest = mint(deck(1), built_at=NOW - EDITION_LEASE_SECONDS + 10)
    assert manifest_is_within_lease(manifest, now=NOW) is True
    assert manifest_is_within_lease(manifest, now=NOW + 20) is False


# ---------------------------------------------------------------------------
# D. Minting — what is refused, and why refusing is the safe direction
# ---------------------------------------------------------------------------


def test_an_unidentifiable_card_refuses_the_whole_manifest():
    """``"?"`` is positional. Two unidentified cards could swap under a pin
    without the manifest noticing, so the pin would silently serve a different
    order — the exact failure it exists to prevent. CERT-2309 is the precedent:
    concept and tournament cards collapsing to ``"?"`` let two of them swap
    without the token moving."""
    items = deck(1, 2) + [{"type": "mystery", "data": {"no_id": True}}]
    assert build_edition_manifest(items, token="t", policy=POLICY, built_at=NOW) is None


def test_concept_and_tournament_cards_key_on_their_own_field():
    """The CERT-2309 case, positively: these carry ``key``, not ``id``, and a
    manifest that could not identify them would refuse every real Discover deck
    (production served 12 concept + 2 tournament cards on the measured slate)."""
    items = [card("concept", "nfl-week-2"), card("tournament", "us-open")]
    manifest = build_edition_manifest(
        items, token="t", policy=POLICY, built_at=NOW
    )
    assert manifest is not None
    assert manifest["members"] == ["concept:nfl-week-2", "tournament:us-open"]


@pytest.mark.parametrize("empty", [[], None, "not a list", {}])
def test_nothing_worth_pinning_mints_nothing(empty):
    """Every empty feed is a refusal (requires-auth, leader-unavailable,
    input-age-ceiling), not an edition — `feed_edition_token`'s own reasoning,
    inherited rather than re-argued."""
    assert build_edition_manifest(empty, token="t", policy=POLICY, built_at=NOW) is None


def test_the_manifest_records_what_it_was_minted_for():
    manifest = mint(deck(1, 2, 3))
    assert manifest["policy"] == POLICY
    assert manifest["total"] == 3
    assert manifest["built_at"] == NOW
    assert manifest["members"] == ["event:1", "event:2", "event:3"]


# ---------------------------------------------------------------------------
# E. Policy fingerprint — what counts as "a different list"
# ---------------------------------------------------------------------------


def test_the_same_request_shape_fingerprints_the_same():
    assert edition_policy_fingerprint(limit=20) == edition_policy_fingerprint(limit=20)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 50},
        {"limit": 20, "sport": "basketball"},
        {"limit": 20, "mode": "sports"},
        {"limit": 20, "category": "politics"},
        {"limit": 20, "include_events": False},
        {"limit": 20, "include_futures": False},
        {"limit": 20, "my_teams_only": True},
        {"limit": 20, "tags": '["sport:basketball"]'},
        {"limit": 20, "event_pct": 0.3},
        {"limit": 20, "principal": "u:7"},
    ],
)
def test_every_build_input_changes_the_fingerprint(kwargs):
    """Each of these makes it a different list, so an order pinned from one is
    meaningless against another."""
    assert edition_policy_fingerprint(**kwargs) != edition_policy_fingerprint(limit=20)


def test_signing_in_is_a_new_edition():
    """The design's "auth change = new edition", stated as the two fingerprints
    a sign-in moves between."""
    anon = edition_policy_fingerprint(limit=20)
    user = edition_policy_fingerprint(limit=20, principal="u:7")
    other = edition_policy_fingerprint(limit=20, principal="u:8")
    assert anon != user != other
    assert anon != other


def test_limit_is_a_build_input_so_native_and_web_never_share_an_edition():
    """Mirrors `feed_page_base_cache_key`'s rule for the same reason: display
    stages size their windows from `limit`, so 20 and 50 are two lists."""
    assert edition_policy_fingerprint(limit=20) != edition_policy_fingerprint(limit=50)


def test_a_free_text_value_cannot_forge_another_shape():
    """Length-delimited, so a category containing the separator cannot collide
    with a different category plus principal."""
    a = edition_policy_fingerprint(limit=20, category="a|b", principal="c")
    b = edition_policy_fingerprint(limit=20, category="a", principal="b|c")
    assert a != b


# ---------------------------------------------------------------------------
# F. The cache key
# ---------------------------------------------------------------------------


def test_the_manifest_key_separates_editions_and_policies():
    a = edition_manifest_cache_key(token="t1", policy="p1")
    b = edition_manifest_cache_key(token="t2", policy="p1")
    c = edition_manifest_cache_key(token="t1", policy="p2")
    assert len({a, b, c}) == 3


def test_the_manifest_key_is_swept_by_the_feed_cache_invalidator():
    """`invalidate_feed_response_cache` scans ``feed_cache:*``. A manifest left
    behind by an invalidation would keep re-pinning the pre-invalidation ORDER
    onto the new build — the page-base comment's trap, one layer up."""
    assert edition_manifest_cache_key(token="t", policy="p").startswith("feed_cache:")


# ---------------------------------------------------------------------------
# G. The unpinned path is untouched
# ---------------------------------------------------------------------------


def test_a_non_list_build_cannot_crash_a_pin():
    """A pin must never be able to turn a feed read into an error."""
    items, status = apply_pinned_edition(
        None, mint(deck(1)), requested_policy=POLICY, now=NOW
    )
    assert items is None and status == EDITION_STATUS_EXPIRED


def test_a_manifest_with_no_members_is_expired_not_a_pin_to_nothing():
    """Otherwise a corrupt manifest would pin every reader to an empty feed —
    a blank page served with a 200, which is the worst of the available
    failures."""
    items, status = apply_pinned_edition(
        deck(1, 2),
        {"policy": POLICY, "members": [], "built_at": NOW},
        requested_policy=POLICY,
        now=NOW,
    )
    assert items is None and status == EDITION_STATUS_EXPIRED


# ---------------------------------------------------------------------------
# H. The route's wiring order — silently breakable, so pinned in source
# ---------------------------------------------------------------------------


def test_the_fingerprint_is_computed_after_the_server_side_defaulting():
    """🔴 ORDER IS LOAD-BEARING AND ITS FAILURE IS INVISIBLE.

    ``get_feed`` rewrites its own build inputs before caching: a bare Discover
    request arrives with ``event_pct=None, mode=None`` and is defaulted to
    ``0.15`` / ``"discover"``. The edition fingerprint must be taken AFTER that,
    or one reader sending ``?mode=discover`` explicitly and another sending
    nothing would fingerprint differently while reading the identical build —
    every pin between them reporting `superseded`.

    That failure degrades to exactly today's behaviour, which is why nothing
    else would catch it: the feature would simply stop working, quietly, and
    the tests would all still pass. Hence a source-order assertion.
    """
    from app.routes.feed import get_feed

    src = inspect.getsource(get_feed)
    defaulting = src.index('event_pct = 0.15')
    fingerprint = src.index("_edition_policy = _edition_policy_for(")
    assert defaulting < fingerprint, (
        "the Discover defaulting must run BEFORE the edition fingerprint"
    )


def test_the_fingerprint_is_computed_after_the_principal_is_resolved():
    """Same class, the other input. ``feed_user``/``feed_session_id`` are what
    make an edition principal-bound (the design's "auth change = new edition");
    fingerprinting before they are resolved would bind every reader to the
    anonymous edition and let one reader pin another's personalized order."""
    from app.routes.feed import get_feed

    src = inspect.getsource(get_feed)
    principal = src.index("feed_session_id = None if debug_global else session_id")
    fingerprint = src.index("_edition_policy = _edition_policy_for(")
    assert principal < fingerprint


def test_the_route_actually_passes_the_principal_into_the_fingerprint():
    """🔴 FOUND BY MUTATION, AND IT SURVIVED THE FIRST CUT OF THIS FILE.

    ``test_signing_in_is_a_new_edition`` proves the FUNCTION separates
    principals. It says nothing about whether the ROUTE hands it one — and
    deleting the ``principal=`` argument from the call site passed all 46 tests.
    That mutant is the security-shaped one: with no principal in the
    fingerprint, every reader shares the anonymous edition, so a signed-in
    reader can pin — and be served — an order minted for someone else.

    The guarded property is the call site, not the helper: both identity
    sources must reach it, or "auth change = new edition" is a docstring.
    """
    from app.routes.feed import get_feed

    src = inspect.getsource(get_feed)
    # The helper that actually calls the fingerprint must forward a principal…
    helper = src[src.index("def _edition_policy_for(principal):") :]
    helper = helper[: helper.index("\n    _edition_policy = ")]
    assert "principal=principal" in helper, (
        "the route must bind the edition to a principal"
    )
    # …and the default binding must derive one from BOTH identity sources.
    call = src[src.index("_edition_policy = _edition_policy_for(") :]
    call = call[: call.index("\n    )\n")]
    assert "feed_user" in call and "feed_session_id" in call, (
        "both an authenticated user and a session must reach the fingerprint"
    )


def test_the_manifest_is_not_republished_on_a_pinned_serve():
    """The lease is measured from the MINT. Republishing on every pinned page
    would reset it on each scroll and turn a 30-minute browsing lease into "as
    long as you keep scrolling" — a reader pinned to an hours-old slate."""
    from app.routes.feed import get_feed

    src = inspect.getsource(get_feed)
    publish = src[src.index("_publish_edition_manifest") - 900 :]
    publish = publish[: publish.index("schedule_background")]
    assert "EDITION_STATUS_PINNED" in publish, (
        "the manifest publish must be guarded on NOT having served a pin"
    )


def test_a_duplicate_identity_in_the_build_resolves_deterministically():
    """A duplicate identity in one build is a defect elsewhere. Resolving it to
    the first occurrence keeps this function deterministic rather than
    dependent on iteration order."""
    first, second = card("event", 1, 0.1), card("event", 1, 0.9)
    items, status = apply_pinned_edition(
        [first, second], mint(deck(1)), requested_policy=POLICY, now=NOW
    )
    assert status == EDITION_STATUS_PINNED
    assert items[0] is first


def test_an_inert_session_resolves_the_anonymous_edition_5102():
    """🔴 CERT-2704's BLOCK, and it is the documented NATIVE path.

    The native surface sends a persistent per-install session id, so
    ``feed_session_id`` is set — but its personalization context is usually
    EMPTY, and LAT-P089 therefore serves it the ANONYMOUS shared payload, which
    carries the anonymous build's edition token and whose manifest was minted
    under the ANONYMOUS policy.

    Fingerprinting that reader by session id meant page two looked up a
    session-keyed manifest that had never existed, read ``expired``, and served
    the unpinned order. Measured on the shipped helpers: anonymous policy
    ``0c75c691ef78f06c``, session policy ``0d4d2a908842c71a``. The pin was dead
    for exactly the readers it was built for — and SILENTLY, because ``expired``
    is a legitimate answer that nothing anywhere would have flagged.
    """
    from app.routes.feed import get_feed

    src = inspect.getsource(get_feed)
    block = src[src.index("# --- T4-B2 / #5102: an INERT session reads") :]
    block = block[: block.index("_edition_policy = _edition_policy_for(None)")]
    # 🔴 Read the CONDITION, not the prose above it. The first cut of this test
    # scanned the whole block and matched the explanatory comment's own mention
    # of `_edition_request` — a grep hitting its own check line, which is a
    # guard that reports on its vocabulary instead of the code.
    narrow = block[block.rindex("if (") :]
    assert "ctx == PersonalizationContext()" in narrow, (
        "the narrowing must use LAT-P089's own structural-equality predicate, "
        "not a looser test of its own"
    )
    assert "not my_teams_only" in narrow, (
        "a followed-teams page must not be reachable from a shared list, "
        "exactly as the page base refuses it"
    )
    assert "_edition_request" not in narrow, (
        "the narrowing must move the MINT as well as the lookup — gated on a "
        "pin request, an inert session that builds page one would stamp a "
        "session-keyed manifest it cannot find one request later"
    )


def test_a_personalized_reader_never_resolves_the_anonymous_edition_5102():
    """The isolation direction, which is the entire risk of the fix above.

    If a genuinely personalized reader could resolve the anonymous manifest,
    one reader's ranking would be pinned onto another's session. Asserted where
    it is decided — the two fingerprints differ, so a personalized reader
    physically cannot address the anonymous manifest — and then that exactly one
    site in the route may narrow.
    """
    assert edition_policy_fingerprint(limit=20) != edition_policy_fingerprint(
        limit=20, principal="u:7"
    )

    from app.routes.feed import get_feed

    src = inspect.getsource(get_feed)
    assert src.count("_edition_policy_for(None)") == 1, (
        "exactly one place may narrow an edition to the anonymous policy"
    )


def test_the_inert_narrowing_happens_after_the_context_is_loaded():
    """Order again, and it cannot be otherwise: ``ctx`` does not exist until
    ``_load_personalization_context`` has run, so a narrowing placed above it
    would read a name that is not yet bound — or, worse, a stale one from an
    earlier assignment if the code is later reshuffled."""
    from app.routes.feed import get_feed

    src = inspect.getsource(get_feed)
    assert src.index("_load_personalization_context(") < src.index(
        "_edition_policy = _edition_policy_for(None)"
    )
