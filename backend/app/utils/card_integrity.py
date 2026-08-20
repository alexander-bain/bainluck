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

#: Above this, the options are NOT mutually exclusive and must not be
#: normalized: "rank 3+", "rank 4+", "market cap above $1T / $1.2T / …" are
#: cumulative thresholds whose probabilities are each meaningful on their own.
#: Dividing by their sum flattens an 81% leader to ~33%. Mirrors the served
#: feed's `_feed_display_scale` cutoff exactly (`app/routes/feed.py`).
INDEPENDENT_BINARY_MAX_SUM = 2.0

#: An unfilled template blank in a market NAME — Polymarket's group-parent
#: shells arrive as "SpaceX IPO closing market cap above ___ ?" while the real
#: thresholds live in the sub-markets sharing their `group_id`. A title with a
#: blank in it cannot be read, ranked, or labelled no matter how good its
#: prices are, so this is a defect of the CARD, not of its field.
UNFILLED_TEMPLATE_RE = re.compile(r"_{2,}")


def has_unfilled_template(name: Optional[str]) -> bool:
    """True for a market name still carrying its template blank (`___`)."""
    if not name:
        return False
    return bool(UNFILLED_TEMPLATE_RE.search(str(name)))


def display_scale(probabilities: Iterable[Any], displayed_count: int = 3) -> float:
    """The divisor every visible probability on a card must share.

    THE POINT OF THIS FUNCTION IS THAT IT IS THE SAME ANSWER THE FEED GIVES.

    `field_coherence` answers *"can these be shown as a distribution?"* and
    calls a sum over 1.5 incoherent — which is true and, taken alone, wrong
    about what to do next. The served feed's answer to "these are not a
    distribution" is not to withhold; it is to stop treating them AS one:

      sum <= threshold            -> raw, already sane
      threshold < sum <= 2.0      -> independent binaries, divide by the sum
      sum > 2.0                   -> cumulative thresholds, show RAW, each
                                     probability is meaningful on its own

    Measured 2026-08-19: the labeling sampler withheld a probability on **21 of
    40** sampled cards, ranks #1/#2/#3 among them, and **all 21 sat in the
    sum > 2.0 band** — the band the feed renders raw. `Ballon d'Or Winner 2026`
    (sum 59.0) is fifty-nine independent "will X win?" binaries, each perfectly
    readable; Discover shows it and the labeling queue showed a blank.

    So the two surfaces held two different renderability rules, which is the
    precise failure this module's docstring was written to prevent — reproduced
    inside the module written to prevent it.

    Returns 1.0 when nothing should be scaled.
    """
    probs = [p for p in (_as_prob(v) for v in probabilities) if p is not None]
    if not probs:
        return 1.0
    shown = probs[:displayed_count]
    if not shown:
        return 1.0
    # Two-outcome markets get the stricter threshold (a true binary).
    threshold = 1.01 if len(shown) == 2 else 1.05
    total = sum(probs)
    if total <= threshold or total > INDEPENDENT_BINARY_MAX_SUM:
        return 1.0
    return total


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
    market_name: Optional[str] = None,
) -> list[str]:
    """Every reason this market cannot currently be rendered honestly.

    A list rather than a first-match, because "which defect" is the question an
    operator asks after "is it defective", and re-deriving it costs a second
    pass over the same rows.

    `market_name` is optional so every existing caller keeps working unchanged;
    supplied, it adds the unfilled-template check.
    """
    defects: list[str] = []
    if has_unfilled_template(market_name):
        defects.append("unfilled_template")
    if is_anonymized_market(outcome_names):
        defects.append("anonymized_outcomes")
    coherence = field_coherence(outcome_probabilities)
    if not coherence["coherent"]:
        defects.append(f"incoherent_field:{coherence['reason']}")
    return defects


def is_unlabelable(
    *,
    outcome_names: Sequence[Optional[str]],
    outcome_probabilities: Sequence[Any],
    market_name: Optional[str] = None,
) -> Optional[str]:
    """Should the LABELING SAMPLER refuse to serve this card? Reason, or None.

    Narrower than `card_defects` on purpose, and the difference is the whole
    fix. A card is refused only when **no honest number can be shown for it**:

      * `unfilled_template`   — the title has a blank in it. Unreadable at any
                                price (Polymarket group-parent shells).
      * `anonymized_outcomes` — "Person B / Person K". Nothing to rank.
      * `no_priced_outcomes`  — there is no probability anywhere.
      * `all_outcomes_certain`— every leg pinned at ~1.0 (#1874's shape).

    A merely WIDE field is NOT refused. `sum_exceeds_one` was silently emptying
    half the labeling queue — including `Presidential Election Winner 2028` and
    `Ballon d'Or Winner 2026` — for markets Discover renders perfectly well via
    `display_scale`. Dropping those would have been culling the most valuable
    cards in the pool and biasing the training slice toward simple binaries; the
    fix is to show them the way the feed does, not to hide them.
    """
    if has_unfilled_template(market_name):
        return "unfilled_template"
    if is_anonymized_market(outcome_names):
        return "anonymized_outcomes"
    coherence = field_coherence(outcome_probabilities)
    if coherence["reason"] in ("no_priced_outcomes", "all_outcomes_certain"):
        return coherence["reason"]
    return None
