"""UX-P040 settled prop-grade contract.

Extends ``feed_card_trust_contract``. Clients may render only an explicit typed
backend verdict; lifecycle, a defaulted winner flag, or a generic settlement
source cannot manufacture HIT/MISS.
"""

from __future__ import annotations


def evaluate(case: dict) -> dict:
    rows = case.get("rows", [])
    if not case.get("same_player_stat", True):
        return {"state": "WITHHOLD", "reason": "mixed_entity_group"}
    hits = {row["hit"] for row in rows if row.get("hit") is not None}
    if len(hits) > 1:
        return {"state": "WITHHOLD", "reason": "conflicting_rung_verdicts"}
    if hits:
        return {"state": "HIT" if True in hits else "MISS", "reason": "explicit_hit"}
    if any(row.get("actual") is not None for row in rows):
        return {"state": "ACTUAL_ONLY", "reason": "no_explicit_verdict"}
    return {"state": "WITHHOLD", "reason": "no_typed_grade"}

