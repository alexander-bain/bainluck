"""The card fingerprint that binds a Label Pass GET to its POST (#1542 / #1873).

── WHY A NEW GUARD WHEN A GET→POST RACE CHECK ALREADY EXISTS ────────────────────

It exists and it cannot fire for this class. ``classify_post`` refuses a verdict
whose ``posted_generation`` disagrees with the proposal's ``proposal_generation``
— but generation is stamped **once, at proposal birth**, and #1542 item 5
deliberately stopped the daily evaluator from ever refreshing it (that refresh was
the "old candidate looks fresh" bug). A value that is written once and never
mutated cannot differ between a GET and the POST that follows it. The generation
check therefore guards **proposal identity**, and nothing guards **card content**.

That gap is the live half of the issue. Between the moment Alex reads a card and
the moment he grades it, the field can re-price, lose coherence, or re-order; the
market stays open, its resolution date stays future, no proposal row is touched,
so every authoritative lifecycle signal still says "actionable" — and the Accept
writes a bounded ±8/−18 term into **live Discover ranking for 14 days** against a
card that no longer exists. Lifecycle staleness and card drift are different
questions and only one of them was being asked.

── THE FINGERPRINT IS OVER THE RENDERED CARD, NOT THE UNDERLYING FLOATS ─────────

This is the load-bearing decision in the file. Hashing raw probabilities would
refuse a verdict every time a poll nudged 0.9200001 → 0.9200004 — a guard that
refuses everything is exactly as useless as one that refuses nothing, and it
would take the label pass down on the night Alex is trying to use it.

So the fingerprint is taken at **the resolution the surface actually renders**.
`frontend/app/admin/label-pass/page.tsx` prints `Math.round(probability * 100)`,
whole percent, so that is the unit here. The consequence is the property worth
having: **the fingerprint changes exactly when the picture changes.** A refusal is
always explicable to the person who was looking at the card, and a re-price too
small to see is not a refusal. Same reasoning as `PROP_TRAVEL_FLOOR` on the prop
rail — the threshold is the surface's own resolution, not a tuned constant.

It covers only what is SERVED: the title, the lifecycle fields on the card, field
coherence, and the served outcome slice in served order. An outcome outside that
slice moving is invisible to Alex, so it must not refuse his verdict.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

#: The served outcome slice. Must match the slice ``_live_features`` renders —
#: fingerprinting more than is shown would refuse verdicts for changes nobody
#: could have seen.
SERVED_OUTCOMES = 8


def rendered_percent(probability: Any) -> int | None:
    """The whole-percent integer the surface prints for this probability.

    ``None`` when there is no number to print — and ``None`` is a distinct value
    in the fingerprint, not a zero: "no price" and "0%" are different cards.

    ** NOT ``round()``. ** Python's built-in is banker's rounding — ``round(56.5)``
    is **56** — and the surface this claims to mirror is JavaScript's
    ``Math.round``, which is half-up: ``Math.round(56.5)`` is **57**. The two
    disagree on exactly the .5 boundary, so a card sitting there would render at
    one percent while the server fingerprinted it at another, and the whole
    argument for this function ("it changes exactly when the picture changes")
    would be false at the only values where it is hard to be right.

    Caught by this file's own test, which had asserted the JS answer in a comment
    while expecting the Python one in the assertion. ``floor(x + 0.5)`` is
    ``Math.round`` for the non-negative domain probabilities live in.
    """
    if probability is None:
        return None
    try:
        return math.floor(float(probability) * 100 + 0.5)
    except (TypeError, ValueError, OverflowError):
        return None


def card_fingerprint(
    *,
    title: str | None,
    status: str | None,
    resolution_date: str | None,
    field_coherent: bool | None,
    outcomes: list[dict] | None,
) -> str:
    """A short, stable digest of the card as it is rendered.

    ``outcomes`` is the served list of ``{"name", "probability"}`` dicts, in
    served order, or ``None`` when the field was withheld as incoherent. Withheld
    and empty are deliberately different fingerprints: a card that shows "we
    cannot draw this field" is not the same card as one that shows nothing.
    """
    payload = {
        "title": title,
        "status": status,
        "resolution_date": resolution_date,
        "field_coherent": field_coherent,
        "outcomes": (
            None
            if outcomes is None
            else [
                [o.get("name"), rendered_percent(o.get("probability"))]
                for o in outcomes[:SERVED_OUTCOMES]
            ]
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


#: How far the write-time reading may have moved and still count as having
#: survived. Queue 355's number, deliberately unchanged: this queue is fixing the
#: absence-read-as-drift bug in the comparison, not re-tuning its tolerance, and
#: quietly moving a neighbouring constant while fixing a defect is how a fix
#: acquires an unowned second change.
MATERIAL_DRIFT = 0.05


def compare_snapshot(snapshot_probability: Any, live_probability: Any) -> str:
    """Three-way comparison of the write-time reading against the live one.

    ── A DIFFERENT BAR FROM THE FINGERPRINT, ON PURPOSE ─────────────────────────

    ``card_fingerprint`` asks "is this the same picture", over the MINUTES of a
    labeling session, and gates a write — so it must be exact at the resolution
    the page renders, and every refusal must be explicable as "the number on
    screen changed". This asks "did a proposal's write-time reading survive",
    over the WEEKS between the evaluator minting it and Alex reaching it, and
    gates nothing — it is a diagnostic. A one-percent wobble is signal to the
    first question and noise to the second (ruling 100: a metric and its early
    warning are different jobs). Two bars, named, rather than one bar serving
    two jobs badly.

    ── WHY THIS IS NOT A BOOLEAN, AND WHY THAT MATTERED ─────────────────────────

    The predicate this replaces returned ``old is not new``, so a snapshot that
    carried **no probability at all** compared unequal to every live reading and
    was counted as drift. Measured on production 2026-08-20: **0 of 39** pending
    snapshots carry a ``probability`` — every one holds exactly ``generation`` and
    ``evidence_generation`` — yet the endpoint reported 33 disagreements and a
    note claiming each was "a card rendered wrong under the old behaviour". It
    could not have been: there was no reading there to render wrong.

    Absence and disagreement are different facts and a gauge that folds them
    together cannot detect drift coming back (ruling 086). Three values, so the
    count that proves the serve half is honest about what it can and cannot see.
    """
    if snapshot_probability is None:
        return "no_reading"
    if live_probability is None:
        return "no_live_reading"
    try:
        old = float(snapshot_probability)
        new = float(live_probability)
    except (TypeError, ValueError):
        return "unreadable"
    return "drifted" if abs(old - new) > MATERIAL_DRIFT else "agrees"
