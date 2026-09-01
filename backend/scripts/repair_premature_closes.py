"""#2444 — un-settle events the staleness nets declared over while their market
was still being quoted.

THE DEFECT THIS CLEANS UP. Both snapshot tables dedup at write time: re-polling
and seeing the SAME value bumps ``valid_until`` and leaves ``captured_at`` alone.
The staleness nets asked "is anything still reporting on this game?" by reading
``captured_at``, so a market whose price simply sat still — a pre-match tennis
line for an afternoon — read as silent. The nets closed the event and stamped a
``completed_at`` derived from a pre-match snapshot.

Downstream, ``/api/events/{id}/history`` caps its window at ``completed_at + 30
min``, so every reading captured after the fabricated completion is clipped out
of the response. The user-visible result is a match page that says FINAL with no
score, and a win-probability line that never moves for an entire match, while
hundreds of real in-play readings sit in the database outside the window.

The producer is fixed (``event_completion.LAST_POST_COMMENCE_SNAPSHOT_SQL`` now
returns ``last_seen`` alongside ``last_snap``, and both nets ask the hold
question with ``last_seen``). This rail repairs the rows the old behaviour
already wrote.

WHAT MAKES A ROW PROVEN. All five, no exceptions:

  1. ``status = 'closed'`` — the staleness nets' own marker. A ``'completed'``
     row came from a real scores feed reporting a real finish; it is not ours.
  2. ``completed_at IS NOT NULL`` — there is a fabricated timestamp to undo.
  3. ``home_score IS NULL AND away_score IS NULL`` — gotcha #21. A row holding a
     real result is a DIFFERENT class and this rail never touches it, so nothing
     it writes can destroy a score.
  4. At least ``_MIN_POST_CLOSE_MOVES`` price CHANGES landed after the stamped
     completion, and
  5. those changes span at least ``_MIN_POST_CLOSE_TRAVEL`` of probability.

🔴 WHY 4+5 ARE "A PRICE CHANGED", NOT "A SOURCE CONFIRMED". The producer guard
asks whether anything is still reporting, and for that question a repeated quote
is the right signal. This rail asks a stricter and different question — *is there
real hidden movement that the chart is currently clipping?* — and the two must
not be conflated. Measured 2026-08-31 over a 7-day window: a confirmation-based
predicate matched **490** rows, most of them soccer/esports derivative rows
("Total Corners", "Exact Score", "Halftime Result") whose prices a blanket poller
keeps touching long after the underlying match ends. Un-settling those would flip
genuinely-finished events back to ``live``, and because something keeps
confirming them, the fixed net would then hold them live indefinitely. The
movement predicate matches **36**, and every one of them has a real in-play
journey sitting invisible behind a fabricated completion.

WHAT THIS DELIBERATELY LEAVES ALONE. Rows closed prematurely that have no
post-close movement are NOT repaired here. Their ``completed_at`` is still wrong,
but there is nothing hidden to reveal, so un-settling them buys no user-visible
change while carrying the stuck-live risk above. That is a real remainder, not a
clean sweep: in the same 7-day window it is roughly 49 rows.

THE REMEDY IS TO UNDO, NOT TO GUESS. ``status='live'``, ``completed_at=NULL`` —
the state the row would have been in had the guard worked. It deliberately does
NOT compute a replacement end time: the repaired row is already past its sport's
max duration, so the FIXED net re-closes it on its next pass and derives
``completed_at`` from the correct evidence. Guessing here would re-introduce
exactly the fabricated-timestamp class this rail exists to remove.

That hand-off is the whole design. If the market really has gone quiet, the row
is re-closed within one beat with an honest end time. If it has not, the event is
genuinely still live and was never over.

Measured 2026-08-31 over events commencing in the last 7 days: 36 proven rows —
33 US Open tennis (18 WTA / 15 ATP), plus one boxing and two soccer. Tennis
dominates because a pre-match tennis line is the market most likely to sit at one
number for hours. The worst single row, Tsitsipas–Fils (ev 15293814), is hiding
375 readings spanning 0.964 of probability: an entire match journey, on a page
whose win-probability line does not move.

    python3 scripts/repair_premature_closes.py                  # DRY-RUN
    python3 scripts/repair_premature_closes.py --days 7 --sport tennis
    python3 scripts/repair_premature_closes.py --apply
"""
import asyncio
import sys

from sqlalchemy import text

from app.utils.event_completion import STILL_ACTIVE_MINUTES

# How much hidden movement makes a row worth un-settling. Both bars must clear:
# the count rules out a couple of stray post-close ticks, the travel rules out a
# market being re-quoted at a price that never really moves.
_MIN_POST_CLOSE_MOVES = 10
_MIN_POST_CLOSE_TRAVEL = 0.05

