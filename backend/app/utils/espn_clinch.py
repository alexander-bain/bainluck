"""Reading ESPN's standings as playoff-grid authority (#7663, #7675).

Two readings come off the one standings body, and they are parsed together
because they are one fetch: the ``clincher`` stat as a terminal grid state
(#7663, below) and the ``overall`` stat as the club's season record (#7675,
:func:`season_record`).


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
import re

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
                    # One unparseable count is skipped, not fatal: this sums
                    # four optional stats only to answer "has this team played
                    # yet", and `played <= 0` below is the backstop for an entry
                    # where none of them parse. Narrow on purpose — `TypeError`
                    # and `ValueError` are what a non-numeric `value` raises,
                    # and nothing wider is caught, so this cannot mask a defect
                    # the way a bare `except Exception` would (#7677).
                    pass

        if played <= 0:
            continue
        claim = clinch_claim(description)
        if claim is not None:
            claims[str(team_id)] = claim

    return claims


#: A servable record is digits separated by hyphens and nothing else: ``95-60``
#: (MLB, W-L), ``2-0`` (NFL), ``3-1-1`` (EPL, W-D-L), ``2-0-0`` (NHL, W-L-OTL).
#: Anything else makes no claim rather than printing a string nobody designed
#: for that column.
_RECORD_SHAPE = re.compile(r"^\d+(?:-\d+)+$")


def season_record(display_value) -> str | None:
    """ESPN's ``overall`` display value as a record the grid can print.

    🔴 **THE DISPLAY VALUE IS NOT ALWAYS THE RECORD.** Measured 2026-09-21
    across the five grids, the ``overall`` stat (``type: total``) reads:

    ====== ======================= ==========================================
    league ``overall.displayValue`` note
    ====== ======================= ==========================================
    MLB    ``95-60``               W-L
    NFL    ``2-0``                 W-L
    EPL    ``3-1-1``               W-D-L
    NHL    ``2-0-0, 4 PTS``        **carries a points suffix**
    NBA    ``0-0``                 preseason; no games played
    ====== ======================= ==========================================

    So NHL's value cannot be served raw — the record column would print
    ``2-0-0, 4 PTS``. The suffix is cut at the comma and the remainder must
    match :data:`_RECORD_SHAPE`, which is also what refuses a shape no league
    here has published.

    Deliberately NOT rebuilt from the ``wins``/``losses``/``ties``/``otLosses``
    stats: the ORDER differs per sport (W-L, W-D-L, W-L-OTL) and a per-sport
    composition table would be a fifth place for the league to be wrong. ESPN
    already composed it correctly for its own sport; this only trims it.
    """
    if not isinstance(display_value, str):
        return None
    text = display_value.split(",")[0].strip()
    if not text or not _RECORD_SHAPE.match(text):
        return None
    return text


#: ESPN's abbreviation for a preseason season-type. Measured 2026-09-21: the
#: NAME differs by sport ("Preseason" in the NHL, "Spring Training" in MLB) but
#: the abbreviation is ``pre`` in both, so the abbreviation is the key and the
#: names below are the backstop.
_PRESEASON_ABBREVIATION = "pre"
_PRESEASON_NAMES = ("preseason", "pre-season", "spring training", "exhibition")


def _standings_season_type(payload: dict) -> dict | None:
    """The ``seasons[].types[]`` entry the standings body is reporting under."""
    if not isinstance(payload, dict):
        return None

    season_type = None
    for node in _iter_group_nodes(payload):
        standings = node.get("standings")
        if isinstance(standings, dict) and standings.get("seasonType") is not None:
            season_type = standings.get("seasonType")
            break
    if season_type is None:
        return None

    seasons = payload.get("seasons")
    if not isinstance(seasons, list):
        return None
    for season in seasons:
        if not isinstance(season, dict):
            continue
        for type_entry in season.get("types") or []:
            if isinstance(type_entry, dict) and str(type_entry.get("id")) == str(season_type):
                return type_entry
    return None


def is_preseason_standings(payload: dict) -> bool:
    """Is this standings body reporting a PRESEASON table? (#7675)

    🔴 **THE SEASON-TYPE NUMBER IS NOT A KEY EITHER** — the same trap as the
    clinch letter, one field over. Measured 2026-09-21, the standings node's
    ``seasonType`` read:

    ====== ============ ==================================================
    league ``seasonType`` what ``seasons[].types[]`` resolves it to
    ====== ============ ==================================================
    NHL    ``1``        **Preseason** (``pre``) — games are being played
    NBA    ``1``        **Preseason** (``pre``)
    MLB    ``2``        Regular Season (``reg``)
    NFL    ``2``        Regular Season (``reg``)
    EPL    ``1``        "2026-27 English Premier League" — soccer has ONE
                        type; ``1`` here is the whole season
    ====== ============ ==================================================

    So ``seasonType == 1`` means preseason in the NHL and means the live
    Premier League table in England. A numeric test would either serve NHL
    preseason records or drop the EPL rows this ship exists to fix. The id is
    resolved through the body's own ``types`` table and the NAME is read —
    exactly as :func:`clinch_claim` reads the description.

    This matters because a preseason record is the defect, not the fix: it is
    the same shape as the spring-training ``10-18-1`` in
    ``_get_team_metadata``'s docstring. Without this gate the overlay wrote
    preseason records onto 25 NHL rows on the day it was built.

    **Fails OPEN.** An unresolvable or absent season type returns ``False`` and
    the reading proceeds — losing the authority on a body we merely could not
    label would cost more than the case it guards.
    """
    type_entry = _standings_season_type(payload)
    if not isinstance(type_entry, dict):
        return False

    abbreviation = type_entry.get("abbreviation")
    if isinstance(abbreviation, str) and abbreviation.strip().lower() == _PRESEASON_ABBREVIATION:
        return True

    name = type_entry.get("name")
    if isinstance(name, str):
        lowered = name.strip().lower()
        return any(word in lowered for word in _PRESEASON_NAMES)
    return False


def parse_standings_records(payload: dict) -> dict[str, str]:
    """``{espn_team_id: record}`` from an ESPN v2 standings body (#7675).

    Same body, same id join and same played-games gate as
    :func:`parse_standings_clinch` — see there for why the key is the ESPN id
    as a string and never a name.

    The played-games gate is what keeps a not-yet-started season from
    overwriting a real record with ``0-0``: measured 2026-09-21, 29 of 30 NBA
    clubs sat at ``0-0`` in preseason, and every one of them makes no claim
    here, so the NBA grid is left exactly as it was found.
    """
    records: dict[str, str] = {}
    if not isinstance(payload, dict):
        return records

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

        overall = None
        played = 0
        for stat in stats:
            if not isinstance(stat, dict):
                continue
            name = stat.get("name")
            if name == "overall":
                overall = stat.get("displayValue")
            elif name in ("wins", "losses", "ties", "otLosses"):
                try:
                    played += int(float(stat.get("value") or 0))
                except (TypeError, ValueError):
                    # One unparseable count is skipped, not fatal: this sums
                    # four optional stats only to answer "has this team played
                    # yet", and `played <= 0` below is the backstop for an entry
                    # where none of them parse. Narrow on purpose — `TypeError`
                    # and `ValueError` are what a non-numeric `value` raises,
                    # and nothing wider is caught, so this cannot mask a defect
                    # the way a bare `except Exception` would (#7677).
                    pass

        if played <= 0:
            continue
        record = season_record(overall)
        if record is not None:
            records[str(team_id)] = record

    return records


def apply_record_overlay(rows: list[tuple[str, dict]], records: dict[str, str]) -> int:
    """Serve ESPN's record for each club it names. Returns the count changed.

    ``rows`` is ``(espn_id, team_row)`` pairs; a club with no ESPN id, or one
    ESPN makes no claim about, keeps whatever ``Team.current_record`` gave it.

    D27, and nothing cleverer: the authority's record REPLACES ours rather than
    being consulted only when ours looks wrong. There is no plausibility
    threshold here on purpose — "a record implying more games than the season
    has played" would be a second, weaker way of asking the question the
    authority already answers, and it would need a per-league matchweek the
    grid does not have.

    Measured over all five grids on 2026-09-21, same minute: MLB 30 of 30
    already identical (so the shape is right and nothing churns), NBA untouched
    (preseason, no games played), and 30 rows corrected — the 3 EPL clubs
    serving a COMPLETED PRIOR SEASON in matchweek 5 (Brighton ``14-11-12`` = 37
    games, Bournemouth ``12-16-7``, Tottenham ``10-11-17`` = 38), plus 2 NFL and
    25 NHL rows where our sync simply lagged a game behind.
    """
    written = 0

    for espn_id, team in rows:
        record = records.get(str(espn_id)) if espn_id else None
        if record is None:
            continue
        if team.get("record") == record:
            continue
        team["record"] = record
        written += 1

    return written


def _iter_group_nodes(node: dict):
    """Every group node in the tree, this one first, then its descendants.

    The sibling of :func:`_iter_entries`: that one yields the leaf entries, this
    one yields the nodes that CARRY them, which is where ``seasonType`` lives.
    """
    if not isinstance(node, dict):
        return
    yield node
    children = node.get("children")
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                yield from _iter_group_nodes(child)


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
