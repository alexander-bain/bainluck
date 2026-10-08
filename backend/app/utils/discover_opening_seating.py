"""#5105 — opening seating: an ordinary live event does not take a first-ten seat
for being live (Alex, Option A, 2026-10-08).

The ruling, in his words: "A live event with no major, marquee or playoff sign
does not take a first-ten seat on being live. It competes from seat 11 down.
Scores stay untouched. This is a seating test, not a scoring change."

This module is the PURE half: given a finished Discover deck (after every
ordering writer, before pagination) and the clock the deck was composed at, it
returns the same cards in an order whose first :data:`OPENING_SEATS` hold no
RESTRICTED card, or an explicit refusal with the input order unchanged. It does
no I/O, reads no clock of its own, never mutates a card, never drops or adds a
card, and never touches a score, ``_rank_score``, probability or provenance
field — the output holds the very same dict objects.

Nothing in production calls this. ``routes/feed.py`` is unchanged; the only
caller is the offline display replay's opt-in arm
(``discover_display_replay.replay_capture(..., opening_seating=True)``).

What RESTRICTED means
---------------------

A card is restricted when BOTH hold:

1. It is RELIABLY live at ``now`` — typed lifecycle evidence, never a headline,
   a "Live" badge or price movement:

   * ``event``: ``data.status == "live"``. A typed ``commence_time`` later than
     ``now`` contradicts it (a CONFLICT, not live).
   * ``tournament``: no ``champion``, and either an ASSERTED schedule status
     (``event_concept._golf_status`` — the shared classifier that returns
     "live" only from ``schedule_status``) or a published play window that
     covers the whole last calendar day (``start_date <= now < end_date + 1
     day`` — the reviewed #5105 contract of ``ae529f5423``, not the capture-era
     ``end_date + 12h`` tail, which retires a final round at noon UTC). The
     served function's movement arm — any golfer's 24h movement — is
     deliberately NOT used: on the October 4 capture it is the only reason the
     undated Korn Ferry card reads "Live". An asserted status whose own dates
     say not-yet-started or long-over is a CONFLICT.
   * ``concept``: ``data.status == "live"``; a typed ``start_date`` later than
     ``now`` is a CONFLICT (each concept domain derives "live" from its own
     window, e.g. F1's four hours of lights-out lead, which the start contradicts).

   Missing or unparseable evidence is UNKNOWN, and unknown is not live: the
   card keeps ordinary handling. Unknowns are reported, never counted as live.
   A CONFLICT is never counted as live OR as not-live: see "Conflicts" below.

2. It carries no exemption. Exempt is a POSITIVE typed sign only:
   ``data.is_major is True``, ``data.is_marquee is True``, or BOTH event tags
   ``tier:1`` and ``importance:playoff``. Either tag alone is not an exemption,
   and an absent field never supplies one.

``futures`` cards are never restricted — a futures card without tournament
flags is not a live event.

Groups
------

Grouping is out of scope, so a group may not launder a child's restriction into
an opening seat. A ``bundle`` whose ``data.items`` hold a restricted child, or a
child of a kind this module does not know, and a ``collection`` whose own status
reads live or whose ``matched_event_ids`` name a restricted event card in the
deck, make the whole call UNSUPPORTED (input unchanged). Groups with nothing to
launder are ordinary cards.

Order
-----

When restricted cards sit in the opening and at least :data:`OPENING_SEATS`
cards are eligible, the opening becomes the first :data:`OPENING_SEATS`
eligible cards in their existing relative order — the eligible occupants keep
their order (closing up over the vacated seats) and the earliest eligible tail
cards fill the remaining seats — and every other card follows in its existing
relative order. So the eligible subsequence and the restricted subsequence of
the deck are both unchanged; the displaced cards lead the tail at seat 11.
Nothing is re-ranked. (Seating a tail card INTO the vacated seat in place was
considered and rejected: it lifts, say, seat 40 above seat 3 — a re-rank.)

Conflicts
---------

A direct ``event``/``tournament``/``concept`` card whose lifecycle is CONFLICT
and that carries no exemption is one this module cannot judge: its own typed
fields say both live and not live, so the arm cannot show the opening holds no
ordinary live event. If such a card would sit in the CANDIDATE opening — the
first :data:`OPENING_SEATS` cards of the deck the stable move would return,
which includes a conflicted tail card the move would promote into a vacated
seat — the whole call is UNSUPPORTED with the input order unchanged and the
conflicted identities named in ``refused_conflicts``. It is never skipped in
favour of the next card, demoted, rescored, or treated as live or settled;
which lifecycle source should win is not this module's decision. A conflict
outside the candidate opening does not refuse an otherwise supported opening.
An exempt conflict keeps its seat exactly as an exempt live card does.

When fewer than :data:`OPENING_SEATS` cards are eligible and a restricted card
would occupy the opening, the outcome is UNRESOLVED_SPARSE_SUPPLY with the
order unchanged. Sparse-supply policy is Alex's to decide; this never relaxes
the rule, drops a card or inserts a blank. A short deck with no restricted card
in it is simply compliant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

#: The opening Alex's ruling protects: seats 1–10 (0-based positions 0–9).
OPENING_SEATS = 10

#: How far a tournament's play window runs past ``end_date``: published play
#: dates name calendar days, not finish instants, so the window covers the whole
#: last day and is EXCLUSIVE of the following midnight (``now < end + 1 day``).
#: The reviewed #5105 contract (``ae529f5423``); the capture-era 12h tail
#: retired the final round at noon UTC.
TOURNAMENT_END_TAIL = timedelta(days=1)

#: The event status that means in play (``routes/event_stream.LIVE_STATUSES``).
EVENT_LIVE_STATUSES = frozenset({"live"})
CONCEPT_LIVE_STATUSES = frozenset({"live"})
#: Collection statuses that would put live games inside a group whose members
#: this module cannot all see.
COLLECTION_LIVE_STATUSES = frozenset({"live", "in_progress", "in-progress", "active"})

EXEMPT_TAGS = frozenset({"tier:1", "importance:playoff"})

#: Card kinds this module can classify. Anything else refuses.
LIFECYCLE_KINDS = frozenset({"event", "tournament", "concept"})
GROUP_KINDS = frozenset({"bundle", "collection"})
KNOWN_KINDS = LIFECYCLE_KINDS | GROUP_KINDS | {"futures"}

# Lifecycle verdicts.
LIVE = "live"
NOT_LIVE = "not_live"
UNKNOWN = "unknown"
CONFLICT = "conflict"

# Outcome statuses.
APPLIED = "applied"
COMPLIANT = "compliant"
UNRESOLVED_SPARSE_SUPPLY = "unresolved_sparse_supply"
UNSUPPORTED = "unsupported"


@dataclass
class CardSeating:
    """What this module concluded about one card, and from which fields."""

    identity: str
    kind: Any
    lifecycle: Optional[str] = None
    lifecycle_evidence: dict = field(default_factory=dict)
    exempt_by: list = field(default_factory=list)
    restricted: bool = False

    def as_dict(self) -> dict:
        return {
            "identity": self.identity,
            "kind": self.kind,
            "lifecycle": self.lifecycle,
            "lifecycle_evidence": self.lifecycle_evidence,
            "exempt_by": list(self.exempt_by),
            "restricted": self.restricted,
        }


@dataclass
class OpeningSeatingOutcome:
    """``items`` is a NEW list holding the input's own card objects. For any
    status other than :data:`APPLIED` it is the input order, unchanged."""

    status: str
    items: list
    detail: str = ""
    #: identities, in output order, of restricted cards moved out of the opening
    displaced: list = field(default_factory=list)
    #: identities, in output order, of tail cards that entered the opening
    entered: list = field(default_factory=list)
    #: per-card conclusions, input order (empty when refused before classifying)
    cards: list = field(default_factory=list)
    #: identities, in candidate-opening order, of unexempt CONFLICT cards that
    #: made the call UNSUPPORTED (empty for every other outcome)
    refused_conflicts: list = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.status == APPLIED

    def summary(self) -> dict:
        def pick(pred):
            return [c.as_dict() for c in self.cards if pred(c)]

        return {
            "status": self.status,
            "detail": self.detail,
            "opening_seats": OPENING_SEATS,
            "displaced": list(self.displaced),
            "entered": list(self.entered),
            "refused_conflicts": list(self.refused_conflicts),
            "restricted": pick(lambda c: c.restricted),
            "exempt_live": pick(lambda c: c.lifecycle == LIVE and c.exempt_by),
            "conflicts": pick(lambda c: c.lifecycle == CONFLICT),
            "unknown_lifecycle": pick(lambda c: c.lifecycle == UNKNOWN),
        }


def _identity(card: Any) -> str:
    from app.utils.feed_cache import feed_edition_member

    return feed_edition_member(card)


def _parse(value: Any) -> Optional[datetime]:
    """An ISO timestamp as an aware UTC datetime; naive means UTC (the served
    tournament arm's own reading). Anything unparseable is ``None``."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _event_lifecycle(data: dict, now: datetime) -> tuple[str, dict]:
    status = data.get("status")
    start = _parse(data.get("commence_time"))
    evidence = {"status": status, "commence_time": data.get("commence_time")}
    if status not in EVENT_LIVE_STATUSES:
        return (NOT_LIVE if isinstance(status, str) and status else UNKNOWN), evidence
    if start is not None and start > now:
        return CONFLICT, evidence
    return LIVE, evidence


def _tournament_lifecycle(data: dict, now: datetime) -> tuple[str, dict]:
    from app.utils.event_concept import _golf_status

    evidence = {
        "champion": data.get("champion"),
        "schedule_status": data.get("schedule_status"),
        "start_date": data.get("start_date"),
        "end_date": data.get("end_date"),
    }
    if data.get("champion"):
        return NOT_LIVE, evidence
    # The shared classifier fed ONLY the asserted status: "live" / "settled" when
    # the schedule says so, "upcoming" when it asserts neither. Its own date
    # fallbacks never run here — the dates are read below, as a calendar-day
    # play window.
    asserted = _golf_status({"schedule_status": data.get("schedule_status")}, now)
    start, end = _parse(data.get("start_date")), _parse(data.get("end_date"))
    dated: Optional[str] = None
    if start is not None and end is not None:
        if now < start:
            dated = "future"
        elif now < end + TOURNAMENT_END_TAIL:
            dated = "live"
        else:
            dated = "past"
    evidence["asserted"] = asserted
    evidence["dated"] = dated
    if asserted == "live":
        return (CONFLICT if dated in ("future", "past") else LIVE), evidence
    if asserted == "settled":
        return (CONFLICT if dated == "live" else NOT_LIVE), evidence
    if dated == "live":
        return LIVE, evidence
    if dated in ("future", "past"):
        return NOT_LIVE, evidence
    return UNKNOWN, evidence


def _concept_lifecycle(data: dict, now: datetime) -> tuple[str, dict]:
    status = data.get("status")
    start = _parse(data.get("start_date"))
    evidence = {"status": status, "start_date": data.get("start_date")}
    if status not in CONCEPT_LIVE_STATUSES:
        return (NOT_LIVE if isinstance(status, str) and status else UNKNOWN), evidence
    if start is not None and start > now:
        return CONFLICT, evidence
    return LIVE, evidence


_LIFECYCLE = {
    "event": _event_lifecycle,
    "tournament": _tournament_lifecycle,
    "concept": _concept_lifecycle,
}


def _exemptions(data: dict) -> list[str]:
    signs = []
    if data.get("is_major") is True:
        signs.append("is_major")
    if data.get("is_marquee") is True:
        signs.append("is_marquee")
    tags = data.get("event_tags")
    if isinstance(tags, (list, tuple)) and EXEMPT_TAGS <= set(tags):
        signs.append("tier:1+importance:playoff")
    return signs


def classify_card(card: Any, *, now: datetime) -> CardSeating:
    """One card's lifecycle, exemptions and restriction. Groups and futures are
    never restricted HERE; :func:`seat_opening` checks a group's members."""
    kind = card.get("type") if isinstance(card, dict) else None
    seating = CardSeating(identity=_identity(card) if isinstance(card, dict) else "?", kind=kind)
    if kind not in LIFECYCLE_KINDS:
        return seating
    data = card.get("data")
    if not isinstance(data, dict):
        seating.lifecycle = UNKNOWN
        return seating
    seating.lifecycle, seating.lifecycle_evidence = _LIFECYCLE[kind](data, now)
    seating.exempt_by = _exemptions(data)
    seating.restricted = seating.lifecycle == LIVE and not seating.exempt_by
    return seating


def _group_refusal(
    card: dict, by_event_id: dict, *, now: datetime
) -> Optional[str]:
    """Why a group card could launder a restriction, or ``None``."""
    ident = _identity(card)
    data = card.get("data")
    if not isinstance(data, dict):
        return f"{ident}: group card without a data object"
    if card["type"] == "bundle":
        children = data.get("items")
        if not isinstance(children, list):
            return f"{ident}: bundle without an items list"
        for index, child in enumerate(children):
            kind = child.get("type") if isinstance(child, dict) else None
            if kind not in KNOWN_KINDS or kind in GROUP_KINDS:
                return f"{ident}: member {index} has unsupported kind {kind!r}"
            if classify_card(child, now=now).restricted:
                return (
                    f"{ident}: member {_identity(child)} is an ordinary live "
                    "event; grouped membership is not supported by opening seating"
                )
        return None
    status = data.get("status")
    if isinstance(status, str) and status.lower() in COLLECTION_LIVE_STATUSES:
        return (
            f"{ident}: collection status {status!r} holds live games this "
            "module cannot all see"
        )
    for event_id in data.get("matched_event_ids") or ():
        member = by_event_id.get(event_id)
        if member is not None and member.restricted:
            return (
                f"{ident}: matched event {member.identity} is an ordinary live "
                "event; grouped membership is not supported by opening seating"
            )
    return None


def seat_opening(items: list, *, now: datetime) -> OpeningSeatingOutcome:
    """Apply the opening-seat restriction to one finished deck. See the module
    docstring for the rule; ``now`` is the clock the deck was composed at and
    must be timezone-aware."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("seat_opening needs an explicit timezone-aware clock")
    unchanged = list(items)

    def refuse(status: str, detail: str, cards: list) -> OpeningSeatingOutcome:
        return OpeningSeatingOutcome(status=status, items=unchanged, detail=detail, cards=cards)

    cards: list[CardSeating] = []
    seen: set[str] = set()
    for index, card in enumerate(items):
        kind = card.get("type") if isinstance(card, dict) else None
        if kind not in KNOWN_KINDS:
            return refuse(UNSUPPORTED, f"[{index}]: card kind {kind!r} is not supported", cards)
        seating = classify_card(card, now=now)
        if seating.identity == "?" or seating.identity in seen:
            return refuse(
                UNSUPPORTED,
                f"[{index}]: identity {seating.identity!r} is missing or duplicated",
                cards,
            )
        seen.add(seating.identity)
        cards.append(seating)

    by_event_id = {
        card["data"].get("id"): seating
        for card, seating in zip(items, cards)
        if seating.kind == "event" and isinstance(card.get("data"), dict)
    }
    for card, seating in zip(items, cards):
        if seating.kind in GROUP_KINDS:
            reason = _group_refusal(card, by_event_id, now=now)
            if reason is not None:
                return refuse(UNSUPPORTED, reason, cards)

    restricted_in_opening = any(c.restricted for c in cards[:OPENING_SEATS])
    eligible = [i for i, c in enumerate(cards) if not c.restricted]
    if restricted_in_opening and len(eligible) < OPENING_SEATS:
        return refuse(
            UNRESOLVED_SPARSE_SUPPLY,
            f"{len(eligible)} eligible card(s) for {OPENING_SEATS} opening seats; "
            "sparse-supply behaviour is undecided, order left unchanged",
            cards,
        )

    # The candidate opening: the deck's own first seats when nothing restricted
    # sits there (they are then exactly the first eligible cards), otherwise the
    # first eligible cards the stable move would seat.
    opening = eligible[:OPENING_SEATS]
    conflicted = [
        i for i in opening if cards[i].lifecycle == CONFLICT and not cards[i].exempt_by
    ]
    if conflicted:
        outcome = refuse(
            UNSUPPORTED,
            "unexempt lifecycle conflict(s) in the candidate opening: "
            + ", ".join(f"{cards[i].identity} (input seat {i + 1})" for i in conflicted)
            + "; their typed fields say both live and not live, so the opening "
            "cannot be shown free of ordinary live events",
            cards,
        )
        outcome.refused_conflicts = [cards[i].identity for i in conflicted]
        return outcome
    if not restricted_in_opening:
        return refuse(COMPLIANT, "no restricted card in the opening", cards)

    chosen = set(opening)
    order = opening + [i for i in range(len(items)) if i not in chosen]
    return OpeningSeatingOutcome(
        status=APPLIED,
        items=[items[i] for i in order],
        detail=f"{sum(c.restricted for c in cards[:OPENING_SEATS])} restricted card(s) left the opening",
        displaced=[cards[i].identity for i in order[OPENING_SEATS:] if i < OPENING_SEATS],
        entered=[cards[i].identity for i in opening if i >= OPENING_SEATS],
        cards=cards,
    )
