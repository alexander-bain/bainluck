"""Pure logic for championship grid building.

Extracted from routes/playoffs.py `get_playoff_grid` (862 lines)
to make grid logic independently testable.
"""

import logging
import re

logger = logging.getLogger(__name__)

EXPECTED_COLUMN_SUMS = {
    "championship": 1.0,
    "conference": 2.0,
    "pennant": 2.0,
}


def monotonic_pairs(columns: list) -> list[tuple[str, str]]:
    """``(bound_key, column_key)`` for every sequential column that has a bound.

    A grid column is bounded by the column a team must ALREADY have come
    through to reach it. That is usually the column before it, which is why
    this used to be implicit — but it is not always, and where it is not, the
    implicit reading is a lie that overwrites real market prices (#7076).

    A column may therefore name its own prerequisite with ``depends_on``. In the
    four leagues that carry a ``division`` column the conference/pennant cell
    declares ``depends_on="make_playoffs"``: a wild card wins the pennant
    without winning its division, so "P(pennant) <= P(division)" is false, and
    enforcing it flattened Boston's pennant and World Series cells onto their
    division blend.

    A ``depends_on`` that does not name an EARLIER sequential column cannot be
    honoured, so it degrades to the previous column — the historical behaviour,
    never something new. That degradation is silent by design (a grid page must
    not 500 over a config typo) and is therefore not the protection: the guard
    test over every LEAGUE_CONFIGS entry is.
    """
    seq_cols = sorted(
        [c for c in columns if (c.sequential if hasattr(c, "sequential") else True)],
        key=lambda c: c.order if hasattr(c, "order") else 0,
    )
    seq_keys = [c.key if hasattr(c, "key") else c for c in seq_cols]

    pairs: list[tuple[str, str]] = []
    for i in range(1, len(seq_keys)):
        declared = getattr(seq_cols[i], "depends_on", None)
        bound = declared if declared in seq_keys[:i] else seq_keys[i - 1]
        if declared is not None and bound != declared:
            logger.warning(
                "Grid column %s declares depends_on=%r, which is not an earlier "
                "sequential column; bounding it by %s instead",
                seq_keys[i], declared, bound,
            )
        pairs.append((bound, seq_keys[i]))
    return pairs


def enforce_monotonicity(teams: list[dict], columns: list) -> int:
    """Enforce monotonicity across sequential grid columns for every team.

    Each sequential column is capped at the column that bounds it — the
    previous one by default, or whatever ``depends_on`` names
    (`monotonic_pairs`).  If Conference > Make Playoffs, cap Conference at Make
    Playoffs.

    This function is idempotent and should be called:
      1. During initial cell building (per-team, before normalization)
      2. After normalize_column_sums (which can inflate columns and break
         monotonicity that was previously enforced)

    Returns the number of violations corrected.
    """
    pairs = monotonic_pairs(columns)

    if not pairs:
        return 0

    violations_fixed = 0
    for team in teams:
        cells = team.get("cells", {})
        for prev_key, curr_key in pairs:
            prev_cell = cells.get(prev_key)
            curr_cell = cells.get(curr_key)
            if prev_cell and curr_cell:
                prev_p = prev_cell.get("merged_probability")
                curr_p = curr_cell.get("merged_probability")
                # Register-backed grids carry settled/missing cells that have no
                # probability at all. They are terminal states, not numbers to
                # compare, so monotonicity simply does not apply to them.
                if prev_p is None or curr_p is None:
                    continue
                if curr_p > prev_p:
                    curr_cell["merged_probability"] = prev_p
                    # Also cap individual source probabilities
                    for src in curr_cell.get("sources", []):
                        if src["probability"] > prev_p:
                            src["probability"] = round(prev_p, 4)
                    violations_fixed += 1
                    logger.debug(
                        "Monotonicity fix: %s %s %.4f > %s %.4f -> capped to %.4f",
                        team.get("name", "?"), curr_key, curr_p,
                        prev_key, prev_p, prev_p,
                    )
    return violations_fixed


