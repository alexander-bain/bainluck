"""#5105 — a pinned Discover opening expires and recomposes when it stops being
compliant (Alex, 2026-10-08: "expire and recompose").

The browsing edition (#5102, ``feed_editions``) pins ORDER so a reader keeps
their place for ~30 minutes. Opening seating (#5105 Option A,
``discover_opening_seating``) keeps an unexempt ordinary-live card out of the
first ten seats. The two meet when a card that was eligible at mint becomes
ordinary-live inside the pinned opening: holding the pin would serve exactly
the opening the seating ruling forbids, and patching that one card out would be
a splice into a pinned page — the thing the edition contract exists to prevent.
Alex chose: the pin EXPIRES AS A WHOLE and a compliant edition is composed from
the CURRENT full deck.

This module is that composition and nothing else. It reuses
:func:`feed_editions.apply_pinned_edition` for policy → lease → membership (and
the section-aware read opt-in), :func:`discover_opening_seating.seat_opening`
for every lifecycle/exemption/conflict/group judgement, and
:func:`feed_cache.feed_edition_token` for the replacement token. It has no pin
logic, no classifier and no token scheme of its own.

The seam is the FINAL FULL deck — after collection assembly, before slicing.
Like both modules it composes, it is pure: no clock of its own, no I/O, never
mutates a card, never touches a score or probability; output lists hold the
input's own card objects. Nothing calls it yet (see the #5105 return for the
route/cache/client integration it still needs).

The transition contract
-----------------------

``compose_opening_edition(items, manifest, requested_token=..., ...)``:

* No edition requested (``requested_token is None``): the current deck is
  seated → :data:`COMPOSED` with ``edition_status`` ``unpinned``.
* Requested, and ``apply_pinned_edition`` does not pin (wrong policy or legacy
  layout → ``superseded``; missing/out-of-lease/malformed → ``expired``; a
  member gone → ``invalidated``): those statuses are preserved verbatim — no
  new eligibility condition is involved — and the current deck is seated as the
  replacement → :data:`COMPOSED`, ``retire_requested`` and
  ``restart_at_page_one`` set.
* Requested and pinnable: the REQUESTED PINNED ORDER (manifest order, current
  bodies) is judged by ``seat_opening`` at ``now``. It is compliant exactly
  when seating would leave its identity order unchanged AND its continuation
  boundary equals the boundary the manifest recorded (``None`` and ``0`` are
  different boundaries). Compliant → :data:`HELD`: the pinned order, current
  bodies, the recorded boundary and the requested token. A moved current
  ranking or a new card outside the membership never matters here — only the
  pinned membership is judged. Not compliant → the pin is ``expired`` whole
  (``seating_expiry`` names why: ``opening_order`` or ``section_boundary``) and
  the FULL current deck is seated as the replacement — fresh entrants
  included, never a reseat of the old membership.
* ``seat_opening`` refuses (an unexempt lifecycle conflict in the candidate
  opening, a group that could launder a live child, an unknown kind, a missing
  or duplicated identity): :data:`UNSUPPORTED`, ``usable`` False, ``items`` is
  the input order unchanged and there is no token or manifest. A refusal while
  judging a pin leaves ``edition_status`` ``None`` — the pin was neither shown
  compliant nor shown expired; a refusal while composing a replacement keeps
  the requested edition's own status (e.g. ``expired``) beside ``usable``
  False, so "expired, with a usable deck" and "no usable deck" never look alike.

The boundary is never inferred from ``OpeningSeatingOutcome.changed``: a thin
deck reports ``sparse_continuation`` (changed) even when its order is already
partitioned. It is compared as a value.

Section-awareness is opt-in on both halves: the requested policy must be a
fingerprint minted with ``opening_seating=True``, and the manifest must carry a
valid ``layout`` (``apply_pinned_edition(sections=True)`` refuses a legacy one
as ``superseded``). A replacement manifest is minted section-aware with
``built_at = now`` under the requested policy; the old manifest is never
touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from app.utils.discover_opening_seating import (
    UNSUPPORTED as SEATING_UNSUPPORTED,
    OpeningSeatingOutcome,
    seat_opening,
)
from app.utils.feed_cache import feed_edition_member, feed_edition_token
from app.utils.feed_editions import (
    EDITION_LEASE_SECONDS,
    EDITION_STATUS_EXPIRED,
    EDITION_STATUS_PINNED,
    EDITION_STATUS_UNPINNED,
    apply_pinned_edition,
    build_edition_manifest,
    manifest_section_layout,
)

# Composition outcomes.
HELD = "held"
COMPOSED = "composed"
UNSUPPORTED = "unsupported"

# Why a pinnable edition expired under the current seating.
SEATING_EXPIRY_OPENING_ORDER = "opening_order"
SEATING_EXPIRY_SECTION_BOUNDARY = "section_boundary"


@dataclass
class OpeningEditionOutcome:
    """What a future caller needs to serve, retire and restart honestly.

    ``items`` is a NEW list of the input's own card objects: the deck to serve
    when ``usable``, otherwise the input order unchanged (never a deck to
    serve). ``continuation_start`` and ``token`` describe ``items`` only when
    ``usable``.
    """

    status: str
    usable: bool
    items: list
    #: the requested edition's fate in the existing vocabulary — ``unpinned``,
    #: ``pinned``, ``expired``, ``superseded``, ``invalidated`` — or ``None``
    #: when a pin could be judged neither compliant nor expired (refusal)
    edition_status: Optional[str]
    #: ``opening_order`` / ``section_boundary`` when a pinnable edition expired
    #: under the current seating; ``None`` otherwise
    seating_expiry: Optional[str] = None
    #: full-deck position of the ordinary-live continuation in ``items``
    continuation_start: Optional[int] = None
    #: edition token of ``items`` + ``continuation_start`` (the requested token
    #: when HELD; a fresh ``feed_edition_token`` when COMPOSED)
    token: Optional[str] = None
    #: the requested token, echoed whenever it was requested
    requested_token: Optional[str] = None
    #: the requested edition must not be served again; its offsets mean nothing
    retire_requested: bool = False
    #: a fresh edition: the caller serves it from page one. This module never
    #: re-slices an old offset onto it and picks no client retry mechanics.
    restart_at_page_one: bool = False
    #: section-aware manifest for a COMPOSED edition (``None`` otherwise, or if
    #: the deck could not be identified well enough to mint one)
    manifest: Optional[dict] = None
    #: ``seat_opening`` over the requested pinned order (``None`` if no pin was
    #: judged)
    pin_seating: Optional[OpeningSeatingOutcome] = None
    #: ``seat_opening`` over the full current deck (``None`` when HELD)
    deck_seating: Optional[OpeningSeatingOutcome] = None
    detail: str = ""

    def summary(self) -> dict:
        return {
            "status": self.status,
            "usable": self.usable,
            "edition_status": self.edition_status,
            "seating_expiry": self.seating_expiry,
            "continuation_start": self.continuation_start,
            "token": self.token,
            "requested_token": self.requested_token,
            "retire_requested": self.retire_requested,
            "restart_at_page_one": self.restart_at_page_one,
            "total": len(self.items) if self.usable else None,
            "pin_seating": self.pin_seating.summary() if self.pin_seating else None,
            "deck_seating": self.deck_seating.summary() if self.deck_seating else None,
            "detail": self.detail,
        }


def _identities(items: list) -> list[str]:
    return [feed_edition_member(item) for item in items]


def compose_opening_edition(
    items: list,
    manifest: Any,
    *,
    requested_token: Optional[str],
    requested_policy: str,
    now: datetime,
    lease_seconds: float = EDITION_LEASE_SECONDS,
) -> OpeningEditionOutcome:
    """Serve, hold or retire-and-recompose one section-aware Discover edition.

    ``items`` is the FINAL full current deck; ``manifest`` the stored record for
    ``requested_token`` (``None`` when absent). ``requested_policy`` must be an
    ``edition_policy_fingerprint(..., opening_seating=True)``. ``now`` is the
    one timezone-aware clock for both the lease and the lifecycle judgement.
    See the module docstring for the contract.
    """
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError(
            "compose_opening_edition needs an explicit timezone-aware clock"
        )
    if not isinstance(items, list):
        raise ValueError("compose_opening_edition needs the full deck as a list")
    epoch = now.timestamp()

    requested = requested_token is not None
    edition_status = EDITION_STATUS_UNPINNED
    pin_seating: Optional[OpeningSeatingOutcome] = None
    seating_expiry: Optional[str] = None
    detail = ""

    if requested:
        pinned, edition_status = apply_pinned_edition(
            items,
            manifest,
            requested_policy=requested_policy,
            now=epoch,
            lease_seconds=lease_seconds,
            sections=True,
        )
        if edition_status == EDITION_STATUS_PINNED and pinned is not None:
            _, pinned_start = manifest_section_layout(manifest)
            # The manifest must be the edition it is filed under: its own token,
            # and the token its membership + boundary re-derive. A disagreeing
            # record is malformed, which this vocabulary calls ``expired``.
            if (
                manifest.get("token") != requested_token
                or feed_edition_token(pinned, pinned_start) != requested_token
            ):
                edition_status = EDITION_STATUS_EXPIRED
                detail = "manifest does not re-derive the requested token"
            else:
                pin_seating = seat_opening(pinned, now=now)
                if pin_seating.status == SEATING_UNSUPPORTED:
                    return OpeningEditionOutcome(
                        status=UNSUPPORTED,
                        usable=False,
                        items=list(items),
                        edition_status=None,
                        requested_token=requested_token,
                        retire_requested=True,
                        pin_seating=pin_seating,
                        detail="the requested pinned order cannot be judged: "
                        + pin_seating.detail,
                    )
                same_order = _identities(pin_seating.items) == _identities(pinned)
                same_boundary = pin_seating.continuation_start == pinned_start
                if same_order and same_boundary:
                    return OpeningEditionOutcome(
                        status=HELD,
                        usable=True,
                        items=list(pinned),
                        edition_status=EDITION_STATUS_PINNED,
                        continuation_start=pinned_start,
                        token=requested_token,
                        requested_token=requested_token,
                        pin_seating=pin_seating,
                        detail="the requested pinned order is still seating-compliant",
                    )
                edition_status = EDITION_STATUS_EXPIRED
                if not same_order:
                    seating_expiry = SEATING_EXPIRY_OPENING_ORDER
                    detail = (
                        "the pinned opening is no longer compliant: "
                        + pin_seating.detail
                    )
                else:
                    seating_expiry = SEATING_EXPIRY_SECTION_BOUNDARY
                    detail = (
                        f"the pinned section boundary {pinned_start!r} is now "
                        f"{pin_seating.continuation_start!r}"
                    )

    deck_seating = seat_opening(items, now=now)
    retire = requested
    if deck_seating.status == SEATING_UNSUPPORTED:
        return OpeningEditionOutcome(
            status=UNSUPPORTED,
            usable=False,
            items=list(items),
            edition_status=edition_status,
            seating_expiry=seating_expiry,
            requested_token=requested_token,
            retire_requested=retire,
            pin_seating=pin_seating,
            deck_seating=deck_seating,
            detail="no usable replacement deck: " + deck_seating.detail,
        )
    deck = deck_seating.items
    start = deck_seating.continuation_start
    token = feed_edition_token(deck, start)
    replacement = (
        build_edition_manifest(
            deck,
            token=token,
            policy=requested_policy,
            built_at=epoch,
            sections=True,
            continuation_start=start,
        )
        if token is not None
        else None
    )
    return OpeningEditionOutcome(
        status=COMPOSED,
        usable=True,
        items=deck,
        edition_status=edition_status,
        seating_expiry=seating_expiry,
        continuation_start=start,
        token=token,
        requested_token=requested_token,
        retire_requested=retire,
        restart_at_page_one=retire,
        manifest=replacement,
        pin_seating=pin_seating,
        deck_seating=deck_seating,
        detail=(detail + "; " if detail else "") + "composed: " + deck_seating.detail,
    )
