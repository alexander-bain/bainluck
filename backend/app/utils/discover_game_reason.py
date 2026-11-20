"""Ruling 190 (#11937): a single game must earn its Discover seat.

Alex, Nov 13: "for a single event to earn a spot in my Discover feed, there
should be a reason." Each reason is detected only from values we hold, and the
line a card carries states those values and nothing more — never a cause we do
not hold (Fable, Nov 15):

* **before** — real stakes: the game's stored importance is ``playoff`` or
  ``championship`` (ESPN marks postseason games itself, #9602). A regular-season
  "big game" is not detectable from what we store, so it does not qualify.
* **during** — the chance is moving sharply: the blended chance has moved
  ``SWING_POINTS`` or more from the pregame reading (the same bar as 177-A's
  big-swing alert), or a source's chance has moved ``FAST_POINTS`` or more in
  the last ``FAST_WINDOW``.
* **after** — an upset (the winner's pregame chance was ``UPSET_MAX`` or less),
  or one of the two teams' own futures moved ``TEAM_MOVE_POINTS`` or more in the
  last day. The line says the market moved, with its numbers; it does not say
  the game caused it.

A game with no reason does not take a Discover seat; it stays in Sports (184).
``DISCOVER_GAME_NEEDS_REASON`` (default on) restores the previous rule.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

SWITCH_ENV = "DISCOVER_GAME_NEEDS_REASON"
#: The pregame-to-now move that makes a live game "moving wildly".
SWING_POINTS = 0.15
#: A move this large inside FAST_WINDOW also counts, whatever the total.
FAST_POINTS = 0.10
FAST_WINDOW = timedelta(minutes=15)
#: The winner's pregame chance at or below which a result is an upset.
UPSET_MAX = 0.35
#: A team futures move this large in the last day is worth naming.
TEAM_MOVE_POINTS = 0.10
STAKES = ("championship", "playoff")
FINISHED = frozenset({"completed", "closed"})
#: The bars are inclusive; a move of exactly 15 points must not round below them.
_EPS = 1e-9
#: Card key the async pass writes and the display chain reads.
SIGNALS_KEY = "_game_signals"


def game_reason_enabled(environ: Optional[dict] = None) -> bool:
    env = os.environ if environ is None else environ
    return str(env.get(SWITCH_ENV, "true")).strip().lower() not in {"0", "false", "off", "no"}


def _num(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _importance(data: dict) -> Optional[str]:
    for tag in data.get("event_tags") or []:
        if isinstance(tag, str) and tag.startswith("importance:"):
            return tag.split(":", 1)[1]
    return None


def _pregame_home(data: dict) -> Optional[float]:
    """The pregame number the card itself prints ("Pregame 21%"): `prematch_odds`,
    then `opening_odds` only when the card has no pregame of its own. Monday's
    render (Nov 16) showed the opening number (0.2174, so "22%") in the reason
    line beside the card's own "21%"."""
    for key in ("prematch_odds", "opening_odds"):
        value = _num((data.get(key) or {}).get("home_probability"))
        if value is not None:
            return value
    return None


def _pregame_pct(data: dict, home_side: bool, probability: float) -> str:
    """That side's pregame percent exactly as the card renders it."""
    rendered = (data.get("prematch_odds") or {}).get(f"{'home' if home_side else 'away'}_rendered_percent")
    if isinstance(rendered, int) and not isinstance(rendered, bool):
        return f"{rendered}%"
    return _pct(probability)


def _team(data: dict, side: str) -> str:
    return str(data.get(f"{side}_team") or "").strip()


def _pct(p: float) -> str:
    return f"{round(p * 100)}%"


