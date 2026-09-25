"""A listing both of whose teams were provably playing someone else (#7345).

THE CARD THIS EXISTS FOR. `/api/events/search?q=arkansas state`, production,
2026-09-25: directly under Arkansas State's real Sep 12 final, search served

    15306765  Arkansas State v South Alabama   2026-09-12 23:00Z   suspended, no score

and the league page printed it as "No result reported · Sep 12". The game never
happened. At that same kick-off instant we hold both teams' real games, each an
ESPN-linked final against a DIFFERENT opponent:

    15309107  Arkansas State v West Georgia    2026-09-12 23:00Z   completed 52-7   espn 401868241
    15304849  Tulane v South Alabama           2026-09-12 23:00Z   completed 28-24  espn 401864575

(ESPN has South Alabama at Arkansas State on Oct 8.) The row is a sportsbook
listing that lived for ~1.5 hours on 2026-09-07 and was never priced again.

WHY NOTHING ELSE REACHES IT. There is no twin: no row anywhere carries this
pairing near this date, so `fold_twin_events` (exact minute), the ±72h
unreported fold (#7345's first half, lane1/632) and the market-born drain
(#6231, Kalshi/Polymarket provenance only) all correctly decline. The league
rail ages it off after two weeks; search has no age-off, so it prints forever.

THE PROOF, AND WHY IT NEEDS NO WINDOW AND NO NAMES. A team cannot play two games
that start at the same instant. If BOTH teams of a listing each hold an
id-anchored final at exactly its kick-off against someone else, the listing is
refuted — by two rows ESPN itself identified, keyed on team ids, not names.
A reversed-orientation copy of the real game can never refute it: the refuter
must be against a team OTHER than the listing's opponent, on each side.

WHAT A ROW MUST BE TO BE ASKED ABOUT, all of which the SQL re-asserts:

* no truth of its own — no score, no `completed_at`;
* no provider id — no `espn_id`, no `statpal_fixture_id` (an id-held row is
  the registry's business, #2017, never a serve-time verdict);
* both team ids present, and a kick-off already in the past;
* NO markets (SQL only) — suppress, never fold, so the row we hide must be
  holding nothing a reader could lose.

Nothing is written. The row stays in the table, addressable by id and visible
to the sentinels and #2693; the verdict is recomputed on every request from
live state. Never raises into a page: the caller's `except` is the belt
(gotcha #42 applied to a stage).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# The refuter clause, once per side. `:side` is spliced from a fixed pair below,
# never from input. `r.<other> <> c.<opponent>` is NULL-false on a missing team
# id, so an unreadable refuter refuses rather than refutes.
_REFUTER = """
    SELECT r.id FROM events r
     WHERE r.commence_time = c.commence_time
       AND r.id <> c.id
       AND NULLIF(r.espn_id, '') IS NOT NULL
       AND r.status IN ('completed', 'closed')
       AND r.home_score IS NOT NULL AND r.away_score IS NOT NULL
       AND ((r.home_team_id = c.{side}_team_id AND r.away_team_id <> c.{opp}_team_id)
         OR (r.away_team_id = c.{side}_team_id AND r.home_team_id <> c.{opp}_team_id))
     ORDER BY r.id
     LIMIT 1
"""

_SAME_INSTANT_REFUTATION_SQL = f"""
SELECT c.id AS event_id, h.id AS home_refuter, a.id AS away_refuter
  FROM events c
  JOIN LATERAL ({_REFUTER.format(side="home", opp="away")}) h ON true
  JOIN LATERAL ({_REFUTER.format(side="away", opp="home")}) a ON true
 WHERE c.id IN :event_ids
   AND c.home_score IS NULL AND c.away_score IS NULL
   AND c.completed_at IS NULL
   AND NULLIF(c.espn_id, '') IS NULL
   AND NULLIF(c.statpal_fixture_id, '') IS NULL
   AND c.home_team_id IS NOT NULL AND c.away_team_id IS NOT NULL
   AND c.commence_time < :now
   AND NOT EXISTS (SELECT 1 FROM futures_markets f WHERE f.event_id = c.id)
"""
_SAME_INSTANT_REFUTATION = text(_SAME_INSTANT_REFUTATION_SQL).bindparams(
    bindparam("event_ids", expanding=True)
)


def is_refutation_candidate_row(row: Any, now: datetime) -> bool:
    """Cheap, pure gate over columns the row already holds.

    An optimisation only; the SQL re-asserts every clause. A gate that drifts
    can only refuse a row the verdict would have hidden (the listing renders,
    today's behaviour), never admit one it would not.
    """
    if getattr(row, "id", None) is None:
        return False
    if (
        getattr(row, "home_score", None) is not None
        or getattr(row, "away_score", None) is not None
        or getattr(row, "completed_at", None) is not None
    ):
        return False
    if getattr(row, "espn_id", None) or getattr(row, "statpal_fixture_id", None):
        return False
    if (
        getattr(row, "home_team_id", None) is None
        or getattr(row, "away_team_id", None) is None
    ):
        return False
    kickoff = getattr(row, "commence_time", None)
    if kickoff is None:
        return False
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    return kickoff < now


async def same_instant_refuted_on_page(
    session: AsyncSession,
    events: Sequence[Any],
    now: Optional[datetime] = None,
) -> dict[int, tuple[int, int]]:
    """``{listing id: (home team's final, away team's final)}`` — do not print.

    Costs nothing on a page with no candidates: the gate is pure, and every
    scored, completed, id-held or upcoming row fails it, so no query is issued.
    """
    now = now or datetime.now(timezone.utc)
    candidates = [int(e.id) for e in events if is_refutation_candidate_row(e, now)]
    if not candidates:
        return {}
    result = await session.execute(
        _SAME_INSTANT_REFUTATION, {"event_ids": candidates, "now": now}
    )
    return {
        int(row._mapping["event_id"]): (
            int(row._mapping["home_refuter"]),
            int(row._mapping["away_refuter"]),
        )
        for row in result.fetchall()
    }
