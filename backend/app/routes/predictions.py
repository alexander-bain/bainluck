"""
Prediction tracking API for the Higher/Lower game.

Records guesses, returns stats (streak, accuracy, category breakdown, badges, trend).
"""

from datetime import datetime, timezone, timedelta
from collections import defaultdict

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, func, desc, cast, Integer, case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.services import get_db, get_db_rw
from app.models.models import UserPrediction, FuturesMarket, FuturesOutcome, User
from app.dependencies.auth import get_optional_user

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class PredictionSubmission(BaseModel):
    market_id: int
    guess: str
    threshold: int
    actual_probability: float
    correct: bool
    category: str | None = None


def _get_identity(request: Request, user: Optional[User] = None) -> tuple[int | None, str | None]:
    """Extract user_id (if authenticated) and session_id."""
    session_id = request.cookies.get("session_id") or request.headers.get("x-session-id")
    user_id = user.id if user else getattr(request.state, "user_id", None)
    return user_id, session_id


def _identity_filter(user_id: int | None, session_id: str | None):
    """Build SQLAlchemy filter for user identity."""
    if user_id and session_id:
        return or_(
            UserPrediction.user_id == user_id,
            UserPrediction.session_id == session_id,
        )
    if user_id:
        return UserPrediction.user_id == user_id
    if session_id:
        return UserPrediction.session_id == session_id
    return UserPrediction.id < 0  # No identity — return nothing


def _compute_streaks(correct_list: list[bool]) -> tuple[int, int]:
    current = 0
    for p in correct_list:
        if p:
            current += 1
        else:
            break
    best = 0
    streak = 0
    for p in reversed(correct_list):
        if p:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return current, best


BADGES = [
    ("first_guess", "First Guess", "🎯", 1),
    ("streak_3", "Hot Start", "🔥", None),
    ("streak_5", "On Fire", "🔥🔥", None),
    ("streak_10", "Unstoppable", "🔥🔥🔥", None),
    ("total_10", "Getting Started", "📊", 10),
    ("total_25", "Regular", "📊📊", 25),
    ("total_50", "Dedicated", "📊📊📊", 50),
    ("total_100", "Centurion", "💯", 100),
    ("accuracy_75", "Sharp Eye", "🎯", None),
]


def _compute_badges(total: int, correct: int, best_streak: int) -> list[dict]:
    badges = []
    accuracy = correct / total if total > 0 else 0
    if total >= 1:
        badges.append({"id": "first_guess", "name": "First Guess", "emoji": "🎯"})
    if best_streak >= 3:
        badges.append({"id": "streak_3", "name": "Hot Start", "emoji": "🔥"})
    if best_streak >= 5:
        badges.append({"id": "streak_5", "name": "On Fire", "emoji": "🔥🔥"})
    if best_streak >= 10:
        badges.append({"id": "streak_10", "name": "Unstoppable", "emoji": "🔥🔥🔥"})
    if total >= 10:
        badges.append({"id": "total_10", "name": "Getting Started", "emoji": "📊"})
    if total >= 25:
        badges.append({"id": "total_25", "name": "Regular", "emoji": "📊📊"})
    if total >= 50:
        badges.append({"id": "total_50", "name": "Dedicated", "emoji": "📊📊📊"})
    if total >= 100:
        badges.append({"id": "total_100", "name": "Centurion", "emoji": "💯"})
    if total >= 10 and accuracy >= 0.75:
        badges.append({"id": "accuracy_75", "name": "Sharp Eye", "emoji": "🎯"})
    return badges


@router.post("")
async def submit_prediction(
    body: PredictionSubmission,
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db_rw),
):
    user_id = user.id if user else None
    session_id = request.cookies.get("session_id") or request.headers.get("x-session-id")

    actual_probability = body.actual_probability
    correct = body.correct

    outcome_result = await db.execute(
        select(FuturesOutcome.current_probability)
        .where(FuturesOutcome.market_id == body.market_id)
        .order_by(FuturesOutcome.current_probability.desc())
        .limit(1)
    )
    server_prob = outcome_result.scalar()
    if server_prob is not None:
        actual_probability = float(server_prob)
        actual_pct = int(actual_probability * 100)
        correct = (
            (body.guess == "higher" and actual_pct > body.threshold)
            or (body.guess == "lower" and actual_pct < body.threshold)
        )

    pred = UserPrediction(
        user_id=user_id,
        session_id=session_id,
        market_id=body.market_id,
        guess=body.guess,
        threshold=body.threshold,
        actual_probability=actual_probability,
        correct=correct,
    )
    db.add(pred)
    await db.commit()
    return {"status": "ok"}


