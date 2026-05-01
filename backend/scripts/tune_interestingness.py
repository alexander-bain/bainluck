"""
Auto-tune interestingness weights against Polymarket ground truth.

Loads all open futures from DB + ground truth from Google Sheet,
simulates feed scoring with different weight configurations,
measures recall (what % of ground truth lands in top N),
and hill-climbs until target recall is reached.

Outputs the best weight configuration as Python code ready to paste
into futures_highlights.py.

Usage:
    heroku run --app bainluck -- python3 scripts/tune_interestingness.py
"""

import asyncio
import json
import os
import sys
import random
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SHEET_ID = "1RztughDfCj1F691yeQWq_67UfCn3LXNpVrejZ35_4_w"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Target: 60% of ground truth markets should appear in feed top 50
TARGET_RECALL_AT_50 = 0.40
TARGET_RECALL_AT_100 = 0.60
MAX_ITERATIONS = 50


@dataclass
class Weights:
    # Category baselines (non-sports get a floor score)
    politics_base: float = 35.0
    geopolitics_base: float = 38.0
    economics_base: float = 33.0
    tech_base: float = 35.0
    entertainment_base: float = 32.0
    culture_base: float = 30.0
    health_base: float = 28.0
    weather_base: float = 25.0
    crypto_base: float = 25.0
    sports_base: float = 20.0  # sports already get boosted by existing logic

    # Penalty for low-quality market patterns
    boring_penalty: float = -25.0

    # Signal boosts
    resolving_soon_7d: float = 15.0
    resolving_soon_30d: float = 8.0
    movement_large: float = 12.0    # >10% 24h change
    movement_medium: float = 6.0    # >3% 24h change
    multi_source: float = 5.0       # on both Kalshi + Polymarket
    decisive_prob: float = 8.0      # leader at 15-85% (not a lock, not a coin flip)
    high_volume: float = 5.0        # volume_24h > 1000
    tier_1: float = 10.0            # championship/major market
    tier_2: float = 5.0             # conference/division

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items()}

    def mutate(self, step: float = 3.0):
        """Create a mutated copy with small random changes."""
        new = Weights(**self.__dict__)
        # Pick 3 random fields to mutate
        fields = [f for f in self.__dict__.keys()]
        for field in random.sample(fields, min(3, len(fields))):
            current = getattr(new, field)
            delta = random.uniform(-step, step)
            setattr(new, field, max(0, current + delta))
        return new


SPORTS_CATEGORIES = {
    "basketball", "football", "baseball", "hockey", "soccer",
    "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
    "esports", "rugby", "lacrosse", "aussierules",
}


