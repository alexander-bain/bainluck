"""The card fingerprint that binds a graded card's READ to the WRITE that grades it.

── THIS MODULE SERVES EVERY SURFACE THAT WRITES A JUDGMENT (#1933) ──────────────

It was born as ``label_pass_card`` in UX-P110, scoped to
``routes/admin_label_pass.py``, and that scoping is the defect #1933 filed:

    "a fix that lives inside one route handler is a fix that the next surface
     will also miss."

It was right. #1873's live-derivation landed in the label-pass route and native —
the surface Alex says he PREFERS — went on grading write-time snapshots for
weeks, because native writes ``RankingJudgment`` through ``admin_judgments.py``
and no import connected the two. Shipping a second drift gate over there would
have reproduced the same shape one layer down, so the gate is here, both routes
call it, and the module is named for the thing rather than for the first screen
that needed it.

** WHAT IS SHARED IS THE DECISION, NOT JUST THE INGREDIENT ** (ruling 021). A
shared hash function under two hand-written policies is still two policies.
``drift_outcome`` below is the policy: three-valued, one implementation, and the
per-surface differences are arguments to it rather than branches inside each
caller.

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

#: The served outcome slice, PER SURFACE, because the two surfaces genuinely
#: render different pictures of the same question: the web label pass prints
#: eight raw outcomes, native prints five display-SCALED ones. The slice is a
#: required argument to ``card_fingerprint`` rather than a module default for
#: exactly that reason — a default is how the third surface silently inherits
#: the first surface's picture and starts refusing verdicts for rows it never
#: showed.
#:
#: Each constant is pinned to the serializer it describes by
#: ``test_graded_card_contract.py``, which reads the real slice out of the real
#: function. A number here that no longer matches what ships is worse than no
#: number at all.
LABEL_PASS_SERVED_OUTCOMES = 8  # admin_label_pass._live_features
NATIVE_SERVED_OUTCOMES = 5  # admin_judgments._serialize_labeling_candidate

#: The client never sent the key at all — distinct from sending it empty.
#: Same sentinel idiom as ``_build_lifecycle_row(posted_generation=...)``.
OMITTED = "__omitted__"


def rendered_percent(probability: Any) -> int | None:
    """The whole-percent integer the surface prints for this probability.

    ``None`` when there is no number to print — and ``None`` is a distinct value
    in the fingerprint, not a zero: "no price" and "0%" are different cards.

    ** NOT ``round()``. ** Python's built-in is banker's rounding — ``round(56.5)``
    is **56** — and the surfaces this claims to mirror are half-up:
    ``Math.round(56.5)`` is **57** on web, and Swift's
    ``(56.5).rounded()`` is **57** on native (``.toNearestOrAwayFromZero``, its
    default rule). The two disagree with Python on exactly the .5 boundary, so a
    card sitting there would render at one percent while the server fingerprinted
    it at another, and the whole argument for this function ("it changes exactly
    when the picture changes") would be false at the only values where it is hard
    to be right.

    Caught by this file's own test, which had asserted the JS answer in a comment
    while expecting the Python one in the assertion. ``floor(x + 0.5)`` is
    ``Math.round`` for the non-negative domain probabilities live in.

    ** THERE ARE NOW THREE RUNTIMES PRINTING THIS NUMBER **, so the boundary is no
    longer a comment: ``contracts/rendered_percent.json`` is the table, and the
    Python, TypeScript and Swift implementations are each driven through every row
    of it (ruling 021 — share the DECISION, not the ingredient). A comment cannot
    keep three runtimes honest; UX-P110 proved that by writing one and getting the
    assertion wrong underneath it.
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
    served_outcomes: int,
) -> str:
    """A short, stable digest of the card as it is rendered.

    ``outcomes`` is the served list of ``{"name", "probability"}`` dicts, in
    served order, or ``None`` when the field was withheld as incoherent. Withheld
    and empty are deliberately different fingerprints: a card that shows "we
    cannot draw this field" is not the same card as one that shows nothing.

    ``served_outcomes`` is the caller's own slice — see the constants above for
    why it has no default.
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
                for o in outcomes[:served_outcomes]
            ]
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


#: What a surface does when the client did not send a fingerprint AT ALL.
#:
#: ── THE ONE PLACE NATIVE IS NOT WEB, AND IT IS NOT A PREFERENCE ──────────────
#:
#: UX-P110 fails closed on an absent fingerprint and gives the reason: the value
#: is minted by the GET in the same request cycle, so any client that read the
#: queue after the deploy has one, and the only way to arrive without it is a tab
#: loaded before the deploy — the exact hazard the gate exists for, remedy a
#: reload.
#:
#: ** THAT ARGUMENT IS ABOUT A PAGE, AND IT DOES NOT SURVIVE THE TRIP TO A
#: BINARY. ** The web client is re-served by this server on every load; the
#: native client is an installed build. Failing closed on native the day this
#: deploys does not ask Alex to reload — it refuses every label from the app
#: already on his phone until he installs a new one, on the surface #1933 records
#: him preferring. A guard whose whole purpose is to protect his label budget
#: cannot begin by voiding all of it.
#:
#: So the native arm binds on a DECLARED capability: a client that sends the key
#: is gated exactly as web is (an empty value is still a refusal — declaring the
#: capability and then not supplying the value is a client bug, not a legacy
#: build). A client that has never heard of the key is written UNBOUND, and
#: unbound is STAMPED ON THE ROW AND COUNTED — never silent, never
#: indistinguishable from a gated write (ruling 086: absence and agreement are
#: different facts, and a store that folds them together cannot report its own
#: coverage). When the gated build is the only one in the field, this flips to
#: ``REFUSE`` and the stamp says exactly when it became safe to.
ABSENT_REFUSE = "refuse"
ABSENT_UNBOUND = "unbound"


# ── WHEN THE NATIVE ARM MAY FLIP TO FAIL-CLOSED (#1933, UX-P112) ─────────────────
#
# The constant above promises the flip happens "when the gated build is the only
# one in the field". That sentence is not checkable, and an uncheckable condition
# is settled by whoever argues hardest on the day. These three numbers make it a
# query.
#
# ** THE LEG THAT IS NOT OBVIOUS IS THE TRAFFIC FLOOR, AND IT IS THE LOAD-BEARING
# ONE. ** "unbound = 0 over N days" is satisfied perfectly by N days in which
# nobody labelled anything — and this exact table contains a 77-day silence
# (2026-05-25 → 2026-08-10). A criterion with only the zero-leg would have been
# passable for eleven straight weeks on no evidence whatsoever. Same class as
# gotcha #53: an empty result is a response shape, not a fact, and the remedy is
# a second signal that says the instrument was pointed at something.
#
#: N. Measured from Alex's real cadence: `ranking_judgments` distinct labelling
#: days run 2026-08-10 → 08-14 → 08-17 → 08-20, i.e. a gap of **3–4 days**. A
#: 14-day window therefore spans three to four separate labelling sessions, so a
#: clean window is a claim about several independent app launches rather than one
#: good night. It is also comfortably longer than the longest recent gap, so a
#: single skipped week cannot satisfy it.
FLIP_WINDOW_DAYS = 14
#: The window must contain real gated traffic. One session is dozens of cards (52
#: rows landed in a single ten-day stretch), so 20 is well inside one session's
#: output while being far above incidental noise.
FLIP_MIN_BOUND = 20
#: …spread across at least three distinct days. One long session cannot retire a
#: build: the old binary is retired by not being *launched*, and a single day
#: observes a single launch.
FLIP_MIN_DAYS = 3


def flip_readiness(
    *,
    bound: int,
    unbound: int,
    distinct_days: int,
    window_days: int = FLIP_WINDOW_DAYS,
) -> dict:
    """Is it safe to flip the native arm from ``unbound`` to ``refuse``?

    Every leg is reported with its own verdict, never folded into one boolean —
    a criterion that answers only "no" tells nobody which leg to go work on, and
    the interesting failure (a quiet window) looks identical to the dangerous one
    (an old build still writing) unless they are named apart.

    Pure. The flip is a decision about a policy constant, so the thing that
    decides it must be provable without a database.
    """
    legs = [
        {
            "leg": "no_unbound_writes",
            "requirement": f"unbound == 0 over the last {window_days}d",
            "observed": unbound,
            "pass": unbound == 0,
            "why": (
                "an unbound write is a client that does not declare the gate — "
                "flipping while one is still writing refuses its labels outright"
            ),
        },
        {
            "leg": "window_had_traffic",
            "requirement": f"bound >= {FLIP_MIN_BOUND}",
            "observed": bound,
            "pass": bound >= FLIP_MIN_BOUND,
            "why": (
                "zero unbound over a silent window is not evidence; this table "
                "has already gone 77 days without a single write"
            ),
        },
        {
            "leg": "traffic_spanned_sessions",
            "requirement": f"distinct labelling days >= {FLIP_MIN_DAYS}",
            "observed": distinct_days,
            "pass": distinct_days >= FLIP_MIN_DAYS,
            "why": (
                "an old build is retired by not being launched, and one day "
                "observes one launch"
            ),
        },
    ]
    return {
        "ready": all(leg["pass"] for leg in legs),
        "window_days": window_days,
        "legs": legs,
        "blocked_on": [leg["leg"] for leg in legs if not leg["pass"]],
        "on_flip": (
            "set on_absent=ABSENT_REFUSE in admin_judgments.create_judgment and "
            "record the date here; the three legs are the evidence it was safe."
        ),
    }


def drift_outcome(
    posted: Any,
    live_fingerprint: str | None,
    *,
    live_card: dict | None = None,
    on_absent: str = ABSENT_REFUSE,
) -> dict:
    """The shared drift decision. Three-valued, one implementation.

    Returns a dict whose ``status`` is one of:

    ``bound``     the posted card is the live card — proceed, and record the
                  fingerprint that was verified.
    ``conflict``  refuse. ``reason`` is ``card_drifted`` or
                  ``card_fingerprint_missing``; ``writes`` is 0.
    ``unbound``   proceed, but the write is NOT gated and says so. Only reachable
                  under ``on_absent=ABSENT_UNBOUND``.

    ** WHY THIS IS A DICT AND NOT A ``None``-MEANS-OK. ** The previous shape
    returned ``None`` for the good case, which reads fine with one caller and
    hides the third outcome from the second. A caller that has to invent
    "unbound" for itself is a caller that will invent it differently — which is
    the whole failure this module is the fix for.

    Pure: the refusal and the non-refusal are both provable without a database.
    """
    live_card = live_card or {}
    summary = {
        "title": live_card.get("title"),
        "status": live_card.get("status"),
        "probability": live_card.get("probability"),
        "field_coherent": live_card.get("field_coherent"),
    }

    if posted == OMITTED:
        if on_absent == ABSENT_UNBOUND:
            return {
                "status": "unbound",
                "reason": "client_did_not_declare_gate",
                "applied": None,
                "expected": live_fingerprint,
                "posted": None,
                "live_card": summary,
            }
        return {
            "status": "conflict",
            "reason": "card_fingerprint_missing",
            "applied": False,
            "writes": 0,
            "expected": live_fingerprint,
            "posted": None,
            "live_card": summary,
        }

    if posted == live_fingerprint and posted:
        return {"status": "bound", "reason": None, "fingerprint": live_fingerprint}

    return {
        "status": "conflict",
        # An empty value from a client that DID send the key is a missing
        # fingerprint, not a drifted one — the reasons steer different words on
        # screen ("reload" vs "it re-priced"), so conflating them tells the
        # reader to do the wrong thing.
        "reason": "card_fingerprint_missing" if not posted else "card_drifted",
        "applied": False,
        "writes": 0,
        "expected": live_fingerprint,
        "posted": posted or None,
        "live_card": summary,
    }


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
