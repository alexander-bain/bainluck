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


def normalize_display_probs(
    outcomes: list[dict],
    key: str = "probability",
    mutually_exclusive: bool = True,
) -> None:
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
    """
    if not mutually_exclusive:
        return  # non-ME participation family — raw per-outcome probs are honest

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
        return  # independent-binary overround — raw YES price is the honest prob
    from app.routes.politics import _normalize_outcome_probs  # shared #23 util

    pct = [{"p": (o.get(key) or 0) * 100} for o in outcomes]
    _normalize_outcome_probs(pct, key="p")
    for o, scaled in zip(outcomes, pct):
        if o.get(key):
            o[key] = round(scaled["p"] / 100, 4)


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
