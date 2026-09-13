"""Shared outcome-display rules for answer surfaces (search, typeahead, futures
detail). ONE source of truth so the surfaces can't diverge.

#993: the futures DETAIL page showed "Other 100%" while search showed the real
leader ("Cleveland Cavaliers 31%") because each surface had its OWN copy of the
placeholder/normalization/leader-pick logic (search fixed, detail not). A third
divergent copy is exactly how that recurs — so these primitives live here and
both surfaces call them.

Rules:
- placeholder filtering  — anonymized reserved slots ("Team C", "Person B", ...)
- #23 normalization      — independent candidate binaries can sum >100%
- leader-pick            — a generic "Other/Field" outcome never headlines
"""

from __future__ import annotations

import re
from typing import Callable, Sequence, TypeVar

from app.utils.ladder_monotonicity import DEC, cumulative_outcome_ladder

_T = TypeVar("_T")

# Anonymized reserved-slot outcomes. "Team X" only at SINGLE letter — "Team GB"/
# "Team USA" (2+ letters) are real Olympic entrants.
#
# UX-P126/F5 (#1696 display half): `Party`, `Manager`, `Driver` and `Coach` were in
# NO placeholder regex, so 69 markets ranked an enumerated slot as their answer. The
# role list is the ONLY thing that was missing — the letter shape was already right.
#
# The letter bound is A-Z + AA-ZZ, NOT a truncated A-L. Measured in production
# 2026-08-24: the runs go the full distance and then some — Party A..Z plus AA..AF,
# Manager A..Z plus AA..AD, Coach A..T, Driver A..J. A bound that stops at L leaves
# "Coach N" and "Party X" ranking, which is the defect, not a narrower version of the
# fix. ("Coach K" is a real nickname elsewhere; here it is n=2 inside an unbroken
# Coach A..T enumeration, so it is a slot like its 19 siblings.)
_PLACEHOLDER_FAMILY_RE = re.compile(
    r"^(Player|Person|Candidate|Movie|Nominee|Party|Manager|Driver|Coach)"
    r"\s+[A-Z]{1,2}$"
)
_PLACEHOLDER_TEAM_RE = re.compile(r"^Team\s+[A-Z]$")
# Party alone also enumerates NUMERICALLY (measured: "Party 2".."Party 40" in one
# 40-way coalition ladder). Deliberately NOT generalized to the other roles: a
# numbered driver or player is a real identity ("Driver 44"), a numbered party is not.
_PLACEHOLDER_NUMBERED_PARTY_RE = re.compile(r"^Party\s+\d{1,3}$")
# Legacy Polymarket garbage ("player AB", "player ABC") — case-insensitive, up to 3.
_LEGACY_PLAYER_RE = re.compile(r"^player\s+[A-Z]{1,3}$", re.IGNORECASE)
# #993 L2-43: bare 1-2 uppercase-letter opaque codes ("AR", "BF", "W") — the
# Ballon d'Or market is fully anonymized this way (real names not yet ingested,
# Lane-1 #125). ALL-CAPS required so "No"/"Yes" (mixed case) are never caught.
_BARE_CODE_RE = re.compile(r"^[A-Z]{1,2}$")

_FIELD_OUTCOME_RE = re.compile(
    r"^(other|others|the field|field|none( of the above)?|no one( else)?|"
    r"neither|any other|someone else|another|tbd)$",
    re.IGNORECASE,
)

# #1200: independent-binary overround ceiling. A field whose raw YES prices sum
# FAR past 100% is a set of INDEPENDENT candidate binaries (a Kalshi 184-way Tour
# de France GC field sums ~2.8x), NOT a coherent mutually-exclusive field — even
# when it is mis-flagged ``mutually_exclusive=True`` upstream. Above this ceiling
# the raw per-outcome YES price IS the honest win probability and must never be
# squeezed to sum ~100%. Mirrors the event_cycling concept-adapter guard so the
# raw /api/futures/{id} + search surfaces match it (gotcha #23).
_FIELD_SUM_MAX = 1.60

