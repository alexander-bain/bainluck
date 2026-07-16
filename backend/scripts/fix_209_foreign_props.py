"""#209 Item 2 — unlink FOREIGN props from settled event pages.

A matching-pass gap (mapped in the #209 forensic) set some Kalshi game/prop
markets' event_id to the WRONG game's event: an event ends up carrying markets
whose ticker game-id encodes a DIFFERENT matchup. Observed classes: college
basketball / tennis / WNCAAB games with a couple of foreign next-day moneylines
attached, and teamless esports events used as dumping grounds for dozens of
unrelated map markets. Exhibit context: /events/8488278 (Stanford-Pitt) — that
event's own props are clean; the CLASS is ~232 settled events.

This is the DATA half (fix-don't-hide). The render half — a defense-in-depth
filter that keeps only the true game's markets — ships in the game-markets
endpoint (`app/utils/prediction_market_matching.filter_foreign_game_markets`).
The write-path root-cause fix (matching passes) is link-rate-critical and is
handed back for its own queue.

TARGET predicate (conservative, evidence-gated, idempotent):
  * event has >1 distinct Kalshi TEAM-code among its linked markets, AND
  * at least one linked team-code's ticker DATE matches the event's commence date
    (so the event's TRUE game is unambiguously present), AND
  * the market's own team-code is NOT one of those true team-codes.
Such markets are unlinked (event_id := NULL — the same treatment as the existing
Phase-2 wrong-game unlink). Team-code (not the full date+teams game-id) is the
key, so legitimate same-matchup markets with a shifted resolution-date ticker
(e.g. KXNBAMENTION dated +1 day) are NOT unlinked. If NO team-code matches the
event date (a timezone-ambiguous event), the whole event is SKIPPED — never
unlink on doubt.

Never touches is_winner, prices, or the market rows themselves — only the
event_id FK. A re-run finds fewer/zero targets (idempotent).
Dry-run by default; pass --apply to commit.

    python3 scripts/fix_209_foreign_props.py            # dry-run (ledger only)
    python3 scripts/fix_209_foreign_props.py --apply    # commit the unlinks
"""
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Postgres-side TEAM-code extraction (mirror of utils.kalshi_game_teams) used
# only to cheaply find candidate events; the authoritative per-market decision is
# made in Python with the shared helpers.
_TEAMS_SQL = (
    "substring(external_id from "
    "'[0-9]{2}[A-Za-z]{3}[0-9]{1,2}(?:[0-9]{4})?([A-Za-z][A-Za-z0-9]*)')"
)

_CANDIDATE_EVENTS_SQL = f"""
    SELECT event_id
    FROM futures_markets
    WHERE event_id IS NOT NULL AND source = 'kalshi'
      AND {_TEAMS_SQL} IS NOT NULL
    GROUP BY event_id
    HAVING count(DISTINCT upper({_TEAMS_SQL})) > 1
"""

_MARKETS_SQL = """
    SELECT fm.id, fm.event_id, fm.external_id, e.commence_time
    FROM futures_markets fm
    JOIN events e ON e.id = fm.event_id
    WHERE fm.event_id = ANY(:ids) AND fm.source = 'kalshi'
    ORDER BY fm.event_id, fm.external_id
"""


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from app.utils.prediction_market_matching import (
        kalshi_game_teams,
        extract_game_date_from_ticker,
    )
    from sqlalchemy import text

    async with get_task_session() as s:
        event_ids = [r.event_id for r in
                     (await s.execute(text(_CANDIDATE_EVENTS_SQL))).all()]
        print(f"Candidate events (>1 distinct Kalshi game-id linked): {len(event_ids)}")
        if not event_ids:
            print("Nothing to do.")
            return

        rows = (await s.execute(text(_MARKETS_SQL), {"ids": event_ids})).all()
        by_event = defaultdict(list)
        for r in rows:
            by_event[r.event_id].append(r)

        foreign_ids: list = []
        skipped_ambiguous = 0
        ledger = []  # (event_id, kept_gids, foreign preview)
        for ev, ms in by_event.items():
            commence = ms[0].commence_time
            if commence is None:
                skipped_ambiguous += 1
                continue
            ev_date = commence.date()
            # Which TEAM-codes have a ticker date matching the event date?
            true_codes = set()
            code_of = {}
            for m in ms:
                tc = kalshi_game_teams(m.external_id)
                code_of[m.id] = tc
                if tc:
                    d = extract_game_date_from_ticker(m.external_id or "")
                    if d and d.date() == ev_date:
                        true_codes.add(tc)
            if not true_codes:
                skipped_ambiguous += 1  # no unambiguous true game — never unlink
                continue
            ev_foreign = [m for m in ms
                          if code_of[m.id] and code_of[m.id] not in true_codes]
            if ev_foreign:
                foreign_ids.extend(m.id for m in ev_foreign)
                ledger.append((ev, sorted(true_codes),
                               [(m.id, m.external_id) for m in ev_foreign]))

        print(f"Events with foreign props: {len(ledger)}  "
              f"(skipped ambiguous/no-true-game: {skipped_ambiguous})")
        print(f"Foreign markets to unlink: {len(foreign_ids)}\n")
        for ev, keep, foreign in ledger[:40]:
            print(f"event {ev}  true={keep}")
            for mid, ext in foreign[:6]:
                print(f"    unlink #{mid}  {ext}")
        if len(ledger) > 40:
            print(f"    ... and {len(ledger) - 40} more events")

        if not apply:
            print(f"\nDRY-RUN — pass --apply to unlink {len(foreign_ids)} foreign "
                  f"markets from {len(ledger)} events. No writes made.")
            return

        if foreign_ids:
            res = await s.execute(
                text("UPDATE futures_markets SET event_id = NULL WHERE id = ANY(:ids)"),
                {"ids": foreign_ids},
            )
            await s.commit()
            print(f"\nCOMMITTED: unlinked {res.rowcount} foreign markets "
                  f"from {len(ledger)} events.")
        else:
            print("\nNo foreign markets — nothing to unlink (idempotent no-op).")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
