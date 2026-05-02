"""Match Kalshi ground truth against our DB and feed."""
import asyncio, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def run():
    from app.tasks.base import get_task_session
    from sqlalchemy import text
    from difflib import SequenceMatcher
    import httpx

    # Load ground truth
    gt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kalshi_ground_truth.json")
    with open(gt_path) as f:
        gt_markets = json.load(f)
    print(f"Kalshi ground truth: {len(gt_markets)} markets, {sum(1 for m in gt_markets if m.get('trending'))} trending")

    # Load our DB markets
    async with get_task_session() as s:
        r = await s.execute(text("""
            SELECT id, name, llm_sport_category, source, volume_24h
            FROM futures_markets WHERE status = 'open'
            ORDER BY volume_24h DESC NULLS LAST LIMIT 10000
        """))
        db_markets = r.all()
    print(f"DB open markets: {len(db_markets)}")

    # Match
    matched = 0
    unmatched = []
    matched_ids = set()
    for gt in gt_markets:
        gt_name = gt["market_name"].lower().strip()
        best_id = None
        best_score = 0
        for dbm in db_markets:
            db_name = (dbm.name or "").lower().strip()
            if gt_name in db_name or db_name in gt_name:
                score = 0.95
            else:
                score = SequenceMatcher(None, gt_name[:50], db_name[:50]).ratio()
            if score > best_score and score > 0.5:
                best_score = score
                best_id = dbm.id
        if best_id:
            matched += 1
            matched_ids.add(best_id)
        else:
            unmatched.append(gt)

    print(f"\nMatched: {matched}/{len(gt_markets)} ({matched*100//len(gt_markets)}%)")
    print(f"Unmatched: {len(unmatched)}")

    # Check how many matched markets appear in our feed
    try:
        resp = httpx.get("https://api.bainluck.com/api/feed?limit=500&event_pct=0.15", timeout=30)
        feed = resp.json().get("items", [])
        feed_ids = set()
        for item in feed:
            if item["type"] == "futures":
                feed_ids.add(item["data"]["id"])

        in_feed = len(matched_ids & feed_ids)
        not_in_feed = len(matched_ids - feed_ids)
        print(f"\nOf {matched} matched markets:")
        print(f"  In our feed: {in_feed} ({in_feed*100//matched if matched else 0}%)")
        print(f"  NOT in feed: {not_in_feed} ({not_in_feed*100//matched if matched else 0}%)")
    except Exception as e:
        print(f"Feed check failed: {e}")

    # Show trending markets we're missing from feed
    print(f"\nTrending Kalshi markets NOT in our feed:")
    for gt in gt_markets:
        if not gt.get("trending"): continue
        gt_name = gt["market_name"].lower().strip()
        in_feed_match = False
        for item in feed:
            if item["type"] != "futures": continue
            db_name = (item["data"].get("name") or "").lower().strip()
            if gt_name in db_name or db_name in gt_name or SequenceMatcher(None, gt_name[:40], db_name[:40]).ratio() > 0.6:
                in_feed_match = True
                break
        if not in_feed_match:
            print(f"  [{gt['category']:15s}] {gt['market_name'][:55]}")

asyncio.run(run())
