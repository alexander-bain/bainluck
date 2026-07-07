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


def normalize_display_probs(outcomes: list[dict], key: str = "probability") -> None:
    """#23: normalize the displayed distribution in place when independent binary
    outcomes sum >100%. Reuses the SINGLE politics normalizer (percentage-scale)
    via a 0-1 adapter — do not fork it. Values on ``key`` are 0-1 floats."""
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
