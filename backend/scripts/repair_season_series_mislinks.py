"""#1220 — repair the season-aggregate → single-game mislinks (data-repair lane).

Prevention already SHIPPED in Queue #238 (commits 948a19b6 + f3a0d5ef): the game
detector now screens season-aggregate names on ALL branches (bare-matchup +
game-prop colon form), so NO NEW bogus links are created. This script is the owed
DATA REPAIR for the rows created before that guard landed.

The census (ops-lane r250/r251, 2026-07-22 — the REAL scope, not the phantom ~110
that were already gone/never-linked):

  * 35 season-aggregate FUTURES markets wrongly linked to single events:
      - 11 Kalshi "Head-to-Head Win Total" (#1220's headline)   → event_id set
      - 24 Polymarket "... Season Series Winner"                → event_id set
    A season-long two-team comparison is a FUTURES market (event_id MUST be NULL);
    linking it to one game surfaces it on the wrong event page and mis-scopes it.

  * 34 of the 35 linked events are BOGUS game events fabricated from those season
    futures: sport key `*_other`, home/away_team_id NULL, status flipped to
    `closed` by `detect_and_close_stale_events` → they render as "FINAL" game
    cards with wrong (bare-name-resolved) logos on native Discover.

  * EXACTLY ONE of the 35 is a REAL game (baseball_mlb, team_ids NOT NULL): a
    Season-Series-Winner market got mislinked onto a genuine MLB game. That event
    is REAL — we only unlink the market from it, we NEVER void it. (Look at the
    target before overwriting: it contradicts the queue's "35 bogus" wording.)

Two repairs, one transaction:
  1. UNLINK every season-aggregate market (event_id → NULL) — all 35, both
     patterns. They become proper futures (the guard stops re-linking).
  2. VOID the bogus events (status → 'voided') — the reversible soft-void already
     used by the dup-merge path ('merged'), excluded from every surface query
     (event_registry match filters IN scheduled/live/completed/closed; the feed's
     game queries the same). Guarded to `*_other` + BOTH team_ids NULL so the one
     real MLB game can never be voided. 691 bogus win_prob_snapshots ride along
     unread (a voided event is never surfaced); we don't cascade-delete them.

Dry-run by default (prints the full ledger + would-do counts). Pass --apply to
commit. Idempotent: after a clean run the census is 0, so a re-run is a no-op.

    python3 scripts/repair_season_series_mislinks.py            # dry-run ledger
    python3 scripts/repair_season_series_mislinks.py --apply    # commit the repair

Heroku one-off (gotcha #48 — non-detached run does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):
    heroku run:detached "python scripts/repair_season_series_mislinks.py --apply" -a bainluck
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The season-aggregate market families that must never carry an event_id (mirrors
# the Queue #238 _SEASON_AGGREGATE_KEYWORDS guard that stops NEW links).
_SEASON_AGG_PREDICATE = """
    (fm.name ILIKE '%Head-to-Head Win Total%'
     OR fm.name ILIKE '%Season Series Winner%'
     OR fm.name ILIKE '%Season Win Total%'
     OR fm.name ILIKE '%make the playoffs%')
"""

_LEDGER_SQL = f"""
    SELECT fm.id AS market_id, fm.source, fm.status AS mkt_status, fm.name AS market_name,
           e.id AS event_id, e.status AS ev_status,
           s.key AS sport_key,
           (e.home_team_id IS NULL OR e.away_team_id IS NULL) AS team_null,
           (e.home_score IS NULL AND e.away_score IS NULL) AS score_null
    FROM futures_markets fm
    JOIN events e ON e.id = fm.event_id
    LEFT JOIN sports s ON s.id = e.sport_id
    WHERE fm.event_id IS NOT NULL
      AND {_SEASON_AGG_PREDICATE}
    ORDER BY fm.source, fm.id
"""

# Unlink every season-aggregate market currently carrying an event_id.
_UNLINK_SQL = f"""
    UPDATE futures_markets fm
    SET event_id = NULL, updated_at = NOW()
    WHERE fm.event_id IS NOT NULL
      AND {_SEASON_AGG_PREDICATE}
"""

# Void the BOGUS events among the (formerly) linked set. Guards, ALL required:
#   * `*_other` sport key      — fabricated events live on the `_other` leagues,
#   * BOTH team_ids NULL       — a real game (the one baseball_mlb) is team-linked,
# so the real MLB game can never match. Reversible (status flip, not a delete).
_VOID_SQL = """
    UPDATE events e
    SET status = 'voided', updated_at = NOW()
    WHERE e.id = ANY(:event_ids)
      AND e.home_team_id IS NULL
      AND e.away_team_id IS NULL
      AND EXISTS (
          SELECT 1 FROM sports s
          WHERE s.id = e.sport_id AND s.key ~ '_other$'
      )
"""

_CENSUS_SQL = f"""
    SELECT COUNT(*) AS linked_markets, COUNT(DISTINCT fm.event_id) AS linked_events
    FROM futures_markets fm
    WHERE fm.event_id IS NOT NULL
      AND {_SEASON_AGG_PREDICATE}
"""


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        rows = (await s.execute(text(_LEDGER_SQL))).all()

        print(f"=== #1220 season-aggregate mislink ledger: {len(rows)} linked markets ===")
        print(f"{'market_id':>12} {'source':>10} {'mkt':>6} {'event_id':>10} "
              f"{'ev':>8} {'sport':>22} {'team_null':>9} | market_name")
        event_ids = set()
        bogus_event_ids = set()
        real_event_ids = set()
        for r in rows:
            event_ids.add(r.event_id)
            is_bogus = bool(r.team_null) and (r.sport_key or "").endswith("_other")
            (bogus_event_ids if is_bogus else real_event_ids).add(r.event_id)
            print(f"{r.market_id:>12} {r.source:>10} {r.mkt_status:>6} {r.event_id:>10} "
                  f"{r.ev_status:>8} {str(r.sport_key):>22} {str(r.team_null):>9} | "
                  f"{(r.market_name or '')[:60]}")

        print(f"\nSummary: {len(rows)} markets link to {len(event_ids)} events "
              f"→ {len(bogus_event_ids)} bogus (void) + {len(real_event_ids)} real "
              f"(unlink-only, NEVER voided).")
        if real_event_ids:
            print(f"  REAL events preserved (team-linked, not `*_other`): "
                  f"{sorted(real_event_ids)}")

        if not rows:
            print("\nNothing to repair — census already 0 (idempotent no-op).")
            return

        if not apply:
            print(f"\nDRY-RUN — pass --apply to: (1) unlink {len(rows)} markets "
                  f"(event_id→NULL), (2) void {len(bogus_event_ids)} bogus events "
                  f"(status→'voided'). No writes made.")
            return

        unlinked = (await s.execute(text(_UNLINK_SQL))).rowcount or 0
        voided = 0
        if bogus_event_ids:
            voided = (await s.execute(
                text(_VOID_SQL), {"event_ids": list(bogus_event_ids)}
            )).rowcount or 0
        await s.commit()
        print(f"\nCOMMITTED: unlinked {unlinked} markets, voided {voided} bogus events.")

        census = (await s.execute(text(_CENSUS_SQL))).one()
        print(f"POST-REPAIR CENSUS: {census.linked_markets} linked markets, "
              f"{census.linked_events} linked events (target: 0 / 0).")
        if census.linked_markets == 0:
            print("✅ #1220 census clean.")
        else:
            print("⚠️  residual links remain — investigate before closing #1220.")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
