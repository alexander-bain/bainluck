"""#7354 — the one-command undo for the settled-orientation-swap repair (D51(b)).

Reads `bak_7354_settled_orientation_swap` and puts every event it names back the
way production held it before the repair ran: the score, the ESPN win
probability, the blend's ESPN leg, and the two observation series.

    python3 scripts/restore_7354_settled_orientation_swap.py            # dry run
    python3 scripts/restore_7354_settled_orientation_swap.py --apply

Heroku one-off (gotcha #48 — non-detached returns empty stdout that reads like
success; PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):

    heroku run:detached -a bainluck \\
      "python3 scripts/restore_7354_settled_orientation_swap.py --apply"

🔴 THE DRY RUN CANNOT BE PAID BEFORE THE APPLY THAT CREATES ITS RESTORE POINT.
The repair creates the backup table, so before any apply this script can only
report an absent table and exit 1. That is the correct answer, not a failure —
a populated dry run is a POST-apply step.

WHAT THE UNDO DELIBERATELY DOES NOT DO
--------------------------------------
🔴 It does not restore an event that has moved on from the state the repair left
it in. The compare-and-swap is on the `new_*` manifest — what WE left behind —
never on "the live row differs from its backup". On this cohort that distinction
is not theoretical: the whole population is rows ESPN adjudicates, and ESPN
correcting its own final again is exactly the outcome that must be allowed
through. An undo keyed on difference would revert the authority's newer score.

🔴 THE COMPARE-AND-SWAP COVERS EVERY RESTORED COLUMN. The score, the ESPN win
probability AND the blend are all in the manifest and all in the WHERE, because
restoring three columns while observing one is a blind overwrite for the other
two — and the blend has a routine newer-value case (`backfill_winners` and any
re-resolve rewrite it without touching the score) that no amount of care about
the score can see. That is the CERT-3141 lesson, inherited from #7147's rail.

🔴 THE SERIES ARE RESTORED AS PART OF THE EVENT, UNDER THE EVENT'S OWN CAS.
`espn_snapshots` and `score_snapshots` were repaired by an exchange of two
columns, and an exchange is its own inverse, so the undo re-runs the same swap
rather than restoring banked values row by row. That is only sound while the
event is provably still in the state the repair left it in — so a series is
swapped back only for events whose row-level CAS passed in this same run, and
only when the repair recorded a non-zero row count for that series. An event
that moved on keeps BOTH halves: no score restored, no series swapped, reported
by id and skipped. Restoring one half of a swapped pair is how a row ends up in
a state neither the repair nor production ever produced (#3780, same argument).

🔴 NOTHING BUT THE EVENT ID IS BOUND. Both the values written and the values
compared come out of the backup table by column reference in one `UPDATE ...
FROM`, so no `numeric` and no `jsonb` ever round-trips through a bind parameter.
That is not tidiness — it is the only form that WORKS: a jsonb column read
through `text()` comes back as a dict, and handing that dict to an untyped bind
reaches `_jsonb_encoder(str_value)` and raises AttributeError on the first row
with a banked blend (CERT-932). `tests/test_restore_jsonb_bind_contract.py`
guards the restores that must obey this.

It does not drop the backup table. A restore that destroys its own evidence
cannot be re-run, and the repair is idempotent precisely so the pair can be
exercised more than once.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.repair_7354_settled_orientation_swap import BAK_TABLE  # noqa: E402

_EXISTS_SQL = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"

_CENSUS_SQL = f"""
    SELECT b.event_id,
           b.old_home_score, b.old_away_score,
           b.new_home_score, b.new_away_score,
           e.home_score, e.away_score,
           b.espn_snapshot_rows, b.score_snapshot_rows, b.espn_leg_rows,
           (e.home_score IS NOT DISTINCT FROM b.new_home_score
            AND e.away_score IS NOT DISTINCT FROM b.new_away_score
            AND e.espn_win_prob_home IS NOT DISTINCT FROM b.new_espn_win_prob_home
            AND e.win_probability_sources
                IS NOT DISTINCT FROM b.new_win_probability_sources) AS cas_ok
      FROM {BAK_TABLE} b
      JOIN events e ON e.id = b.event_id
     ORDER BY b.event_id
"""

#: One statement, no binds. The CAS names all four manifest columns; an event
#: that has moved on simply does not match and is left alone.
_RESTORE_EVENT_SQL = f"""
    UPDATE events e
       SET home_score              = b.old_home_score,
           away_score              = b.old_away_score,
           espn_win_prob_home      = b.old_espn_win_prob_home,
           win_probability_sources = b.old_win_probability_sources
      FROM {BAK_TABLE} b
     WHERE e.id = b.event_id
       AND e.home_score IS NOT DISTINCT FROM b.new_home_score
       AND e.away_score IS NOT DISTINCT FROM b.new_away_score
       AND e.espn_win_prob_home IS NOT DISTINCT FROM b.new_espn_win_prob_home
       AND e.win_probability_sources
           IS NOT DISTINCT FROM b.new_win_probability_sources
    RETURNING e.id