# Proven-premature closes, worst hidden journey first. The five conditions in the
# module docstring, in the same order. The join is on `captured_at` — a price
# CHANGE — deliberately, and NOT on the `last_seen` confirmation the producer
# guard uses; see the docstring for the 490-vs-36 measurement behind that choice.
_PREMATURE_CLOSES_SQL = """
    WITH cand AS (
        SELECT e.id, e.commence_time, e.completed_at,
               e.home_team_name, e.away_team_name, s.key AS sport_key
          FROM events e
          JOIN sports s ON s.id = e.sport_id
         WHERE e.status = 'closed'
           AND e.completed_at IS NOT NULL
           AND e.home_score IS NULL
           AND e.away_score IS NULL
           AND e.commence_time > now() - make_interval(days => :days)
           -- The pattern arrives fully formed. Building it in SQL would need a
           -- literal '%' inside text(), which is the gotcha #45 footgun.
           AND (:sport_pattern IS NULL OR s.key LIKE :sport_pattern)
    )
    SELECT c.id, c.commence_time, c.completed_at,
           c.home_team_name, c.away_team_name, c.sport_key,
           count(*) AS hidden_moves,
           max(o.home_win_probability) - min(o.home_win_probability) AS travel,
           max(o.captured_at) AS last_hidden_at
      FROM cand c
      JOIN odds_snapshots o
        ON o.event_id = c.id
       AND o.captured_at > c.completed_at
                           + make_interval(mins => :still_active_minutes)
     GROUP BY c.id, c.commence_time, c.completed_at,
              c.home_team_name, c.away_team_name, c.sport_key
    HAVING count(*) >= :min_moves
       AND max(o.home_win_probability) - min(o.home_win_probability)
           >= :min_travel
     ORDER BY travel DESC
     LIMIT :limit
"""

# One statement, addressed by primary key over the PROVEN ids only — never a
# predicate re-evaluated at write time, which could sweep in a row that settled
# legitimately between the SELECT and the UPDATE.
_UNSETTLE_SQL = """
    UPDATE events
       SET status = 'live', completed_at = NULL
     WHERE id = ANY(:event_ids)
       AND status = 'closed'
       AND home_score IS NULL
       AND away_score IS NULL
"""


async def repair(session, apply: bool, *, days: int, sport: str | None,
                 limit: int) -> dict:
    rows = (await session.execute(
        text(_PREMATURE_CLOSES_SQL),
        {"days": days, "limit": limit,
         "sport_pattern": f"{sport}%" if sport else None,
         "still_active_minutes": STILL_ACTIVE_MINUTES,
         "min_moves": _MIN_POST_CLOSE_MOVES,
         "min_travel": _MIN_POST_CLOSE_TRAVEL},
    )).all()

    ledger = [{
        "event_id": r.id,
        "sport_key": r.sport_key,
        "matchup": f"{r.home_team_name} vs {r.away_team_name}",
        "stamped_completed_at": r.completed_at.isoformat(),
        "hidden_moves": r.hidden_moves,
        "hidden_travel": round(float(r.travel), 3),
        "hidden_until": r.last_hidden_at.isoformat(),
    } for r in rows]

    unsettled = 0
    if apply and rows:
        res = await session.execute(
            text(_UNSETTLE_SQL), {"event_ids": [r.id for r in rows]}
        )
        unsettled = res.rowcount or 0
        await session.commit()

    by_sport: dict[str, int] = {}
    for e in ledger:
        by_sport[e["sport_key"]] = by_sport.get(e["sport_key"], 0) + 1

    return {"proven": len(ledger), "unsettled": unsettled,
            "by_sport": by_sport, "ledger": ledger}


async def run(apply: bool, days: int, sport: str | None, limit: int) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        res = await repair(s, apply, days=days, sport=sport, limit=limit)

    print(f"=== #2444 premature closes ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"window={days}d sport={sport or 'ALL'} limit={limit}")
    print(f"proven premature (>={_MIN_POST_CLOSE_MOVES} price changes spanning "
          f">={_MIN_POST_CLOSE_TRAVEL} probability, all landing >"
          f"{STILL_ACTIVE_MINUTES} min after the stamped completion and all "
          f"currently clipped out of the chart): {res['proven']}")
    for sk, n in sorted(res["by_sport"].items(), key=lambda kv: -kv[1]):
        print(f"  {n:>4}  {sk}")
    for e in res["ledger"][:60]:
        print(f"  ev{e['event_id']} [{e['sport_key']}] {e['matchup']}: "
              f"stamped {e['stamped_completed_at']}, then {e['hidden_moves']} "
              f"hidden readings spanning {e['hidden_travel']} through "
              f"{e['hidden_until']}")
    print("\nNOT REPAIRED HERE: prematurely-closed rows with no hidden movement. "
          "Their completed_at is still wrong, but there is nothing to reveal and "
          "un-settling them risks sticking them live. Run the #2444 census to "
          "size that remainder — it is not zero.")
    if apply:
        print(f"\nCOMMITTED unsettled={res['unsettled']} "
              f"(status='live', completed_at=NULL). The FIXED staleness net "
              f"re-closes each one on its next pass with an honest end time — "
              f"this rail deliberately does not guess a replacement.")
        if res["unsettled"] != res["proven"]:
            print(f"NOTE: {res['proven'] - res['unsettled']} row(s) no longer "
                  f"matched the write guard and were left alone.")
    else:
        print("\nDRY-RUN — pass --apply to commit.")


if __name__ == "__main__":
    _days, _sport, _limit = 7, None, 500
    for i, a in enumerate(sys.argv):
        if a == "--days" and i + 1 < len(sys.argv):
            _days = int(sys.argv[i + 1])
        if a == "--sport" and i + 1 < len(sys.argv):
            _sport = sys.argv[i + 1]
        if a == "--limit" and i + 1 < len(sys.argv):
            _limit = int(sys.argv[i + 1])
    asyncio.run(run("--apply" in sys.argv, _days, _sport, _limit))
