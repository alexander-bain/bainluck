"""Which side of a fixture does the short team name on an outcome NAME?

Lifted out of :mod:`app.utils.period_window_grade` (#1735) unchanged when
:mod:`app.utils.final_score_margin` (#6312) needed the same question answered
about a FULL-GAME margin question. It is one module rather than two copies for
the reason that module already states about its window classifier: two
resolvers drift the moment either one's matching rule is widened, and the
direction they drift in prints a verdict under the wrong club's name.

Both readers grade a row a reader will SEE, so both want the strict, fail-safe
test below and not a matcher helper. A permissive matcher is the right tool for
LINKING two rows that are probably the same fixture (#2693) and the wrong tool
for displaying a result.
"""

from __future__ import annotations

import re

__all__ = ["normalize_team_text", "resolve_team_side"]


def normalize_team_text(text) -> str:
    """Lowercased, single-spaced, punctuation-light — for team-name comparison only."""
    if not text:
        return ""
    cleaned = re.sub(r"[.'’]", "", str(text)).lower()
    return " ".join(cleaned.split())


def resolve_team_side(team_text, home_team_name, away_team_name):
    """``"home"``, ``"away"``, or ``None`` when the name does not name exactly one.

    The outcome wears a SHORT name and the row wears the full one — "Tampa Bay"
    against "Tampa Bay Rays", "Gwangju" against "Gwangju FC". So the test is
    prefix containment in either direction, and the fail-safe is **exactly one**
    side matching:

    * "New York" on a Yankees/Mets matchup matches both, so it resolves to
      neither. Picking one would print a verdict under the wrong club's name.
    * "Chicago WS" matches neither "Chicago White Sox" nor "Pittsburgh Pirates",
      because "ws" is an abbreviation and not a prefix. That row keeps today's
      behaviour — no verdict — rather than being graded off a guess.
    """
    needle = normalize_team_text(team_text)
    if not needle:
        return None

    matches = []
    for side, full_name in (("home", home_team_name), ("away", away_team_name)):
        candidate = normalize_team_text(full_name)
        if not candidate:
            continue
        if candidate == needle or candidate.startswith(needle) or needle.startswith(candidate):
            matches.append(side)

    return matches[0] if len(matches) == 1 else None
