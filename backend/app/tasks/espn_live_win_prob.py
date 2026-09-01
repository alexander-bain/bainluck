"""Keep the ESPN win-probability reading current on games that are live NOW.

Why this exists
---------------
`sync_espn_live_events` reads ESPN's win probability out of the scoreboard, at
`competitions[0].situation.lastPlay.probability.homeWinPercentage`. That field is
present for NFL and WNBA and ABSENT for MLB — probed live 2026-08-31, a live MLB
game's `situation` carries only `balls / batter / lastPlay / onFirst / onSecond /
onThird / outs / pitcher / strikes`. So for baseball the scoreboard pass is not
slow, it is blind, and the numbers say so: over 21 days of completed
espn_id-matched games, live-captured ESPN points per game came in at

    americanfootball_nfl   p50 116     basketball_wnba   p50  80
    baseball_mlb           p50   5     soccer_*          p50   0

A five-point series over three hours is the flat, janky ESPN line. It also ages
the `win_probability_sources.espn` stamp out past the hero's relative-age decay
window, so the blend correctly demotes ESPN to the 0.1 weight floor and the
source stops counting for anything.

The soccer zeros are NOT our bug: ESPN publishes no soccer win probability at
all, on the core feed (400 "Probabilities are not supported for sport: soccer")
or on `/summary` (no `winprobability` key). This task learns that from the 400
and stops asking.

What it does
------------
Selects live, espn_id-matched games whose stored ESPN reading has gone stale,
oldest reading first, and refreshes each from ESPN's core probabilities feed
(~1 KB, versus ~800 KB for the summary endpoint that carries the same number).
Every refresh re-stamps `win_probability_sources.espn` even when the value has
not moved, because the stamp is what the blend's decay reads — a source that is
still reporting the same number is not a stale source.

Rate limit
----------
ESPN publishes no rate limit for these undocumented endpoints, so the budget is
ours, stated rather than assumed: `ESPNAPIService` sleeps `rate_limit_delay`
(0.5 s) after every 200, i.e. a self-imposed ceiling of 120 requests/min for the
whole client. This task takes a bounded slice of that — `DEFAULT_EVENT_BUDGET`
games per 60 s cycle, at most 3 requests each and usually fewer (see
`get_live_win_probability`'s point-count short circuit) — and LOGS what it did
not reach rather than trimming quietly. Measured peak concurrency for the
population it serves is 16 simultaneous live MLB games (p90 = 11) over the last
7 days, so the default budget covers the whole slate at its busiest.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text

from app.models.models import Event, Sport
from app.tasks.base import get_task_session
from app.tasks.config import ESPN_SPORT_MAPPING
from app.utils.aggregation import stamp_source_reading

logger = logging.getLogger(__name__)

#: Games refreshed per cycle. 16 is the measured 7-day peak of simultaneous live
#: MLB games; 24 leaves room for a second blind league without a code change.
DEFAULT_EVENT_BUDGET = 24

#: Wall-clock stop, checked before each probe. The count budget above is sized
#: off a measured slate, but the thing that actually has to hold is the 50 s soft
#: time limit on the task — a count cannot know that ESPN is answering slowly
#: tonight. Measured cost per game against the live feed: 1.77 s for a cold read
#: (3 requests, two of them 0.5 s rate-limit sleeps) and 0.53 s when the feed has
#: not moved (1 request). This leaves room to commit and close out.
DEADLINE_SECONDS = 40.0

#: Commit every N writes rather than once at the end. A cycle that runs into the
#: soft time limit must not throw away the games it already refreshed.
COMMIT_EVERY = 5

#: A reading younger than this is already fresh enough — the scoreboard pass is
#: serving this league (NFL/WNBA) and there is nothing for this task to do. Sits
#: BELOW the 60 s beat so a game is picked up on every cycle rather than every
#: other one (the LAT-P159 lesson: a gate at or above its own beat halves the
#: real cadence).
STALE_AFTER_SECONDS = 45

#: How far back a live game can have started before we stop chasing it. Long
#: enough for a 97-minute rain delay plus a full extra-innings game.
MAX_GAME_AGE_HOURS = 10

#: Leagues that answered "probabilities are not supported". A league-level fact,
#: not a game-level one — ESPN says so in the 400 body — so one refusal retires
#: every game in that league for the life of the worker. Plain strings only
#: (gotcha #6: a module-global cache never holds live ORM rows).
_UNSUPPORTED_LEAGUES: set[str] = set()

#: event_id -> (point_count, home_win_probability), and ONLY for readings whose
#: write has been COMMITTED.
#:
#: CERT-653 [P1]: this used to advance the moment the reading was fetched. If the
#: write then failed, the next cycle saw an unchanged `point_count`, took the
#: cached value with `value_is_new=False`, re-stamped, and never appended the
#: chart point — so one transient database error permanently punched a hole in the
#: very curve this task exists to draw. A cache that says "we have this" is only
#: honest after the row is durable, so entries are promoted at the commit boundary
#: and dropped on rollback.
_LAST_READING: dict[int, tuple[int, float]] = {}

#: event_id -> consecutive 404s from ESPN. A 404 means THIS event id is unknown to
#: ESPN, which for a stale or wrong `espn_id` never resolves; three strikes retires
#: the event so it stops costing a request every minute. It never retires the
#: league (CERT-653 [P1] — that was the bug).
_EVENT_404_STRIKES: dict[int, int] = {}

#: Consecutive 404s before an event stops being probed. Not one: ESPN can 404 a
#: game briefly while its own feed opens.
MAX_EVENT_404_STRIKES = 3


def _reset_caches_for_test() -> None:
    """Clear the process-global memos. Tests only."""
    _UNSUPPORTED_LEAGUES.clear()
    _LAST_READING.clear()
    _EVENT_404_STRIKES.clear()


def _forget_finished_events(live_event_ids) -> None:
    """Drop cache entries for games that are no longer live.

    A worker that runs for weeks would otherwise accumulate one entry per game
    it ever saw. The live slate is the natural bound.
    """
    for cache in (_LAST_READING, _EVENT_404_STRIKES):
        for stale_id in [k for k in cache if k not in live_event_ids]:
            cache.pop(stale_id, None)


def _parse_stamp(raw):
    """`win_probability_sources.<source>.updated_at` as an aware datetime."""
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _espn_stamp_of(sources) -> str | None:
    """The stored ESPN write time, tolerating the legacy bare-number entry."""
    if not isinstance(sources, dict):
        return None
    entry = sources.get("espn")
    if not isinstance(entry, dict):
        return None
    return entry.get("updated_at")


def _candidate_query(now, limit: int):
    """Live espn_id-matched games, stalest ESPN reading first.

    Ordered NULLS FIRST so a game that has never had an ESPN reading — the MLB
    default — outranks one that merely went quiet. The staleness cut itself is
    applied in Python against the parsed stamp: a `::timestamptz` cast over the
    whole live slate would take the query down on the first malformed string it
    met, and this column has six independent writers.

    Columns, not entities, on purpose. The loop commits every few games so a
    cycle that hits the soft time limit keeps the work it already did, and gotcha
    #6 says a commit expires live ORM rows underneath a loop like this one. A Row
    of scalars survives it.
    """
    return (
        select(
            Event.id,
            Event.espn_id,
            Sport.key.label("sport_key"),
            Event.home_score,
            Event.away_score,
            Event.game_clock,
            Event.period,
            Event.win_probability_sources,
        )
        .join(Sport, Sport.id == Event.sport_id)
        .where(
            Event.status == "live",
            Event.espn_id.isnot(None),
            Event.commence_time <= now,
            Event.commence_time >= now - timedelta(hours=MAX_GAME_AGE_HOURS),
        )
        .order_by(
            Event.win_probability_sources["espn"]["updated_at"]
            .astext.asc()
            .nullsfirst()
        )
        .limit(limit)
    )


async def _sync_espn_live_win_probability(budget: int = DEFAULT_EVENT_BUDGET):
    """Refresh the ESPN win-probability reading on every stale live game."""
    from app.services.espn_api import ESPNAPIService

    stats = {
        "candidates": 0,
        "refreshed": 0,
        "value_changed": 0,
        "unchanged_reaffirmed": 0,
        "no_reading": 0,
        "unsupported_league": 0,
        "event_not_found": 0,
        "event_retired_404": 0,
        "already_fresh": 0,
        "over_budget": 0,
        "out_of_time": 0,
        "write_rollbacks": 0,
        "errors": [],
    }
    #: Readings written but NOT yet committed. Promoted into `_LAST_READING` only
    #: when the commit lands, dropped on rollback (CERT-653 [P1]).
    pending: dict[int, tuple[int, float]] = {}

    async def _commit(session):
        await session.commit()
        _LAST_READING.update(pending)
        pending.clear()

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(seconds=DEADLINE_SECONDS)
    stale_before = now - timedelta(seconds=STALE_AFTER_SECONDS)

    try:
        async with get_task_session() as session:
            # Over-fetch: rows skipped as fresh or as an unsupported league must
            # not eat a probe slot, or one soccer slate starves the whole budget.
            result = await session.execute(
                _candidate_query(now, limit=max(budget * 4, budget))
            )
            rows = result.all()
            stats["candidates"] = len(rows)
            _forget_finished_events({r.id for r in rows})
            if not rows:
                return {**stats, "status": "no_live_espn_events"}

            service = ESPNAPIService()
            probed = 0
            try:
                for row in rows:
                    sport_key = row.sport_key
                    if sport_key not in ESPN_SPORT_MAPPING:
                        continue
                    if sport_key in _UNSUPPORTED_LEAGUES:
                        stats["unsupported_league"] += 1
                        continue
                    if _EVENT_404_STRIKES.get(row.id, 0) >= MAX_EVENT_404_STRIKES:
                        stats["event_retired_404"] += 1
                        continue

                    stamp = _parse_stamp(_espn_stamp_of(row.win_probability_sources))
                    if stamp is not None and stamp > stale_before:
                        stats["already_fresh"] += 1
                        continue

                    if probed >= budget:
                        stats["over_budget"] += 1
                        continue
                    if datetime.now(timezone.utc) >= deadline:
                        stats["out_of_time"] += 1
                        continue

                    probed += 1
                    cached = _LAST_READING.get(row.id)
                    try:
                        reading = await service.get_live_win_probability(
                            sport_key,
                            row.espn_id,
                            known_point_count=cached[0] if cached else None,
                        )
                    except Exception as e:  # one game must never wipe the pass
                        stats["errors"].append(f"event_{row.id}: {str(e)[:80]}")
                        continue

                    if reading is None:
                        stats["no_reading"] += 1
                        continue

                    if not reading.supported:
                        _UNSUPPORTED_LEAGUES.add(sport_key)
                        stats["unsupported_league"] += 1
                        logger.info(
                            "ESPN publishes no win probability for %s — retiring the "
                            "league for this worker", sport_key,
                        )
                        continue

                    if reading.event_missing:
                        # ESPN does not know THIS id. Never the league.
                        strikes = _EVENT_404_STRIKES.get(row.id, 0) + 1
                        _EVENT_404_STRIKES[row.id] = strikes
                        stats["event_not_found"] += 1
                        if strikes >= MAX_EVENT_404_STRIKES:
                            logger.warning(
                                "ESPN has 404'd event %s (espn_id=%s, %s) %d times — "
                                "retiring this EVENT, not the league. A wrong espn_id "
                                "is the usual cause.",
                                row.id, row.espn_id, sport_key, strikes,
                            )
                        continue
                    _EVENT_404_STRIKES.pop(row.id, None)

                    home_wp = reading.home_win_probability
                    if home_wp is None:
                        # The feed has not moved since our last read. Re-affirm
                        # the cached value: a source still reporting the same
                        # number is not a source that stopped reporting.
                        if cached is None:
                            stats["no_reading"] += 1
                            continue
                        home_wp = cached[1]
                        value_is_new = False
                    else:
                        home_wp = round(float(home_wp), 4)
                        value_is_new = cached is None or cached[1] != home_wp

                    try:
                        await _write_reading(
                            session, row, home_wp, value_is_new=value_is_new,
                        )
                    except Exception as e:
                        # A Postgres statement error aborts the TRANSACTION, so
                        # without this rollback every later game in the slate dies
                        # on `InFailedSQLTransaction` — one bad write becomes a
                        # wiped pass, which is the gotcha #42 class the per-item
                        # try/except was supposed to prevent. The rollback also
                        # discards the uncommitted writes since the last commit,
                        # so `pending` is dropped with them: those games must be
                        # re-read and re-written, not remembered as done.
                        stats["errors"].append(f"write_{row.id}: {str(e)[:80]}")
                        stats["write_rollbacks"] += 1
                        pending.clear()
                        try:
                            await session.rollback()
                        except Exception as rb:
                            stats["errors"].append(f"rollback: {str(rb)[:80]}")
                            raise
                        continue

                    # Only now, and still only provisionally — the commit promotes it.
                    if reading.point_count is not None:
                        pending[row.id] = (reading.point_count, home_wp)

                    stats["refreshed"] += 1
                    if value_is_new:
                        stats["value_changed"] += 1
                    else:
                        stats["unchanged_reaffirmed"] += 1

                    if stats["refreshed"] % COMMIT_EVERY == 0:
                        await _commit(session)

                await _commit(session)
            finally:
                await service.close()

    except Exception as e:
        logger.warning("ESPN live win-prob sync error: %s", e, exc_info=True)
        stats["errors"].append(f"task_error: {str(e)[:200]}")

    if stats["over_budget"] or stats["out_of_time"]:
        # Never a silent cap: a trimmed slate reads as a covered slate.
        logger.warning(
            "ESPN live win-prob: %d stale live games NOT refreshed this cycle "
            "(%d over the %d-game budget, %d past the %.0fs deadline)",
            stats["over_budget"] + stats["out_of_time"],
            stats["over_budget"], budget, stats["out_of_time"], DEADLINE_SECONDS,
        )
    return stats


#: Merge ONE source key server-side instead of writing back a dict we read.
#:
#: Every other writer of `win_probability_sources` does read-modify-write through
#: `stamp_source_reading` and gets away with it because it reads and writes in the
#: same breath. This task cannot: it selects the whole live slate up front and
#: then spends up to 1.77 s of network per game, so a row picked up late in the
#: cycle was read tens of seconds ago — and in those seconds Kalshi (p50 age
#: 7.4 s) and the betting line (23.1 s) have both written. Writing our
#: remembered dict back would silently roll their readings backwards, once a
#: minute, on exactly the live games this queue exists to keep fresh.
#:
#: `CAST(:entry AS jsonb)` and not `:entry::jsonb` — asyncpg reads `::` as the
#: start of a bind parameter.
_MERGE_ESPN_SOURCE = text("""
    UPDATE events
    SET win_probability_sources = jsonb_set(
            COALESCE(win_probability_sources, '{}'::jsonb),
            '{espn}',
            CASE
                WHEN jsonb_typeof(win_probability_sources -> 'espn') = 'object'
                    THEN (win_probability_sources -> 'espn') || CAST(:entry AS jsonb)
                ELSE CAST(:entry AS jsonb)
            END,
            true
        ),
        espn_win_prob_home = :home
    WHERE id = :event_id