# UX-P126/F5: a field outcome at or above this DISPLAYED probability is never a real
# answer — it is an untraded midpoint or a no-bid ask (gotcha #17/#19), and it must not
# occupy a leader or top-N slot. Evaluated AFTER `normalize_display_probs` so the
# number judged is the number rendered. Deliberately high: a field that genuinely
# carries most of the probability mass (a wide-open 12-way race where "Other" is 55%)
# is INFORMATION and keeps its rank.
_FIELD_DOMINANT_MIN = 0.9


def is_placeholder_outcome_name(name: str | None) -> bool:
    """True for anonymized reserved-slot outcomes that must not display."""
    n = (name or "").strip()
    return bool(
        _PLACEHOLDER_FAMILY_RE.match(n)
        or _PLACEHOLDER_TEAM_RE.match(n)
        or _PLACEHOLDER_NUMBERED_PARTY_RE.match(n)
        or _LEGACY_PLAYER_RE.match(n)
        or _BARE_CODE_RE.match(n)
    )


def is_field_outcome(name: str | None) -> bool:
    """True for generic catch-all outcomes ("Other", "The Field", "None of the
    above") that shouldn't headline an answer even at plurality."""
    return bool(_FIELD_OUTCOME_RE.match((name or "").strip()))


def drop_incoherent_near_certain(
    items: Sequence[_T],
    prob_of: Callable[[_T], float | None],
    *,
    mutually_exclusive: bool,
    market_is_open: bool,
    is_winner_of: Callable[[_T], bool | None] | None = None,
) -> list[_T]:
    """Remove every leg of a single-winner field that is at/above the NEAR-CERTAINTY
    bar when MORE THAN ONE of them is — because then none of them is a real price.

    #4253. The rule is not a new one: ``winner_field_coherence.field_is_incoherent``
    already states it, and capture and grading already obey it. Display is the third
    site, and it never adopted it — which is verbatim the drift this module and that
    one both exist to prevent. The bar and the predicate are IMPORTED, never
    re-derived here, so the three sites cannot disagree about what the defect is.

    NAME-BLIND, and that is the whole difference from
    :func:`drop_dominant_field_outcomes`. That guard is gated on
    ``is_field_outcome(name)``, so it only ever removes a row *called* "Other" or
    "The Field". Measured live 2026-09-09, the rows doing the damage carry perfectly
    real names and walk straight through it:

    * ``/api/futures/12764689`` (*Dancing with the Stars*) — ``Contestant 22 1.0 ·
      Contestant 16 1.0 · Contestant 33 1.0 · Contestant 43 1.0 · Contestant 45 1.0``
    * ``/api/futures/114045`` (*Lead Bank in SpaceX's IPO?*) — ``Goldman Sachs 1.0``
      heading four more banks at 1.0
    * ``/api/futures/113419`` (*Next CEO of Apple?*) — ``John Ternus 1.0``

    Five different candidates, each certain to win the same single-winner prize.

    APPLY THIS TO THE WHOLE FIELD, BEFORE THE SORT AND THE ``[:N]`` SLICE. Both
    failure modes below were measured on the specimens above, and each on its own is
    enough to make a post-slice call do nothing at all:

    * **It under-detects.** ``113419`` holds 22 outcomes of which 19 are frozen at
      1.0, but only ONE survives into the displayed four — so a slice-local count
      sees a single near-certain leg, which is exactly what an honest settled market
      looks like, and the predicate correctly declines to fire.
    * **It self-cancels.** ``12764689`` sorts 50 junk 1.0s above its 2 real legs, so
      every row in the ``[:5]`` slice is junk; dropping them all would empty the
      list, ``NEVER EMPTIES`` returns the input unchanged, and the reader still sees
      five contestants at 100%.

    Judging the RAW price rather than the rendered one is deliberate, and is the
    opposite placement from ``_FIELD_DOMINANT_MIN`` (which is documented as judging
    the number rendered). These legs are why the rendered number is wrong:
    :func:`normalize_display_probs` bails out above ``_FIELD_SUM_MAX`` (#1200), and a
    run of frozen 1.0s pushes the sum there by itself — 12764689's field sums past
    50 — so the whole market renders raw and there is no "rendered" number to judge
    that the junk has not already corrupted. Removing them first is what lets the
    #23 squeeze see a coherent field again, the same reasoning #1201 applies to a run
    of untraded 0.5 midpoints.

    NEVER EMPTIES, matching :func:`drop_dominant_field_outcomes` and
    :func:`display_rank_order`: if every leg is near-certain the input is returned
    unchanged, because an honest-empty decision belongs to the surface and a silent
    zero-outcome card is a worse artifact than a labelled one. Seven markets (100
    rows) are wholly frozen and stay wholly frozen under this rule; they need the
    ingest half, not the display half.

    Non-mutually-exclusive families are never judged, for the reason gotcha #23 and
    #199 give: golf make-cut / top-N legs are simultaneously true and several of them
    are legitimately near-certain at once. The one card on `/api/feed` 2026-09-09
    holding two legs at 0.95 is *Pylon: First Week Pure Album Sales* — ``Above 5K`` /
    ``Above 12K`` / ``Above 20K``, a nested threshold ladder that is flagged
    ``mutually_exclusive = false`` and is correctly refused here.

    TWO EXEMPTIONS, both measured, both load-bearing:

    * **A CROWNED LEG IS NEVER DROPPED.** ``is_winner`` is a settlement, not a quote
      — the same reason ``_retire_unpriced_legs`` (#4000) refuses to touch one. 397
      resolved Polymarket markets and 239 resolved Kalshi markets hold a crowned
      winner at >= 0.95 *beside* another near-certain leg and still have survivors
      below the bar, so a rule without this exemption would delete the actual result
      from every one of them and leave the losers on the page. That is the standing
      "settled means settled" ruling broken by a display helper.
    * **OPEN MARKETS ONLY.** A resolved market that shows several 1.0s and never got
      a winner stamped is the #1527 GRADING defect, which belongs to the grader that
      owns ``winners_are_incoherent`` — not to a display drop that would paper over
      it. 131 resolved markets are in that state and are deliberately left alone.

    Note the asymmetry: a crowned leg still COUNTS toward incoherence detection (one
    real winner plus four frozen 1.0s is exactly the field this is for) but is exempt
    from removal. Detection and suppression are different questions.
    """
    from app.utils.winner_field_coherence import NEAR_CERTAIN_PROB, field_is_incoherent

    kept_all = list(items)
    if not market_is_open:
        return kept_all
    if not field_is_incoherent(
        (prob_of(i) for i in kept_all), mutually_exclusive=mutually_exclusive
    ):
        return kept_all

    def _drop(i: _T) -> bool:
        p = prob_of(i)
        if p is None or float(p) < NEAR_CERTAIN_PROB:
            return False
        return not (is_winner_of(i) if is_winner_of is not None else False)

    kept = [i for i in kept_all if not _drop(i)]
    return kept if kept else kept_all


