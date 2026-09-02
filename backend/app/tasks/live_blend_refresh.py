"""Q460 — the fast lane's last mile: WebSocket price -> the number on the card.

WHAT WAS BROKEN. `worker-ws` has been streaming Kalshi prices into
`futures_outcomes.current_probability` in production for months, sub-second,
and none of it was visible. Measured 2026-08-30 18:32 UTC: 4 of 10 live Kalshi
outcomes moved inside a 25-second window, while `Event.win_probability_sources`
— the JSONB every hero and every card actually renders — advanced only on the
120-second `poll_live_prediction_markets` pass. Sampled three times across 90s,
the Kalshi blend stamp read 54s / 0s / 24s old: a clean 120s sawtooth. The fast
lane existed, worked, and stopped one table short of the number.

Alex's own specimen (Hawaii @ Stanford, 2026-08-29) is the cost. That event's
blend carried exactly one prediction-market source, and its in-game snapshots
land 240s / 360s / 600s / 1200s apart. A number that moves every four to twenty
minutes during a football game is what "constantly behind the action" means.

WHAT THIS DOES. After the WS flushes prices for a batch of outcomes, it hands
the affected event ids here. For each, this recomputes that source's home
probability from the rows the flush just wrote — via
`app/utils/live_blend.py`, the SAME expression the 120s poll uses, so the two
writers cannot disagree — and stamps `win_probability_sources`.

THREE THINGS IT DELIBERATELY DOES NOT DO.

* **It does not go through Celery.** It is called in-process on the `worker-ws`
  dyno. The background queue is a known congestion point (GIN beat starvation),
  and a fast lane queued behind a slow one is not a fast lane.
* **It does not write `win_prob_snapshots`.** The chart's cadence is a separate
  product question and the 120s poll still owns it. Writing a snapshot per tick
  would multiply that table's growth by ~60x to make a line that no one can see
  the extra resolution in.
* **It does not re-derive the inversion verdict per tick.**
  `_check_and_fix_inversion` costs a per-event `odds_snapshots` lookup, which is
  affordable every 120 seconds and not every 2. Orientation is a property of the
  LINKAGE, not of the price, so it is computed once and cached — and the 120s
  poll re-derives it authoritatively regardless, which bounds how long a wrong
  verdict can survive to one poll interval.

SAFETY POSTURE. Every failure here is swallowed and counted. This runs inside
the WS consumer's flush loop, and a blend refresh that raises must never take
down the price streaming that is the dyno's actual job (gotcha #42, one bad item
must not wipe the pass).
"""

from __future__ import annotations

import logging
import math
import time
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


#: Per-event floor between fast-lane recomputes. The WS flushes every 2s; an
#: event whose price ticks continuously does not need a JSONB write every tick
#: to feel live, and 5s keeps the write rate bounded on a busy slate.
DEFAULT_MIN_REFRESH_INTERVAL_S = 5.0

#: How long a cached inversion verdict stays good. One poll interval plus slack:
#: the 120s poll re-derives it authoritatively, so this never has to be the
#: durable answer, only a cheap one that cannot be stale for long.
DEFAULT_INVERSION_TTL_S = 150.0

#: When the recomputed value rounds to what is already stored, the write is
#: still worth making occasionally — `updated_at` is what drives the hero's
#: recency decay (#1829), so a source that goes quiet must still look ALIVE
#: rather than progressively losing weight. Just not every five seconds.
UNCHANGED_RESTAMP_INTERVAL_S = 45.0