def score_market(market: dict, weights: Weights) -> float:
    """Score a single market using the weight configuration."""
    score = 0.0
    cat = (market.get("category") or "other").lower()

    # Category baseline
    if cat == "politics":
        score += weights.politics_base
    elif cat == "geopolitics":
        score += weights.geopolitics_base
    elif cat == "economics":
        score += weights.economics_base
    elif cat == "tech":
        score += weights.tech_base
    elif cat == "entertainment":
        score += weights.entertainment_base
    elif cat == "culture":
        score += weights.culture_base
    elif cat == "health":
        score += weights.health_base
    elif cat == "weather":
        score += weights.weather_base
    elif cat == "crypto":
        score += weights.crypto_base
    elif cat in SPORTS_CATEGORIES:
        score += weights.sports_base
    else:
        score += 15.0  # unknown category

    # Existing market_tier boost
    tier = market.get("market_tier")
    if tier == 1:
        score += weights.tier_1
    elif tier == 2:
        score += weights.tier_2

    # Resolution proximity
    res_date = market.get("resolution_date")
    if res_date:
        try:
            if isinstance(res_date, str):
                rd = datetime.fromisoformat(res_date.replace("Z", "+00:00"))
            else:
                rd = res_date
            days_until = (rd - datetime.now(timezone.utc)).days
            if 0 <= days_until <= 7:
                score += weights.resolving_soon_7d
            elif 7 < days_until <= 30:
                score += weights.resolving_soon_30d
        except (ValueError, TypeError):
            pass

    # Probability decisiveness (15-85% range is most interesting)
    leader_prob = market.get("leader_prob")
    if leader_prob and 0.15 <= leader_prob <= 0.85:
        score += weights.decisive_prob

    # Volume
    volume = market.get("volume_24h") or 0
    if volume > 1000:
        score += weights.high_volume

    # Movement (24h)
    movement = market.get("movement_24h") or 0
    if abs(movement) > 0.10:
        score += weights.movement_large
    elif abs(movement) > 0.03:
        score += weights.movement_medium

    # Multi-source
    source_count = market.get("source_count", 1)
    if source_count >= 2:
        score += weights.multi_source

    # Boring market penalty — low-quality patterns that flood the feed
    name = (market.get("name") or "").lower()
    import re
    boring_patterns = [
        r"# ?(posts|tweets|truths)",     # social media post counts
        r"photographed every",            # "Trump photographed every day"
        r"(ted cruz|trump|biden|harris).*(posts|tweets)",  # politician tweet counts
        r"white house #",                 # White House post counts
        r"what will .+ say during",       # speech prediction (boring)
        r"# of (views|likes|comments)",   # engagement metrics
        r"(savannah|kathy|janet).*(say|drop|announce)",  # obscure politician actions
        r"reauthorize",                   # procedural politics
        r"gold cards? will .+ issue",     # trivial Trump props
    ]
    if any(re.search(p, name) for p in boring_patterns):
        score += weights.boring_penalty

    # Quality boost — genuinely compelling patterns
    compelling_patterns = [
        r"(invade|invasion|war|strike|military action)",
        r"(ceasefire|peace deal|treaty)",
        r"(nba|nfl|mlb|nhl|fifa|world cup|super bowl|olympics|masters|champions league).*(champion|winner)",
        r"(fed decision|interest rate|recession|rate cut)",
        r"\bipo\b|acquire|bankrupt|fail|earnings",
        r"(taylor swift|beyonce|drake|kardashian|bieber)",
        r"(openai|gpt|claude|ai model|deepseek|gemini)",
        r"(u\.?s\.? president|presidential election).*(winner|2028|2026)",
        r"(approval rating).*(trump|biden)",
        r"(regime|coup|revolution|overthrow|fall)",
        r"(china|russia|iran|israel|ukraine|taiwan).*(invade|strike|ceasefire|war|peace)",
        r"(elon musk|jeff bezos|mark zuckerberg|sam altman|warren buffett)",
        r"(s&p 500|dow jones|nasdaq|bitcoin|ethereum).*(high|crash|hit)",
        r"(fda|drug).*(approve|psychedelic|cannabis)",
    ]
    compelling_count = sum(1 for p in compelling_patterns if re.search(p, name))
    if compelling_count > 0:
        score += 8.0 * min(compelling_count, 3)

    # Obscure election penalty — local/regional elections nobody cares about
    obscure_election_patterns = [
        r"(mayoral|mayor).*(election|winner)",
        r"(hackney|newham|lewisham|watford|venice|watford|doncaster|croydon|tower hamlets)",
        r"(by-election|byelection|terrebone|b\.c\. conservative|chungche)",
        r"(wales|scotland).*(parliamentary|assembly).*(election|winner)",
        r"(andalusia|bavaria|saxony|thuringia|hesse).*(election|winner)",
        r"(yang seung|jorge nieto|fidesz)",
    ]
    if any(re.search(p, name) for p in obscure_election_patterns):
        score += -20.0

    return min(100, max(0, score))


