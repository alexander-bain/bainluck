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


# ── THE TWO SIDES OF ONE QUESTION MUST SUM TO ONE HUNDRED (#2060) ────────────────
#
# `rendered_percent` above is correct and was never the bug. The bug is applying it
# TWICE to one question and printing both answers.
#
# Alex's card, from his 08-20 gold session (market 59183794):
#
#     Los Angeles D   0.925  ->  93
#     Colorado        0.075  ->   8      93 + 8 = 101
#
# Neither rounding is wrong. Kalshi quotes a complement pair on a HALF-CENT grid,
# so `p * 100` lands on `.5` for **both sides at once**, and half-up — the rule this
# module exists to pin — rounds both up. Measured on production 2026-08-21:
# **10,198 of 21,524** open two-outcome markets render a sum other than 100, and
# 8,982 of those are 101 against only 318 at 99. A 28:1 skew is not noise; it is one
# systematic cause.
#
# ** WHY A BAND, AND WHY THIS BAND. ** Two outcomes are not automatically two sides
# of one question. Measured over the same population, two-outcome field sums run from
# 0.001 to 2.0, and normalizing a field that sums to 0.001 would invent a probability
# rather than round one. But the distribution is not flat: **19,564 of 21,410 (91.4%)
# sit in (0.99, 1.01]**, and 1.01 is already this codebase's own answer to "is this a
# true binary" — `card_integrity.display_scale` uses exactly that threshold, and only
# for two-outcome cards. So the band here is that constant made SYMMETRIC. The
# asymmetry was itself half the defect: a pair summing to 0.99 rendered 99 and nothing
# in the system considered that a problem.
#
# `field_coherence`'s [0.5, 1.5] band is deliberately NOT reused. It answers "can this
# be drawn as a field at all", which is a different and much looser question — under
# it a pair summing to 1.49 would be normalized, and that is fabrication.
#
#: A two-outcome field is a complement pair when its members sum into this band.
#: Outside it the card is not claiming to be two sides of one question, the invariant
#: does not apply, and the values are rendered independently and left alone.
COMPLEMENT_MIN = 0.99
COMPLEMENT_MAX = 1.01


def is_complement_pair(probabilities: list[Any] | None) -> bool:
    """Are these exactly two priced sides of one question?

    Pure, and deliberately strict: exactly two entries, both priced, summing into
    ``[COMPLEMENT_MIN, COMPLEMENT_MAX]``. Anything else is False, because the cost
    of a false positive here is a fabricated percentage point on a card Alex grades.
    """
    if not probabilities or len(probabilities) != 2:
        return False
    try:
        values = [float(p) for p in probabilities if p is not None]
    except (TypeError, ValueError):
        return False
    if len(values) != 2:
        return False
    total = values[0] + values[1]
    return COMPLEMENT_MIN <= total <= COMPLEMENT_MAX


def rendered_card_percents(probabilities: list[Any] | None) -> list[int | None]:
    """The whole percents a surface prints for ONE CARD's served outcomes.

    This is the card-level decision that `rendered_percent` is the ingredient of
    (ruling 021 — share the DECISION, not the ingredient). Every surface prints a
    CARD, not a lone probability, so the card is the unit that has to be shared, or
    three runtimes agree perfectly about each number and still disagree about the
    sum.

    ** COMPLEMENT PAIRS ARE NORMALIZED, ROUNDED ONCE, AND DERIVED. ** For a pair the
    steps are: divide both by their true total (removing the vig SYMMETRICALLY rather
    than dumping all of it on one side), round the **leader** with `rendered_percent`,
    and derive the other as ``100 - leader``. Both halves of #2060's requested fix,
    composed — normalize pre-rounding AND round once.

    ``probabilities`` is in **SERVED ORDER**, and index 0 is the card's headline: it
    is what `rendered_probability` reports and the first number Alex reads. So index 0
    is the value that survives untouched and index 1 absorbs the derivation. Both
    serializers sort descending before calling, so the headline is also the leader.

    Everything that is not a complement pair is rendered exactly as before, one
    `rendered_percent` per outcome. That direction is asserted by the invariant tests
    as explicitly as the fixed direction is — a cap whose guard only proves it fires
    is how the Sports tab got emptied (gotcha #43).
    """
    if not probabilities:
        return []
    if not is_complement_pair(probabilities):
        return [rendered_percent(p) for p in probabilities]

    total = float(probabilities[0]) + float(probabilities[1])
    leader = rendered_percent(float(probabilities[0]) / total)
    if leader is None:  # unreachable for a priced pair; never guess on the way out
        return [rendered_percent(p) for p in probabilities]
    return [leader, 100 - leader]