def normalize_display_probs(
    outcomes: list[dict],
    key: str = "probability",
    mutually_exclusive: bool = True,
) -> bool:
    """#23: normalize the displayed distribution in place when independent binary
    outcomes sum >100%. Reuses the SINGLE politics normalizer (percentage-scale)
    via a 0-1 adapter — do not fork it. Values on ``key`` are 0-1 floats.

    #199: only mutually-exclusive fields (exactly one winner) should be squeezed to
    sum ~100%. Non-mutually-exclusive PARTICIPATION families — golf make-cut /
    top-5 / top-N, where many outcomes are simultaneously true and the set sums to
    several multiples of 100% — must NOT be normalized: doing so squashed an honest
    86%-to-make-the-cut down to ~1% on The Open's detail/ladder rail. Callers pass
    ``mutually_exclusive`` from ``FuturesMarket.mutually_exclusive`` (reliable:
    Kalshi/DataGolf both flag make-cut/top-N False, winner fields True). Default
    True preserves every existing caller (search, awards/tennis/f1/election, etc.).

    #1200: even when flagged ``mutually_exclusive=True``, a field whose RAW YES
    prices sum FAR past 100% (> ``_FIELD_SUM_MAX``) is a set of INDEPENDENT
    candidate binaries (Kalshi 184-way Tour de France GC field ≈ 2.8x), NOT a
    coherent one-winner field. Squeezing that to ~100% dilutes a near-lock leader
    into a false coin-flip (Pogačar 94.5% → 33.6%). Only a coherent (~1.0, mild-
    vig) field gets the #23 squeeze; the overrounded field keeps its raw prices.
    This mirrors the event_cycling concept-adapter guard and now also protects the
    raw /api/futures/{id} detail + search surfaces that only had the flag gate.

    #5835: RETURNS WHETHER THE PRINTED COLUMN ACTUALLY MOVED, because a caller that
    prints a SECOND column of un-squeezed prices beside this one needs to know. The
    answer is MEASURED — the values before against the values after — never
    re-derived from the thresholds, and that is the whole point. The squeeze fires
    only when ``_normalize_outcome_probs`` sees a sum past 105 (``politics.py``), so
    a caller asking "did it fire?" by re-testing ``raw_sum`` here would need to know
    a constant that lives in another module and can be changed without this one
    noticing. Three branches return False for three different real reasons — a
    non-ME family, an overrounded field left raw, and a coherent field already
    summing under the threshold — and a caller only has to care that nothing moved.
    Existing callers ignore the return and are unaffected.
    """
    if not mutually_exclusive:
        return False  # non-ME participation family — raw per-outcome probs are honest

    # #1201: strip Kalshi untraded-midpoint placeholders from a CORRUPTED ME field.
    # An illiquid Kalshi independent-binary field (e.g. the 79-way Super Bowl MVP,
    # market 479) parks every UNTRADED candidate at EXACTLY 0.5 — the bid/ask
    # midpoint with no trades (gotcha #17/#23). Dozens of 0.5s inflate the field
    # sum to ~19.7 (1967%), tripping the #1200 overround guard so the WHOLE field
    # renders RAW and a real 0.265 leader (Drake Maye) shows an absurd 26.5% to win
    # a single-game MVP. Excluding the placeholders first brings the coherent field
    # back into the normalizable band so the real outcomes squeeze sensibly.
    #
    # Predicate is deliberately narrow so nothing else is touched: >=10 outcomes at
    # EXACTLY 0.5 AND a raw sum far past any coherent field (>3). A legitimate 2-way
    # Yes/No coin-flip (2 sides at 0.5) is untouched; a coherent one-winner field
    # (no run of exact-0.5 placeholders, sum near 1.0) is untouched; a genuine
    # independent-binary field like the Tour de France GC (varied prices, no 0.5
    # run) is untouched and still keeps its raw prices via the #1200 guard below.
    half_count = sum(1 for o in outcomes if o.get(key) == 0.5)
    if half_count >= 10 and sum((o.get(key) or 0) for o in outcomes) > 3.0:
        kept = [o for o in outcomes if o.get(key) != 0.5]
        if kept:
            outcomes[:] = kept  # drop the untraded-midpoint placeholders in place

    raw_sum = sum((o.get(key) or 0) for o in outcomes)
    if raw_sum > _FIELD_SUM_MAX:
        return False  # independent-binary overround — raw YES price is the honest prob
    from app.routes.politics import _normalize_outcome_probs  # shared #23 util

    # Snapshotted BEFORE the write-back, so "did it move" is a fact about what the
    # reader is handed rather than a prediction from the thresholds. Values that
    # survive the rounding unchanged (a 0.0005 longshot under a factor of 1.06
    # rounds back to 0.0005 at 4dp) correctly count as NOT moved: the printed
    # number is the raw price and there is nothing for a second column to disagree
    # with. `any` is the right quantifier — one moved row is one false comparison.
    before = [o.get(key) for o in outcomes]
    pct = [{"p": (o.get(key) or 0) * 100} for o in outcomes]
    _normalize_outcome_probs(pct, key="p")
    for o, scaled in zip(outcomes, pct):
        if o.get(key):
            o[key] = round(scaled["p"] / 100, 4)
    return any(b != o.get(key) for b, o in zip(before, outcomes))


