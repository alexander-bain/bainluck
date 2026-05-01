"""
Calibrate feed interestingness against Polymarket ground truth.

Reads the enriched Google Sheet, matches market names against our DB,
compares ground truth interestingness scores against our feed scores,
and reports gaps (markets Polymarket highlights that we rank low).

Usage:
    heroku run --app bainluck -- python3 scripts/calibrate_interestingness.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHEET_ID = "1RztughDfCj1F691yeQWq_67UfCn3LXNpVrejZ35_4_w"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _get_sheets_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not creds_json:
        creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not creds_json:
        creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_file and os.path.exists(creds_file):
            creds_json = open(creds_file).read()
    if not creds_json:
        raise RuntimeError("No Google credentials found")

    creds_dict = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=credentials)


async def calibrate():
    from sqlalchemy import select, text
    from app.tasks.base import get_task_session
    from app.models.models import FuturesMarket, FuturesOutcome

    # 1. Read ground truth from sheet
    print("Reading ground truth sheet...")
    service = _get_sheets_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="Sheet1!A1:M1000",
    ).execute()
    rows = result.get("values", [])
    if len(rows) < 2:
        print("Sheet is empty")
        return

    headers = rows[0]
    ground_truth = []
    for row in rows[1:]:
        while len(row) < 13:
            row.append("")
        gt = {
            "date": row[0],
            "market_name": row[2],
            "regex_category": row[3],
            "llm_category": row[8],
            "hook": row[9],
            "interestingness": int(row[10]) if row[10] else 0,
            "timeliness": row[11],
            "shareability": int(row[12]) if row[12] else 0,
        }
        if gt["market_name"] and gt["interestingness"] > 0:
            ground_truth.append(gt)

    print(f"Ground truth: {len(ground_truth)} enriched markets")

    # 2. Match against our DB
    print("\nMatching against futures_markets DB...")
    async with get_task_session() as session:
        # Get our feed scores for comparison
        feed_result = await session.execute(text("""
            SELECT fm.id, fm.name, fm.llm_sport_category, fm.market_tier,
                   fm.status, fm.source,
                   (SELECT MAX(fo.current_probability) FROM futures_outcomes fo WHERE fo.market_id = fm.id) as leader_prob,
                   fm.volume_24h
            FROM futures_markets fm
            WHERE fm.status = 'open'
            ORDER BY fm.volume_24h DESC NULLS LAST
            LIMIT 5000
        """))
        db_markets = feed_result.all()

    print(f"DB open markets: {len(db_markets)}")

    # 3. Fuzzy match ground truth → DB
    from difflib import SequenceMatcher

    matched = []
    unmatched = []

    for gt in ground_truth:
        gt_name = gt["market_name"].lower().strip()
        best_match = None
        best_score = 0

        for dbm in db_markets:
            db_name = (dbm.name or "").lower().strip()
            # Try exact substring match first
            if gt_name in db_name or db_name in gt_name:
                score = 0.95
            else:
                score = SequenceMatcher(None, gt_name, db_name).ratio()

            if score > best_score and score > 0.5:
                best_score = score
                best_match = dbm

        if best_match and best_score > 0.5:
            matched.append({
                "gt": gt,
                "db_id": best_match.id,
                "db_name": best_match.name,
                "db_category": best_match.llm_sport_category,
                "db_tier": best_match.market_tier,
                "db_source": best_match.source,
                "db_volume": best_match.volume_24h,
                "db_leader_prob": float(best_match.leader_prob) if best_match.leader_prob else None,
                "match_score": best_score,
            })
        else:
            unmatched.append(gt)

    print(f"\nMatched: {len(matched)}/{len(ground_truth)} ({len(matched) * 100 // len(ground_truth)}%)")
    print(f"Unmatched: {len(unmatched)}")

    # 4. Analysis
    print("\n" + "=" * 70)
    print("CALIBRATION REPORT")
    print("=" * 70)

    # Category distribution
    from collections import Counter
    gt_cats = Counter(gt["llm_category"] for gt in ground_truth)
    print("\nGround truth category distribution:")
    for cat, count in gt_cats.most_common():
        print(f"  {cat:20s} {count:3d} ({count * 100 // len(ground_truth)}%)")

    # High-interestingness markets we DON'T have
    print(f"\n--- HIGH-VALUE MARKETS WE'RE MISSING ({len(unmatched)} unmatched) ---")
    high_value_missing = [gt for gt in unmatched if gt["interestingness"] >= 8]
    high_value_missing.sort(key=lambda x: x["interestingness"], reverse=True)
    for gt in high_value_missing[:15]:
        print(f"  int={gt['interestingness']} share={gt['shareability']} [{gt['llm_category']:12s}] {gt['market_name'][:60]}")

    # Category gaps: what categories does Polymarket highlight that we underweight?
    print("\n--- CATEGORY GAPS ---")
    matched_cats = Counter(m["gt"]["llm_category"] for m in matched)
    unmatched_cats = Counter(gt["llm_category"] for gt in unmatched)
    all_cats = set(gt_cats.keys())
    print(f"{'Category':20s} {'GT Total':>8s} {'Matched':>8s} {'Missing':>8s} {'Match%':>8s}")
    for cat in sorted(all_cats):
        total = gt_cats[cat]
        found = matched_cats.get(cat, 0)
        missing = unmatched_cats.get(cat, 0)
        pct = f"{found * 100 // total}%" if total > 0 else "N/A"
        flag = " ← GAP" if missing > found else ""
        print(f"  {cat:20s} {total:>6d} {found:>8d} {missing:>8d} {pct:>8s}{flag}")

    # Interestingness distribution for matched markets
    if matched:
        print("\n--- MATCHED MARKET ANALYSIS ---")
        avg_int = sum(m["gt"]["interestingness"] for m in matched) / len(matched)
        avg_share = sum(m["gt"]["shareability"] for m in matched) / len(matched)
        print(f"Average interestingness: {avg_int:.1f}/10")
        print(f"Average shareability: {avg_share:.1f}/10")

        # Markets with high ground truth but low DB presence (no volume)
        low_volume_high_interest = [
            m for m in matched
            if m["gt"]["interestingness"] >= 8 and (m["db_volume"] is None or m["db_volume"] < 100)
        ]
        if low_volume_high_interest:
            print(f"\nHigh-interest but low-volume in our DB ({len(low_volume_high_interest)}):")
            for m in low_volume_high_interest[:10]:
                print(f"  int={m['gt']['interestingness']} vol={m['db_volume'] or 0:>8.0f} [{m['db_category'] or '?':12s}] {m['db_name'][:50]}")

    # 5. Feed ranking check — where do these markets rank in our actual feed?
    print("\n--- FEED RANKING CHECK ---")
    print("Fetching live feed to check where ground truth markets rank...")
    try:
        import httpx
        feed_resp = httpx.get(
            "https://api.bainluck.com/api/feed?limit=500&include_events=false",
            timeout=30,
        )
        feed_data = feed_resp.json()
        feed_items = feed_data.get("items", [])
        feed_market_ids = set()
        feed_rank = {}
        for i, item in enumerate(feed_items):
            if item.get("type") == "futures":
                mid = item["data"].get("id")
                feed_market_ids.add(mid)
                feed_rank[mid] = i + 1

        in_top_50 = 0
        in_top_100 = 0
        in_top_200 = 0
        in_feed = 0
        not_in_feed = 0

        for m in matched:
            db_id = m["db_id"]
            rank = feed_rank.get(db_id)
            if rank:
                in_feed += 1
                if rank <= 50: in_top_50 += 1
                if rank <= 100: in_top_100 += 1
                if rank <= 200: in_top_200 += 1
            else:
                not_in_feed += 1

        print(f"  Of {len(matched)} matched ground truth markets:")
        print(f"    In feed top 50:  {in_top_50:3d} ({in_top_50 * 100 // len(matched)}%)")
        print(f"    In feed top 100: {in_top_100:3d} ({in_top_100 * 100 // len(matched)}%)")
        print(f"    In feed top 200: {in_top_200:3d} ({in_top_200 * 100 // len(matched)}%)")
        print(f"    In feed at all:  {in_feed:3d} ({in_feed * 100 // len(matched)}%)")
        print(f"    NOT in feed:     {not_in_feed:3d} ({not_in_feed * 100 // len(matched)}%)")

        # Show specific high-interest markets NOT in the feed
        buried = [m for m in matched if m["db_id"] not in feed_market_ids and m["gt"]["interestingness"] >= 8]
        if buried:
            print(f"\n  High-interest markets NOT in feed ({len(buried)}):")
            for m in buried[:10]:
                print(f"    int={m['gt']['interestingness']} [{m['gt']['llm_category']:12s}] {m['db_name'][:55]}")

        # Show what IS in the feed top 20 for comparison
        print(f"\n  What's actually in our feed top 20:")
        for i, item in enumerate(feed_items[:20]):
            if item.get("type") == "futures":
                d = item["data"]
                cat = d.get("llm_sport_category", "?")
                score = item.get("score", 0)
                print(f"    #{i+1:2d} score={score:3d} [{cat:12s}] {d.get('name','')[:50]}")
    except Exception as e:
        print(f"  Feed check failed: {e}")

    # Summary stats
    print("\n--- SUMMARY ---")
    print(f"Ground truth markets: {len(ground_truth)}")
    print(f"Matched to our DB: {len(matched)} ({len(matched) * 100 // len(ground_truth)}%)")
    print(f"Missing from DB: {len(unmatched)} ({len(unmatched) * 100 // len(ground_truth)}%)")
    print(f"Top categories Polymarket highlights: {', '.join(c for c, _ in gt_cats.most_common(5))}")
    top_missing_cats = unmatched_cats.most_common(3)
    if top_missing_cats:
        print(f"Top categories we're missing: {', '.join(f'{c}({n})' for c, n in top_missing_cats)}")


# Fix: define matched_count properly
async def _run():
    await calibrate()


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
