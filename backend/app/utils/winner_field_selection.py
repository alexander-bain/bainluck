"""Settled-concept winner-field selection invariant (#1177).

Pure, dependency-free selection logic shared by every event-concept adapter that
builds a winner field from competing source markets (soccer World Cup, cycling
Grand Tours, …). Imports nothing from the app so it can never create a circular
import (mirrors ``sport_keys.py``).

The invariant it enforces — Alex's *settled means settled*, generalized:

    A SETTLED concept must NEVER serve an UNGRADED winner field when a GRADED
    market (one carrying authoritative ``is_winner`` rows) exists among its
    candidates. The crown must not depend on which source market happened to
    update last — a freshly-polled odds_api field that FIZZLES on a settled
    tournament (World Cup: Spain to 0.587, field sum 0.498) must lose to the
    Polymarket/Kalshi market where Spain is graded ``is_winner``.

For a LIVE / unsettled field (no candidate is graded) the pre-existing
"adapter's own freshest/widest coherent field wins" behavior is preserved
exactly: this helper only ever *overrides* an ungraded pick with a graded one.
"""

from datetime import datetime, timezone


def market_has_graded_winner(market) -> bool:
    """True when a futures market carries ≥1 authoritative graded winner outcome
    (``is_winner`` set). A graded winner-field market means the tournament has a
    decided champion, so a settled concept must prefer it over any ungraded field."""
    return any(
        bool(getattr(o, "is_winner", False))
        for o in (getattr(market, "outcomes", None) or [])
    )


def prefer_graded_winner_field(best, best_real, coherent):
    """Enforce the #1177 settled-concept invariant on an adapter's selection.

    ``best`` / ``best_real`` are the market the adapter already picked by its own
    freshest/widest rule and that market's real priced outcomes. ``coherent`` is
    the full pool of ``(market, real_outcomes, freshness)`` tuples that passed the
    adapter's spread + coherence gates.

    If ``best`` is ungraded but ≥1 graded market exists in ``coherent``, return the
    graded one (freshest graded, widest field as tiebreak) — a settled concept can
    never serve an ungraded fizzled field while an authoritative graded one exists.
    Otherwise return ``(best, best_real)`` unchanged (live/unsettled fields, and
    fields the adapter already resolved to a graded market)."""
    if best is None:
        return best, best_real
    if market_has_graded_winner(best):
        return best, best_real
    graded = [c for c in coherent if market_has_graded_winner(c[0])]
    if not graded:
        return best, best_real
    g = max(graded, key=lambda c: (c[2], len(c[1])))
    return g[0], g[1]


def _min_time() -> datetime:
    """Sentinel freshness floor for outcomes with no ``last_updated`` — exported so
    adapters compute freshness identically to this module's expectations."""
    return datetime.min.replace(tzinfo=timezone.utc)