"""

_UNSWAP_ESPN_SNAPSHOTS_SQL = """
    UPDATE espn_snapshots
       SET home_score = away_score, away_score = home_score,
           home_win_probability = away_win_probability,
           away_win_probability = home_win_probability
     WHERE event_id = ANY(CAST(:event_ids AS bigint[]))
"""

_UNSWAP_SCORE_SNAPSHOTS_SQL = """
    UPDATE score_snapshots
       SET home_score = away_score, away_score = home_score
     WHERE event_id = ANY(CAST(:event_ids AS bigint[]))
"""

_UNSWAP_ESPN_LEG_SQL = """
    UPDATE win_prob_snapshots
       SET home_win_probability = away_win_probability,
           away_win_probability = home_win_probability
     WHERE event_id = ANY(CAST(:event_ids AS bigint[])) AND source = 'espn'
"""


async def restore(session, apply: bool) -> dict:
    """Put back what the repair wrote, for every event that has not moved on."""
    from sqlalchemy import text

    exists = (await session.execute(text(_EXISTS_SQL))).scalar()
    if not exists:
        return {"table_missing": True, "banked": 0, "restorable": 0,
                "moved_on": [], "restored": 0, "rows": {}}

    census = (await session.execute(text(_CENSUS_SQL))).mappings().all()
    restorable = [r for r in census if r["cas_ok"]]
    moved_on = [r["event_id"] for r in census if not r["cas_ok"]]

    res = {
        "table_missing": False,
        "banked": len(census),
        "restorable": len(restorable),
        "moved_on": moved_on,
        "restored": 0,
        "rows": {"espn_snapshots": 0, "score_snapshots": 0, "espn_leg": 0},
        "census": census,
    }
    if not apply:
        return res

    restored_ids = [r[0] for r in (await session.execute(text(_RESTORE_EVENT_SQL))).all()]
    res["restored"] = len(restored_ids)

    # The series are swapped back ONLY for events whose row CAS just passed, and
    # only where the repair recorded a non-zero count for that series — a series
    # the repair left alone must not be swapped by its undo.
    banked = {r["event_id"]: r for r in census}
    for key, sql, col in (
        ("espn_snapshots", _UNSWAP_ESPN_SNAPSHOTS_SQL, "espn_snapshot_rows"),
        ("score_snapshots", _UNSWAP_SCORE_SNAPSHOTS_SQL, "score_snapshot_rows"),
        ("espn_leg", _UNSWAP_ESPN_LEG_SQL, "espn_leg_rows"),
    ):
        ids = [i for i in restored_ids if (banked.get(i) or {}).get(col)]
        if not ids:
            continue
        r = await session.execute(text(sql), {"event_ids": ids})
        res["rows"][key] = r.rowcount or 0

    await session.commit()
    return res


async def run(apply: bool) -> int:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        res = await restore(s, apply)

    print(f"=== #7354 restore ({'APPLY' if apply else 'DRY-RUN'}) ===")
    if res["table_missing"]:
        print(f"{BAK_TABLE} does not exist — the repair has never applied on this "
              f"database, so there is nothing to restore. This is the expected "
              f"answer before the first apply, not a failure.")
        return 1

    print(f"banked={res['banked']} restorable={res['restorable']} "
          f"moved_on={len(res['moved_on'])}")
    for r in res["census"][:60]:
        if r["cas_ok"]:
            print(f"  [restore] ev{r['event_id']}: "
                  f"{r['new_home_score']}-{r['new_away_score']} -> "
                  f"{r['old_home_score']}-{r['old_away_score']} "
                  f"(series: espn={r['espn_snapshot_rows']} "
                  f"score={r['score_snapshot_rows']} leg={r['espn_leg_rows']})")
        else:
            print(f"  [moved_on] ev{r['event_id']}: live {r['home_score']}-"
                  f"{r['away_score']} is not what the repair left "
                  f"({r['new_home_score']}-{r['new_away_score']}) — left alone")

    if apply:
        print(f"\nRESTORED events={res['restored']} rows={res['rows']}")
        print(f"{BAK_TABLE} is deliberately NOT dropped — it is the evidence.")
    else:
        print("\nDRY-RUN — pass --apply to restore.")
    return 0


USAGE = """restore_7354_settled_orientation_swap — the undo for the #7354 repair

  --apply             commit the restore (default is a dry-run that writes nothing)
  --help              print this and exit without opening a database

Reports `table_missing` and exits 1 before the repair has ever applied — that is
the expected pre-apply answer, not a failure. Only events still in the state the
repair left them in are restored; one that has moved on keeps both halves.
"""

if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print(USAGE)
        sys.exit(0)
    sys.exit(asyncio.run(run("--apply" in sys.argv)))
