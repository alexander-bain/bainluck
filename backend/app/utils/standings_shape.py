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

# Keys that hold a real, correctly-labelled rank — and are still unsupported
# before a team has played. See `standings_show_no_games_played`.
RANK_KEYS_NEEDING_A_PLAYED_GAME = ("div_rank", "league_rank")


def standings_show_no_games_played(standings) -> bool:
    """True only when this row PROVES the team has played nothing.

    #5377. Measured on production 2026-09-11, the morning before NFL week 1:
    30 of 32 teams were 0-0 and ALL 30 carried a `div_rank` 1-4, so the AFC
    South's four identical 0-0 records were served as Titans #1, Colts #2,
    Jaguars #3, Texans #4 — an order nothing that happened on a field produced.
    The two teams with an earned rank were the two who had played Thursday
    (NE 0-1, SEA 1-0).

    PROVES is the whole contract. Returns False whenever the record cannot be
    read, so an unmeasurable row keeps whatever the caller would have shown
    anyway — this suppresses the case we can demonstrate, never one we merely
    failed to measure. The three ways a row fails to prove it: a missing
    `wins`/`losses` key, a value that will not coerce to an int, or any
    non-zero win/loss/draw/tie.
    """
    if not isinstance(standings, dict):
        return False
    wins, losses = standings.get("wins"), standings.get("losses")
    if wins is None or losses is None:
        return False
    try:
        if int(wins) or int(losses):
            return False
        # A draw is a game played even though it moves neither W nor L, so a
        # 0-0-1 soccer side is NOT fresh. Both spellings are checked because
        # the writer stores whichever the venue used.
        for key in ("draws", "ties"):
            value = standings.get(key)
            if value is not None and int(value):
                return False
    except (TypeError, ValueError):
        return False
    return True


def _dropped_keys(standings) -> tuple:
    """Every key `public_standings` must withhold from this row."""
    dropped = tuple(WRITE_DEAD_STANDINGS_KEYS)
    # #5377. A rank is dropped for its CONTENT, not its name — the same key is
    # served untouched the moment the team has played once. That is the
    # difference from `conf_rank`, which is wrong on every row forever.
    if standings_show_no_games_played(standings):
        dropped += RANK_KEYS_NEEDING_A_PLAYED_GAME
    return dropped


def record_text(current_record, standings):
    """Return the W-L(-D) string a reader should be shown, or None.

    TWO COLUMNS ANSWER THIS QUESTION AND THEY DISAGREE (#5520).
    `teams.current_record` is stamped when a game completes; `standings_data`'s
    `wins`/`losses` come from the once-daily StatPal board.

    `current_record` IS NOT SIMPLY THE FRESHER ONE — that premise is true in
    MLB and false in two other leagues, so the preference is CONDITIONED rather
    than blanket. Measured across all 137 rows carrying both columns,
    production 2026-09-19 03:45Z:

      * **MLB, in season.** One `standings_updated_at` for all 30 rows
        (2026-09-18 08:00:00Z, 19.7h old); 25 of 30 disagreed and
        `current_record` led in 25 of 25 — never behind, never a different
        split at the same game count. A lag is monotone like that. This is the
        case the fix exists for: the hero served "Dodgers 92-60" off a row
        whose `current_record` said 93-60.
      * **NHL, between seasons.** The board has ROLLED OVER to 0-0 while
        `current_record` still holds last season's finished 82 games
        (Anaheim `43-33-6` against a snapshot of `0-0`). Preferring
        `current_record` here would print a completed season for a league that
        has played no games — #6266's defect, on the hero.
      * **NBA, after the season.** The direction REVERSES: `current_record`
        is the stale one (Brooklyn `18-59`, 77 games, against a complete
        `20-62`). Twelve rows are behind like this.

    So `current_record` wins only where it can be shown to be the same season
    and further along: the snapshot must show a played game (else it is a
    rollover), and `current_record` must not have FEWER games than the snapshot
    (else it is the stale half). Simulated over those 137 rows the rule moves
    29 — the 25 MLB rows, 4 NHL residue rows — and leaves NFL and NBA at zero.

    The RANK is deliberately not this function's business and its vintage does
    not change: callers keep reading it from `public_standings(standings)`, so
    the #5377 no-games-played guard still fires on the same input it always
    did. Taking the fresher record alongside it is strictly less wrong than
    printing a stale record next to that same rank.

    A record is only returned when it can be demonstrated — an unparseable
    `current_record` falls through to the snapshot rather than printing
    whatever string the column happens to hold (notice 34: empty beats wrong).
    """
    snapshot = _snapshot_record(standings)
    parsed = _parse_record(current_record)
    if parsed is None:
        return snapshot
    if snapshot is None:
        return parsed
    # A rollover, not a lag: the board has started a new season and
    # `current_record` is still describing the last one.
    if standings_show_no_games_played(standings):
        return snapshot
    # `current_record` is behind the board rather than ahead of it, so it is
    # the stale half here and the snapshot is the better answer.
    snapshot_games = _count_games(snapshot)
    current_games = _count_games(parsed)
    if snapshot_games is not None and current_games is not None:
        if current_games < snapshot_games:
            return snapshot
    return parsed


def _snapshot_record(standings):
    """The W-L(-D) string `standings_data` alone would have produced."""
    if not isinstance(standings, dict):
        return None
    if "wins" not in standings or "losses" not in standings:
        return None
    record = f"{standings['wins']}-{standings['losses']}"
    draws = standings.get("draws") or standings.get("ties")
    if draws:
        record += f"-{draws}"
    return record


def _count_games(record):
    """Games represented by a W-L(-D) string, or None if it is not one."""
    parsed = _parse_record(record)
    if parsed is None:
        return None
    return sum(int(part) for part in parsed.split("-"))


def _parse_record(current_record):
    """`current_record` echoed back only if it is 2-3 hyphen-joined integers."""
    if not isinstance(current_record, str):
        return None
    parts = current_record.strip().split("-")
    if len(parts) not in (2, 3):
        return None
    for part in parts:
        if not part.isdigit():
            return None
    return "-".join(parts)


def public_standings(standings):
    """Return `standings` without any key this row may not be shown by.

    A no-op for the rows that carry none of them: the same object is returned,
    so the common path allocates nothing.

    Never mutates the argument — these dicts are live SQLAlchemy JSONB values,
    and mutating one in place is the silent-write failure of gotcha #4.
    """
    if not isinstance(standings, dict):
        return standings
    dropped = _dropped_keys(standings)
    if not any(key in standings for key in dropped):
        return standings
    return {k: v for k, v in standings.items() if k not in dropped}
