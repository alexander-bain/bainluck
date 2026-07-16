"""#210 Item 3 — clean up the World Cup PLACEHOLDER phantom events (gotcha #32).

A mislinked Kalshi WC prop (e.g. the 07-15 semifinal's corner markets) spawned
teamless / wrong-date placeholder EVENTS in the ``soccer_fifa_world_cup`` sport:
verified live 2026-07-16, ~25 teamless 06-25..07-15 rows plus a 07-29
"England vs Argentina" phantom built from the semifinal's corner markets. The WC
concept page already HIDES these at render (`_match_is_real` +
`_drop_slot_duplicate_phantoms`, #209 Item 3), and the write-side is now blocked
in the registry (find_or_create_event refuses teamless creation). This script is
the DATA half (fix-don't-hide): it frees the markets stranded on the phantoms.

PHANTOM predicate (mirrors the render-side `_match_is_real` gate exactly):
  a soccer_fifa_world_cup event with external_id IS NULL AND no win-prob sources
  (a schedule source always sets external_id; a real match always has win-prob) —
  OR a teamless event (blank home/away). Such events are matching mis-creations,
  never real fixtures.

For each phantom: UNLINK its linked futures_markets (event_id := NULL) so the
next matching cycle can re-home them to the correct event (or leave them honestly
unlinked). Never touches is_winner/prices/market rows; only the event_id FK. The
now-empty phantom events are left in place (harmless, hidden by the render guard,
and safe against FK/calibration surprises) — deletion is a separate, riskier op.

Dry-run by default; pass --apply to commit.

    python3 scripts/fix_210_wc_placeholders.py            # dry-run (ledger only)
    python3 scripts/fix_210_wc_placeholders.py --apply    # commit the unlinks
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PHANTOM_EVENTS_SQL = """
    SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time, e.status,
           e.external_id
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    WHERE s.key = 'soccer_fifa_world_cup'
      AND (
        -- render-side _match_is_real phantom gate: no schedule id AND no win-prob
        (e.external_id IS NULL
         AND (e.win_probability_sources IS NULL
              OR e.win_probability_sources = '{}'::jsonb))
        -- teamless placeholder rows
        OR e.home_team_name IS NULL OR btrim(e.home_team_name) = ''
        OR e.away_team_name IS NULL OR btrim(e.away_team_name) = ''
      )
    ORDER BY e.commence_time
"""

_LINKED_MARKETS_SQL = """
    SELECT id, event_id, external_id, name
    FROM futures_markets
    WHERE event_id = ANY(:ids)
    ORDER BY event_id, id
"""


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        events = (await s.execute(text(_PHANTOM_EVENTS_SQL))).all()
        print(f"WC phantom/placeholder events: {len(events)}")
        if not events:
            print("Nothing to do.")
            return

        ev_ids = [e.id for e in events]
        mkts = (await s.execute(text(_LINKED_MARKETS_SQL), {"ids": ev_ids})).all()
        by_event: dict = {}
        for m in mkts:
            by_event.setdefault(m.event_id, []).append(m)

        market_ids = [m.id for m in mkts]
        empty_phantoms = [e for e in events if e.id not in by_event]
        print(f"Phantom events holding stranded markets: {len(by_event)}")
        print(f"Markets to unlink: {len(market_ids)}")
        print(f"Empty phantom events (no markets, left in place): {len(empty_phantoms)}\n")

        shown = 0
        for e in events:
            ms = by_event.get(e.id, [])
            tag = "TEAMLESS" if not (e.home_team_name or "").strip() or not (e.away_team_name or "").strip() else "phantom"
            date = e.commence_time.date().isoformat() if e.commence_time else "?"
            print(f"event {e.id}  [{tag}] {e.home_team_name!r} vs {e.away_team_name!r}  "
                  f"{date} {e.status}  (ext_id={e.external_id})")
            for m in ms[:6]:
                print(f"    unlink #{m.id}  {m.external_id}  {m.name[:50]}")
            if len(ms) > 6:
                print(f"    ... and {len(ms) - 6} more markets")
            shown += 1
            if shown >= 40:
                print(f"    ... and {len(events) - 40} more events")
                break

        if not apply:
            print(f"\nDRY-RUN — pass --apply to unlink {len(market_ids)} markets from "
                  f"{len(by_event)} WC phantom events. No writes.")
            return

        if market_ids:
            res = await s.execute(
                text("UPDATE futures_markets SET event_id = NULL WHERE id = ANY(:ids)"),
                {"ids": market_ids},
            )
            await s.commit()
            print(f"\nCOMMITTED: unlinked {res.rowcount} markets from "
                  f"{len(by_event)} WC phantom events. "
                  f"({len(empty_phantoms)} empty phantoms left for the render guard.)")
        else:
            print("\nNo stranded markets — nothing to unlink (idempotent no-op).")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