# ── WHY A CARD'S TWO NUMBERS DO NOT ADD UP (#2088) ───────────────────────────────
#
# `rendered_card_percents` fixed the pair that SHOULD total 100 and deliberately left
# alone the pair that should not. That was right — normalizing a pair summing to 0.97
# would invent three points of probability rather than round one — but it shipped the
# reader a card reading `57 / 40` with nothing on it saying why, which is
# indistinguishable from the `93 / 8` bug it had just fixed. INT-104 measured UX-P113's
# own deploy check at **17 of 18** and filed #2088 for exactly that: *an unexplained
# non-100 is the defect; a labelled one is a fact.*
#
# ** RE-MEASURED ON PRODUCTION 2026-08-29 ** over the same endpoint the issue used
# (`/api/admin/ranking-judgments/candidates?limit=100`): 100 cards, **18 two-outcome,
# 17 summing to 100, 1 summing to 99** — `Diane Parry vs Ann Li: Set 2 Winner`, served
# `[51, 48]`. A different market from the filed exemplar and the same shape: the two
# sides of one tennis set, quoted independently, landing just UNDER the band. The
# class is live and it is not the filed row, so it is a population and not an anecdote.
#
# ** THE REASON IS NOT AN ILLIQUIDITY MARK, AND THAT WAS CHECKED RATHER THAN ASSUMED. **
# `utils/market_liquidity.grade_liquidity` is the obvious thing to reach for — #2088's
# own text calls this "the source-disagreement / illiquidity class" and UX-P157/158 had
# just built a graded mark for it. On the filed exemplar it returns **`traded`**: the
# book is `0.55 / 0.59`, a four-cent spread against a `0.57` midpoint, nowhere near
# `ask - bid >= midpoint`; and `volume_updated_at` is not written on this population at
# all, so the volume fact is not even checkable. Drawing a thinness mark here would be
# a verdict that module explicitly refuses to reach, invented on a surface where Alex
# grades. The honest reason is the arithmetic one, and it needs no book: these are two
# INDEPENDENTLY QUOTED sides, not two halves of one question.
#
# ** SCOPE, STATED SO A LATER QUEUE DOES NOT WIDEN IT BY ACCIDENT: two outcomes only. **
# A three-outcome field totalling 97 is the independent-binary class (gotcha #23) and
# already has its own machinery — `field_coherence` decides whether it may be drawn at
# all, and `feed._feed_display_scale` decides its basis. Handing it this reason would be
# a different ruling rather than this one implemented, and it would put an explanation
# on a large share of Discover at a moment when the density of the liquidity mark is
# itself an open question with Alex. Arity other than two returns `None` — and `None`
# here means "this card makes no claim about a total", never "checked and fine".

#: A served outcome has no price at all, so there is no total to check.
SUM_UNPRICED_OUTCOME = "unpriced_outcome"
#: Both sides are priced and the pair is outside the complement band — the venue is
#: quoting two independent questions, so the total is whatever the two books say.
SUM_INDEPENDENT_PRICES = "independent_prices"


def card_sum(probabilities: list[Any] | None) -> int | None:
    """The integer total a surface actually prints for one card, or ``None``.

    ``None`` when the card prints no number at all. An unpriced outcome contributes
    nothing rather than a zero — "no price" and "0%" are different cards, the same
    distinction `rendered_percent` draws — so a `[57, None]` card totals 57 and is
    explained by `card_sum_reason` rather than silently reported as a 43-point miss.
    """
    percents = [p for p in rendered_card_percents(probabilities) if p is not None]
    if not percents:
        return None
    return sum(percents)


def card_sum_reason(probabilities: list[Any] | None) -> str | None:
    """Why this card's printed percents do not total 100, or ``None`` if they do.

    Pure, and taken over `rendered_card_percents` rather than over the raw floats, so
    it answers for **the picture** — the same discipline `card_fingerprint` is built
    on. A complement pair is normalized, rounded once and derived, so it totals 100 by
    construction and can never earn a reason; that direction is asserted as explicitly
    as the firing one, because a guard that only proves it fires is how the Sports tab
    got emptied (gotcha #43).

    ``None`` is returned for any arity other than two — see the scope note above. It
    means "no claim about a total is being made here", not "checked and fine", and the
    surfaces must not render it as a clean bill of health.
    """
    if not probabilities or len(probabilities) != 2:
        return None
    percents = rendered_card_percents(probabilities)
    if any(p is None for p in percents):
        return SUM_UNPRICED_OUTCOME
    if sum(percents) == 100:
        return None
    return SUM_INDEPENDENT_PRICES


