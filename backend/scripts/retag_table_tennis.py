"""#1230 — retag mis-tagged Setka/TT-Cup table-tennis markets (data-repair lane).

#1230's finding: ~thousands of Polymarket Setka Cup / TT Cup table-tennis markets
land in ``llm_sport_category='baseball'``. They manufacture the alarming
"baseball open link-rate 7.4%" number and pollute the baseball feed/calibration
cohort. The fix retags them to ``table_tennis``.

THE SAFE PREDICATE (the whole point of this repair — protect real MLB):
A naive "baseball market with no MLB team token → table tennis" rule is UNSAFE —
it would wrongly retag real MLB *player props* ("Lane Thomas: Home Runs O/U 1.5",
"Gleyber Torres: Home Runs O/U 0.5"), which carry no team nickname. So we
positively identify table tennis by its unambiguous STRUCTURAL tells — a match
priced with "Total Games O/U" or "Game Handicap" (table tennis is scored in
games; baseball never is) — and expand safely along ``group_id``:

  * A Polymarket ``group_id`` is exactly one Poly event = one Setka match, so a
    group containing a TT-tell market also holds that match's bare winner and
    handicap siblings ("Mitul Anatoli vs. Bodac Alexandr"). Retagging by group
    catches those too.
  * A whole group is PROTECTED (never retagged) if ANY market in it carries an
    MLB team token OR a real-baseball-stat token (Home Runs / Strikeout / RBI /
    Innings / …). A genuine MLB event's group can therefore never be swept even
    if a name coincidentally matched a tell. Precision over recall by design.

Verified live (2026-07-23): 689 TT-tell groups → 674 eligible (all-clean),
15 protected; ~3,751 markets retag; real MLB player-prop groups untouched.

Uses SQLAlchemy Core with parameterized regexes (asyncpg-safe). Dry-run by
default; --apply to commit. Idempotent (a second run finds 0 baseball-tagged TT
groups). Session-taking ``repair()`` backs POST /api/admin/repairs/tt-retag
(Queue #247 Item 5).

    python3 scripts/retag_table_tennis.py            # dry-run census
    python3 scripts/retag_table_tennis.py --apply    # commit the retag

Heroku one-off (gotcha #48 — non-detached run does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):
    heroku run:detached "python scripts/retag_table_tennis.py --apply" -a bainluck
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- Safe-predicate token sets -------------------------------------------------
# TT structural tells: table tennis is scored in GAMES; baseball is not.
_TT_TELL = r"(Total Games|Game Handicap)"

# MLB team tokens (nicknames + the MLB tag). Presence anywhere in a group PROTECTS
# the whole group from retag.
_MLB_TOKEN = (
    r"(Yankees|Red Sox|Blue Jays|Rays|Orioles|Guardians|Twins|White Sox|Tigers|"
    r"Royals|Astros|Mariners|Rangers|Angels|Athletics|Braves|Mets|Phillies|"
    r"Marlins|Nationals|Cubs|Cardinals|Brewers|Reds|Pirates|Dodgers|Padres|"
    r"Giants|Diamondbacks|Rockies|MLB)"
)

# Real-baseball-stat tells — a group carrying any of these is a genuine baseball
# event and is PROTECTED (never a table-tennis match).
_BB_STAT = (
    r"(Home Runs|Strikeout|RBI|Innings|Total Bases|Earned Run|Stolen Base|"
    r"Hits O/U|Runs O/U)"
)

# One CTE classifies each Polymarket baseball group; a group is ELIGIBLE only if it
# has a TT tell AND no MLB token AND no baseball-stat token.
_GRP_CTE = f"""
    WITH grp AS (
        SELECT group_id,
               bool_or(name ~* :tt)  AS tt,
               bool_or(name ~* :mlb) AS mlb,
               bool_or(name ~* :bb)  AS bb
        FROM futures_markets
        WHERE source = 'polymarket'
          AND llm_sport_category = 'baseball'
          AND group_id IS NOT NULL
        GROUP BY group_id
    )
"""

_CENSUS_SQL = """
    SELECT
        (SELECT count(*) FROM futures_markets
           WHERE source='polymarket' AND llm_sport_category='baseball')      AS baseball,
        (SELECT count(*) FROM futures_markets
           WHERE source='polymarket' AND llm_sport_category='table_tennis')  AS table_tennis
"""

_GROUPS_SQL = _GRP_CTE + """
    SELECT
        count(*) FILTER (WHERE tt)                              AS tt_groups,
        count(*) FILTER (WHERE tt AND NOT mlb AND NOT bb)       AS eligible_groups,
        count(*) FILTER (WHERE tt AND (mlb OR bb))             AS protected_groups
    FROM grp
"""

_TARGET_COUNT_SQL = _GRP_CTE + """
    SELECT count(*) AS n
    FROM futures_markets f
    JOIN grp g USING (group_id)
    WHERE f.source='polymarket' AND f.llm_sport_category='baseball'
      AND g.tt AND NOT g.mlb AND NOT g.bb
"""

_RETAG_SQL = _GRP_CTE + """
    UPDATE futures_markets f
    SET llm_sport_category = 'table_tennis', updated_at = NOW()
    FROM grp g
    WHERE f.group_id = g.group_id
      AND f.source='polymarket' AND f.llm_sport_category='baseball'
      AND g.tt AND NOT g.mlb AND NOT g.bb
"""

_PARAMS = {"tt": _TT_TELL, "mlb": _MLB_TOKEN, "bb": _BB_STAT}


async def repair(session, apply: bool) -> dict:
    """Session-taking core (CLI + POST /api/admin/repairs/tt-retag). Does all work
    on ``session``; commits only when ``apply``. Returns a before/after census."""
    from sqlalchemy import text

    s = session
    before = (await s.execute(text(_CENSUS_SQL))).one()
    groups = (await s.execute(text(_GROUPS_SQL), _PARAMS)).one()
    target = (await s.execute(text(_TARGET_COUNT_SQL), _PARAMS)).one().n

    retagged = 0
    if apply and target:
        retagged = (await s.execute(text(_RETAG_SQL), _PARAMS)).rowcount or 0
        await s.commit()

    after = (await s.execute(text(_CENSUS_SQL))).one()
    return {
        "repair": "tt-retag",
        "applied": bool(apply),
        "tt_groups": groups.tt_groups,
        "eligible_groups": groups.eligible_groups,
        "protected_groups": groups.protected_groups,
        "target_markets": target,
        "retagged": retagged,
        "before": {"baseball": before.baseball, "table_tennis": before.table_tennis},
        "after": {"baseball": after.baseball, "table_tennis": after.table_tennis},
    }


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        result = await repair(s, apply)
    print("=== #1230 table-tennis retag ===")
    print(f"  TT-tell groups:   {result['tt_groups']}")
    print(f"  eligible (clean): {result['eligible_groups']}")
    print(f"  protected:        {result['protected_groups']} (MLB/baseball-stat token in group)")
    print(f"  target markets:   {result['target_markets']}")
    print(f"  before: baseball={result['before']['baseball']} "
          f"table_tennis={result['before']['table_tennis']}")
    if apply:
        print(f"  COMMITTED: retagged {result['retagged']} market(s) → table_tennis")
        print(f"  after:  baseball={result['after']['baseball']} "
              f"table_tennis={result['after']['table_tennis']}")
    else:
        print(f"  DRY-RUN — pass --apply to retag {result['target_markets']} market(s). "
              f"No writes made.")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
