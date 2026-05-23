"""
Push notification tasks: daily challenge + big move alerts.

Daily challenge push: sent once daily at 2 PM UTC to all users with
active device tokens who have not opted out.

Big move alerts: sent every 30 min for futures markets with >15pp
movement in the last 30 minutes, targeted at users who pinned those
markets.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DeviceToken, FuturesMarket, FuturesOutcome, User, UserPin

logger = logging.getLogger(__name__)

# Minimum absolute movement (in probability points, 0-1 scale) to trigger an alert
BIG_MOVE_THRESHOLD = 0.15  # 15 percentage points


async def _send_daily_challenge_push() -> dict:
    """Send daily challenge notification to all opted-in device tokens."""
    from app.tasks.base import get_task_session

    sent = 0
    failed = 0
    skipped = 0

    async with get_task_session() as db:
        # Get all active device tokens, joined to user for preference check
        result = await db.execute(
            select(DeviceToken, User)
            .outerjoin(User, DeviceToken.user_id == User.id)
            .where(DeviceToken.is_active.is_(True))
        )
        rows = result.all()

        if not rows:
            logger.info("No active device tokens — skipping daily challenge push")
            return {"sent": 0, "skipped": 0, "failed": 0, "reason": "no_tokens"}

        for device_token, user in rows:
            # Check push preferences — default True if no user or no prefs set
            if user and isinstance(user.push_preferences, dict):
                if not user.push_preferences.get("daily_challenge", True):
                    skipped += 1
                    continue

            try:
                _send_fcm_message(
                    token=device_token.device_token,
                    title="Daily Challenge Ready!",
                    body="Today's challenge is ready! Can you keep your streak going?",
                    data={"type": "daily_challenge", "url": "/discover"},
                )
                sent += 1
            except _InvalidTokenError:
                # Token is stale — mark inactive
                await db.execute(
                    sa_update(DeviceToken)
                    .where(DeviceToken.id == device_token.id)
                    .values(is_active=False)
                )
                failed += 1
            except Exception as exc:
                logger.warning(
                    "Failed to send daily challenge push to token %s...%s: %s",
                    device_token.device_token[:8],
                    device_token.device_token[-4:],
                    exc,
                )
                failed += 1

    logger.info(
        "Daily challenge push: sent=%d skipped=%d failed=%d", sent, skipped, failed
    )
    return {"sent": sent, "skipped": skipped, "failed": failed}


async def _send_big_move_alerts() -> dict:
    """Find markets with big moves and alert users who pinned them."""
    from app.tasks.base import get_task_session

    sent = 0
    failed = 0
    skipped = 0
    markets_alerted = 0

    async with get_task_session() as db:
        # Find futures markets with outcomes that moved >15pp in the last update cycle
        # We use max_movement_24h on the market as a fast pre-filter, then check
        # individual outcome probability_change_24h for precision.
        big_movers = await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesOutcome.name.label("outcome_name"),
                FuturesOutcome.probability_change_24h,
                FuturesOutcome.current_probability,
            )
            .join(FuturesOutcome, FuturesOutcome.market_id == FuturesMarket.id)
            .where(
                and_(
                    FuturesMarket.status.in_(["open", "active"]),
                    FuturesOutcome.probability_change_24h.isnot(None),
                    # Use abs() in Python — SQLAlchemy func.abs works on Numeric
                    FuturesOutcome.probability_change_24h >= BIG_MOVE_THRESHOLD,
                )
            )
        )
        # Also check negative moves
        big_movers_neg = await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesOutcome.name.label("outcome_name"),
                FuturesOutcome.probability_change_24h,
                FuturesOutcome.current_probability,
            )
            .join(FuturesOutcome, FuturesOutcome.market_id == FuturesMarket.id)
            .where(
                and_(
                    FuturesMarket.status.in_(["open", "active"]),
                    FuturesOutcome.probability_change_24h.isnot(None),
                    FuturesOutcome.probability_change_24h <= -BIG_MOVE_THRESHOLD,
                )
            )
        )

        # Combine positive and negative movers, dedup by market_id
        movers_by_market: dict[int, dict] = {}
        for row in list(big_movers.all()) + list(big_movers_neg.all()):
            market_id = row[0]
            if market_id not in movers_by_market:
                movers_by_market[market_id] = {
                    "market_id": market_id,
                    "market_name": row[1],
                    "outcome_name": row[2],
                    "change": float(row[3]) if row[3] is not None else 0,
                    "probability": float(row[4]) if row[4] is not None else 0,
                }
            else:
                # Keep the outcome with the largest absolute move
                existing_change = abs(movers_by_market[market_id]["change"])
                new_change = abs(float(row[3])) if row[3] is not None else 0
                if new_change > existing_change:
                    movers_by_market[market_id] = {
                        "market_id": market_id,
                        "market_name": row[1],
                        "outcome_name": row[2],
                        "change": float(row[3]) if row[3] is not None else 0,
                        "probability": float(row[4]) if row[4] is not None else 0,
                    }

        if not movers_by_market:
            logger.info("No big movers found — skipping alerts")
            return {
                "sent": 0,
                "skipped": 0,
                "failed": 0,
                "markets_checked": 0,
            }

        # Find users who pinned these markets
        market_ids = list(movers_by_market.keys())
        pinned = await db.execute(
            select(UserPin.user_id, UserPin.target_id)
            .where(
                and_(
                    UserPin.pin_type == "future",
                    UserPin.target_id.in_(market_ids),
                )
            )
        )
        pin_rows = pinned.all()

        if not pin_rows:
            logger.info(
                "No users pinned the %d big-mover markets", len(market_ids)
            )
            return {
                "sent": 0,
                "skipped": 0,
                "failed": 0,
                "markets_checked": len(market_ids),
            }

        # Group by user_id → list of market_ids they pinned
        user_markets: dict[int, list[int]] = {}
        for user_id, target_id in pin_rows:
            user_markets.setdefault(user_id, []).append(target_id)

        # Get device tokens for these users
        user_ids = list(user_markets.keys())
        tokens_result = await db.execute(
            select(DeviceToken, User)
            .outerjoin(User, DeviceToken.user_id == User.id)
            .where(
                and_(
                    DeviceToken.user_id.in_(user_ids),
                    DeviceToken.is_active.is_(True),
                )
            )
        )
        token_rows = tokens_result.all()

        for device_token, user in token_rows:
            # Check push preferences
            if user and isinstance(user.push_preferences, dict):
                if not user.push_preferences.get("big_moves", True):
                    skipped += 1
                    continue

            # Find the most dramatic move among this user's pinned markets
            pinned_market_ids = user_markets.get(device_token.user_id, [])
            best_mover = None
            best_abs_change = 0
            for mid in pinned_market_ids:
                mover = movers_by_market.get(mid)
                if mover and abs(mover["change"]) > best_abs_change:
                    best_mover = mover
                    best_abs_change = abs(mover["change"])

            if not best_mover:
                continue

            markets_alerted += 1
            change_pp = round(best_mover["change"] * 100, 1)
            direction = "up" if change_pp > 0 else "down"
            abs_change = abs(change_pp)

            body = (
                f"{best_mover['outcome_name']} is {direction} {abs_change}pp "
                f"in {best_mover['market_name']}"
            )

            try:
                _send_fcm_message(
                    token=device_token.device_token,
                    title="Big Move Alert",
                    body=body,
                    data={
                        "type": "big_move",
                        "market_id": str(best_mover["market_id"]),
                        "url": f"/futures/{best_mover['market_id']}",
                    },
                )
                sent += 1
            except _InvalidTokenError:
                await db.execute(
                    sa_update(DeviceToken)
                    .where(DeviceToken.id == device_token.id)
                    .values(is_active=False)
                )
                failed += 1
            except Exception as exc:
                logger.warning(
                    "Failed to send big move alert to token %s...%s: %s",
                    device_token.device_token[:8],
                    device_token.device_token[-4:],
                    exc,
                )
                failed += 1

    logger.info(
        "Big move alerts: sent=%d skipped=%d failed=%d markets=%d",
        sent, skipped, failed, markets_alerted,
    )
    return {
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "markets_alerted": markets_alerted,
    }


# ---------------------------------------------------------------------------
# Firebase Cloud Messaging helpers
# ---------------------------------------------------------------------------


class _InvalidTokenError(Exception):
    """Raised when an FCM token is invalid/expired and should be deactivated."""


def _send_fcm_message(
    token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> str:
    """Send a push notification via Firebase Cloud Messaging.

    Returns the FCM message ID on success.
    Raises _InvalidTokenError if the token is stale.
    Raises Exception for other failures.
    """
    from firebase_admin import messaging

    from app.services.firebase_auth import _init_firebase

    if not _init_firebase():
        raise RuntimeError("Firebase Admin SDK not configured")

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    alert=messaging.ApsAlert(title=title, body=body),
                    sound="default",
                ),
            ),
        ),
        data=data or {},
        token=token,
    )

    try:
        return messaging.send(message)
    except messaging.UnregisteredError:
        raise _InvalidTokenError(f"Token {token[:8]}... is unregistered")
    except messaging.InvalidArgumentError as exc:
        if "not a valid FCM registration token" in str(exc).lower():
            raise _InvalidTokenError(str(exc))
        raise