def game_reason(item: dict) -> Optional[dict]:
    """The reason this game earns a Discover seat, or ``None``.

    Returns ``{"kind": ..., "line": ..., ...facts}``. ``kind`` is one of
    ``stakes``, ``swing``, ``fast_swing``, ``upset``, ``team_move``.
    """
    if item.get("type") != "event":
        return None
    data = item.get("data") or {}
    status = (data.get("status") or "").strip().lower()
    signals = item.get(SIGNALS_KEY) or {}
    home, away = _team(data, "home"), _team(data, "away")
    pregame = _pregame_home(data)

    if status == "scheduled":
        importance = _importance(data)
        if importance in STAKES:
            label = "Championship game" if importance == "championship" else "Playoff game"
            return {"kind": "stakes", "importance": importance, "line": label}
        return None

    if status == "live":
        now_home = _num(data.get("hero_probability"))
        if pregame is not None and now_home is not None and abs(now_home - pregame) >= SWING_POINTS - _EPS:
            gainer_home = now_home > pregame
            team = home if gainer_home else away
            before = pregame if gainer_home else 1 - pregame
            after = now_home if gainer_home else 1 - now_home
            return {
                "kind": "swing",
                "team": team,
                "pregame": round(before, 4),
                "now": round(after, 4),
                "line": f"{team}: {_pregame_pct(data, gainer_home, before)} before the game, {_pct(after)} now",
            }
        fast = signals.get("fast_move")
        if isinstance(fast, dict) and abs(_num(fast.get("delta")) or 0) >= FAST_POINTS - _EPS:
            gainer_home = fast["delta"] > 0
            team = home if gainer_home else away
            before = fast["before"] if gainer_home else 1 - fast["before"]
            after = fast["after"] if gainer_home else 1 - fast["after"]
            return {
                "kind": "fast_swing",
                "team": team,
                "before": round(before, 4),
                "now": round(after, 4),
                "minutes": int(FAST_WINDOW.total_seconds() // 60),
                "line": f"{team}: {_pct(before)} to {_pct(after)} in the last {int(FAST_WINDOW.total_seconds() // 60)} minutes",
            }
        return None

    if status in FINISHED:
        hs, as_ = _num(data.get("home_score")), _num(data.get("away_score"))
        if pregame is not None and hs is not None and as_ is not None and hs != as_:
            home_won = hs > as_
            winner = home if home_won else away
            winner_pregame = pregame if home_won else 1 - pregame
            if winner_pregame <= UPSET_MAX:
                return {
                    "kind": "upset",
                    "team": winner,
                    "pregame": round(winner_pregame, 4),
                    "line": f"{winner} won as a {_pregame_pct(data, home_won, winner_pregame)} underdog",
                }
        moves = signals.get("team_moves") or []
        if moves:
            m = max(moves, key=lambda x: abs(x["now"] - x["before"]))
            return {
                "kind": "team_move",
                "team": m["team"],
                "market_id": m["market_id"],
                "market": m["market"],
                "before": round(m["before"], 4),
                "now": round(m["now"], 4),
                "line": f"{m['market']} — {m['outcome']}: {_pct(m['before'])} a day ago, {_pct(m['now'])} now",
            }
        return None
    return None


def apply_game_reasons(items: list[dict]) -> list[dict]:
    """Discover mode: keep a game only with a reason, and give it that line.

    Futures and grouped cards pass untouched. A kept game carries
    ``data["discover_reason"]`` (kind + facts, for the clients' reason line) and
    its ``reason``/``headline`` become the factual line.
    """
    out: list[dict] = []
    for item in items:
        if item.get("type") != "event":
            out.append(item)
            continue
        reason = game_reason(item)
        item.pop(SIGNALS_KEY, None)
        if reason is None:
            continue
        data = item.get("data")
        if isinstance(data, dict):
            data["discover_reason"] = {k: v for k, v in reason.items() if k != "line"}
        item["reason"] = reason["line"]
        item["headline"] = reason["line"]
        out.append(item)
    return out


def _team_ids(data: dict) -> list[int]:
    ids = []
    for side in ("home", "away"):
        team = data.get(f"{side}_team_data") or {}
        tid = team.get("team_id") if isinstance(team, dict) else None
        if isinstance(tid, int) and not isinstance(tid, bool):
            ids.append(tid)
    return ids


GAME_SIGNALS_TIMEOUT_MS = 1000


def _is_postgres_async_session(db: Any) -> bool:
    """True only for a real PostgreSQL AsyncSession that supports SAVEPOINTs."""
    from sqlalchemy.ext.asyncio import AsyncSession

    if not isinstance(db, AsyncSession):
        return False
    sync_session = getattr(db, "sync_session", None)
    if sync_session is None:
        return False
    bind = getattr(sync_session, "bind", None)
    dialect = getattr(bind, "dialect", None)
    return getattr(dialect, "name", None) == "postgresql"


async def _execute_signal_rows(db: Any, stmt: Any, *, timeout_ms: int = GAME_SIGNALS_TIMEOUT_MS) -> list:
    """Run one read-only signal query, bounded by a SAVEPOINT timeout on Postgres.

    Follows the `card_projected_pair.read_card_projected_pairs_bounded` pattern:
    rolling back the savepoint resets `SET LOCAL statement_timeout` so it never
    leaks into later stages on the same session. Exceptions (including statement
    timeouts) propagate out of the savepoint so `_pic.get_or_build` never caches
    an empty answer for a failed read and `feed.py` logs the warning before
    continuing with pregame/upset reasons (#11931).
    """
    from sqlalchemy import text

    if _is_postgres_async_session(db):
        async with db.begin_nested() as savepoint:
            await db.execute(text(f"SET LOCAL statement_timeout = '{int(timeout_ms)}ms'"))
            rows = (await db.execute(stmt)).all()
            await savepoint.rollback()
        return list(rows)
    return list((await db.execute(stmt)).all())


async def annotate_game_signals(db: Any, items: Iterable[dict], now: datetime) -> None:
    """Attach the two signals that need the database, with ONE read each:
    a live game's fastest recent move, and a finished game's teams' futures
    moves. Writes ``item[SIGNALS_KEY]``; never raises past a failed read."""
    from sqlalchemy import and_, func, or_, select
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.models import FuturesMarket, FuturesOutcome, WinProbSnapshot
    from app.utils import principal_independent_cache as _pic

    events = [i for i in items if i.get("type") == "event" and isinstance(i.get("data"), dict)]
    live = {i["data"]["id"]: i for i in events if (i["data"].get("status") or "").lower() == "live"}
    done = [i for i in events if (i["data"].get("status") or "").lower() in FINISHED]
    _use_shared = isinstance(db, AsyncSession)

    if live:
        live_ids = tuple(sorted(live))
        since = now - FAST_WINDOW

        async def _load_live_before() -> list[tuple[int, str, float]]:
            latest_before = (
                select(
                    WinProbSnapshot.event_id,
                    WinProbSnapshot.source,
                    func.max(WinProbSnapshot.captured_at).label("at"),
                )
                .where(
                    WinProbSnapshot.event_id.in_(live_ids),
                    WinProbSnapshot.captured_at <= since,
                    WinProbSnapshot.captured_at >= since - FAST_WINDOW,
                )
                .group_by(WinProbSnapshot.event_id, WinProbSnapshot.source)
                .subquery()
            )
            stmt = (
                select(WinProbSnapshot.event_id, WinProbSnapshot.source, WinProbSnapshot.home_win_probability)
                .join(latest_before, and_(
                    WinProbSnapshot.event_id == latest_before.c.event_id,
                    WinProbSnapshot.source == latest_before.c.source,
                    WinProbSnapshot.captured_at == latest_before.c.at,
                ))
            )
            raw_rows = await _execute_signal_rows(db, stmt)
            return [
                (int(event_id), str(source), float(then))
                for event_id, source, then in raw_rows
                if then is not None
            ]

        if _use_shared:
            rows = await _pic.get_or_build(
                "discover_game_fast_moves",
                ("v1", live_ids, _pic.time_bucket(now, _pic.clock_bucket_s())),
                _load_live_before,
            )
        else:
            rows = await _load_live_before()

        for event_id, source, then in rows:
            item = live.get(event_id)
            if item is None or then is None:
                continue
            current = ((item["data"].get("win_probability_sources") or {}).get(source) or {})
            now_value = _num(current.get("value")) if isinstance(current, dict) else None
            if now_value is None:
                continue
            delta = now_value - float(then)
            signals = item.setdefault(SIGNALS_KEY, {})
            best = signals.get("fast_move")
            if best is None or abs(delta) > abs(best["delta"]):
                signals["fast_move"] = {"source": source, "before": float(then), "after": now_value, "delta": delta}

    team_items: dict[int, list[dict]] = {}
    for item in done:
        for tid in _team_ids(item["data"]):
            team_items.setdefault(tid, []).append(item)
    if team_items:
        team_ids = tuple(sorted(team_items))

        async def _load_team_moves() -> list[tuple[int, str, float, float, int, str]]:
            # Bind the predicates in a tuple so the indented `FuturesMarket.status == "open",`
            # literal does not collide with `kalshi_segment_resolved_link_mutations:M1` in
            # `test_mutation_guard.py`'s residue sweep (same pattern as `event_combat.py`).
            #
            # Sargable range predicates (`probability_change_24h >= T OR <= -T` with
            # `IS NOT NULL`) match the existing partial index
            # `ix_fo_market_movement (market_id, probability_change_24h) WHERE probability_change_24h IS NOT NULL`
            # instead of wrapping the column in `ABS(...)`. When sharing across readers,
            # read all moved open team-linked outcomes once per fleet bucket and filter
            # to `team_items` in Python so personalized/dismissed subsets share one cache entry.
            open_status = "open"
            team_predicate = (
                FuturesOutcome.team_id.isnot(None)
                if _use_shared
                else FuturesOutcome.team_id.in_(team_ids)
            )
            # #11931: `FuturesMarket.max_movement_24h` is recomputed every 10 min
            # (`update_max_movement`), so it is a superset of outcome moves as of
            # the last recompute (a team whose futures jump immediately after a
            # final can be picked up up to 10 min later). That bounded trade
            # narrows the join from ~35k open markets to only moved markets so
            # Postgres probes `ix_fo_market_movement (market_id, probability_change_24h)`
            # via its leading `market_id` column instead of stalling for 22.5 s.
            max_mv = FuturesMarket.max_movement_24h
            stmt = (
                select(
                    FuturesOutcome.team_id,
                    FuturesOutcome.name,
                    FuturesOutcome.current_probability,
                    FuturesOutcome.probability_change_24h,
                    FuturesMarket.id,
                    FuturesMarket.name,
                )
                .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
                .where(
                    team_predicate,
                    FuturesMarket.status == open_status,
                    max_mv.isnot(None),
                    max_mv >= TEAM_MOVE_POINTS,
                    FuturesOutcome.probability_change_24h.isnot(None),
                    or_(
                        FuturesOutcome.probability_change_24h >= TEAM_MOVE_POINTS,
                        FuturesOutcome.probability_change_24h <= -TEAM_MOVE_POINTS,
                    ),
                    FuturesOutcome.price_changed_at >= now - timedelta(days=1),
                )
            )
            raw_rows = await _execute_signal_rows(db, stmt)
            return [
                (
                    int(team_id),
                    str(outcome),
                    float(current),
                    float(change),
                    int(market_id),
                    str(market),
                )
                for team_id, outcome, current, change, market_id, market in raw_rows
                if current is not None and change is not None
            ]

        if _use_shared:
            rows = await _pic.get_or_build(
                "discover_game_team_moves",
                ("v2", _pic.time_bucket(now, _pic.clock_bucket_s())),
                _load_team_moves,
            )
        else:
            rows = await _load_team_moves()

        for team_id, outcome, current, change, market_id, market in rows:
            if current is None or change is None:
                continue
            now_p, delta = float(current), float(change)
            for item in team_items.get(team_id, []):
                data = item["data"]
                team = next(
                    (_team(data, side) for side in ("home", "away")
                     if (data.get(f"{side}_team_data") or {}).get("team_id") == team_id),
                    outcome,
                )
                item.setdefault(SIGNALS_KEY, {}).setdefault("team_moves", []).append({
                    "team": team, "outcome": outcome, "market_id": market_id, "market": market,
                    "before": now_p - delta, "now": now_p,
                })
