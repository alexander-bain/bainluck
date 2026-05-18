"""Task helpers for bug report lifecycle notification emails.

This module owns only the task plumbing for "your bug was fixed" emails:
eligibility gates, prompt input construction, and injectable side-effect seams.
"""

from __future__ import annotations

import base64
import html
import inspect
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import BugReport

logger = logging.getLogger(__name__)

GMAIL_CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN")
GMAIL_SENDER_EMAIL = os.environ.get("GMAIL_SENDER_EMAIL", "bugs@bainluck.com")

BUG_FIXED_EMAIL_SUBJECT = "Your bug report was fixed"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_HEADER_CONTROL_RE = re.compile(r"[\r\n]")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_BLOCK_END_RE = re.compile(r"</(?:p|div|li|h[1-6])\s*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class BugFixedEmailPromptInput:
    """Structured input for the future LLM-generated notification body."""

    first_name: str
    description: str
    resolution_summary: str


EmailBodyGenerator = Callable[[BugFixedEmailPromptInput], str | Awaitable[str]]
EmailSender = Callable[..., bool | Awaitable[bool]]
NotificationMarker = Callable[[AsyncSession, int, datetime], None | Awaitable[None]]


def _valid_user_email(user_email: Optional[str]) -> bool:
    """Return whether the report has a usable recipient email."""
    if not user_email:
        return False
    cleaned = user_email.strip()
    return not _HEADER_CONTROL_RE.search(cleaned) and bool(_EMAIL_RE.match(cleaned))


def _safe_header_value(value: str, field_name: str) -> str:
    """Reject CR/LF header injection before building a MIME message."""
    if _HEADER_CONTROL_RE.search(value):
        raise ValueError(f"{field_name} contains invalid header characters")
    return value


def _html_to_plain_text(body_html: str) -> str:
    """Convert the simple notification HTML into a readable plain-text part."""
    with_breaks = _BR_RE.sub("\n", body_html)
    with_breaks = _BLOCK_END_RE.sub("\n", with_breaks)
    without_tags = _TAG_RE.sub("", with_breaks)
    unescaped = html.unescape(without_tags)

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in unescaped.splitlines()]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = not line
        if is_blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = is_blank
    return "\n".join(collapsed).strip()


def _build_gmail_message(to_email: str, subject: str, body_html: str) -> EmailMessage:
    """Build a multipart Gmail message with validated headers."""
    recipient = to_email.strip()
    sender_email = GMAIL_SENDER_EMAIL.strip()

    if not _valid_user_email(recipient):
        raise ValueError("recipient email is invalid")
    if not _valid_user_email(sender_email):
        raise ValueError("Gmail sender email is invalid")

    message = EmailMessage()
    message["To"] = recipient
    message["From"] = formataddr(("Bain Luck", sender_email))
    message["Subject"] = _safe_header_value(subject, "subject")
    message["Auto-Submitted"] = "auto-generated"
    message["Precedence"] = "bulk"
    message["X-Auto-Response-Suppress"] = "All"
    message.set_content(_html_to_plain_text(body_html))
    message.add_alternative(body_html, subtype="html")
    return message


def _derive_first_name(user_email: str, app_state: Optional[dict[str, Any]]) -> str:
    """Prefer the app-captured user name, then fall back to the email local part."""
    if app_state:
        raw_name = app_state.get("user_name")
        if isinstance(raw_name, str) and raw_name.strip():
            return raw_name.strip().split()[0]

    local_part = user_email.split("@", 1)[0]
    first_token = re.split(r"[._+-]", local_part)[0]
    return first_token.capitalize() if first_token else "there"


def build_bug_fixed_email_prompt_input(report: BugReport) -> BugFixedEmailPromptInput:
    """Build the stable LLM prompt input from a bug report row."""
    user_email = (report.user_email or "").strip()
    app_state = report.app_state if isinstance(report.app_state, dict) else None
    return BugFixedEmailPromptInput(
        first_name=_derive_first_name(user_email, app_state),
        description=(report.description or "a bug").strip() or "a bug",
        resolution_summary=(
            report.resolution_summary
            or "We looked into it and shipped a fix."
        ).strip(),
    )


def build_bug_fixed_email_prompt_body(
    prompt_input: BugFixedEmailPromptInput,
) -> str:
    """Build the body prompt that will be sent to the LLM integration."""
    return (
        f"Write a short email to {prompt_input.first_name} thanking them for "
        "reporting a bug in Bain Luck.\n\n"
        f"Bug they reported: \"{prompt_input.description}\"\n\n"
        f"What we fixed: \"{prompt_input.resolution_summary}\"\n\n"
        "Tone: personal, grateful, specific, and concise. Do not include jokes, "
        "puns, or quips. End with encouragement to keep reporting bugs. "
        "Just the body text; no subject line, greeting, or sign-off."
    )


