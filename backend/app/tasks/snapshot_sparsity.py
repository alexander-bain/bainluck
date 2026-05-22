"""Automated snapshot sparsity detection and historical backfill.

Runs daily. Finds completed events from the last 48 hours with fewer
than the expected number of snapshots and triggers historical API
backfills to fill the gaps.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import text

from app.tasks.base import get_task_session, run_async
from app.tasks.redis_state import record_task_metric

logger = logging.getLogger(__name__)

TIER1_SPORTS = {
    "basketball_nba", "icehockey_nhl", "baseball_mlb",
    "americanfootball_nfl", "basketball_ncaab",
}
TIER2_SPORTS = {
    "basketball_wnba", "soccer_epl", "soccer_usa_mls",
    "soccer_uefa_champs_league", "mma_mixed_martial_arts",
}

SNAPSHOT_THRESHOLD = 20
MAX_BACKFILL_PER_RUN = 10


async def _check_and_backfill():
    """Find sparse events and backfill from historical API."""
    from app.services.odds_api import OddsAPIService
    from app.models.models import OddsSnapshot
    from app.utils.odds_math import moneyline_to_probability
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.tasks.redis_state import get_redis_client

    all_sports = TIER1_SPORTS | TIER2_SPORTS
    sports_filter = ", ".join(f"'{s}'" for s in all_sports)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=48)

    async with get_task_session() as session:
        q = await session.execute(text(f"""
            SELECT
                e.id,
                s.key AS sport_key,
                e.home_team,
                e.away_team,
                e.commence_time,
                e.external_id,
                COUNT(os.id) AS snapshot_count
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            LEFT JOIN odds_snapshots os ON os.event_id = e.id
            WHERE e.status IN ('completed', 'closed')
              AND e.commence_time >= :cutoff
              AND e.external_id IS NOT NULL
              AND s.key IN ({sports_filter})
            GROUP BY e.id, s.key, e.home_team, e.away_team, e.commence_time, e.external_id
            HAVING COUNT(os.id) < :threshold
            ORDER BY e.commence_time
            LIMIT :max_events
        """), {
            "cutoff": cutoff,
            "threshold": SNAPSHOT_THRESHOLD,
            "max_events": MAX_BACKFILL_PER_RUN,
        })

        sparse_events = q.all()

        if not sparse_events:
            logger.info("snapshot_sparsity: no sparse events in last 48h")
            return {"sparse_events": 0, "backfilled": 0}

        logger.warning(
            "snapshot_sparsity: found %d sparse events in last 48h, backfilling",
            len(sparse_events),
        )

        # Record alert in Redis for admin dashboard
        r = get_redis_client()
        if r:
            r.set(
                "bainluck:sparsity_alert",
                f"{len(sparse_events)} sparse events detected at {now.isoformat()}",
                ex=86400,
            )

        service = OddsAPIService()
        total_backfilled = 0

        for event in sparse_events:
            event_id = event.id
            sport_key = event.sport_key
            external_id = event.external_id
            commence_time = event.commence_time

            if commence_time.tzinfo is None:
                commence_time = commence_time.replace(tzinfo=timezone.utc)

            game_duration_hours = 4.0
            start = commence_time - timedelta(hours=1)
            end = commence_time + timedelta(hours=game_duration_hours)

            snapshots_added = 0
            current = start

            while current <= end:
                date_param = current.strftime("%Y-%m-%dT%H:%M:%SZ")
                try:
                    url = f"{service.BASE_URL}/historical/sports/{sport_key}/odds"
                    response = await service.client.get(url, params={
                        "apiKey": service.api_key,
                        "regions": "us",
                        "markets": "h2h",
                        "date": date_param,
                    })
                    service._capture_quota(response)

                    if response.status_code != 200:
                        current += timedelta(minutes=5)
                        continue

                    data = response.json()
                    for ev in data.get("data", []):
                        if ev.get("id") != external_id:
                            continue

                        for bm in ev.get("bookmakers", []):
                            for mkt in bm.get("markets", []):
                                if mkt["key"] != "h2h":
                                    continue

                                outcomes = mkt.get("outcomes", [])
                                if len(outcomes) < 2:
                                    continue

                                home_prob, away_prob = None, None
                                for o in outcomes:
                                    prob = moneyline_to_probability(o["price"]) if isinstance(o["price"], (int, float)) else None
                                    if o["name"] == ev.get("home_team"):
                                        home_prob = prob
                                    elif o["name"] == ev.get("away_team"):
                                        away_prob = prob

                                ts = data.get("timestamp", date_param)
                                captured_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))

                                stmt = pg_insert(OddsSnapshot).values(
                                    event_id=event_id,
                                    bookmaker=bm["key"],
                                    home_odds=outcomes[0].get("price"),
                                    away_odds=outcomes[1].get("price") if len(outcomes) > 1 else None,
                                    home_probability=home_prob,
                                    away_probability=away_prob,
                                    captured_at=captured_at,
                                ).on_conflict_do_nothing()
                                await session.execute(stmt)
                                snapshots_added += 1

                    next_ts = data.get("next_timestamp")
                    if next_ts:
                        current = datetime.fromisoformat(next_ts.replace("Z", "+00:00"))
                    else:
                        current += timedelta(minutes=5)

                except Exception as e:
                    logger.warning("Backfill error for event %d at %s: %s", event_id, date_param, e)
                    current += timedelta(minutes=5)

            await session.commit()
            total_backfilled += snapshots_added
            logger.info(
                "Backfilled %d snapshots for %s %s @ %s (event %d, was %d)",
                snapshots_added, event.away_team, event.home_team,
                str(commence_time)[:16], event_id, event.snapshot_count,
            )

        return {
            "sparse_events": len(sparse_events),
            "backfilled": total_backfilled,
            "quota_remaining": service.last_requests_remaining,
        }


def check_and_backfill_sparse_snapshots():
    """Celery task entry point."""
    return run_async(_check_and_backfill())


async def _backfill_historical_for_sport(sport: str, days_back: int = 30, max_events: int = 500):
    """Backfill sparse events from The Odds API historical endpoint."""
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import text
    from app.services.odds_api import OddsAPIService
    from app.models.models import OddsSnapshot
    from app.utils.odds_math import moneyline_to_probability
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    async with get_task_session() as session:
        sparse_q = await session.execute(text("""
            SELECT
                e.id, e.home_team_name, e.away_team_name, e.commence_time,
                e.external_id, e.status,
                COUNT(os.id) AS snap_count
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            LEFT JOIN odds_snapshots os ON os.event_id = e.id
            WHERE e.commence_time >= :cutoff
              AND s.key = :sport
              AND e.external_id IS NOT NULL
              AND e.status IN ('completed', 'closed', 'live', 'scheduled')
            GROUP BY e.id, e.home_team_name, e.away_team_name, e.commence_time, e.external_id, e.status
            HAVING COUNT(os.id) < 20
            ORDER BY COUNT(os.id) ASC
            LIMIT :max_events
        """), {"cutoff": cutoff, "sport": sport, "max_events": max_events})

        sparse_events = sparse_q.all()
        logger.info("backfill_historical: %d sparse %s events to backfill", len(sparse_events), sport)

        if not sparse_events:
            return {"sport": sport, "events_processed": 0, "total_new_snapshots": 0}

        service = OddsAPIService()
        results = []
        total_snapshots = 0

        for event in sparse_events:
            commence = event.commence_time
            if commence.tzinfo is None:
                commence = commence.replace(tzinfo=timezone.utc)

            start = commence - timedelta(hours=1)
            end = commence + timedelta(hours=4)
            current = start
            event_snapshots = 0

            while current <= end:
                date_param = current.strftime("%Y-%m-%dT%H:%M:%SZ")
                try:
                    url = f"{service.BASE_URL}/historical/sports/{sport}/odds"
                    response = await service.client.get(url, params={
                        "apiKey": service.api_key,
                        "regions": "us",
                        "markets": "h2h",
                        "date": date_param,
                    })
                    service._capture_quota(response)

                    if response.status_code != 200:
                        current += timedelta(minutes=10)
                        continue

                    data = response.json()

                    for ev_data in data.get("data", []):
                        if ev_data.get("id") != event.external_id:
                            continue

                        for bm in ev_data.get("bookmakers", []):
                            for mkt in bm.get("markets", []):
                                if mkt["key"] != "h2h":
                                    continue
                                outcomes = mkt.get("outcomes", [])
                                if len(outcomes) < 2:
                                    continue

                                home_prob, away_prob = None, None
                                for o in outcomes:
                                    prob = moneyline_to_probability(o["price"]) if isinstance(o["price"], (int, float)) else None
                                    if o["name"] == ev_data.get("home_team"):
                                        home_prob = prob
                                    elif o["name"] == ev_data.get("away_team"):
                                        away_prob = prob

                                ts = data.get("timestamp", date_param)
                                captured_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))

                                stmt = pg_insert(OddsSnapshot).values(
                                    event_id=event.id,
                                    bookmaker=bm["key"],
                                    home_odds=outcomes[0].get("price"),
                                    away_odds=outcomes[1].get("price") if len(outcomes) > 1 else None,
                                    home_probability=home_prob,
                                    away_probability=away_prob,
                                    captured_at=captured_at,
                                ).on_conflict_do_nothing()
                                await session.execute(stmt)
                                event_snapshots += 1

                    next_ts = data.get("next_timestamp")
                    if next_ts:
                        current = datetime.fromisoformat(next_ts.replace("Z", "+00:00"))
                    else:
                        current += timedelta(minutes=10)

                except Exception as e:
                    logger.warning("Backfill error event %d at %s: %s", event.id, date_param, e)
                    current += timedelta(minutes=10)

            await session.commit()
            total_snapshots += event_snapshots
            logger.info(
                "Backfilled %d snaps for %s @ %s (event %d, was %d)",
                event_snapshots, event.away_team_name, event.home_team_name,
                event.id, event.snap_count,
            )

            results.append({
                "event_id": event.id,
                "teams": f"{event.away_team_name} @ {event.home_team_name}",
                "existing": event.snap_count,
                "new": event_snapshots,
            })

        return {
            "sport": sport,
            "events_processed": len(results),
            "total_new_snapshots": total_snapshots,
            "quota_remaining": service.last_requests_remaining,
            "events": results,
        }
