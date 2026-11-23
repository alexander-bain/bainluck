"""Read-only interest suggestions for the unreleased first-run sentence box."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.routes.user import teams_by_location
from app.services import get_db
from app.services.onboarding_interest_sentences import (
    InterestChip,
    read_sentence,
    resolve_interests,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/onboarding/interests",
    response_model=list[InterestChip],
    response_model_exclude_none=True,
)
async def onboarding_interests(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> list[InterestChip]:
    """Suggest reader-confirmable interests without saving the sentence or chips."""
    response.headers["Cache-Control"] = "no-store"

    async def city_team_ids(city: str) -> list[int]:
        return [team.id for team in await teams_by_location(city, db)]

    try:
        sentence = await read_sentence(request)
        return await resolve_interests(sentence, db, city_team_ids)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "Onboarding interest lookup failed reason=%s", type(exc).__name__
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "sentence_unavailable", "fallback": "search"},
            headers={"Cache-Control": "no-store"},
        ) from None