def evaluate(weights: Weights, all_markets: list, gt_ids: set, top_n: int = 50) -> dict:
    """Score all markets, rank them, measure recall against ground truth."""
    scored = [(m["id"], score_market(m, weights)) for m in all_markets]
    scored.sort(key=lambda x: -x[1])

    top_ids = {mid for mid, _ in scored[:top_n]}
    top_100_ids = {mid for mid, _ in scored[:100]}
    top_200_ids = {mid for mid, _ in scored[:200]}

    recall_50 = len(gt_ids & top_ids) / len(gt_ids) if gt_ids else 0
    recall_100 = len(gt_ids & top_100_ids) / len(gt_ids) if gt_ids else 0
    recall_200 = len(gt_ids & top_200_ids) / len(gt_ids) if gt_ids else 0

    # Category diversity in top 50
    top_cats = Counter()
    for mid, _ in scored[:top_n]:
        m = next((m for m in all_markets if m["id"] == mid), None)
        if m:
            top_cats[(m.get("category") or "other").lower()] += 1

    non_sport_in_top = sum(c for cat, c in top_cats.items() if cat not in SPORTS_CATEGORIES)
    diversity = non_sport_in_top / top_n if top_n > 0 else 0

    return {
        "recall_50": recall_50,
        "recall_100": recall_100,
        "recall_200": recall_200,
        "diversity": diversity,
        "top_cats": dict(top_cats.most_common(10)),
        "score": recall_50 * 0.4 + recall_100 * 0.3 + diversity * 0.3,
    }


