"""Adopt Kalshi's finalized settlement status for markets stuck ``status='open'``.

CAL-P049 Item 2 (#1818). The WRITE half of the settlement-status sync. The READ
half — why the population exists at all — is fixed in ``app/tasks/kalshi.py``:
the poll derived market status from ``m.status in ("closed", "settled")``, which
against live Kalshi matches nothing that carries a result, so every poll rewrote
an all-``finalized`` event back to ``'open'``. See ``app/utils/kalshi_market_status``.

This repair exists even though the poll fix alone will drain most of the
population on its next cycle, for two reasons the poll cannot cover:

* a market the unfiltered events listing no longer returns is never re-polled,
  so its status can only be corrected by asking for it BY TICKER — which is what
  this does, and which works at ANY age (see the retention note below);
* the acceptance for #1818 is a measured before/after on the standing
  population, and the rail returns exactly that census in its own response.

AUTHORITY. This adopts venue-declared state — Kalshi's own ``status`` on its own
market — not our judgment. That is the ruled authority for settlement. It is
still a stored-value change, so it is dry-run by default, capped, and ATTENDED:
never wire it to a beat.

RETENTION IS NOT A CONSTRAINT HERE, and that is a measured claim, not an
assumption (gotcha #35 says EVENT data is permanent while MARKET data is purged
at 74–86 days). Probed 2026-08-13: ``GET /events/KXEURUSDW-26MAY0817`` — settled
89 days earlier, i.e. PAST the upper retention bound — still returned its market
``finalized`` with ``result='yes'``. Status recovery therefore has no cliff. Only
PRICE recovery does, and this repair writes no prices.

FAIL-CLOSED CASES, each of which leaves the row untouched and is counted:

* ``get_event`` returned None — that is 404 *or* a swallowed transport error
  (gotcha #36), so it is "unknown", never "absent";
* the event came back with ZERO markets — an empty 200 is a response shape, not
  a fact (gotcha #53). At this age it usually means retention purged the market
  list, and inferring "not settled" from it would be inventing a fact;
* ANY sub-market is non-terminal — a part-settled event has not settled;
* every sub-market is terminal but NONE carries a ``result`` (e.g. all
  ``closed``) — terminal is not the same as declared, so there is nothing to
  adopt yet.

Usage (the rail, not an incantation — gotcha #48):

    POST /api/admin/repairs/kalshi-settlement-status?apply=false          # census
    POST /api/admin/repairs/kalshi-settlement-status?apply=true&limit=40  # commit
    ...re-invoke with ?offset=<next_offset> while ``exhausted`` is false
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy import text

from app.utils.kalshi_market_status import has_declared_result, is_terminal

logger = logging.getLogger(__name__)

#: Hard ceiling on rows written per call. A module constant, NOT a parameter, so
#: the cap cannot be dialled off mid-run (the winner-field-repair discipline).
APPLY_MARKET_CAP = 60

#: Wall-clock budget per call. The repair rail runs inside the web dyno, which
#: has a 30s HTTP timeout; one Kalshi fetch per market means the bound has to be
#: time, not just count. Returning a partial page with a resume offset is a
#: normal outcome, not a failure.
_MAX_SECONDS = 20.0

#: The standing population, in one place so the before-census, the work
#: selection and the after-census cannot drift from each other.
_POPULATION_PREDICATE = """
    source = 'kalshi'
    AND status <> 'resolved'
    AND resolution_date IS NOT NULL
    AND resolution_date < NOW()
