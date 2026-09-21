"""Reading ESPN's ``clincher`` standings stat as a playoff-grid state (#7663).

ESPN publishes, per team per season, a ``clincher`` stat saying whether the club
has clinched something or been eliminated. That is the AUTHORITY on a question
the grid currently answers from prices alone, which is D27's whole subject:
authority outranks inference.

🔴 **THE LETTER IS NOT A KEY, AND NEITHER IS THE NUMBER.** Measured against ESPN
on 2026-09-21 across four leagues:

===== ============================ ==================== ========================
code   MLB 2026                     NFL 2025             NBA 2025 / NHL 2025
===== ============================ ==================== ========================
``x``  Clinched **Division**        --                   Clinched **Playoff Berth**
``y``  --                           Clinched Wild Card   Clinched Division (Title)
``z``  Clinched **Playoff Berth**   Clinched **Division**  Clinched Conference
``e``  Eliminated (``value=4.0``)   Eliminated (``0.0``) Eliminated (``4.0``/``5.0``)
===== ============================ ==================== ========================

So a letter map is wrong on MLB and NFL *simultaneously* — ``x`` is a division in
MLB and a berth in the two winter leagues, ``z`` is a berth in MLB and a division
in the NFL. The numeric ``value`` is worse than useless: "Eliminated" is ``0.0``
in the NFL, so ``if stat["value"]:`` reads NFL elimination as absent while
working everywhere else.

The ``description`` is the only field that carries the meaning, so it is the only
field this module reads.

This module imports nothing of the app: it is the pure half, so the cross-sport
table above is testable without a network or a database.
"""

import logging

logger = logging.getLogger(__name__)

#: A club is out of the playoffs. Every league observed spells this with the
#: word "eliminated" ("Eliminated from Playoff Contention", NBA's "Eliminated
#: From Playoff"), and no non-elimination description contains it.
CLINCH_OUT = "out"

#: A club has secured a playoff berth, by any route, without this module
#: claiming to know which one.
CLINCH_BERTH = "berth"

#: A club has won its division — which also secures a berth in every league that
#: publishes the phrase, so :func:`clinch_claim` returning this implies
#: :data:`CLINCH_BERTH` as well.
CLINCH_DIVISION = "division"

#: Mirrors ``playoff_grid.DECIDED_STATES`` / ``routes/playoffs.
#: _GRID_DECIDED_STATES``. Duplicated for the same stated reason they are:
#: this module imports nothing of the app.
DECIDED_STATES = frozenset({"won", "eliminated", "lost"})

#: Descriptions that say "clinched" and do NOT mean a playoff berth.
#:
#: NBA publishes ``pb`` / "Clinched Play-in Berth", and a play-in berth is not a
#: playoff berth — the club plays one game and can still miss. Matching
#: ``"clinched"`` alone would print a clinch badge for a team that is not in.
#: Its sibling ``xp`` / "Clinched Playoff - Won Play-In" HAS won through and is
#: deliberately not caught by this, which is why the phrase is "play-in berth"
#: and not "play-in".
_NOT_A_BERTH = ("play-in berth", "play in berth")


def clinch_claim(description) -> str | None:
    """What ESPN's ``clincher`` description states, or ``None`` for "nothing".

    ``None`` means *this module makes no claim* — an unrecognised, empty or
    non-string description leaves the grid exactly as it found it. That is the
    safe direction for an affirmative state claim and the reason the
    unrecognised case is not logged as an error: ESPN adding a new code must
    never be able to blank or badge a cell.

    Returns one of :data:`CLINCH_OUT`, :data:`CLINCH_DIVISION`,
    :data:`CLINCH_BERTH`, or ``None``.
    """
    if not isinstance(description, str):
        return None
    text = description.strip().lower()
    if not text:
        return None

    # Elimination first: no observed description says both.
    if "eliminated" in text:
        return CLINCH_OUT

    if "clinched" not in text:
        return None
    if any(phrase in text for phrase in _NOT_A_BERTH):
        return None

    # "Clinched Division", "Clinched Division Title", "Clinched Division and
    # Bye". Winning a division secures a berth everywhere it is published, so
    # the caller reads this as the berth claim plus the division one.
    if "division" in text:
        return CLINCH_DIVISION

    # "Clinched Playoff Berth", "Clinched Wild Card", "Clinched Conference",
    # "Clinched Best Record in Conference", "Clinched Presidents' Trophy",
    # "Clinched Playoff - Won Play-In". Each is a berth; which one it is beyond
    # that is not a distinction the grid's Make Playoffs column can render.
    return CLINCH_BERTH