def leader_pick_order(
    outcomes: list[dict], name_key: str = "name", prob_key: str = "probability"
) -> list[dict]:
    """If a generic Field/Other outcome sorts first (holds plurality), demote it
    below the top NAMED outcome so the answer leads with a real name — the field's
    share stays visible in the list. In place; returns the list.

    UX-P126/F5: a one-slot demotion is not enough when the field outcome is priced
    at a DOMINANT ``>= _FIELD_DOMINANT_MIN``. Measured live 2026-08-24 on
    ``/api/futures/16631690`` ("2027 Pro Football Draft: 1st Overall Pick"): a real
    leader (Byrum Brown, 47.5%) headlined correctly, and "Other" at 100% sat one slot
    below it at served position 2 — inside every top-N the card renders. A field
    outcome at ~100% is an untraded/no-bid artifact, never a real answer, so it goes
    to the END of the list rather than one rung down.
    """
    demote_dominant_field(outcomes, name_key=name_key, prob_key=prob_key)
    if outcomes and is_field_outcome(outcomes[0].get(name_key, "")):
        named_idx = next(
            (i for i, o in enumerate(outcomes)
             if not is_field_outcome(o.get(name_key, ""))),
            None,
        )
        if named_idx is not None:
            outcomes.insert(0, outcomes.pop(named_idx))
    return outcomes


