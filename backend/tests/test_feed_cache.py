import re
from pathlib import Path

import pytest

from app.tasks import redis_state
from app.utils.feed_cache import (
    FEED_EDITION_FIELD,
    FEED_RESPONSE_STALE_TTL_SECONDS,
    _FEED_EDITION_IDENT_FIELDS,
    _feed_edition_member,
    build_feed_cache_metadata,
    feed_edition_token,
    invalidate_feed_response_cache,
    render_feed_page_from_base,
)


class _FakeAsyncRedis:
    def __init__(self, keys: list[str]):
        self.keys = list(keys)
        self.deleted: list[str] = []
        self.closed = False

    async def scan_iter(self, match: str, count: int = 100):
        assert match == "feed_cache:*"
        assert count == 100
        for key in list(self.keys):
            if key.startswith("feed_cache:"):
                yield key

    async def delete(self, *keys: str) -> int:
        self.deleted.extend(keys)
        return len(keys)

    async def aclose(self) -> None:
        self.closed = True


def test_build_feed_cache_metadata_exposes_stable_fields():
    assert build_feed_cache_metadata("miss", ttl_seconds=60) == {
        "status": "miss",
        "ttl_seconds": 60,
        "stale_ttl_seconds": FEED_RESPONSE_STALE_TTL_SECONDS,
    }


@pytest.mark.asyncio
async def test_invalidate_feed_response_cache_deletes_fresh_and_stale_keys(
    monkeypatch,
):
    fake = _FakeAsyncRedis(
        [
            "feed_cache:fresh",
            "feed_cache:fresh:stale",
            "other_cache:key",
        ]
    )
    monkeypatch.setattr(redis_state, "get_async_redis_client", lambda: fake)

    result = await invalidate_feed_response_cache("test")

    assert result == {"status": "ok", "deleted": 2, "reason": "test"}
    assert fake.deleted == ["feed_cache:fresh", "feed_cache:fresh:stale"]
    assert fake.closed is True


# =============================================================================
# D1 clause (a) / #4110 — the feed's edition token.
#
# THE READER'S COMPLAINT THIS ANSWERS. Alex, on his phone at 3:30pm PT on
# 2026-09-08: the Discover feed re-rendered several times while loading and a
# card he was reading disappeared. "Unsettling."
#
# native/072 measured the client half and found no race — it is what a normal
# successful load does. ``DiscoverViewModel`` assigns the whole ``items`` array
# in three places (boot seed from last-good cache, fresh fetch, pagination
# merge) and re-derives order via ``FeedInterleave.byCategory`` each time. The
# cached body and the fresh body are different inputs, so they interleave to
# different orders: the boot paint is not a prefix of the fresh paint.
#
# The client fix is to reconcile instead of reassign (#4110, native's). It needs
# one thing from the server that the server did not previously say: IS THIS THE
# SAME LIST I ALREADY PAINTED? A wholesale reorder becomes legal only when the
# server says the ordering changed.
#
# WHAT IS GUARDED, IN ONE LINE: ``feed_edition_token`` changes when, and ONLY
# when, the ordered membership of the feed changes. Both halves of that
# biconditional are load-bearing and they fail in opposite directions, so both
# are tested:
#
#   * changed when it should not (a per-request nonce, a build timestamp) => the
#     client is told "new edition" on every 2-minute live-price poll and
#     reshuffles under the reader's thumb — the exact bug, now with a token
#     blessing it. This is the direction ``_page_base_built_at`` fails in, which
#     is why it could not be reused.
#   * stayed put when it should not => the client holds an order the server has
#     abandoned, pinning stale cards on page one.
#
# The third clause is offset stability: pagination merges page 2 into the list
# page 1 painted, so page 2 must prove it belongs to page 1's edition.
#
# These live in this file rather than their own because a NEW test file
# repartitions the four CI shards, which reds whichever file then lands beside
# the process-global rate-limit ceiling leak (#4090, not this lane's).
# =============================================================================


#: The identity field each kind ACTUALLY carries in the served payload, read off
#: production `GET /api/feed?limit=40` on 2026-09-08: 28 futures + 8 bundle + 1
#: event on ``data.id``, 3 concept on ``data.key`` and no ``id`` at all.
#:
#: Stated here, in the fixture, rather than imported from the module under test.
#: CERT-2309 blocked this file's first cut because the fixture gave EVERY kind an
#: ``id``, so the tests below passed on a payload shape production never serves
#: and the concept collapse was invisible to all of them. A fixture that borrows
#: the implementation's own map could not fail that way either — and could not
#: fail if the map itself were wrong, which is the failure that actually happened.
_FIXTURE_IDENT_FIELD = {
    "event": "id",
    "futures": "id",
    "bundle": "id",
    "concept": "key",
    "tournament": "key",
}


