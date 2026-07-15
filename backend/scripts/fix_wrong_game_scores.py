"""#207 Item 3 — Class-B wrong-game score correction (re-derive per gotcha #32/#46).

A class of completed events carry a WRONG stored final score (a different game's
score written over the real one), while their win-probability sources
(stat_model/mlb/espn) stayed CORRECT. Signature: the score-derived stat_model
contradicts the recorded winner. Census (2026-07-15) found 59 candidates; ESPN
ground-truth showed 44 are genuinely wrong (team-verified), 15 are FALSE
positives (stored == ESPN; stat_model was merely a stale mid-game value) and must
never be touched. Full ledger in the Queue #207 report.

This re-derives the authoritative final score from ESPN's summary endpoint and
corrects `home_score`/`away_score` ONLY when:
  1. ESPN reports a completed game with an integer final score, AND
  2. ESPN's home & away teams token-match OUR home & away teams (identity guard —
     never trust a possibly-mislinked espn_id blindly), AND
  3. the stored score actually DIFFERS from ESPN's (auto-skips the 15 stale-but-
     correct false positives, and makes the run idempotent).

Does NOT touch is_winner / calibration (gotcha #21). Correcting the score makes
the event page + score-derived inputs authoritative; is_winner re-resolution is a
tracked follow-up (the lower-authority score path will re-derive; it never
overwrites an api_settlement — resolution_authority.py).

    python3 scripts/fix_wrong_game_scores.py            # dry-run (ledger only)
    python3 scripts/fix_wrong_game_scores.py --apply    # commit the corrections
"""
import asyncio
import gzip
import json
import os
import ssl
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# sport key -> ESPN summary path
_SPORT_PATH = {
    "baseball_mlb": "baseball/mlb",
    "baseball_ncaa": "baseball/college-baseball",
    "basketball_nba": "basketball/nba",
}

_CANDIDATE_SQL = """
    SELECT e.id, e.espn_id, s.key AS sport,
           ht.name AS home_team, at.name AS away_team,
           e.home_score AS hs, e.away_score AS aws
    FROM events e
    JOIN sports s ON s.id = e.sport_id
    LEFT JOIN teams ht ON ht.id = e.home_team_id
    LEFT JOIN teams at ON at.id = e.away_team_id
    WHERE e.status IN ('completed', 'closed')
      AND e.home_score IS NOT NULL AND e.away_score IS NOT NULL
      AND e.home_score <> e.away_score
      AND e.commence_time >= '2026-04-15'
      AND e.espn_id IS NOT NULL
      AND (e.win_probability_sources->>'stat_model') IS NOT NULL
      AND (
          (e.home_score > e.away_score AND (e.win_probability_sources->>'stat_model')::float <= 0.15)
          OR
          (e.home_score < e.away_score AND (e.win_probability_sources->>'stat_model')::float >= 0.85)
      )
    ORDER BY e.commence_time DESC
"""

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _tokens(s: str) -> set:
    return set((s or "").lower().replace(".", "").split())


def _espn_final(path: str, espn_id: str):
    """Return (home_team, home_score:int, away_team, away_score:int) for a
    COMPLETED game, else None."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/summary?event={espn_id}"
    req = urllib.request.Request(
        url, headers={"Accept-Encoding": "gzip", "User-Agent": "Mozilla/5.0"},
    )
    raw = urllib.request.urlopen(req, timeout=20, context=_CTX).read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    d = json.loads(raw)
    comp = (d.get("header", {}).get("competitions") or [{}])[0]
    if not comp.get("status", {}).get("type", {}).get("completed", False):
        return None
    hs = as_ = ht = at = None
    for c in comp.get("competitors", []):
        if c.get("homeAway") == "home":
            hs, ht = c.get("score"), c.get("team", {}).get("displayName")
        elif c.get("homeAway") == "away":
            as_, at = c.get("score"), c.get("team", {}).get("displayName")
    try:
        return (ht, int(hs), at, int(as_))
    except (TypeError, ValueError):
        return None


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        rows = (await s.execute(text(_CANDIDATE_SQL))).all()
        print(f"Class-B candidates (stat_model contradicts recorded score): {len(rows)}")

        corrections = []   # (id, (old_h,old_a), (new_h,new_a))
        skipped = {"no_path": 0, "espn_incomplete": 0, "team_mismatch": 0, "stored_correct": 0}

        for r in rows:
            path = _SPORT_PATH.get(r.sport)
            if not path:
                skipped["no_path"] += 1
                continue
            try:
                res = _espn_final(path, r.espn_id)
            except Exception as e:
                skipped["espn_incomplete"] += 1
                print(f"  {r.id}: ESPN fetch error {type(e).__name__}: {str(e)[:50]}")
                continue
            if not res:
                skipped["espn_incomplete"] += 1
                continue
            eht, ehs, eat, eas = res
            if not (_tokens(r.home_team) & _tokens(eht)) or not (_tokens(r.away_team) & _tokens(eat)):
                skipped["team_mismatch"] += 1
                print(f"  {r.id}: TEAM MISMATCH ours '{r.home_team}'/'{r.away_team}' vs "
                      f"ESPN '{eht}'/'{eat}' — needs manual review, skipped")
                continue
            if r.hs == ehs and r.aws == eas:
                skipped["stored_correct"] += 1  # false positive (stale stat_model)
                continue
            corrections.append((r.id, (r.hs, r.aws), (ehs, eas)))
            print(f"  {r.id}  {r.home_team} v {r.away_team}: stored {r.hs}-{r.aws} -> ESPN {ehs}-{eas}")

        print(f"\nCONFIRMED wrong-score + team-verified: {len(corrections)}")
        print(f"skipped: {skipped}")

        if not corrections:
            print("Nothing to correct.")
            return
        if not apply:
            print(f"\nDRY-RUN — pass --apply to correct {len(corrections)} scores. No writes made.")
            return

        for eid, _old, (nh, na) in corrections:
            await s.execute(
                text("UPDATE events SET home_score = :h, away_score = :a WHERE id = :id"),
                {"h": nh, "a": na, "id": eid},
            )
        await s.commit()
        print(f"\nAPPLIED: corrected {len(corrections)} wrong-game scores from ESPN authority. "
              f"is_winner NOT touched (gotcha #21) — re-resolution is a tracked follow-up.")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
