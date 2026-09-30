"""Is this box score a MID-GAME capture? One answer for every grader (#9734).

``Event.box_score_data`` has two writers. The settled pass
(``espn_helpers.fetch_completed_box_scores`` / ``espn_sync._backfill_box_scores``)
writes the final box with no ``live`` key. The live pass
(``espn_helpers.fetch_live_box_scores``) writes ``"live": True`` beside a
snapshot of the game AS IT STOOD at ``fetched_at``.

A finished event whose box still says ``live`` never received its final box: a
starved live pass, a refused write, an ESPN outage, or a game older than the
settled pass's 48-hour window. On `/events/15320240` (Cubs @ Padres, final 8-0)
the box was the 02:11Z capture, eleven minutes after first pitch, and the page
graded 203 props off it — "Michael King 2+ strikeouts … missed" for a pitcher
who struck out 8. Production 2026-09-30: 1,390 finished events carry a live-era
box, and 2,845 stored ``box_score`` / ``box_score_bound`` verdicts on them were
computed from one.

So a live capture never grades a settled prop. The route withholds, and the
resolver passes skip the event until the final box lands. Withholding a verdict
costs the reader a row marked pending; publishing one off a first-inning box
prints a false result beside a game they just watched.
"""

from __future__ import annotations

#: The resolution sources whose verdict was computed from ``box_score_data``
#: player stats (``backfill_winners._resolve_kalshi_player_props_from_boxscore``
#: and ``_resolve_kalshi_total_bases_from_boxscore``). While the event's box is
#: still a live capture, a stored verdict from one of these is the same
#: mid-game read, laundered through the table.
BOX_SCORE_SOURCES: frozenset[str] = frozenset({"box_score", "box_score_bound"})


def box_is_live_capture(box) -> bool:
    """True when ``box`` is a live-pass snapshot rather than the final box.

    FAILS CLOSED. The only writer stamps ``True``, but any ``live`` value other
    than absent / ``None`` / ``False`` is read as live: a box we cannot read as
    final is not a box to grade from. A non-dict carries no flag and is left to
    the caller's own shape checks.
    """
    if not isinstance(box, dict):
        return False
    live = box.get("live")
    return live is not None and live is not False