def edition_card(kind: str, ident, *, probability=0.5, score=70, reason="") -> dict:
    """A feed item in the shape ``GET /api/feed`` serves — including which field
    carries the identity, which differs by kind (`_FIXTURE_IDENT_FIELD`).

    ``probability``/``score``/``reason`` are the volatile fields — the ones that
    move on the 2-minute live-price poll and on every rescore. They are
    parameters precisely so a test can move them and assert the token does not.
    """
    return {
        "type": kind,
        "score": score,
        "reason": reason,
        "headline": None,
        "data": {
            _FIXTURE_IDENT_FIELD.get(kind, "id"): ident,
            "probability": probability,
        },
    }


def an_edition_feed(n: int = 6) -> list[dict]:
    """A mixed list of the three types Discover actually interleaves."""
    kinds = ("event", "futures", "bundle")
    return [edition_card(kinds[i % 3], 1000 + i) for i in range(n)]


# --- the token is a function of the ordered membership, and nothing else -------


def test_the_same_list_yields_the_same_token_in_any_process():
    """Reproducibility. Two dynos building the same list must agree, or a cache
    eviction would present to the client as a brand-new edition and reshuffle."""
    assert feed_edition_token(an_edition_feed()) == feed_edition_token(
        an_edition_feed()
    )


def test_prices_moving_does_not_roll_the_edition():
    """THE CENTRAL CLAUSE. `poll_live_prediction_markets` runs every 2 minutes and
    rewrites the probability on most cards. If that rolled the edition, the client
    would be authorised to reorder the page a reader is mid-scroll on, roughly 30
    times an hour — which is the reported bug, not a fix for it."""
    before = an_edition_feed()
    after = [dict(c, data=dict(c["data"], probability=0.99)) for c in before]

    assert [c["data"]["probability"] for c in after] != [
        c["data"]["probability"] for c in before
    ], "fixture must actually move the prices, or this asserts nothing"
    assert feed_edition_token(after) == feed_edition_token(before)


def test_rescoring_and_rewording_do_not_roll_the_edition():
    """Same argument for the other two volatile fields. A reason string rewritten
    by a deterministic composer, or a score nudged by personalization, is not a
    new list."""
    before = an_edition_feed()
    after = [dict(c, score=1, reason="totally different sentence") for c in before]

    assert feed_edition_token(after) == feed_edition_token(before)


def test_reordering_the_same_cards_rolls_the_edition():
    """The other direction. Same membership, different order IS a new edition —
    the client must not keep painting an order the server abandoned."""
    before = an_edition_feed()
    after = list(before)
    after[0], after[1] = after[1], after[0]

    assert feed_edition_token(after) != feed_edition_token(before)


def test_a_card_leaving_rolls_the_edition():
    before = an_edition_feed()
    after = before[:-1]

    assert feed_edition_token(after) != feed_edition_token(before)


def test_a_card_arriving_rolls_the_edition():
    before = an_edition_feed()
    after = before + [edition_card("futures", 9999)]

    assert feed_edition_token(after) != feed_edition_token(before)


def test_a_swapped_card_rolls_the_edition_even_at_the_same_length():
    """Length alone is not identity: a card replaced in place is a new list."""
    before = an_edition_feed()
    after = list(before)
    after[2] = edition_card("futures", 424242)

    assert feed_edition_token(after) != feed_edition_token(before)


def test_the_same_id_under_a_different_type_is_a_different_card():
    """`event:1000` and `futures:1000` are two different cards that happen to share
    an integer. Keying on the id alone would call them one."""
    assert feed_edition_token([edition_card("event", 1000)]) != feed_edition_token(
        [edition_card("futures", 1000)]
    )


# --- CERT-2309's repair: every kind the route emits has an identity -------------
# `4110-CONCEPT-AND-TOURNAMENT-KEYS-PARTICIPATE-IN-EDITION`.
#
# The first cut read ``data["id"]`` for every card. `concept` and `tournament`
# carry ``data["key"]`` instead, so on the production payload three concepts and
# the live tournament all rendered as ``"?"`` — positionally present, individually
# indistinguishable. The bus's falsifier is the first two tests here: swap two real
# concepts, or replace one outright, and the token did not move. The server told
# the client "same list" about a list whose visible cards had changed.