async def tune():
    from sqlalchemy import text
    from app.tasks.base import get_task_session

    # 1. Read ground truth
    print("Reading ground truth...")
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if not creds_json:
        print("No Google credentials"); return
    creds = service_account.Credentials.from_service_account_info(
        json.loads(creds_json), scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="Sheet1!A1:M1000"
    ).execute()
    rows = result.get("values", [])
    gt_names = []
    for row in rows[1:]:
        while len(row) < 13: row.append("")
        if row[2] and row[10]:
            gt_names.append(row[2].lower().strip())
    print(f"Ground truth: {len(gt_names)} markets")

    # 2. Load all open futures from DB
    print("Loading futures from DB...")
    async with get_task_session() as session:
        r = await session.execute(text("""
            SELECT fm.id, fm.name, fm.llm_sport_category, fm.market_tier,
                   fm.resolution_date, fm.source, fm.volume_24h,
                   (SELECT MAX(fo.current_probability) FROM futures_outcomes fo WHERE fo.market_id = fm.id) as leader_prob,
                   (SELECT MAX(ABS(fo.probability_change_24h)) FROM futures_outcomes fo WHERE fo.market_id = fm.id) as movement_24h,
                   (SELECT COUNT(DISTINCT fm2.source) FROM futures_markets fm2 WHERE fm2.canonical_market_key = fm.canonical_market_key AND fm2.canonical_market_key IS NOT NULL) as source_count
            FROM futures_markets fm
            WHERE fm.status = 'open' AND fm.event_id IS NULL
            ORDER BY fm.volume_24h DESC NULLS LAST
            LIMIT 5000
        """))
        db_rows = r.all()

    all_markets = []
    for row in db_rows:
        all_markets.append({
            "id": row.id,
            "name": row.name,
            "category": row.llm_sport_category,
            "market_tier": row.market_tier,
            "resolution_date": row.resolution_date,
            "source": row.source,
            "volume_24h": float(row.volume_24h) if row.volume_24h else 0,
            "leader_prob": float(row.leader_prob) if row.leader_prob else None,
            "movement_24h": float(row.movement_24h) if row.movement_24h else 0,
            "source_count": row.source_count or 1,
        })
    print(f"DB futures: {len(all_markets)}")

    # 3. Match ground truth to DB IDs
    from difflib import SequenceMatcher
    gt_ids = set()
    for gt_name in gt_names:
        best_id = None
        best_score = 0
        for m in all_markets:
            db_name = (m["name"] or "").lower().strip()
            if gt_name in db_name or db_name in gt_name:
                score = 0.95
            else:
                score = SequenceMatcher(None, gt_name[:50], db_name[:50]).ratio()
            if score > best_score and score > 0.5:
                best_score = score
                best_id = m["id"]
        if best_id:
            gt_ids.add(best_id)
    print(f"Matched ground truth IDs: {len(gt_ids)}")

    # 4. Hill-climb
    print(f"\n{'='*60}")
    print(f"HILL-CLIMBING (target: {TARGET_RECALL_AT_50:.0%} recall@50, {TARGET_RECALL_AT_100:.0%} recall@100)")
    print(f"{'='*60}")

    best_weights = Weights()
    best_eval = evaluate(best_weights, all_markets, gt_ids)
    print(f"\nBaseline: recall@50={best_eval['recall_50']:.1%} recall@100={best_eval['recall_100']:.1%} diversity={best_eval['diversity']:.1%} score={best_eval['score']:.3f}")
    print(f"  Top cats: {best_eval['top_cats']}")

    for i in range(MAX_ITERATIONS):
        candidate = best_weights.mutate(step=4.0 if i < 20 else 2.0)
        ev = evaluate(candidate, all_markets, gt_ids)

        if ev["score"] > best_eval["score"]:
            best_weights = candidate
            best_eval = ev
            print(f"  [{i+1:2d}] IMPROVED: recall@50={ev['recall_50']:.1%} recall@100={ev['recall_100']:.1%} diversity={ev['diversity']:.1%} score={ev['score']:.3f}")

        if best_eval["recall_50"] >= TARGET_RECALL_AT_50 and best_eval["recall_100"] >= TARGET_RECALL_AT_100:
            print(f"\n  TARGET REACHED at iteration {i+1}!")
            break

    # 5. Report
    print(f"\n{'='*60}")
    print("BEST WEIGHTS FOUND")
    print(f"{'='*60}")
    print(f"Recall@50:  {best_eval['recall_50']:.1%}")
    print(f"Recall@100: {best_eval['recall_100']:.1%}")
    print(f"Recall@200: {best_eval['recall_200']:.1%}")
    print(f"Diversity:  {best_eval['diversity']:.1%}")
    print(f"Top categories in feed top 50: {best_eval['top_cats']}")

    print(f"\n# Paste into futures_highlights.py:")
    print(f"CATEGORY_BASE_SCORES = {{")
    w = best_weights
    for cat, val in [
        ("politics", w.politics_base), ("geopolitics", w.geopolitics_base),
        ("economics", w.economics_base), ("tech", w.tech_base),
        ("entertainment", w.entertainment_base), ("culture", w.culture_base),
        ("health", w.health_base), ("weather", w.weather_base),
        ("crypto", w.crypto_base),
    ]:
        print(f'    "{cat}": {val:.1f},')
    print(f"}}")
    print(f"SPORTS_BASE = {w.sports_base:.1f}")
    print(f"RESOLVING_7D_BOOST = {w.resolving_soon_7d:.1f}")
    print(f"RESOLVING_30D_BOOST = {w.resolving_soon_30d:.1f}")
    print(f"MOVEMENT_LARGE_BOOST = {w.movement_large:.1f}  # >10% 24h")
    print(f"MOVEMENT_MEDIUM_BOOST = {w.movement_medium:.1f}  # >3% 24h")
    print(f"MULTI_SOURCE_BOOST = {w.multi_source:.1f}")
    print(f"DECISIVE_PROB_BOOST = {w.decisive_prob:.1f}  # leader 15-85%")
    print(f"HIGH_VOLUME_BOOST = {w.high_volume:.1f}  # vol > 1000")
    print(f"TIER_1_BOOST = {w.tier_1:.1f}")
    print(f"TIER_2_BOOST = {w.tier_2:.1f}")

    # Show what the new top 20 would look like
    print(f"\n--- SIMULATED FEED TOP 20 WITH NEW WEIGHTS ---")
    scored = [(m, score_market(m, best_weights)) for m in all_markets]
    scored.sort(key=lambda x: -x[1])
    for i, (m, s) in enumerate(scored[:20]):
        cat = (m.get("category") or "?").lower()
        gt_flag = " ★" if m["id"] in gt_ids else ""
        print(f"  #{i+1:2d} score={s:5.1f} [{cat:12s}] {m['name'][:50]}{gt_flag}")


def main():
    asyncio.run(tune())

if __name__ == "__main__":
    main()
