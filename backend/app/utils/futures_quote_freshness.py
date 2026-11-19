"""The refresh task and its guard must agree when a field needs a real read."""


def registered_price_refresh_market_ids() -> set[int]:
    """Read the explicit tournament and Midterms price registries."""
    from app.utils.midterms_collection import MARKET_IDS, REGISTERED_POLYMARKET_TWIN_IDS
    from app.utils.tournament_register import registered_market_ids

    return registered_market_ids().union(MARKET_IDS, REGISTERED_POLYMARKET_TWIN_IDS)


def price_refresh_due_sql(cutoff: str) -> str:
    """Compose against market alias ``fm`` and a caller-owned SQL cutoff.

    Retain the existing missing-capture case. A recent sibling cannot also
    excuse an old, still-priced leg that the writer is allowed to refresh.
    Graded outcomes and absent/terminal prices do not add work to a field
    whose other quotes are fresh. Refused old prices remain due, subject to
    the task's unchanged per-market attempt marker and run budgets.
    """
    return f"""(
        NOT EXISTS (
            SELECT 1
              FROM futures_outcomes fo
              JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
             WHERE fo.market_id = fm.id
               AND s.captured_at > {cutoff}
               AND fo.last_updated > {cutoff}
        )
        OR EXISTS (
            SELECT 1
              FROM futures_outcomes old_quote
             WHERE old_quote.market_id = fm.id
               AND old_quote.is_winner IS NOT TRUE
               AND old_quote.resolution_source IS DISTINCT FROM 'api_settlement'
               AND old_quote.current_probability > 0
               AND old_quote.current_probability < 1
               AND old_quote.last_updated <= {cutoff}
        )
    )"""
