"""#209 Item 1 — flip the inverted MID-GAME mlb snapshot SERIES on the settled
events that #208 Item 2 only half-corrected.

Background: #208 Item 2 (`fix_207_peer_inversions.py`) corrected the mlb
orientation-swap disease at the BLEND input and the CLOSING (latest captured_at)
snapshot only — deliberately, per the #1112 rails, because a uniformly-inverted
series could not then be distinguished from a guard-corrected one. That left the
settled-event CHART still rendering the inverted mid-game mlb line: the home
win-prob climbs to the *mirror* (e.g. 0.99 for a team that lost 3-9) across the
whole series, then discontinuously CLIFFS to the corrected closing value at the
very last snapshot. Exhibit 14970356 (Rangers 3, Astros 9): body ends 0.966,
closing 0.015 — a ~0.95 cliff between the final two 2-minute snapshots that no
real game produces. That cliff IS the #208-flipped-closing fingerprint.

For mlb the swap is DETERMINISTIC per-event (the writer stored the away side for
the ENTIRE series), so the full-series flip is now safe: invert every mlb
snapshot EXCEPT the already-corrected closing row.

TARGET predicate (identical conservatism to fix_207 — same peer-agreement gate so
the score is trustworthy, gotchas #21/#32/#46):
  Candidate = settled, real distinct scores, commence_time >= 2026-04-15,
    completed_at >= commence_time, all three of mlb/espn/stat_model present, and
    the mlb blend + both sibling peers now AGREE with the score (the post-#208
    corrected Class-A signature). Then, among candidates, an event is a TARGET iff
    its mlb series shows the closing-only-flip fingerprint:
      * the closing (latest captured_at) snapshot is EXTREME (<=0.2 or >=0.8) and
        AGREES with the final score, AND
      * the second-to-last snapshot is on the OPPOSITE side of 0.5, AND
      * |closing - second_to_last| > 0.4 (the artificial cliff).
    The extreme-and-agrees closing gate excludes the two `last_notok` events whose
    closing DISAGREES with the score (possible wrong-game merge / genuine late
    swing) — verify-before-regrade, not a flip.

Correction (one Core-SQL UPDATE, gotcha #4): for every TARGET event, flip
home<->away on every mlb snapshot EXCEPT the closing (latest captured_at) row,
which #208 already corrected. Never touches is_winner (authoritative; gotcha #21),
never the blend (already correct), never the closing snapshot (already correct).

Idempotent: after the flip the body agrees with the closing (same side), so the
opposite-side cliff gate no longer matches — a corrected event is not re-selected.
Dry-run by default; pass --apply to commit.

    python3 scripts/fix_209_mlb_series_flip.py            # dry-run (ledger only)
    python3 scripts/fix_209_mlb_series_flip.py --apply    # commit the correction
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Post-#208 corrected Class-A signature: the mlb blend + both sibling peers now
# agree with the score (so the score/home-away is trustworthy).
_CANDIDATE_SQL = """
    SELECT id, home_score AS hs, away_score AS aw
    FROM events
    WHERE status IN ('completed', 'closed')
      AND home_score IS NOT NULL AND away_score IS NOT NULL
      AND home_score <> away_score
      AND commence_time >= '2026-04-15'
      AND (completed_at IS NULL OR completed_at >= commence_time)   -- gotcha #46
      AND (win_probability_sources->>'mlb')        IS NOT NULL
      AND (win_probability_sources->>'espn')       IS NOT NULL
      AND (win_probability_sources->>'stat_model') IS NOT NULL
      AND (
        (   -- home LOST, all three sources now read home<0.5 (mlb corrected extreme)
            home_score < away_score
            AND (win_probability_sources->>'mlb')::float        <= 0.15
            AND (win_probability_sources->>'espn')::float       <  0.5
            AND (win_probability_sources->>'stat_model')::float <  0.5
        )
        OR
        (   -- home WON, all three sources now read home>0.5
            home_score > away_score
            AND (win_probability_sources->>'mlb')::float        >= 0.85
            AND (win_probability_sources->>'espn')::float       >  0.5
            AND (win_probability_sources->>'stat_model')::float >  0.5
        )
      )
