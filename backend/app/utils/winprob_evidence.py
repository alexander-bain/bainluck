"""What a served win-probability point can prove about observation (#7878).

Codex's card-B decision (2026-09-24): only a stored reading's `captured_at` is an
observation instant, and two consecutive readings no more than G apart prove the
stretch between them was recorded at resolution G. A wider gap is UNKNOWN — the
chart breaks the line or says history is unavailable, and never claims the feed
was down.

Two halves live here so they cannot drift apart:

* **The stamp** the 48-hour retention collapse writes on a keeper row
  (`tasks/retention.py`): ``game_state.evidence_span = {contract, resolution_s,
  covered_through}`` — the latest genuine capture the merged run contained. The
  constants below are the ones that SQL writes and reads.
* **The served shape** `/api/events/{id}/history` puts on each point. The route
  narrows `game_state` to the keys clients read (#6546), which removes the stamp
  and every provenance key, so the evidence travels as its own small key,
  computed here BEFORE that projection runs:

      response["evidence_contract"] = {"v": "7878.v1", "resolution_s": 300}
      point["evidence"]             = {"kind": ..., "covered_through"?: ISO}

  A point with no ``evidence`` key is a plain observation at its own
  ``timestamp``. Every other point says what it is:

      observed      a reading that also proves coverage through ``covered_through``
                    (a validated span; malformed or foreign spans are dropped,
                    and the point is then a plain observation)
      candle        a venue candlestick aggregate (`history_backfill`), not a tick
      price_history a venue price-history point (Polymarket CLOB backfill)
      play_history  an ESPN win-probability point written after the game from
                    ESPN's play-by-play, stamped at its play's ``wallclock``
                    (#8514) — ESPN's value at a true time, not a tick we observed
      estimated_time an ESPN backfill point written before #8514, stamped at an
                    evenly spread guess between kick-off and when the backfill
                    ran; drawn, never evidence, and not served at all for a series
                    that also holds ``play_history`` points
      live_edge     synthesised at request time to carry the line to now
      final         synthesised from our resolved result
      terminal_row  the last stored reading of a finished game; a completed game
                    rewrites that row's value in place (#922), so it is not
                    evidence of observation at its timestamp

  Only a plain observation or ``observed`` proves anything. A client that does not
  see ``evidence_contract`` is talking to a server without this classification
  and must keep its previous behaviour.

Payload: plain observations — nearly every point — carry nothing new, so #6546's
reduction stands.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

#: Display evidence resolution G. Not a freshness SLA and not proof of
#: continuous observation (Codex card-B decision, item 1).
EVIDENCE_RESOLUTION_S = 300

#: Names the contract a stamped span was written under. A span stamped under any
#: other contract or resolution is ignored, so a future change to G cannot
#: inherit coverage proven at a coarser resolution.
EVIDENCE_CONTRACT = "7878.v1"

#: `covered_through` is written in exactly this shape by the retention SQL and
#: accepted back only if it matches (there, before a cast; here, before a parse).
COVERED_THROUGH_RE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
_COVERED_THROUGH = re.compile(COVERED_THROUGH_RE)

#: Served once per response so a client can tell a classifying server apart
#: from one that predates this contract.
SERVED_CONTRACT = {"v": EVIDENCE_CONTRACT, "resolution_s": EVIDENCE_RESOLUTION_S}


#: `game_state.time_basis` on an ESPN win-probability backfill row whose
#: `captured_at` is its play's evidenced `wallclock` (#8514). The backfill writes
#: it; retention, this module and the route read it.
PLAY_WALLCLOCK_BASIS = "play_wallclock"

#: What `espn_wp_backfill_basis` answers for a backfill row written before
#: #8514, whose `captured_at` was spread evenly over a guessed window.
ESTIMATED_BASIS = "estimated"


def espn_wp_backfill_basis(state: Any) -> Optional[str]:
    """How an ESPN win-probability BACKFILL row got its `captured_at`, or None.

    That backfill has always written ``{"seconds_left", "backfilled": true}``;
    ``game_state_backfill`` also writes ``backfilled`` but never ``seconds_left``
    (its rows are period markers), so the pair is this writer's signature. Since
    #8514 the row also says ``time_basis``; a row without one predates it and
    sits at an estimated time.
    """
    if not isinstance(state, dict) or state.get("backfilled") is not True:
        return None
    if "seconds_left" not in state:
        return None
    if state.get("time_basis") == PLAY_WALLCLOCK_BASIS:
        return PLAY_WALLCLOCK_BASIS
    return ESTIMATED_BASIS


def drop_superseded_estimates(points: list) -> tuple[list, int]:
    """Remove estimated-time backfill points from a series that has evidenced ones.

    Once the backfill has re-read a game with play times (#8514), its older
    estimated rows are the same ESPN readings at the wrong instants — on
    15318166 they trailed every other source by 15–40 minutes and ran 27 minutes
    past the final. Nothing is deleted from the table; a series with no
    evidenced point is returned whole. Returns (points, number removed).
    """
    bases = [espn_wp_backfill_basis(p.get("game_state")) for p in points]
    if PLAY_WALLCLOCK_BASIS not in bases:
        return points, 0
    kept = [p for p, basis in zip(points, bases) if basis != ESTIMATED_BASIS]
    return kept, len(points) - len(kept)


def _parse(ts: Any) -> Optional[datetime]:
    if not isinstance(ts, str):
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def validated_covered_through(state: Any, captured_at: Any) -> Optional[datetime]:
    """The span end a stored stamp proves, or None. Fails closed on anything odd."""
    if not isinstance(state, dict):
        return None
    span = state.get("evidence_span")
    if not isinstance(span, dict):
        return None
    resolution = span.get("resolution_s")
    if (
        span.get("contract") != EVIDENCE_CONTRACT
        or isinstance(resolution, bool)
        or resolution != EVIDENCE_RESOLUTION_S
    ):
        return None
    raw = span.get("covered_through")
    if not isinstance(raw, str) or not _COVERED_THROUGH.match(raw):
        return None
    through = _parse(raw)
    start = _parse(captured_at)
    if through is None or start is None or through < start:
        return None
    return through


def served_evidence(point: dict, *, terminal_row: bool = False) -> Optional[dict]:
    """The ``evidence`` value for one served point, or None for a plain reading.

    Order matters: a live-edge point copies its predecessor's ``game_state``
    (stamp included), so synthetic kinds are decided before anything is read
    off the state.
    """
    if point.get("live_edge"):
        return {"kind": "live_edge"}
    state = point.get("game_state")
    state = state if isinstance(state, dict) else {}
    if state.get("final") is True:
        return {"kind": "final"}
    if state.get("poll_type") == "history_backfill":
        return {"kind": "candle"}
    if state.get("backfill") is True:
        return {"kind": "price_history"}
    # #8514: ESPN's play-by-play, written after the fact. Decided before the
    # stamp is read — a pre-#8514 retention pass merged these rows and stamped
    # spans on them, which would otherwise serve as `observed`.
    basis = espn_wp_backfill_basis(state)
    if basis == PLAY_WALLCLOCK_BASIS:
        return {"kind": "play_history"}
    if basis is not None:
        return {"kind": "estimated_time"}
    if terminal_row:
        return {"kind": "terminal_row"}
    through = validated_covered_through(state, point.get("timestamp"))
    if through is not None:
        return {"kind": "observed", "covered_through": through.isoformat()}
    return None


def attach_served_evidence(win_prob_history: dict, *, is_finished: bool) -> None:
    """Put ``evidence`` on every point that needs one. Must run BEFORE
    `_project_served_game_state`, which removes the keys this reads.

    On a finished game the last stored reading of each series (the last point
    that is neither synthesised result nor live edge) is ``terminal_row``. When
    the route's end cap has already cut the true last row off, this marks a
    genuine reading instead — which only withholds coverage, never invents it.
    """
    for points in (win_prob_history or {}).values():
        if not points:
            continue
        last_stored = None
        if is_finished:
            for index in range(len(points) - 1, -1, -1):
                candidate = points[index]
                state = candidate.get("game_state")
                synthetic = candidate.get("live_edge") or (
                    isinstance(state, dict) and state.get("final") is True
                )
                if not synthetic:
                    last_stored = index
                    break
        for index, point in enumerate(points):
            evidence = served_evidence(point, terminal_row=(index == last_stored))
            if evidence is not None:
                point["evidence"] = evidence
            else:
                point.pop("evidence", None)
