#!/usr/bin/env python3
"""
Audit cross-source matching for non-sport prediction markets.

Measures how well Kalshi and Polymarket markets are unified via
canonical_market_key for politics, entertainment, economics, weather,
and other non-sport categories.

Usage:
    python3 scripts/audit_cross_source_matching.py

Requires DATABASE_URL environment variable (or .env file).
"""

import os
import sys
from collections import defaultdict

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def main():
    from sqlalchemy import create_engine, text

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        # Try loading from .env
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("DATABASE_URL="):
                    db_url = line.strip().split("=", 1)[1].strip('"').strip("'")
                    break

    if not db_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    db_url = db_url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(db_url)

    categories = [
        "politics", "entertainment", "economics", "weather",
        "crypto", "tech", "geopolitics", "culture", "social_media",
    ]
    cat_list = ", ".join(f"'{c}'" for c in categories)

    with engine.connect() as conn:
        # 1. Overall stats
        result = conn.execute(text(f"""
            SELECT
                llm_sport_category,
                COUNT(*) AS total,
                COUNT(canonical_market_key) AS with_key,
                COUNT(*) - COUNT(canonical_market_key) AS without_key,
                COUNT(DISTINCT source) AS source_count
            FROM futures_markets
            WHERE status = 'open'
              AND llm_sport_category IN ({cat_list})
            GROUP BY llm_sport_category
            ORDER BY total DESC
        """))
        rows = result.fetchall()

        print("\n" + "=" * 70)
        print("CROSS-SOURCE MATCHING AUDIT — Non-Sport Markets")
        print("=" * 70)
        print(f"\n{'Category':<18} {'Total':>7} {'With Key':>9} {'No Key':>8} {'Sources':>8}")
        print("-" * 55)
        grand_total = 0
        grand_with_key = 0
        for r in rows:
            cat, total, with_key, without_key, src_count = r
            grand_total += total
            grand_with_key += with_key
            print(f"{cat:<18} {total:>7} {with_key:>9} {without_key:>8} {src_count:>8}")
        print("-" * 55)
        print(f"{'TOTAL':<18} {grand_total:>7} {grand_with_key:>9} {grand_total - grand_with_key:>8}")
        pct = grand_with_key / grand_total * 100 if grand_total else 0
        print(f"\nCanonical key coverage: {pct:.1f}%")

        # 2. Cross-source matched pairs (markets sharing a canonical_market_key with 2+ sources)
        result = conn.execute(text(f"""
            SELECT
                canonical_market_key,
                COUNT(*) AS market_count,
                COUNT(DISTINCT source) AS source_count,
                array_agg(DISTINCT source) AS sources,
                MIN(name) AS sample_name
            FROM futures_markets
            WHERE status = 'open'
              AND llm_sport_category IN ({cat_list})
              AND canonical_market_key IS NOT NULL
            GROUP BY canonical_market_key
            HAVING COUNT(DISTINCT source) >= 2
            ORDER BY market_count DESC
            LIMIT 15
        """))
        pairs = result.fetchall()

        print(f"\n\n{'=' * 70}")
        print("MATCHED PAIRS (same canonical_market_key, 2+ sources)")
        print("=" * 70)
        if pairs:
            for p in pairs:
                key, count, src_count, sources, sample = p
                print(f"\n  Key: {key}")
                print(f"  Markets: {count} | Sources: {sources}")
                print(f"  Sample: {sample[:70]}")
        else:
            print("  No matched pairs found.")

        # Count total matched
        result = conn.execute(text(f"""
            SELECT COUNT(DISTINCT canonical_market_key) AS matched_keys,
                   SUM(cnt) AS matched_markets
            FROM (
                SELECT canonical_market_key, COUNT(*) AS cnt
                FROM futures_markets
                WHERE status = 'open'
                  AND llm_sport_category IN ({cat_list})
                  AND canonical_market_key IS NOT NULL
                GROUP BY canonical_market_key
                HAVING COUNT(DISTINCT source) >= 2
            ) sub
        """))
        matched = result.fetchone()
        print(f"\n  Total matched keys: {matched[0] or 0}")
        print(f"  Total matched markets: {matched[1] or 0}")

        # 3. Likely duplicates (NULL key, same category, different source, similar name)
        print(f"\n\n{'=' * 70}")
        print("LIKELY DUPLICATES (NULL key, similar names, different sources)")
        print("=" * 70)

        try:
            result = conn.execute(text(f"""
                SELECT
                    a.id AS id_a, b.id AS id_b,
                    a.source AS src_a, b.source AS src_b,
                    a.name AS name_a, b.name AS name_b,
                    a.llm_sport_category,
                    similarity(a.name, b.name) AS sim
                FROM futures_markets a
                JOIN futures_markets b
                    ON a.id < b.id
                    AND a.llm_sport_category = b.llm_sport_category
                    AND a.source != b.source
                    AND a.canonical_market_key IS NULL
                    AND b.canonical_market_key IS NULL
                    AND a.status = 'open'
                    AND b.status = 'open'
                WHERE a.llm_sport_category IN ({cat_list})
                  AND similarity(a.name, b.name) > 0.5
                ORDER BY sim DESC
                LIMIT 15
            """))
            dupes = result.fetchall()

            if dupes:
                for d in dupes:
                    print(f"\n  sim={d.sim:.2f} | {d.llm_sport_category}")
                    print(f"    [{d.src_a}] {d.name_a[:65]}")
                    print(f"    [{d.src_b}] {d.name_b[:65]}")
            else:
                print("  No likely duplicates found (similarity > 0.5)")
        except Exception as e:
            print(f"  Skipped (pg_trgm not available or query failed): {e}")

        # 4. Summary
        print(f"\n\n{'=' * 70}")
        print("SUMMARY")
        print("=" * 70)
        print(f"  Total non-sport markets: {grand_total}")
        print(f"  With canonical_market_key: {grand_with_key} ({pct:.1f}%)")
        print(f"  Matched cross-source pairs: {matched[0] or 0} keys")
        print(f"  NULL key (potential unmatched): {grand_total - grand_with_key}")
        print()


if __name__ == "__main__":
    main()
