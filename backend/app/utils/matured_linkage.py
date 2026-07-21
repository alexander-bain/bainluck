"""Matured-linkage metric — pure summarization logic (Queue #220/221 Item 2).

Alex's ruling: *the blend is the product* and *below-100% must MEAN something*.
The old headline linkage number (all-future coverage / all-status link rate) sits
permanently below 100 for non-defect reasons — aged-out settled markets, upstream
sports a source never covers — so its below-100 reading is noise, not signal.

The **matured-linkage** metric fixes that by measuring only what a real defect
would move:

  * Universe = *matured* events: status scheduled/live and starting within the
    imminent window (NOW-6h .. NOW+24h). By game time, linkage should be done.
  * Denominator = each event's OWN blend sources — the sources actually present in
    ``events.win_probability_sources`` (what the blend, i.e. the product, claims to
    use). Scoping to the event's own blend keys means we NEVER expect a source the
    event doesn't have (no "expect Kalshi for MiLB" noise) — so a miss is always a
    real defect, never an upstream gap.
  * Check = for the two sources whose blend contribution comes from a *linkable*
    market (Kalshi, Polymarket), there MUST be a linked winner market
    (``futures_markets.event_id = event AND source = src``). A blend that carries a
    Kalshi/Poly number with no linked market behind it is a phantom source — a
    stale/unbacked number feeding the product (the "blend gate ≠ link" class).
    The other blend sources (betting/odds_api, espn, mlb, stat_model) have no
    futures_market to link — their blend entry *is* their backing — so they are
    not checkable here and are excluded from the denominator.

Below-100 therefore means exactly one thing: a prediction-market source is in an
imminent event's blend but its winner market is not linked. Every such
(event, source) pair is a real, filed defect.
"""

from __future__ import annotations

from typing import Any

# Sources whose blend contribution is backed by a linkable game-winner market.
# Only these can diverge (blend-present but link-missing) — the checkable set.
CHECKABLE_SOURCES: tuple[str, ...] = ("kalshi", "polymarket")


def summarize_matured_linkage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize checkable (event, source) blend pairs into the metric payload.

    Each row is one (imminent event, blend source) pair for a CHECKABLE source:
        {"event_id", "sport", "matchup", "commence_time", "source", "linked"}
    ``linked`` is True when a winner market from ``source`` is linked to the event.

    Returns the headline pct, per-source breakdown, the miss list (phantom blend
    sources — the filed defects), and event-level consistency. When the imminent
    slate carries no checkable blend pairs (e.g. an off-brand lull with no
    Kalshi/Poly game blends), the headline is None with status
    ``insufficient_slate`` rather than a misleading 100 or 0."""
    total = len(rows)
    backed = sum(1 for r in rows if r.get("linked"))
    misses = [
        {
            "event_id": r.get("event_id"),
            "source": r.get("source"),
            "sport": r.get("sport"),
            "matchup": r.get("matchup"),
            "commence_time": r.get("commence_time"),
        }
        for r in rows
        if not r.get("linked")
    ]

    by_source: dict[str, dict[str, int]] = {}
    for r in rows:
        src = r.get("source") or "unknown"
        b = by_source.setdefault(src, {"total": 0, "backed": 0, "phantom": 0})
        b["total"] += 1
        if r.get("linked"):
            b["backed"] += 1
        else:
            b["phantom"] += 1
    for src, b in by_source.items():
        b["backed_pct"] = round(100.0 * b["backed"] / b["total"], 1) if b["total"] else None

    # Event-level consistency: an event is consistent when none of its checkable
    # blend sources is a phantom.
    events_seen: set[Any] = set()
    events_with_phantom: set[Any] = set()
    for r in rows:
        eid = r.get("event_id")
        events_seen.add(eid)
        if not r.get("linked"):
            events_with_phantom.add(eid)

    status = "insufficient_slate" if total == 0 else "ok"
    return {
        "headline_pct": round(100.0 * backed / total, 1) if total else None,
        "status": status,
        "checkable_pairs": total,
        "backed": backed,
        "phantom": total - backed,
        "by_source": by_source,
        "events_checked": len(events_seen),
        "events_consistent": len(events_seen) - len(events_with_phantom),
        "misses": misses,
        "definition": (
            "Of imminent events (scheduled/live, starting within NOW-6h..NOW+24h), "
            "the fraction of blend prediction-market sources (Kalshi/Polymarket "
            "present in win_probability_sources) that are backed by a linked winner "
            "market. Below 100% = a phantom blend source (a real defect); scoped to "
            "each event's own blend so it never counts upstream gaps."
        ),
    }