def a_production_shaped_feed() -> list[dict]:
    """The mix production actually serves, per the 2026-09-08 census: the
    id-keyed kinds AND the key-keyed ones, which is what the old fixture lacked."""
    return [
        edition_card("futures", 5001),
        edition_card("concept", "us-open-2026"),
        edition_card("bundle", 7001),
        edition_card("concept", "fed-september"),
        edition_card("tournament", "vuelta-a-espana-2026"),
        edition_card("event", 9001),
        edition_card("concept", "world-cup-2030"),
    ]


def test_swapping_two_concepts_rolls_the_edition():
    """CERT-2309's falsifier, first half. Two concept cards trading slots is a
    reorder the reader can see; before the repair both hashed as ``"?"`` and the
    token was byte-identical."""
    before = a_production_shaped_feed()
    after = list(before)
    after[1], after[3] = after[3], after[1]

    assert after != before, "fixture must actually swap, or this asserts nothing"
    assert feed_edition_token(after) != feed_edition_token(before)


def test_replacing_a_concept_with_a_different_one_rolls_the_edition():
    """CERT-2309's falsifier, second half. A substitution at the same slot, same
    kind, same length — identity is the only thing that changed, so identity is
    the only thing that can catch it."""
    before = a_production_shaped_feed()
    after = list(before)
    after[1] = edition_card("concept", "a-completely-different-concept")

    assert feed_edition_token(after) != feed_edition_token(before)


def test_replacing_a_tournament_rolls_the_edition():
    """The other key-keyed kind, which the falsifier reached through the same
    collapse. `tournament` is one card on the page, so a repair that fixed only
    `concept` would leave the marquee card unidentifiable."""
    before = a_production_shaped_feed()
    after = list(before)
    after[4] = edition_card("tournament", "some-other-tournament")

    assert feed_edition_token(after) != feed_edition_token(before)


def test_no_card_the_route_emits_hashes_as_unidentified():
    """The direct statement of the defect, kind by kind, so a regression names the
    kind that broke rather than just moving a hash."""
    for kind, ident in (
        ("event", 1),
        ("futures", 2),
        ("bundle", 3),
        ("concept", "a-key"),
        ("tournament", "a-tournament-key"),
    ):
        member = _feed_edition_member(edition_card(kind, ident))
        assert member != "?", f"{kind} card collapsed to '?' — CERT-2309's defect"
        assert member == f"{kind}:{ident}"


def test_every_kind_the_feed_route_emits_is_taught_to_the_edition():
    """The guard that makes the NEXT kind fail here instead of in production.

    `concept` and `tournament` were not new when this token shipped — they were
    simply never enumerated. So this reads the kinds out of the source that emits
    them and requires the map to know each one. A sixth card kind added to the
    feed with neither an ``id`` nor a ``key`` fails this test on the day it is
    written, which is the only day it is cheap to fix.

    Read from source rather than from a live payload deliberately: a payload
    census only sees the kinds that happened to rank today (`tournament` is
    frequently absent), and a guard that passes because a kind was missing is the
    same failure one level up.
    """
    emitters = (
        Path(__file__).resolve().parents[1] / "app" / "routes" / "feed.py",
        Path(__file__).resolve().parents[1] / "app" / "utils" / "discover_bundles.py",
    )
    emitted = set()
    for path in emitters:
        assert path.exists(), f"emitter moved: {path}"
        emitted |= set(re.findall(r'"type":\s*"([a-z_]+)"', path.read_text()))

    assert emitted, "found no card kinds in the source — the pattern went stale"
    assert {"concept", "tournament"} <= emitted, (
        "the two kinds CERT-2309 was about are no longer found in the source; "
        "this guard is reading the wrong place"
    )

    untaught = emitted - set(_FEED_EDITION_IDENT_FIELDS)
    assert not untaught, (
        f"card kind(s) {sorted(untaught)} are emitted by the feed but have no "
        "identity field in _FEED_EDITION_IDENT_FIELDS, so every one of them "
        "hashes to '?' and cannot be told apart within an edition (CERT-2309)"
    )


