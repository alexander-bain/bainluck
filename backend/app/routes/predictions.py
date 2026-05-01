"""
Prediction tracking API for the Higher/Lower game.

Records guesses, returns stats (streak, accuracy, category breakdown, badges, trend).
"""

from datetime import datetime, timezone, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select, func, desc, cast, Integer, case
from app.services import get_db as get_session
from app.models.models import UserPrediction, FuturesMarket

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class PredictionSubmission(BaseModel):
    market_id: int
    guess: str
    threshold: int
    actual_probability: float
    correct: bool
    category: str | None = None


def _get_identity(request: Request) -> tuple[int | None, str | None]:
    """Extract user_id (if authenticated) and session_id."""
    session_id = request.cookies.get("session_id") or request.headers.get("x-session-id")
    user_id = getattr(request.state, "user_id", None)
    return user_id, session_id


def _identity_filter(user_id: int | None, session_id: str | None):
    """Build SQLAlchemy filter for user identity (prefer user_id)."""
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
async def submit_prediction(body: PredictionSubmission, request: Request):
    user_id, session_id = _get_identity(request)
    async with get_session() as session:
        pred = UserPrediction(
            user_id=user_id,
            session_id=session_id,
            market_id=body.market_id,
            guess=body.guess,
            threshold=body.threshold,
            actual_probability=body.actual_probability,
            correct=body.correct,
        )
        session.add(pred)
        await session.commit()
    return {"status": "ok"}


@router.get("/stats")
async def get_stats(request: Request):
    user_id, session_id = _get_identity(request)
    identity = _identity_filter(user_id, session_id)

    async with get_session() as session:
        result = await session.execute(
            select(
                func.count(UserPrediction.id).label("total"),
                func.count(case((UserPrediction.correct == True, 1))).label("correct"),
            ).where(identity)
        )
        row = result.one()
        total = row.total or 0
        correct = row.correct or 0
        accuracy = correct / total if total > 0 else 0

        preds_result = await session.execute(
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
async def get_detailed_stats(request: Request):
    user_id, session_id = _get_identity(request)
    identity = _identity_filter(user_id, session_id)

    async with get_session() as session:
        # All predictions with market info
        result = await session.execute(
            select(UserPrediction, FuturesMarket.name, FuturesMarket.llm_sport_category)
            .outerjoin(FuturesMarket, UserPrediction.market_id == FuturesMarket.id)
            .where(identity)
            .order_by(desc(UserPrediction.created_at))
        )
        rows = result.all()

        total = len(rows)
        correct = sum(1 for r in rows if r[0].correct)
        accuracy = correct / total if total > 0 else 0

        preds_ordered = [r[0].correct for r in rows]
        current_streak, best_streak = _compute_streaks(preds_ordered)

        # Category breakdown
        by_category: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})
        for pred, name, cat in rows:
            c = cat or "other"
            by_category[c]["total"] += 1
            if pred.correct:
                by_category[c]["correct"] += 1
        for v in by_category.values():
            v["accuracy"] = round(v["correct"] / v["total"], 3) if v["total"] > 0 else 0

        # Trend (daily accuracy for last 14 days)
        trend = []
        now = datetime.now(timezone.utc)
        for days_ago in range(13, -1, -1):
            day = (now - timedelta(days=days_ago)).date()
            day_preds = [r for r in rows if r[0].created_at and r[0].created_at.date() == day]
            if day_preds:
                day_total = len(day_preds)
                day_correct = sum(1 for r in day_preds if r[0].correct)
                trend.append({"date": day.isoformat(), "total": day_total, "correct": day_correct, "accuracy": round(day_correct / day_total, 3)})

        # Badges
        badges = _compute_badges(total, correct, best_streak)

        # Recent predictions
        recent = []
        for pred, name, cat in rows[:20]:
            recent.append({
                "market_name": name or f"Market #{pred.market_id}",
                "category": cat,
                "guess": pred.guess,
                "threshold": pred.threshold,
                "actual": round(float(pred.actual_probability) * 100),
                "correct": pred.correct,
                "created_at": pred.created_at.isoformat() if pred.created_at else None,
            })

    return {
        "total": total, "correct": correct, "accuracy": round(accuracy, 3),
        "current_streak": current_streak, "best_streak": best_streak,
        "by_category": dict(by_category),
        "trend": trend,
        "badges": badges,
        "recent": recent,
    }


# Seen tracking endpoints temporarily disabled — will re-add after
# migration tree is cleaned up. The user_seen_markets table exists
# in the DB but the migration file was removed to unblock deploys.
