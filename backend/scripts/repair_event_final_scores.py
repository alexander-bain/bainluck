"""CAL-P002 — repair settled events frozen on a NON-FINAL score.

Invariant: a settled event's stored score IS the game's final score. A violation
means the page shows a wrong final (we held ``BOS 3-1`` where the real final was
``6-3``) and every score-derived grade underneath it stands on a mid-game number.

WHY NOTHING ELSE FIXES THIS. Two rails write settled scores today and both have a
hole this repair fills:

* ``_corrected_final_score`` (``tasks/espn_sync.py``) refuses to write unless our
  stored total is **0** — deliberately, citing gotcha #21 ("a real non-zero stored
  score is NEVER overwritten"). A score frozen at a plausible ``3-2`` is therefore
  structurally uncorrectable by every existing path.
* ``backfill_missing_scores`` (``utils/espn_helpers.py``) is gated on
  ``home_score IS NULL`` and a 7-day window. Same blind spot.

The producer is the wall-clock staleness net (``espn_sync._transition_event_statuses_impl``
and ``odds_polling.detect_and_close_stale_events``): both close an event purely on
elapsed time, keep whatever score the last poll happened to have written, and then
grade ``win_probability_sources.final_result`` to 1.0/0.0 off that mid-game score.
So a frozen 3-2 in the 6th becomes a permanent "home team won".

CAL-P002's measured evidence (2026-08-05, identity-verified vs ESPN finals):

    closed  · NHL/NBA/MLB/WNBA     10 / 399  =  2.5%
    closed  · NCAA Baseball        43 / 388  = 11.1%
    completed · major, 2-9d old    19 /  70  = 27.1%   <- all MLB
    completed · major, 30-60d      43 / 199  = 21.6%   <- all MLB
    completed · major, 100-160d     6 / 200  =  3.0%

Two sub-classes, ONE fix (overwrite with the event's own ESPN final):
  A. frozen in-progress score — NBA ev12080353 held 45-56 (a halftime score) for a
     game ESPN finalled 87-109; MLB/NCAA rows frozen at 0-0.
  B. wrong-game score from the same series — ev15182558 (Giants@Brewers 7/29) held
     ``SF 2-8 MIL``, which is the final of the 7/28 game. Its ``espn_id`` and
     ``commence_time`` both correctly identify the 7/29 game; only the score is
     another game's. (Link-level series mislinkage stays #1466 scope; this repairs
     the score value, not the link.)

SAFETY RAILS (each one earned):
  * Writes ONLY when ESPN reports the game FINAL (``status == "post"``). Writing a
    non-final ESPN score is bug #980/#981 recurring.
  * TEAM-IDENTITY GUARD: our home/away must match ESPN's home/away for that
    ``espn_id`` before we trust its score. The CAL-P002 census found 3 NCAA-Baseball
    rows whose ``espn_id`` points at a different game entirely — repairing off those
    would import a wrong score, not remove one. Identity-blocked rows are reported,
    never written (they are an ``espn_id`` linkage defect, a different repair).
  * ``completed_at`` is derived from the last REAL post-commence snapshot (gotcha
    #22), never ``now()``, and never written if that would invert ``commence_time``
    (gotcha #46). No snapshot ⇒ left NULL and reported.
  * When a corrected score changes the winner, ``win_probability_sources`` is
    re-resolved through the EXISTING ``_apply_final_pm_win_prob`` helper (#1000
    shape-safe). This changes no weights and no blend math — it restamps a derived
    final that was computed from the wrong score.
  * Commits per (sport, date) group, so a 30s HTTP timeout leaves consistent,
    resumable progress. Re-invoke until ``groups_remaining`` is 0.
  * Oldest-first by default (gotcha #41 — newest-first ordering never reaches the
    old tail).

    POST /api/admin/repairs/event-final-scores?apply=false            # dry-run census
    POST /api/admin/repairs/event-final-scores?apply=true&limit=40    # commit a batch

    python3 scripts/repair_event_final_scores.py            # dry-run ledger
    python3 scripts/repair_event_final_scores.py --apply    # commit

Heroku one-off (gotcha #48 — non-detached does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`). Prefer the endpoint.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Settled events that ESPN can adjudicate: terminal status, a stored score, an
# espn_id to look up, and old enough that "still being played" is not the answer.
_CANDIDATE_SQL = """
    SELECT e.id AS event_id, e.espn_id, s.key AS sport_key, e.status AS ev_status,
           e.home_team_name, e.away_team_name, e.home_score, e.away_score,
           e.commence_time, e.completed_at,
           (e.commence_time AT TIME ZONE 'America/New_York')::date AS game_date,
           (SELECT MAX(w.captured_at) FROM win_prob_snapshots w
              WHERE w.event_id = e.id AND w.captured_at >= e.commence_time) AS last_wp_snap,
           (SELECT MAX(o.captured_at) FROM odds_snapshots o
              WHERE o.event_id = e.id AND o.captured_at >= e.commence_time) AS last_odds_snap
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE e.status IN ('closed', 'completed')
      AND e.espn_id IS NOT NULL
      AND e.home_score IS NOT NULL
      AND e.away_score IS NOT NULL
      AND e.commence_time IS NOT NULL
      AND e.commence_time < NOW() - INTERVAL '2 days'
      AND s.key = ANY(:sport_keys)
    ORDER BY e.commence_time
