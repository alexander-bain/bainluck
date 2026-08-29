"""Membership authority for a golf tournament detail page (#1625).

A settled major page was rendering chess, rodeo, PBA basketball, movie and LPGA
rows, and crowning "PGA Tour" as the champion of The Masters. Every one of those
arrived through the same door: **membership was decided lexically**. `masters` is
a sufficient golf signal, so "Norway Chess Masters" and "Rodeo Masters" matched;
the completed fallback scans all golf-classified markets; and a graded winner was
kept even when it sat outside the authoritative DataGolf field, so the grade
overrode membership instead of being subject to it.

This module is the single place that answers "does this row belong on this
tournament page?", and it is PURE — no DB, no I/O — so it can be unit-tested
against the same cases the Codex corpus `golf_event_membership_contract` grades.
The reason codes are deliberately IDENTICAL to that contract's, so a divergence
between the oracle and the implementation is visible by name rather than by
behaviour.

The ordering rule that matters, and the one the old code had backwards:
**a grade is not a membership proof.** `is_winner` says who won a market; it says
nothing about whether that market belongs to this tournament. So the grade is
evaluated LAST and can only ever add a reason, never clear one.
"""

from __future__ import annotations

from typing import Any, Iterable

# Domains that are never golf. A market naming one of these does not belong on a
# golf page no matter how well its title happens to overlap a tournament name.
#
# UX-P168 added the second row. `masters`, `open`, `classic`, `invitational` and
# `major` are all sufficient golf signals on their own (`_GOLF_SIGNAL_RE`), and
# none of them is a golf word — every sport below runs an event called one of
# them. "New Zealand Darts Masters: Winner" reached the golf page on `masters`
# alone and was served as a PGA Tour tournament.
FOREIGN_TERMS = frozenset(
    {
        "chess", "rodeo", "bowling", "basketball", "pba", "movie", "film",
        "actor", "actress", "squash", "tennis", "esports", "valorant",
        "darts", "snooker", "cricket", "poker", "billiards",
    }
)

# Outcomes that are not golfers. A tour, a country or a yes/no side can win a
# market, but it can never be the CHAMPION of a tournament, and crowning one is
# the "The Masters winner: PGA Tour" symptom.
PROP_OUTCOMES = frozenset(
    {
        "pga tour", "lpga tour", "liv", "dp world tour", "asian tour",
        "united states", "europe", "yes", "no", "over", "under", "draw",
    }
)

# Membership arrived at by title overlap rather than by a canonical key. Legal,
# but only once an authoritative event id confirms it.
FUZZY_BASES = frozenset({"shared_word", "two_word_overlap"})


def _words(value: Any) -> set[str]:
    return set(str(value or "").lower().replace("-", " ").split())


def is_foreign_domain(name: str | None) -> bool:
    """True when a market or outcome name names a non-golf domain."""
    return bool(_words(name) & FOREIGN_TERMS)


def is_prop_outcome(name: str | None) -> bool:
    """True when an outcome is a tour/country/side rather than a golfer."""
    return str(name or "").strip().lower() in PROP_OUTCOMES


def evaluate_membership(row: dict[str, Any]) -> dict[str, Any]:
    """Decide whether one market/outcome row belongs on a tournament page.

    Mirrors `backend/scripts/evals/golf_event_membership_contract.py` exactly.
    Returns ``{"verdict": "KEEP"|"DROP", "reasons": [...]}``.
    """
    reasons: set[str] = set()

    if is_foreign_domain(row.get("market_name")):
        reasons.add("FOREIGN_DOMAIN_MARKET")
    if is_foreign_domain(row.get("outcome_name")):
        reasons.add("FOREIGN_DOMAIN_OUTCOME")
    if is_prop_outcome(row.get("outcome_name")):
        reasons.add("PROP_OUTCOME_NOT_GOLFER")
    if row.get("page_gender") != row.get("market_gender"):
        reasons.add("GENDER_FIELD_MISMATCH")
    if row.get("page_tournament_key") != row.get("market_tournament_key"):
        reasons.add("TOURNAMENT_KEY_MISMATCH")
    if row.get("authoritative_field_present") and not row.get("outcome_in_authoritative_field"):
        reasons.add("OUTSIDE_AUTHORITATIVE_FIELD")
    if row.get("membership_basis") in FUZZY_BASES and not row.get("authoritative_event_id_match"):
        reasons.add("FUZZY_MATCH_UNCONFIRMED")

    # LAST, and additive only. A grade cannot clear a membership failure — it can
    # only make one louder. This is the inversion #1625 is about.
    if row.get("graded_winner") and reasons:
        reasons.add("GRADE_CANNOT_OVERRIDE_MEMBERSHIP")

    return {"verdict": "KEEP" if not reasons else "DROP", "reasons": sorted(reasons)}


def belongs(row: dict[str, Any]) -> bool:
    """Convenience predicate over :func:`evaluate_membership`."""
    return evaluate_membership(row)["verdict"] == "KEEP"


def drop_foreign_markets(markets: Iterable[Any]) -> list[Any]:
    """Filter out markets whose own name names a non-golf domain.

    The cheapest and highest-yield half of the authority: it is what keeps
    "Norway Chess Masters" and "PBA Basketball Masters" off The Masters, and it
    needs no schedule, no field and no DB round-trip to decide.
    """
    return [m for m in markets if not is_foreign_domain(getattr(m, "name", None))]


def drop_foreign_field_markets(markets: Iterable[Any]) -> list[Any]:
    """Filter out markets whose OUTCOMES name a non-golf domain.

    The name-side half above cannot see "Asia Masters 2026 Winner" — the title is
    domain-neutral and the esports is entirely in the field ("T1 Esports Academy",
    "Dplus Challengers"). `evaluate_membership` has always specified this check on
    `outcome_name`; nothing on the OPEN-tournament path ever ran it.

    Outcomes are read out of ``__dict__`` rather than via attribute access on
    purpose. This runs inside an async request, and a plain ``market.outcomes``
    on a market whose relationship was not eager-loaded would fire a lazy load and
    raise ``MissingGreenlet``. An unloaded relationship is therefore read as NO
    EVIDENCE and the market is KEPT — the drop needs a foreign outcome it can
    actually see, never the mere absence of a loaded field.
    """
    kept = []
    for market in markets:
        outcomes = market.__dict__.get("outcomes") if hasattr(market, "__dict__") else None
        if outcomes and any(is_foreign_domain(getattr(o, "name", None)) for o in outcomes):
            continue
        kept.append(market)
    return kept
