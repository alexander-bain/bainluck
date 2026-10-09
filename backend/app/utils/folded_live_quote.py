"""Compact authoritative detail quote, shared across recipients of one update."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import json

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Event
from app.services.database import async_session_maker
from app.utils.aggregation import newest_source_reading_time
from app.utils.draw_priced_winner import printable_away
from app.utils.hero_probability import hero_sportsbook_count, resolve_hero
from app.utils.kalshi_occurrence_start import loaded_sport_key
from app.utils.lifecycle import served_event_status
from app.utils.price_evidence import load_price_evidence
from app.utils.probability_source_format import format_probability_sources
from app.utils.proven_duplicates import FoldedBlendView, folded_probability_sources_with_revision
from app.utils.serve_fold_absorbed import serve_fold_absorbed_rows

logger = logging.getLogger(__name__)

PROJECTION_TIMEOUT_S = 1.0
MAX_PENDING = 8
MAX_CACHED = 64


async def load_folded_quote(event_id: int, origin_id: int, origin_rev: int):
    """Reuse detail's read-only fold and probability policy, without its page IO."""
    async with async_session_maker() as db:
        event = (await db.execute(
            select(Event).options(selectinload(Event.sport)).where(Event.id == event_id)
        )).scalar_one_or_none()
        if event is None:
            return None
        absorbed = await serve_fold_absorbed_rows(db, event)
        sources, revision = await folded_probability_sources_with_revision(db, event, absorbed)
        if (revision is None or str(event_id) not in revision
                or revision.get(str(origin_id), -1) < origin_rev):
            return None
        view = FoldedBlendView(event, sources)
        hero = resolve_hero(view)
        sport = loaded_sport_key(event)
        observed_at = (
            newest_source_reading_time(view, require_complete=True)
            if hero is not None and hero.source == "blend" else None
        )
        public_sources = format_probability_sources(sources)
        pm = public_sources.get("polymarket")
        if isinstance(pm, dict):
            # Exactly the detail rail's durable price evidence, never venue IO.
            pm["price_evidence"] = await load_price_evidence(db, sources.get("polymarket"))
        away = None if hero is None else hero.away_probability
        if hero is not None and hero.source != "settled":
            away = printable_away(away, hero.home_probability, sport)
        quote = {
            "event_id": event_id,
            "hero_probability": None if hero is None else hero.home_probability,
            "hero_probability_away": away,
            "hero_probability_source": None if hero is None else hero.source,
            "hero_probability_observed_at": None if observed_at is None else observed_at.isoformat(),
            "blend_fold_revision": revision,
            "win_probability_sources": public_sources,
            "hero_sportsbook_count": (
                hero_sportsbook_count(view)
                if hero is not None and hero.source == "blend" else None
            ),
            "hero_settled_result": None if hero is None else hero.settled_result,
            "status": served_event_status(event.status, event.commence_time, datetime.now(timezone.utc)),
            "sport": sport,
        }
        # Shared legacy formatting accepts numeric shapes; transport authority
        # additionally needs valid JSON numbers, without changing detail policy.
        json.dumps(quote, allow_nan=False)
        return quote


@dataclass
class _Work:
    task: asyncio.Task
    waiters: int = 0


class FoldedQuoteProjector:
    """Bounded per-process coalescing, with no subscription or ingestion policy."""

    def __init__(self):
        self._pending = {}
        self._cached = OrderedDict()
        self._slots = asyncio.Semaphore(2)

    async def _load(self, event_id, origin_id, revision):
        try:
            async with asyncio.timeout(PROJECTION_TIMEOUT_S):
                async with self._slots:
                    return await load_folded_quote(event_id, origin_id, revision)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("folded quote unavailable for event %s", event_id, exc_info=True)
            return None

    async def project(self, event_id: int, frame: dict):
        origin_id, revision = frame.get("event_id"), frame.get("rev")
        if (type(origin_id) is not int or not isinstance(revision, dict)
                or set(revision) != {str(origin_id)}
                or type(revision[str(origin_id)]) is not int
                or revision[str(origin_id)] < 0):
            return None
        if any(frame.get(field) is not None and not isinstance(frame[field], str)
               for field in ("status", "updated_at")):
            return None
        key = (event_id, origin_id, revision[str(origin_id)],
               frame.get("status"), frame.get("updated_at"))
        if key in self._cached:
            self._cached.move_to_end(key)
            return self._cached[key]
        work = self._pending.get(key)
        if work is not None and work.task.cancelling():
            return None  # departing last waiter still owns bounded cleanup
        if work is None:
            if len(self._pending) >= MAX_PENDING:
                return None
            work = _Work(asyncio.create_task(self._load(event_id, origin_id, revision[str(origin_id)])))
            self._pending[key] = work
        work.waiters += 1
        try:
            quote = await asyncio.shield(work.task)
            if quote is not None:
                self._cached[key] = quote
                self._cached.move_to_end(key)
                while len(self._cached) > MAX_CACHED:
                    self._cached.popitem(last=False)
            return quote
        finally:
            work.waiters -= 1
            if work.waiters == 0:
                # One departing reader cannot cancel another's shared read.
                # The last one joins cleanup, even through repeated cancellation.
                if not work.task.done():
                    work.task.cancel()
                while not work.task.done():
                    try:
                        await asyncio.wait({work.task})
                    except asyncio.CancelledError:
                        continue
                if not work.task.cancelled():
                    work.task.exception()
                self._pending.pop(key, None)