"""

_POPULATION_SQL = """
    SELECT COUNT(*) AS n
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE e.status IN ('closed', 'completed')
      AND e.espn_id IS NOT NULL
      AND e.home_score IS NOT NULL
      AND e.away_score IS NOT NULL
      AND e.commence_time IS NOT NULL
      AND e.commence_time < NOW() - INTERVAL '2 days'
      AND s.key = ANY(:sport_keys)
"""

_FIX_SCORE_SQL = """
    UPDATE events SET home_score = :home_score, away_score = :away_score
    WHERE id = :event_id
"""

_FIX_COMPLETED_AT_SQL = """
    UPDATE events SET completed_at = :completed_at WHERE id = :event_id
"""

# Default group budget per invocation. Each group is ONE ESPN scoreboard call and
# the client sleeps 0.5s between requests, so this stays inside the 30s HTTP wall.
_GROUP_LIMIT = 25


def score_is_stale(our_home, our_away, espn_home, espn_away, espn_is_final: bool) -> bool:
    """True when a settled event's stored score disagrees with ESPN's FINAL.

    Deliberately the inverse of ``_corrected_final_score``'s "only when our total is
    0" rule: CAL-P002 proved the frozen-at-a-real-score case is the LARGER half of
    the defect (a frozen 3-2 is invisible to the total==0 test). ESPN's final is the
    authority for a settled game's score; a non-final ESPN reading never is.
    """
    if not espn_is_final:
        return False
    if espn_home is None or espn_away is None:
        return False
    if our_home is None or our_away is None:
        return False
    return (our_home, our_away) != (espn_home, espn_away)


def resolved_home_from_score(home_score: int, away_score: int) -> float:
    """The final win-prob a settled score implies (matches the staleness net)."""
    if home_score > away_score:
        return 1.0
    if home_score < away_score:
        return 0.0
    return 0.5


def _identity_matches(our_home, our_away, espn_home, espn_away) -> bool:
    """Does this ESPN game describe the SAME fixture as our event?

    Guards the case the census found: an ``espn_id`` pointing at a different game.
    Without this, "repair" would import a wrong score instead of removing one.
    """
    from app.utils.name_normalization import names_match

    if not (espn_home and espn_away):
        return False
    return bool(
        names_match(our_home or "", espn_home) and names_match(our_away or "", espn_away)
    )


def _espn_team_name(team) -> str:
    if team is None:
        return ""
    return team.display_name or team.name or team.short_name or ""


def espn_date_matches(our_game_date, espn_dt) -> bool:
    """Does this ESPN game fall on the SAME calendar day as our event?

    THE GUARD THAT TEAM IDENTITY CANNOT PROVIDE. In a playoff series the same two
    teams meet repeatedly, so ``_identity_matches`` passes on every game of the
    series — and CAL-P002 found events whose ``espn_id`` points at a DIFFERENT game
    of their own series:

        ev14861878  our 2026-06-09  ->  espn_id 401874173 is the 06-06 game
        ev14881094  our 2026-06-11  ->  espn_id 401874172 is the 06-04 game
        ev14792938  our 2026-05-27  ->  espn_id 401873385 is the 05-25 game
        ev14639101  our 2026-05-16  ->  espn_id 401871407 is the 05-12 game

    A simulated repair that trusted identity alone imported those neighbours'
    finals and RAISED the KXNHLSPREAD disagreement count 8 -> 14. The batched
    scoreboard-by-date fetch already makes this structurally impossible (a game on
    another date is simply absent from the slate we asked for), but that is a
    property of the fetch strategy, not of the write rule. Pin it here so a future
    per-event ``summary`` fallback cannot silently reintroduce the corruption.

    Both sides are normalized to US/Eastern — the same basis our ``game_date`` is
    computed on — so the comparison is symmetric, not a UTC/local mix.
    """
    if our_game_date is None or espn_dt is None:
        return False
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    dt = espn_dt
    if dt.tzinfo is None:
        from datetime import timezone as _tz

        dt = dt.replace(tzinfo=_tz.utc)
    return dt.astimezone(et).date() == our_game_date


async def repair(
    session,
    apply: bool,
    limit: int = _GROUP_LIMIT,
    sport: str | None = None,
    newest_first: bool = False,
) -> dict:
    """Session-taking core (shared by the CLI and POST /api/admin/repairs/
    event-final-scores). Commits per group when ``apply``; returns a
    before/after census plus a per-event ledger.

    ``limit`` bounds (sport, date) GROUPS — one ESPN scoreboard call each — not
    events. Re-invoke while ``groups_remaining > 0``.
    """
    from sqlalchemy import text

    from app.services.espn_api import get_espn_service
    from app.utils.sport_keys import ESPN_SPORT_MAPPING

    s = session
    # Gate on the mapping the rest of the ESPN pipeline uses, so this repair never
    # attempts a fetch the other tasks would not make.
    sport_keys = sorted(ESPN_SPORT_MAPPING)
    if sport:
        sport_keys = [k for k in sport_keys if k == sport]
        if not sport_keys:
            return {
                "repair": "event-final-scores",
                "applied": False,
                "error": f"sport '{sport}' is not in ESPN_SPORT_MAPPING",
                "available": sorted(ESPN_SPORT_MAPPING),
            }

    population = (await s.execute(text(_POPULATION_SQL), {"sport_keys": sport_keys})).one().n
    rows = (await s.execute(text(_CANDIDATE_SQL), {"sport_keys": sport_keys})).all()

    # Group by (sport_key, ET game date): one ESPN scoreboard call covers a slate.
    groups: dict[tuple[str, object], list] = {}
    for r in rows:
        groups.setdefault((r.sport_key, r.game_date), []).append(r)
    ordered = sorted(groups, key=lambda k: (k[1], k[0]), reverse=bool(newest_first))
    selected = ordered[: max(0, int(limit))]

    espn = get_espn_service()
    stats = {
        "events_scanned": 0,
        "espn_not_found": 0,
        "espn_not_final": 0,
        "date_blocked": 0,
        "identity_blocked": 0,
        "score_defects": 0,
        "completed_at_gaps": 0,
        "scores_repaired": 0,
        "completed_at_repaired": 0,
        "blend_repaired": 0,
        "winner_flips": 0,
    }
    ledger: list[dict] = []

    for sport_key, game_date in selected:
        bucket = groups[(sport_key, game_date)]
        try:
            board = await espn.get_scoreboard(sport_key, game_date.strftime("%Y%m%d"))
        except Exception as exc:  # a dead slate must not kill the whole batch
            ledger.append({
                "sport_key": sport_key, "date": game_date.isoformat(),
                "action": "skip_scoreboard_error", "error": f"{type(exc).__name__}: {exc}",
            })
            continue
        by_id = {str(e.espn_id): e for e in board if e.espn_id is not None}

        group_writes = 0
        for r in bucket:
            stats["events_scanned"] += 1
            ee = by_id.get(str(r.espn_id))
            if ee is None:
                stats["espn_not_found"] += 1
                continue
            is_final = ee.status == "post"
            if not is_final:
                stats["espn_not_final"] += 1
                continue

            # Series guard: same-teams is NOT same-game in a playoff series.
            if not espn_date_matches(r.game_date, ee.date):
                stats["date_blocked"] += 1
                ledger.append({
                    "event_id": r.event_id, "sport_key": sport_key,
                    "espn_id": r.espn_id, "action": "skip_espn_id_wrong_date",
                    "our_date": r.game_date.isoformat(),
                    "espn_date": ee.date.isoformat() if ee.date else None,
                })
                continue

            espn_home_name = _espn_team_name(ee.home_team)
            espn_away_name = _espn_team_name(ee.away_team)
            if not _identity_matches(
                r.home_team_name, r.away_team_name, espn_home_name, espn_away_name
            ):
                # An espn_id linkage defect, NOT a score defect. Report, never write.
                stats["identity_blocked"] += 1
                ledger.append({
                    "event_id": r.event_id, "sport_key": sport_key,
                    "espn_id": r.espn_id, "action": "skip_identity_mismatch",
                    "ours": f"{r.home_team_name} vs {r.away_team_name}",
                    "espn": f"{espn_home_name} vs {espn_away_name}",
                })
                continue

            stale = score_is_stale(
                r.home_score, r.away_score, ee.home_score, ee.away_score, is_final
            )
            needs_completed_at = r.completed_at is None
            if not stale and not needs_completed_at:
                continue

            entry = {
                "event_id": r.event_id, "sport_key": sport_key,
                "status": r.ev_status, "espn_id": r.espn_id,
                "matchup": f"{r.home_team_name} vs {r.away_team_name}",
                "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            }

            new_completed_at = None
            if needs_completed_at:
                stats["completed_at_gaps"] += 1
                candidates = [
                    t for t in (r.last_wp_snap, r.last_odds_snap) if t is not None
                ]
                cand = max(candidates) if candidates else None
                # gotcha #46: never stamp a completion that precedes the start.
                if cand is not None and cand >= r.commence_time:
                    new_completed_at = cand
                    entry["new_completed_at"] = cand.isoformat()
                else:
                    entry["completed_at_action"] = "skip_no_post_commence_snapshot"

            if stale:
                stats["score_defects"] += 1
                old_res = resolved_home_from_score(r.home_score, r.away_score)
                new_res = resolved_home_from_score(ee.home_score, ee.away_score)
                entry.update({
                    "stored_score": f"{r.home_score}-{r.away_score}",
                    "espn_final": f"{ee.home_score}-{ee.away_score}",
                    "winner_flip": old_res != new_res,
                    "action": "fix_score",
                })
                if old_res != new_res:
                    stats["winner_flips"] += 1
            else:
                entry["action"] = "fix_completed_at_only"

            ledger.append(entry)

            if not apply:
                continue

            if stale:
                await s.execute(text(_FIX_SCORE_SQL), {
                    "event_id": r.event_id,
                    "home_score": ee.home_score,
                    "away_score": ee.away_score,
                })
                stats["scores_repaired"] += 1
                group_writes += 1

                # The staleness net already graded the blend off the WRONG score.
                # Restamp it from the corrected one via the existing shape-safe
                # helper (#1000) — no weight or blend-math change.
                new_res = resolved_home_from_score(ee.home_score, ee.away_score)
                old_res = resolved_home_from_score(r.home_score, r.away_score)
                if old_res != new_res:
                    from sqlalchemy import select, update as sql_update

                    from app.models.models import Event
                    from app.tasks.espn_sync import _apply_final_pm_win_prob

                    cur = (await s.execute(
                        select(Event.win_probability_sources).where(Event.id == r.event_id)
                    )).scalar_one_or_none()
                    if cur and "final_result" in (cur or {}):
                        await s.execute(
                            sql_update(Event)
                            .where(Event.id == r.event_id)
                            .values(
                                win_probability_sources=_apply_final_pm_win_prob(cur, new_res)
                            )
                        )
                        stats["blend_repaired"] += 1

            if new_completed_at is not None:
                await s.execute(text(_FIX_COMPLETED_AT_SQL), {
                    "event_id": r.event_id, "completed_at": new_completed_at,
                })
                stats["completed_at_repaired"] += 1
                group_writes += 1

        if apply and group_writes:
            # Commit per group: a timeout leaves consistent, resumable progress.
            await s.commit()

    after = (await s.execute(text(_POPULATION_SQL), {"sport_keys": sport_keys})).one().n
    return {
        "repair": "event-final-scores",
        "applied": bool(apply),
        "population": population,
        "population_after": after,
        "groups_total": len(ordered),
        "groups_scanned": len(selected),
        "groups_remaining": max(0, len(ordered) - len(selected)),
        "order": "newest_first" if newest_first else "oldest_first",
        "sport": sport or "all_espn_mapped",
        **stats,
        "defect_rate_scanned": (
            round(stats["score_defects"] / stats["events_scanned"], 4)
            if stats["events_scanned"] else None
        ),
        "ledger": ledger,
    }


async def run(apply: bool, limit: int, sport: str | None) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        res = await repair(s, apply, limit=limit, sport=sport)

    print(f"=== CAL-P002 event-final-scores ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"population={res['population']} groups={res['groups_scanned']}/"
          f"{res['groups_total']} (remaining {res['groups_remaining']})")
    print(f"scanned={res['events_scanned']} score_defects={res['score_defects']} "
          f"winner_flips={res['winner_flips']} completed_at_gaps={res['completed_at_gaps']}")
    print(f"identity_blocked={res['identity_blocked']} not_final={res['espn_not_final']} "
          f"not_found={res['espn_not_found']}")
    for e in res["ledger"][:40]:
        if e.get("action") == "fix_score":
            print(f"  ev{e['event_id']} [{e['sport_key']}] {e['matchup']}: "
                  f"{e['stored_score']} -> {e['espn_final']}"
                  + ("  *WINNER FLIP*" if e.get("winner_flip") else ""))
    if apply:
        print(f"\nCOMMITTED scores={res['scores_repaired']} "
              f"completed_at={res['completed_at_repaired']} blend={res['blend_repaired']}")
        if res["groups_remaining"]:
            print(f"Re-run until groups_remaining is 0 (now {res['groups_remaining']}).")
    else:
        print("\nDRY-RUN — pass --apply to commit.")


if __name__ == "__main__":
    _limit = _GROUP_LIMIT
    _sport = None
    for i, a in enumerate(sys.argv):
        if a == "--limit" and i + 1 < len(sys.argv):
            _limit = int(sys.argv[i + 1])
        if a == "--sport" and i + 1 < len(sys.argv):
            _sport = sys.argv[i + 1]
    asyncio.run(run("--apply" in sys.argv, _limit, _sport))
