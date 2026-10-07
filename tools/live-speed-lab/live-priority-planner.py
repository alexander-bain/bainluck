"""#10678 lab — order the reviewed #10655 phases live-first. NOT application code.

A pure wrapper around the pinned #10655 planner
(`app.tasks.kalshi_ws.linked_first_phases` at eaa8027a59). It never builds a
phase of its own: it takes the planner's phases exactly as returned and only
re-orders them, so every rule the planner owns — whole markets, complement
pairs, siblings without a buffered tick, transitive connected-event
components, the unknown-membership single transaction and the pending-refresh
all-games fallback — holds by construction.

Tiers, stable within each (Python's sort is stable, so the planner's
first-seen order survives inside a tier):

  0  a game component touching ANY event in ``live_event_ids``
  1  any other game component (scheduled / unknown status)
  2  the unrelated phase (no linked event) — already last in the planner

``live_event_ids`` is a frozen set the caller snapshots ONCE per flush. The
wrapper copies it on entry, so a status change during the flush can only take
effect on the next call. An empty set is the baseline plan, byte-for-byte.
"""
from __future__ import annotations

from typing import Iterable

LIVE, SCHEDULED, UNLINKED = 0, 1, 2


def component_events(phase, market_id_by_outcome, event_id_by_outcome):
    """Every event connected to ``phase``'s markets through the known map.

    Walks market -> event -> market over the WHOLE subscription map (not just
    the buffered rows), the same graph the #10655 planner unions, so a live
    event reached only through an un-ticked sibling still marks the phase.
    """
    events_by_market: dict = {}
    markets_by_event: dict = {}
    for oid, event in event_id_by_outcome.items():
        market = market_id_by_outcome.get(oid)
        if event is None or market is None:
            continue
        events_by_market.setdefault(market, set()).add(event)
        markets_by_event.setdefault(event, set()).add(market)
    seen_markets: set = set()
    seen_events: set = set()
    stack = [market_id_by_outcome.get(oid) for oid in phase]
    while stack:
        market = stack.pop()
        if market is None or market in seen_markets:
            continue
        seen_markets.add(market)
        for event in events_by_market.get(market, ()):
            if event not in seen_events:
                seen_events.add(event)
                stack.extend(markets_by_event[event])
    return frozenset(seen_events)


def phase_tier(phase, market_id_by_outcome, event_id_by_outcome, live):
    events = component_events(phase, market_id_by_outcome, event_id_by_outcome)
    if not events:
        return UNLINKED
    return LIVE if events & live else SCHEDULED


def live_first_phases(
    batch,
    market_id_by_outcome,
    event_id_by_outcome,
    pending_events=(),
    live_event_ids: Iterable[int] = frozenset(),
    planner=None,
):
    """The #10655 plan, re-ordered live -> scheduled -> unrelated."""
    if planner is None:
        from app.tasks.kalshi_ws import linked_first_phases as planner
    live = frozenset(live_event_ids)  # the per-flush snapshot
    phases = planner(
        batch, market_id_by_outcome, event_id_by_outcome,
        pending_events=pending_events,
    )
    if len(phases) < 2 or not live:
        return phases
    tiers = [
        phase_tier(p, market_id_by_outcome, event_id_by_outcome, live)
        for p in phases
    ]
    order = sorted(range(len(phases)), key=lambda i: tiers[i])
    return [phases[i] for i in order]
