"""Authority for membership on a golf tournament detail page."""

from __future__ import annotations

from typing import Any


FOREIGN_TERMS = {
    "chess", "rodeo", "bowling", "basketball", "pba", "movie", "film",
    "actor", "actress", "squash", "tennis", "esports", "valorant",
}
PROP_OUTCOMES = {
    "pga tour", "lpga tour", "liv", "dp world tour", "asian tour",
    "united states", "europe", "yes", "no", "over", "under", "draw",
}


def _words(value: Any) -> set[str]:
    return set(str(value or "").lower().replace("-", " ").split())


def evaluate(row: dict[str, Any]) -> dict[str, Any]:
    reasons: set[str] = set()
    market_words = _words(row.get("market_name"))
    outcome_words = _words(row.get("outcome_name"))
    if market_words & FOREIGN_TERMS:
        reasons.add("FOREIGN_DOMAIN_MARKET")
    if outcome_words & FOREIGN_TERMS:
        reasons.add("FOREIGN_DOMAIN_OUTCOME")
    if str(row.get("outcome_name") or "").strip().lower() in PROP_OUTCOMES:
        reasons.add("PROP_OUTCOME_NOT_GOLFER")
    if row.get("page_gender") != row.get("market_gender"):
        reasons.add("GENDER_FIELD_MISMATCH")
    if row.get("page_tournament_key") != row.get("market_tournament_key"):
        reasons.add("TOURNAMENT_KEY_MISMATCH")
    if row.get("authoritative_field_present") and not row.get("outcome_in_authoritative_field"):
        reasons.add("OUTSIDE_AUTHORITATIVE_FIELD")
    if row.get("membership_basis") in {"shared_word", "two_word_overlap"} and not row.get("authoritative_event_id_match"):
        reasons.add("FUZZY_MATCH_UNCONFIRMED")
    if row.get("graded_winner") and reasons:
        reasons.add("GRADE_CANNOT_OVERRIDE_MEMBERSHIP")
    return {"verdict": "KEEP" if not reasons else "DROP", "reasons": sorted(reasons)}
