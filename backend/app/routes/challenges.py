"""
Friend Challenge API — shareable Higher/Lower prediction challenges.

Create a challenge, share the link, friend accepts with their guess.
No account required for the friend.
"""

import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.models.models import PredictionChallenge, FuturesMarket, FuturesOutcome
from app.services import get_db as get_session

router = APIRouter()

FRONTEND_BASE = "https://bainluck.com"


# ---------- Request / Response schemas ----------

class CreateChallengeRequest(BaseModel):
    market_id: int
    guess: str  # "higher" or "lower"
    threshold: int


class AcceptChallengeRequest(BaseModel):
    guess: str  # "higher" or "lower"


# ---------- Helpers ----------

def _generate_code() -> str:
    """Generate a short shareable challenge code like 'BL-abc123'."""
    return f"BL-{secrets.token_urlsafe(6)}"


# ---------- Routes ----------

@router.post("")
async def create_challenge(body: CreateChallengeRequest, request: Request):
    """Create a new friend challenge and return a shareable URL."""
    if body.guess not in ("higher", "lower"):
        raise HTTPException(status_code=400, detail="guess must be 'higher' or 'lower'")

    session_id = request.cookies.get("session_id") or request.headers.get("x-session-id")
    user_id = getattr(request.state, "user_id", None)

    async with get_session() as db:
        # Verify market exists and grab its name
        market_result = await db.execute(
            select(FuturesMarket.id, FuturesMarket.name)
            .where(FuturesMarket.id == body.market_id)
        )
        market_row = market_result.first()
        if not market_row:
            raise HTTPException(status_code=404, detail="Market not found")

        # Generate unique code (retry on collision — astronomically unlikely)
        for _ in range(5):
            code = _generate_code()
            exists = await db.execute(
                select(PredictionChallenge.id)
                .where(PredictionChallenge.challenge_code == code)
            )
            if not exists.scalar():
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate unique code")

        challenge = PredictionChallenge(
            creator_user_id=user_id,
            creator_session_id=session_id,
            challenge_code=code,
            market_id=body.market_id,
            market_name=market_row.name,
            creator_guess=body.guess,
            creator_threshold=body.threshold,
        )
        db.add(challenge)
        await db.commit()
        await db.refresh(challenge)

    return {
        "challenge_code": code,
        "url": f"{FRONTEND_BASE}/challenge/{code}",
        "market_name": market_row.name,
        "creator_guess": body.guess,
        "threshold": body.threshold,
    }


@router.get("/{code}")
async def get_challenge(code: str):
    """Get challenge details for the friend landing page."""
    async with get_session() as db:
        result = await db.execute(
            select(PredictionChallenge)
            .where(PredictionChallenge.challenge_code == code)
        )
        challenge = result.scalar()
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")

        # Get current probability for the market's top outcome
        prob_result = await db.execute(
            select(FuturesOutcome.current_probability)
            .where(FuturesOutcome.market_id == challenge.market_id)
            .order_by(FuturesOutcome.current_probability.desc())
            .limit(1)
        )
        current_prob = prob_result.scalar()

    return {
        "challenge_code": challenge.challenge_code,
        "market_name": challenge.market_name,
        "market_id": challenge.market_id,
        "creator_guess": challenge.creator_guess,
        "threshold": challenge.creator_threshold,
        "friend_guess": challenge.friend_guess,
        "current_probability": float(current_prob) if current_prob is not None else None,
        "creator_correct": challenge.creator_correct,
        "friend_correct": challenge.friend_correct,
        "resolved_at": challenge.resolved_at.isoformat() if challenge.resolved_at else None,
        "created_at": challenge.created_at.isoformat() if challenge.created_at else None,
    }


@router.post("/{code}/accept")
async def accept_challenge(code: str, body: AcceptChallengeRequest, request: Request):
    """Friend submits their guess on a challenge."""
    if body.guess not in ("higher", "lower"):
        raise HTTPException(status_code=400, detail="guess must be 'higher' or 'lower'")

    session_id = request.cookies.get("session_id") or request.headers.get("x-session-id")

    async with get_session() as db:
        result = await db.execute(
            select(PredictionChallenge)
            .where(PredictionChallenge.challenge_code == code)
        )
        challenge = result.scalar()
        if not challenge:
            raise HTTPException(status_code=404, detail="Challenge not found")

        if challenge.friend_guess is not None:
            raise HTTPException(status_code=409, detail="Challenge already accepted")

        challenge.friend_guess = body.guess
        challenge.friend_session_id = session_id

        # Check current probability and evaluate both guesses
        prob_result = await db.execute(
            select(FuturesOutcome.current_probability)
            .where(FuturesOutcome.market_id == challenge.market_id)
            .order_by(FuturesOutcome.current_probability.desc())
            .limit(1)
        )
        current_prob = prob_result.scalar()
        if current_prob is not None:
            actual_pct = int(float(current_prob) * 100)
            challenge.actual_probability = float(current_prob)
            challenge.creator_correct = (
                (challenge.creator_guess == "higher" and actual_pct > challenge.creator_threshold)
                or (challenge.creator_guess == "lower" and actual_pct < challenge.creator_threshold)
            )
            challenge.friend_correct = (
                (body.guess == "higher" and actual_pct > challenge.creator_threshold)
                or (body.guess == "lower" and actual_pct < challenge.creator_threshold)
            )

        await db.commit()

    return {
        "status": "accepted",
        "challenge_code": code,
        "friend_guess": body.guess,
        "actual_probability": float(current_prob) if current_prob is not None else None,
        "creator_correct": challenge.creator_correct,
        "friend_correct": challenge.friend_correct,
    }