def demote_dominant_field(
    outcomes: list[dict], name_key: str = "name", prob_key: str = "probability"
) -> list[dict]:
    """Move every field outcome priced ``>= _FIELD_DOMINANT_MIN`` to the END, in
    place. Dict-shaped wrapper over :func:`display_rank_order`."""
    outcomes[:] = display_rank_order(
        outcomes,
        lambda o: o.get(name_key, ""),
        lambda o: o.get(prob_key),
        drop_placeholders=False,
    )
    return outcomes


def drop_dominant_field_outcomes(
    items: Sequence[_T],
    name_of: Callable[[_T], str | None],
    prob_of: Callable[[_T], float | None],
) -> list[_T]:
    """Remove field outcomes priced ``>= _FIELD_DOMINANT_MIN`` from a list that is
    about to be SLICED and SCALED into a card.

    UX-P163. :func:`display_rank_order` DEMOTES such a row to the end rather than
    deleting it, deliberately — "the field's share stays visible" is asserted by
    ``test_other_at_100_leaves_the_top_n`` and must not change. But demotion only
    keeps the row out of a top-N slot while the list is LONGER than N, and a card
    slices ``[:3]`` off a list the placeholder filter has already shortened. On
    ``/api/feed`` 2026-08-29, market 112903 ("Which party will win the House in
    2026?") reached this point as exactly three rows — ``Democratic Party 0.855``,
    ``Republican Party 0.145``, and a demoted ``Other 1.0`` — so "the end" was still
    inside the card, and this module's own stated rule ("must not occupy a leader or
    top-N slot") was not achieved by ordering alone.

    Worse than the wasted row: that ``Other`` is a no-bid ask (measured bid
    ``0.0000`` / ask ``1.0000``, gotcha #17/#19), and its 1.0 was still counted in
    ``_feed_display_scale``'s divisor. The three surviving rows summed to exactly
    2.0 — the inclusive top of the normalization band — so EVERY number the card
    printed was halved, and Discover rendered ``Democratic Party 43%`` against a
    book price of 85.5% that the market page was showing at the same moment.
    Removing the row that is "never a real answer" from the card is what makes the
    divisor honest; the halving is a symptom of counting it, not a separate bug.

    NEVER EMPTIES, for the same reason :func:`display_rank_order` does not: if every
    item is a dominant field outcome the input is returned unchanged, because an
    honest-empty decision belongs to the surface and a silent zero-outcome card is a
    worse artifact than a labelled one.
    """
    kept = [
        i
        for i in items
        if not (
            is_field_outcome(name_of(i)) and (prob_of(i) or 0) >= _FIELD_DOMINANT_MIN
        )
    ]
    return kept if kept else list(items)


