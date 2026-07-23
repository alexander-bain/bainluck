"""#1201 — MLB schedule-coverage check: the sentinel side of the schedule-diff.

Fetches the official MLB schedule for a date and reconciles it against our
events using the pure classifier in ``app/utils/schedule_diff.py``. The invariant
it asserts is **every official MLB game that day ↔ exactly one of our events**;
it also surfaces ``premature_settle`` (the #1193/#1201 rot) and ``postponed``
state divergences.

Read-only (it never mutates events — applying the transitions is a separate,
gated path). Fails soft: if statsapi is unreachable it returns ``skipped=True``,
never a false alarm. Exposed on-demand via the admin route so ops/Fable can prove
"today's slate clean" without waiting for a beat.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def run_mlb_schedule_coverage(date: Optional[str] = None) -> dict:
    """Reconcile the official MLB schedule for ``date`` (YYYY-MM-DD, default
    today UTC) against our events. Returns a verdict dict:

        {checked, passed, skipped, transitions: [...], counts: {...}, date}
    """
    from sqlalchemy import select, text  # noqa: F401

    from app.models.models import Event, Sport, Team
    from app.services.mlb_api import MLBAPIService
    from app.tasks.base import get_task_session
    from app.utils.schedule_diff import diff_schedule, normalize_official_game

    now = datetime.now(timezone.utc)
    day = date or now.strftime("%Y-%m-%d")

    service = MLBAPIService()
    try:
        raw_games = await service.get_todays_games(date=day)
    except Exception as exc:
        logger.warning("MLB schedule fetch failed for %s: %s", day, exc)
        return {"flow": "mlb_schedule_coverage", "date": day, "checked": 0,
                "passed": True, "skipped": True,
                "evidence": {"reason": f"statsapi unreachable: {str(exc)[:120]}"}}
    finally:
        await service.close()

    if not raw_games:
        # An empty official slate (off-day) is not a failure.
        return {"flow": "mlb_schedule_coverage", "date": day, "checked": 0,
                "passed": True, "skipped": True,
                "evidence": {"reason": "no official MLB games on this date"}}

    official = [normalize_official_game(g) for g in raw_games]

    # Our MLB events for the same UTC day (±18h to cover boundary crossings), the
    # same window audit_event_counts uses.
    day_noon = datetime.strptime(day, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
    our_events: list[dict] = []
    async with get_task_session() as s:
        rows = (await s.execute(
            select(Event.id, Event.status, Team.name.label("home"),
                   Sport.key.label("sport"))
            .join(Sport, Sport.id == Event.sport_id)
            .outerjoin(Team, Team.id == Event.home_team_id)
            .where(
                Sport.key.in_(["baseball_mlb", "baseball_mlb_preseason"]),
                Event.commence_time.between(day_noon - timedelta(hours=18),
                                            day_noon + timedelta(hours=18)),
            )
        )).all()
        # Second pass for away names (kept separate to avoid a double outerjoin alias).
        ev_map = {r.id: {"id": r.id, "status": r.status, "home_team": r.home or "",
                         "away_team": ""} for r in rows}
        if ev_map:
            away_rows = (await s.execute(
                select(Event.id, Team.name.label("away"))
                .outerjoin(Team, Team.id == Event.away_team_id)
                .where(Event.id.in_(list(ev_map.keys())))
            )).all()
            for ar in away_rows:
                if ar.id in ev_map:
                    ev_map[ar.id]["away_team"] = ar.away or ""
        our_events = list(ev_map.values())

    transitions = diff_schedule(official, our_events, now=now)
    counts: dict[str, int] = {}
    for t in transitions:
        counts[t.kind] = counts.get(t.kind, 0) + 1

    failures = [
        {"kind": t.kind, "detail": t.detail, "game_pk": t.game_pk,
         "event_ids": t.event_ids}
        for t in transitions
    ]
    return {
        "flow": "mlb_schedule_coverage",
        "date": day,
        "checked": len(official),
        "our_events": len(our_events),
        "passed": len(failures) == 0,
        "skipped": False,
        "counts": counts,
        "failures": failures,
    }


# ---------------------------------------------------------------------------
# #1201/#1193 self-heal — repair the standing inverted / future-settled MLB rows.
#
# The resolved_state Flow Sentinel goes RED on MLB events that are settled but
# violate ``completed_at >= commence_time`` (gotcha #32/#46): commence_time is in
# the FUTURE, or completed_at PRECEDES commence_time. These are cross-merged rows
# (an earlier game's terminal state folded onto a later sibling via a collapsed
# commence_time) or a postponed game closed by the staleness net and later
# rescheduled. The durable *prevention* already ships (the ESPN write-side fold
# guards + the un-settle-on-replay branch in ``espn_helpers.py``). This heals the
# rows corrupted BEFORE those guards existed, and — wired to the daily beat below
# — keeps healing any that slip through, using the free MLB Stats API as ground
# truth. It is the importable core; ``scripts/repair_inverted_mlb_events.py`` is a
# thin CLI over it. Bounded (MLB + invariant-violating rows only), evidence-logged
# per row, Core SQL, and never touches is_winner / calibration (gotcha #21).
# ---------------------------------------------------------------------------

# Settled MLB rows that violate the invariant: settled but commence in the future
# OR completed_at before commence_time. Pull scores + ids to classify scored-vs-
# empty and re-date via ground truth.
_INVERTED_CANDIDATE_SQL = """
    SELECT e.id, e.status, e.commence_time, e.completed_at,
           e.home_score AS hs, e.away_score AS aws,
           ht.name AS home_team, at.name AS away_team
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    LEFT JOIN teams ht ON ht.id = e.home_team_id
    LEFT JOIN teams at ON at.id = e.away_team_id
    WHERE s.key IN ('baseball_mlb', 'baseball_mlb_preseason')
      AND e.status IN ('completed', 'closed')
      AND (
          e.commence_time > (now() at time zone 'utc')
          OR (e.completed_at IS NOT NULL AND e.completed_at < e.commence_time)
      )
    ORDER BY e.commence_time