def column_scale_factor(col_sum: float, expected: float) -> float:
    """The factor :func:`normalize_column_sums` applies to a column — or 1.0.

    #7458. This is the WHOLE normalization policy as one pure function, because
    the grid's table is not the only surface that publishes these numbers: the
    trend chart beside it draws the same column and must arrive at the same
    quantity. It used to reimplement nothing at all — it simply skipped this
    stage — so EPL published Arsenal at 0.4750 in the legend and 0.4167 in the
    table on one screen, a constant x1.140 apart, which is exactly this
    function's factor for a column summing to 1.1388.

    Sharing the policy rather than the arithmetic is the point. A second copy of
    ``expected / col_sum`` would agree today and drift the first time a
    threshold moves.

    The dead band is deliberate and load-bearing: a column between 0.85 and 1.05
    of expected is left ALONE, so a grid whose sources already agree is never
    nudged. So is the 2.5x ceiling — a column that far over is a matching bug
    (one team's outcome counted twice, a mis-classified market), and scaling it
    would hide the defect behind a plausible-looking distribution instead of
    leaving it visible.
    """
    if not expected or col_sum <= 0:
        return 1.0
    if col_sum > expected * 2.5:
        # Likely a matching bug — the caller warns; never quietly rescale it.
        return 1.0
    if col_sum > expected * 1.05 or col_sum < expected * 0.85:
        return expected / col_sum
    return 1.0


#: Cell states that record a VENUE SETTLEMENT rather than a price. Mirrors
#: ``routes/playoffs._GRID_DECIDED_STATES``; duplicated rather than imported so
#: this module keeps importing nothing of the app.
DECIDED_STATES = frozenset({"won", "eliminated", "lost"})

#: The decided states that END a team's run. Every stage downstream of one is
#: unreachable, whatever a market still quotes for it.
OUT_STATES = frozenset({"eliminated", "lost"})


def propagate_elimination(teams: list[dict], columns: list) -> int:
    """A team that is OUT at one stage is out of every stage that needs it.

    `enforce_monotonicity` bounds a stage by the stage a team must already have
    come through — but only as a NUMBER, and a settled cell carries no number,
    so the bound silently does not apply to it. That left the MLB grid saying
    both things in one row: on 2026-09-20 the Pirates, Cardinals and Marlins
    were ✗ for Make Playoffs and Division (venue-settled — all three are
    mathematically out with six games left) and, in the same row, priced at
    0.5% for the pennant and 0.1% for the World Series, off an illiquid ask on
    a champion market that had not dropped them.

    Elimination runs down the same ``depends_on`` ladder that bounds the
    prices: you cannot win the pennant without making the playoffs. A dependent
    cell is rewritten only when it is not ITSELF settled — a venue grade
    outranks this inference, the same way "settled outranks trading" governs
    one step earlier.

    Idempotent. Call after `enforce_monotonicity`: `monotonic_pairs` returns
    pairs in dependent-column order and a bound is always an earlier column, so
    one forward pass carries an elimination the whole length of the ladder.

    Returns the number of cells rewritten.
    """
    pairs = monotonic_pairs(columns)
    if not pairs:
        return 0

    rewritten = 0
    for team in teams:
        cells = team.get("cells") or {}
        for bound_key, col_key in pairs:
            bound_cell = cells.get(bound_key)
            cell = cells.get(col_key)
            if not bound_cell or not cell:
                continue
            if bound_cell.get("state") not in OUT_STATES:
                continue
            if cell.get("state") in DECIDED_STATES:
                continue
            logger.info(
                "Grid elimination: %s is %s at %s, so %s (%s) is unreachable",
                team.get("name", "?"), bound_cell.get("state"), bound_key,
                col_key, cell.get("merged_probability"),
            )
            cell["merged_probability"] = None
            cell["sources"] = []
            cell["trend_24h"] = None
            cell["state"] = "eliminated"
            rewritten += 1
    return rewritten