def _generate_email_body(
    first_name: str, description: str, resolution_summary: str
) -> str:
    """Generate the notification body, falling back to a deterministic template."""
    prompt_input = BugFixedEmailPromptInput(
        first_name=first_name,
        description=description,
        resolution_summary=resolution_summary,
    )
    try:
        import openai

        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write short, warm emails for Bain Luck, a prediction market discovery app. "
                        "Never reference gambling or betting. Keep it to 4-5 sentences."
                    ),
                },
                {
                    "role": "user",
                    "content": build_bug_fixed_email_prompt_body(prompt_input),
                },
            ],
            max_tokens=200,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("OpenAI email generation failed, using template: %s", exc)
        return (
            f"You reported \"{description[:100]}\" and we fixed it. "
            f"{resolution_summary} "
            "Thanks for helping make Bain Luck better. Keep sending reports when something looks off."
        )


def _get_access_token() -> str:
    import requests

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": GMAIL_CLIENT_ID,
            "client_secret": GMAIL_CLIENT_SECRET,
            "refresh_token": GMAIL_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _send_gmail(to_email: str, subject: str, body_html: str) -> bool:
    """Send an email through Gmail OAuth.

    Kept as a small side-effect seam so task tests can inject a fake sender.
    """
    if not all([GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN]):
        logger.warning("Gmail OAuth not configured, skipping email send")
        return False

    try:
        import requests

        access_token = _get_access_token()

        message = _build_gmail_message(to_email, subject, body_html)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        resp = requests.post(
            f"https://gmail.googleapis.com/gmail/v1/users/{GMAIL_SENDER_EMAIL}/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Bug fix email sent to %s", to_email)
        return True
    except Exception as exc:
        logger.error("Failed to send bug fix email to %s: %s", to_email, exc)
        return False


def format_bug_fixed_email_html(first_name: str, body_text: str) -> str:
    """Format the generated notification body as the final email HTML."""
    safe_name = html.escape(first_name)
    safe_body = html.escape(body_text).replace("\n", "<br>")
    return f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; color: #1a1a1a;">
        <p style="font-size: 15px; line-height: 1.6;">Hi {safe_name},</p>
        <p style="font-size: 15px; line-height: 1.6;">{safe_body}</p>
        <p style="font-size: 15px; line-height: 1.6;">
            <a href="https://bainluck.com" style="color: #2563eb; text-decoration: none; font-weight: 600;">Open Bain Luck</a>
        </p>
        <p style="font-size: 13px; color: #6b7280; margin-top: 24px;">The Bain Luck team</p>
    </div>
    """


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _mark_notification_sent(
    db: AsyncSession, report_id: int, sent_at: datetime
) -> None:
    await db.execute(
        update(BugReport)
        .where(BugReport.id == report_id)
        .values(notification_sent_at=sent_at)
    )
    await db.commit()


async def send_bug_fixed_email(
    report_id: int,
    db: AsyncSession,
    *,
    generate_body: Optional[EmailBodyGenerator] = None,
    send_email: Optional[EmailSender] = None,
    mark_notification_sent: Optional[NotificationMarker] = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> bool:
    """Look up a bug report and send a fixed-bug notification if eligible."""
    result = await db.execute(select(BugReport).where(BugReport.id == report_id))
    report = result.scalar_one_or_none()

    if not report:
        logger.warning("Bug report %d not found", report_id)
        return False

    if not _valid_user_email(report.user_email):
        logger.info("Bug report %d has no valid user email, skipping", report_id)
        return False

    if report.notification_sent_at:
        logger.info("Bug report %d already notified, skipping", report_id)
        return False

    prompt_input = build_bug_fixed_email_prompt_input(report)
    generator = generate_body or (
        lambda prompt: _generate_email_body(
            prompt.first_name,
            prompt.description,
            prompt.resolution_summary,
        )
    )
    body_text = await _maybe_await(generator(prompt_input))
    body_html = format_bug_fixed_email_html(prompt_input.first_name, body_text)

    sender = send_email or _send_gmail
    success = await _maybe_await(
        sender(
            to_email=report.user_email.strip(),
            subject=BUG_FIXED_EMAIL_SUBJECT,
            body_html=body_html,
        )
    )

    if not success:
        return False

    marker = mark_notification_sent or _mark_notification_sent
    await _maybe_await(marker(db, report_id, now_fn()))
    return True
