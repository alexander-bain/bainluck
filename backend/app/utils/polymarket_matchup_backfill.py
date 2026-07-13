"""A2 title-backfill helper — recover a Polymarket game event's matchup title.

A Polymarket game event is stored as decomposed sub-market rows (gotcha #18): the
moneyline and O/U rows carry "Team A vs. Team B" in their ``name``, but the spread
("Spread: San Diego Padres (-2.5)") and prop ("Will the game go to extra
innings?: …") rows do not — so the participant grammar cannot recover both teams
from those rows' names alone. That is the root of the poly ``market_event`` shadow
gap: those rows produce ZERO participants, so the resolution engine can't
reproduce their (correct) stored ``event_id`` link.

The fix is source-native and non-circular: every sub-market of one game shares a
``group_id`` (``polymarket:<event_id>``), and at least one sibling (the moneyline
/ an O/U row) names the full "A vs. B" matchup. We recover that group matchup and
stamp it onto the siblings that lack it (``market_metadata['matchup_title']``), so
``grammar_adapters.annotate_stored_market`` can read both participants. The engine
then independently proves the event link by participant-set agreement with the
event's own team names — the matchup title is derived from Polymarket's own group,
never from the event we are trying to reproduce.

Pure logic only (no DB) so it is unit-testable; the DB write lives in
``scripts/backfill_polymarket_matchups.py``.
"""

from __future__ import annotations

from typing import Iterable, Optional

from app.utils.prediction_market_matching import extract_matchup


def matchup_from_name(name: str | None) -> Optional[tuple[str, str]]:
    """The two teams in a sub-market name ("A vs. B: O/U 11.5" → (A, B)), or None
    when the name carries no full matchup (spread/prop rows)."""
    m = extract_matchup(name or "")
    if m and m.team_a and m.team_b:
        return (m.team_a, m.team_b)
    return None


def group_matchup(names: Iterable[str]) -> Optional[str]:
    """Best "Team A vs. Team B" title recoverable from a group's sibling names.

    Prefers the SHORTEST name that still parses (least line/prop noise → the
    cleanest matchup, typically the moneyline row). Returns the canonical
    "A vs. B" string, or None when no sibling names a matchup (not a game group).
    """
    best_len: Optional[int] = None
    best_title: Optional[str] = None
    for n in names:
        mu = matchup_from_name(n)
        if not mu:
            continue
        title = f"{mu[0]} vs. {mu[1]}"
        if best_len is None or len(n or "") < best_len:
            best_len, best_title = len(n or ""), title
    return best_title


def needs_matchup_backfill(name: str | None, existing_matchup_title: str | None) -> bool:
    """True if a row can't yield its two participants from its own name and does
    not already carry a ``matchup_title`` — i.e. it needs the group matchup
    stamped on it. Idempotent: a row already backfilled returns False."""
    if existing_matchup_title:
        return False
    return matchup_from_name(name) is None