def propagate_division_complement(
    teams: list[dict], columns: list, division_key: str = "division",
) -> int:
    """One club won the division, so its rivals did not. Returns cells rewritten.

    `propagate_elimination` runs the VERTICAL ladder — a club out at one stage is
    out of every stage behind it, within its own row. This is the HORIZONTAL one,
    across the cohort, and until #7695 nothing computed it: on 2026-09-21 the MLB
    grid said Atlanta had won the NL East and, three rows down, priced
    Philadelphia at 1.0% to win the NL East. Both statements on one screen.

    Philadelphia was the single row where neither authority spoke. ESPN marks
    only the club that clinched — it publishes nothing about that club's rivals,
    and Philadelphia legitimately carries no `clincher` because it is still alive
    for a wild card. Every other NL East club already read eliminated because the
    venue had graded its division leg. So the gap is narrow and it is ours.

    A division is a CLOSED COHORT WITH EXACTLY ONE WINNER, so the complement is
    arithmetic, not inference — the same standing that makes the elimination
    ladder safe. Three things keep it that way:

    * **This column only.** `make_playoffs` is not a one-winner cohort
      (Philadelphia is ~99% to make the playoffs, and that is true), and neither
      is a wild card. Writing a complement into a multi-winner column would
      manufacture exactly the false settled claim the clinch overlay exists to
      prevent.
    * **The cohort key is (conference, division), and an unplaced club is
      skipped.** Pooling on the division LABEL alone puts the AL East and the NL
      East in one bucket and eliminates five clubs on another league's clinch.
      A club missing either half cannot be pooled at all, so it is left alone —
      this fails closed, and a league with divisions but no conferences gets no
      complement rather than a wrong one.
    * **A venue grade is never overwritten**, same order as
      `apply_clinch_overlay` and `propagate_elimination`.

    Two winners in one cohort is a contradiction this must not resolve: picking
    one would eliminate a club that a venue or ESPN says has won. It is logged
    and the cohort is left exactly as it stands.

    Idempotent: a second pass finds the same lone winner and every rival already
    decided. Call it beside the clinch overlay, before normalization, so the
    column is summed over what is actually live.
    """
    keys = {c.key if hasattr(c, "key") else c for c in (columns or [])}
    if division_key not in keys:
        return 0

    cohorts: dict[tuple, list[dict]] = {}
    for team in teams:
        conference = team.get("conference")
        division = team.get("division")
        if not conference or not division:
            continue
        cohorts.setdefault((conference, division), []).append(team)

    rewritten = 0
    for (conference, division), cohort in cohorts.items():
        winners = [
            team for team in cohort
            if ((team.get("cells") or {}).get(division_key) or {}).get("state") == "won"
        ]
        if len(winners) != 1:
            if len(winners) > 1:
                logger.warning(
                    "Grid division complement: %s %s has %d clubs marked won "
                    "(%s) — leaving the cohort alone",
                    conference, division, len(winners),
                    ", ".join(t.get("name", "?") for t in winners),
                )
            continue

        winner = winners[0]
        # The winner needs no special case: its own cell reads `won`, so the
        # decided-state guard below leaves it exactly where it is. A separate
        # identity check here would be a branch no specimen can ever reach.
        for team in cohort:
            cell = (team.get("cells") or {}).get(division_key)
            if cell is None:
                # Absent is not eliminated (#6442). A club this column never
                # priced gets no cell invented for it.
                continue
            if cell.get("state") in DECIDED_STATES:
                continue
            logger.info(
                "Grid division complement: %s won the %s %s, so %s (%s) cannot",
                winner.get("name", "?"), conference, division,
                team.get("name", "?"), cell.get("merged_probability"),
            )
            cell["merged_probability"] = None
            cell["sources"] = []
            cell["trend_24h"] = None
            cell["state"] = "eliminated"
            rewritten += 1
    return rewritten


def normalize_column_sums(
    teams: list[dict],
    columns: list,
    league_slug: str,
) -> dict[str, float]:
    """Normalize championship/conference column probabilities to expected sums.

    When raw probabilities undershoot by >15% (common with prediction market
    data where long-tail teams floor at 0.1%), scales all values proportionally.

    Modifies teams in-place, and RETURNS the factor actually applied to each
    column (#7458) so the trend chart can publish the same quantity this leaves
    in the table. Columns left alone are absent from the mapping rather than
    present as 1.0, so a caller can tell "policy said don't touch it" from
    "policy is not defined for this column" — the trend chart treats both as
    1.0, but a future consumer should not have to guess.
    """
    applied: dict[str, float] = {}
    for col in columns:
        col_key = col.key if hasattr(col, "key") else col.get("key", "")
        expected = EXPECTED_COLUMN_SUMS.get(col_key)
        if not expected:
            continue
        # Settled/missing cells (register-backed grids) contribute no
        # probability — normalizing against them would scale the live cells by a
        # denominator that never included them.
        col_sum = sum(
            p for p in (
                t["cells"].get(col_key, {}).get("merged_probability")
                for t in teams
            ) if p is not None
        )
        if col_sum > expected * 2.5:
            logger.warning(
                "Column %s sum=%.1f%% exceeds 2.5x expected %.0f%% for %s — likely a matching bug",
                col_key, col_sum * 100, expected * 100, league_slug,
            )

        scale = column_scale_factor(col_sum, expected)
        if scale != 1.0:
            applied[col_key] = scale
            logger.info(
                "Normalizing %s column from %.1f%% to %.0f%% (x%.2f) for %s%s",
                col_key, col_sum * 100, expected * 100, scale, league_slug,
                " (overshoot)" if col_sum > expected else "",
            )
            for t in teams:
                cell = t["cells"].get(col_key)
                if cell and cell.get("merged_probability") is not None:
                    cell["merged_probability"] = round(cell["merged_probability"] * scale, 4)
                    for src in cell.get("sources", []):
                        src["probability"] = round(src["probability"] * scale, 4)

        # After any normalization, cap individual cells at 100%.
        # Column-sum normalization can push a dominant team above 1.0 when
        # scaling up from an undershoot (e.g., OKC at 69% conference win
        # scaled by 1.5x → 103%). Cap merged_probability and source
        # probabilities to prevent impossible >100% display values.
        for t in teams:
            cell = t["cells"].get(col_key)
            if cell and cell.get("merged_probability") is not None:
                if cell["merged_probability"] > 1.0:
                    cell["merged_probability"] = 1.0
                for src in cell.get("sources", []):
                    if src["probability"] > 1.0:
                        src["probability"] = 1.0

    return applied


