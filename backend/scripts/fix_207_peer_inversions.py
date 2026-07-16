"""#208 Item 2 (from #207's find) — Evidence-gated correction of PEER-SOURCE
closing-snapshot inversions (espn / mlb / stat_model).

The #1112 work fixed polymarket side-inversions. Auditing the same corpus for the
*peer* sources it trusts to confirm poly (the tributaries feeding the blend)
surfaced the same disease in the peers themselves: a completed game where a peer's
stored home_win_probability is the EXACT MIRROR of the recorded outcome. Exhibit
event 14970356 (Rangers 3, Astros 9 — home LOST): mlb=0.985 (says home wins) while
espn=0.001, stat_model=0.001, polymarket=0.0005 all correctly read home≈0. The mlb
writer stored the away side. "The blend must be clean from EVERY tributary."

CLASS-A predicate (the ONLY set corrected — same conservatism as fix_1112):
  * completed/closed, real distinct scores, commence_time >= 2026-04-15
  * source S ∈ {espn, mlb, stat_model} is EXTREME-MIRROR-wrong vs the score
    (home won & S<=0.15, or home lost & S>=0.85)
  * BOTH sibling peers (the other two of espn/mlb/stat_model) are present AND
    DIRECTIONALLY CORRECT (agree with the score) — so S is the LONE inverted peer
    and the score is trustworthy (not a home/away swap).

CLASS-B is EXCLUDED (verify-before-regrade, gotchas #21/#32/#46): if a sibling peer
ALSO dissents from the score, the recorded score/home-away is suspect (a wrong-game
merge), not a lone peer inversion — those need matching-layer forensics, not a flip.
Events violating completed_at >= commence_time (gotcha #46) are excluded too.

Two writes per (event, source), both Core SQL (gotcha #4) — identical rails to
fix_1112_poly_inversion:
  1. events.win_probability_sources[S] := round(1 - old, 4)   (the blend input)
  2. the CLOSING (latest captured_at) win_prob_snapshot row for source=S: home/away
     probabilities flipped (what the Measure "disagreements" corpus reads).

Does NOT touch is_winner (authoritative; gotcha #21) nor the full snapshot series
(cannot distinguish a uniformly-inverted series from a guard-corrected one — the
#1112 lesson). Idempotent: a corrected row no longer matches the mirror predicate.
Dry-run by default; pass --apply to commit.

    python3 scripts/fix_207_peer_inversions.py            # dry-run (ledger only)
    python3 scripts/fix_207_peer_inversions.py --apply    # commit the correction
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PEERS = ("espn", "mlb", "stat_model")


def _class_a_where(S: str, p1: str, p2: str) -> str:
    """Class-A predicate for peer source S with sibling peers p1, p2."""
    return f"""
        status IN ('completed', 'closed')
        AND home_score IS NOT NULL AND away_score IS NOT NULL
        AND home_score <> away_score
        AND commence_time >= '2026-04-15'
        AND (completed_at IS NULL OR completed_at >= commence_time)  -- gotcha #46
        AND (win_probability_sources->>'{S}')  IS NOT NULL
        AND (win_probability_sources->>'{p1}') IS NOT NULL
        AND (win_probability_sources->>'{p2}') IS NOT NULL
        AND (
            (   -- home WON, S says home loses (mirror); both siblings agree home won
                home_score > away_score
                AND (win_probability_sources->>'{S}')::float  <= 0.15
                AND (win_probability_sources->>'{p1}')::float > 0.5
                AND (win_probability_sources->>'{p2}')::float > 0.5
            )
            OR
            (   -- home LOST, S says home wins (mirror); both siblings agree home lost
                home_score < away_score
                AND (win_probability_sources->>'{S}')::float  >= 0.85
                AND (win_probability_sources->>'{p1}')::float < 0.5
                AND (win_probability_sources->>'{p2}')::float < 0.5
            )
        )
    """


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    total_blend = 0
    total_snap = 0
    grand_ids: dict[str, list] = {}

    async with get_task_session() as s:
        for S in _PEERS:
            p1, p2 = [p for p in _PEERS if p != S]
            where = _class_a_where(S, p1, p2)
            rows = (await s.execute(text(f"""
                SELECT id, home_score, away_score,
                       (win_probability_sources->>'{S}')::float  AS s_val,
                       (win_probability_sources->>'{p1}')::float AS p1_val,
                       (win_probability_sources->>'{p2}')::float AS p2_val
                FROM events
                WHERE {where}
                ORDER BY commence_time DESC
            """))).all()
            ids = [r.id for r in rows]
            grand_ids[S] = ids
            print(f"\n=== {S} lone-inverted (siblings {p1}/{p2} both correct): {len(ids)} ===")
            print(f"{'event_id':>10} {'score':>8} {S+'_old':>10} -> {'new':>7}   {p1}/{p2}")
            for r in rows:
                print(f"{r.id:>10} {r.home_score:>3}-{r.away_score:<3} "
                      f"{r.s_val:>10.4f} -> {round(1 - r.s_val, 4):>7.4f}   "
                      f"{r.p1_val:.3f}/{r.p2_val:.3f}")

            if not ids:
                continue
            if not apply:
                continue

            # 1) Flip the blend input for source S (Core SQL for JSONB — gotcha #4).
            blend_res = await s.execute(text(f"""
                UPDATE events
                SET win_probability_sources = jsonb_set(
                    win_probability_sources,
                    '{{{S}}}',
                    to_jsonb(round((1 - (win_probability_sources->>'{S}')::numeric), 4))
                )
                WHERE id = ANY(:ids)
            """), {"ids": ids})

            # 2) Flip the CLOSING snapshot row for source S (home<->away).
            snap_res = await s.execute(text("""
                UPDATE win_prob_snapshots wp
                SET home_win_probability = round((1 - wp.home_win_probability)::numeric, 4),
                    away_win_probability = CASE
                        WHEN wp.away_win_probability IS NOT NULL
                        THEN round(wp.home_win_probability::numeric, 4)
                        ELSE wp.away_win_probability END
                FROM (
                    SELECT DISTINCT ON (event_id) id
                    FROM win_prob_snapshots
                    WHERE source = :src
                      AND event_id = ANY(:ids)
                      AND home_win_probability IS NOT NULL
                    ORDER BY event_id, captured_at DESC
                ) latest
                WHERE wp.id = latest.id
            """), {"src": S, "ids": ids})

            total_blend += blend_res.rowcount
            total_snap += snap_res.rowcount
            print(f"  APPLIED {S}: blends {blend_res.rowcount}, closing snapshots {snap_res.rowcount}")

        counts = {k: len(v) for k, v in grand_ids.items()}
        grand = sum(counts.values())
        print(f"\nLEDGER: {counts}  (total {grand})")
        if apply:
            await s.commit()
            print(f"COMMITTED: {total_blend} blend inputs + {total_snap} closing snapshots flipped.")
        else:
            print(f"\nDRY-RUN — pass --apply to correct {grand} peer inversions. No writes made.")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
