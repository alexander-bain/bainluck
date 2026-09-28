"""The threshold a single-leg Kalshi market is really asking about (#9383).

A Kalshi event with ONE market is stored as one outcome named ``Yes``
(``_kalshi_outcome_name`` rule 1). On a plain question that is right — "Will X
happen? Yes 40%". On a THRESHOLD market it throws the question away: the venue's
own leg label is ``Over 2.5 maps`` / ``7,845 or above`` / ``1+ overtime
periods``, and the card printed ``Yes 52%`` under a title that never says the
number. Measured on production 2026-09-28 ~13:40Z: esports "Total Maps" boards,
the index/Pokemon Up-or-Down family and the NCAAF/WNBA "Overtime" family.

WHY THE NAME STAYS ``Yes``. 29 consumers key on a stored ``Yes`` (economics'
and weather's yes-leg pick, the feed's binary reason, team linking's non-team
guard, …). Renaming the row would drop these markets from the pages that read
them. So the label rides beside the row in ``market_metadata.threshold_label``
— additive, rewritten by the ordinary poll — and the served-name sites print it
in place of the lone ``Yes``.

THE PREDICATE IS THE VENUE'S OWN. A threshold market carries a ``strike_type``
from the set below AND a numeric strike AND a leg label that is not itself
``Yes``. Each clause refuses a real plain binary (venue read 2026-09-28):
``KXINDUS-27JAN01-YES`` has strike ``None``; ``KXMIDTERMHAPPEN-2026-T50`` has
``greater_or_equal`` but ``yes_sub_title='Yes'``; ``KXCANADACUP-30`` has strike
``None``. The label is returned VERBATIM — the venue already wrote the sentence
a reader would say ("7,845 or above"), and re-typesetting it from the strike
would only add a way to be wrong.
"""

from __future__ import annotations

from typing import Optional, Sequence

THRESHOLD_STRIKE_TYPES = frozenset(
    {"greater", "greater_or_equal", "less", "less_or_equal", "between"}
)

_PLAIN_ANSWERS = frozenset({"yes", "no"})


def single_leg_threshold_label(markets: Sequence) -> Optional[str]:
    """The venue's leg label when ``markets`` is one threshold market, else ``None``.

    ``None`` is the unchanged path: the outcome keeps printing ``Yes``. Only a
    single-market event qualifies — a multi-market event already names each leg
    from its own ``yes_sub_title`` through the naming ladder.
    """
    if len(markets) != 1:
        return None
    market = markets[0]
    if getattr(market, "strike_type", None) not in THRESHOLD_STRIKE_TYPES:
        return None
    if (
        getattr(market, "floor_strike", None) is None
        and getattr(market, "cap_strike", None) is None
    ):
        return None
    label = (getattr(market, "yes_sub_title", None) or "").strip()
    if not label or label.lower() in _PLAIN_ANSWERS:
        return None
    return label


__all__ = ["THRESHOLD_STRIKE_TYPES", "single_leg_threshold_label"]
