"""Provenance for a per-sportsbook projected-final-points history point (#10239 / #10461).

`get_event_history` builds `bookmaker_history` two ways and emits both with the
same shape: a snapshot captured inside the window is stamped at its own capture
minute, and a snapshot captured BEFORE the request cutoff (but still valid at
it) is re-stamped at the cutoff minute. The second is a carry, not a new
sportsbook reading, and nothing on the point says so — a client drawing
"projected final points" cannot tell a recorded forecast from a prior one moved
to the left edge of the window.

`bookmaker_history_provenance` names which one a point is, as additive metadata:

- ``kind``: ``"recorded"`` iff there is no cutoff or the capture is at/after it
  (the exact predicate the route uses to keep the capture minute), otherwise
  ``"synthetic"``.
- ``observed_at``: the snapshot's ORIGINAL capture instant, ISO-8601. This is
  when we captured the snapshot, not when the venue traded — never present it
  as a trade clock.

It never touches probabilities, projected scores, the displayed ``timestamp``
or ``valid_until``, and it does not decide whether a point is included (the
route's ``valid_until`` exclusion stays where it is). Input that is not an
aware datetime — missing, naive, the wrong type, or a tzinfo that cannot answer
— gets ``None``: no metadata is better than inventing recorded evidence, and a
refusal must never raise into the rest of the history.

Pure: no clock, no I/O, no import side effects.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict

RECORDED: Literal["recorded"] = "recorded"
SYNTHETIC: Literal["synthetic"] = "synthetic"


class BookmakerHistoryProvenance(TypedDict):
    kind: Literal["recorded", "synthetic"]
    observed_at: str


def _is_aware_instant(value: object) -> bool:
    if not isinstance(value, datetime):
        return False
    try:
        return value.utcoffset() is not None
    except Exception:
        return False


def bookmaker_history_provenance(
    *, captured_at: datetime, cutoff: datetime | None
) -> BookmakerHistoryProvenance | None:
    """Return ``{"kind", "observed_at"}`` for one snapshot, or ``None`` to refuse."""
    if not _is_aware_instant(captured_at):
        return None
    if cutoff is not None and not _is_aware_instant(cutoff):
        return None
    try:
        recorded = cutoff is None or captured_at >= cutoff
        observed_at = captured_at.isoformat()
    except Exception:
        return None
    return {"kind": RECORDED if recorded else SYNTHETIC, "observed_at": observed_at}