@router.get("/stats")
async def get_stats(
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    user_id, session_id = _get_identity(request, user)
    identity = _identity_filter(user_id, session_id)

    result = await db.execute(
        select(
            func.count(UserPrediction.id).label("total"),
            func.count(case((UserPrediction.correct == True, 1))).label("correct"),
        ).where(identity)
    )
    row = result.one()
    total = row.total or 0
    correct = row.correct or 0
    accuracy = correct / total if total > 0 else 0

    preds_result = await db.execute(
        select(UserPrediction.correct).where(identity).order_by(desc(UserPrediction.created_at))
    )
    preds = [r.correct for r in preds_result.all()]
    current_streak, best_streak = _compute_streaks(preds)

    return {
        "total": total, "correct": correct,
        "accuracy": round(accuracy, 3),
        "current_streak": current_streak, "best_streak": best_streak,
    }


@router.get("/detailed-stats")
async def get_detailed_stats(
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    user_id, session_id = _get_identity(request, user)
    identity = _identity_filter(user_id, session_id)

    totals_result = await db.execute(
        select(
            func.count(UserPrediction.id).label("total"),
            func.count(case((UserPrediction.correct == True, 1))).label("correct"),
        ).where(identity)
    )
    totals = totals_result.one()
    total = totals.total or 0
    correct = totals.correct or 0
    accuracy = correct / total if total > 0 else 0

    cat_col = func.coalesce(FuturesMarket.llm_sport_category, "other")
    cat_result = await db.execute(
        select(
            cat_col.label("cat"),
            func.count(UserPrediction.id).label("total"),
            func.count(case((UserPrediction.correct == True, 1))).label("correct"),
        )
        .outerjoin(FuturesMarket, UserPrediction.market_id == FuturesMarket.id)
        .where(identity)
        .group_by(cat_col)
    )
    by_category = {}
    for r in cat_result.all():
        by_category[r.cat] = {
            "total": r.total, "correct": r.correct,
            "accuracy": round(r.correct / r.total, 3) if r.total > 0 else 0,
        }

    from sqlalchemy import Date
    trend_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    day_col = cast(UserPrediction.created_at, Date)
    trend_result = await db.execute(
        select(
            day_col.label("day"),
            func.count(UserPrediction.id).label("total"),
            func.count(case((UserPrediction.correct == True, 1))).label("correct"),
        )
        .where(identity, UserPrediction.created_at >= trend_cutoff)
        .group_by(day_col)
        .order_by(day_col)
    )
    trend = [
        {"date": r.day.isoformat(), "total": r.total, "correct": r.correct,
         "accuracy": round(r.correct / r.total, 3) if r.total > 0 else 0}
        for r in trend_result.all()
    ]

    streak_result = await db.execute(
        select(UserPrediction.correct)
        .where(identity)
        .order_by(desc(UserPrediction.created_at))
        .limit(1000)
    )
    preds_ordered = [r.correct for r in streak_result.all()]
    current_streak, best_streak = _compute_streaks(preds_ordered)

    badges = _compute_badges(total, correct, best_streak)

    recent_result = await db.execute(
        select(UserPrediction, FuturesMarket.name, FuturesMarket.llm_sport_category)
        .outerjoin(FuturesMarket, UserPrediction.market_id == FuturesMarket.id)
        .where(identity)
        .order_by(desc(UserPrediction.created_at))
        .limit(20)
    )
    recent = [
        {
            "market_name": name or f"Market #{pred.market_id}",
            "category": cat,
            "guess": pred.guess,
            "threshold": pred.threshold,
            "actual": round(float(pred.actual_probability) * 100),
            "correct": pred.correct,
            "created_at": pred.created_at.isoformat() if pred.created_at else None,
        }
        for pred, name, cat in recent_result.all()
    ]

    return {
        "total": total, "correct": correct, "accuracy": round(accuracy, 3),
        "current_streak": current_streak, "best_streak": best_streak,
        "by_category": by_category,
        "trend": trend,
        "badges": badges,
        "recent": recent,
    }


@router.get("/resolutions")
async def get_resolutions(
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Return predictions on markets that have since resolved."""
    user_id, session_id = _get_identity(request, user)
    identity = _identity_filter(user_id, session_id)
    if identity is None:
        return {"resolutions": []}

    result = await db.execute(
        select(UserPrediction, FuturesMarket.name, FuturesMarket.llm_sport_category)
        .join(FuturesMarket, UserPrediction.market_id == FuturesMarket.id)
        .where(
            identity,
            FuturesMarket.status.in_(("resolved", "closed")),
        )
        .order_by(desc(UserPrediction.created_at))
        .limit(20)
    )
    rows = result.all()

    return {
        "resolutions": [
            {
                "market_name": name or f"Market #{pred.market_id}",
                "category": cat,
                "guess": pred.guess,
                "threshold": pred.threshold,
                "actual": round(float(pred.actual_probability) * 100),
                "correct": pred.correct,
                "created_at": pred.created_at.isoformat() if pred.created_at else None,
            }
            for pred, name, cat in rows
        ],
    }


# Seen tracking endpoints temporarily disabled — will re-add after
# migration tree is cleaned up. The user_seen_markets table exists
# in the DB but the migration file was removed to unblock deploys.
