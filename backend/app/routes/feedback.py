"""Bug report submission API for rage shake feature."""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator as pydantic_field_validator
from sqlalchemy import select, update, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.auth import get_optional_user
from app.models.models import BugReport, User
from app.services import get_db, get_db_rw

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


BUG_REPORT_CATEGORIES = {
    "ui",
    "data_quality",
    "performance",
    "feature_request",
    "ios",
    "other",
}

_CATEGORY_PATTERNS = {
    "feature_request": [
        (
            r"\b(feature request|please add|can you add|could you add|"
            r"would like|i wish|support for)\b"
        ),
        (
            r"\b(add|allow|let me|need a way to|want to)\b.*\b("
            r"filter|sort|search|pin|share|export|custom|favorite)\b"
        ),
    ],
    "data_quality": [
        (
            r"\b(wrong|incorrect|inaccurate|bad|stale|outdated|missing|"
            r"duplicate|mismatch|mismatched)\b.*\b(odds|probabilit(?:y|ies)|"
            r"score|team|player|market|data|line|spread|total|game|event)\b"
        ),
        (
            r"\b(odds|probabilit(?:y|ies)|score|team|player|market|data|"
            r"line|spread|total|game|event)\b.*\b(wrong|incorrect|inaccurate|"
            r"bad|stale|outdated|missing|duplicate|mismatch|mismatched)\b"
        ),
        (
            r"\b(not updating|hasn'?t updated|old odds|bad match|wrong team|"
            r"wrong player|wrong score|missing game|missing market)\b"
        ),
    ],
    "performance": [
        (
            r"\b(slow|lag|laggy|freez(?:e|es|ing)|hang(?:s|ing)?|stuck|"
            r"timeout|timed out|loading forever)\b"
        ),
        (
            r"\b(crash(?:es|ed|ing)?|unresponsive|spinning|spinner|"
            r"takes forever|won'?t load|doesn'?t load)\b"
        ),
    ],
    "ios": [
        (
            r"\b(ios|iphone|ipad|testflight|swiftui|apple sign[- ]?in|"
            r"face id|touch id|keychain|push notification|apns)\b"
        ),
        r"\b(native app|mobile app|macos|mac app)\b",
    ],
    "ui": [
        (
            r"\b(layout|button|text|label|font|color|image|card|modal|sheet|"
            r"chart|nav|navigation|tab|screen|view)\b.*\b(broken|blank|"
            r"cut off|overlap|overlapping|hidden|unreadable|misaligned|"
            r"cropped|too small|too large|doesn'?t fit)\b"
        ),
        (
            r"\b(broken|blank|cut off|overlap|overlapping|hidden|unreadable|"
            r"misaligned|cropped|too small|too large|doesn'?t fit)\b.*\b("
            r"layout|button|text|label|font|color|image|card|modal|sheet|"
            r"chart|nav|navigation|tab|screen|view)\b"
        ),
        r"\b(can'?t tap|tap target|visual bug|looks wrong|display issue|render(?:ing)? issue)\b",
    ],
}

_CATEGORY_TIEBREAK = [
    "feature_request",
    "data_quality",
    "performance",
    "ios",
    "ui",
]


def _flatten_app_state_text(value: object, *, depth: int = 0, limit: int = 80) -> list[str]:
    if value is None or depth > 3 or limit <= 0:
        return []
    if isinstance(value, dict):
        parts: list[str] = []
        for key, child in value.items():
            if len(parts) >= limit:
                break
            if isinstance(key, str):
                parts.append(key)
            parts.extend(
                _flatten_app_state_text(
                    child,
                    depth=depth + 1,
                    limit=limit - len(parts),
                )
            )
        return parts[:limit]
    if isinstance(value, (list, tuple)):
        parts = []
        for child in value:
            if len(parts) >= limit:
                break
            parts.extend(
                _flatten_app_state_text(
                    child,
                    depth=depth + 1,
                    limit=limit - len(parts),
                )
            )
        return parts[:limit]
    if isinstance(value, (str, int, float, bool)):
        return [str(value)]
    return []


def categorize_bug_report(
    description: str | None,
    app_state: dict | None = None,
) -> str:
    """Deterministically assign the first-pass admin category for a bug report."""
    parts = [description or ""]
    parts.extend(_flatten_app_state_text(app_state))
    text = " ".join(parts).lower()
    text = re.sub(r"[_\-/]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return "other"

    scores = {category: 0 for category in BUG_REPORT_CATEGORIES if category != "other"}
    for category, patterns in _CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                scores[category] += 1

    # Platform context is useful, but should not override a clear report type.
    if re.search(
        r"\b(platform|device|os|system name)\b.{0,40}\b(ios|iphone|ipad|macos)\b",
        text,
    ):
        scores["ios"] += 1

    top_score = max(scores.values(), default=0)
    if top_score <= 0:
        return "other"

    for category in _CATEGORY_TIEBREAK:
        if scores[category] == top_score:
            return category
    return "other"


class BugReportSubmission(BaseModel):
    description: Optional[str] = None
    screenshot_base64: Optional[str] = None
    app_state: Optional[dict] = None
    notify_on_fix: bool = False

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
    db: AsyncSession = Depends(get_db_rw),
    user: User | None = Depends(get_optional_user),
):
    session_id = request.headers.get("x-session-id")
    user_id = user.id if user else None

    user_email = user.email if user else None

    report = BugReport(
        user_id=user_id,
        user_email=user_email,
        session_id=session_id,
        description=body.description,
        screenshot_base64=body.screenshot_base64,
        app_state=body.app_state,
        status="new",
        category=categorize_bug_report(body.description, body.app_state),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    logger.info(
        "Bug report #%d submitted (user=%s, session=%s, desc=%s)",
        report.id, user_id, session_id,
        (body.description or "")[:50],
    )

    return {"status": "ok", "id": report.id, "category": report.category}
