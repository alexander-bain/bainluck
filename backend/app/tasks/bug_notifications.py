"""Send 'your bug was fixed' emails via Gmail API + OpenAI."""

import base64
import logging
import os
from datetime import datetime, timezone
from email.mime.text import MIMEText

import requests
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import BugReport

logger = logging.getLogger(__name__)

GMAIL_CLIENT_ID = os.environ.get("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.environ.get("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = os.environ.get("GMAIL_REFRESH_TOKEN")
GMAIL_SENDER_EMAIL = os.environ.get("GMAIL_SENDER_EMAIL", "bugs@bainluck.com")


def _get_access_token() -> str:
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


def _generate_email_body(
    first_name: str, description: str, resolution_summary: str
) -> str:
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
                    "content": (
                        f"Write a short email to {first_name} thanking them for reporting a bug in Bain Luck.\n\n"
                        f"Bug they reported: \"{description}\"\n\n"
                        f"What we fixed: \"{resolution_summary}\"\n\n"
                        "Tone: personal, grateful, specific. Include a dad joke or witty quip related to the bug or prediction markets. "
                        "End with encouragement to keep reporting bugs (shake the phone!). "
                        "Just the body text — no subject line, no greeting (we add 'Hi {name}' separately), no sign-off."
                    ),
                },
            ],
            max_tokens=200,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("OpenAI email generation failed, using template: %s", e)
        return (
            f"You reported: \"{description[:100]}\" — and we fixed it! "
            f"{resolution_summary} "
            "Thanks for helping make Bain Luck better. Keep shaking that phone when something looks off!"
        )


def _send_gmail(to_email: str, subject: str, body_html: str) -> bool:
    if not all([GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN]):
        logger.warning("Gmail OAuth not configured, skipping email send")
        return False

    try:
        access_token = _get_access_token()

        message = MIMEText(body_html, "html")
        message["to"] = to_email
        message["from"] = f"Bain Luck <{GMAIL_SENDER_EMAIL}>"
        message["subject"] = subject

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
    except Exception as e:
        logger.error("Failed to send bug fix email to %s: %s", to_email, e)
        return False


async def send_bug_fixed_email(report_id: int, db: AsyncSession) -> bool:
    """Look up a bug report, generate a personal email, and send it."""
    result = await db.execute(
        select(BugReport).where(BugReport.id == report_id)
    )
    report = result.scalar_one_or_none()

    if not report:
        logger.warning("Bug report %d not found", report_id)
        return False

    if not report.user_email:
        logger.info("Bug report %d has no user email, skipping", report_id)
        return False

    if report.notification_sent_at:
        logger.info("Bug report %d already notified, skipping", report_id)
        return False

    description = report.description or "a bug"
    resolution = report.resolution_summary or "We looked into it and shipped a fix."
    first_name = report.user_email.split("@")[0].split(".")[0].capitalize()

    if report.app_state and isinstance(report.app_state, dict):
        name = report.app_state.get("user_name", "")
        if name:
            first_name = name.split()[0]

    body_text = _generate_email_body(first_name, description, resolution)

    body_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 480px; margin: 0 auto; color: #1a1a1a;">
        <p style="font-size: 15px; line-height: 1.6;">Hi {first_name},</p>
        <p style="font-size: 15px; line-height: 1.6;">{body_text}</p>
        <p style="font-size: 15px; line-height: 1.6;">
            <a href="https://bainluck.com" style="color: #2563eb; text-decoration: none; font-weight: 600;">Open Bain Luck →</a>
        </p>
        <p style="font-size: 13px; color: #6b7280; margin-top: 24px;">— The Bain Luck team 🍀</p>
    </div>
    """

    success = _send_gmail(
        to_email=report.user_email,
        subject="Your bug report was fixed 🍀",
        body_html=body_html,
    )

    if success:
        await db.execute(
            update(BugReport)
            .where(BugReport.id == report_id)
            .values(notification_sent_at=datetime.now(timezone.utc))
        )
        await db.commit()

    return success