# ── CUMULATIVE LADDERS (#4610) ──
#
# A "cumulative" ladder is a set of outcomes on ONE nested condition: "Above 52",
# "Above 58", "Above 67" … Each rung's event CONTAINS the next one's, so
# ``P(Above 67) <= P(Above 58)`` is not a convention, it is arithmetic. A set
# that breaks it is telling the reader two things that cannot both be true.
#
# THE LAW AND ITS GRAMMAR ARE NOT REDEFINED HERE. Both live in
# :mod:`app.utils.ladder_monotonicity` (CAL-P134/136), which already owns the
# containment argument, the leg grammar, and the discriminator that keeps a
# mutually EXCLUSIVE band set ("29,900 to 29,999.99", "Exactly 3.64%") out of
# it — bands partition rather than nest and may be priced in any order, so a
# favorite is a real thing on a band set and a category error on a ladder. A
# second copy of that grammar in a display module is exactly the third-divergent-
# copy failure this module was created for (#993). What is added here is the two
# things a DISPLAY caller needs and a census does not: a tolerance, and an answer
# to "which rung is the wrong one".
_LADDER_MONOTONE_TOLERANCE = 0.02

# WHY A DISPLAY FILTER REFUSES LESS THAN THE LAW. `monotonicity_violations` is
# strict: any reversal is a reversal, which is correct for a census counting
# contradictions. A card is a different question — it drops a bar the reader was
# going to be shown, and a rung that dips half a cent under its neighbour is
# bid/ask noise, not something a reader can see is impossible. Measured on
# production 2026-09-09 across the 12 cumulative ladders served in
# `GET /api/feed?limit=100`: the reader-visible breaks run 6 to 57 points
# (Netflix "Above 67" 94% over an 80.5% floor, Hulu "Above 79" 95.5% over 38%),
# while the smallest strict reversal in the same population is 0.5 of a point
# ("Qwen market share", 16.0% -> 16.5%). Two points refuses every break a reader
# could catch and keeps every rounding artifact on the card.

# Below this many priced rungs, nothing is dropped. With two rungs a reversal is
# real but UNATTRIBUTABLE — either price could be the wrong one — and dropping
# the arbitrary half of a contradiction is worse than showing both.
_LADDER_MIN_PRICED_RUNGS = 3


def incoherent_ladder_verdict(
    items: Sequence[_T],
    name_of: Callable[[_T], str | None],
    prob_of: Callable[[_T], float | None],
) -> tuple[set[int], int]:
    """``(positions to drop, how many priced rungs the ladder had)``.

    The second half is the part a caller that filters UPSTREAM cannot recover
    afterwards, and CERT-2451 is the cost of not returning it: once the drop has
    happened the survivors are coherent by construction, so nothing downstream
    can tell a two-rung ladder from the one rung left of a six-rung one. See
    :func:`ladder_treatment_collapsed`.

    Everything else about the verdict is documented on
    :func:`incoherent_ladder_indexes`, which is this function's first half.
    """
    # The rows handed to the law are throwaway dicts carrying the caller's
    # POSITION, not its label: a leg is identified by where it sits in `items`,
    # never by its name, which two rows of one list are free to repeat.
    ladder = cumulative_outcome_ladder(
        [{"name": name_of(item) or "", "index": index} for index, item in enumerate(items)]
    )
    if ladder is None:
        return set(), 0
    legs, direction = ladder

    ordered: list[tuple[float, float, int]] = []
    for value, leg in legs:
        index = int(leg["index"])  # type: ignore[call-overload]
        probability = prob_of(items[index])
        if probability is None:
            continue
        ordered.append((value, float(probability), index))
    ordered.sort(key=lambda rung: rung[0])

    if len(ordered) < _LADDER_MIN_PRICED_RUNGS:
        return set(), len(ordered)

    # Longest coherent run, O(n^2) over a list a market's outcome count bounds.
    # `bound` is the run's running EXTREME rather than its previous element:
    # compared pairwise only, a run could drift by the tolerance at every step
    # and end up contradicting its own first rung.
    falling = direction == DEC
    best_length = [1] * len(ordered)
    bound = [probability for _, probability, _ in ordered]
    previous: list[int | None] = [None] * len(ordered)
    for i in range(len(ordered)):
        probability = ordered[i][1]
        for j in range(i):
            if falling:
                fits = probability <= bound[j] + _LADDER_MONOTONE_TOLERANCE
                carried = min(bound[j], probability)
            else:
                fits = probability >= bound[j] - _LADDER_MONOTONE_TOLERANCE
                carried = max(bound[j], probability)
            if not fits:
                continue
            # Longest first; among equals the most permissive bound, so the run
            # that survives is the one a later rung can still join.
            better_length = best_length[j] + 1 > best_length[i]
            same_length_looser_bound = best_length[j] + 1 == best_length[i] and (
                carried > bound[i] if falling else carried < bound[i]
            )
            if better_length or same_length_looser_bound:
                best_length[i] = best_length[j] + 1
                bound[i] = carried
                previous[i] = j

    end = max(range(len(ordered)), key=lambda i: best_length[i])
    coherent: set[int] = set()
    cursor: int | None = end
    while cursor is not None:
        coherent.add(ordered[cursor][2])
        cursor = previous[cursor]

    return (
        {index for _, _, index in ordered if index not in coherent},
        len(ordered),
    )