# ── THE SAME QUESTION, IN FIXED POSITIONS INSTEAD OF SORTED ORDER (UX-P114) ──────
#
# `rendered_card_percents` above assumes SERVED ORDER, where index 0 is the headline
# because both labeling serializers sort descending before calling it. The Discover
# EVENT card does not sort: it prints the away side on the left and the home side on
# the right, always, because those positions carry meaning a probability ranking
# would destroy.
#
# It is nonetheless the most exact complement pair in the product. `routes/feed.py`
# derives the away side as `round(1.0 - current_home_prob, 6)`, so the two numbers on
# a game card sum to one BY CONSTRUCTION — and the double-rounding defect therefore
# fires on a fixed, provable condition: whenever `home * 100` lands exactly on `.5`,
# both sides round up and the card prints 101. It can never print 99. (Let
# `home*100 = n + f`. `f == 0.5` gives `(n+1) + (100-n)`; every other `f` gives 100.)
#
# ** MEASURED ON PRODUCTION 2026-08-21 ** over the 414 scheduled/live events inside
# the feed's own window, with the blend computed by `compute_aggregate_probability`
# itself rather than approximated: **34 (8.2%) render a sum of 101**, all 101, none
# 99. Among them Green Bay Packers @ Denver Broncos (33 + 68), Toronto FC @ Inter
# Miami CF (50 + 51), Cremonese @ Empoli (41 + 60), and eight UFC bouts. The blend is
# a weighted MEDIAN, so it frequently IS one source's exact reading — and a Kalshi or
# sportsbook half-cent quote lands the median on the `.5` grid, which is the same
# systematic cause #2060 measured on the labeling card.
#
# ** THE DERIVED POINT GOES ON THE UNDERDOG. ** A duel has no served order to inherit
# a headline from, so the rule that replaces it is the one `rendered_card_percents`
# was written to express: the number a reader anchors on survives untouched, and the
# side nobody is quoting absorbs the derivation. Positional order (always "away
# first") would instead move the favourite's number half the time, which is the one
# number on a game card that anybody checks.


def rendered_duel_percents(
    away_probability: Any, home_probability: Any
) -> list[int | None]:
    """The two whole percents a game card prints, returned as ``[away, home]``.

    The positional wrapper over `rendered_card_percents` — same band, same
    normalize-round-derive, no second constant. The favourite is handed in at index
    0 so it is the value that survives, and the result is mapped back into away/home
    order for the caller.

    Anything that is not a complement pair (a missing side, a pair that does not sum
    into the band) is rendered independently, exactly as before.
    """
    pair = [away_probability, home_probability]
    if not is_complement_pair(pair):
        return [rendered_percent(away_probability), rendered_percent(home_probability)]

    away = float(away_probability)
    home = float(home_probability)
    if away >= home:
        return rendered_card_percents([away, home])
    home_pct, away_pct = rendered_card_percents([home, away])
    return [away_pct, home_pct]


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

    ** THE DIGEST IS TAKEN OVER `rendered_card_percents`, NOT `rendered_percent`. **
    This module's load-bearing promise is that "the fingerprint changes exactly when
    the picture changes", and after #2060 the picture of a two-outcome card is no
    longer one independent rounding per side. Fingerprinting the per-outcome value
    while the surface prints the derived one would break that promise at precisely
    the boundary the complement rule exists for: the server would expect 93/8, every
    client would show 93/7, and every verdict on a Kalshi binary would be refused for
    a drift nobody could see. The slice is taken FIRST so the pair rule is applied to
    what is served rather than to what exists.
    """
    served = None if outcomes is None else outcomes[:served_outcomes]
    percents = (
        None
        if served is None
        else rendered_card_percents([o.get("probability") for o in served])
    )
    payload = {
        "title": title,
        "status": status,
        "resolution_date": resolution_date,
        "field_coherent": field_coherent,
        "outcomes": (
            None
            if served is None
            else [[o.get("name"), percents[i]] for i, o in enumerate(served)]
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
