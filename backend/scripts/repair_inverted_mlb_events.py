"""#1201/#1193 — one-shot repair of the standing inverted/future-settled MLB events.

The resolved_state Flow Sentinel goes RED on MLB events that are settled
(status completed/closed) but violate the ``completed_at >= commence_time``
invariant (gotcha #32/#46): either commence_time is in the FUTURE, or
completed_at PRECEDES commence_time. These are cross-merged rows — an earlier
game's terminal state folded onto a later (future) sibling via the collapsed
commence_time, or a postponed game closed by the staleness net and later
rescheduled.

The durable prevention is already deployed (the ESPN write-side fold guards +
the #1201 un-settle-on-replay branch in ``espn_helpers.py``). This script heals
the rows that were corrupted BEFORE those guards existed, using the free MLB
Stats API (statsapi.mlb.com) as ground truth — the same method r242 used:

  * SCORED rows  -> re-date. The stored completed_at + score belong to a REAL
    finished game; commence_time points at the wrong (future) sibling. We look
    up the actual game on MLB's schedule (matching teams + final score near the
    completed_at date) and set commence_time to that game's real start, so
    completed_at >= commence_time holds and the settled row is authoritative.
  * 0-0 / NULL-score rows -> void the settle. A future game that never really
    finished: status -> scheduled, completed_at -> NULL, scores -> NULL. The
    normal pipeline re-settles it correctly once it actually plays.
  * Anything we cannot verify against MLB ground truth is LOGGED and SKIPPED
    (never a blind write).

Bounded (MLB only, resolved_state-failing rows only), evidence-logged per row,
Core SQL, and does NOT touch is_winner / calibration (gotcha #21).

    python3 scripts/repair_inverted_mlb_events.py            # dry-run (ledger only)
    python3 scripts/repair_inverted_mlb_events.py --apply    # commit the repairs
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# resolved_state-failing MLB rows: settled but commence in the future OR
# completed_at before commence_time (the inversion). We pull scores + ids so we
# can classify scored-vs-empty and re-date via ground truth.
_CANDIDATE_SQL = """
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


def _tokens(s: str) -> set:
    return set((s or "").lower().replace(".", "").split())


def _teams_match(our_home, our_away, mlb_home, mlb_away) -> bool:
    """True if our (home, away) matches the MLB game in either orientation."""
    hh = bool(_tokens(our_home) & _tokens(mlb_home))
    aa = bool(_tokens(our_away) & _tokens(mlb_away))
    hswap = bool(_tokens(our_home) & _tokens(mlb_away))
    aswap = bool(_tokens(our_away) & _tokens(mlb_home))
    return (hh and aa) or (hswap and aswap)


async def _mlb_final_for(service, home, away, hs, aws, around_date):
    """Find the real MLB game (Final) matching our teams + score within ±1 day
    of ``around_date``. Returns (game_datetime_iso, mlb_home, mlb_away) or None.

    Score match is orientation-aware: we accept either {hs,aws} == {mlbHome,
    mlbAway} score set so a home/away swap in our row doesn't cause a miss.
    """
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
            if not _teams_match(home, away, mh, ma):
                continue
            mhs = (teams.get("home", {}) or {}).get("score")
            mas = (teams.get("away", {}) or {}).get("score")
            got_scores = sorted([s for s in (mhs, mas) if s is not None])
            # If we have stored scores, require them to match MLB's final;
            # if we don't (shouldn't happen for the scored branch), accept team+date.
            if want_scores and got_scores and want_scores != got_scores:
                continue
            return (g.get("gameDate"), mh, ma)
    return None


async def run(apply: bool) -> None:
    from app.services.mlb_api import MLBAPIService
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    service = MLBAPIService()

    redate = []   # (id, old_commence_iso, new_commence_iso, evidence)
    void = []     # (id, reason)
    review = []   # (id, reason)

    try:
        async with get_task_session() as s:
            rows = (await s.execute(text(_CANDIDATE_SQL))).all()
            print(f"resolved_state-failing MLB events (settled + invariant-violating): {len(rows)}")

            for r in rows:
                scored = (r.hs is not None and r.aws is not None
                          and not (r.hs == 0 and r.aws == 0))
                tag = f"  {r.id} {r.home_team} v {r.away_team} [{r.status}] " \
                      f"commence={r.commence_time} completed_at={r.completed_at} " \
                      f"score={r.hs}-{r.aws}"

                if not scored:
                    # 0-0 / NULL -> future game prematurely settled: void the settle.
                    void.append((r.id, "empty/0-0 score, settled before a real result"))
                    print(f"{tag} -> VOID (un-settle: no real result recorded)")
                    continue

                # Scored: the completed_at + score are a real finished game. Find it
                # on MLB's schedule near the completed_at date and re-date to its
                # real start so completed_at >= commence_time.
                anchor = r.completed_at or now
                res = await _mlb_final_for(
                    service, r.home_team, r.away_team, r.hs, r.aws,
                    anchor.astimezone(timezone.utc) if anchor.tzinfo else anchor.replace(tzinfo=timezone.utc),
                )
                if not res:
                    review.append((r.id, "scored but no matching MLB Final (teams+score) near completed_at"))
                    print(f"{tag} -> REVIEW (no MLB ground-truth match; skipped)")
                    continue
                new_commence_iso, mh, ma = res
                new_commence = datetime.fromisoformat(new_commence_iso.replace("Z", "+00:00"))
                # Only re-date if it actually fixes the invariant (new commence <= completed_at).
                if r.completed_at is not None and new_commence > r.completed_at:
                    review.append((r.id, f"MLB start {new_commence_iso} still after completed_at — ambiguous"))
                    print(f"{tag} -> REVIEW (MLB start after completed_at; skipped)")
                    continue
                redate.append((r.id, r.commence_time.isoformat(), new_commence_iso,
                               f"MLB Final {mh} v {ma} @ {new_commence_iso}"))
                print(f"{tag} -> RE-DATE commence -> {new_commence_iso} ({mh} v {ma})")

            print(f"\nledger: {len(redate)} re-date · {len(void)} void · {len(review)} review-only")

            if not (redate or void):
                print("Nothing to repair.")
                return
            if not apply:
                print(f"\nDRY-RUN — pass --apply to repair {len(redate) + len(void)} rows. No writes made.")
                return

            for eid, _old, new_iso, _ev in redate:
                await s.execute(
                    text("UPDATE events SET commence_time = :c, commence_time_source = 'mlb_schedule_repair' "
                         "WHERE id = :id"),
                    {"c": datetime.fromisoformat(new_iso.replace("Z", "+00:00")), "id": eid},
                )
            for eid, _reason in void:
                await s.execute(
                    text("UPDATE events SET status = 'scheduled', completed_at = NULL, "
                         "home_score = NULL, away_score = NULL WHERE id = :id"),
                    {"id": eid},
                )
            await s.commit()
            print(f"\nAPPLIED: re-dated {len(redate)}, voided {len(void)} settles. "
                  f"is_winner NOT touched (gotcha #21). {len(review)} rows left for manual review.")
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
