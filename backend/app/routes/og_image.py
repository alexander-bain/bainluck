"""
OG Image generation for shareable prediction cards.

Returns an HTML page that renders as a card image when shared on social media.
Uses Vercel/Next.js OG image generation or server-side HTML rendering.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from app.database import get_session
from app.models.models import FuturesMarket, FuturesOutcome

router = APIRouter(prefix="/api/og", tags=["og"])


@router.get("/prediction")
async def prediction_card(
    market_id: int,
    guess: str = "higher",
    correct: bool = True,
    threshold: int = 50,
    actual: int = 65,
):
    """Generate an OG-compatible HTML card for a prediction share."""

    # Fetch market name
    market_name = "Prediction Market"
    async with get_session() as session:
        result = await session.execute(
            select(FuturesMarket.name, FuturesMarket.llm_sport_category)
            .where(FuturesMarket.id == market_id)
        )
        row = result.one_or_none()
        if row:
            market_name = row.name
            category = row.llm_sport_category or "markets"

    badge_color = "#16a34a" if correct else "#dc2626"
    badge_text = "✓ Correct!" if correct else "✗ Not quite"
    bg_gradient = "linear-gradient(135deg, #0f172a, #1e293b)"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta property="og:title" content="{'I got it right!' if correct else 'So close!'} — {market_name}" />
<meta property="og:description" content="I guessed {guess} than {threshold}% — actual was {actual}%. Play at bainluck.com/discover" />
<meta property="og:image" content="https://api.bainluck.com/api/og/prediction/image?market_id={market_id}&guess={guess}&correct={correct}&threshold={threshold}&actual={actual}" />
<meta property="og:url" content="https://bainluck.com/discover" />
<meta name="twitter:card" content="summary_large_image" />
<style>
  body {{ margin: 0; display: flex; align-items: center; justify-content: center; min-height: 100vh; background: #f1f5f9; font-family: -apple-system, system-ui, sans-serif; }}
  .card {{ width: 600px; border-radius: 24px; overflow: hidden; box-shadow: 0 20px 60px rgba(0,0,0,0.15); }}
  .hero {{ background: {bg_gradient}; padding: 40px; text-align: center; color: white; }}
  .badge {{ display: inline-block; background: {badge_color}; color: white; padding: 6px 16px; border-radius: 20px; font-size: 14px; font-weight: 800; margin-bottom: 16px; }}
  .prob {{ font-size: 72px; font-weight: 900; letter-spacing: -2px; }}
  .label {{ font-size: 14px; opacity: 0.7; margin-top: 8px; }}
  .content {{ padding: 24px 32px; background: white; }}
  .title {{ font-size: 18px; font-weight: 700; margin-bottom: 8px; }}
  .meta {{ font-size: 13px; color: #64748b; }}
  .footer {{ padding: 16px 32px; background: #f8fafc; border-top: 1px solid #e2e8f0; display: flex; align-items: center; justify-content: space-between; }}
  .logo {{ font-weight: 900; font-size: 14px; color: #0f172a; }}
  .cta {{ font-size: 12px; color: #3b82f6; font-weight: 600; }}
</style>
</head>
<body>
<div class="card">
  <div class="hero">
    <div class="badge">{badge_text}</div>
    <div class="prob">{actual}%</div>
    <div class="label">I guessed {guess} than {threshold}%</div>
  </div>
  <div class="content">
    <div class="title">{market_name}</div>
    <div class="meta">Actual probability: {actual}% · Threshold: {threshold}%</div>
  </div>
  <div class="footer">
    <span class="logo">⚡ Bain Luck</span>
    <span class="cta">Play at bainluck.com/discover →</span>
  </div>
</div>
</body>
</html>"""
    return HTMLResponse(content=html)