def test_an_unknown_kind_still_participates_if_it_carries_either_field():
    """The fallback. A kind this module has not been taught degrades to a search
    for the two conventional fields rather than straight to ``"?"`` — so the guard
    above is what enforces the map, and an untaught kind is still identified in
    the meantime instead of silently costing the token its resolution."""
    assert _feed_edition_member(
        {"type": "novel_kind", "data": {"key": "abc"}}
    ) == "novel_kind:abc"
    assert _feed_edition_member(
        {"type": "novel_kind", "data": {"id": 12}}
    ) == "novel_kind:12"


def test_a_card_with_no_identity_is_still_positional():
    """``"?"`` remains the floor: unidentifiable cards must still occupy a slot, or
    a list of three would hash like an empty one and a card could vanish without
    moving the token."""
    assert _feed_edition_member({"type": "mystery", "data": {}}) == "?"

    one = [{"type": "mystery", "data": {}}]
    two = [{"type": "mystery", "data": {}}, {"type": "mystery", "data": {}}]
    assert feed_edition_token(one) != feed_edition_token(two)


# --- offset stability: native's question 3 --------------------------------------


def test_every_page_of_one_build_carries_one_edition():
    """Pagination merges page 2 into the list page 1 painted, so the two must
    agree on which edition they belong to.

    This exercises the real mechanism rather than asserting the intent: the token
    is computed over the WHOLE list and stored on the base, and
    ``render_feed_page_from_base`` — which copies every non-per-serve key — is what
    carries it onto each page. If a future edit moved the token into the per-serve
    pop-list, this test is what fails."""
    items = an_edition_feed(120)
    base = {
        "items": items,
        "total": len(items),
        FEED_EDITION_FIELD: feed_edition_token(items),
    }

    page1 = render_feed_page_from_base(base, limit=50, offset=0)
    page2 = render_feed_page_from_base(base, limit=50, offset=50)
    page3 = render_feed_page_from_base(base, limit=50, offset=100)

    assert page1[FEED_EDITION_FIELD] == page2[FEED_EDITION_FIELD]
    assert page2[FEED_EDITION_FIELD] == page3[FEED_EDITION_FIELD]
    # And the pages really are different windows, so the agreement above is not
    # three reads of one identical object.
    assert page1["items"] != page2["items"]


def test_the_edition_is_the_whole_lists_not_the_windows():
    """The bug this forecloses: computing the token over ``paginated``. It would
    pass every membership test above and still give each page its own token,
    making the pagination merge unprovable."""
    items = an_edition_feed(120)
    whole = feed_edition_token(items)

    assert feed_edition_token(items[0:50]) != whole
    assert feed_edition_token(items[50:100]) != whole


# --- absence is a state, not a value --------------------------------------------


@pytest.mark.parametrize("empty", [[], None, "not a list", {}, 0])
def test_a_refusal_states_no_edition_rather_than_a_constant_one(empty):
    """Every empty return in ``get_feed`` is a refusal — requires-auth,
    leader-unavailable, input-age-ceiling — not an edition of the feed.

    Hashing the empty list to a stable constant would hand all three the same
    authoritative-looking token, and a client reconciling against it would treat
    three different failures as one agreed ordering. ``None`` is also what an
    older backend sends, so the client needs the absent branch anyway."""
    assert feed_edition_token(empty) is None


def test_an_unidentifiable_card_occupies_its_slot_rather_than_vanishing():
    """A card we cannot identify must still register, or the token would be blind
    to exactly the population it is meant to watch.

    Skipping unidentifiable items would make a list of three of them hash
    identically to the empty list, and would let such a card appear or disappear
    without moving the token — the failure this whole file exists to prevent."""
    one = feed_edition_token([edition_card("event", 1), {"type": None, "data": None}])
    two = feed_edition_token([edition_card("event", 1)])
    three = feed_edition_token(
        [edition_card("event", 1), {"type": None, "data": None}, {"junk": True}]
    )

    assert one != two
    assert three != one


def test_the_token_is_a_short_stable_hex_string():
    """Shape contract for the client decoding it and for the header/log reader."""
    token = feed_edition_token(an_edition_feed())

    assert isinstance(token, str)
    assert len(token) == 16
    assert all(ch in "0123456789abcdef" for ch in token)


def test_computing_the_token_does_not_mutate_the_feed():
    """It runs after the private-key scrub and immediately before the page base is
    stored; a mutation here would be published to every reader of page 2."""
    items = an_edition_feed()
    snapshot = [dict(c, data=dict(c["data"])) for c in items]

    feed_edition_token(items)

    assert items == snapshot