def parse_standings_clinch(payload: dict) -> dict[str, str]:
    """``{espn_team_id: claim}`` from an ESPN v2 standings body.

    Keyed on the ESPN team id as a STRING, to join ``Team.espn_id`` — never on a
    name. Measured 2026-09-21: 30 of 30 MLB clubs join on the id, and the one
    club whose name differs is ``St.Louis Cardinals`` (ours) against
    ``St. Louis Cardinals`` (ESPN) — an ELIMINATED club, so a name join would
    have silently dropped exactly the row this ship exists to correct.

    Entries with no games played are skipped. ESPN's season-less standings URL
    already labels its body ``season.year: 2027`` while serving 2026's table, so
    the body cannot be trusted to say which season it is; a table that has been
    played is the check that a claim is about a season in progress. A
    not-yet-started season carries no ``clincher`` anyway, which makes this a
    second lock on a door that is already shut rather than the only one.
    """
    claims: dict[str, str] = {}
    if not isinstance(payload, dict):
        return claims

    for entry in _iter_entries(payload):
        team = entry.get("team")
        if not isinstance(team, dict):
            continue
        team_id = team.get("id")
        if team_id is None:
            continue

        stats = entry.get("stats")
        if not isinstance(stats, list):
            continue

        description = None
        played = 0
        for stat in stats:
            if not isinstance(stat, dict):
                continue
            name = stat.get("name")
            if name == "clincher":
                description = stat.get("description")
            elif name in ("wins", "losses", "ties", "otLosses"):
                try:
                    played += int(float(stat.get("value") or 0))
                except (TypeError, ValueError):
                    pass

        if played <= 0:
            continue
        claim = clinch_claim(description)
        if claim is not None:
            claims[str(team_id)] = claim

    return claims


def _iter_entries(node: dict):
    """Every standings entry in ESPN's nested group tree.

    Groups nest arbitrarily (league -> conference -> division) and a node may
    carry both ``children`` and its own ``standings``, so both are walked.
    """
    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                yield from _iter_entries(child)

    standings = node.get("standings")
    if isinstance(standings, dict):
        entries = standings.get("entries")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    yield entry


def apply_clinch_overlay(
    rows: list[tuple[str, dict]],
    claims: dict[str, str],
    column_keys,
    playoffs_key: str = "make_playoffs",
    division_key: str = "division",
) -> int:
    """Write ESPN's clinch/elimination states onto grid cells. Returns the count.

    ``rows`` is ``(espn_id, team_row)`` pairs; a row whose club has no ESPN id,
    or no claim, is untouched.

    **A venue grade is never overwritten.** A settled market leg is a reading of
    an actual result and outranks a standings badge, the same order
    ``propagate_elimination`` uses one step later ("a venue grade outranks an
    inference"). Where the two disagree the existing cell stands and the
    disagreement is logged rather than resolved here — silently preferring
    either one would make the conflict unfindable.

    Only the two columns ESPN's ``clincher`` actually speaks to are written.
    Elimination is NOT cascaded here: ``propagate_elimination`` already runs the
    ``depends_on`` ladder over the whole grid after normalization, so writing
    Make Playoffs is enough to reach the pennant and championship cells, and
    doing it twice in two places is how the two would drift.
    """
    keys = {c.key if hasattr(c, "key") else c for c in (column_keys or [])}
    written = 0

    for espn_id, team in rows:
        claim = claims.get(str(espn_id)) if espn_id else None
        if claim is None:
            continue
        cells = team.get("cells")
        if not isinstance(cells, dict):
            continue

        targets = []
        if playoffs_key in keys:
            targets.append((playoffs_key, "eliminated" if claim == CLINCH_OUT else "won"))
        if claim == CLINCH_DIVISION and division_key in keys:
            targets.append((division_key, "won"))
        elif claim == CLINCH_OUT and division_key in keys:
            targets.append((division_key, "eliminated"))

        for col_key, state in targets:
            cell = cells.get(col_key)
            if cell is None:
                # Absent is not eliminated (#6442) and it is not clinched
                # either. A club ESPN knows about but this column never priced
                # gets no cell invented for it.
                continue
            existing = cell.get("state")
            if existing in DECIDED_STATES:
                if existing != state:
                    logger.warning(
                        "Grid clinch conflict: ESPN says %s is %s at %s, the "
                        "venue graded it %s — keeping the venue grade",
                        team.get("name", "?"), state, col_key, existing,
                    )
                continue
            logger.info(
                "Grid clinch: ESPN says %s is %s at %s (was %s)",
                team.get("name", "?"), state, col_key,
                cell.get("merged_probability"),
            )
            cell["merged_probability"] = None
            cell["sources"] = []
            cell["trend_24h"] = None
            cell["state"] = state
            written += 1

    return written
