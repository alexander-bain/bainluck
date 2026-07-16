"""#210 Item 2 — unlink the dominant-plurality wrong-game subset (the #209 residual).

#209's fix_209_foreign_props.py resolved the DATE-ANCHORED foreign-prop class:
events where at least one linked Kalshi team-code's ticker date matches the
event's commence date (so the event's TRUE game is unambiguous — unlink the
rest). It deliberately SKIPPED events where NO team-code's ticker date matched
the event date — ~923 events whose true game can't be pinned by date alone.

#209 split that residual:
  * ~782 genuinely AMBIGUOUS — teamless esports tournament dumps (dozens of
    same-date LOL/CS2/Valorant matches on one event) and same-day college
    doubleheaders. No single game dominates; resolving them needs the
    college/esports team-identity matcher (follow-up issue).
  * ~141 have a clear DOMINANT-GAME PLURALITY — one team-code owns a strong
    majority of the event's markets, the rest are a few foreign strays. This
    subset is safe to resolve by plurality.

This script handles ONLY the dominant-plurality subset (fix-don't-hide):
keep the dominant team-code's markets, unlink the minority foreign strays
(event_id := NULL — same treatment as the Phase-2 wrong-game unlink). It never
touches is_winner, prices, or the market rows — only the event_id FK.

DOMINANT-PLURALITY predicate (conservative, evidence-gated, idempotent):
  * event has >1 distinct Kalshi team-code among linked markets, AND
  * NO team-code's ticker date matches the event commence date (so this is the
    #209 residual, NOT the already-resolved date-anchored class), AND
  * one team-code is the UNIQUE maximum by market count, has >= 2 markets, and
    is DOMINANT: it holds >= 60% of the event's coded markets OR at least twice
    the runner-up's count.
Events that don't clear the dominance bar (ties, flat esports dumps) are counted
as `ambiguous_deferred` and left untouched for the team-identity matcher.

Dry-run by default; pass --apply to commit.

    python3 scripts/fix_210_dominant_plurality.py            # dry-run (ledger only)
    python3 scripts/fix_210_dominant_plurality.py --apply    # commit the unlinks
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

# Dominance thresholds — a game must clearly own the event to be kept.
_MIN_KEEP_MARKETS = 2
_DOMINANT_FRACTION = 0.60
_DOMINANT_RATIO = 2.0


def _dominant_code(counts: dict) -> str | None:
    """Return the uniquely-dominant team-code, or None if the event is ambiguous.

    counts: team-code -> number of coded markets. Dominant means: a unique max
    with >= _MIN_KEEP_MARKETS markets that holds >= 60% of coded markets OR at
    least 2x the runner-up.
    """
    if len(counts) < 2:
        return None
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    (top_code, top_n), (_, second_n) = ordered[0], ordered[1]
    if top_n < _MIN_KEEP_MARKETS:
        return None
    if top_n == second_n:  # tie for first — not unique
        return None
    total = sum(counts.values())
    if top_n / total >= _DOMINANT_FRACTION or top_n >= _DOMINANT_RATIO * second_n:
        return top_code
    return None


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
        print(f"Candidate events (>1 distinct Kalshi team-code linked): {len(event_ids)}")
        if not event_ids:
            print("Nothing to do.")
            return

        rows = (await s.execute(text(_MARKETS_SQL), {"ids": event_ids})).all()
        by_event = defaultdict(list)
        for r in rows:
            by_event[r.event_id].append(r)

        foreign_ids: list = []
        date_anchored_skipped = 0   # #209's class — already resolved
        ambiguous_deferred = 0      # the ~782 — no dominant game
        ledger = []                 # (event_id, kept_code, kept_n, foreign preview)
        for ev, ms in by_event.items():
            commence = ms[0].commence_time
            if commence is None:
                ambiguous_deferred += 1
                continue
            ev_date = commence.date()
            code_of = {}
            counts: dict = defaultdict(int)
            has_date_match = False
            for m in ms:
                tc = kalshi_game_teams(m.external_id)
                code_of[m.id] = tc
                if tc:
                    counts[tc] += 1
                    d = extract_game_date_from_ticker(m.external_id or "")
                    if d and d.date() == ev_date:
                        has_date_match = True
            if has_date_match:
                # #209's date-anchored class — resolved by fix_209_foreign_props.
                date_anchored_skipped += 1
                continue
            keep = _dominant_code(counts)
            if keep is None:
                ambiguous_deferred += 1
                continue
            ev_foreign = [m for m in ms
                          if code_of[m.id] and code_of[m.id] != keep]
            if ev_foreign:
                foreign_ids.extend(m.id for m in ev_foreign)
                ledger.append((ev, keep, counts[keep],
                               [(m.id, m.external_id) for m in ev_foreign]))

        print(f"Date-anchored (fix_209 class, skipped): {date_anchored_skipped}")
        print(f"Ambiguous deferred (need team-identity matcher): {ambiguous_deferred}")
        print(f"Dominant-plurality events resolved: {len(ledger)}")
        print(f"Foreign markets to unlink: {len(foreign_ids)}\n")
        for ev, keep, keep_n, foreign in ledger[:60]:
            print(f"event {ev}  keep={keep} ({keep_n} mkts)")
            for mid, ext in foreign[:6]:
                print(f"    unlink #{mid}  {ext}")
            if len(foreign) > 6:
                print(f"    ... and {len(foreign) - 6} more foreign markets")
        if len(ledger) > 60:
            print(f"    ... and {len(ledger) - 60} more events")

        if not apply:
            print(f"\nDRY-RUN — pass --apply to unlink {len(foreign_ids)} foreign "
                  f"markets from {len(ledger)} dominant-plurality events. No writes.")
            return

        if foreign_ids:
            res = await s.execute(
                text("UPDATE futures_markets SET event_id = NULL WHERE id = ANY(:ids)"),
                {"ids": foreign_ids},
            )
            await s.commit()
            print(f"\nCOMMITTED: unlinked {res.rowcount} foreign markets "
                  f"from {len(ledger)} dominant-plurality events.")
        else:
            print("\nNo foreign markets — nothing to unlink (idempotent no-op).")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
