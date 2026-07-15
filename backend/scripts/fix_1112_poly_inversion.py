"""#1112 — Evidence-gated historical correction of polymarket side-inversions.

Fixes the confirmed Class-A poly side-inversions on completed events: events
where polymarket's stored home_win_probability is the EXACT MIRROR of the true
outcome, confirmed by the score-derived stat_model AND at least one independent
live source. See issue #1112 / Queue #207 Item 1.

Two writes per event (both Core SQL — gotcha #4, JSONB ORM assignment silently
fails):
  1. events.win_probability_sources['polymarket']  := round(1 - old, 4)  (the blend)
  2. the CLOSING (latest captured_at) polymarket win_prob_snapshot row  (the value
     the Measure "disagreements" corpus reads): home/away probabilities flipped.

We deliberately DO NOT flip the whole poly snapshot series: 62/72 series cross
0.5, and we cannot cheaply distinguish a uniformly-inverted competitive game from
a series where `_check_and_fix_inversion` already flipped some polls — flipping
the whole series would risk re-inverting a guard-corrected snapshot. The blend +
closing value fully satisfy the acceptance criteria; full-series chart repair is
a tracked follow-up.

Class-B safety (verify-before-regrade, gotcha #21): the census EXCLUDES any event
where BOTH independent live sources (mlb AND espn) are extreme on poly's side —
that would mean the stored SCORE is suspect (a score-integrity Class-B case, Item
3), not a poly inversion. At census time this excluded 0 events.

Idempotent: re-running finds only events still matching the (now-empty) Class-A
predicate. Dry-run by default; pass --apply to commit.

    python3 scripts/fix_1112_poly_inversion.py            # dry-run (ledger only)
    python3 scripts/fix_1112_poly_inversion.py --apply    # commit the correction
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The Class-A predicate: poly extreme-wrong vs the recorded outcome, stat_model
# confirms the outcome, and NOT a hidden Class-B (both mlb+espn siding with poly).
_CLASS_A_WHERE = """
    status IN ('completed', 'closed')
    AND home_score IS NOT NULL AND away_score IS NOT NULL
    AND home_score <> away_score
    AND commence_time >= '2026-04-15'
    AND (win_probability_sources->>'polymarket') IS NOT NULL
    AND (win_probability_sources->>'stat_model') IS NOT NULL
    AND (
        (   -- home won, poly says home loses (mirror), stat_model confirms home won
            home_score > away_score
            AND (win_probability_sources->>'polymarket')::float <= 0.15
            AND (win_probability_sources->>'stat_model')::float >= 0.85
            -- Class-B guard: exclude ONLY if BOTH independent live sources are
            -- present AND extreme on poly's side (score suspect). NULL peers must
            -- not poison the predicate (they would three-value the NOT to NULL).
            AND NOT (
                (win_probability_sources->>'mlb') IS NOT NULL
                AND (win_probability_sources->>'espn') IS NOT NULL
                AND (win_probability_sources->>'mlb')::float <= 0.15
                AND (win_probability_sources->>'espn')::float <= 0.15
            )
        )
        OR
        (   -- away won, poly says home wins (mirror), stat_model confirms away won
            home_score < away_score
            AND (win_probability_sources->>'polymarket')::float >= 0.85
            AND (win_probability_sources->>'stat_model')::float <= 0.15
            AND NOT (
                (win_probability_sources->>'mlb') IS NOT NULL
                AND (win_probability_sources->>'espn') IS NOT NULL
                AND (win_probability_sources->>'mlb')::float >= 0.85
                AND (win_probability_sources->>'espn')::float >= 0.85
            )
        )
    )
"""


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        rows = (await s.execute(text(f"""
            SELECT id,
                   home_score, away_score,
                   (win_probability_sources->>'polymarket')::float AS poly,
                   (win_probability_sources->>'stat_model')::float AS sm
            FROM events
            WHERE {_CLASS_A_WHERE}
            ORDER BY commence_time DESC
        """))).all()

        ids = [r.id for r in rows]
        print(f"Class-A poly side-inversions matched: {len(ids)}")
        print(f"{'event_id':>10} {'score':>8} {'poly_old':>9} -> {'poly_new':>8}   stat_model")
        for r in rows:
            print(f"{r.id:>10} {r.home_score:>3}-{r.away_score:<3} "
                  f"{r.poly:>9.4f} -> {round(1 - r.poly, 4):>8.4f}   {r.sm:.4f}")

        if not ids:
            print("\nNothing to correct.")
            return

        if not apply:
            print(f"\nDRY-RUN — pass --apply to correct {len(ids)} events. No writes made.")
            return

        # 1) Flip the blend input (Core SQL for JSONB — gotcha #4).
        blend_res = await s.execute(text(f"""
            UPDATE events
            SET win_probability_sources = jsonb_set(
                win_probability_sources,
                '{{polymarket}}',
                to_jsonb(round((1 - (win_probability_sources->>'polymarket')::numeric), 4))
            )
            WHERE id = ANY(:ids)
        """), {"ids": ids})

        # 2) Flip the CLOSING poly snapshot (what the Measure corpus reads).
        #    new_home = 1 - old_home ; new_away = old_home (keeps home+away = 1).
        snap_res = await s.execute(text("""
            UPDATE win_prob_snapshots wp
            SET home_win_probability = round((1 - wp.home_win_probability)::numeric, 4),
                away_win_probability = round(wp.home_win_probability::numeric, 4)
            FROM (
                SELECT DISTINCT ON (event_id) id
                FROM win_prob_snapshots
                WHERE source = 'polymarket'
                  AND event_id = ANY(:ids)
                  AND home_win_probability IS NOT NULL
                ORDER BY event_id, captured_at DESC
            ) latest
            WHERE wp.id = latest.id
        """), {"ids": ids})

        await s.commit()
        print(f"\nAPPLIED: blends corrected on {blend_res.rowcount} events; "
              f"closing poly snapshots flipped on {snap_res.rowcount} events.")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
