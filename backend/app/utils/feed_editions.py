"""T4-B2 / #5102: browsing editions — pin page two to the order page one painted.

#4110 gave the client a way to NOTICE that the list changed (`feed_cache.
feed_edition_token`, a content hash of the ordered membership). It deliberately
did not give it a way to ASK for the list it already painted, and that is the
half a reader feels:

    `feed_response_cache_ttls` gives the offset-independent page base a **30
    second** fresh TTL whenever any card on the deck is live
    (`FEED_RESPONSE_TTL_LIVE_SECONDS`). A reader spends longer than that on
    twenty cards. When the base expires mid-scroll the next request rebuilds,
    and page two is a window onto a DIFFERENT ranked list.

Measured on production 2026-09-12 08:32–08:45Z, before this module existed:

  * inside one base lifetime paging is exact — offsets 0…120 at `limit=20`
    returned 131 unique cards, 0 duplicated, 0 skipped, one edition throughout;
  * across a 150s dwell, page one read edition `469e45c9c75e7c24` and page two
    read `4f67fc81a997ead2`, while two full-deck reads taken at those same two
    moments both said `469e…`. Two orderings were live at once and the reader
    had no way to name the one they were reading.

THE FIX IS AN ORDER, NOT A SNAPSHOT. The manifest stores ordered MEMBERSHIP —
card identities, nothing else. Page two is then rendered by reordering the
CURRENT build into the manifest's order, so the reader keeps their place while
every probability, price and score on the card is live. Freezing the payload
would have been a smaller diff and the wrong product: "a card stays put while
its number updates" is the ship, and a 30-minute-old price is not an update.

WHAT INVALIDATES, AND WHY IT IS NEVER A SPLICE. If a pinned member is no longer
in the build (it aged out, it settled, the noise filter took it), this does NOT
quietly drop it and shuffle the rest up — that is the "new order spliced into
page two" the design rules out, and it is indistinguishable to the reader from
the bug. The whole edition is declared `invalidated`, the caller serves the
current list, and the status field says so out loud so the client can restart
cleanly rather than merge two orders.

Cards that are NEW since the manifest was minted are likewise not inserted. A
reader browses the edition they started; the next edition is where new cards
live. `total` therefore comes from the manifest, so the scroll ends where the
pinned list ends.

This module is PURE — no clock, no I/O, no Redis, no randomness. Every
time-dependent decision is handed in (`now`, `built_at`), which is gotcha #44's
rule ("a test anchor must not branch on the clock") applied at the seam rather
than in the tests: a function with no clock has no clock to branch on. The
route owns the Redis round-trips; everything decidable is decided here.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable, Optional

from app.utils.feed_cache import feed_edition_member

#: How long a reader may keep browsing one edition. The design calls it a
#: "browsing lease": long enough to read a deck and come back from a phone call,
#: short enough that a pinned reader is never hours behind the slate. Prices are
#: NOT frozen for this window — only the order is — so the cost of the upper end
#: is staleness of MEMBERSHIP alone (a game that went live 20 minutes ago is not
#: spliced in), which is exactly the trade the ship asks for.
EDITION_LEASE_SECONDS = 1800

#: Response field carrying what happened to a pin request. Absent entirely when
#: the caller did not ask for one, so the unpinned payload shape is byte-for-byte
#: what it was before this module existed.
FEED_EDITION_STATUS_FIELD = "edition_status"

#: The caller asked for no edition. Never serialized (the field is omitted), but
#: returned by `apply_pinned_edition` so the route has one total function to
#: branch on instead of a None-check plus a status.
EDITION_STATUS_UNPINNED = "unpinned"

#: Served in the requested edition's order. The only status that reorders.
EDITION_STATUS_PINNED = "pinned"

#: No manifest under that token: the lease ran out, or the token was never ours.
#: Not an error — a reader who leaves a tab open overnight should get today's
#: feed, not a 410. The client restarts its list.
EDITION_STATUS_EXPIRED = "expired"

#: The manifest exists but was minted for a different BUILD — a different limit,
#: mode, sport, category, or a different principal. Distinct from `expired`
#: because it means "you are asking the wrong list", which is a client bug or an
#: auth change, and the two want different client behaviour and different alerts.
EDITION_STATUS_SUPERSEDED = "superseded"

#: A pinned member is gone from the current build. The edition cannot be honoured
#: without either a hole or a splice, so it is retired whole. See the header.
EDITION_STATUS_INVALIDATED = "invalidated"


def edition_policy_fingerprint(
    *,
    sport: Optional[str] = None,
    limit: int,
    include_events: bool = True,
    include_futures: bool = True,
    tags: Optional[str] = None,
    event_pct: Optional[float] = None,
    my_teams_only: bool = False,
    mode: Optional[str] = None,
    category: Optional[str] = None,
    principal: Optional[str] = None,
) -> str:
    """Identity of the BUILD an edition was minted from.

    Deliberately mirrors `feed_cache.feed_page_base_cache_key`'s parameter list,
    for the reason that docstring gives: every one of these is a build input, so
    two requests that disagree on any of them are looking at two different lists
    and an order pinned from one is meaningless against the other. `limit` is in
    here for the same reason it is in the base key — several display stages size
    their windows from it, so native (50) and web (20) are two lists, not two
    windows onto one.

    ``principal`` is the addition this file makes, and it is what the design
    means by "bound to the principal when personalized" and "auth change = new
    edition". A personalized list is not the anonymous one; pinning across a
    sign-in would serve one reader's ranking to another's session. Signing in
    therefore changes the fingerprint, the pin reads `superseded`, and the client
    starts a fresh edition — which is the correct visible behaviour, not a
    failure.

    Length-delimited for `category` and `principal` for the same reason
    `feed_response_cache_key` does it: two free-text values concatenated with a
    separator they may themselves contain can otherwise collide.
    """
    parts = (
        f"{sport or 'all'}:{limit}:{include_events}:{include_futures}:"
        f"{tags or ''}:{event_pct or ''}:{my_teams_only}:{mode or 'discover'}"
    )
    if category:
        parts = f"cat={len(category)}:{category}|{parts}"
    if principal:
        parts = f"prin={len(principal)}:{principal}|{parts}"
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]


def edition_manifest_cache_key(*, token: str, policy: str) -> str:
    """Redis key for one edition's ordered membership.

    Under the ``feed_cache:`` prefix on purpose, exactly as the page base is:
    `invalidate_feed_response_cache`'s ``feed_cache:*`` scan then clears
    manifests too. An invalidation that dropped the pages and left manifests
    behind would keep re-pinning the pre-invalidation ORDER onto the new build
    — the same trap the page-base comment warns about, one layer up.

    The policy is IN the key as well as in the body. In the key so two builds
    cannot share a manifest slot when their tokens happen to match (the token is
    64 bits over membership alone, and two different builds really can serve the
    same cards); in the body so a manifest read through any other path can still
    prove what it was minted for rather than trusting its own address.
    """
    return f"feed_cache:edition:{policy}:{token}"


def build_edition_manifest(
    items: Any, *, token: str, policy: str, built_at: float
) -> Optional[dict]:
    """The storable record of one ordered list.

    Membership only — ``feed_edition_member`` is reused rather than
    re-implemented so the manifest cannot drift from the token that names it.
    CERT-2309's lesson is baked into that helper (concept and tournament cards
    key on ``key``, not ``id``, or they all collapse to ``"?"``); a second
    identity function here would have to relearn it, and would learn it the same
    way — from a reader seeing two concepts swap places.

    Returns ``None`` for anything not worth storing: a non-list, the empty list
    (every empty feed is a refusal, not an edition — `feed_edition_token`'s own
    reasoning), or a list we cannot fully identify. That last one is the strict
    bit: if ANY member resolves to ``"?"`` we decline to mint the edition at all,
    because ``"?"`` is positional and two unidentified cards could swap under a
    pin without the manifest noticing — which would make the pin silently serve
    a different order, the precise failure it exists to prevent.
    """
    if not isinstance(items, list) or not items:
        return None
    members = [feed_edition_member(item) for item in items]
    if any(member == "?" for member in members):
        return None
    return {
        "token": token,
        "policy": policy,
        "members": members,
        "total": len(members),
        "built_at": float(built_at),
    }


def manifest_is_within_lease(
    manifest: Any, *, now: float, lease_seconds: float = EDITION_LEASE_SECONDS
) -> bool:
    """Whether a manifest is still inside its browsing lease.

    The Redis TTL is the primary expiry and this is the belt to its braces: a
    manifest can outlive its lease in a body read from a stale mirror, or
    through any future path that persists one. ``now`` is a parameter, not a
    clock read, so the boundary is testable from both sides without faking time.

    A manifest with no usable ``built_at`` is NOT treated as fresh. Defaulting an
    unknown age to zero is how a lease becomes unbounded, and the failure is
    invisible — the reader simply keeps an old order forever.
    """
    if not isinstance(manifest, dict):
        return False
    built_at = manifest.get("built_at")
    if not isinstance(built_at, (int, float)):
        return False
    return (now - float(built_at)) <= lease_seconds


def apply_pinned_edition(
    items: Any,
    manifest: Any,
    *,
    requested_policy: str,
    now: float,
    lease_seconds: float = EDITION_LEASE_SECONDS,
) -> tuple[Optional[list], str]:
    """Reorder the current build into a requested edition's order.

    Returns ``(ordered_items, status)``. ``ordered_items`` is non-``None`` only
    for :data:`EDITION_STATUS_PINNED`; every other status means "serve the
    current list and tell the client which of these happened", and the caller
    does not have to know which statuses those are.

    The returned list holds the CURRENT payload objects — same identities, same
    order as the manifest, live prices. It is the ORDER that is pinned; see the
    module header for why a payload snapshot would be the wrong product.

    Order of the checks matters and is the diagnostic quality of the field:
    policy is read before the lease so an account switch reports `superseded`
    rather than whichever expiry happens to fire first, and the lease is read
    before membership so a reader returning tomorrow gets `expired` rather than
    an `invalidated` that blames the slate for the clock.

    Not a bug: cards present in ``items`` but absent from the manifest are
    dropped from this serve. That is the "never splice a new order into page
    two" clause — a new card belongs to the next edition. ``total`` therefore
    comes from the manifest, which the caller must carry through, or the scroll
    would run past the end of the pinned list.
    """
    if not isinstance(items, list):
        return None, EDITION_STATUS_EXPIRED
    if not isinstance(manifest, dict):
        return None, EDITION_STATUS_EXPIRED
    if manifest.get("policy") != requested_policy:
        return None, EDITION_STATUS_SUPERSEDED
    if not manifest_is_within_lease(manifest, now=now, lease_seconds=lease_seconds):
        return None, EDITION_STATUS_EXPIRED

    members = manifest.get("members")
    if not isinstance(members, list) or not members:
        return None, EDITION_STATUS_EXPIRED

    index: dict[str, Any] = {}
    for item in items:
        ident = feed_edition_member(item)
        # First occurrence wins. A duplicate identity in one build is already a
        # defect elsewhere; resolving it to the earlier card keeps this function
        # deterministic instead of order-of-iteration dependent.
        if ident != "?" and ident not in index:
            index[ident] = item

    ordered: list = []
    for member in members:
        hit = index.get(member)
        if hit is None:
            return None, EDITION_STATUS_INVALIDATED
        ordered.append(hit)
    return ordered, EDITION_STATUS_PINNED


def pinned_member_identities(items: Iterable[Any]) -> list[str]:
    """Identities of a list, in order — the manifest's view of a build.

    Exposed for the route's observability and for tests that want to assert an
    ordering without reaching into a private helper.
    """
    return [feed_edition_member(item) for item in items]
