"""Whether a market can be rendered as an honest card (#1872 / #1873 / #1874).

Three defects Alex hit in one 2026-08-14 labeling session, which turned out to
share one root and one place to fix it:

* **#1873** — the labeling queue rendered ``proposal.features``, a snapshot
  captured when the proposal was WRITTEN and read back arbitrarily later. A
  months-old snapshot of a since-resolved, since-repriced market is what put
  2024-era copy on a card served today.
* **#1874** — that same card showed every option AND the hero at 100%. Storage
  is clean (0 of 361 sampled markets store all-100%; mean probability sum
  1.147), so the 100%s are introduced at or after read time — a settled
  market's frozen price path replayed out of a stale snapshot is exactly the
  shape that yields 1.0 on every leg.
* **#1872** — 6,984 outcomes across 525 Polymarket markets are named
  ``Person B`` / ``Person K``. Measured against the upstream record, Polymarket
  serves the anonymization ITSELF (``"Will Person K be the next Secretary
  General of the United Nations?"`` comes back that way from the CLOB API), so
  this is not our rewrite collapsing names and cannot be fixed by fixing us.

The unifying rule, and why it lives in one pure module
------------------------------------------------------
**A card must be derived from live state, and a field that cannot be computed
coherently is withheld rather than printed.** (Honest-empty, ruling 027.) The
three defects are one question — *may this be shown?* — asked at three
different surfaces: Discover, the labeling sampler, and the card renderer. A
predicate that lives in one of them gets re-implemented, slightly differently,
in the other two.

Nothing here reaches a database or a network. It takes the live rows a caller
already holds and answers a question about them.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional, Sequence

#: An outcome name that carries no information for a reader: a placeholder
#: label plus a single letter or digit. Deliberately ANCHORED and narrow — it
#: must not catch real names. "Person K" matches; "Person of the Year" does
#: not, and neither does a real surname.
ANONYMIZED_OUTCOME_RE = re.compile(
    r"^\s*(?:person|candidate|option|player|team|entrant|contestant|nominee)"
    r"\s+[A-Z0-9]\s*$",
    re.IGNORECASE,
)

#: Above this, a set of mutually exclusive options cannot be a probability
#: distribution and must not be rendered as one. Chosen to sit well clear of
#: ordinary vig: the measured mean sum across 361 live Polymarket markets is
#: 1.147, and 3.0% exceed 1.5. Kalshi candidate binaries are the known class
#: that blow past it (gotcha #23).
INCOHERENT_FIELD_SUM = 1.5

#: Below this, the field is missing rather than merely wide.
MIN_COHERENT_FIELD_SUM = 0.5


def is_anonymized_outcome_name(name: Optional[str]) -> bool:
    """True for an at-source placeholder like ``Person K`` / ``Candidate 3``."""
    if not name:
        return False
    return bool(ANONYMIZED_OUTCOME_RE.match(str(name)))


def count_anonymized(names: Iterable[Optional[str]]) -> int:
    return sum(1 for n in names if is_anonymized_outcome_name(n))


def is_anonymized_market(names: Sequence[Optional[str]]) -> bool:
    """True when a market's option set is placeholder-shaped.

    The threshold is a MAJORITY rather than all, because a field can be
    partially disclosed ("Trump", "Person B", "Person C") and that card is just
    as unreadable as a fully anonymized one — worse, arguably, since it looks
    like it has real content.

    A market with no outcomes is not anonymized; it is empty, which is a
    different defect with a different owner.
    """
    real = [n for n in names if n is not None and str(n).strip()]
    if not real:
        return False
    return count_anonymized(real) * 2 > len(real)


def _as_prob(value: Any) -> Optional[float]:
    """Coerce a probability, tolerating Decimal/str/None. Never raises."""
    if value is None:
        return None
    try:
        prob = float(value)
    except (TypeError, ValueError):
        return None
    if prob != prob:  # NaN
        return None
    return prob


def field_coherence(probabilities: Iterable[Any]) -> dict[str, Any]:
    """Can these options be shown as a probability field?

    Returns the verdict AND the terms behind it, so a caller can explain a
    withheld field rather than silently dropping it.
    """
    probs = [p for p in (_as_prob(v) for v in probabilities) if p is not None]
    if not probs:
        return {
            "coherent": False,
            "reason": "no_priced_outcomes",
            "sum": None,
            "count": 0,
            "all_certain": False,
        }
    total = sum(probs)
    # The exact shape Alex saw: every leg pinned at ~1.0.
    all_certain = len(probs) > 1 and all(p >= 0.99 for p in probs)
    if all_certain:
        reason = "all_outcomes_certain"
    elif total > INCOHERENT_FIELD_SUM:
        reason = "sum_exceeds_one"
    elif total < MIN_COHERENT_FIELD_SUM:
        reason = "sum_below_one"
    else:
        reason = "coherent"
    return {
        "coherent": reason == "coherent",
        "reason": reason,
        "sum": round(total, 6),
        "count": len(probs),
        "all_certain": all_certain,
    }


def card_defects(
    *,
    outcome_names: Sequence[Optional[str]],
    outcome_probabilities: Sequence[Any],
) -> list[str]:
    """Every reason this market cannot currently be rendered honestly.

    A list rather than a first-match, because "which defect" is the question an
    operator asks after "is it defective", and re-deriving it costs a second
    pass over the same rows.
    """
    defects: list[str] = []
    if is_anonymized_market(outcome_names):
        defects.append("anonymized_outcomes")
    coherence = field_coherence(outcome_probabilities)
    if not coherence["coherent"]:
        defects.append(f"incoherent_field:{coherence['reason']}")
    return defects
