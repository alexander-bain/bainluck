"""Generic Event Concept framework — slice 1 (#999).

An "event concept" is a real-world competition (golf tournament, tennis slam,
UFC card, F1 GP, awards ceremony) that owns a set of markets across sources. This
module is the DOMAIN-PARAMETERIZED core: a small adapter interface + registry +
event-key parsing. Each domain provides an adapter that returns the SAME generic
envelope, so `/api/event/{key}` + the `/event/[key]` page render any domain.

Slice 1 ships the GOLF adapter, which delegates to the existing, proven
`routes/golf.py` tournament-detail aggregation (golf.py stays untouched — the
parity bar) and maps its output into the generic envelope. Tennis / UFC / F1 /
awards adapters (design §5, §6) are future slices: each implements
`build_event()` to produce the same envelope shape documented below.

Envelope shape (domain-agnostic — every adapter returns this):
    {
      "event":   {key, domain, name, status, start_date, end_date, venue,
                  location, is_major},
      "primary": {kind, label, competitors, evolution_market_id}
                 # kind flexes: "winner_field" (golf/tennis/F1-championship —
                 # a leaderboard/field) | "co_equal_list" (UFC card, awards
                 # categories — no single overall winner). Design §3.4 / §5 / §6.
      "sections": [...]   # market groups (winner / top-N / props), ordered
      "children": [...]   # matchup / prop / progression child markets
      "movers":   [...]   # biggest 24h movers within the event
    }
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession


def parse_event_key(key: str) -> tuple[str, str]:
    """Parse an event key into (domain, slug).

    Canonical form: ``event:<domain>:<slug>`` (e.g. ``event:golf:2026-masters``,
    ``event:tennis:wimbledon-2026``). Also tolerates ``<domain>:<slug>``. A bare
    slug is treated as golf (parity convenience for slice 1). The slug may itself
    contain hyphens; only the domain segment is split off.
    """
    parts = key.split(":")
    if len(parts) >= 3 and parts[0] == "event":
        return parts[1], ":".join(parts[2:])
    if len(parts) == 2:
        return parts[0], parts[1]
    return "golf", key


@runtime_checkable
class EventConceptAdapter(Protocol):
    """A per-domain adapter. Implement `domain` + `build_event`.

    `build_event(slug, db)` returns the generic envelope (see module docstring)
    for the event, or None if the event doesn't exist. Future domains (tennis,
    ufc, f1, awards) add an adapter and register it — no route/frontend change.
    """

    domain: str

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None: ...


_ADAPTERS: dict[str, EventConceptAdapter] = {}


def register_adapter(adapter: EventConceptAdapter) -> None:
    _ADAPTERS[adapter.domain] = adapter


def get_adapter(domain: str) -> EventConceptAdapter | None:
    return _ADAPTERS.get(domain)


def registered_domains() -> list[str]:
    return sorted(_ADAPTERS.keys())


# ---------------------------------------------------------------------------
# Golf adapter — the reference implementation (delegates to routes/golf.py).
# ---------------------------------------------------------------------------

def _golf_status(tournament: dict) -> str:
    """Normalize golf's schedule_status into upcoming/live/settled."""
    raw = (tournament.get("schedule_status") or "").lower()
    if raw in ("in_progress", "live", "active"):
        return "live"
    if raw in ("completed", "closed", "resolved", "final", "settled"):
        return "settled"
    return "upcoming"


def golf_detail_to_envelope(key: str, slug: str, data: dict) -> dict:
    """Map get_golf_tournament()'s output into the generic event envelope.

    Pure — unit-tested. Preserves the golf data (parity) under generic keys so the
    frontend renders domain-agnostically."""
    t = data.get("tournament", {}) or {}
    return {
        "event": {
            "key": key if key.startswith("event:") else f"event:golf:{slug}",
            "domain": "golf",
            "name": t.get("name"),
            "status": _golf_status(t),
            "start_date": t.get("start_date"),
            "end_date": t.get("end_date"),
            "venue": t.get("venue"),
            "location": t.get("location"),
            "is_major": bool(t.get("is_major", False)),
        },
        "primary": {
            "kind": "winner_field",  # golf is always a winner-field (leaderboard)
            "label": "Winner",
            "competitors": data.get("golfers", []) or [],
            "evolution_market_id": data.get("evolution_market_id"),
        },
        "sections": data.get("markets", []) or [],
        "children": data.get("related_futures", []) or [],
        "movers": data.get("biggest_movers", []) or [],
    }


class GolfEventAdapter:
    domain = "golf"

    async def build_event(self, slug: str, db: AsyncSession) -> dict | None:
        # Lazy import — golf.py pulls a large dependency graph; importing at call
        # time keeps this module (and the route) cheap and circular-import safe.
        from fastapi import HTTPException
        from app.routes.golf import get_golf_tournament

        try:
            data = await get_golf_tournament(slug=slug, db=db)
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise
        key = f"event:golf:{slug}"
        return golf_detail_to_envelope(key, slug, data)


register_adapter(GolfEventAdapter())

# Tennis adapter (slice 2, #999) — separate module; registered here so the
# registry stays the single hub. Its DB work is lazy-imported inside build_event.
from app.utils.event_tennis import TennisEventAdapter  # noqa: E402

register_adapter(TennisEventAdapter())
