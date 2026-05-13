"""Daily digest email: top movers, interesting markets, resolved predictions.

Sends a morning email to opted-in users summarizing what's happening
on Bain Luck. Uses Gmail API via the same OAuth2 setup as bug notifications.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FuturesMarket, FuturesOutcome
from app.tasks.bug_notifications import _send_gmail, _generate_email_body

logger = logging.getLogger(__name__)


async def build_digest_content(db: AsyncSession) -> dict:
    """Build the daily digest data: top movers, resolving soon, new markets."""
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=24)
    tomorrow = now + timedelta(hours=24)

    # Top movers: markets with biggest 24h probability change
    movers_query = (
        select(
            FuturesOutcome.name,
            FuturesOutcome.current_probability,
            FuturesOutcome.probability_change_24h,
            FuturesMarket.name.label("market_name"),
            FuturesMarket.source,
        )
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesMarket.status == "open",
            FuturesOutcome.probability_change_24h.isnot(None),
            FuturesOutcome.current_probability > 0.05,
            FuturesOutcome.current_probability < 0.95,
        )
        .order_by(func.abs(FuturesOutcome.probability_change_24h).desc())
        .limit(5)
    )
    movers_result = await db.execute(movers_query)
    movers = [
        {
            "outcome": row.name,
            "market": row.market_name,
            "probability": float(row.current_probability) if row.current_probability else 0,
            "change": float(row.probability_change_24h) if row.probability_change_24h else 0,
            "source": row.source,
        }
        for row in movers_result.all()
    ]

    # Resolving soon: markets closing in the next 24h
    resolving_query = (
        select(
            FuturesMarket.name,
            FuturesMarket.resolution_date,
            FuturesMarket.source,
        )
        .where(
            FuturesMarket.status == "open",
            FuturesMarket.resolution_date.isnot(None),
            FuturesMarket.resolution_date.between(now, tomorrow),
        )
        .order_by(FuturesMarket.resolution_date)
        .limit(5)
    )
    resolving_result = await db.execute(resolving_query)
    resolving = [
        {
            "name": row.name,
            "resolves": row.resolution_date.strftime("%b %d, %I:%M %p") if row.resolution_date else "soon",
            "source": row.source,
        }
        for row in resolving_result.all()
    ]

    return {
        "movers": movers,
        "resolving": resolving,
        "date": now.strftime("%A, %B %d"),
    }


def format_digest_html(digest: dict) -> str:
    """Format the digest data into an HTML email body."""
    movers_html = ""
    for m in digest["movers"]:
        direction = "📈" if m["change"] > 0 else "📉"
        change_pct = f"{m['change']*100:+.1f}pp"
        prob_pct = f"{m['probability']*100:.0f}%"
        movers_html += f"""
        <tr>
            <td style="padding: 8px 0; border-bottom: 1px solid #f0f0f0;">
                <div style="font-size: 14px; font-weight: 600; color: #1a1a1a;">{direction} {m['outcome']}</div>
                <div style="font-size: 12px; color: #6b7280; margin-top: 2px;">{m['market']}</div>
            </td>
            <td style="padding: 8px 0; border-bottom: 1px solid #f0f0f0; text-align: right; white-space: nowrap;">
                <div style="font-size: 16px; font-weight: 800; font-family: monospace; color: #1a1a1a;">{prob_pct}</div>
                <div style="font-size: 11px; color: {'#16a34a' if m['change'] > 0 else '#dc2626'}; font-weight: 600;">{change_pct}</div>
            </td>
        </tr>"""

    resolving_html = ""
    for r in digest["resolving"]:
        resolving_html += f"""
        <tr>
            <td style="padding: 6px 0; border-bottom: 1px solid #f0f0f0;">
                <div style="font-size: 13px; color: #1a1a1a;">{r['name']}</div>
            </td>
            <td style="padding: 6px 0; border-bottom: 1px solid #f0f0f0; text-align: right; font-size: 12px; color: #6b7280;">
                {r['resolves']}
            </td>
        </tr>"""

    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 520px; margin: 0 auto; color: #1a1a1a;">
        <div style="text-align: center; padding: 24px 0 16px;">
            <div style="font-size: 32px;">🍀</div>
            <h1 style="font-size: 20px; font-weight: 800; margin: 8px 0 4px;">Bain Luck Daily</h1>
            <p style="font-size: 13px; color: #6b7280; margin: 0;">{digest['date']}</p>
        </div>

        {'<div style="margin: 16px 0;"><h2 style="font-size: 14px; font-weight: 700; color: #1a1a1a; margin: 0 0 8px; text-transform: uppercase; letter-spacing: 0.5px;">Biggest Movers (24h)</h2><table style="width: 100%; border-collapse: collapse;">' + movers_html + '</table></div>' if movers_html else ''}

        {'<div style="margin: 16px 0;"><h2 style="font-size: 14px; font-weight: 700; color: #1a1a1a; margin: 0 0 8px; text-transform: uppercase; letter-spacing: 0.5px;">Resolving Soon</h2><table style="width: 100%; border-collapse: collapse;">' + resolving_html + '</table></div>' if resolving_html else ''}

        <div style="text-align: center; padding: 24px 0;">
            <a href="https://bainluck.com" style="display: inline-block; background: #1a1a1a; color: white; padding: 12px 32px; border-radius: 10px; text-decoration: none; font-size: 14px; font-weight: 700;">Open Bain Luck</a>
        </div>

        <p style="font-size: 11px; color: #9ca3af; text-align: center; margin-top: 16px;">
            You're receiving this because you opted in on Bain Luck.
            <a href="https://bainluck.com/preferences" style="color: #6b7280;">Manage preferences</a>
        </p>
    </div>
    """


async def send_daily_digest(db: AsyncSession, to_email: str) -> bool:
    """Build and send the daily digest to a single recipient."""
    try:
        digest = await build_digest_content(db)

        if not digest["movers"] and not digest["resolving"]:
            logger.info("No digest content to send")
            return False

        html = format_digest_html(digest)
        subject = f"🍀 Bain Luck Daily — {digest['date']}"

        return _send_gmail(to_email=to_email, subject=subject, body_html=html)
    except Exception as e:
        logger.error("Failed to build/send daily digest: %s", e)
        return False