"""

# Among candidates, select the closing-only-flip fingerprint from the mlb series.
_TARGET_SQL = """
    WITH cand AS (%s),
    s AS (
        SELECT event_id, home_win_probability AS hwp,
               ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY captured_at DESC) AS rn,
               COUNT(*)     OVER (PARTITION BY event_id) AS n
        FROM win_prob_snapshots
        WHERE source = 'mlb' AND home_win_probability IS NOT NULL
          AND event_id IN (SELECT id FROM cand)
    )
    SELECT c.id, c.hs, c.aw, MAX(c2.n) AS n,
           MAX(CASE WHEN c2.rn = 1 THEN c2.hwp END) AS closing,
           MAX(CASE WHEN c2.rn = 2 THEN c2.hwp END) AS prev
    FROM cand c
    JOIN s c2 ON c2.event_id = c.id
    GROUP BY c.id, c.hs, c.aw
    HAVING
      (   -- home LOST: closing correctly low & extreme, prev is the mirror (high)
          c.hs < c.aw
          AND MAX(CASE WHEN c2.rn = 1 THEN c2.hwp END) <= 0.2
          AND MAX(CASE WHEN c2.rn = 2 THEN c2.hwp END) >  0.5
          AND ABS(MAX(CASE WHEN c2.rn = 1 THEN c2.hwp END)
                - MAX(CASE WHEN c2.rn = 2 THEN c2.hwp END)) > 0.4
      )
      OR
      (   -- home WON: closing correctly high & extreme, prev is the mirror (low)
          c.hs > c.aw
          AND MAX(CASE WHEN c2.rn = 1 THEN c2.hwp END) >= 0.8
          AND MAX(CASE WHEN c2.rn = 2 THEN c2.hwp END) <  0.5
          AND ABS(MAX(CASE WHEN c2.rn = 1 THEN c2.hwp END)
                - MAX(CASE WHEN c2.rn = 2 THEN c2.hwp END)) > 0.4
      )
    ORDER BY c.id
""" % _CANDIDATE_SQL


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        targets = (await s.execute(text(_TARGET_SQL))).all()
        ids = [r.id for r in targets]

        print(f"=== #209 Item 1 target set: {len(ids)} settled mlb events with an "
              f"inverted mid-game series (closing-only-flip fingerprint) ===")
        print(f"{'event_id':>10} {'score':>8} {'n':>4} {'closing':>8} {'prev(rn2)':>10}")
        for r in targets:
            print(f"{r.id:>10} {r.hs:>3}-{r.aw:<3} {r.n:>4} "
                  f"{float(r.closing):>8.3f} {float(r.prev):>10.3f}")

        if not ids:
            print("\nNo targets — nothing to flip (idempotent no-op).")
            return

        if not apply:
            print(f"\nDRY-RUN — pass --apply to flip the body (every mlb snapshot "
                  f"EXCEPT the closing row) on {len(ids)} events. No writes made.")
            return

        # Flip home<->away on every mlb snapshot for the target events EXCEPT the
        # closing (latest captured_at) row, which #208 already corrected.
        res = await s.execute(text("""
            UPDATE win_prob_snapshots wp
            SET home_win_probability = round((1 - wp.home_win_probability)::numeric, 4),
                away_win_probability = CASE
                    WHEN wp.away_win_probability IS NOT NULL
                    THEN round(wp.home_win_probability::numeric, 4)
                    ELSE wp.away_win_probability END
            WHERE wp.source = 'mlb'
              AND wp.event_id = ANY(:ids)
              AND wp.home_win_probability IS NOT NULL
              AND wp.id NOT IN (
                  SELECT DISTINCT ON (event_id) id
                  FROM win_prob_snapshots
                  WHERE source = 'mlb' AND event_id = ANY(:ids)
                    AND home_win_probability IS NOT NULL
                  ORDER BY event_id, captured_at DESC
              )
        """), {"ids": ids})
        await s.commit()
        print(f"\nCOMMITTED: flipped {res.rowcount} mid-game mlb snapshots across "
              f"{len(ids)} events (closing rows left untouched).")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
