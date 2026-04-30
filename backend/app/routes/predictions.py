"""
Prediction tracking API for the Higher/Lower game.

Records guesses, returns stats (streak, accuracy, total).
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from app.database import get_session
from app.models.models import UserPrediction

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class PredictionSubmission(BaseModel):
    market_id: int
    guess: str  # "higher" or "lower"
    threshold: int
    actual_probability: float
    correct: bool


class PredictionStats(BaseModel):
    total: int
    correct: int
    accuracy: float
    current_streak: int
    best_streak: int


@router.post("")
async def submit_prediction(body: PredictionSubmission, request: Request):
    """Record a Higher/Lower guess."""
    session_id = request.cookies.get("session_id") or request.headers.get("x-session-id")

    async with get_session() as session:
        pred = UserPrediction(
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
    """Get prediction stats for the current session."""
    session_id = request.cookies.get("session_id") or request.headers.get("x-session-id")
    if not session_id:
        return PredictionStats(total=0, correct=0, accuracy=0, current_streak=0, best_streak=0)

    async with get_session() as session:
        # Total + correct
        result = await session.execute(
            select(
                func.count(UserPrediction.id).label("total"),
                func.sum(func.cast(UserPrediction.correct, type_=func.literal(1).__class__)).label("correct"),
            )
            .where(UserPrediction.session_id == session_id)
        )
        row = result.one()
        total = row.total or 0
        correct = int(row.correct or 0)
        accuracy = correct / total if total > 0 else 0

        # Streak calculation
        preds_result = await session.execute(
            select(UserPrediction.correct)
            .where(UserPrediction.session_id == session_id)
            .order_by(desc(UserPrediction.created_at))
        )
        preds = [r.correct for r in preds_result.all()]

        current_streak = 0
        for p in preds:
            if p:
                current_streak += 1
            else:
                break

        best_streak = 0
        streak = 0
        for p in reversed(preds):
            if p:
                streak += 1
                best_streak = max(best_streak, streak)
            else:
                streak = 0

    return PredictionStats(
        total=total,
        correct=correct,
        accuracy=round(accuracy, 3),
        current_streak=current_streak,
        best_streak=best_streak,
    )