# Below half a percentage point a 24h change is not a move a reader can act on,
# and every client already discards it: the web ribbon and the /playoffs section
# both floor at 0.005, iOS at 0.001. Publishing it anyway padded the list out to
# `limit` with teams that had not moved, which is what `limit` is for the top of
# — not a quota to fill. Two consequences, both reader-visible (#7742):
# a change of exactly 0.0 was stamped `direction: "down"`, and the league page
# sizes its chrome on the UNFILTERED length, so `earnsMoversStrip` saw ten and
# printed a "BIGGEST MOVERS (24H)" header over the one or two chips that
# survived the client floor — precisely what CHROME_MOVERS_MIN = 3 exists to
# prevent. The floor belongs with the producer so all three clients agree.
MOVER_FLOOR_24H = 0.005  # 0.5 percentage points


def compute_movers(
    teams: list[dict],
    championship_col: str,
    limit: int = 10,
) -> list[dict]:
    """Compute biggest 24h movers in the championship column.

    Only teams whose championship probability actually moved — by at least
    ``MOVER_FLOOR_24H`` in either direction — are returned. A team that did not
    move is not a mover, so the list is as long as the truth allows and never
    padded to ``limit``; callers may therefore size chrome on ``len()``.

    Returns list of mover dicts sorted by absolute change, descending.
    """
    movers = []
    for team_row in teams:
        champ_cell = team_row["cells"].get(championship_col)
        if not champ_cell:
            continue
        change = champ_cell.get("trend_24h")
        if change is None or abs(change) < MOVER_FLOOR_24H:
            continue
        movers.append({
            "name": team_row["name"],
            "short_name": team_row["short_name"],
            "team_id": team_row["team_id"],
            "column": championship_col,
            "change_24h": change,
            "direction": "up" if change > 0 else "down",
            "logo_url": team_row.get("logo_url"),
            "primary_color": team_row.get("primary_color"),
        })

    movers.sort(key=lambda m: abs(m["change_24h"]), reverse=True)
    return movers[:limit]


# Sort weights for cells that carry no probability. "Eliminated" is a DECIDED
# zero. A row with no cell at all for this column has not been decided by
# anyone — nobody priced it — and it is not the same fact, so it sorts below.
_SORT_WON = 1.0
_SORT_ELIMINATED = 0.0
_SORT_NO_CELL = -1.0


def _championship_sort_value(team: dict, championship_col: str) -> float:
    """Sort weight for a team's championship cell.

    Live cells sort by probability. A settled cell has no probability, so it
    sorts by its terminal result: a confirmed champion belongs at the top, an
    eliminated team at the bottom — the same place its 100%/0% would have put it.

    A row with NO cell for this column is not a result at all and sorts below
    both. #7754: an unresolvable venue name ("Oakland Athletics", which our
    `Athletics` row does not match) minted a 31st row on a 30-seat MLB grid
    carrying only a division cell. It fell through to the same ``0.0`` as the
    thirteen clubs whose championship cell says `eliminated`, and ``list.sort``
    is stable, so position inside that tied block was ARRIVAL ORDER. The
    phantom landed at rank 24 and the Cincinnati Reds — a real club — were cut
    by the cap. Measured on all six live grids the day this shipped, no
    published row lacks a championship cell, so this reaches nothing else.
    """
    cell = team["cells"].get(championship_col)
    if not cell:
        return _SORT_NO_CELL
    prob = cell.get("merged_probability")
    if prob is not None:
        return float(prob)
    return _SORT_WON if cell.get("state") == "won" else _SORT_ELIMINATED


