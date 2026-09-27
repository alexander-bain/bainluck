"""Serve the stored line score only when it adds up to the served score (#9067).

``Event.box_score_data`` carries ESPN's per-period line score as
``home_period_scores`` / ``away_period_scores`` (ints, ``None`` = a hole the
venue left blank). The event payload used to strip them, so the iPhone's Game
Segments table rebuilt each period from chart polling and printed
``STAN 7 · 3 · 3`` beside a total of 19 (rage shake #159, event 15315948).

THE ARRAYS ARE NOT ALWAYS THE GAME, SO THEY ARE CHECKED AGAINST THE SCORE
-----------------------------------------------------------------------
The line score is written by the ESPN box pass (every ~2 min while live, once
more after full time); the headline score moves every ~15 s. Measured on
production 2026-09-27: of the 195 games completed in the trailing three days
that carry period arrays, **10 do not add up to their own final score** —
seven froze before the last points (FAMU 21–40 stored three quarters; Mercury
stored 80 of 82), three are hockey shootouts whose winning goal is in the score
and in no period. Serving those reprints the reader's complaint, "scores don't
add up", from the server instead of the phone.

So a pair is served only when each side's recorded periods sum to that side's
served score. A hole cannot be summed, so with a hole the recorded periods may
not EXCEED the score (the hole can carry the rest). Anything else — lengths that
differ, a non-integer entry, a missing score — is withheld, and the client keeps
its fallback. A side whose arrays are swapped against ours sums to the other
side's score and is withheld by the same check, unless the two scores are equal.

The last entry of a live array is the period in progress: a running score, never
a result. Grading stays behind ``_grade_closed_windows``' own gate.
"""

from __future__ import annotations

from typing import Any, Optional


def _is_period(value: Any) -> bool:
    # bool is an int subclass; a True in a line score is corruption, not a run.
    return value is None or (isinstance(value, int) and not isinstance(value, bool))


def _adds_up(periods: list, score: int) -> bool:
    recorded = sum(p for p in periods if p is not None)
    if any(p is None for p in periods):
        return recorded <= score
    return recorded == score


def served_period_scores(
    box: Any, home_score: Any, away_score: Any
) -> Optional[dict[str, list]]:
    """``{"home_period_scores", "away_period_scores"}`` or ``None`` (withhold)."""
    if not isinstance(box, dict):
        return None
    home = box.get("home_period_scores")
    away = box.get("away_period_scores")
    if not isinstance(home, list) or not isinstance(away, list):
        return None
    if not home or len(home) != len(away):
        return None
    if not all(_is_period(p) for p in home + away):
        return None
    for score in (home_score, away_score):
        if not isinstance(score, int) or isinstance(score, bool):
            return None
    if not (_adds_up(home, home_score) and _adds_up(away, away_score)):
        return None
    return {"home_period_scores": list(home), "away_period_scores": list(away)}