"""


async def _census(session) -> dict[str, Any]:
    """Count the standing population, and its age against the retention bounds."""
    row = (
        await session.execute(
            text(
                f"""
                SELECT COUNT(*) AS markets,
                       COUNT(*) FILTER (
                           WHERE resolution_date < NOW() - INTERVAL '86 days'
                       ) AS past_purge_bound,
                       COUNT(*) FILTER (
                           WHERE resolution_date < NOW() - INTERVAL '74 days'
                             AND resolution_date >= NOW() - INTERVAL '86 days'
                       ) AS in_retention_band,
                       COUNT(*) FILTER (
                           WHERE resolution_date < NOW() - INTERVAL '60 days'
                             AND resolution_date >= NOW() - INTERVAL '74 days'
                       ) AS at_risk_60_73,
                       MAX(
                           FLOOR(EXTRACT(EPOCH FROM (NOW() - resolution_date)) / 86400)
                       )::int AS oldest_days
                FROM futures_markets
                WHERE {_POPULATION_PREDICATE}
                """
            )
        )
    ).one()
    return {
        "markets": row.markets,
        "past_purge_bound_86d": row.past_purge_bound,
        "in_retention_band_74_85d": row.in_retention_band,
        "at_risk_60_73d": row.at_risk_60_73,
        "oldest_days_past_resolution": row.oldest_days,
    }


def _classify(event: dict | None) -> tuple[str, dict[str, Any]]:
    """Decide what the venue says about this event. Pure — no DB, no network.

    Returns ``(verdict, detail)`` where verdict is one of ``settled`` (safe to
    adopt), ``not_settled``, ``no_markets`` or ``unknown``.
    """
    if event is None:
        return "unknown", {"reason": "event lookup returned None (404 or error)"}

    markets = event.get("markets") or []
    if not markets:
        # gotcha #53: an empty 200 is a shape, not a fact.
        return "no_markets", {"reason": "event returned zero markets"}

    statuses = [m.get("status") for m in markets]
    non_terminal = sorted({s for s in statuses if not is_terminal(s)})
    if non_terminal:
        return "not_settled", {
            "non_terminal_statuses": non_terminal,
            "markets": len(markets),
        }

    declared = sum(
        1
        for m in markets
        if has_declared_result(m.get("status")) and m.get("result") not in (None, "")
    )
    if declared == 0:
        return "not_settled", {
            "reason": "all terminal but none carries a result",
            "statuses": sorted(set(statuses)),
            "markets": len(markets),
        }

    return "settled", {
        "markets": len(markets),
        "with_result": declared,
        "statuses": sorted(set(statuses)),
    }


async def repair(
    session,
    apply: bool = False,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    """Census → per-market venue lookup → exact-match flip. Dry-run by default."""
    from app.services.kalshi_api import KalshiAPIService

    started = time.monotonic()
    window = min(int(limit or APPLY_MARKET_CAP), APPLY_MARKET_CAP)
    cursor = max(int(offset or 0), 0)

    before = await _census(session)

    # OLDEST FIRST (gotcha #41). There is no expiring floor to pair it with here
    # — the events endpoint answers at any age, proven above — so oldest-first is
    # safe on its own. If this repair is ever extended to write PRICES, it needs
    # the floor back, because that population does expire.
    rows = (
        await session.execute(
            text(
                f"""
                SELECT id, external_id, llm_sport_category,
                       FLOOR(
                           EXTRACT(EPOCH FROM (NOW() - resolution_date)) / 86400
                       )::int AS age_days
                FROM futures_markets
                WHERE {_POPULATION_PREDICATE}
                ORDER BY resolution_date ASC, id ASC
                LIMIT :lim OFFSET :off
                """
            ),
            {"lim": window, "off": cursor},
        )
    ).all()

    verdicts: dict[str, int] = {}
    flipped = 0
    examined = 0
    skipped_detail: list[dict[str, Any]] = []
    timed_out = False

    service = KalshiAPIService()
    try:
        for row in rows:
            if time.monotonic() - started > _MAX_SECONDS:
                timed_out = True
                break
            examined += 1

            event = await service.get_event(row.external_id, with_nested_markets=True)
            verdict, detail = _classify(event)
            verdicts[verdict] = verdicts.get(verdict, 0) + 1

            if verdict != "settled":
                if len(skipped_detail) < 15:
                    skipped_detail.append(
                        {
                            "market_id": row.id,
                            "ticker": row.external_id,
                            "age_days": row.age_days,
                            "verdict": verdict,
                            **detail,
                        }
                    )
                continue

            if not apply:
                flipped += 1
                continue

            if flipped >= APPLY_MARKET_CAP:
                break

            # Status-guarded so a concurrent poll that already fixed this row
            # makes the UPDATE a no-op rather than a redundant write.
            result = await session.execute(
                text(
                    """
                    UPDATE futures_markets
                    SET status = 'resolved', updated_at = NOW()
                    WHERE id = :id AND status <> 'resolved'
                    """
                ),
                {"id": row.id},
            )
            flipped += result.rowcount
    finally:
        try:
            await service.close()
        except Exception:
            pass

    if apply and flipped:
        await session.commit()

    after = await _census(session) if apply else before

    return {
        "before": before,
        "after": after,
        "window": {"limit": window, "offset": cursor, "returned": len(rows)},
        "examined": examined,
        "verdicts": verdicts,
        "flipped" if apply else "would_flip": flipped,
        "skipped_examples": skipped_detail,
        "next_offset": cursor + examined,
        # A partial page (budget hit) is NOT exhaustion — say so explicitly, so a
        # reader cannot mistake "we stopped" for "there was nothing left".
        "exhausted": (not timed_out) and len(rows) < window,
        "stopped_on_time_budget": timed_out,
        "elapsed_s": round(time.monotonic() - started, 1),
        "apply_market_cap": APPLY_MARKET_CAP,
    }