def sort_teams_by_championship(
    teams: list[dict],
    championship_col: str,
    max_teams: int,
) -> list[dict]:
    """Sort teams by championship probability (descending) and cap to max.

    Ties break toward the row that resolved to a real club, so the cap never
    spends its last seat on a row we could not identify while cutting an
    equally-ranked club we could. That is a TIE-BREAK, deliberately not a
    blanket preference for a non-null ``team_id``: measured on production
    2026-09-21, wncaab carries three rows with a null ``team_id`` that are real
    tournament schools our name matching missed (`Ohio St.`, `North Carolina
    St.`, `Iowa St.`) and mls carries `New York RB`. All four hold a real
    championship price. Dropping them for a lower-priced club would be this
    same defect pointed the other way, so a row that outranks on a real price
    keeps its seat whether or not we could name it.

    Rows that tie on BOTH of those terms break on name, so the order is one
    fixed sequence rather than whatever order the rows happened to arrive in
    (#8209). This is not cosmetic: measured on production 2026-09-23,
    ``ncaa-basketball`` serves 23 of its 68 rows at an identical
    ``championship`` of 0.0005, and ``max_teams`` is 68 — so the cap cuts
    THROUGH the tie. With no third term, 75 of the 78 order inversions seen
    across a 2.5 h gap were between rows whose prices were byte-identical and
    equal to each other, and three schools silently left the grid while three
    others joined it, every displayed percentage unchanged. Three consecutive
    rebuilds seconds apart agreed exactly, so this was never per-request
    randomness: it is a comparator with no tiebreak over an input order that
    is not pinned.

    Name is the third term rather than ``team_id`` because it is total — a row
    that reached the grid always has one, while ``team_id`` is null on real
    schools our name matching missed (see above). It makes the cut at the cap
    DETERMINISTIC, not fair: which of 23 equally-priced longshots hold the last
    seats is still arbitrary, and that is the separate product question.

    The cap is the last thing that can silently lose a club, so it says so.
    """
    teams.sort(
        key=lambda t: (
            -_championship_sort_value(t, championship_col),
            t.get("team_id") is None,
            t.get("name") or "",
        )
    )
    if len(teams) <= max_teams:
        return teams

    kept = teams[:max_teams]
    dropped = teams[max_teams:]
    logger.info(
        "Grid cap on %s: %d candidates for %d seats, dropped %d "
        "(%d identified clubs dropped, %d unidentified rows kept a seat): %s",
        championship_col,
        len(teams),
        max_teams,
        len(dropped),
        sum(1 for t in dropped if t.get("team_id") is not None),
        sum(1 for t in kept if t.get("team_id") is None),
        ", ".join(t.get("name", "?") for t in dropped[:10]),
    )
    return kept


# Regex for outcomes that are NOT team names (thresholds, dates, generic text)
_NON_TEAM_OUTCOME_RE = re.compile(
    r"""
    ^\d                |   # Starts with digit: "#1 seed", "1+ wins"
    \bover\b           |   # Over/Under
    \bunder\b          |
    \byes\b            |
    \bno\b             |
    \btotal\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_valid_grid_outcome(
    outcome_name: str,
    probability: float,
    source: str,
    has_real_bid: bool,
    sport_category: str | None = None,
    country_names: set[str] | None = None,
) -> bool:
    """Check if an outcome should be included in the grid.

    Filters out: non-team names, generic yes/no, matchup pairs,
    country names in club competitions, and prediction market noise.
    """
    name = outcome_name.strip()

    if not name:
        return False
    if probability <= 0 or probability >= 1.0:
        return False
    if name.lower() in ("yes", "no", "over", "under"):
        return False
    if re.match(r"^#?\d+", name):
        return False

    # Matchup pairs like "Tampa Bay and Colorado"
    if re.search(r"\band\b", name, re.IGNORECASE):
        if not re.search(r"\bTrail\s+Blazers\b", name, re.IGNORECASE):
            if re.match(r"^[\w\s.]+ and [\w\s.]+$", name):
                return False

    # Country names in club competitions
    if sport_category == "soccer" and country_names and name in country_names:
        return False

    # Prediction market noise (near-50% with no real bid activity)
    if source in ("kalshi", "polymarket") and abs(probability - 0.5) < 0.02:
        if not has_real_bid:
            return False

    return True
