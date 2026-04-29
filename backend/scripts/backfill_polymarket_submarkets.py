"""Backfill: Decompose existing Polymarket game events into per-sub-market rows.

Polymarket game events (e.g., "Magic vs. Pistons") contain ~40 sub-markets
(moneyline, spread, O/U, player props) but were stored as 1 FuturesMarket
with all sub-markets flattened into outcomes. This script:

1. Reports category breakdown (including crypto count)
2. Finds Polymarket game events that need decomposition
3. Re-fetches their data from the Gamma API
4. Creates separate FuturesMarket rows per sub-market
5. Optionally cleans up stale crypto markets

Usage:
    # Dry run (report only, no changes):
    heroku run --app bainluck -- python3 scripts/backfill_polymarket_submarkets.py --dry-run

    # Execute decomposition:
    heroku run --app bainluck -- python3 scripts/backfill_polymarket_submarkets.py

    # Also clean up crypto:
    heroku run --app bainluck -- python3 scripts/backfill_polymarket_submarkets.py --cleanup-crypto
"""

import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run(dry_run: bool = False, cleanup_crypto: bool = False):
    from sqlalchemy import text, select, func
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.tasks.base import get_task_session
    from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
    from app.services.polymarket_api import PolymarketAPIService
    from app.utils.odds_math import probability_to_american
    from app.utils.market_label_normalization import compute_market_tier

    async with get_task_session() as session:
        # ── Step 1: Category breakdown ──
        print("=" * 60)
        print("CATEGORY BREAKDOWN")
        print("=" * 60)
        r = await session.execute(text("""
            SELECT llm_sport_category, source, COUNT(*) as cnt
            FROM futures_markets
            GROUP BY llm_sport_category, source
            ORDER BY cnt DESC
        """))
        cats: dict[str, dict[str, int]] = {}
        for row in r.all():
            cat = row[0] or "NULL"
            src = row[1] or "?"
            cats.setdefault(cat, {})[src] = row[2]
        for cat in sorted(cats.keys()):
            sources = cats[cat]
            total = sum(sources.values())
            parts = ", ".join(f"{s}={c}" for s, c in sorted(sources.items()))
            print(f"  {cat:25s} {total:>7d}  ({parts})")

        crypto_count = sum(cats.get("crypto", {}).values())
        print(f"\nCrypto markets: {crypto_count}")

        # ── Step 2: Find game events needing decomposition ──
        print("\n" + "=" * 60)
        print("POLYMARKET GAME EVENTS TO DECOMPOSE")
        print("=" * 60)

        # Game events = non-neg_risk multi-market events (group_type='polymarket_event')
        # that have outcomes but no sub-markets yet
        game_events_r = await session.execute(text("""
            SELECT fm.id, fm.external_id, fm.name, fm.llm_sport_category,
                   fm.event_id, fm.commence_time, fm.resolution_date,
                   fm.status, fm.llm_league, fm.group_id,
                   COUNT(fo.id) as outcome_count
            FROM futures_markets fm
            LEFT JOIN futures_outcomes fo ON fo.market_id = fm.id
            WHERE fm.source = 'polymarket'
              AND fm.group_type = 'polymarket_event'
              AND fm.status = 'open'
              AND NOT EXISTS (
                  SELECT 1 FROM futures_markets sub
                  WHERE sub.group_id = fm.group_id
                    AND sub.group_type = 'polymarket_sub_market'
              )
            GROUP BY fm.id
            HAVING COUNT(fo.id) > 2
            ORDER BY fm.commence_time DESC NULLS LAST
            LIMIT 500
        """))
        game_events = game_events_r.all()
        print(f"Game events with >2 outcomes (need decomposition): {len(game_events)}")

        # Check how many already have sub-markets
        existing_sub_r = await session.execute(text("""
            SELECT COUNT(*) FROM futures_markets
            WHERE source = 'polymarket'
              AND group_type = 'polymarket_sub_market'
        """))
        existing_subs = existing_sub_r.scalar()
        print(f"Existing sub-markets (already decomposed): {existing_subs}")

        if not game_events:
            print("Nothing to decompose.")
        else:
            for ge in game_events[:10]:
                print(f"  id={ge.id} ext={ge.external_id} outcomes={ge.outcome_count} "
                      f"event_id={ge.event_id} name={ge.name[:50]}")
            if len(game_events) > 10:
                print(f"  ... +{len(game_events) - 10} more")

        if dry_run:
            print("\n[DRY RUN] No changes made. Run without --dry-run to execute.")
            return

        # ── Step 3: Decompose game events ──
        if game_events:
            print(f"\nDecomposing {len(game_events)} game events...")
            api = PolymarketAPIService()
            decomposed = 0
            sub_markets_created = 0
            errors = 0
            now_str = "now()"

            try:
                for i, ge in enumerate(game_events):
                    try:
                        event_data = await api.get_event_by_id(ge.external_id)
                        if not event_data:
                            print(f"  [{i+1}/{len(game_events)}] SKIP {ge.external_id} — not found on Gamma API")
                            continue

                        markets = event_data.get("markets", [])
                        if len(markets) <= 1:
                            continue

                        for mkt_data in markets:
                            condition_id = mkt_data.get("conditionId") or mkt_data.get("condition_id")
                            question = mkt_data.get("question", "")
                            if not condition_id or not question:
                                continue

                            outcome_prices = mkt_data.get("outcomePrices")
                            if isinstance(outcome_prices, str):
                                import json
                                try:
                                    outcome_prices = json.loads(outcome_prices)
                                except (json.JSONDecodeError, TypeError):
                                    outcome_prices = []
                            outcome_prices = [float(p) for p in (outcome_prices or []) if p]

                            prob = outcome_prices[0] if outcome_prices else None
                            if not prob or prob <= 0:
                                best_bid = mkt_data.get("bestBid") or mkt_data.get("best_bid")
                                best_ask = mkt_data.get("bestAsk") or mkt_data.get("best_ask")
                                if best_bid and best_ask and float(best_bid) > 0 and float(best_ask) > 0:
                                    prob = (float(best_bid) + float(best_ask)) / 2
                                elif mkt_data.get("lastTradePrice") or mkt_data.get("last_trade_price"):
                                    ltp = mkt_data.get("lastTradePrice") or mkt_data.get("last_trade_price")
                                    prob = float(ltp) if ltp else None
                            if not prob or prob <= 0:
                                continue

                            sub_tier = compute_market_tier(
                                question, "game_prop",
                                sport_category=ge.llm_sport_category,
                            )

                            sub_stmt = pg_insert(FuturesMarket).values(
                                source="polymarket",
                                external_id=condition_id,
                                name=question,
                                category="game_prop",
                                llm_sport_category=ge.llm_sport_category,
                                llm_league=ge.llm_league,
                                market_tier=sub_tier,
                                mutually_exclusive=True,
                                commence_time=ge.commence_time,
                                resolution_date=ge.resolution_date,
                                status=ge.status,
                                group_id=ge.group_id,
                                group_type="polymarket_sub_market",
                                event_id=ge.event_id,
                            ).on_conflict_do_update(
                                index_elements=["source", "external_id"],
                                set_={
                                    "name": question,
                                    "market_tier": sub_tier,
                                    "status": ge.status,
                                    "event_id": ge.event_id,
                                    "updated_at": func.now(),
                                },
                            ).returning(FuturesMarket.id)
                            sub_result = await session.execute(sub_stmt)
                            sub_market_id = sub_result.scalar_one()

                            # Over/Yes outcome
                            is_ou = "o/u" in question.lower()
                            over_name = "Over" if is_ou else "Yes"
                            american = probability_to_american(prob) if 0 < prob < 1 else None

                            over_stmt = pg_insert(FuturesOutcome).values(
                                market_id=sub_market_id,
                                external_id=f"{condition_id}_yes",
                                name=over_name,
                                current_probability=prob,
                                current_american_odds=american,
                                opening_probability=prob,
                                opening_american_odds=american,
                                rank=1,
                            ).on_conflict_do_update(
                                index_elements=["market_id", "external_id"],
                                set_={
                                    "current_probability": prob,
                                    "current_american_odds": american,
                                    "rank": 1,
                                    "last_updated": func.now(),
                                },
                            )
                            await session.execute(over_stmt)

                            # Under/No outcome
                            if len(outcome_prices) > 1:
                                under_prob = outcome_prices[1]
                                under_name = "Under" if is_ou else "No"
                                under_american = probability_to_american(under_prob) if 0 < under_prob < 1 else None
                                under_stmt = pg_insert(FuturesOutcome).values(
                                    market_id=sub_market_id,
                                    external_id=f"{condition_id}_no",
                                    name=under_name,
                                    current_probability=under_prob,
                                    current_american_odds=under_american,
                                    opening_probability=under_prob,
                                    opening_american_odds=under_american,
                                    rank=2,
                                ).on_conflict_do_update(
                                    index_elements=["market_id", "external_id"],
                                    set_={
                                        "current_probability": under_prob,
                                        "current_american_odds": under_american,
                                        "rank": 2,
                                        "last_updated": func.now(),
                                    },
                                )
                                await session.execute(under_stmt)

                            sub_markets_created += 1

                        decomposed += 1
                        if (i + 1) % 20 == 0:
                            print(f"  [{i+1}/{len(game_events)}] Decomposed {decomposed} events, {sub_markets_created} sub-markets")
                            await session.flush()

                    except Exception as e:
                        errors += 1
                        print(f"  ERROR on {ge.external_id}: {e}")
                        if errors > 20:
                            print("  Too many errors, stopping.")
                            break

            finally:
                await api.close()

            print(f"\nDone: decomposed={decomposed}, sub_markets={sub_markets_created}, errors={errors}")

        # ── Step 3b: Propagate event_id from parents to sub-markets ──
        print(f"\n{'=' * 60}")
        print("PROPAGATING event_id FROM PARENTS TO SUB-MARKETS")
        print("=" * 60)
        prop_result = await session.execute(text("""
            UPDATE futures_markets sub
            SET event_id = parent.event_id
            FROM futures_markets parent
            WHERE sub.group_type = 'polymarket_sub_market'
              AND sub.event_id IS NULL
              AND sub.group_id IS NOT NULL
              AND parent.source = 'polymarket'
              AND parent.group_type = 'polymarket_event'
              AND parent.group_id = sub.group_id
              AND parent.event_id IS NOT NULL
        """))
        print(f"  Sub-markets linked: {prop_result.rowcount}")

        # Also skip re-decomposing events that already have sub-markets
        # by counting how many sub-markets now exist
        sub_count_r = await session.execute(text("""
            SELECT COUNT(*) FROM futures_markets
            WHERE source = 'polymarket' AND group_type = 'polymarket_sub_market'
        """))
        print(f"  Total sub-markets now: {sub_count_r.scalar()}")

        linked_sub_r = await session.execute(text("""
            SELECT COUNT(*) FROM futures_markets
            WHERE source = 'polymarket'
              AND group_type = 'polymarket_sub_market'
              AND event_id IS NOT NULL
        """))
        print(f"  Sub-markets with event_id: {linked_sub_r.scalar()}")

        # ── Step 4: Crypto cleanup ──
        if cleanup_crypto and crypto_count > 0:
            print(f"\n{'=' * 60}")
            print(f"CRYPTO CLEANUP: Removing {crypto_count} crypto markets")
            print("=" * 60)

            # Delete snapshots → outcomes → markets (FK order)
            await session.execute(text("""
                DELETE FROM futures_odds_snapshots WHERE outcome_id IN (
                    SELECT fo.id FROM futures_outcomes fo
                    JOIN futures_markets fm ON fo.market_id = fm.id
                    WHERE fm.llm_sport_category = 'crypto'
                )
            """))
            await session.execute(text("""
                DELETE FROM futures_outcomes WHERE market_id IN (
                    SELECT id FROM futures_markets WHERE llm_sport_category = 'crypto'
                )
            """))
            result = await session.execute(text("""
                DELETE FROM futures_markets WHERE llm_sport_category = 'crypto'
            """))
            print(f"  Deleted {result.rowcount} crypto market rows")
        elif cleanup_crypto:
            print("\nNo crypto markets found — nothing to clean up.")


def main():
    parser = argparse.ArgumentParser(description="Backfill Polymarket sub-markets")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no changes")
    parser.add_argument("--cleanup-crypto", action="store_true", help="Also delete crypto markets")
    args = parser.parse_args()

    asyncio.run(run(dry_run=args.dry_run, cleanup_crypto=args.cleanup_crypto))


if __name__ == "__main__":
    main()
