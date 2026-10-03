"""What a freshly received ESPN player box says about itself (#10237, #10268).

The three box writers (the live pass and the completed pass in
``espn_helpers``, the settled backfill in ``espn_sync``) each replace
``box_score_data`` with one whole dict. This module builds the one sibling key
that dict may carry, ``provider_box_evidence``, so the three writers cannot
drift apart:

    {"provider": "espn", "provider_event_id": "401872660",
     "evidence_kind": "fresh_provider_box",
     "captured_at": <the box's own fetched_at string>,
     "provider_status": {"name": ..., "state": ..., "completed": ...},
     "provider_final": bool}

It records what the SAME response said, and decides nothing. Whether a box is
an official final statistic, a comparison or a settlement is the After
reader's decision (Authority), never this writer's.

Admission is narrow on purpose:

* a NON-EMPTY player box from this response. A scoring-plays-only answer, an
  empty answer, a box kept from an earlier fetch, authority dark and the error
  branch get no marker. Callers only call this on the fresh-box branch, and
  this function refuses an empty ``players`` itself as well.
* the response's own ``header.id`` equals the ESPN id we asked for. A missing
  or different id gets no marker. Nothing is matched by name or time and no id
  is substituted.
* ``captured_at`` is the caller's ``fetched_at`` string itself. This module
  reads no clock.

``provider_final`` is true only when ESPN's ``completed`` is exactly ``True``
and its status name is not one of the excluded names below. ``state == "post"``
or a ``STATUS_FINAL`` name alone is never enough, because ESPN puts a postponed
game in ``post`` as well. The raw triple is stored as received, so a reader can
apply a stricter rule without a writer change.

Pure: no I/O, no clock, no imports from the app.
"""

from __future__ import annotations

from typing import Any, Optional

PROVIDER = "espn"
EVIDENCE_KIND = "fresh_provider_box"

# A status name in this set never asserts final, even next to completed=True.
NONFINAL_STATUS_NAMES = frozenset({
    "STATUS_POSTPONED",
    "STATUS_CANCELED",
    "STATUS_SUSPENDED",
    "STATUS_ABANDONED",
    "STATUS_DELAYED",
})

_SCALAR_TYPES = (str, bool, int, float)


def _raw_scalar(value: Any) -> Any:
    """A status field as ESPN sent it, or ``None`` if it is not a JSON scalar."""
    return value if isinstance(value, _SCALAR_TYPES) else None


def provider_status_is_final(status: Any) -> bool:
    """ESPN's own "this game is over": completed exactly True, name not excluded.

    Malformed, missing or partial input is never final.
    """
    if not isinstance(status, dict):
        return False
    if status.get("completed") is not True:
        return False
    name = status.get("name")
    if not isinstance(name, str) or not name:
        return False
    return name not in NONFINAL_STATUS_NAMES


def build_provider_box_evidence(
    *,
    requested_event_id: Any,
    players: Any,
    scores: Any,
    captured_at: Any,
) -> Optional[dict]:
    """The ``provider_box_evidence`` for one freshly received box, or ``None``.

    ``requested_event_id`` is the ``event.espn_id`` the writer asked ESPN for.
    ``players`` is this response's parsed player box. ``scores`` is this
    response's ``context["scores"]`` (``provider_event_id`` and
    ``provider_status`` come from ``_parse_header_scores``). ``captured_at`` is
    the exact string the writer stores as the box's ``fetched_at``.

    ``None`` means "write the box as before, with no marker".
    """
    if not isinstance(players, dict) or not players:
        return None
    if not isinstance(captured_at, str) or not captured_at:
        return None
    if not isinstance(scores, dict):
        return None
    if requested_event_id is None:
        return None
    requested = str(requested_event_id).strip()
    returned = scores.get("provider_event_id")
    if not requested or not isinstance(returned, str) or returned != requested:
        return None

    raw_status = scores.get("provider_status")
    if not isinstance(raw_status, dict):
        raw_status = {}
    provider_status = {
        "name": _raw_scalar(raw_status.get("name")),
        "state": _raw_scalar(raw_status.get("state")),
        "completed": _raw_scalar(raw_status.get("completed")),
    }
    return {
        "provider": PROVIDER,
        "provider_event_id": returned,
        "evidence_kind": EVIDENCE_KIND,
        "captured_at": captured_at,
        "provider_status": provider_status,
        "provider_final": provider_status_is_final(provider_status),
    }
