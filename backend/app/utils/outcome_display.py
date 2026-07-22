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

# Anonymized reserved-slot outcomes. "Team X" only at SINGLE letter — "Team GB"/
# "Team USA" (2+ letters) are real Olympic entrants.
_PLACEHOLDER_FAMILY_RE = re.compile(
    r"^(Player|Person|Candidate|Movie|Nominee)\s+[A-Z]{1,2}$"
)
_PLACEHOLDER_TEAM_RE = re.compile(r"^Team\s+[A-Z]$")
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


def is_placeholder_outcome_name(name: str | None) -> bool:
    """True for anonymized reserved-slot outcomes that must not display."""
    n = (name or "").strip()
    return bool(
        _PLACEHOLDER_FAMILY_RE.match(n)
        or _PLACEHOLDER_TEAM_RE.match(n)
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
    raw_sum = sum((o.get(key) or 0) for o in outcomes)
    if raw_sum > _FIELD_SUM_MAX:
        return  # independent-binary overround — raw YES price is the honest prob
    from app.routes.politics import _normalize_outcome_probs  # shared #23 util

    pct = [{"p": (o.get(key) or 0) * 100} for o in outcomes]
    _normalize_outcome_probs(pct, key="p")
    for o, scaled in zip(outcomes, pct):
        if o.get(key):
            o[key] = round(scaled["p"] / 100, 4)


def leader_pick_order(outcomes: list[dict], name_key: str = "name") -> list[dict]:
    """If a generic Field/Other outcome sorts first (holds plurality), demote it
    below the top NAMED outcome so the answer leads with a real name — the field's
    share stays visible in the list. In place; returns the list."""
    if outcomes and is_field_outcome(outcomes[0].get(name_key, "")):
        named_idx = next(
            (i for i, o in enumerate(outcomes)
             if not is_field_outcome(o.get(name_key, ""))),
            None,
        )
        if named_idx is not None:
            outcomes.insert(0, outcomes.pop(named_idx))
    return outcomes
