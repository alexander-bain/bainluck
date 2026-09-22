"""#7807 acceptance — one log line when the DURABLE tier actually served a chart.

PILLAR: TRUTH. SHIP: a recovered venue history remains available to the next
reader after the fast cache loses it.

WHY A RECEIPT AND NOT A SAMPLER. #7807 shipped a second tier: when Redis has
evicted a market's venue-history bank, `durable_state_snapshots` answers instead
and the CHART is unchanged — same points, same outcomes, same line. What differs
is one metadata field: `venue_history.tier` reads `durable` instead of `cache`,
and #7351 publishes it precisely so the two-tier read is legible. So a durable
serve is not invisible; it is visible to EXACTLY ONE PARTY — the reader whose own
request took the fallback, in that request's own response.

That is what defeats sampling, and the distinction is worth keeping straight. A
durable serve REHYDRATES Redis, so the next read says `cache` again. A scheduled
sampler therefore cannot see a durable serve some OTHER reader took: by the time
it looks, the evidence is gone. It can only ever catch a fallback it causes
itself, which is a fallback a real user was not having. Scheduled reader sampling
was retired as a proof for this reason — not because the event leaves no trace,
but because the trace is only ever in the response of whoever tripped it.

So the reader writes down what it did, at the instant it did it. One line, on
the response-metadata boundary that already exists, only when the durable tier
is the tier that answered.

BOTH CHART READERS WRITE IT, AND THE PHONE'S DOOR IS THE ONE THAT MATTERS.
`/history` and `/probability-timeline` both load the bank through
`_load_generic_venue_history`, so either can be the first to touch an evicted
one — and the first through takes the durable tier and rehydrates Redis for the
second. `APIClient.swift:929` fetches `/probability-timeline`, and nothing native
fetches `/history`, so the phone is the likelier first reader. Wired into
`/history` alone, a phone-first fallback wrote nothing and the `/history` read
behind it reported `cache`: a durable serve that happened and left no record, in
the half of the traffic that matters most. `surface` names which door fell back.

WHAT IT IS NOT. Not a monitoring program, not a metric, not a new store: no DB
row, no endpoint, no network call, no periodic anything. Its whole job is to let
the acceptance step name ONE real market / build / bank, so the chart for that
bank can be looked at. After that it is a rare, cheap line about a rare event.

LEVEL: `warning`, and the reason is MEASURED, not stylistic. The web dyno runs
`uvicorn app.main:app` with no logging configuration anywhere in the app, so the
root logger keeps its default level (WARNING) and holds no handlers — Sentry's
integration monkeypatches rather than attaching one. A record below WARNING is
therefore discarded before `logging.lastResort` ever sees it: `logger.info` from
the request path reaches no sink at all. WARNING is the lowest level this sink
carries. It is also honest about what happened — the fast cache lost a bank the
chart needed — and it stays out of Sentry's event stream, which starts at ERROR.

A DURABLE LOOKUP ALONE IS NOT SUCCESS. The receipt fires for every durable-tier
read, because a durable read that served nothing is exactly as interesting as
one that served a chart. `success` is the separate, guarded claim: warm state,
non-zero rows, a bank that dated itself, and no reader-scope refusal. A warm
cache, a missing or expired bank, a refused response and a zero-row response can
none of them set it.

EVERY FIELD IS READ OFF THE BLOCK THE RESPONSE CARRIES. Not recomputed, not
looked up again — the receipt describes the payload that was returned, by
construction, or it describes nothing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: The grep handle. One stable token at the head of the line so a log search can
#: find these without matching the prose of anything else.
RECEIPT_MARKER = "DURABLE-VENUE-SERVE"

#: Bound on the copied refusal reason. The reason is our own short string, but a
#: receipt must never be a channel for unbounded text.
_REASON_MAX = 120

#: Bound on any identifier copied into the receipt. Same reasoning as
#: `_REASON_MAX`, applied to the two values that arrive from the caller.
_IDENT_MAX = 64


def _safe_ident(value: Any) -> Any:
    """A value fit to appear in a log line, whatever the caller handed us.

    Both shipped callers now hand this the LOADED ROW's `market.id` rather than
    their route parameter, so no user-provided value reaches the sink on either
    path (CodeQL `py/log-injection` alert 2981 named exactly those two
    parameters as its sources; the row's column is not one). This narrowing
    stays anyway, and not as decoration: a receipt is a line a person greps, and
    a line a stranger can add newlines to is a line a stranger can forge. The
    guard belongs to the boundary, not to the two call sites that happen to be
    careful today.

    `json.dumps` already escapes control characters, so the forging is not
    reachable TODAY. That is an argument about the current encoder, not about
    the value, and the encoder is not where this guarantee belongs: the next
    caller to log a receipt field without `json.dumps` would inherit the hole
    silently. So the value is narrowed here, at the boundary, once.

    An integer id stays an integer — that is what a market id is, and it is
    unforgeable by construction. Anything else becomes a bounded string with
    control characters removed, which keeps the receipt readable when the id is
    a legitimate non-integer and keeps it to one line when it is not.
    """
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return value
    text = str(value)
    # Drop, rather than escape: a receipt has no use for a control character,
    # and removing them cannot itself introduce one.
    cleaned = "".join(ch for ch in text if ch.isprintable())
    return cleaned[:_IDENT_MAX]


def _reader_scale_refusal(block: dict) -> Optional[str]:
    """The reader-scope refusal this response carries, if it refused one.

    `_GenericVenueHistory.describe` appends `{"scope": "reader", ...}` to the
    refusal list when the reader declined the venue rows on scale grounds, and
    sets the block's state to `refused` at the same time. Read from the block
    rather than taken as a second argument, so the receipt cannot disagree with
    the response about whether rows were refused.
    """
    for refusal in block.get("refusals") or ():
        if not isinstance(refusal, dict) or refusal.get("scope") != "reader":
            continue
        reason = refusal.get("reason")
        return str(reason)[:_REASON_MAX] if reason else "refused"
    return None


def _as_count(value: Any) -> int:
    """A count, or 0 — never a string, never a bool dressed as a number."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def durable_serve_receipt(
    block: Any, *, market_id: Any, surface: str
) -> Optional[dict]:
    """What to write down about this response, or None if no durable tier answered.

    Pure: builds the receipt, decides `success`, touches no logger. The emit half
    is :func:`log_durable_venue_serve`, so the guards can be tested without a
    log sink and the sink can be tested without the guards.
    """
    if not isinstance(block, dict) or block.get("tier") != "durable":
        return None

    from app.utils.db_session_identity import current_build_id

    state = block.get("state")
    built_at = block.get("built_at")
    points = _as_count(block.get("points_served"))
    outcomes = _as_count(block.get("outcomes_served"))
    scale_refused = _reader_scale_refusal(block)
    return {
        "market_id": _safe_ident(market_id),
        "surface": _safe_ident(surface),
        "tier": "durable",
        # The whole claim, in one boolean, under the guards named in the module
        # docstring. `state == "warm"` is what excludes `cold`, `empty`,
        # `refused` and `unavailable` in one predicate — `describe` already
        # rewrites the state to `refused` when the reader refused the scale, so
        # a refused response can never reach this line with `warm`.
        "success": bool(
            state == "warm" and points > 0 and built_at and scale_refused is None
        ),
        "state": state,
        "built_at": built_at,
        "points_served": points,
        "outcomes_served": outcomes,
        "scale_refused": scale_refused,
        # Reported beside the counts, never folded into them: a durable serve
        # that dropped some points is still a durable serve, and a reader of
        # this line must not have to infer that from a smaller number.
        "unsupported_points_withheld": _as_count(
            block.get("unsupported_points_withheld")
        ),
        "fill_status": block.get("fill_status"),
        "build": current_build_id(),
    }


def log_durable_venue_serve(
    block: Any, *, market_id: Any, surface: str
) -> Optional[dict]:
    """Emit the receipt. NEVER raises — instrumentation may not change a response.

    Returns the receipt it wrote (for tests), or None when there was nothing to
    write or when writing failed. The caller ignores the return value: a chart
    that renders is not contingent on a log line, in either direction.
    """
    try:
        receipt = durable_serve_receipt(block, market_id=market_id, surface=surface)
        if receipt is None:
            return None
        logger.warning(
            "%s %s",
            RECEIPT_MARKER,
            json.dumps(receipt, separators=(",", ":"), sort_keys=True, default=str),
        )
        return receipt
    except Exception:  # noqa: BLE001 — a receipt never costs a reader their chart
        try:
            logger.debug("durable venue receipt not written", exc_info=True)
        except Exception:  # noqa: BLE001 — a broken sink is still not the caller's problem
            pass
        return None
