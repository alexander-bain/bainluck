"""Shape rules for `Team.standings_data` at the serving boundary.

Imports nothing, so it stays circular-import safe for both `routes/teams.py`
and `routes/events.py`.

WHY THIS EXISTS — `conf_rank` IS WRITE-DEAD, NOT MERELY STALE (#4811).

`tasks/statpal_sync.py:2056` is the only writer of `standings_data` anywhere in
the backend, and since #4732 it emits `div_rank` or `league_rank`:

    rank_field = "div_rank" if team_entry.get("_rank_scope") == "division" else "league_rank"

`conf_rank` survives in that file only inside comments. No code path writes it.
StatPal's board nests teams under `league[].division[]`, so the `position` that
used to be stored as `conf_rank` was always a DIVISION place — printed by every
renderer against the CONFERENCE name.

So a `conf_rank` still sitting in the column is pre-#4732 residue, and every
value it can return is a division position wearing a conference label. It is
wrong on its face — independent of how stale the row is, and independent of the
duplicate-team-identity defect underneath it (D35/#2693, lane1's, not fixed
here). Measured in production 2026-09-11: 137 rows carry standings, 124 have
`div_rank`, 13 have `conf_rank`, and the two sets are disjoint. The standings
feed no longer names those 13, so no future pass corrects them and no dedupe
can either — among them Columbus and Ottawa, two genuinely different clubs,
both claiming Eastern Conference #5.

The fix is applied HERE, at the serving boundary, rather than in the renderers,
because the key reaches readers through four sites and at least five clients
(the team page hero, `RelatedFutures` twice, `lib/types.ts`, the iOS models).
Cutting it once server-side fixes every surface and touches no ux-owned layout
file (notice 41). A hero then prints the team and its conference with no rank —
empty rather than wrong (notice 34).

If a source ever genuinely scopes a rank to a conference, it should write
`conf_rank` again and this tuple is where that is re-enabled — deliberately,
with the renderers checked, not by accident.
"""

# Keys that no writer produces any more and that no client may be shown.
WRITE_DEAD_STANDINGS_KEYS = ("conf_rank",)


def public_standings(standings):
    """Return `standings` without any write-dead key.

    A no-op for the 124 of 137 rows that never carried one: the same object is
    returned, so the common path allocates nothing.

    Never mutates the argument — these dicts are live SQLAlchemy JSONB values,
    and mutating one in place is the silent-write failure of gotcha #4.
    """
    if not isinstance(standings, dict):
        return standings
    if not any(key in standings for key in WRITE_DEAD_STANDINGS_KEYS):
        return standings
    return {k: v for k, v in standings.items() if k not in WRITE_DEAD_STANDINGS_KEYS}
