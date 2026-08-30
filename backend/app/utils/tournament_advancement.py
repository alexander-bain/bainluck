"""Each player's chance of reaching each later round — in the shape the grid already speaks.

═══ ALEX'S QUESTION, AND THE ANSWER ═══

Alex, 2026-08-28: *"During an MLB game, don't we show the odds of each team
advancing to each stage of the playoff grid?"*

**Yes — but not through the endpoint the code makes it look like.**  Checked in
the source rather than recalled, because the two answers differ:

* What SHIPS is the ``CHAMPIONSHIP PATH`` block inside each team's card in the
  Related Futures section of an event page — one row per playoff stage, a
  label, a bar, the probability, the 24h move, and ``✓ clinched`` at >= 99.5%.
  It is fed by the **related-futures** payload's playoff-stage markets
  (``buildPathEntries``), and it existed as two verbatim copies, one per card.
  This queue lifted it into ``components/event/AdvancementPath``.

* What does NOT ship is ``GET /api/events/{id}/team-progression``.  The
  endpoint is real, the event page fetches it on every render, and the
  component written to draw it — ``GridPlayoffPathPair`` in
  ``RelatedFutures.tsx`` — was **never mounted**.  Dead since it was written.
  Its own docstring, and this route's, both claimed it rendered on event
  pages.  UX-P152 deleted it; the fetch is still a live gate on other sections
  and is left alone.

Neither fires for tennis anyway: ``team-progression`` needs a
``league_configs`` entry and a ``teams`` anchor, and a draw has neither —
measured 2026-08-28, ``/api/events/15293845/team-progression`` returns
``{"league": null, "home_team": null, "away_team": null}``.

So this module answers the same question from the data we do have: the
register's pinned ``reaches``, which the tournament page's playoff grid is
already built from (UX-P139).  It emits rows in the shape ``AdvancementPath``
takes, so the tennis strip and the league path are **one component with two
callers** rather than two implementations that agree today.  That is what Alex
asked for by "same component family": not a resemblance, the component.

═══ WHAT THE DATA CAN AND CANNOT COVER ═══

Measured against the live register 2026-08-28: **112** players carry reach
cells, against 96 R128 fixtures.  Of those fixtures:

* **14** have both players on the reach board,
* **56** have exactly one,
* **26** have neither.

A reach board is the field markets' top of the draw; an unseeded first-round
player is simply not quoted to reach the quarter-finals, and no amount of
plumbing conjures that number.  A side with no cells renders as an empty half
of the grid — so the one player who IS quoted keeps his own column rather than
stretching across the row and reading as the only entrant — and the section
suppresses itself entirely when NEITHER side has a cell, because two empty
columns is a promise of something that is not there.

═══ WHICH CARD GOES ON WHICH SIDE ═══

The contract has a ``home_team`` and an ``away_team`` slot and the event row has
a home and an away name, so the two cards have to be ordered.  That ordering is
the ONLY place a name is compared in this module, and it is not an identity
decision: **each card prints its own player's name**, so the worst case of a
non-decisive comparison is two correctly-labelled cards in the other order —
legible, not wrong.  Identity is already settled by
``tournament_event_link`` before this module is called, by id.  When the
comparison is not decisive the register's own order is kept, and
``side_order`` records which of the two happened.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: How a reach column's ``long_label`` opens.  Stripped so the strip reads as a
#: list of destinations ("Quarter-finals") under one heading rather than
#: repeating "To reach the" on every row.  Data-driven off the label the grid
#: already publishes — deliberately NOT a second round-name map that can drift
#: from ``tournament_grid.ROUNDS``.
_LABEL_PREFIXES = ("To reach the ", "To reach ", "To win the ", "To win ")


def stage_label(column: dict[str, Any]) -> str:
    """A reach column -> the words on the row."""
    long_label = column.get("long_label")
    if isinstance(long_label, str) and long_label.strip():
        text = long_label.strip()
        for prefix in _LABEL_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix) :]
                break
        if text:
            return text[0].upper() + text[1:]
    short = column.get("short_label")
    return short if isinstance(short, str) and short else str(column.get("key") or "")


def _fold(name: Any) -> str:
    """Accent- and case-insensitive form, for ORDERING ONLY (see module docstring)."""
    if not isinstance(name, str):
        return ""
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


def _surnames(name: Any) -> set[str]:
    return {tok for tok in _fold(name).split() if len(tok) > 2}


def _build_row(
    grid_row: dict[str, Any], columns: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """One reach row -> one ``TeamProgressionRow``, or ``None`` when it is empty.

    ``None`` rather than a row of nulls: the component filters
    ``probability !== null`` and would render a titled card with no rows, which
    reads as "we looked and the answer is nothing" rather than "we have not
    been told".
    """
    cells = grid_row.get("cells") or {}
    stages: list[dict[str, Any]] = []
    priced = 0
    for column in columns:
        key = column.get("key")
        cell = cells.get(key) or {}
        probability = cell.get("probability")
        if not isinstance(probability, (int, float)):
            probability = None
        else:
            probability = float(probability)
            priced += 1
        stages.append({
            "key": key,
            "label": stage_label(column),
            "probability": probability,
            # The register pins a reading, not a history; there is no 24h mark
            # on a reach cell. `null` is the contract's own "no move to show"
            # and the component already skips the delta on it — inventing a 0
            # would print "no change" about a number we never measured twice.
            "trend_24h": None,
            # SOURCE ATTRIBUTION OF A NUMBER THE READER IS LOOKING AT — allowed,
            # and often good, under ruling 141 as amended by Alex 2026-08-28.
            # The component renders these as a dot per source plus a count.
            "sources": [
                {"source": s.get("source"), "probability": s.get("probability")}
                for s in (cell.get("sources") or [])
                if isinstance(s, dict)
                and s.get("source")
                # A SOURCE THAT IS NOT QUOTING IS NOT A SOURCE OF THIS NUMBER.
                # The grid lists every source registered against the cell,
                # priced or not; the component draws one dot per entry and
                # prints "2 sources" underneath. On an unpriced cell that reads
                # as two suppliers agreeing about a blank.
                and isinstance(s.get("probability"), (int, float))
            ],
        })

    if priced == 0:
        return None

    display_name = grid_row.get("display_name") or grid_row.get("entity_key") or ""
    seed = grid_row.get("seed")
    return {
        "name": display_name,
        # The card's compact heading. A tennis player is not a franchise with a
        # nickname, so the surname is the short form a reader actually uses.
        "short_name": (display_name.split()[-1] if display_name else ""),
        "team_id": None,
        "logo_url": ((grid_row.get("image") or {}).get("url")),
        "primary_color": None,
        "secondary_color": None,
        # The contract's `record` slot, carrying the one standing fact a draw
        # has about a player. Seeds are the tennis equivalent and the component
        # already prints this field small and to the right.
        "record": (f"Seed {seed}" if isinstance(seed, int) else None),
        "conference": None,
        "stages": stages,
        # ── A LADDER THAT CLIMBS (see `monotonic`) ──
        "monotonic": is_monotonic(stages),
    }


def is_monotonic(stages: list[dict[str, Any]]) -> bool:
    """Does this ladder fall the way a draw must — never likelier later?

    A player cannot be likelier to reach the final than the semis.
    ``tournament_grid.evaluate_monotonicity`` already measures this across the
    whole board and its ruling is **report, not correct**: measured 2026-08-26,
    21 of 84 ladder players violate it, all in the sub-5% tail where a thin
    binary prices "reach the final" a point above "reach the semis". That is
    the market's own incoherence and correcting it would be the page lying on
    the market's behalf.

    Reported here too, and for a reason the grid does not have. On the grid a
    2% against a 4% is two cells in an 84-row table and reads as noise. On a
    match page it is five large rows on one of two cards, and it reads as a
    contradiction the page has not noticed — the same numbers, at a
    magnification where silence stops being neutral. So the strip carries the
    verdict and prints one sentence, rather than either hiding a row or
    printing the inversion with a straight face.

    Same epsilon as the grid's, imported rather than restated: two surfaces
    disagreeing about whether a ladder is coherent is worse than either answer.
    """
    from app.utils.tournament_grid import MONOTONICITY_EPSILON  # noqa: PLC0415

    priced = [
        s["probability"] for s in stages if isinstance(s.get("probability"), (int, float))
    ]
    return all(
        before >= after - MONOTONICITY_EPSILON
        for before, after in zip(priced, priced[1:])
    )


def build_advancement(
    grids: dict[str, Any],
    *,
    matchup: dict[str, Any],
    event_id: int,
    home_team_name: Optional[str],
    away_team_name: Optional[str],
    tournament_title: Optional[str] = None,
    tournament_slug: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """The two players' reach rows, in ``TeamProgressionResponse`` shape.

    ``grids`` is ``build_grids``' output verbatim — this module reads the SAME
    object the tournament page's playoff grid renders, so the strip on the
    event page and the grid on the hub cannot disagree about a cell.  There is
    no second read of the register here and no second blend.

    Returns ``None`` when neither player has a priced reach cell.
    """
    entity_keys = [k for k in (matchup.get("players") or []) if isinstance(k, str)]
    if len(entity_keys) != 2:
        return None

    draw = matchup.get("draw")
    grid = (grids or {}).get(draw) or {}
    columns = [
        c for c in (grid.get("columns") or [])
        if isinstance(c, dict) and c.get("key")
    ]
    if not columns:
        return None

    by_entity = {
        r.get("entity_key"): r
        for r in (grid.get("rows") or [])
        if isinstance(r, dict) and r.get("entity_key")
    }

    rows: list[Optional[dict[str, Any]]] = []
    for key in entity_keys:
        grid_row = by_entity.get(key)
        rows.append(_build_row(grid_row, columns) if grid_row else None)

    if not any(rows):
        # NEITHER side is quoted to reach anything. 26 of 96 R128 fixtures, and
        # the honest output is no section rather than an empty one.
        return None

    # ── ORDERING ONLY. Identity was settled by id upstream. ──
    first, second = rows
    side_order = "register"
    home_fold, away_fold = _surnames(home_team_name), _surnames(away_team_name)
    names = [(r or {}).get("name") for r in rows]
    if home_fold and away_fold and not (home_fold & away_fold):
        first_names = _surnames(names[0])
        second_names = _surnames(names[1])
        first_is_home = bool(first_names & home_fold) and not (first_names & away_fold)
        second_is_away = bool(second_names & away_fold) and not (second_names & home_fold)
        first_is_away = bool(first_names & away_fold) and not (first_names & home_fold)
        second_is_home = bool(second_names & home_fold) and not (second_names & away_fold)
        if first_is_home or second_is_away:
            side_order = "event"
        elif first_is_away or second_is_home:
            first, second = second, first
            side_order = "event"

    return {
        "event_id": event_id,
        # The contract's league slot. The hub is this draw's grid, so the
        # "see the whole grid" affordance the component already renders points
        # at the surface the numbers came from.
        "league": tournament_slug,
        "league_name": tournament_title,
        "grid_url": (f"/tournaments/{tournament_slug}" if tournament_slug else None),
        "columns": [
            {"key": c.get("key"), "label": stage_label(c), "order": i}
            for i, c in enumerate(columns)
        ],
        "home_team": first,
        "away_team": second,
        # Which rule ordered the two cards — read by the test that proves a
        # non-decisive comparison falls back rather than guessing.
        "side_order": side_order,
    }
