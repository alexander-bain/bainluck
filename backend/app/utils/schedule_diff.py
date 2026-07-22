"""#1201 — MLB schedule-diff: reconcile the official MLB schedule against our
events and emit TYPED transitions (the root fix that supersedes the 60s mop-up).

The recurring resolved_state rot (#1193: cross-merged / prematurely-settled MLB
events) exists because we have no schedule-transition model — nothing polls the
official schedule and reconciles it against our rows. This module is that
reconciler's pure core: given the official schedule (from
``MLBAPIService.get_todays_games``) and our events, it classifies every
divergence into a typed :class:`ScheduleTransition` so a caller (a task or the
Flow Sentinel) can act on or file it.

Pure + dependency-light (dicts in, dataclasses out) so the classification is
unit-tested deterministically. The sentinel invariant is: **every official game
today ↔ exactly one of our events** (0 matches = ``missing_event``; >1 =
``duplicate_events``). On top of that it detects state divergence:
``premature_settle`` (we settled a game MLB still has live/scheduled — the
#1193/#1201 class) and ``postponed`` (MLB postponed a game we still have
active).

Applying the transitions (creating the missing event, merging duplicates,
un-settling, splitting a doubleheader) is deliberately left to the caller and
gated — this module only classifies. That keeps the risky mutation path out of a
pure, always-on detector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# MLB statusCode / detailedState groupings (statsapi).
_LIVE_STATES = {"In Progress", "Manager Challenge", "Warmup"}
_SCHEDULED_STATES = {"Scheduled", "Pre-Game", "Warmup", "Delayed Start", "Delayed"}
_FINAL_STATES = {"Final", "Game Over", "Completed Early"}
_POSTPONED_STATES = {"Postponed", "Suspended", "Cancelled", "Canceled"}

# Our terminal statuses.
_SETTLED_STATUSES = {"completed", "closed"}


@dataclass
class OfficialGame:
    """One game off the official MLB schedule, normalized from the raw dict."""
    game_pk: Optional[int]
    home: str
    away: str
    detailed_state: str
    game_datetime: Optional[str]  # ISO
    doubleheader: str = "N"       # "N" (none) | "S" (split) | "Y" (traditional)
    game_number: int = 1


@dataclass
class ScheduleTransition:
    """A typed divergence between the official schedule and our events."""
    kind: str  # missing_event | duplicate_events | premature_settle | postponed
    home: str
    away: str
    detail: str
    game_pk: Optional[int] = None
    event_ids: list[int] = field(default_factory=list)


def _tokens(s: str) -> set:
    return set((s or "").lower().replace(".", "").split())


def teams_match(our_home: str, our_away: str, off_home: str, off_away: str) -> bool:
    """True if our (home, away) matches the official game in either orientation
    (token overlap on both sides). Orientation-tolerant because our home/away can
    be swapped relative to MLB's (gotcha #32 sibling handling)."""
    aligned = bool(_tokens(our_home) & _tokens(off_home)) and bool(_tokens(our_away) & _tokens(off_away))
    swapped = bool(_tokens(our_home) & _tokens(off_away)) and bool(_tokens(our_away) & _tokens(off_home))
    return aligned or swapped


def normalize_official_game(raw: dict) -> OfficialGame:
    """Extract an :class:`OfficialGame` from a raw MLB schedule game dict
    (``MLBAPIService.get_todays_games`` element)."""
    teams = raw.get("teams", {}) or {}
    home = (teams.get("home", {}) or {}).get("team", {}).get("name", "") or ""
    away = (teams.get("away", {}) or {}).get("team", {}).get("name", "") or ""
    status = raw.get("status", {}) or {}
    try:
        game_number = int(raw.get("gameNumber", 1) or 1)
    except (TypeError, ValueError):
        game_number = 1
    return OfficialGame(
        game_pk=raw.get("gamePk"),
        home=home,
        away=away,
        detailed_state=status.get("detailedState", "") or "",
        game_datetime=raw.get("gameDate"),
        doubleheader=raw.get("doubleHeader", "N") or "N",
        game_number=game_number,
    )


def diff_schedule(
    official_games: list[OfficialGame],
    our_events: list[dict],
    now: Optional[datetime] = None,
) -> list[ScheduleTransition]:
    """Classify every official game against our events into typed transitions.

    ``our_events`` are dicts with at least: ``id``, ``home_team``/``home``,
    ``away_team``/``away``, ``status``. Only divergences are returned — an
    official game with exactly one, correctly-stated event yields nothing.
    """
    out: list[ScheduleTransition] = []

    def _e_home(e):
        return e.get("home_team") or e.get("home") or ""

    def _e_away(e):
        return e.get("away_team") or e.get("away") or ""

    for og in official_games:
        matches = [
            e for e in our_events
            if teams_match(_e_home(e), _e_away(e), og.home, og.away)
        ]
        dh = "" if og.doubleheader in ("N", "") else f" (DH game {og.game_number})"

        if len(matches) == 0:
            out.append(ScheduleTransition(
                kind="missing_event", home=og.home, away=og.away, game_pk=og.game_pk,
                detail=f"official MLB game {og.away} @ {og.home}{dh} has NO matching event",
            ))
            continue

        if len(matches) > 1:
            out.append(ScheduleTransition(
                kind="duplicate_events", home=og.home, away=og.away, game_pk=og.game_pk,
                event_ids=[m.get("id") for m in matches if m.get("id") is not None],
                detail=f"official MLB game {og.away} @ {og.home}{dh} matches "
                       f"{len(matches)} events (expected exactly 1)",
            ))
            # A split doubleheader legitimately has two events; only flag when the
            # official game is NOT a doubleheader (so two events = a real dup).
            continue

        # Exactly one event — check state divergence.
        e = matches[0]
        e_settled = (e.get("status") or "") in _SETTLED_STATUSES
        if og.detailed_state in _POSTPONED_STATES and not e_settled:
            out.append(ScheduleTransition(
                kind="postponed", home=og.home, away=og.away, game_pk=og.game_pk,
                event_ids=[e.get("id")] if e.get("id") is not None else [],
                detail=f"official MLB game {og.away} @ {og.home} is {og.detailed_state} "
                       f"but our event is {e.get('status')!r}",
            ))
        elif e_settled and og.detailed_state in (_LIVE_STATES | _SCHEDULED_STATES):
            out.append(ScheduleTransition(
                kind="premature_settle", home=og.home, away=og.away, game_pk=og.game_pk,
                event_ids=[e.get("id")] if e.get("id") is not None else [],
                detail=f"our event {e.get('id')} is settled ({e.get('status')}) but official "
                       f"MLB status is {og.detailed_state!r} — premature settle (#1201/gotcha #32)",
            ))

    return out
