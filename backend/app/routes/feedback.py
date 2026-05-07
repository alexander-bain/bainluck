"""Bug report submission API for rage shake feature."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator as pydantic_field_validator
from sqlalchemy import select, update, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import BugReport
from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


class BugReportSubmission(BaseModel):
    description: Optional[str] = None
    screenshot_base64: Optional[str] = None
    app_state: Optional[dict] = None

    @pydantic_field_validator("description")
    @classmethod
    def check_description_length(cls, v):
        if v and len(v) > 5000:
            raise ValueError("Description too long (max 5000 chars)")
        return v

    @pydantic_field_validator("screenshot_base64")
    @classmethod
    def check_screenshot_size(cls, v):
        if v and len(v) > 2_000_000:
            raise ValueError("Screenshot too large (max ~1.5MB)")
        return v

    @pydantic_field_validator("app_state")
    @classmethod
    def check_app_state_size(cls, v):
        if v:
            import json
            if len(json.dumps(v)) > 50_000:
                raise ValueError("App state too large (max 50KB)")
        return v


@router.post("/bug-report")
async def submit_bug_report(
    body: BugReportSubmission,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session_id = request.headers.get("x-session-id")
    user_id = getattr(request.state, "user_id", None)

    report = BugReport(
        user_id=user_id,
        session_id=session_id,
        description=body.description,
        screenshot_base64=body.screenshot_base64,
        app_state=body.app_state,
        status="new",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    logger.info(
        "Bug report #%d submitted (user=%s, session=%s, desc=%s)",
        report.id, user_id, session_id,
        (body.description or "")[:50],
    )

    return {"status": "ok", "id": report.id}