class LiveBlendRefresher:
    """Stateful per-source refresher, owned by one WS consumer run.

    State (throttles, inversion verdicts) is per-instance rather than global so
    the Kalshi and Polymarket consumers on the shared dyno cannot evict each
    other's entries, and so a reconnect starts clean.
    """

    def __init__(
        self,
        source: str,
        *,
        min_refresh_interval_s: float = DEFAULT_MIN_REFRESH_INTERVAL_S,
        inversion_ttl_s: float = DEFAULT_INVERSION_TTL_S,
        unchanged_restamp_interval_s: float = UNCHANGED_RESTAMP_INTERVAL_S,
    ) -> None:
        self.source = source
        self.min_refresh_interval_s = min_refresh_interval_s
        self.inversion_ttl_s = inversion_ttl_s
        self.unchanged_restamp_interval_s = unchanged_restamp_interval_s
        self._last_refresh_at: dict[int, float] = {}
        self._last_write_at: dict[int, float] = {}
        self._last_written_value: dict[int, float] = {}
        self._inversion: dict[int, tuple[float, bool]] = {}
        self.stats: dict[str, int] = {
            "considered": 0,
            "throttled": 0,
            "no_reading": 0,
            "stamped": 0,
            "unchanged_skipped": 0,
            "errors": 0,
        }

    # ── throttling ───────────────────────────────────────────────────────────

    def _due(self, event_id: int, now: float) -> bool:
        last = self._last_refresh_at.get(event_id)
        return last is None or (now - last) >= self.min_refresh_interval_s

    # ── inversion orientation, cached ────────────────────────────────────────

    async def _oriented(self, session, event_id: int, home_prob: float) -> float:
        """Apply the inversion verdict, computing it at most once per TTL.

        Returns the home probability the poll would have written. The verdict is
        cached as a BOOLEAN (did this linkage need flipping), not as a value —
        caching the value would pin a price, which is the opposite of the point.
        """
        now = time.monotonic()
        cached = self._inversion.get(event_id)
        if cached is not None and now < cached[0]:
            return 1.0 - home_prob if cached[1] else home_prob

        from app.tasks.prediction_market_matching import _check_and_fix_inversion

        corrected = await _check_and_fix_inversion(
            session, event_id, home_prob, self.source,
        )
        flipped = not math.isclose(corrected, home_prob, rel_tol=0.0, abs_tol=1e-9)
        self._inversion[event_id] = (now + self.inversion_ttl_s, flipped)
        return corrected

    # ── the refresh itself ───────────────────────────────────────────────────

    async def refresh(self, event_ids: Iterable[int]) -> dict[str, int]:
        """Recompute and stamp the blend for these events. Never raises."""
        now = time.monotonic()
        due = [eid for eid in set(event_ids) if self._due(eid, now)]
        self.stats["considered"] += len(due)
        skipped = len(set(event_ids)) - len(due)
        if skipped > 0:
            self.stats["throttled"] += skipped
        if not due:
            return self.stats

        try:
            await self._refresh_batch(due, now)
        except Exception:
            self.stats["errors"] += 1
            logger.exception(
                "live_blend_refresh[%s]: batch failed for %d events",
                self.source, len(due),
            )
        return self.stats

    async def _refresh_batch(self, event_ids: list[int], now: float) -> None:
        from sqlalchemy import select, update

        from app.models.models import Event, FuturesMarket, FuturesOutcome
        from app.tasks.base import get_task_session
        from app.utils.aggregation import stamp_source_reading
        from app.utils.live_blend import (
            MarketOutcomes, compute_source_home_probability,
        )

        # Stamp the throttle for EVERY event we are about to attempt, before any
        # of them can fail to resolve. Stamping per-resolved-event instead would
        # leave an event with no linked markets of this source permanently
        # "due", and `get_task_session()` builds a fresh engine and connection
        # pool per call — so that event would open a Postgres connection every
        # 2-second flush, forever, to discover the same nothing.
        for event_id in event_ids:
            self._last_refresh_at[event_id] = now

        async with get_task_session() as session:
            market_rows = (
                await session.execute(
                    select(FuturesMarket, Event)
                    .join(Event, FuturesMarket.event_id == Event.id)
                    .where(
                        FuturesMarket.source == self.source,
                        FuturesMarket.event_id.in_(event_ids),
                    )
                )
            ).all()
            if not market_rows:
                return

            market_ids = [m.id for m, _ in market_rows]
            outcomes_by_market: dict[int, list] = {}
            for outcome in (
                await session.execute(
                    select(FuturesOutcome).where(
                        FuturesOutcome.market_id.in_(market_ids)
                    )
                )
            ).scalars():
                outcomes_by_market.setdefault(outcome.market_id, []).append(outcome)

            grouped: dict[int, tuple] = {}
            for market, event in market_rows:
                entry = grouped.setdefault(event.id, (event, []))
                entry[1].append(
                    MarketOutcomes(
                        market=market,
                        outcomes=outcomes_by_market.get(market.id, []),
                    )
                )

            for event_id, (event, group) in grouped.items():
                try:
                    reading = compute_source_home_probability(
                        group, event.home_team_name, event.away_team_name,
                    )
                    if reading is None:
                        self.stats["no_reading"] += 1
                        continue

                    home_prob = await self._oriented(
                        session, event_id, reading.home_probability,
                    )
                    value = round(home_prob, 4)

                    if not self._should_write(event_id, value, now):
                        self.stats["unchanged_skipped"] += 1
                        continue

                    current = (
                        await session.execute(
                            select(Event.win_probability_sources).where(
                                Event.id == event_id
                            )
                        )
                    ).scalar_one_or_none()
                    # Core update, never ORM attribute assignment — gotcha #4.
                    await session.execute(
                        update(Event)
                        .where(Event.id == event_id)
                        .values(
                            win_probability_sources=stamp_source_reading(
                                current, self.source, value,
                            )
                        )
                    )
                    self._last_write_at[event_id] = now
                    self._last_written_value[event_id] = value
                    self.stats["stamped"] += 1
                except Exception:
                    self.stats["errors"] += 1
                    logger.exception(
                        "live_blend_refresh[%s]: event %s failed",
                        self.source, event_id,
                    )

    def _should_write(self, event_id: int, value: float, now: float) -> bool:
        """Write on any real move; on no move, re-stamp only occasionally.

        The re-stamp is not cosmetic. `updated_at` feeds the hero's RELATIVE
        recency decay, so a source that keeps quoting the same price must keep
        saying so or it slowly loses weight against noisier siblings and the
        blend drifts toward whichever source moves most.
        """
        previous = self._last_written_value.get(event_id)
        if previous is None or previous != value:
            return True
        last_write = self._last_write_at.get(event_id, 0.0)
        return (now - last_write) >= self.unchanged_restamp_interval_s


def event_ids_for_outcomes(
    outcome_to_event: dict[int, Optional[int]], outcome_ids: Iterable[int]
) -> set[int]:
    """The distinct linked event ids behind a batch of flushed outcomes."""
    seen: set[int] = set()
    for outcome_id in outcome_ids:
        event_id = outcome_to_event.get(outcome_id)
        if event_id is not None:
            seen.add(event_id)
    return seen