"""


def _repair_tokens(s) -> set:
    return set((s or "").lower().replace(".", "").split())


def _repair_teams_match(our_home, our_away, mlb_home, mlb_away) -> bool:
    """True if our (home, away) matches the MLB game in either orientation."""
    hh = bool(_repair_tokens(our_home) & _repair_tokens(mlb_home))
    aa = bool(_repair_tokens(our_away) & _repair_tokens(mlb_away))
    hswap = bool(_repair_tokens(our_home) & _repair_tokens(mlb_away))
    aswap = bool(_repair_tokens(our_away) & _repair_tokens(mlb_home))
    return (hh and aa) or (hswap and aswap)


def _repair_as_utc(dt):
    """Coerce a datetime to tz-aware UTC (naive -> assume UTC)."""
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _classify_scored_inverted(completed_at, commence_time, new_start) -> str:
    """Decide the repair action for a SCORED inverted row, given the confirmed MLB
    Final start (all args tz-aware UTC or None):

    * ``redate``  — commence was the wrong (future) field: the Final's start is
      <= completed_at, so re-dating commence to it restores the invariant.
    * ``fix_end`` — completed_at is the corrupt pre-first-pitch field: commence
      already matches the Final start (within 6h), so completed_at must move to the
      game end. The dominant standing class.
    * ``review``  — neither holds; unsafe to auto-repair.

    Pure and side-effect free so the boundary is unit-testable without a DB."""
    if completed_at is None or new_start <= completed_at:
        return "redate"
    if commence_time is not None and abs(
            (new_start - commence_time).total_seconds()) <= 6 * 3600:
        return "fix_end"
    return "review"


async def _mlb_final_for(service, home, away, hs, aws, around_date):
    """Find the real MLB game (Final) matching our teams + score within ±1 day of
    ``around_date``. Returns (game_datetime_iso, mlb_home, mlb_away) or None.

    Score match is orientation-aware: accept either {hs,aws} == {mlbHome,mlbAway}
    score set so a home/away swap in our row doesn't cause a miss."""
    want_scores = sorted([s for s in (hs, aws) if s is not None])
    for delta in (0, -1, 1):
        day = (around_date + timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            games = await service.get_todays_games(date=day)
        except Exception:
            continue
        for g in games:
            state = (g.get("status", {}) or {}).get("detailedState", "")
            if state not in ("Final", "Game Over", "Completed Early"):
                continue
            teams = g.get("teams", {}) or {}
            mh = (teams.get("home", {}) or {}).get("team", {}).get("name", "")
            ma = (teams.get("away", {}) or {}).get("team", {}).get("name", "")
            if not _repair_teams_match(home, away, mh, ma):
                continue
            mhs = (teams.get("home", {}) or {}).get("score")
            mas = (teams.get("away", {}) or {}).get("score")
            got_scores = sorted([s for s in (mhs, mas) if s is not None])
            if want_scores and got_scores and want_scores != got_scores:
                continue
            return (g.get("gameDate"), mh, ma)
    return None


async def repair_inverted_mlb_events(apply: bool = True) -> dict:
    """Heal (re-date / fix-completed_at / void) the standing inverted / future-
    settled MLB rows. Every write is gated on an MLB ground-truth Final matching
    the row's teams AND final score — never a blind write.

    * SCORED, commence wrong -> re-date. completed_at + score belong to a REAL
      finished game; commence_time points at the wrong (future) sibling. The MLB
      Final's start is <= completed_at, so set commence_time to it and the invariant
      (completed_at >= commence_time) holds.
    * SCORED, completed_at wrong -> fix completed_at. commence_time + score already
      match the confirmed MLB Final (start within 6h of commence), but completed_at
      was set BEFORE first pitch (the dominant standing class — a stale/mis-merged
      terminal timestamp). Move completed_at to the game end (start + nominal 9-inning
      duration) so the invariant holds. Score / is_winner untouched (gotcha #21).
    * 0-0 / NULL-score rows -> void the settle (status->scheduled, completed_at/
      scores->NULL). The normal pipeline re-settles it once it actually plays.
    * Anything unverifiable vs MLB ground truth is LOGGED and SKIPPED.

    Returns ``{candidates, redate, fix_end, void, review, applied}``. Idempotent.
    """
    from sqlalchemy import text

    from app.services.mlb_api import MLBAPIService
    from app.tasks.base import get_task_session

    now = datetime.now(timezone.utc)
    service = MLBAPIService()

    redate: list = []   # (id, old_commence_iso, new_commence_iso, evidence)
    fix_end: list = []  # (id, old_completed_iso, new_completed_iso, evidence)
    void: list = []     # (id, reason)
    review: list = []    # (id, reason)
    candidates = 0

    try:
        async with get_task_session() as s:
            rows = (await s.execute(text(_INVERTED_CANDIDATE_SQL))).all()
            candidates = len(rows)
            logger.info(
                "repair_inverted_mlb: %d resolved_state-failing MLB rows", candidates
            )

            for r in rows:
                scored = (r.hs is not None and r.aws is not None
                          and not (r.hs == 0 and r.aws == 0))
                if not scored:
                    void.append((r.id, "empty/0-0 score, settled before a real result"))
                    continue

                # Find the real MLB Final for this matchup+score. Anchor on
                # completed_at first; when completed_at is the CORRUPT field the
                # Final sits at commence_time instead, so fall back to that anchor.
                res = await _mlb_final_for(
                    service, r.home_team, r.away_team, r.hs, r.aws,
                    _repair_as_utc(r.completed_at or now),
                )
                if not res and r.commence_time is not None:
                    res = await _mlb_final_for(
                        service, r.home_team, r.away_team, r.hs, r.aws,
                        _repair_as_utc(r.commence_time),
                    )
                if not res:
                    review.append((r.id, "scored but no matching MLB Final"))
                    continue
                new_start_iso, mh, ma = res
                new_start = datetime.fromisoformat(new_start_iso.replace("Z", "+00:00"))
                ev = f"MLB Final {mh} v {ma} @ {new_start_iso}"
                completed_utc = _repair_as_utc(r.completed_at) if r.completed_at else None
                commence_utc = _repair_as_utc(r.commence_time) if r.commence_time else None

                action = _classify_scored_inverted(completed_utc, commence_utc, new_start)
                if action == "redate":
                    # commence was the wrong (future) field; completed_at is a real
                    # post-game timestamp. Re-date commence to the confirmed start.
                    redate.append((r.id, r.commence_time.isoformat(), new_start_iso, ev))
                elif action == "fix_end":
                    # commence already matches the confirmed Final start — completed_at
                    # is the corrupt pre-first-pitch field. Move completed_at to the
                    # game end (start + nominal 9-inning duration). Score / is_winner
                    # untouched (gotcha #21).
                    new_end = new_start + timedelta(hours=3, minutes=15)
                    fix_end.append((r.id, r.completed_at.isoformat(), new_end.isoformat(),
                                    f"{ev}; commence correct, completed_at was pre-start"))
                else:
                    review.append((r.id, f"ambiguous: Final start {new_start_iso} "
                                          "neither after commence nor at commence"))

            ledger = {
                "candidates": candidates,
                "redate": len(redate),
                "fix_end": len(fix_end),
                "void": len(void),
                "review": len(review),
                "applied": False,
            }

            if apply and (redate or fix_end or void):
                for eid, _old, new_iso, _ev in redate:
                    await s.execute(
                        text("UPDATE events SET commence_time = :c, "
                             "commence_time_source = 'mlb_schedule_repair' WHERE id = :id"),
                        {"c": datetime.fromisoformat(new_iso.replace("Z", "+00:00")), "id": eid},
                    )
                for eid, _old, new_iso, _ev in fix_end:
                    await s.execute(
                        text("UPDATE events SET completed_at = :c WHERE id = :id"),
                        {"c": datetime.fromisoformat(new_iso.replace("Z", "+00:00")), "id": eid},
                    )
                for eid, _reason in void:
                    await s.execute(
                        text("UPDATE events SET status = 'scheduled', completed_at = NULL, "
                             "home_score = NULL, away_score = NULL WHERE id = :id"),
                        {"id": eid},
                    )
                await s.commit()
                ledger["applied"] = True
                logger.info(
                    "repair_inverted_mlb: APPLIED re-date %d, fix-completed_at %d, void %d "
                    "(%d review, is_winner untouched)",
                    len(redate), len(fix_end), len(void), len(review))
            return ledger
    finally:
        await service.close()


async def run_mlb_schedule_coverage_and_repair() -> dict:
    """Daily beat entry point (#1201/#1193/#1202): self-heal the standing inverted
    MLB rows, then run the read-only coverage check so the 07:10 Flow Sentinel and
    the cockpit read a clean, freshly-reconciled slate. Both halves are best-effort
    and independent; a failure in one never suppresses the other."""
    result: dict = {}
    try:
        result["repair"] = await repair_inverted_mlb_events(apply=True)
    except Exception as exc:  # heal is best-effort; still run detection
        logger.warning("repair_inverted_mlb_events failed: %s", exc)
        result["repair"] = {"error": str(exc)[:200]}
    try:
        result["coverage"] = await run_mlb_schedule_coverage()
    except Exception as exc:
        logger.warning("run_mlb_schedule_coverage failed: %s", exc)
        result["coverage"] = {"error": str(exc)[:200]}
    return result