def incoherent_ladder_indexes(
    items: Sequence[_T],
    name_of: Callable[[_T], str | None],
    prob_of: Callable[[_T], float | None],
) -> set[int]:
    """Positions in ``items`` whose price contradicts their own cumulative ladder.

    Returns an EMPTY set unless
    :func:`app.utils.ladder_monotonicity.cumulative_outcome_ladder` says the
    outcomes are one nested ladder, so a band set, a mixed set, a two-tail set
    and a set with no comparator legs all come back untouched.

    Which rungs are named is not "everything that dips": the answer is the
    complement of the LONGEST run that IS coherent. Take a ladder priced 93.5% /
    73% / 37% / 2% / 24% / 8.5% / 3.5% up its rungs. A scan that flags every rung
    sitting above its predecessors' floor blames the last three — three prices
    that agree with each other and with everything below them — and leaves the
    one broken rung (the 2%) standing as the ladder's own definition of the
    truth. Keeping the longest coherent run names the 2%, and on the two
    production cards this was written for it names "Above 67" (Netflix) and
    "Above 94.609" (USDINR): the rungs those cards were headlined by.
    """
    return incoherent_ladder_verdict(items, name_of, prob_of)[0]


# How many rows the reader's card needs to show a FIELD rather than an answer.
# Not a display taste: `FuturesCard.tsx` draws the heatmap only on
# `heatmapRows.length >= 2` and falls through past the distribution branch to a
# plain leader card below it, so a one-rung "ladder" is not a smaller ladder —
# it is a card with its field deleted (the UX-P008 failure).
#
# PUBLIC because it is the same number at three sites and they must not drift
# (CERT-2456): the refusal here, the classifier's decision to serve the refused
# ladder as `outcome_distribution` instead, and that format's leaf gate in
# `FuturesCard.tsx`. A refusal that the renderer will not honour hides the field
# just as completely as the heatmap it refused.
LADDER_MIN_DRAWN_RUNGS = 2


def ladder_treatment_collapsed(
    items: Sequence[_T],
    name_of: Callable[[_T], str | None],
    prob_of: Callable[[_T], float | None],
) -> bool:
    """True when dropping the incoherent rungs leaves too few to draw a ladder.

    CERT-2451. :func:`drop_incoherent_ladder_outcomes` deliberately never
    empties, so a serializer that filters and hands the survivors on presents
    the classifier with a coherent ladder of one rung — indistinguishable from a
    market that only ever had one. The classifier then re-emits
    ``threshold_heatmap`` (a group or canonical key is enough), the frontend
    needs two rows, finds one, and the whole field disappears.

    So the caller that owns the drop asks this question BEFORE it drops, and
    carries the answer to the classifier. Measured on the grader's specimen —
    ``Above 10`` .20 / ``Above 20`` .90 / ``Above 30`` .95 — the coherent run is
    ``Above 10`` alone, and this returns True.
    """
    incoherent, priced_rungs = incoherent_ladder_verdict(items, name_of, prob_of)
    if not incoherent:
        return False
    return priced_rungs - len(incoherent) < LADDER_MIN_DRAWN_RUNGS