""")


def espn_source_entry(home_wp: float, now=None) -> dict:
    """The `win_probability_sources.espn` entry this task writes.

    Kept byte-identical to what `stamp_source_reading` produces, and pinned to it
    by a guard, because that function's docstring asks every writer of this
    column to route through it and this one deliberately does not (see
    `_MERGE_ESPN_SOURCE` for why). Same shape, different transport.
    """
    return stamp_source_reading({}, "espn", home_wp, now=now)["espn"]


async def _write_reading(session, row, home_wp: float, value_is_new: bool):
    """Persist one reading: the blend stamp, and — if it moved — the chart point.

    The stamp is written on EVERY refresh; the two time-series rows only when the
    value actually moved. A repeated point at the same probability adds nothing
    to a line chart, and `_create_or_update_win_prob_snapshot` would dedup it
    anyway — but the stamp is what the hero's relative-age decay reads, and
    withholding it is what made a still-reporting source look dead.
    """
    from app.models.models import ESPNSnapshot
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot

    away_wp = round(1.0 - home_wp, 4)

    await session.execute(
        _MERGE_ESPN_SOURCE,
        {
            "entry": json.dumps(espn_source_entry(home_wp)),
            "home": home_wp,
            "event_id": row.id,
        },
    )

    if not value_is_new:
        return

    session.add(
        ESPNSnapshot(
            event_id=row.id,
            home_win_probability=home_wp,
            away_win_probability=away_wp,
            home_score=row.home_score,
            away_score=row.away_score,
            game_clock=row.game_clock,
            period=row.period,
        )
    )

    snapshot, is_new = await _create_or_update_win_prob_snapshot(
        session,
        event_id=row.id,
        source="espn",
        home_win_probability=home_wp,
        away_win_probability=away_wp,
        game_state={
            "clock": row.game_clock,
            "period": row.period,
            "home_score": row.home_score,
            "away_score": row.away_score,
            "feed": "espn_core_probabilities",
        },
        is_completed=False,
    )
    if is_new:
        session.add(snapshot)