def drop_incoherent_ladder_outcomes(
    items: Sequence[_T],
    name_of: Callable[[_T], str | None],
    prob_of: Callable[[_T], float | None],
) -> list[_T]:
    """Remove the rungs :func:`incoherent_ladder_indexes` names.

    #4610. A price that cannot be true is not evidence: it may not be a card's
    leader, its mover, its surprise, or a bar the reader is asked to read. On
    production 2026-09-09 the Discover card "Netflix App Downloads in September"
    served ``P(Above 67) = 94%`` over ``P(Above 58) = 88%``, and that single rung
    generated all four of the card's reasons (``major_movement_24h``,
    ``leader_change``, ``rank_shakeup``, ``major_surprise``), its headline "New
    favorite: Above 67 (94%)", its caption, and the score that put it on page
    one at position 20 of 100.

    NEVER EMPTIES, matching :func:`drop_dominant_field_outcomes`: an
    honest-empty decision belongs to the surface, not to a filter.

    AND NEVER ATTRIBUTES WHAT IT CANNOT ATTRIBUTE (CERT-2451). If removing the
    incoherent rungs would leave fewer than two, every priced rung contradicts
    every other one and "which rung is the wrong one" has no answer — the
    surviving rung is whichever the longest-run tie-break happened to reach.
    That is the same argument ``_LADDER_MIN_PRICED_RUNGS`` already makes for a
    two-rung reversal, one step further out, so it gets the same answer: drop
    NOTHING and let the caller refuse the ladder TREATMENT via
    :func:`ladder_treatment_collapsed`. The field the reader was going to be
    shown survives; only the bars, which are where the contradiction is legible,
    do not. Measured 2026-09-09 on `GET /api/feed?limit=250`: of the 11 served
    cumulative ladders, 2 lose a rung and **0** collapse — this is a defensive
    path, not a population.
    """
    incoherent, priced_rungs = incoherent_ladder_verdict(items, name_of, prob_of)
    if not incoherent:
        return list(items)
    if priced_rungs - len(incoherent) < LADDER_MIN_DRAWN_RUNGS:
        return list(items)
    kept = [item for index, item in enumerate(items) if index not in incoherent]
    return kept if kept else list(items)


def display_rank_order(
    items: Sequence[_T],
    name_of: Callable[[_T], str | None],
    prob_of: Callable[[_T], float | None],
    drop_placeholders: bool = True,
) -> list[_T]:
    """Order any outcome-shaped sequence so nothing UNRANKABLE holds a leader or
    top-N slot: anonymized placeholders are dropped, and a field outcome priced
    ``>= _FIELD_DOMINANT_MIN`` is pushed to the end.

    Accessor-based rather than key-based so the FEED can call it on ORM rows — the
    feed builds ``top_outcomes`` off raw ``sorted_outcomes`` and never went through
    this module, which is exactly the third-divergent-copy failure #993 was about.

    NEVER EMPTIES and never reorders into nothing: if every item is a placeholder,
    or every item is a dominant field outcome, the input order is returned unchanged.
    An honest-empty decision belongs to the surface, not to a sort helper — and a
    silent zero-outcome card is a worse artifact than a labelled one.
    """
    kept = list(items)
    if drop_placeholders:
        real = [i for i in kept if not is_placeholder_outcome_name(name_of(i))]
        if real:
            kept = real

    dominant = {
        n
        for n, i in enumerate(kept)
        if is_field_outcome(name_of(i)) and (prob_of(i) or 0) >= _FIELD_DOMINANT_MIN
    }
    if not dominant or len(dominant) == len(kept):
        return kept
    return [i for n, i in enumerate(kept) if n not in dominant] + [
        kept[n] for n in sorted(dominant)
    ]
